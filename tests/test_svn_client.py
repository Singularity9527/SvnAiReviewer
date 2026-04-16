"""SVN Client 单元测试

通过 Mock 模拟 SVN 命令行输出，测试各解析逻辑的正确性。
无需真实 SVN 环境即可运行。
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from svn_client import (
    SVNClient,
    SVNClientError,
    SVNNotInstalledError,
    SVNCommandError,
    InvalidRevisionError,
)
from models.diff_data import DiffData, FileDiff
from models.log_data import LogData


class TestRevisionValidation(unittest.TestCase):
    """版本号验证测试"""

    def test_valid_single_revision(self):
        start, end = SVNClient.validate_revision("1024")
        self.assertEqual(start, "1024")
        self.assertIsNone(end)

    def test_valid_revision_range(self):
        start, end = SVNClient.validate_revision("1020:1025")
        self.assertEqual(start, "1020")
        self.assertEqual(end, "1025")

    def test_valid_head_revision(self):
        start, end = SVNClient.validate_revision("HEAD")
        self.assertEqual(start, "HEAD")
        self.assertIsNone(end)

    def test_valid_mixed_range(self):
        start, end = SVNClient.validate_revision("1020:HEAD")
        self.assertEqual(start, "1020")
        self.assertEqual(end, "HEAD")

    def test_empty_revision_raises(self):
        with self.assertRaises(InvalidRevisionError):
            SVNClient.validate_revision("")

    def test_invalid_revision_raises(self):
        with self.assertRaises(InvalidRevisionError):
            SVNClient.validate_revision("abc")

    def test_invalid_range_start_raises(self):
        with self.assertRaises(InvalidRevisionError):
            SVNClient.validate_revision("abc:1025")

    def test_whitespace_trimmed(self):
        start, end = SVNClient.validate_revision("  1024  ")
        self.assertEqual(start, "1024")
        self.assertIsNone(end)


class TestDiffParsing(unittest.TestCase):
    """Diff 输出解析测试"""

    SAMPLE_DIFF = """Index: src/main.py
===================================================================
--- src/main.py\t(revision 1023)
+++ src/main.py\t(revision 1024)
@@ -10,6 +10,8 @@
 import os
 import sys
+import logging
+import json

 def main():
-    print("hello")
+    print("hello world")
Index: src/utils.py
===================================================================
--- src/utils.py\t(revision 0)
+++ src/utils.py\t(revision 1024)
@@ -0,0 +1,5 @@
+def helper():
+    pass
+
+def format_output(data):
+    return str(data)
"""

    @patch("shutil.which", return_value="/usr/bin/svn")
    def setUp(self, mock_which):
        self.client = SVNClient()

    def test_parse_multi_file_diff(self):
        file_diffs = self.client._parse_diff_output(self.SAMPLE_DIFF)
        self.assertEqual(len(file_diffs), 2)
        self.assertEqual(file_diffs[0].file_path, "src/main.py")
        self.assertEqual(file_diffs[1].file_path, "src/utils.py")

    def test_parse_added_lines(self):
        file_diffs = self.client._parse_diff_output(self.SAMPLE_DIFF)
        main_diff = file_diffs[0]
        # +import logging, +import json, +print("hello world") = 3 added
        self.assertEqual(main_diff.added_lines, 3)
        # -print("hello") = 1 removed
        self.assertEqual(main_diff.removed_lines, 1)

    def test_parse_new_file(self):
        file_diffs = self.client._parse_diff_output(self.SAMPLE_DIFF)
        utils_diff = file_diffs[1]
        self.assertEqual(utils_diff.status, "A")  # 新增文件
        self.assertEqual(utils_diff.added_lines, 5)
        self.assertEqual(utils_diff.removed_lines, 0)

    def test_parse_empty_diff(self):
        file_diffs = self.client._parse_diff_output("")
        self.assertEqual(len(file_diffs), 0)

    def test_parse_none_diff(self):
        file_diffs = self.client._parse_diff_output(None)
        self.assertEqual(len(file_diffs), 0)

    def test_parse_status_output(self):
        raw_status = "M       src/main.py\nA       src/new_file.py\n?       tmp/debug.txt\n"
        status_map = self.client._parse_status_output(raw_status)
        self.assertEqual(status_map["src/main.py"], "M")
        self.assertEqual(status_map["src/new_file.py"], "A")
        self.assertEqual(status_map["tmp/debug.txt"], "?")


class TestLogParsing(unittest.TestCase):
    """Log 输出解析测试"""

    SAMPLE_LOG = """------------------------------------------------------------------------
