"""SVN 命令封装模块

封装 SVN 命令行操作，提供获取代码差异(Diff)和提交日志(Log)的功能。
通过 subprocess 调用系统 SVN 客户端，并将结果解析为结构化数据模型。
"""
import logging
import re
import subprocess
import shutil
from typing import Dict, List, Optional, Tuple

from models.diff_data import DiffData, FileDiff
from models.log_data import LogData

logger = logging.getLogger(__name__)


class SVNClientError(Exception):
    """SVN 客户端异常基类"""
    pass


class SVNNotInstalledError(SVNClientError):
    """SVN 未安装异常"""
    pass


class SVNCommandError(SVNClientError):
    """SVN 命令执行异常"""

    def __init__(self, message: str, return_code: int = -1, stderr: str = ""):
        super().__init__(message)
        self.return_code = return_code
        self.stderr = stderr


class InvalidRevisionError(SVNClientError):
    """无效版本号异常"""
    pass


class SVNClient:
    """SVN 命令行封装客户端

    封装 svn diff、svn log 等命令，自动处理异常并返回结构化数据。

    用法示例::

        client = SVNClient(working_dir="/path/to/svn/repo")

        # 获取单版本 diff
        diff_data = client.get_diff("1024")

        # 获取版本范围 diff
        diff_data = client.get_diff("1020:1025")

        # 获取提交日志
        log_data = client.get_log("1024")
    """

    # SVN diff 中文件头的正则匹配
    _FILE_HEADER_PATTERN = re.compile(
        r"^Index:\s+(.+)$", re.MULTILINE
    )

    # SVN log 分隔线
    _LOG_SEPARATOR = "------------------------------------------------------------------------"

    # SVN log 信息行正则：r版本号 | 作者 | 日期 | 行数
    _LOG_INFO_PATTERN = re.compile(
        r"^r(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)\s+.+$"
    )

    # SVN 变更路径正则
    _CHANGED_PATH_PATTERN = re.compile(
        r"^\s+([AMDRC])\s+(.+)$"
    )

    # svn status 输出：首列为状态，文件路径位于末尾
    _STATUS_LINE_PATTERN = re.compile(r"^([ACDIMRX!?~ ])(?:.{0,6})\s+(.+)$")

    # 非标准 Unicode 占位符：{U+4E2D}
    _UNICODE_PLACEHOLDER_PATTERN = re.compile(r"\{U\+([0-9A-Fa-f]{4,6})\}")

    def __init__(self, working_dir: Optional[str] = None, svn_binary: str = "svn",
                 timeout: int = 60, encoding: str = None,
                 repo_url: Optional[str] = None, trust_server_cert: bool = False,
                 username: Optional[str] = None, password: Optional[str] = None):
        """初始化 SVN 客户端

        Args:
            working_dir: SVN 工作副本目录路径，默认使用当前目录
            svn_binary: SVN 可执行文件路径，默认 'svn'
            timeout: 命令执行超时时间（秒）
            encoding: 输出编码格式
            repo_url: 远程 SVN 仓库 URL（可替代 working_dir）
            trust_server_cert: 是否信任自签名 SSL 证书
            username: SVN 认证用户名
            password: SVN 认证密码
        """
        self.working_dir = working_dir
        self.svn_binary = svn_binary
        self.timeout = timeout
        self.encoding = encoding or self._detect_encoding()
        self.repo_url = repo_url
        self.trust_server_cert = trust_server_cert
        self.username = username
        self.password = password

        # 验证 SVN 是否可用
        self._check_svn_installed()

    @staticmethod
    def _detect_encoding() -> str:
        """检测系统默认编码，Windows 通常为 GBK"""
        import locale
        return locale.getpreferredencoding(False) or "utf-8"

    def _check_svn_installed(self) -> None:
        """检查 SVN 客户端是否已安装

        Raises:
            SVNNotInstalledError: SVN 客户端未安装或不在 PATH 中
        """
        if shutil.which(self.svn_binary) is None:
            raise SVNNotInstalledError(
                f"SVN 客户端未安装或不在 PATH 中。"
                f"请先安装 SVN 客户端：https://subversion.apache.org/packages.html"
            )

    def _run_command(self, args: List[str]) -> Tuple[str, str]:
        """执行 SVN 命令

        Args:
            args: SVN 命令参数列表（不含 svn 本身）

        Returns:
            Tuple[str, str]: (stdout, stderr) 输出内容

        Raises:
            SVNCommandError: 命令执行失败
            SVNClientError: 命令超时或其他异常
        """
        cmd = [self.svn_binary] + args

        # 添加认证和 SSL 参数
        if self.trust_server_cert:
            cmd.extend(["--non-interactive", "--trust-server-cert-failures=unknown-ca,cn-mismatch,expired,not-yet-valid,other"])
        elif "--non-interactive" not in cmd:
            cmd.append("--non-interactive")
        if self.username:
            cmd.extend(["--username", self.username])
        if self.password:
            cmd.extend(["--password", self.password])

        safe_cmd = []
        i = 0
        while i < len(cmd):
            item = cmd[i]
            safe_cmd.append(item)
            if item == "--password" and i + 1 < len(cmd):
                safe_cmd.append("***")
                i += 2
                continue
            i += 1

        logger.debug("执行命令: %s", " ".join(safe_cmd))

        try:
            result = subprocess.run(
                cmd,
                cwd=self.working_dir,
                capture_output=True,
                timeout=self.timeout,
            )

            stdout = self._decode_output(result.stdout)
            stderr = self._decode_output(result.stderr)

            if result.returncode != 0:
                error_msg = stderr.strip() or "未知错误"
                logger.error("SVN 命令失败 (code=%d): %s", result.returncode, error_msg)
                raise SVNCommandError(
                    f"SVN 命令执行失败: {error_msg}",
                    return_code=result.returncode,
                    stderr=stderr,
                )

            return stdout, stderr

        except subprocess.TimeoutExpired:
            raise SVNClientError(
                f"SVN 命令执行超时（{self.timeout}秒）: {' '.join(cmd)}"
            )
        except FileNotFoundError:
            raise SVNNotInstalledError(
                f"无法找到 SVN 可执行文件: {self.svn_binary}"
            )

    def _decode_output(self, data: bytes) -> str:
        """智能解码 SVN 输出

        优先尝试 UTF-8，失败则回退到系统编码（如 GBK）。
        """
        if not data:
            return ""
        if isinstance(data, str):
            return data
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode(self.encoding, errors="replace")

    @staticmethod
    def validate_revision(revision: str) -> Tuple[str, Optional[str]]:
        """验证并解析版本号

        支持格式:
            - 单版本号: "1024"
            - 版本范围: "1020:1025"
            - HEAD: "HEAD"
            - BASE: "BASE"

        Args:
            revision: 版本号字符串

        Returns:
            Tuple[str, Optional[str]]: (起始版本, 结束版本)，单版本时结束版本为 None

        Raises:
            InvalidRevisionError: 版本号格式无效
        """
        revision = revision.strip()

        if not revision:
            raise InvalidRevisionError("版本号不能为空")

        # 版本范围
        if ":" in revision:
            parts = revision.split(":", 1)
            start, end = parts[0].strip(), parts[1].strip()

            if not SVNClient._is_valid_single_revision(start):
                raise InvalidRevisionError(f"无效的起始版本号: {start}")
            if not SVNClient._is_valid_single_revision(end):
                raise InvalidRevisionError(f"无效的结束版本号: {end}")

            return start, end

        # 单版本号
        if not SVNClient._is_valid_single_revision(revision):
            raise InvalidRevisionError(f"无效的版本号: {revision}")

        return revision, None

    @staticmethod
    def _is_valid_single_revision(rev: str) -> bool:
        """检查单个版本号是否有效"""
        valid_keywords = {"HEAD", "BASE", "COMMITTED", "PREV"}
        return rev.upper() in valid_keywords or rev.isdigit()

    def get_diff(self, revision: str) -> DiffData:
        """获取指定版本的代码差异

        Args:
            revision: 版本号或版本范围（如 "1024" 或 "1020:1025"）

        Returns:
            DiffData: 结构化的差异数据

        Raises:
            InvalidRevisionError: 版本号格式无效
            SVNCommandError: SVN 命令执行失败
        """
        start_rev, end_rev = self.validate_revision(revision)

        # 构建 svn diff 命令参数
        if end_rev is not None:
            args = ["diff", "-r", f"{start_rev}:{end_rev}"]
        else:
            # 单版本号：对比前一个版本
            args = ["diff", "-c", start_rev]

        # 远程 URL 模式
        if self.repo_url:
            args.append(self.repo_url)

        try:
            stdout, _ = self._run_command(args)
        except SVNCommandError as e:
            return DiffData(
                revision=revision,
                raw_diff="",
                error=str(e),
            )

        # 解析 diff 输出
        file_diffs = self._parse_diff_output(stdout)

        return DiffData(
            revision=revision,
            raw_diff=stdout,
            file_diffs=file_diffs,
        )

    def get_working_copy_status(self) -> Dict[str, str]:
        """获取当前工作副本的本地变更状态。

        Returns:
            Dict[str, str]: 文件路径到状态码的映射
        """
        stdout, _ = self._run_command(["status"])
        return self._parse_status_output(stdout)

    def get_working_copy_diff(self) -> DiffData:
        """获取当前工作副本未提交的代码差异。"""
        try:
            stdout, _ = self._run_command(["diff"])
            status_map = self.get_working_copy_status()
        except SVNCommandError as e:
            return DiffData(
                revision="LOCAL",
                raw_diff="",
                error=str(e),
            )

        file_diffs = self._parse_diff_output(stdout)

        for file_diff in file_diffs:
            if file_diff.file_path in status_map:
                file_diff.status = status_map[file_diff.file_path]

        diff_paths = {file_diff.file_path for file_diff in file_diffs}
        for file_path, status in status_map.items():
            if file_path not in diff_paths:
                file_diffs.append(
                    FileDiff(
                        file_path=file_path,
                        status=status,
                        diff_content="",
                    )
                )

        return DiffData(
            revision="LOCAL",
            raw_diff=stdout,
            file_diffs=file_diffs,
        )

    def get_log(self, revision: str, verbose: bool = True) -> LogData:
        """获取指定版本的提交日志

        Args:
            revision: 版本号
            verbose: 是否包含变更路径列表

        Returns:
            LogData: 结构化的日志数据

        Raises:
            InvalidRevisionError: 版本号格式无效
            SVNCommandError: SVN 命令执行失败
        """
        start_rev, _ = self.validate_revision(revision)

        args = ["log", "-r", start_rev]
        if verbose:
            args.append("-v")  # 显示变更路径
        if self.repo_url:
            args.append(self.repo_url)

        try:
            stdout, _ = self._run_command(args)
        except SVNCommandError as e:
            return LogData(
                revision=start_rev,
                author="",
                date="",
                message="",
                error=str(e),
            )

        # 解析 log 输出
        return self._parse_log_output(stdout, start_rev)

    def get_log_range(self, start_rev: str, end_rev: str, verbose: bool = True) -> List[LogData]:
        """获取版本范围内的所有提交日志

        Args:
            start_rev: 起始版本号
            end_rev: 结束版本号
            verbose: 是否包含变更路径列表

        Returns:
            List[LogData]: 日志数据列表
        """
        args = ["log", "-r", f"{start_rev}:{end_rev}"]
        if verbose:
            args.append("-v")

        try:
            stdout, _ = self._run_command(args)
        except SVNCommandError as e:
            return [LogData(
                revision=f"{start_rev}:{end_rev}",
                author="",
                date="",
                message="",
                error=str(e),
            )]

        return self._parse_multi_log_output(stdout)

    def get_info(self) -> dict:
        """获取当前工作副本信息

        Returns:
            dict: 包含 URL、版本号等信息
        """
        stdout, _ = self._run_command(["info"])
        info = {}
        for line in stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                info[key.strip()] = value.strip()
        return info

    def _parse_diff_output(self, raw_diff: str) -> List[FileDiff]:
        """解析 svn diff 输出，拆分为各文件的 diff

        Args:
            raw_diff: svn diff 命令的原始输出

        Returns:
            List[FileDiff]: 按文件拆分的 diff 列表
        """
        if not raw_diff or raw_diff.strip() == "":
            return []

        file_diffs: List[FileDiff] = []

        # 按 "Index: " 行拆分文件
        matches = list(self._FILE_HEADER_PATTERN.finditer(raw_diff))

        if not matches:
            # 没有标准头，整体作为一个 diff
            return [FileDiff(
                file_path="unknown",
                status="M",
                diff_content=raw_diff,
            )]

        for i, match in enumerate(matches):
            file_path = match.group(1).strip()

            # 截取当前文件的 diff 内容（到下一个 Index: 之前）
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_diff)
            content = raw_diff[start:end]

            # 判断变更状态
            status = self._detect_file_status(content)

            file_diffs.append(FileDiff(
                file_path=file_path,
                status=status,
                diff_content=content,
            ))

        return file_diffs

    def _parse_status_output(self, raw_status: str) -> Dict[str, str]:
        """解析 svn status 输出。"""
        if not raw_status or raw_status.strip() == "":
            return {}

        results = {}
        for line in raw_status.splitlines():
            if not line.strip():
                continue

            match = self._STATUS_LINE_PATTERN.match(line)
            if not match:
                continue

            status = match.group(1).strip() or " "
            file_path = match.group(2).strip()
            if file_path:
                results[file_path] = status

        return results

    @staticmethod
    def _detect_file_status(diff_content: str) -> str:
        """根据 diff 内容检测文件变更状态

        Args:
            diff_content: 单个文件的 diff 内容

        Returns:
            str: 状态标识 M/A/D
        """
        has_add = False
        has_remove = False

        for line in diff_content.splitlines():
            if line.startswith("--- (nonexistent)") or line.startswith("--- (revision 0)"):
                return "A"  # 新增文件
            if line.startswith("+++ (nonexistent)"):
                return "D"  # 删除文件
            if line.startswith("+") and not line.startswith("+++"):
                has_add = True
            elif line.startswith("-") and not line.startswith("---"):
                has_remove = True

        if has_add and not has_remove:
            return "A"
        if has_remove and not has_add:
            return "D"
        return "M"  # 修改

    def _parse_log_output(self, raw_log: str, default_revision: str) -> LogData:
        """解析单条 svn log 输出

        Args:
            raw_log: svn log 命令的原始输出
            default_revision: 默认版本号（解析失败时使用）

        Returns:
            LogData: 解析后的日志数据
        """
        logs = self._parse_multi_log_output(raw_log)
        if logs:
            return logs[0]

        return LogData(
            revision=default_revision,
            author="",
            date="",
            message="",
            error="无法解析 SVN 日志输出",
        )

    def _parse_multi_log_output(self, raw_log: str) -> List[LogData]:
        """解析多条 svn log 输出

        SVN log 格式示例::

            ------------------------------------------------------------------------
            r1024 | zhangsan | 2026-04-14 10:30:00 +0800 | 3 lines
            Changed paths:
               M /trunk/src/main.py
               A /trunk/src/utils.py

            修复登录接口安全问题
            增加输入参数校验
            ------------------------------------------------------------------------

        Args:
            raw_log: svn log 命令的原始输出

        Returns:
            List[LogData]: 解析后的日志数据列表
        """
        if not raw_log or raw_log.strip() == "":
            return []

        results: List[LogData] = []
        lines = raw_log.splitlines()

        i = 0
        while i < len(lines):
            # 跳过分隔线
            if lines[i].startswith("---"):
                i += 1
                continue

            # 尝试匹配日志信息行
            match = self._LOG_INFO_PATTERN.match(lines[i].strip())
            if not match:
                i += 1
                continue

            revision = match.group(1)
            author = match.group(2).strip()
            date = match.group(3).strip()
            msg_line_count = int(match.group(4))
            i += 1

            # 解析变更路径
            changed_paths: List[str] = []
            if i < len(lines) and lines[i].strip().startswith("Changed paths:"):
                i += 1
                while i < len(lines):
                    path_match = self._CHANGED_PATH_PATTERN.match(lines[i])
                    if path_match:
                        changed_paths.append(f"{path_match.group(1)} {path_match.group(2)}")
                        i += 1
                    else:
                        break

            # 跳过空行
            while i < len(lines) and lines[i].strip() == "":
                i += 1

            # 读取提交信息
            message_lines: List[str] = []
            for _ in range(msg_line_count):
                if i < len(lines) and not lines[i].startswith("---"):
                    message_lines.append(lines[i])
                    i += 1
                else:
                    break

            message = "\n".join(message_lines).strip()
            message = self._decode_unicode_placeholders(message)

            results.append(LogData(
                revision=revision,
                author=author,
                date=date,
                message=message,
                changed_paths=changed_paths,
            ))

        return results

    @classmethod
    def _decode_unicode_placeholders(cls, text: str) -> str:
        """将 {U+XXXX} 形式的占位符还原为真实字符。"""
        if not text:
            return text

        def _replace(match: re.Match) -> str:
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)

        return cls._UNICODE_PLACEHOLDER_PATTERN.sub(_replace, text)

    def get_revisions_in_range(self, start_rev: str, end_rev: str) -> List[str]:
        """获取版本范围内的所有版本号列表

        Args:
            start_rev: 起始版本号
            end_rev: 结束版本号

        Returns:
            List[str]: 版本号列表
        """
        args = ["log", "-r", f"{start_rev}:{end_rev}", "-q"]

        try:
            stdout, _ = self._run_command(args)
        except SVNCommandError:
            return []

        revisions = []
        for line in stdout.splitlines():
            match = re.match(r"^r(\d+)\s*\|", line.strip())
            if match:
                revisions.append(match.group(1))

        return revisions
