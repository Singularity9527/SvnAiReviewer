# SVN AI 智能审查助手

基于 AI 的 SVN 代码审查命令行工具，支持本地私有化部署（Ollama/vLLM）和云端 API（OpenAI/阿里云百炼等兼容接口）。

## 功能特性

- **代码审查** — 对 SVN 提交进行 AI 驱动的安全性、逻辑性、规范性审查
- **批量审查** — 支持版本范围批量审查，自动汇总报告
- **远程审查** — 支持直接审查远程 SVN 仓库（无需本地工作副本）
- **自签名证书** — 支持企业内网自签名 SSL 证书
- **报告生成** — Markdown / JSON 格式报告，终端美化渲染
- **自动日志** — 根据代码变更自动生成提交日志
- **配置向导** — 交互式配置 AI 模型参数

---

## 安装

### 环境要求

- Python 3.9+
- SVN 命令行客户端（如 TortoiseSVN 的 command line tools）

### 方式一：pip 安装（推荐）

```bash
pip install svn_ai_reviewer-1.0.0-py3-none-any.whl
```

### 方式二：源码安装

```bash
cd svn-ai-reviewer
pip install .
```

### 方式三：开发模式

```bash
cd svn-ai-reviewer
pip install -e .
```

### 验证安装

```bash
svn-ai --version
svn-ai --help
```

---

## 快速开始

### 1. 配置 AI 模型

#### 交互式配置（推荐）

```bash
svn-ai config
```

按提示选择 AI 模式（本地/云端）并填写参数，配置自动保存到 `~/.svn-ai/config.yaml`。

#### 手动配置

创建 `~/.svn-ai/config.yaml`：

```yaml
# 本地模式（Ollama）
ai_mode: local
local:
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5-coder:7b"
  api_key: "ollama"
```

```yaml
# 云端模式（OpenAI 兼容接口）
ai_mode: cloud
cloud:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  api_key: "sk-your-api-key"
  temperature: 0.3
  max_tokens: 4096
  timeout: 120
```

### 2. 测试连接

```bash
svn-ai test-connection
```

### 3. 审查代码

```bash
# 审查本地工作副本中的提交
svn-ai review -r 1024

# 指定工作副本目录
svn-ai review -r 1024 -d /path/to/svn/working-copy

# 审查远程 SVN 仓库（无需工作副本）
svn-ai review -r 1024 -u https://svn.example.com/repo/trunk

# 内网自签名证书
svn-ai review -r 1024 -u https://10.1.0.101/svn/project --trust-ssl
```

---

## 命令详解

### `svn-ai review` — 代码审查

```
用法: svn-ai review [OPTIONS]

选项:
  -r, --revision TEXT    版本号或范围 (如: 1024 或 1020:1025)  [必填]
  -d, --working-dir DIR  SVN 工作副本目录
  -u, --url URL          远程 SVN 仓库 URL
  --trust-ssl            信任自签名 SSL 证书
  --format [markdown|json]  输出格式 (默认: markdown)
  -o, --output FILE      保存报告到文件
  --show-prompt          显示发送给 AI 的 Prompt（调试用）
  --max-chars INT        Diff 最大字符数限制
  --dry-run              仅获取 Diff，不调用 AI
```

**示例：**

```bash
# 单版本审查
svn-ai review -r 37965

# 版本范围批量审查（自动逐版本审查并汇总）
svn-ai review -r 37960:37965

# 保存报告
svn-ai review -r 1024 -o review_report.md

# JSON 格式报告
svn-ai review -r 1024 --format json -o report.json

# 仅预览变更（不调用 AI）
svn-ai review -r 1024 --dry-run

# 远程仓库 + 内网证书
svn-ai review -r 37965 -u https://10.1.0.101/svn/CygSys/develop --trust-ssl
```

### `svn-ai config` — 配置管理

```bash
# 交互式配置向导
svn-ai config

# 查看当前配置
svn-ai config --show
```

### `svn-ai test-connection` — 测试 AI 连接

```bash
svn-ai test-connection
```

### `svn-ai generate-log` — 自动生成提交日志

```bash
# 在 SVN 工作副本中生成提交日志
svn-ai generate-log

# 指定工作目录
svn-ai generate-log -d /path/to/working-copy
```

---

## 配置文件

配置文件搜索顺序（优先级从高到低）：

1. 当前目录下的 `config.yaml`
2. 当前目录下的 `.svn-ai/config.yaml`
3. 用户目录 `~/.svn-ai/config.yaml`

### 完整配置项

```yaml
ai_mode: local  # local 或 cloud

local:
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5-coder:7b"
  api_key: "ollama"
  temperature: 0.3      # 可选，生成温度 (0-2)
  max_tokens: 4096       # 可选，最大输出 token
  timeout: 120           # 可选，请求超时（秒）

cloud:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  api_key: "sk-..."
  temperature: 0.3
  max_tokens: 4096
  timeout: 120

review:
  max_diff_chars: 60000  # 可选，Diff 最大字符数
```

---

## 支持的 AI 服务

| 模式 | 服务 | base_url 示例 |
|------|------|---------------|
| local | Ollama | `http://localhost:11434/v1` |
| local | vLLM | `http://localhost:8000/v1` |
| cloud | OpenAI | `https://api.openai.com/v1` |
| cloud | 阿里云百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| cloud | DeepSeek | `https://api.deepseek.com/v1` |
| cloud | 其他兼容接口 | 任何 OpenAI Compatible API |

---

## SVN 环境配置

### Windows (TortoiseSVN)

1. 运行 TortoiseSVN 安装程序 → 选择 **Modify**
2. 勾选 **command line client tools**
3. 将 `C:\Program Files\TortoiseSVN\bin` 添加到系统 PATH

### 验证 SVN

```bash
svn --version --quiet
```

---

## 常见问题

### Q: `svn-ai` 命令找不到？

将 Python Scripts 目录添加到 PATH：
```bash
# Windows
set PATH=%APPDATA%\..\Local\Python\Python3x\Scripts;%PATH%
```

### Q: 内网 SVN 提示 SSL 证书错误？

使用 `--trust-ssl` 参数：
```bash
svn-ai review -r 1024 -u https://内网地址/svn/repo --trust-ssl
```

### Q: 中文乱码？

工具已内置智能编码检测（UTF-8 优先，GBK 回退），一般不会出现乱码。

### Q: AI 响应超时？

在配置文件中增大 `timeout` 值：
```yaml
cloud:
  timeout: 300  # 5分钟
```

---

## 项目结构

```
svn-ai-reviewer/
├── cli.py                 # 命令行入口
├── svn_client.py          # SVN 命令封装
├── prompt_builder.py      # Prompt 构建器
├── config_manager.py      # 配置管理器
├── report_generator.py    # 报告生成器
├── batch_processor.py     # 批量审查处理器
├── log_generator.py       # 提交日志生成器
├── ai_provider/           # AI 推理接口
│   ├── base.py            # 抽象基类 + 重试机制
│   ├── local_provider.py  # 本地模式 (Ollama/vLLM)
│   ├── cloud_provider.py  # 云端模式 (OpenAI 等)
│   └── factory.py         # 工厂模式创建 Provider
├── commands/              # CLI 命令实现
├── models/                # 数据模型
├── templates/             # Prompt 和报告模板
├── pyproject.toml         # 打包配置
└── requirements.txt       # 依赖清单
```

## 许可证

MIT License