r1024 | zhangsan | 2026-04-14 10:30:00 +0800 (Mon, 14 Apr 2026) | 2 lines
Changed paths:
   M /trunk/src/main.py
   A /trunk/src/utils.py

修复登录接口安全问题
增加输入参数校验
------------------------------------------------------------------------
"""

    SAMPLE_MULTI_LOG = """------------------------------------------------------------------------
r1024 | zhangsan | 2026-04-14 10:30:00 +0800 (Mon, 14 Apr 2026) | 1 lines
Changed paths:
   M /trunk/src/main.py

修复登录bug
------------------------------------------------------------------------
r1025 | lisi | 2026-04-14 11:00:00 +0800 (Mon, 14 Apr 2026) | 1 lines
Changed paths:
   A /trunk/src/config.py

新增配置模块
------------------------------------------------------------------------
"""

    SAMPLE_LOG_WITH_UNICODE_PLACEHOLDER = """------------------------------------------------------------------------
r38374 | yangql@SZNARI | 2026-04-16 09:34:50 +0800 (Thu, 16 Apr 2026) | 1 lines

feat(libservices):{U+589E}{U+52A0}{U+670D}{U+52A1}{U+8282}{U+70B9}{U+6269}{U+5C55}{U+4FE1}{U+606F}
------------------------------------------------------------------------
"""

    SAMPLE_LOG_ZH = """------------------------------------------------------------------------
r38374 | yangql@SZNARI | 2026-04-16 09:34:50 +0800 (周四, 2026-04-16) | 1 行
Changed paths:
   M /develop/01_Middleware/example.py

