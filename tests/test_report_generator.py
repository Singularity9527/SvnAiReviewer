"""报告生成器单元测试"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from report_generator import ReportGenerator, ReviewResult


def _make_result(**kwargs) -> ReviewResult:
    """创建测试用 ReviewResult"""
    defaults = dict(
        revision="1024",
        author="zhangsan",
        date="2026-04-14 10:30:00",
        message="修复登录接口安全问题",
        total_files=3,
        added_lines=25,
        removed_lines=10,
        file_list=[
            "- `src/auth/login.py` (M, +15/-5)",
            "- `src/auth/utils.py` (M, +8/-3)",
            "- `tests/test_login.py` (A, +2/-2)",
        ],
        review_content="## 审查发现\n\n| 文件 | 问题 | 建议 |\n|---|---|---|\n| login.py | SQL注入 | 使用参数化查询 |",
        model="qwen2.5-coder:7b",
        elapsed_seconds=3.5,
        total_tokens=1200,
        prompt_tokens=800,
        completion_tokens=400,
        generated_at="2026-04-14 10:31:00",
    )
    defaults.update(kwargs)
    return ReviewResult(**defaults)


class TestReviewResult(unittest.TestCase):
    """ReviewResult 数据类测试"""

    def test_default_generated_at(self):
        r = ReviewResult()
        self.assertTrue(len(r.generated_at) > 0)

    def test_is_success(self):
        r = _make_result()
        self.assertTrue(r.is_success)

    def test_is_error(self):
        r = _make_result(status="error", error="连接失败")
        self.assertFalse(r.is_success)

    def test_from_review_data(self):
        """从模拟的审查数据创建"""
        from unittest.mock import MagicMock

        diff = MagicMock()
        diff.file_diffs = [
            MagicMock(file_path="a.py", status="M", added_lines=10, removed_lines=3),
            MagicMock(file_path="b.py", status="A", added_lines=5, removed_lines=0),
        ]
        diff.total_files = 2
        diff.total_added_lines = 15
        diff.total_removed_lines = 3
        diff.revision = "1024"

        log = MagicMock()
        log.revision = "1024"
        log.author = "testuser"
        log.date = "2026-04-14"
        log.message = "test commit"

        response = MagicMock()
        response.content = "审查结果内容"
        response.is_success = True
        response.model = "gpt-4o"
        response.elapsed_seconds = 2.5
        response.total_tokens = 500
        response.prompt_tokens = 300
        response.completion_tokens = 200
        response.error = None

        result = ReviewResult.from_review_data(diff, log, response)
        self.assertEqual(result.revision, "1024")
        self.assertEqual(result.author, "testuser")
        self.assertEqual(result.total_files, 2)
        self.assertEqual(result.review_content, "审查结果内容")
        self.assertEqual(len(result.file_list), 2)
        self.assertTrue(result.is_success)

    def test_from_review_data_error(self):
        from unittest.mock import MagicMock

        diff = MagicMock()
        diff.file_diffs = []
        diff.total_files = 0
        diff.total_added_lines = 0
        diff.total_removed_lines = 0
        diff.revision = "1024"

        log = MagicMock()
        log.revision = "1024"
        log.author = ""
        log.date = ""
        log.message = ""

        response = MagicMock()
        response.content = ""
        response.is_success = False
        response.model = ""
        response.elapsed_seconds = 0
        response.total_tokens = 0
        response.prompt_tokens = 0
        response.completion_tokens = 0
        response.error = "AI 连接失败"

        result = ReviewResult.from_review_data(diff, log, response)
        self.assertFalse(result.is_success)
        self.assertEqual(result.error, "AI 连接失败")


class TestGenerateMarkdown(unittest.TestCase):
    """Markdown 生成测试"""

    def setUp(self):
        self.gen = ReportGenerator()
        self.result = _make_result()

    def test_contains_revision(self):
        md = self.gen.generate_markdown(self.result)
        self.assertIn("r1024", md)

    def test_contains_author(self):
        md = self.gen.generate_markdown(self.result)
        self.assertIn("zhangsan", md)

    def test_contains_review_content(self):
        md = self.gen.generate_markdown(self.result)
        self.assertIn("SQL注入", md)

    def test_contains_file_list(self):
        md = self.gen.generate_markdown(self.result)
        self.assertIn("login.py", md)

    def test_contains_model_info(self):
        md = self.gen.generate_markdown(self.result)
        self.assertIn("qwen2.5-coder:7b", md)

    def test_empty_review_content(self):
        result = _make_result(review_content="")
        md = self.gen.generate_markdown(result)
        self.assertIn("无审查内容", md)

    def test_empty_file_list(self):
        result = _make_result(file_list=[])
        md = self.gen.generate_markdown(result)
        self.assertIn("无文件变更", md)

    def test_fallback_on_bad_template(self):
        """模板有未知占位符时回退到简单格式"""
        gen = ReportGenerator(template_path="/nonexistent/template.md")
        md = gen.generate_markdown(self.result)
        self.assertIn("r1024", md)

    def test_custom_template(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# CUSTOM - {revision}\n{review_content}\n")
            path = f.name
        try:
            gen = ReportGenerator(template_path=path)
            md = gen.generate_markdown(self.result)
            self.assertIn("CUSTOM", md)
            self.assertIn("r1024", md)
        finally:
            os.unlink(path)


class TestGenerateJSON(unittest.TestCase):
    """JSON 生成测试"""

    def setUp(self):
        self.gen = ReportGenerator()
        self.result = _make_result()

    def test_valid_json(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertIsInstance(data, dict)

    def test_json_contains_revision(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertEqual(data["revision"], "r1024")

    def test_json_contains_commit(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertEqual(data["commit"]["author"], "zhangsan")

    def test_json_contains_changes(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertEqual(data["changes"]["total_files"], 3)
        self.assertEqual(data["changes"]["added_lines"], 25)

    def test_json_contains_ai_info(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertEqual(data["ai"]["model"], "qwen2.5-coder:7b")
        self.assertEqual(data["ai"]["tokens"]["total"], 1200)

    def test_json_contains_review(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertIn("SQL注入", data["review"])

    def test_json_error_field(self):
        result = _make_result(status="error", error="连接失败")
        json_str = self.gen.generate_json(result)
        data = json.loads(json_str)
        self.assertIn("error", data)
        self.assertEqual(data["error"], "连接失败")

    def test_json_no_error_field_on_success(self):
        json_str = self.gen.generate_json(self.result)
        data = json.loads(json_str)
        self.assertNotIn("error", data)

    def test_compact_json(self):
        json_str = self.gen.generate_json(self.result, pretty=False)
        self.assertNotIn("\n", json_str)


class TestSaveReport(unittest.TestCase):
    """报告保存测试"""

    def test_save_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            result = _make_result()
            path = gen.save(result, output_format="markdown")
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".md"))
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("r1024", content)

    def test_save_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            result = _make_result()
            path = gen.save(result, output_format="json")
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".json"))
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["revision"], "r1024")

    def test_save_custom_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = os.path.join(tmpdir, "my_report.md")
            gen = ReportGenerator()
            result = _make_result()
            path = gen.save(result, output_path=custom_path)
            self.assertEqual(path, custom_path)
            self.assertTrue(os.path.exists(custom_path))

    def test_save_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "sub", "dir", "report.md")
            gen = ReportGenerator()
            result = _make_result()
            gen.save(result, output_path=nested)
            self.assertTrue(os.path.exists(nested))

    def test_filename_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            result = _make_result()
            path = gen.save(result, output_format="markdown")
            filename = os.path.basename(path)
            self.assertTrue(filename.startswith("review_r1024_"))
            self.assertTrue(filename.endswith(".md"))


class TestRenderTerminal(unittest.TestCase):
    """终端渲染测试（验证不崩溃）"""

    def test_render_success(self):
        from io import StringIO
        from rich.console import Console
        gen = ReportGenerator()
        result = _make_result()
        # 重定向输出避免 GBK 编码问题
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        gen._render_with_console(result, console)
        output = buf.getvalue()
        self.assertIn("r1024", output)

    def test_render_empty_content(self):
        from io import StringIO
        from rich.console import Console
        gen = ReportGenerator()
        result = _make_result(review_content="")
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        gen._render_with_console(result, console)
        output = buf.getvalue()
        self.assertIn("无审查内容", output)

    def test_render_empty_author(self):
        from io import StringIO
        from rich.console import Console
        gen = ReportGenerator()
        result = _make_result(author="", date="", message="")
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        gen._render_with_console(result, console)
        output = buf.getvalue()
        self.assertIn("未知", output)


if __name__ == "__main__":
    unittest.main()
