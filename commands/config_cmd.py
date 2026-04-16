"""config 命令实现

交互式配置向导，帮助用户设置 AI 模式和连接参数。
"""
import os
import sys

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_provider.factory import ProviderFactory
from ai_provider.base import AIProviderError
from config_manager import ConfigManager, ConfigError, DEFAULT_CONFIG_PATH

console = Console()


@click.command("config")
@click.option("--show", is_flag=True, default=False, help="显示当前配置")
@click.option("--path", default=None, help="指定配置文件路径")
def config_command(show, path):
    """交互式配置向导

    设置 AI 模式、模型地址、API Key 等参数。

    示例:

      svn-ai config

      svn-ai config --show
    """
    config_path = path or DEFAULT_CONFIG_PATH

    if show:
        _show_config(config_path)
        return

    try:
        _interactive_config(config_path)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消配置[/yellow]")
        sys.exit(130)


def _show_config(config_path: str):
    """显示当前配置"""
    mgr = ConfigManager(config_path=config_path)
    try:
        mgr.load()
    except ConfigError:
        console.print(f"[yellow]配置文件不存在: {config_path}[/yellow]")
        console.print("请运行 [bold]svn-ai config[/bold] 创建配置。")
        return

    console.print(Panel(f"[bold]配置文件: {mgr.config_path}[/bold]", style="blue"))

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("配置项", style="bold")
    table.add_column("值")

    for key, value in mgr.to_display_dict().items():
        table.add_row(key, value)

    # 显示验证状态
    errors = mgr.validate()
    if errors:
        table.add_row("验证状态", f"[red]✗ {len(errors)} 个问题[/red]")
        for err in errors:
            table.add_row("", f"[red]  - {err}[/red]")
    else:
        table.add_row("验证状态", "[green]✓ 配置有效[/green]")

    console.print(table)


def _interactive_config(config_path: str):
    """交互式配置向导"""
    console.print(Panel("[bold]SVN AI 审查助手 - 配置向导[/bold]", style="blue"))
    console.print()

    # 加载已有配置
    mgr = ConfigManager(config_path=config_path)
    try:
        mgr.load()
    except ConfigError:
        mgr.reset_to_defaults()

    # ─── 选择 AI 模式 ───
    console.print("[bold]第 1 步: 选择 AI 模式[/bold]")
    console.print("  [1] local  - 本地私有化部署 (Ollama/vLLM)")
    console.print("  [2] cloud  - 云端 API 调用 (OpenAI/阿里云百炼)")
    console.print()

    current_mode = mgr.get_active_mode()
    default_choice = "1" if current_mode == "local" else "2"

    choice = click.prompt(
        "请选择模式",
        type=click.Choice(["1", "2"]),
        default=default_choice,
    )
    ai_mode = "local" if choice == "1" else "cloud"
    mgr.set("ai_mode", ai_mode)

    # ─── 配置参数 ───
    defaults = ProviderFactory.get_default_config(ai_mode)
    existing_mode = mgr.get(ai_mode, {})
    if not isinstance(existing_mode, dict):
        existing_mode = {}

    console.print()
    console.print(f"[bold]第 2 步: 配置 {ai_mode} 模式参数[/bold]")
    console.print()

    base_url = click.prompt(
        "API 服务地址",
        default=existing_mode.get("base_url", defaults.get("base_url", "")),
    )

    model = click.prompt(
        "模型名称",
        default=existing_mode.get("model", defaults.get("model", "")),
    )

    if ai_mode == "cloud":
        api_key = click.prompt(
            "API Key",
            default=existing_mode.get("api_key", ""),
            hide_input=True,
            confirmation_prompt=True,
        )
    else:
        api_key = click.prompt(
            "API Key (本地模式可填占位符)",
            default=existing_mode.get("api_key", defaults.get("api_key", "ollama")),
        )

    # ─── 通过 ConfigManager 保存 ───
    mgr.set(f"{ai_mode}.base_url", base_url)
    mgr.set(f"{ai_mode}.model", model)
    mgr.set(f"{ai_mode}.api_key", api_key)

    saved_path = mgr.save(config_path)

    console.print()
    console.print(f"[green]✓ 配置已保存至: {saved_path}[/green]")

    # 显示验证结果
    errors = mgr.validate()
    if errors:
        console.print(f"[yellow]⚠ 配置验证发现 {len(errors)} 个问题:[/yellow]")
        for err in errors:
            console.print(f"  [yellow]- {err}[/yellow]")
    console.print()

    # ─── 测试连接 ───
    if click.confirm("是否测试 AI 连接？", default=True):
        _test_connection(mgr.config)


def _test_connection(config: dict):
    """测试 AI 连接"""
    console.print()
    try:
        with console.status("[bold blue]正在测试连接...[/bold blue]"):
            provider = ProviderFactory.create_from_config(config)
            success = provider.test_connection()

        if success:
            console.print("[green]✓ 连接测试成功！[/green]")
        else:
            console.print("[red]✗ 连接测试失败[/red]")
    except AIProviderError as e:
        console.print(f"[red]✗ 连接失败:[/red] {e}")
    except Exception as e:
        console.print(f"[red]✗ 未预期错误:[/red] {e}")


@click.command("test-connection")
@click.option("--config-path", default=None, help="配置文件路径")
def test_connection_command(config_path):
    """测试 AI 服务连接

    示例:

      svn-ai test-connection
    """
    mgr = ConfigManager(config_path=config_path)
    try:
        mgr.load()
        mgr.validate_or_raise()
    except ConfigError as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)

    _test_connection(mgr.config)