feat(libservices):增加服务节点扩展信息,客户端根据用户信息定位 author:liukai
------------------------------------------------------------------------
"""

    @patch("shutil.which", return_value="/usr/bin/svn")
    def setUp(self, mock_which):
        self.client = SVNClient()

    def test_parse_single_log(self):
        log = self.client._parse_log_output(self.SAMPLE_LOG, "1024")
        self.assertEqual(log.revision, "1024")
        self.assertEqual(log.author, "zhangsan")
        self.assertIn("2026-04-14", log.date)
        self.assertIn("修复登录接口安全问题", log.message)

    def test_parse_changed_paths(self):
        log = self.client._parse_log_output(self.SAMPLE_LOG, "1024")
        self.assertEqual(len(log.changed_paths), 2)
        self.assertIn("M /trunk/src/main.py", log.changed_paths[0])

    def test_parse_multi_log(self):
        logs = self.client._parse_multi_log_output(self.SAMPLE_MULTI_LOG)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].revision, "1024")
        self.assertEqual(logs[1].revision, "1025")
        self.assertEqual(logs[1].author, "lisi")

    def test_parse_empty_log(self):
        logs = self.client._parse_multi_log_output("")
        self.assertEqual(len(logs), 0)

    def test_parse_log_decodes_unicode_placeholder(self):
        log = self.client._parse_log_output(self.SAMPLE_LOG_WITH_UNICODE_PLACEHOLDER, "38374")
        self.assertIn("增加服务节点扩展信息", log.message)

    def test_parse_log_with_chinese_line_unit(self):
        log = self.client._parse_log_output(self.SAMPLE_LOG_ZH, "38374")
        self.assertEqual(log.author, "yangql@SZNARI")
        self.assertIn("增加服务节点扩展信息", log.message)


class TestDiffDataModel(unittest.TestCase):
    """DiffData 数据模型测试"""

    def test_diff_summary(self):
        diff = DiffData(
            revision="1024",
            raw_diff="...",
            file_diffs=[
                FileDiff("a.py", "M", "+line1\n-line2\n", added_lines=1, removed_lines=1),
                FileDiff("b.py", "A", "+new\n", added_lines=1, removed_lines=0),
            ],
        )
        self.assertEqual(diff.total_files, 2)
        self.assertEqual(diff.total_added_lines, 2)
        self.assertEqual(diff.total_removed_lines, 1)
        self.assertIn("2 个文件变更", diff.summary())

    def test_empty_diff(self):
        diff = DiffData(revision="1024", raw_diff="")
        self.assertTrue(diff.is_empty)

    def test_file_paths(self):
        diff = DiffData(
            revision="1024",
            raw_diff="...",
            file_diffs=[
                FileDiff("a.py", "M", "..."),
                FileDiff("b.py", "A", "..."),
            ],
        )
        self.assertEqual(diff.get_file_paths(), ["a.py", "b.py"])


class TestLogDataModel(unittest.TestCase):
    """LogData 数据模型测试"""

    def test_log_summary(self):
        log = LogData(
            revision="1024",
            author="zhangsan",
            date="2026-04-14 10:30:00",
            message="修复登录bug",
        )
        self.assertIn("r1024", log.summary())
        self.assertIn("zhangsan", log.summary())

    def test_empty_message(self):
        log = LogData(revision="1024", author="test", date="", message="")
        self.assertTrue(log.is_empty_message)

    def test_parsed_date(self):
        log = LogData(
            revision="1024",
            author="test",
            date="2026-04-14 10:30:00",
            message="test",
        )
        parsed = log.parsed_date
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 4)

    def test_long_message_truncated_in_summary(self):
        log = LogData(
            revision="1024",
            author="test",
            date="",
            message="A" * 100,
        )
        summary = log.summary()
        self.assertIn("...", summary)


class TestSVNClientIntegration(unittest.TestCase):
    """SVN Client 集成测试（Mock subprocess）"""

    @patch("shutil.which", return_value="/usr/bin/svn")
    def setUp(self, mock_which):
        self.client = SVNClient()

    @patch("subprocess.run")
    def test_get_diff_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""Index: test.py
===================================================================
--- test.py\t(revision 1023)
+++ test.py\t(revision 1024)
@@ -1,3 +1,4 @@
 line1
+line2
 line3
""",
            stderr="",
        )
        diff = self.client.get_diff("1024")
        self.assertIsNone(diff.error)
        self.assertEqual(len(diff.file_diffs), 1)
        self.assertEqual(diff.file_diffs[0].file_path, "test.py")

    @patch("subprocess.run")
    def test_get_diff_command_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="svn: E195012: Unable to find repository",
        )
        diff = self.client.get_diff("9999")
        self.assertIsNotNone(diff.error)

    @patch("subprocess.run")
    def test_get_log_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""------------------------------------------------------------------------
r1024 | admin | 2026-04-14 10:00:00 +0800 (Mon, 14 Apr 2026) | 1 lines

Fix bug
------------------------------------------------------------------------
""",
            stderr="",
        )
        log = self.client.get_log("1024")
        self.assertIsNone(log.error)
        self.assertEqual(log.author, "admin")

    @patch.object(SVNClient, "get_working_copy_status")
    @patch("subprocess.run")
    def test_get_working_copy_diff_success(self, mock_run, mock_status):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""Index: src/main.py
===================================================================
--- src/main.py	(revision 10)
+++ src/main.py	(working copy)
@@ -1 +1,2 @@
+line2
""",
            stderr="",
        )
        mock_status.return_value = {"src/main.py": "M", "tmp/debug.txt": "?"}

        diff = self.client.get_working_copy_diff()
        self.assertEqual(diff.revision, "LOCAL")
        self.assertIsNone(diff.error)
        self.assertEqual(len(diff.file_diffs), 2)
        self.assertEqual(diff.file_diffs[0].status, "M")
        self.assertEqual(diff.file_diffs[1].file_path, "tmp/debug.txt")
        self.assertEqual(diff.file_diffs[1].status, "?")

    @patch.object(SVNClient, "get_working_copy_status")
    @patch("subprocess.run")
    def test_get_working_copy_diff_command_error(self, mock_run, mock_status):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="svn: E155007: 'C:/repo' is not a working copy",
        )
        mock_status.return_value = {}

        diff = self.client.get_working_copy_diff()
        self.assertIsNotNone(diff.error)

    @patch("shutil.which", return_value=None)
    def test_svn_not_installed(self, mock_which):
        with self.assertRaises(SVNNotInstalledError):
            SVNClient()


if __name__ == "__main__":
    unittest.main()
