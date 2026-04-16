"""批量审查模块

支持版本范围批量审查，逐版本执行 SVN 获取 + Prompt 构建 + AI 推理流程，
汇总生成综合报告。提供进度回调和失败重试机制。
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from svn_client import SVNClient, SVNClientError
from prompt_builder import PromptBuilder
from ai_provider.base import AIProvider, AIProviderError
from report_generator import ReviewResult, ReportGenerator

logger = logging.getLogger(__name__)


@dataclass
class BatchProgress:
    """批量审查进度信息"""

    total: int = 0
    """总版本数"""

    completed: int = 0
    """已完成数"""

    failed: int = 0
    """失败数"""

    skipped: int = 0
    """跳过数（如 Diff 为空）"""

    current_revision: str = ""
    """当前处理的版本号"""

    @property
    def remaining(self) -> int:
        return self.total - self.completed - self.failed - self.skipped

    @property
    def success_count(self) -> int:
        return self.completed - self.failed

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed + self.failed + self.skipped) / self.total * 100


@dataclass
class BatchResult:
    """批量审查的最终结果"""

    results: List[ReviewResult] = field(default_factory=list)
    """各版本的审查结果列表"""

    failed_revisions: List[Dict[str, str]] = field(default_factory=list)
    """失败的版本列表 [{"revision": "1024", "error": "..."}]"""

    skipped_revisions: List[str] = field(default_factory=list)
    """跳过的版本列表（Diff 为空）"""

    total_elapsed: float = 0.0
    """总耗时（秒）"""

    @property
    def total_count(self) -> int:
        return len(self.results) + len(self.failed_revisions) + len(self.skipped_revisions)

    @property
    def success_count(self) -> int:
        return len(self.results)

    @property
    def failed_count(self) -> int:
        return len(self.failed_revisions)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_revisions)

    def generate_summary_markdown(self) -> str:
        """生成批量审查汇总 Markdown"""
        lines = [
            f"# SVN AI 批量审查报告",
            "",
            f"> 审查版本数: {self.total_count}  |  "
            f"成功: {self.success_count}  |  "
            f"失败: {self.failed_count}  |  "
            f"跳过: {self.skipped_count}  |  "
            f"总耗时: {self.total_elapsed:.1f}s",
            "",
            "---",
            "",
        ]

        # 概览表格
        lines.append("## 审查概览")
        lines.append("")
        lines.append("| 版本号 | 作者 | 日志 | 文件数 | 状态 |")
        lines.append("|--------|------|------|--------|------|")

        for r in self.results:
            msg = (r.message[:30] + "...") if len(r.message) > 30 else r.message
            lines.append(
                f"| r{r.revision} | {r.author or '未知'} | {msg or '（空）'} "
                f"| {r.total_files} | {r.status} |"
            )
        for fail in self.failed_revisions:
            lines.append(
                f"| r{fail['revision']} | - | - | - | 失败: {fail['error'][:30]} |"
            )
        for skip_rev in self.skipped_revisions:
            lines.append(f"| r{skip_rev} | - | - | 0 | 跳过（无变更） |")

        lines.append("")
        lines.append("---")
        lines.append("")

        # 各版本详细结果
        if self.results:
            lines.append("## 详细审查结果")
            lines.append("")
            for r in self.results:
                lines.append(f"### 版本 r{r.revision} - {r.author or '未知'}")
                lines.append("")
                lines.append(f"- **日志**: {r.message or '（空）'}")
                lines.append(f"- **文件数**: {r.total_files}")
                lines.append(f"- **变更**: +{r.added_lines}/-{r.removed_lines}")
                lines.append(f"- **模型**: {r.model}  |  Token: {r.total_tokens:,}")
                lines.append("")
                lines.append(r.review_content or "（无审查内容）")
                lines.append("")
                lines.append("---")
                lines.append("")

        return "\n".join(lines)

    def generate_summary_json(self) -> dict:
        """生成批量审查汇总 JSON 数据"""
        import json

        return {
            "summary": {
                "total": self.total_count,
                "success": self.success_count,
                "failed": self.failed_count,
                "skipped": self.skipped_count,
                "total_elapsed": round(self.total_elapsed, 2),
            },
            "results": [
                {
                    "revision": f"r{r.revision}",
                    "author": r.author,
                    "date": r.date,
                    "message": r.message,
                    "total_files": r.total_files,
                    "added_lines": r.added_lines,
                    "removed_lines": r.removed_lines,
                    "model": r.model,
                    "tokens": r.total_tokens,
                    "review": r.review_content,
                }
                for r in self.results
            ],
            "failed": self.failed_revisions,
            "skipped": self.skipped_revisions,
        }


# 进度回调函数类型
ProgressCallback = Callable[[BatchProgress], None]


class BatchProcessor:
    """批量审查处理器

    逐版本执行完整审查流程，支持进度回调和失败重试。

    用法示例::

        svn = SVNClient()
        provider = ProviderFactory.create_from_config(config)
        processor = BatchProcessor(svn, provider)

        result = processor.process("1020", "1025")
        print(result.generate_summary_markdown())
    """

    def __init__(
        self,
        svn_client: SVNClient,
        provider: AIProvider,
        max_retries: int = 1,
        retry_delay: float = 3.0,
        max_chars: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """初始化批量处理器

        Args:
            svn_client: SVN 客户端实例
            provider: AI Provider 实例
            max_retries: AI 调用失败时的最大重试次数
            retry_delay: 重试间隔（秒）
            max_chars: 单次 Prompt 最大字符数
            progress_callback: 进度回调函数
        """
        self._svn = svn_client
        self._provider = provider
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_chars = max_chars
        self._progress_callback = progress_callback
        self._prompt_builder = PromptBuilder()

    def process(self, start_rev: str, end_rev: str) -> BatchResult:
        """执行批量审查

        Args:
            start_rev: 起始版本号
            end_rev: 结束版本号

        Returns:
            BatchResult: 批量审查结果
        """
        batch_start = time.time()
        batch_result = BatchResult()

        # 获取版本列表
        revisions = self._svn.get_revisions_in_range(start_rev, end_rev)

        if not revisions:
            logger.warning("版本范围 %s:%s 内未找到版本", start_rev, end_rev)
            batch_result.total_elapsed = time.time() - batch_start
            return batch_result

        progress = BatchProgress(total=len(revisions))

        logger.info("开始批量审查: %s:%s, 共 %d 个版本", start_rev, end_rev, len(revisions))

        for rev in revisions:
            progress.current_revision = rev
            self._notify_progress(progress)

            result = self._process_single(rev)

            if result is None:
                # Diff 为空，跳过
                progress.skipped += 1
                batch_result.skipped_revisions.append(rev)
                logger.info("版本 r%s: Diff 为空，跳过", rev)
            elif result.error:
                # 审查失败
                progress.failed += 1
                batch_result.failed_revisions.append({
                    "revision": rev,
                    "error": result.error,
                })
                logger.warning("版本 r%s 审查失败: %s", rev, result.error)
            else:
                # 成功
                progress.completed += 1
                batch_result.results.append(result)
                logger.info("版本 r%s 审查完成", rev)

            self._notify_progress(progress)

        batch_result.total_elapsed = time.time() - batch_start
        logger.info(
            "批量审查完成: 成功=%d, 失败=%d, 跳过=%d, 耗时=%.1fs",
            batch_result.success_count,
            batch_result.failed_count,
            batch_result.skipped_count,
            batch_result.total_elapsed,
        )

        return batch_result

    def _process_single(self, revision: str) -> Optional[ReviewResult]:
        """处理单个版本的审查

        Args:
            revision: 版本号

        Returns:
            ReviewResult: 审查成功时返回结果
            None: Diff 为空时返回 None
        """
        # 获取 Diff
        try:
            diff_data = self._svn.get_diff(revision)
        except SVNClientError as e:
            return ReviewResult(
                revision=revision,
                status="error",
                error=f"获取 Diff 失败: {e}",
            )

        if diff_data.error:
            return ReviewResult(
                revision=revision,
                status="error",
                error=f"Diff 错误: {diff_data.error}",
            )

        if diff_data.is_empty:
            return None

        # 获取 Log
        try:
            log_data = self._svn.get_log(revision)
        except SVNClientError as e:
            return ReviewResult(
                revision=revision,
                status="error",
                error=f"获取 Log 失败: {e}",
            )

        # 构建 Prompt
        try:
            prompt_result = self._prompt_builder.build(
                diff_data, log_data, max_chars=self._max_chars
            )
        except Exception as e:
            return ReviewResult(
                revision=revision,
                author=getattr(log_data, "author", ""),
                status="error",
                error=f"构建 Prompt 失败: {e}",
            )

        # 调用 AI（带重试）
        response = self._call_ai_with_retry(prompt_result)

        return ReviewResult.from_review_data(diff_data, log_data, response)

    def _call_ai_with_retry(self, prompt_result):
        """调用 AI 推理，失败时重试

        Args:
            prompt_result: PromptBuilder.build() 的结果

        Returns:
            AIResponse
        """
        last_response = None

        for attempt in range(1 + self._max_retries):
            response = self._provider.chat(
                prompt=prompt_result.user_prompt,
                system_prompt=prompt_result.system_prompt,
            )

            if response.is_success:
                return response

            last_response = response
            if attempt < self._max_retries:
                logger.warning(
                    "AI 推理失败 (第%d/%d次): %s, %.1fs 后重试",
                    attempt + 1,
                    1 + self._max_retries,
                    response.error,
                    self._retry_delay,
                )
                time.sleep(self._retry_delay)

        return last_response

    def _notify_progress(self, progress: BatchProgress) -> None:
        """发送进度通知"""
        if self._progress_callback:
            try:
                self._progress_callback(progress)
            except Exception as e:
                logger.debug("进度回调异常: %s", e)
