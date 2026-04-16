# AGENTS.md

本文件面向在本仓库中工作的自动化编码代理。
目标是帮助代理快速理解构建方式、测试入口与现有代码风格。

## 适用范围
- 本文件适用于 `SvnAiReviewer/` 整个仓库。
- 当前未发现 `.cursorrules`、`.cursor/rules/` 或 `.github/copilot-instructions.md`。
- 因此没有额外的 Cursor / Copilot 仓库级规则需要继承。

## 项目概览
- 语言：Python 3.9+。
- 打包方式：`setuptools` + `python -m build`。
- CLI 框架：`click`。
- 终端渲染：`rich`。
- 配置格式：YAML。
- HTTP 调用：`requests`。
- 测试框架：`unittest`，不是 pytest 风格。
- 入口脚本：`cli.py`，控制台命令为 `svn-ai`。
- 模块布局较扁平，顶层 `.py` 文件与包目录并存。

## 常用命令
### 安装依赖
```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```
- 开发时优先使用 `pip install -e .`。
- 若只想运行脚本，也可以仅安装 `requirements.txt`。
### 运行 CLI
```bash
python cli.py --help
python -m cli --help
svn-ai --help
```
- 仓库已经在 `pyproject.toml` 中声明了 `svn-ai = "cli:main"`。
- 若未安装入口脚本，直接用 `python cli.py` 即可。

## 测试命令
### 运行全部测试
```bash
python -m unittest discover -s tests
```
- 这是当前仓库最可靠的全量测试命令。
- 已实测可通过，当前套件规模约 200+ 个测试。
### 运行单个测试文件
```bash
python -m unittest tests.test_svn_client
python -m unittest tests.test_cli
```
### 运行单个测试类
```bash
python -m unittest tests.test_svn_client.TestRevisionValidation
python -m unittest tests.test_cli.TestReviewCommand
```
### 运行单个测试方法
```bash
python -m unittest tests.test_svn_client.TestRevisionValidation.test_valid_single_revision
python -m unittest tests.test_cli.TestReviewCommand.test_review_dry_run_with_diff
```
- 修改单个模块后，优先跑对应测试类或测试方法。
- 涉及 CLI 入口、配置、SVN 解析、AI provider 基类时，再补全量测试。

## 构建与发布命令
### 构建 Python 包
```bash
python -m build
```
- 会生成 `dist/*.whl` 与 `dist/*.tar.gz`。
- `package.bat` 本质上也是围绕该命令做检查、清理和包装。
### Windows 下构建可执行文件
```bat
build.bat
```
- 通过 `PyInstaller` 和 `svn-ai.spec` 生成 `dist/svn-ai.exe`。
- 脚本会自动安装缺失的 `pyinstaller` 与运行时依赖。
### Windows 下打包发布
```bat
package.bat
release.bat
```
- `package.bat`：生成 wheel 与 sdist。
- `release.bat`：先编译 exe，再打包 Python 安装包，并归档到 `release/`。

## Lint / 格式化现状
- 当前仓库未配置 `ruff`、`flake8`、`pylint`、`black`、`isort` 或 `mypy`。
- 当前也没有 `pytest` 配置。
- 不要假设仓库遵循 Black 风格后再大范围重排代码。
### 可接受的轻量检查
```bash
python -m compileall .
python -m unittest discover -s tests
```
- 若用户要求“lint”，应明确说明仓库没有正式 lint 工具链。
- 默认用 `compileall` 做语法烟雾检查，用 `unittest` 做行为验证。

## 目录约定
- `cli.py`：CLI 根入口。
- `commands/`：各子命令实现。
- `models/`：dataclass 数据模型。
- `ai_provider/`：AI provider 抽象层与具体实现。
- 顶层模块如 `svn_client.py`、`prompt_builder.py`、`report_generator.py`：核心业务逻辑。
- `templates/`：Markdown prompt 与报告模板。
- `tests/`：单元测试，覆盖核心逻辑较多。

## 导入风格
- 遵循三段式导入：标准库、第三方、本地模块。
- 各导入组之间保留一个空行。
- 本仓库大量使用扁平模块导入，例如 `from svn_client import SVNClient`。
- 不要无故改成包内相对导入，除非你准备整体迁移导入体系。
- 除非正在做明确的包结构重构，否则保留这种兼容写法。

## 格式化风格
- 缩进使用 4 个空格。
- 常量使用全大写加下划线，例如 `DEFAULT_CONFIG_PATH`。
- 长参数列表通常采用悬挂缩进，和现有文件保持一致。
- 文档字符串和用户可见文本以中文为主。
- 文件读写显式写 `encoding="utf-8"`。

## 类型与数据建模
- 现有代码广泛使用 `typing` 旧式标注：`List`、`Dict`、`Optional`、`Tuple`。
- 新代码应优先沿用这一风格，不要在同一文件里混用大量 `list[str]` / `dict[str, Any]` 新语法。
- 简单结构优先使用 `@dataclass`，见 `models/` 与 `ai_provider/base.py`。
- 复杂返回值常用结构化对象而不是裸字典。
- 布尔语义优先通过 `@property` 暴露，如 `is_empty`、`is_success`。

## 命名约定
- 模块文件名使用 `snake_case`。
- 类名使用 `PascalCase`。
- 函数、方法、变量使用 `snake_case`。
- Click 命令对象通常命名为 `xxx_command`。
- 内部辅助函数以前导下划线标识，例如 `_do_review`、`_load_template`。
- 异常类型使用 `Error` 后缀，例如 `ConfigError`、`SVNCommandError`。

## 错误处理
- 每个核心模块通常定义自己的异常层级，先复用再新增。
- 基础设施层错误尽量转换为清晰的中文错误信息。
- CLI 层负责把异常转换为用户可见输出，并以 `sys.exit(...)` 结束。
- 新逻辑应和所在模块保持一致：不要混入完全不同的错误传播策略。

## 日志与输出
- 模块级 logger 写法统一为 `logger = logging.getLogger(__name__)`。
- 调试信息走 `logging`，不要用 `print` 代替。
- 面向 CLI 用户的输出由 `click` 或 `rich` 完成。
- 新增终端消息时保持中文，并与现有成功/警告/失败语气一致。

## 测试风格
- 使用 `unittest.TestCase` 组织测试。
- Mock 优先使用 `unittest.mock.patch` 和 `MagicMock`。
- CLI 测试使用 `click.testing.CliRunner`。
- 现有测试偏单元测试，尽量避免真实网络、真实 SVN、真实 AI 调用。
- 需要外部依赖的地方通常通过 patch `subprocess.run`、`requests.post`、`shutil.which` 解决。

## 变更建议
- 优先做小而集中的修改，不要顺手大规模重排 import 或重写格式。
- 保持中文文案、异常文本和帮助信息风格统一。
- 若新增模块，请同步补充对应 `tests/test_*.py`。
- 若改动入口行为，请至少覆盖一个 CLI 测试。
- 若改动解析逻辑，请优先补充样例驱动测试。

## 代理工作准则
- 先读相关模块和测试，再修改代码。
- 先运行最小相关测试，再决定是否跑全量测试。
- 不要引入新的工具链配置，除非用户明确要求。
- 提交结果时说明你实际运行了哪些命令、哪些没有运行。
