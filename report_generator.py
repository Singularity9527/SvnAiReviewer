"""报告生成模块

解析 AI 审查结果，生成 Markdown/JSON 格式报告，支持终端渲染和文件保存。
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 模板目录
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_REPORT_TEMPLATE = os.path.join(_TEMPLATE_DIR, "report_template.md")

# 默认报告输出目录
DEFAULT_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")


@dataclass
class ReviewResult:
    """单次审查结果的结构化数据

    汇聚 SVN 数据、AI 响应和审查内容，作为报告生成的输入。
    """

    # 版本信息
    revision: str = ""
    author: str = ""
    date: str = ""
    message: str = ""

    # 变更统计
    total_files: int = 0
    added_lines: int = 0
    removed_lines: int = 0
    file_list: List[str] = field(default_factory=list)

    # AI 审查
    review_content: str = ""
    model: str = ""
    elapsed_seconds: float = 0.0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # 元信息
    generated_at: str = ""
    status: str = "success"
    error: Optional[str] = None

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def is_success(self) -> bool:
        return self.status == "success" and self.error is None

    @staticmethod
    def from_review_data(diff_data, log_data, ai_response) -> "ReviewResult":
        """从审查数据创建 ReviewResult

        Args:
            diff_data: DiffData 对象
            log_data: LogData 对象
            ai_response: AIResponse 对象

        Returns:
            ReviewResult 实例
        """
        file_list = []
        if hasattr(diff_data, "file_diffs"):
            for fd in diff_data.file_diffs:
                file_list.append(f"- `{fd.file_path}` ({fd.status}, +{fd.added_lines}/-{fd.removed_lines})")
        elif hasattr(diff_data, "file_paths"):
            file_list = [f"- `{fp}`" for fp in diff_data.file_paths]

        return ReviewResult(
            revision=str(getattr(log_data, "revision", getattr(diff_data, "revision", ""))),
            author=getattr(log_data, "author", "") or "",
            date=getattr(log_data, "date", "") or "",
            message=getattr(log_data, "message", "") or "",
            total_files=getattr(diff_data, "total_files", len(file_list)),
            added_lines=getattr(diff_data, "total_added_lines", 0),
            removed_lines=getattr(diff_data, "total_removed_lines", 0),
            file_list=file_list,
            review_content=ai_response.content if ai_response.is_success else "",
            model=ai_response.model,
            elapsed_seconds=ai_response.elapsed_seconds,
            total_tokens=ai_response.total_tokens,
            prompt_tokens=ai_response.prompt_tokens,
            completion_tokens=ai_response.completion_tokens,
            status="success" if ai_response.is_success else "error",
            error=ai_response.error,
        )


class ReportGenerator:
    """报告生成器

    支持 Markdown 和 JSON 两种输出格式，可渲染到终端或保存为文件。

    用法示例::

        gen = ReportGenerator()

        # 从审查数据生成 Markdown
        result = ReviewResult.from_review_data(diff, log, response)
        markdown = gen.generate_markdown(result)

        # 保存到文件
        path = gen.save(result, output_format="markdown")

        # 生成 JSON
        json_str = gen.generate_json(result)
    """

    def __init__(self, output_dir: Optional[str] = None, template_path: Optional[str] = None):
        """初始化报告生成器

        Args:
            output_dir: 报告输出目录，默认 ./reports/
            template_path: 自定义报告模板路径
        """
        self._output_dir = output_dir or DEFAULT_REPORTS_DIR
        self._template_path = template_path or _REPORT_TEMPLATE
        self._template_cache: Optional[str] = None

    @property
    def output_dir(self) -> str:
        return self._output_dir

    def _load_template(self) -> str:
        """加载报告模板"""
        if self._template_cache:
            return self._template_cache

        try:
            with open(self._template_path, "r", encoding="utf-8") as f:
                self._template_cache = f.read()
            return self._template_cache
        except OSError as e:
            logger.warning("无法加载报告模板 (%s): %s, 使用默认模板", self._template_path, e)
            return self._default_template()

    @staticmethod
    def _default_template() -> str:
        """内置默认模板（模板文件不可用时的回退）"""
        return (
            "# SVN AI 代码审查报告 - 版本 {revision}\n\n"
            "> 生成时间: {generated_at}\n\n"
            "## 提交信息\n\n"
            "- 版本: {revision}\n"
            "- 作者: {author}\n"
            "- 时间: {date}\n"
            "- 日志: {message}\n\n"
            "## 变更概览\n\n"
            "- 文件数: {total_files}\n"
            "- 新增: +{added_lines}\n"
            "- 删除: -{removed_lines}\n\n"
            "{file_list}\n\n"
            "## AI 审查结果\n\n"
            "{review_content}\n"
        )

    def generate_markdown(self, result: ReviewResult) -> str:
        """生成 Markdown 格式报告

        Args:
            result: ReviewResult 审查结果

        Returns:
            str: Markdown 格式的报告文本
        """
        template = self._load_template()

        file_list_str = "\n".join(result.file_list) if result.file_list else "（无文件变更信息）"

        try:
            report = template.format(
                revision=f"r{result.revision}",
                generated_at=result.generated_at,
                author=result.author or "未知",
                date=result.date or "未知",
                message=result.message or "（空）",
                total_files=result.total_files,
                added_lines=result.added_lines,
                removed_lines=result.removed_lines,
                file_list=file_list_str,
                model=result.model or "未知",
                elapsed=f"{result.elapsed_seconds:.1f}",
                tokens=f"{result.total_tokens:,}",
                review_content=result.review_content or "（无审查内容）",
            )
        except KeyError as e:
            logger.warning("模板中存在未知占位符: %s, 使用简单格式", e)
            report = self._generate_simple_markdown(result)

        return report

    def _generate_simple_markdown(self, result: ReviewResult) -> str:
        """简单 Markdown 格式（模板解析失败时回退）"""
        lines = [
            f"# SVN AI 代码审查报告 - 版本 r{result.revision}",
            "",
            f"> 生成时间: {result.generated_at}",
            "",
            "## 提交信息",
            "",
            f"- **版本号**: r{result.revision}",
            f"- **作者**: {result.author or '未知'}",
            f"- **时间**: {result.date or '未知'}",
            f"- **日志**: {result.message or '（空）'}",
            "",
            "## 变更概览",
            "",
            f"- 文件数: {result.total_files}",
            f"- 变更: +{result.added_lines}/-{result.removed_lines}",
            "",
        ]

        if result.file_list:
            lines.append("### 变更文件列表")
            lines.append("")
            lines.extend(result.file_list)
            lines.append("")

        lines.append("## AI 审查结果")
        lines.append("")
        lines.append(result.review_content or "（无审查内容）")
        lines.append("")

        return "\n".join(lines)

    def generate_json(self, result: ReviewResult, pretty: bool = True) -> str:
        """生成 JSON 格式报告

        Args:
            result: ReviewResult 审查结果
            pretty: 是否格式化输出

        Returns:
            str: JSON 格式的报告文本
        """
        data = {
            "status": result.status,
            "revision": f"r{result.revision}",
            "generated_at": result.generated_at,
            "commit": {
                "author": result.author,
                "date": result.date,
                "message": result.message,
            },
            "changes": {
                "total_files": result.total_files,
                "added_lines": result.added_lines,
                "removed_lines": result.removed_lines,
                "files": result.file_list,
            },
            "ai": {
                "model": result.model,
                "elapsed_seconds": round(result.elapsed_seconds, 2),
                "tokens": {
                    "total": result.total_tokens,
                    "prompt": result.prompt_tokens,
                    "completion": result.completion_tokens,
                },
            },
            "review": result.review_content,
        }

        if result.error:
            data["error"] = result.error

        indent = 2 if pretty else None
        return json.dumps(data, ensure_ascii=False, indent=indent)

    def save(
        self,
        result: ReviewResult,
        output_format: str = "markdown",
        output_path: Optional[str] = None,
    ) -> str:
        """保存报告到文件

        Args:
            result: ReviewResult 审查结果
            output_format: 输出格式 ("markdown" 或 "json")
            output_path: 自定义输出路径，None 则自动生成

        Returns:
            str: 保存的文件路径
        """
        if output_path is None:
            output_path = self._generate_filename(result, output_format)

        # 生成报告内容
        if output_format == "json":
            content = self.generate_json(result)
        else:
            content = self.generate_markdown(result)

        # 确保目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("报告已保存: %s", output_path)
        return output_path

    def _generate_filename(self, result: ReviewResult, output_format: str) -> str:
        """生成报告文件名

        格式: review_r{版本号}_{时间戳}.{扩展名}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "json" if output_format == "json" else "md"
        revision = result.revision.replace(":", "-") if result.revision else "unknown"
        filename = f"review_r{revision}_{timestamp}.{ext}"
        return os.path.join(self._output_dir, filename)

    def render_terminal(self, result: ReviewResult) -> None:
        """在终端渲染报告（使用 rich 库）

        Args:
            result: ReviewResult 审查结果
        """
        from rich.console import Console
        console = Console()
        self._render_with_console(result, console)

    def _render_with_console(self, result: ReviewResult, console) -> None:
        """使用指定的 Console 对象渲染报告

        Args:
            result: ReviewResult 审查结果
            console: rich.console.Console 实例
        """
        from rich.markdown import Markdown
        from rich.panel import Panel
        from rich.table import Table
        console.print()
        console.print(
            Panel(
                f"[bold]SVN AI 代码审查报告 - 版本 r{result.revision}[/bold]",
                style="blue",
            )
        )

        # 提交信息表格
        info_table = Table(title="提交信息", show_header=True, header_style="bold cyan")
        info_table.add_column("项目", style="bold")
        info_table.add_column("内容")
        info_table.add_row("版本号", f"r{result.revision}")
        info_table.add_row("作者", result.author or "未知")
        info_table.add_row("时间", result.date or "未知")
        info_table.add_row("日志", result.message[:100] if result.message else "（空）")
        console.print(info_table)

        # 变更统计
        stat_table = Table(title="变更概览", show_header=True, header_style="bold cyan")
        stat_table.add_column("项目", style="bold")
        stat_table.add_column("数据")
        stat_table.add_row("文件数", str(result.total_files))
        stat_table.add_row("新增行数", f"[green]+{result.added_lines}[/green]")
        stat_table.add_row("删除行数", f"[red]-{result.removed_lines}[/red]")
        console.print(stat_table)

        # 文件列表
        if result.file_list:
            console.print("\n[bold]变更文件:[/bold]")
            for f_item in result.file_list:
                console.print(f"  {f_item}")

        # AI 信息
        console.print(
            f"\n[blue]►[/blue] AI 模型: {result.model}  |  "
            f"耗时: {result.elapsed_seconds:.1f}s  |  "
            f"Token: {result.total_tokens:,}"
        )

        # 审查内容
        console.print()
        if result.review_content:
            console.print(Panel("[bold]审查结果[/bold]", style="green"))
            console.print(Markdown(result.review_content))
        else:
            console.print("[yellow]（无审查内容）[/yellow]")

        console.print()

