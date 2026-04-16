"""SVN Log 数据模型

定义提交日志的结构化数据类型，用于在各模块间传递 Log 信息。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class LogData:
    """SVN 提交日志数据"""

    revision: str
    """版本号"""

    author: str
    """提交作者"""

    date: str
    """提交时间（原始字符串）"""

    message: str
    """提交日志信息"""

    changed_paths: List[str] = field(default_factory=list)
    """变更文件路径列表"""

    error: Optional[str] = None
    """获取 log 时的错误信息（如有）"""

    @property
    def parsed_date(self) -> Optional[datetime]:
        """尝试解析日期字符串为 datetime 对象"""
        formats = [
            "%Y-%m-%d %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(self.date, fmt)
            except ValueError:
                continue
        return None

    @property
    def is_empty_message(self) -> bool:
        """提交日志是否为空"""
        return not self.message or self.message.strip() == ""

    def summary(self) -> str:
        """生成日志摘要"""
        msg_preview = self.message[:50] + "..." if len(self.message) > 50 else self.message
        return f"r{self.revision} | {self.author} | {self.date} | {msg_preview}"

    def __str__(self) -> str:
        return self.summary()
