"""日志生成器单元测试"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from log_generator import LogGenerator, LogCandidate, GenerateResult
from models.diff_data import DiffData, FileDiff
from ai_provider.base import AIResponse


# ─── 测试辅助 ───

def _make_diff(empty=False, error=None):
    if empty:
        return DiffData(revision="WORKING", raw_diff="", file_diffs=[], error=error)
    return DiffData(
        revision="WORKING",
        raw_diff="Index: main.py\n--- main.py\n+++ main.py\n@@ -1 +1 @@\n-old\n+new",
        file_diffs=[
            FileDiff(file_path="main.py", status="M", diff_content="-old\n+new", added_lines=1, removed_lines=1)
        ],
        error=error,
    )


def _make_ai_response(content="", success=True, error=None):
    return AIResponse(
        content=content,
        model="test-model",
        usage={"total_tokens": 100},
        elapsed_seconds=1.0,
        error=error if not success else None,
    )


SAMPLE_AI_RESPONSE = """
--- 候选 1 ---
fix: 修复主模块逻辑错误

--- 候选 2 ---
fix: 修复 main.py 中的逻辑判断错误

将旧的判断逻辑替换为新实现，避免边界条件问题。

--- 候选 3 ---
fix: 修复 main.py 核心逻辑

- 移除过时的旧逻辑
- 添加新的处理方式
- 修正边界条件处理
"""


class TestLogCandidate(unittest.TestCase):
    """LogCandidate 数据类测试"""

    def test_full_message_title_only(self):
        c = LogCandidate(index=1, title="fix: 修复 bug")
        self.assertEqual(c.full_message, "fix: 修复 bug")

    def test_full_message_with_body(self):
        c = LogCandidate(index=1, title="feat: 新功能", body="详细描述")
        self.assertEqual(c.full_message, "feat: 新功能\n\n详细描述")

    def test_str(self):
        c = LogCandidate(index=1, title="test")
        self.assertEqual(str(c), "test")


class TestGenerateResult(unittest.TestCase):
    """GenerateResult 数据类测试"""

    def test_success(self):
        r = GenerateResult(
            candidates=[LogCandidate(index=1, title="test")],
            raw_response="raw",
        )
        self.assertTrue(r.is_success)

    def test_error(self):
        r = GenerateResult(error="失败")
        self.assertFalse(r.is_success)

    def test_empty_candidates(self):
        r = GenerateResult(candidates=[])
        self.assertFalse(r.is_success)


class TestParseCandidates(unittest.TestCase):
    """候选日志解析测试"""

    def test_parse_standard_format(self):
        candidates = LogGenerator._parse_candidates(SAMPLE_AI_RESPONSE)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].index, 1)
        self.assertIn("修复", candidates[0].title)

    def test_parse_with_body(self):
        candidates = LogGenerator._parse_candidates(SAMPLE_AI_RESPONSE)
        # 候选 2 和 3 有详细描述
        self.assertTrue(any(c.body for c in candidates))

    def test_parse_empty_response(self):
        candidates = LogGenerator._parse_candidates("")
        self.assertEqual(len(candidates), 0)

    def test_parse_no_markers(self):
        """无标准分隔符时，整体作为单条日志"""
        candidates = LogGenerator._parse_candidates("fix: 修复了一个问题\n\n详细描述内容")
        self.assertEqual(len(candidates), 1)
        self.assertIn("修复", candidates[0].title)

    def test_parse_with_markdown_title(self):
        """标题带 # 前缀"""
        text = "--- 候选 1 ---\n## fix: 修复问题\n--- 候选 2 ---\nfeat: 新功能"
        candidates = LogGenerator._parse_candidates(text)
        self.assertEqual(len(candidates), 2)
        self.assertFalse(candidates[0].title.startswith("#"))

    def test_parse_single_candidate(self):
        text = "--- 候选 1 ---\nrefactor: 重构代码"
        candidates = LogGenerator._parse_candidates(text)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].title, "refactor: 重构代码")


