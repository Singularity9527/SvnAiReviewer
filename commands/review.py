"""review 命令实现

核心审查命令，串联 SVN 命令封装、Prompt 构建、AI 推理的完整流程。
"""
import json
import logging
import sys
import os
from datetime import datetime

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# 将项目根目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from svn_client import SVNClient, SVNClientError, InvalidRevisionError
from prompt_builder import PromptBuilder
from ai_provider.factory import ProviderFactory
from ai_provider.base import AIProviderError
from config_manager import ConfigManager, ConfigError
from report_generator import ReportGenerator, ReviewResult
from batch_processor import BatchProcessor, BatchResult
from models.log_data import LogData

logger = logging.getLogger(__name__)
console = Console()


def _load_config() -> dict:
    """通过 ConfigManager 加载配置"""
    mgr = ConfigManager()
    try:
        return mgr.load()
    except ConfigError:
        return {}


@click.command("review")
@click.option("-r", "--revision", required=False, help="版本号或版本范围 (如: 1024 或 1020:1025)")
@click.option("--local", "review_local", is_flag=True, default=False, help="审查当前工作副本未提交代码")
@click.option("--format", "output_format", type=click.Choice(["markdown", "json"]), default="markdown",
              help="输出格式")
@click.option("--output", "-o", "output_file", default=None, help="输出文件路径")
@click.option("--show-prompt", is_flag=True, default=False, help="显示构建的 Prompt（调试用）")
@click.option("--working-dir", "-d", default=None, help="SVN 工作副本目录")
@click.option("--url", "-u", default=None, help="远程 SVN 仓库 URL")
@click.option("--trust-ssl", is_flag=True, default=False, help="信任自签名 SSL 证书")
@click.option("--username", default=None, help="SVN 认证用户名（可选）")
@click.option("--password", default=None, help="SVN 认证密码（可选）")
@click.option("--max-chars", default=None, type=int, help="Diff 最大字符数限制")
@click.option("--dry-run", is_flag=True, default=False, help="仅获取 Diff，不调用 AI")
def review_command(revision, review_local, output_format, output_file, show_prompt, working_dir, url, trust_ssl, username, password, max_chars, dry_run):
    """审查指定 SVN 版本的代码变更

    示例:

      svn-ai review -r 1024

      svn-ai review -r 1020:1025

      svn-ai review -r 1024 --format json -o report.json

      svn-ai review --local
    """
    try:
        _do_review(
            revision,
            review_local,
            output_format,
            output_file,
            show_prompt,
            working_dir,
            url,
            trust_ssl,
            username,
            password,
            max_chars,
            dry_run,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")
        sys.exit(130)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except Exception as e:
        console.print(f"[red]✗ 未预期的错误:[/red] {e}")
        logger.exception("未预期的错误")
        sys.exit(1)


def _validate_review_args(revision, review_local, url):
    """校验 review 命令参数组合。"""
    if review_local and revision:
        raise click.UsageError("--revision 与 --local 不能同时使用")
    if not review_local and not revision:
        raise click.UsageError("必须提供 --revision，或使用 --local 审查本地未提交代码")
    if review_local and url:
        raise click.UsageError("--local 模式不支持 --url，请改用本地工作副本目录")


def _build_local_log_data() -> LogData:
    """构造本地未提交代码审查用的伪提交信息。"""
    return LogData(
        revision="LOCAL",
        author=os.environ.get("USERNAME") or os.environ.get("USER") or "",
        date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message="本地未提交代码审查",
    )


def _do_review(revision, review_local, output_format, output_file, show_prompt, working_dir, url, trust_ssl, username, password, max_chars, dry_run):
    """执行审查的核心逻辑"""
    _validate_review_args(revision, review_local, url)

    # ─── 1. 初始化 SVN 客户端 ───
    console.print(Panel("[bold]SVN AI 智能审查助手[/bold]", style="blue"))

    try:
        with console.status("[bold blue]初始化 SVN 客户端...[/bold blue]"):
            svn = SVNClient(
                working_dir=working_dir,
                repo_url=url,
                trust_server_cert=trust_ssl,
                username=username,
                password=password,
            )
        console.print("[green]\u2713[/green] SVN 客户端就绪")
    except SVNClientError as e:
        console.print(f"[red]✗ SVN 错误:[/red] {e}")
        sys.exit(1)

    if review_local:
        console.print("[blue]►[/blue] 审查目标: 本地未提交代码")
        with console.status("[bold blue]获取本地未提交代码变更...[/bold blue]"):
            diff_data = svn.get_working_copy_diff()
            log_data = _build_local_log_data()

        if diff_data.error:
            console.print(f"[red]✗ 获取本地 Diff 失败:[/red] {diff_data.error}")
            sys.exit(1)

        if diff_data.is_empty:
            console.print("[yellow]⚠ 当前工作副本没有未提交代码变更。[/yellow]")
            sys.exit(0)

        _print_diff_summary(diff_data, log_data)
        _finish_review(diff_data, log_data, output_format, output_file, show_prompt, max_chars, dry_run)
        return

    # ─── 2. 验证版本号 ───
    try:
        start_rev, end_rev = SVNClient.validate_revision(revision)
    except InvalidRevisionError as e:
        console.print(f"[red]✗ 版本号无效:[/red] {e}")
        sys.exit(1)

    rev_display = f"r{start_rev}" + (f":r{end_rev}" if end_rev else "")
    console.print(f"[blue]►[/blue] 审查版本: {rev_display}")

    # 如果是版本范围，走批量审查路径
    if end_rev:
        _do_batch_review(svn, start_rev, end_rev, output_format, output_file, max_chars, dry_run)
        return

    # ─── 3. 获取 Diff 和 Log ───
    with console.status(f"[bold blue]获取 {rev_display} 代码变更...[/bold blue]"):
        diff_data = svn.get_diff(revision)
        log_data = svn.get_log(start_rev)

    if diff_data.error:
        console.print(f"[red]✗ 获取 Diff 失败:[/red] {diff_data.error}")
        sys.exit(1)

    if diff_data.is_empty:
        console.print("[yellow]⚠ Diff 为空，该版本可能没有代码变更。[/yellow]")
        sys.exit(0)

    # 显示变更摘要
    _print_diff_summary(diff_data, log_data)

    _finish_review(diff_data, log_data, output_format, output_file, show_prompt, max_chars, dry_run)


def _finish_review(diff_data, log_data, output_format, output_file, show_prompt, max_chars, dry_run):
    """执行 Prompt、AI 和报告生成的公共逻辑。"""
    
    if dry_run:
        console.print("\n[yellow]--dry-run 模式，跳过 AI 审查。[/yellow]")
        if show_prompt:
            builder = PromptBuilder()
            result = builder.build(diff_data, log_data, max_chars=max_chars)
            console.print("\n[bold]System Prompt:[/bold]")
            console.print(result.system_prompt[:500] + "...")
            console.print(f"\n[bold]User Prompt ({result.total_chars} 字符):[/bold]")
            console.print(result.user_prompt[:2000] + "...")
        return

    # ─── 4. 构建 Prompt ───
    with console.status("[bold blue]构建审查 Prompt...[/bold blue]"):
        builder = PromptBuilder()
        prompt_result = builder.build(diff_data, log_data, max_chars=max_chars)

    if prompt_result.is_truncated:
        console.print(
            f"[yellow]⚠ Diff 内容已截断: "
            f"{prompt_result.original_char_count:,} → {prompt_result.truncated_char_count:,} 字符[/yellow]"
        )

    console.print(
        f"[green]✓[/green] Prompt 构建完成 "
        f"(≈{prompt_result.estimated_tokens:,} tokens)"
    )

    if show_prompt:
        console.print("\n[bold]═══ System Prompt ═══[/bold]")
        console.print(prompt_result.system_prompt)
        console.print(f"\n[bold]═══ User Prompt ({prompt_result.total_chars:,} 字符) ═══[/bold]")
        console.print(prompt_result.user_prompt)
        console.print("[bold]═══════════════════[/bold]\n")

    # ─── 5. 加载 AI 配置 ───
    try:
        mgr = ConfigManager()
        config = mgr.load()
        mgr.validate_or_raise()
        console.print(f"[green]✓[/green] 配置已加载: {mgr.config_path}")
    except ConfigError as e:
        console.print(f"[red]✗ {e}[/red]")
        console.print("请先运行 [bold]svn-ai config[/bold] 创建配置。")
        sys.exit(1)

    # ─── 6. 调用 AI 推理 ───
    try:
        provider = ProviderFactory.create_from_config(config)
    except AIProviderError as e:
        console.print(f"[red]✗ AI 配置错误:[/red] {e}")
        sys.exit(1)

    console.print(f"[blue]►[/blue] AI 模型: {provider.config.model}")

    with console.status("[bold blue]AI 正在审查代码...[/bold blue]"):
        response = provider.chat(
            prompt=prompt_result.user_prompt,
            system_prompt=prompt_result.system_prompt,
        )

    if not response.is_success:
        console.print(f"[red]✗ AI 推理失败:[/red] {response.error}")
        sys.exit(1)

    # ─── 7. 生成报告 ───
    console.print(
        f"[green]✓[/green] 审查完成 "
        f"(耗时 {response.elapsed_seconds:.1f}s, "
        f"Token: {response.total_tokens:,})"
    )

    review_result = ReviewResult.from_review_data(diff_data, log_data, response)
    generator = ReportGenerator()

    if output_file:
        saved_path = generator.save(review_result, output_format=output_format, output_path=output_file)
        console.print(f"[green]✓[/green] 报告已保存至: {saved_path}")
    elif output_format == "json":
        click.echo(generator.generate_json(review_result))
    else:
        generator.render_terminal(review_result)


def _print_diff_summary(diff_data, log_data):
    """打印变更摘要表格"""
    table = Table(title="变更摘要", show_header=True, header_style="bold cyan")
    table.add_column("项目", style="bold")
    table.add_column("内容")

    table.add_row("版本号", f"r{log_data.revision}")
    table.add_row("作者", log_data.author or "未知")
    table.add_row("时间", log_data.date or "未知")
    table.add_row("日志", log_data.message[:80] if log_data.message else "（空）")
    table.add_row("文件数", str(diff_data.total_files))
    table.add_row("变更行数", f"+{diff_data.total_added_lines}/-{diff_data.total_removed_lines}")

    console.print(table)


def _do_batch_review(svn, start_rev, end_rev, output_format, output_file, max_chars, dry_run):
    """执行批量审查"""
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
    import json as json_mod

    # 加载配置
    try:
        mgr = ConfigManager()
        config = mgr.load()
        mgr.validate_or_raise()
        console.print(f"[green]\u2713[/green] 配置已加载: {mgr.config_path}")
    except ConfigError as e:
        console.print(f"[red]\u2717 {e}[/red]")
        console.print("请先运行 [bold]svn-ai config[/bold] 创建配置。")
        sys.exit(1)

    try:
        provider = ProviderFactory.create_from_config(config)
    except AIProviderError as e:
        console.print(f"[red]\u2717 AI 配置错误:[/red] {e}")
        sys.exit(1)

    console.print(f"[blue]\u25ba[/blue] AI 模型: {provider.config.model}")

    # 获取版本列表
    with console.status("[bold blue]获取版本列表...[/bold blue]"):
        revisions = svn.get_revisions_in_range(start_rev, end_rev)

    if not revisions:
        console.print("[yellow]\u26a0 版本范围内未找到任何版本。[/yellow]")
        sys.exit(0)

    console.print(f"[green]\u2713[/green] 找到 {len(revisions)} 个版本")

    if dry_run:
        console.print("\n[yellow]--dry-run 模式，版本列表:[/yellow]")
        for rev in revisions:
            console.print(f"  r{rev}")
        return

    # 进度条回调
    progress_bar = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    )

    task_id = None

    def on_progress(p):
        nonlocal task_id
        done = p.completed + p.failed + p.skipped
        if task_id is not None:
            progress_bar.update(task_id, completed=done, description=f"审查 r{p.current_revision}")

    # 执行批量审查
    processor = BatchProcessor(
        svn_client=svn,
        provider=provider,
        max_chars=max_chars,
        progress_callback=on_progress,
    )

    with progress_bar:
        task_id = progress_bar.add_task("批量审查", total=len(revisions))
        batch_result = processor.process(start_rev, end_rev)
        progress_bar.update(task_id, completed=len(revisions))

    # 输出结果摘要
    console.print()
    console.print(
        f"[green]\u2713[/green] 批量审查完成: "
        f"成功={batch_result.success_count}, "
        f"失败={batch_result.failed_count}, "
        f"跳过={batch_result.skipped_count}, "
        f"耗时={batch_result.total_elapsed:.1f}s"
    )

    # 生成报告
    if output_format == "json":
        json_data = batch_result.generate_summary_json()
        json_str = json_mod.dumps(json_data, ensure_ascii=False, indent=2)
        if output_file:
            os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(json_str)
            console.print(f"[green]\u2713[/green] 报告已保存至: {output_file}")
        else:
            click.echo(json_str)
    else:
        md_content = batch_result.generate_summary_markdown()
        if output_file:
            os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(md_content)
            console.print(f"[green]\u2713[/green] 报告已保存至: {output_file}")
        else:
            console.print()
            console.print(Markdown(md_content))
            console.print()
