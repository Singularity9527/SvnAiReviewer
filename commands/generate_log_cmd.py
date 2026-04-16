"""generate-log 命令实现

根据当前工作区变更，调用 AI 自动生成候选提交日志。
"""
import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from svn_client import SVNClient, SVNClientError
from ai_provider.factory import ProviderFactory
from ai_provider.base import AIProviderError
from config_manager import ConfigManager, ConfigError
from log_generator import LogGenerator

console = Console()


@click.command("generate-log")
@click.option("--working-dir", "-d", default=None, help="SVN 工作副本目录")
@click.option("--max-chars", default=30000, type=int, help="Diff 最大字符数")
@click.option("--copy", "-c", is_flag=True, default=False, help="自动复制选中日志到剪贴板")
@click.option("--raw", is_flag=True, default=False, help="显示 AI 原始返回（调试用）")
def generate_log_command(working_dir, max_chars, copy, raw):
    """根据工作区变更自动生成提交日志

    分析当前 SVN 工作区中未提交的代码变更，
    调用 AI 生成多个候选提交日志供选择。

    示例:

      svn-ai generate-log

      svn-ai generate-log -d /path/to/working-copy
    """
    try:
        _do_generate_log(working_dir, max_chars, copy, raw)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]✗ 未预期的错误:[/red] {e}")
        sys.exit(1)


def _do_generate_log(working_dir, max_chars, copy_to_clipboard, show_raw):
    """执行日志生成的核心逻辑"""

    console.print(Panel("[bold]SVN AI 智能提交日志生成[/bold]", style="blue"))

    # 1. 初始化 SVN
    try:
        with console.status("[bold blue]初始化 SVN 客户端...[/bold blue]"):
            svn = SVNClient(working_dir=working_dir)
        console.print("[green]✓[/green] SVN 客户端就绪")
    except SVNClientError as e:
        console.print(f"[red]✗ SVN 错误:[/red] {e}")
        sys.exit(1)

    # 2. 加载配置
    try:
        mgr = ConfigManager()
        config = mgr.load()
        mgr.validate_or_raise()
    except ConfigError as e:
        console.print(f"[red]✗ {e}[/red]")
        console.print("请先运行 [bold]svn-ai config[/bold] 创建配置。")
        sys.exit(1)

    # 3. 创建 AI Provider
    try:
        provider = ProviderFactory.create_from_config(config)
    except AIProviderError as e:
        console.print(f"[red]✗ AI 配置错误:[/red] {e}")
        sys.exit(1)

    console.print(f"[blue]►[/blue] AI 模型: {provider.config.model}")

    # 4. 调用日志生成器
    gen = LogGenerator(svn, provider)

    with console.status("[bold blue]AI 正在分析变更并生成提交日志...[/bold blue]"):
        result = gen.generate(max_diff_chars=max_chars)

    if not result.is_success:
        console.print(f"[red]✗ {result.error}[/red]")
        sys.exit(1)

    # 5. 显示 AI 原始返回（调试用）
    if show_raw:
        console.print("\n[bold]═══ AI 原始返回 ═══[/bold]")
        console.print(result.raw_response)
        console.print("[bold]═══════════════════[/bold]\n")

    # 6. 展示候选日志
    console.print()
    console.print(f"[green]✓[/green] 生成了 {len(result.candidates)} 个候选提交日志")
    console.print()

    for c in result.candidates:
        console.print(Panel(
            f"[bold]{c.title}[/bold]" + (f"\n\n{c.body}" if c.body else ""),
            title=f"候选 {c.index}",
            style="cyan",
        ))
        console.print()

    # 7. 用户选择
    if len(result.candidates) > 1:
        choices = [str(c.index) for c in result.candidates]
        choice = click.prompt(
            "请选择一个候选日志 (输入编号)",
            type=click.Choice(choices),
            default=choices[0],
        )
        selected = next(c for c in result.candidates if str(c.index) == choice)
    else:
        selected = result.candidates[0]

    console.print()
    console.print("[green]✓ 已选择:[/green]")
    console.print(f"  {selected.full_message}")
    console.print()

    # 8. 复制到剪贴板（可选）
    if copy_to_clipboard:
        try:
            import subprocess
            process = subprocess.Popen(
                ["clip"], stdin=subprocess.PIPE, shell=True
            )
            process.communicate(selected.full_message.encode("utf-8"))
            console.print("[green]✓ 已复制到剪贴板[/green]")
        except Exception:
            console.print("[yellow]⚠ 无法复制到剪贴板，请手动复制上方日志[/yellow]")
