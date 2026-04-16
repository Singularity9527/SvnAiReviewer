"""SVN AI 智能审查助手 - 命令行入口

用法:
    svn-ai review -r 1024              审查单个版本
    svn-ai review -r 1020:1025         审查版本范围
    svn-ai review -r 1024 --format json 输出 JSON 格式
    svn-ai config                       交互式配置向导
    svn-ai config --show                显示当前配置
    svn-ai test-connection              测试 AI 连接
    svn-ai generate-log                 自动生成提交日志
"""
import logging
import sys
import os

import click

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from commands.review import review_command
from commands.config_cmd import config_command, test_connection_command
from commands.generate_log_cmd import generate_log_command


def _setup_logging(verbose: bool):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version="0.1.0", prog_name="svn-ai")
@click.option("-v", "--verbose", is_flag=True, default=False, help="显示详细日志")
def cli(verbose):
    """SVN AI 智能审查助手

    基于 AI 的 SVN 代码审查工具，支持本地和云端模型。
    """
    _setup_logging(verbose)


# 注册子命令
cli.add_command(review_command)
cli.add_command(config_command)
cli.add_command(test_connection_command)
cli.add_command(generate_log_command)


def main():
    """程序入口"""
    cli()


if __name__ == "__main__":
    main()
