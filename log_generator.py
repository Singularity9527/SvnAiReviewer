"""自动生成提交日志模块

根据 SVN 工作区的代码变更，调用 AI 自动生成规范的提交日志候选项。
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_COMMIT_LOG_PROMPT = os.path.join(_TEMPLATE_DIR, "commit_log_prompt.md")


@dataclass
class LogCandidate:
    """单条候选提交日志"""

    index: int
    """候选编号（1-based）"""

    title: str
    """标题行"""

    body: str = ""
    """详细描述（可选）"""

    @property
    def full_message(self) -> str:
        """完整的提交日志"""
        if self.body:
            return f"{self.title}\n\n{self.body}"
        return self.title

    def __str__(self) -> str:
        return self.full_message


@dataclass
class GenerateResult:
    """日志生成结果"""

    candidates: List[LogCandidate] = field(default_factory=list)
    """候选日志列表"""

    raw_response: str = ""
    """AI 原始返回"""

    diff_summary: str = ""
    """变更摘要"""

    error: Optional[str] = None
    """错误信息"""

    @property
    def is_success(self) -> bool:
        return self.error is None and len(self.candidates) > 0


class LogGenerator:
    """提交日志生成器

    调用 AI 根据当前工作区变更生成候选提交日志。

    用法示例::

        from svn_client import SVNClient
        from ai_provider.factory import ProviderFactory

        svn = SVNClient()
        provider = ProviderFactory.create_from_config(config)
        gen = LogGenerator(svn, provider)

        result = gen.generate()
        for c in result.candidates:
            print(f"[{c.index}] {c.title}")
    """

    def __init__(self, svn_client, provider, template_path: Optional[str] = None):
        """初始化日志生成器

        Args:
            svn_client: SVNClient 实例
            provider: AIProvider 实例
            template_path: 自定义 Prompt 模板路径
        """
        self._svn = svn_client
        self._provider = provider
        self._template_path = template_path or _COMMIT_LOG_PROMPT
        self._template_cache: Optional[str] = None

    def generate(self, max_diff_chars: int = 30000) -> GenerateResult:
        """生成候选提交日志

        Args:
            max_diff_chars: Diff 最大字符数（超长时截断）

        Returns:
            GenerateResult: 生成结果
        """
        # 1. 获取工作区未提交变更（优先使用 svn diff 无版本参数）
        try:
            diff_data = self._get_working_diff()
        except Exception:
            # 回退到 BASE:HEAD
            try:
                diff_data = self._svn.get_diff("BASE:HEAD")
            except Exception as e:
                return GenerateResult(error=f"获取工作区变更失败: {e}")

        if diff_data.is_empty:
            # 再尝试 BASE:HEAD（可能有远程更新）
            try:
                diff_data = self._svn.get_diff("BASE:HEAD")
            except Exception:
                pass

        if diff_data.is_empty:
            return GenerateResult(error="工作区没有未提交的变更")

        # 2. 构建变更摘要
        diff_text = diff_data.raw_diff or ""
        if len(diff_text) > max_diff_chars:
            diff_text = diff_text[:max_diff_chars] + "\n\n... (diff 内容已截断) ..."
            logger.info("Diff 内容已截断: %d → %d 字符", len(diff_data.raw_diff), max_diff_chars)

        file_summary = diff_data.summary() if hasattr(diff_data, "summary") else ""

        # 3. 构建 Prompt
        system_prompt = self._load_template()
        user_prompt = self._build_user_prompt(diff_text, file_summary)

        # 4. 调用 AI
        response = self._provider.chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        if not response.is_success:
            return GenerateResult(
                raw_response=response.content,
                diff_summary=file_summary,
                error=f"AI 推理失败: {response.error}",
            )

        # 5. 解析候选日志
        candidates = self._parse_candidates(response.content)

        return GenerateResult(
            candidates=candidates,
            raw_response=response.content,
            diff_summary=file_summary,
        )

    def _get_working_diff(self):
        """获取工作区未提交变更的 diff"""
        # 使用 _run_command 直接调用 svn diff（无版本参数）
        from models.diff_data import DiffData

        try:
            stdout, _ = self._svn._run_command(["diff"])
        except Exception as e:
            return DiffData(revision="WORKING", raw_diff="", file_diffs=[], error=str(e))

        file_diffs = self._svn._parse_diff_output(stdout)
        return DiffData(
            revision="WORKING",
            raw_diff=stdout,
            file_diffs=file_diffs,
        )

    def _load_template(self) -> str:
        """加载 Prompt 模板"""
        if self._template_cache:
            return self._template_cache

        try:
            with open(self._template_path, "r", encoding="utf-8") as f:
                self._template_cache = f.read()
            return self._template_cache
        except OSError as e:
            logger.warning("无法加载模板 (%s): %s", self._template_path, e)
            return self._default_template()

    @staticmethod
    def _default_template() -> str:
        """内置默认模板"""
        return (
            "你是一位资深软件工程师。根据以下代码变更，生成 3 个候选提交日志。\n"
            "每个候选用 '--- 候选 N ---' 分隔，包含一行标题和可选的详细描述。\n"
            "使用中文撰写，标题不超过 72 字符。"
        )

    @staticmethod
    def _build_user_prompt(diff_text: str, file_summary: str) -> str:
        """构建用户 Prompt"""
        parts = []

        if file_summary:
            parts.append(f"## 变更概览\n\n{file_summary}")

        parts.append(f"## 代码变更 (diff)\n\n```diff\n{diff_text}\n```")
        parts.append("\n请根据以上变更，生成 3 个候选提交日志。")

        return "\n\n".join(parts)

    @staticmethod
    def _parse_candidates(ai_response: str) -> List[LogCandidate]:
        """解析 AI 返回的候选日志

        支持格式:
            --- 候选 1 ---
            标题行
            详细描述...

            --- 候选 2 ---
            ...
        """
        candidates = []

        # 按 "--- 候选 N ---" 分割
        pattern = r"---\s*候选\s*(\d+)\s*---"
        parts = re.split(pattern, ai_response)

        # parts: [前文, "1", 内容1, "2", 内容2, "3", 内容3]
        i = 1
        while i < len(parts) - 1:
            try:
                index = int(parts[i])
            except (ValueError, IndexError):
                i += 2
                continue

            content = parts[i + 1].strip()
            if content:
                lines = content.split("\n", 1)
                title = lines[0].strip()
                body = lines[1].strip() if len(lines) > 1 else ""

                # 清理 title 中可能的 markdown 格式
                title = title.lstrip("#").strip()
                title = title.strip("`").strip()

                if title:
                    candidates.append(LogCandidate(
                        index=index,
                        title=title,
                        body=body,
                    ))

            i += 2

        # 如果解析失败，尝试整体作为单条日志
        if not candidates and ai_response.strip():
            lines = ai_response.strip().split("\n", 1)
            title = lines[0].strip().lstrip("#").strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            if title:
                candidates.append(LogCandidate(index=1, title=title, body=body))

        return candidates
