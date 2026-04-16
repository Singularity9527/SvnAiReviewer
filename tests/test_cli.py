"""命令行交互模块单元测试

测试 CLI 命令的参数解析、帮助信息和基本调用逻辑。
使用 click.testing.CliRunner 进行测试，无需真实 SVN 或 AI 环境。
"""
import sys
import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from click.testing import CliRunner
from cli import cli


class TestCLIHelp(unittest.TestCase):
    """CLI 帮助信息测试"""

    def setUp(self):
        self.runner = CliRunner()

    def test_main_help(self):
        result = self.runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("SVN AI 智能审查助手", result.output)
        self.assertIn("review", result.output)
        self.assertIn("config", result.output)
        self.assertIn("test-connection", result.output)

    def test_version(self):
        result = self.runner.invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("0.1.0", result.output)

    def test_review_help(self):
        result = self.runner.invoke(cli, ["review", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--revision", result.output)
        self.assertIn("--local", result.output)
        self.assertIn("--format", result.output)
        self.assertIn("--username", result.output)
        self.assertIn("--password", result.output)
        self.assertIn("--dry-run", result.output)
        self.assertIn("--show-prompt", result.output)

    def test_config_help(self):
        result = self.runner.invoke(cli, ["config", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--show", result.output)

    def test_test_connection_help(self):
        result = self.runner.invoke(cli, ["test-connection", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--config-path", result.output)


class TestReviewCommand(unittest.TestCase):
    """review 命令测试"""

    def setUp(self):
        self.runner = CliRunner()

    def test_review_requires_revision(self):
        """review 命令缺少 -r 参数应报错"""
        result = self.runner.invoke(cli, ["review"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--local", result.output)

    def test_review_revision_and_local_conflict(self):
        result = self.runner.invoke(cli, ["review", "-r", "1024", "--local"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("不能同时使用", result.output)

    def test_review_local_and_url_conflict(self):
        result = self.runner.invoke(cli, ["review", "--local", "--url", "https://svn.example.com/repo"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("不支持", result.output)

    @patch("commands.review.SVNClient")
    def test_review_invalid_revision(self, mock_svn_cls):
        """无效版本号应报错"""
        from svn_client import InvalidRevisionError
        mock_svn_cls.validate_revision.side_effect = InvalidRevisionError("无效版本号")
        mock_svn_cls.return_value = MagicMock()

        result = self.runner.invoke(cli, ["review", "-r", "abc"])
        self.assertNotEqual(result.exit_code, 0)

    @patch("commands.review.SVNClient")
    def test_review_dry_run_empty_diff(self, mock_svn_cls):
        """dry-run 模式下 diff 为空应正常退出"""
        mock_svn = MagicMock()
        mock_svn_cls.return_value = mock_svn
        mock_svn_cls.validate_revision.return_value = ("1024", None)

        # 模拟空 diff
        mock_diff = MagicMock()
        mock_diff.error = None
        mock_diff.is_empty = True
        mock_svn.get_diff.return_value = mock_diff

        result = self.runner.invoke(cli, ["review", "-r", "1024", "--dry-run"])
        self.assertEqual(result.exit_code, 0)

    @patch("commands.review.SVNClient")
    def test_review_dry_run_with_diff(self, mock_svn_cls):
        """dry-run 模式下有 diff 应显示摘要"""
        mock_svn = MagicMock()
        mock_svn_cls.return_value = mock_svn
        mock_svn_cls.validate_revision.return_value = ("1024", None)

        # 模拟有 diff
        mock_diff = MagicMock()
        mock_diff.error = None
        mock_diff.is_empty = False
        mock_diff.total_files = 2
        mock_diff.total_added_lines = 10
        mock_diff.total_removed_lines = 5
        mock_diff.raw_diff = "+new line\n-old line\n"
        mock_diff.file_diffs = []
        mock_svn.get_diff.return_value = mock_diff

        # 模拟 log
        mock_log = MagicMock()
        mock_log.revision = "1024"
        mock_log.author = "testuser"
        mock_log.date = "2026-04-14"
        mock_log.message = "test commit"
        mock_svn.get_log.return_value = mock_log

        result = self.runner.invoke(cli, ["review", "-r", "1024", "--dry-run"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("dry-run", result.output)

    @patch("commands.review.SVNClient")
    def test_review_passes_auth_options_to_svn_client(self, mock_svn_cls):
        mock_svn = MagicMock()
        mock_svn_cls.return_value = mock_svn
        mock_svn_cls.validate_revision.return_value = ("1024", None)

        mock_diff = MagicMock()
        mock_diff.error = None
        mock_diff.is_empty = True
        mock_svn.get_diff.return_value = mock_diff

        result = self.runner.invoke(
            cli,
            [
                "review",
                "-r",
                "1024",
                "--username",
                "aaa",
                "--password",
                "123456",
                "--dry-run",
            ],
        )
        self.assertEqual(result.exit_code, 0)
        mock_svn_cls.assert_called_once()
        _, kwargs = mock_svn_cls.call_args
        self.assertEqual(kwargs.get("username"), "aaa")
        self.assertEqual(kwargs.get("password"), "123456")

    @patch("commands.review.SVNClient")
    def test_review_local_dry_run_empty_diff(self, mock_svn_cls):
        mock_svn = MagicMock()
        mock_svn_cls.return_value = mock_svn

        mock_diff = MagicMock()
        mock_diff.error = None
        mock_diff.is_empty = True
        mock_svn.get_working_copy_diff.return_value = mock_diff

        result = self.runner.invoke(cli, ["review", "--local", "--dry-run"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("没有未提交代码变更", result.output)

    @patch("commands.review.SVNClient")
    def test_review_local_dry_run_with_diff(self, mock_svn_cls):
        mock_svn = MagicMock()
        mock_svn_cls.return_value = mock_svn

        mock_diff = MagicMock()
        mock_diff.error = None
        mock_diff.is_empty = False
        mock_diff.total_files = 2
        mock_diff.total_added_lines = 8
        mock_diff.total_removed_lines = 3
        mock_diff.raw_diff = "Index: a.py\n+line\n"
        mock_diff.file_diffs = []
        mock_svn.get_working_copy_diff.return_value = mock_diff

        result = self.runner.invoke(cli, ["review", "--local", "--dry-run"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("本地未提交代码", result.output)
        self.assertIn("dry-run", result.output)

    def test_review_format_choices(self):
        """--format 只接受 markdown/json"""
        result = self.runner.invoke(cli, ["review", "-r", "1024", "--format", "xml"])
        self.assertNotEqual(result.exit_code, 0)


class TestConfigCommand(unittest.TestCase):
    """config 命令测试"""

    def setUp(self):
        self.runner = CliRunner()

    def test_config_show_no_file(self):
        """--show 无配置文件应提示"""
        result = self.runner.invoke(cli, ["config", "--show", "--path", "/nonexistent/config.yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("不存在", result.output)

    def test_config_show_with_file(self):
        """--show 有配置文件应显示内容"""
        import yaml

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump({
                "ai_mode": "local",
                "local": {
                    "base_url": "http://localhost:11434/v1",
                    "model": "qwen2.5-coder:7b",
                    "api_key": "ollama",
                }
            }, f)
            tmp_path = f.name

        try:
            result = self.runner.invoke(cli, ["config", "--show", "--path", tmp_path])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("local", result.output)
            self.assertIn("qwen2.5-coder", result.output)
        finally:
            os.unlink(tmp_path)


class TestTestConnectionCommand(unittest.TestCase):
    """test-connection 命令测试"""

    def setUp(self):
        self.runner = CliRunner()

    def test_no_config_file(self):
        """无配置文件应报错"""
        result = self.runner.invoke(cli, ["test-connection", "--config-path", "/nonexistent/config.yaml"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
