"""SVN Diff 数据模型

定义代码差异的结构化数据类型，用于在各模块间传递 Diff 信息。
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FileDiff:
    """单个文件的差异信息"""

    file_path: str
    """变更文件的路径"""

    status: str
    """变更状态: M(修改), A(新增), D(删除), R(替换)"""

    diff_content: str
    """该文件的 diff 内容"""

    added_lines: int = 0
    """新增行数"""

    removed_lines: int = 0
    """删除行数"""

    def __post_init__(self):
        """自动统计新增/删除行数"""
        if self.diff_content and self.added_lines == 0 and self.removed_lines == 0:
            for line in self.diff_content.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    self.added_lines += 1
                elif line.startswith("-") and not line.startswith("---"):
                    self.removed_lines += 1

    @property
    def is_empty(self) -> bool:
        """判断 diff 是否为空"""
        return not self.diff_content or self.diff_content.strip() == ""

    @property
    def total_changes(self) -> int:
        """总变更行数"""
        return self.added_lines + self.removed_lines

    def __str__(self) -> str:
        return f"FileDiff({self.file_path}, {self.status}, +{self.added_lines}/-{self.removed_lines})"


@dataclass
class DiffData:
    """SVN Diff 的完整数据，包含多个文件的差异"""

    revision: str
    """版本号，如 '1024' 或 '1020:1025'"""

    raw_diff: str
    """原始 diff 输出"""

    file_diffs: List[FileDiff] = field(default_factory=list)
    """各文件的差异列表"""

    error: Optional[str] = None
    """获取 diff 时的错误信息（如有）"""

    @property
    def is_empty(self) -> bool:
        """判断整体 diff 是否为空"""
        return len(self.file_diffs) == 0 and (not self.raw_diff or self.raw_diff.strip() == "")

    @property
    def total_files(self) -> int:
        """涉及的文件总数"""
        return len(self.file_diffs)

    @property
    def total_added_lines(self) -> int:
        """所有文件的总新增行数"""
        return sum(f.added_lines for f in self.file_diffs)

    @property
    def total_removed_lines(self) -> int:
        """所有文件的总删除行数"""
        return sum(f.removed_lines for f in self.file_diffs)

    def get_file_paths(self) -> List[str]:
        """获取所有变更文件路径"""
        return [f.file_path for f in self.file_diffs]

    def summary(self) -> str:
        """生成变更摘要"""
        return (
            f"版本 r{self.revision}: "
            f"{self.total_files} 个文件变更, "
            f"+{self.total_added_lines}/-{self.total_removed_lines} 行"
        )

    def __str__(self) -> str:
        return self.summary()