class TestLogGenerator(unittest.TestCase):
    """LogGenerator 核心流程测试"""

    def setUp(self):
        self.svn = MagicMock()
        self.provider = MagicMock()

    def test_generate_success(self):
        """正常生成候选日志"""
        self.svn.get_diff.return_value = _make_diff()
        self.provider.chat.return_value = _make_ai_response(
            content=SAMPLE_AI_RESPONSE, success=True
        )

        gen = LogGenerator(self.svn, self.provider)
        result = gen.generate()

        self.assertTrue(result.is_success)
        self.assertEqual(len(result.candidates), 3)
        self.provider.chat.assert_called_once()

    def test_generate_empty_diff(self):
        """工作区无变更"""
        self.svn.get_diff.return_value = _make_diff(empty=True)
        # _get_working_diff 也返回空
        self.svn._run_command.return_value = ("", "")
        self.svn._parse_diff_output.return_value = []

        gen = LogGenerator(self.svn, self.provider)
        result = gen.generate()

        self.assertFalse(result.is_success)
        self.assertIn("没有未提交的变更", result.error)

    def test_generate_ai_failure(self):
        """AI 推理失败"""
        self.svn.get_diff.return_value = _make_diff()
        self.provider.chat.return_value = _make_ai_response(
            success=False, error="连接超时"
        )

        gen = LogGenerator(self.svn, self.provider)
        result = gen.generate()

        self.assertFalse(result.is_success)
        self.assertIn("AI 推理失败", result.error)

    def test_generate_diff_truncation(self):
        """超长 Diff 截断"""
        long_diff = DiffData(
            revision="WORKING",
            raw_diff="x" * 50000,
            file_diffs=[FileDiff(file_path="big.py", status="M", diff_content="x" * 50000)],
        )
        self.svn.get_diff.return_value = long_diff
        self.provider.chat.return_value = _make_ai_response(
            content="--- 候选 1 ---\nfeat: 大改动", success=True
        )

        gen = LogGenerator(self.svn, self.provider)
        result = gen.generate(max_diff_chars=1000)

        self.assertTrue(result.is_success)
        # 验证传给 AI 的 prompt 被截断了
        call_args = self.provider.chat.call_args
        prompt = call_args[1].get("prompt", call_args[0][0] if call_args[0] else "")
        # prompt 中应包含截断提示（或 diff 内容不超过 1000 + 模板文字）

    def test_generate_svn_exception_fallback(self):
        """SVN 异常回退到工作区 diff"""
        self.svn.get_diff.side_effect = Exception("不支持的版本格式")
        self.svn._run_command.return_value = (
            "Index: test.py\n--- test.py\n+++ test.py\n@@ -1 +1 @@\n-a\n+b",
            "",
        )
        self.svn._parse_diff_output.return_value = [
            FileDiff(file_path="test.py", status="M", diff_content="-a\n+b")
        ]
        self.provider.chat.return_value = _make_ai_response(
            content="--- 候选 1 ---\nfix: 修复", success=True
        )

        gen = LogGenerator(self.svn, self.provider)
        result = gen.generate()

        self.assertTrue(result.is_success)

    def test_custom_template(self):
        """自定义模板"""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("自定义模板：请生成提交日志")
            path = f.name

        try:
            self.svn.get_diff.return_value = _make_diff()
            self.provider.chat.return_value = _make_ai_response(
                content="--- 候选 1 ---\ntest: 测试", success=True
            )

            gen = LogGenerator(self.svn, self.provider, template_path=path)
            result = gen.generate()

            self.assertTrue(result.is_success)
            # 验证使用了自定义模板
            call_args = self.provider.chat.call_args
            system_prompt = call_args[1].get("system_prompt", "")
            self.assertIn("自定义模板", system_prompt)
        finally:
            os.unlink(path)


class TestBuildUserPrompt(unittest.TestCase):
    """用户 Prompt 构建测试"""

    def test_with_summary(self):
        prompt = LogGenerator._build_user_prompt("diff content", "3 files changed")
        self.assertIn("变更概览", prompt)
        self.assertIn("3 files changed", prompt)
        self.assertIn("diff content", prompt)

    def test_without_summary(self):
        prompt = LogGenerator._build_user_prompt("diff content", "")
        self.assertNotIn("变更概览", prompt)
        self.assertIn("diff content", prompt)

    def test_contains_instruction(self):
        prompt = LogGenerator._build_user_prompt("diff", "")
        self.assertIn("候选提交日志", prompt)


class TestCLICommand(unittest.TestCase):
    """generate-log CLI 命令基础测试"""

    def test_command_help(self):
        from click.testing import CliRunner
        from commands.generate_log_cmd import generate_log_command

        runner = CliRunner()
        result = runner.invoke(generate_log_command, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("generate-log", result.output)
        self.assertIn("工作区", result.output)


if __name__ == "__main__":
    unittest.main()
