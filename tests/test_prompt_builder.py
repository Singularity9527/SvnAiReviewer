"""Prompt 构建器单元测试"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt_builder import PromptBuilder, PromptResult
from models.diff_data import DiffData, FileDiff
from models.log_data import LogData


def _make_log(revision="1024", author="zhangsan", date="2026-04-14 10:30:00",
              message="修复登录安全问题"):
    return LogData(revision=revision, author=author, date=date, message=message)


def _make_diff(revision="1024", raw_diff="", file_diffs=None):
    return DiffData(
        revision=revision,
        raw_diff=raw_diff or "Index: test.py\n+line1\n-line2\n",
        file_diffs=file_diffs or [
            FileDiff("src/main.py", "M", "+import os\n-import sys\n", added_lines=1, removed_lines=1),
            FileDiff("src/utils.py", "A", "+def helper():\n+    pass\n", added_lines=2, removed_lines=0),
        ],
    )


class TestPromptBuilder(unittest.TestCase):
    """Prompt 构建器基本功能测试"""

    def setUp(self):
        self.builder = PromptBuilder()
        self.log = _make_log()
        self.diff = _make_diff()

    def test_build_returns_prompt_result(self):
        result = self.builder.build(self.diff, self.log)
        self.assertIsInstance(result, PromptResult)

    def test_system_prompt_loaded(self):
        result = self.builder.build(self.diff, self.log)
        self.assertIn("代码审计专家", result.system_prompt)
        self.assertIn("安全性", result.system_prompt)
        self.assertIn("逻辑性", result.system_prompt)
        self.assertIn("规范性", result.system_prompt)

    def test_user_prompt_contains_commit_info(self):
        result = self.builder.build(self.diff, self.log)
        self.assertIn("r1024", result.user_prompt)
        self.assertIn("zhangsan", result.user_prompt)
        self.assertIn("2026-04-14", result.user_prompt)
        self.assertIn("修复登录安全问题", result.user_prompt)

    def test_user_prompt_contains_file_list(self):
        result = self.builder.build(self.diff, self.log)
        self.assertIn("src/main.py", result.user_prompt)
        self.assertIn("src/utils.py", result.user_prompt)
        self.assertIn("修改", result.user_prompt)  # M -> 修改
        self.assertIn("新增", result.user_prompt)  # A -> 新增

    def test_user_prompt_contains_diff_content(self):
        result = self.builder.build(self.diff, self.log)
        self.assertIn("Index: test.py", result.user_prompt)

    def test_empty_message_placeholder(self):
        log = _make_log(message="")
        result = self.builder.build(self.diff, log)
        self.assertIn("无提交日志", result.user_prompt)

    def test_no_file_diffs(self):
        diff = DiffData(revision="1024", raw_diff="some diff", file_diffs=[])
        result = self.builder.build(diff, self.log)
        self.assertIn("无变更文件", result.user_prompt)


class TestPromptResult(unittest.TestCase):
    """PromptResult 数据模型测试"""

    def test_total_chars(self):
        result = PromptResult(system_prompt="abc", user_prompt="defgh")
        self.assertEqual(result.total_chars, 8)

    def test_estimated_tokens(self):
        result = PromptResult(system_prompt="a" * 100, user_prompt="b" * 150)
        # 250 chars / 2.5 = 100
        self.assertEqual(result.estimated_tokens, 100)

    def test_summary_normal(self):
        result = PromptResult(system_prompt="sys", user_prompt="usr")
        summary = result.summary()
        self.assertIn("字符数=", summary)

    def test_summary_truncated(self):
        result = PromptResult(
            system_prompt="sys", user_prompt="usr",
            is_truncated=True, original_char_count=100000, truncated_char_count=50000,
        )
        summary = result.summary()
        self.assertIn("已截断", summary)

    def test_summary_segmented(self):
        result = PromptResult(
            system_prompt="sys", user_prompt="usr",
            segment_index=1, total_segments=3,
        )
        summary = result.summary()
        self.assertIn("分段 2/3", summary)


class TestTruncation(unittest.TestCase):
    """截断策略测试"""

    def setUp(self):
        self.builder = PromptBuilder()

    def test_no_truncation_when_within_limit(self):
        diff = _make_diff(raw_diff="short diff")
        result = self.builder.build(diff, _make_log(), max_chars=100000)
        self.assertFalse(result.is_truncated)

    def test_truncation_when_exceeds_limit(self):
        long_diff = "Index: file1.py\n" + "+" * 10000 + "\nIndex: file2.py\n" + "+" * 10000
        diff = _make_diff(raw_diff=long_diff)
        result = self.builder.build(diff, _make_log(), max_chars=5000)
        self.assertTrue(result.is_truncated)

    def test_truncation_adds_notice(self):
        long_diff = "x" * 10000
        diff = _make_diff(raw_diff=long_diff)
        result = self.builder.build(diff, _make_log(), max_chars=1000)
        self.assertIn("已截断", result.user_prompt)

    def test_truncate_at_file_boundary(self):
        """优先在文件边界处截断"""
        diff_text = "Index: a.py\n" + "+" * 3000 + "\nIndex: b.py\n" + "+" * 3000
        truncated = PromptBuilder._truncate_diff(diff_text, 4000)
        # 应该在 Index: b.py 之前截断
        self.assertNotIn("Index: b.py", truncated)
        self.assertIn("已截断", truncated)

    def test_static_truncate_short_content(self):
        content = "short"
        result = PromptBuilder._truncate_diff(content, 100)
        self.assertEqual(result, "short")


class TestSegmentation(unittest.TestCase):
    """分段策略测试"""

    def setUp(self):
        self.builder = PromptBuilder()

    def test_single_segment_when_small(self):
        diff = _make_diff()
        segments = self.builder.build_segments(diff, _make_log(), max_chars_per_segment=100000)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].total_segments, 1)

    def test_multiple_segments_when_large(self):
        files = [
            FileDiff(f"file{i}.py", "M", "+" * 5000, added_lines=100, removed_lines=0)
            for i in range(5)
        ]
        raw_diff = "\n".join(f.diff_content for f in files)
        diff = DiffData(revision="1024", raw_diff=raw_diff, file_diffs=files)

        segments = self.builder.build_segments(diff, _make_log(), max_chars_per_segment=8000)
        self.assertGreater(len(segments), 1)

        # 验证分段索引正确
        for i, seg in enumerate(segments):
            self.assertEqual(seg.segment_index, i)
            self.assertEqual(seg.total_segments, len(segments))

    def test_segment_contains_commit_info(self):
        files = [
            FileDiff(f"file{i}.py", "M", "+" * 5000, added_lines=100, removed_lines=0)
            for i in range(3)
        ]
        raw_diff = "\n".join(f.diff_content for f in files)
        diff = DiffData(revision="1024", raw_diff=raw_diff, file_diffs=files)

        segments = self.builder.build_segments(diff, _make_log(), max_chars_per_segment=6000)
        # 每个分段都应包含提交信息
        for seg in segments:
            self.assertIn("r1024", seg.user_prompt)
            self.assertIn("zhangsan", seg.user_prompt)

    def test_single_large_file_truncated(self):
        """单个超大文件应被截断"""
        files = [
            FileDiff("huge.py", "M", "+" * 50000, added_lines=10000, removed_lines=0)
        ]
        diff = DiffData(revision="1024", raw_diff="+" * 50000, file_diffs=files)

        segments = self.builder.build_segments(diff, _make_log(), max_chars_per_segment=10000)
        self.assertEqual(len(segments), 1)


class TestTokenEstimation(unittest.TestCase):
    """Token 估算测试"""

    def test_empty_text(self):
        self.assertEqual(PromptBuilder.estimate_tokens(""), 0)

    def test_english_text(self):
        text = "hello world this is a test"
        tokens = PromptBuilder.estimate_tokens(text)
        # 26 chars / 4.0 ≈ 6
        self.assertGreater(tokens, 0)
        self.assertLess(tokens, 20)

    def test_chinese_text(self):
        text = "这是一个中文测试文本"
        tokens = PromptBuilder.estimate_tokens(text)
        # 10 chars / 1.5 ≈ 6
        self.assertGreater(tokens, 0)
        self.assertLess(tokens, 20)

    def test_mixed_text(self):
        text = "Hello 世界 Test 测试"
        tokens = PromptBuilder.estimate_tokens(text)
        self.assertGreater(tokens, 0)


class TestTemplateLoading(unittest.TestCase):
    """模板加载测试"""

    def test_invalid_template_dir(self):
        with self.assertRaises(FileNotFoundError):
            PromptBuilder(templates_dir="/nonexistent/path")

    def test_templates_loaded(self):
        builder = PromptBuilder()
        self.assertTrue(len(builder._system_prompt_template) > 0)
        self.assertTrue(len(builder._review_prompt_template) > 0)


if __name__ == "__main__":
    unittest.main()
