"""Prompt 构建模块

将 SVN Diff 内容、提交日志、文件路径等信息组装成结构化 Prompt，
用于发送给 AI 模型进行代码审查。

支持功能：
- 从模板文件加载 System Prompt 和 User Prompt
- 自动组装提交信息和代码差异
- 超长文本智能截断（按 Token 数或字符数限制）
- 按文件拆分的分段审查策略
"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from models.diff_data import DiffData, FileDiff
from models.log_data import LogData

logger = logging.getLogger(__name__)

# 模板目录
_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class PromptResult:
    """Prompt 构建结果"""

    system_prompt: str
    """系统提示词"""

    user_prompt: str
    """用户提示词"""

    is_truncated: bool = False
    """内容是否被截断"""

    original_char_count: int = 0
    """原始字符数"""

    truncated_char_count: int = 0
    """截断后字符数"""

    segment_index: int = 0
    """分段索引（0 表示完整或第一段）"""

    total_segments: int = 1
    """总分段数"""

    @property
    def total_chars(self) -> int:
        """总字符数（system + user）"""
        return len(self.system_prompt) + len(self.user_prompt)

    @property
    def estimated_tokens(self) -> int:
        """估算 Token 数（中文约 1.5 字符/token，英文约 4 字符/token，取平均 2.5）"""
        return int(self.total_chars / 2.5)

    def summary(self) -> str:
        """构建摘要"""
        parts = [f"字符数={self.total_chars}, 估算Token≈{self.estimated_tokens}"]
        if self.is_truncated:
            parts.append(f"已截断({self.original_char_count}→{self.truncated_char_count})")
        if self.total_segments > 1:
            parts.append(f"分段 {self.segment_index + 1}/{self.total_segments}")
        return ", ".join(parts)


class PromptBuilder:
    """Prompt 构建器

    将 DiffData 和 LogData 组装成可发送给 AI 的 Prompt。

    用法示例::

        builder = PromptBuilder()
        result = builder.build(diff_data, log_data)
        print(result.system_prompt)
        print(result.user_prompt)

        # 带截断
        result = builder.build(diff_data, log_data, max_chars=50000)

        # 分段审查
        segments = builder.build_segments(diff_data, log_data, max_chars_per_segment=30000)
    """

    # 默认最大字符数限制（约对应 ~40K tokens）
    DEFAULT_MAX_CHARS = 100_000

    def __init__(
        self,
        templates_dir: Optional[str] = None,
        system_prompt_file: str = "system_prompt.md",
        review_prompt_file: str = "review_prompt.md",
    ):
        """初始化 Prompt 构建器

        Args:
            templates_dir: 模板文件目录，默认使用项目内置模板
            system_prompt_file: 系统提示词文件名
            review_prompt_file: 审查提示词模板文件名
        """
        self.templates_dir = Path(templates_dir) if templates_dir else _TEMPLATES_DIR
        self.system_prompt_file = system_prompt_file
        self.review_prompt_file = review_prompt_file

        # 加载模板
        self._system_prompt_template = self._load_template(system_prompt_file)
        self._review_prompt_template = self._load_template(review_prompt_file)

    def _load_template(self, filename: str) -> str:
        """加载模板文件

        Args:
            filename: 模板文件名

        Returns:
            str: 模板内容

        Raises:
            FileNotFoundError: 模板文件不存在
        """
        filepath = self.templates_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"模板文件不存在: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        logger.debug("加载模板: %s (%d 字符)", filename, len(content))
        return content

    def build(
        self,
        diff_data: DiffData,
        log_data: LogData,
        max_chars: Optional[int] = None,
    ) -> PromptResult:
        """构建完整的 Prompt

        Args:
            diff_data: SVN Diff 数据
            log_data: SVN 提交日志
            max_chars: 最大字符数限制（仅限 diff 内容部分），None 表示使用默认值

        Returns:
            PromptResult: 构建结果
        """
        if max_chars is None:
            max_chars = self.DEFAULT_MAX_CHARS

        # 构建系统提示词
        system_prompt = self._system_prompt_template

        # 构建文件列表
        file_list = self._build_file_list(diff_data)

        # 处理 diff 内容（可能截断）
        diff_content = diff_data.raw_diff
        original_len = len(diff_content)
        is_truncated = False

        if original_len > max_chars:
            diff_content = self._truncate_diff(diff_content, max_chars)
            is_truncated = True
            logger.warning(
                "Diff 内容已截断: %d → %d 字符", original_len, len(diff_content)
            )

        # 填充用户提示词模板
        user_prompt = self._review_prompt_template.format(
            revision=log_data.revision,
            author=log_data.author,
            date=log_data.date,
            message=log_data.message if not log_data.is_empty_message else "（无提交日志）",
            file_list=file_list,
            diff_content=diff_content,
        )

        return PromptResult(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            is_truncated=is_truncated,
            original_char_count=original_len,
            truncated_char_count=len(diff_content),
        )

    def build_segments(
        self,
        diff_data: DiffData,
        log_data: LogData,
        max_chars_per_segment: Optional[int] = None,
    ) -> List[PromptResult]:
        """按文件分段构建 Prompt（适用于超大 Diff）

        当 Diff 内容过大时，按文件拆分成多个 Prompt 段，每段包含部分文件的 Diff。

        Args:
            diff_data: SVN Diff 数据
            log_data: SVN 提交日志
            max_chars_per_segment: 每段的最大字符数

        Returns:
            List[PromptResult]: 分段 Prompt 列表
        """
        if max_chars_per_segment is None:
            max_chars_per_segment = self.DEFAULT_MAX_CHARS

        # 如果总内容不超限，直接返回完整 Prompt
        if len(diff_data.raw_diff) <= max_chars_per_segment:
            result = self.build(diff_data, log_data)
            return [result]

        # 按文件分组
        segments: List[PromptResult] = []
        current_files: List[FileDiff] = []
        current_chars = 0

        for file_diff in diff_data.file_diffs:
            file_chars = len(file_diff.diff_content)

            # 单文件超限，需要截断
            if file_chars > max_chars_per_segment:
                # 先提交当前批次
                if current_files:
                    segments.append(
                        self._build_segment(current_files, log_data, diff_data.revision)
                    )
                    current_files = []
                    current_chars = 0

                # 截断该文件
                truncated = FileDiff(
                    file_path=file_diff.file_path,
                    status=file_diff.status,
                    diff_content=self._truncate_diff(
                        file_diff.diff_content, max_chars_per_segment
                    ),
                )
                segments.append(
                    self._build_segment([truncated], log_data, diff_data.revision)
                )
                continue

            # 累加到当前批次
            if current_chars + file_chars > max_chars_per_segment and current_files:
                segments.append(
                    self._build_segment(current_files, log_data, diff_data.revision)
                )
                current_files = []
                current_chars = 0

            current_files.append(file_diff)
            current_chars += file_chars

        # 处理剩余文件
        if current_files:
            segments.append(
                self._build_segment(current_files, log_data, diff_data.revision)
            )

        # 更新分段索引
        total = len(segments)
        for i, seg in enumerate(segments):
            seg.segment_index = i
            seg.total_segments = total

        logger.info("Diff 已拆分为 %d 个分段", total)
        return segments

    def _build_segment(
        self,
        file_diffs: List[FileDiff],
        log_data: LogData,
        revision: str,
    ) -> PromptResult:
        """构建单个分段的 Prompt

        Args:
            file_diffs: 该分段包含的文件 diff 列表
            log_data: 提交日志
            revision: 版本号

        Returns:
            PromptResult: 分段 Prompt
        """
        # 组装 diff 内容
        diff_content = "\n".join(fd.diff_content for fd in file_diffs)

        # 构建文件列表
        file_list_lines = []
        for fd in file_diffs:
            status_map = {"A": "新增", "D": "删除", "M": "修改", "R": "替换"}
            status_text = status_map.get(fd.status, fd.status)
            file_list_lines.append(
                f"- `{fd.file_path}` ({status_text}, +{fd.added_lines}/-{fd.removed_lines})"
            )
        file_list = "\n".join(file_list_lines) if file_list_lines else "（无变更文件）"

        # 填充模板
        system_prompt = self._system_prompt_template
        user_prompt = self._review_prompt_template.format(
            revision=revision,
            author=log_data.author,
            date=log_data.date,
            message=log_data.message if not log_data.is_empty_message else "（无提交日志）",
            file_list=file_list,
            diff_content=diff_content,
        )

        return PromptResult(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            original_char_count=len(diff_content),
            truncated_char_count=len(diff_content),
        )

    def _build_file_list(self, diff_data: DiffData) -> str:
        """构建变更文件列表的展示文本

        Args:
            diff_data: Diff 数据

        Returns:
            str: 格式化的文件列表
        """
        if not diff_data.file_diffs:
            return "（无变更文件）"

        lines = []
        status_map = {"A": "新增", "D": "删除", "M": "修改", "R": "替换"}

        for fd in diff_data.file_diffs:
            status_text = status_map.get(fd.status, fd.status)
            lines.append(
                f"- `{fd.file_path}` ({status_text}, +{fd.added_lines}/-{fd.removed_lines})"
            )

        return "\n".join(lines)

    @staticmethod
    def _truncate_diff(content: str, max_chars: int) -> str:
        """智能截断 Diff 内容

        尽量在完整文件边界处截断，避免截断到文件 diff 中间。

        Args:
            content: 原始 diff 内容
            max_chars: 最大字符数

        Returns:
            str: 截断后的内容
        """
        if len(content) <= max_chars:
            return content

        # 预留截断提示的空间
        notice = "\n\n... [内容已截断，超出审查长度限制] ...\n"
        effective_max = max_chars - len(notice)

        if effective_max <= 0:
            return notice

        # 尝试在 "Index: " 边界处截断
        truncated = content[:effective_max]
        last_index = truncated.rfind("\nIndex: ")

        if last_index > effective_max * 0.5:
            # 在文件边界处截断
            truncated = truncated[:last_index]
        else:
            # 在行边界处截断
            last_newline = truncated.rfind("\n")
            if last_newline > 0:
                truncated = truncated[:last_newline]

        return truncated + notice

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算文本的 Token 数

        简单估算规则：
        - 中文字符: ~1.5 字符/token
        - 英文/代码: ~4 字符/token
        - 综合取平均 ~2.5 字符/token

        Args:
            text: 输入文本

        Returns:
            int: 估算的 Token 数
        """
        if not text:
            return 0

        # 统计中文字符比例
        chinese_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        total_count = len(text)

        if total_count == 0:
            return 0

        chinese_ratio = chinese_count / total_count
        # 根据中英文比例动态调整
        avg_chars_per_token = 1.5 * chinese_ratio + 4.0 * (1 - chinese_ratio)

        return int(total_count / avg_chars_per_token)
