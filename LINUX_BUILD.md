# Linux 构建说明

本文档说明如何将 `svn-ai` 构建为可在 Linux 上执行的单文件程序。

## 1. 结论先说

- 请在 Linux 环境中构建 Linux 可执行文件。
- 不建议在 Windows 上直接交叉编译 Linux 可执行文件。
- 当前项目使用 `PyInstaller` 打包，通常需要“在哪个平台构建，就产出哪个平台的可执行文件”。

推荐的构建环境：

- 原生 Linux 机器
- WSL2（Ubuntu 等）
- Docker Linux 容器
- Linux CI 环境（如 GitHub Actions / GitLab CI）

## 2. 前置要求

构建机器需要：

- Python 3.9+
- pip
- bash
- `svn` 命令行客户端

注意：Python 3.4、3.5、3.6、3.7、3.8 都不满足当前项目构建要求。

建议先确认：

```bash
python3 --version
python3 -m pip --version
svn --version
```

如果系统里同时存在多个 Python 版本，建议显式使用 `python3.9`、`python3.10` 或 `python3.11`。

Ubuntu / Debian 可参考：

```bash
sudo apt update
sudo apt install -y python3.11 python3-pip subversion
```

如果系统提示没有 `pip`，可以尝试：

```bash
python3.11 -m ensurepip --upgrade
python3.11 -m pip --version
```

## 3. 一键构建

项目根目录已经提供 Linux 构建脚本：`build.sh`

执行步骤：

```bash
chmod +x build.sh
./build.sh
```

脚本会自动完成以下事情：

1. 检查 Python 与 pip
2. 检查并安装 `PyInstaller`
3. 安装 `requirements.txt` 中的依赖
4. 清理旧的构建产物
5. 调用 `svn-ai.spec` 生成 Linux 可执行文件

脚本会优先查找可用的 `python3.12` / `python3.11` / `python3.10` / `python3.9`。
如果系统默认 `python3` 太旧，脚本会直接报错，而不会继续构建。

构建成功后，产物位于：

```bash
dist/svn-ai
```

## 4. 手动构建命令

如果你不想使用脚本，也可以手动执行：

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller
python3 -m PyInstaller svn-ai.spec --clean --noconfirm
chmod +x dist/svn-ai
```

如果你的系统默认 `python3` 不是 3.9+，请改成明确版本，例如：

```bash
python3.11 -m pip install -r requirements.txt
python3.11 -m pip install pyinstaller
python3.11 -m PyInstaller svn-ai.spec --clean --noconfirm
chmod +x dist/svn-ai
```

## 5. 运行方式

在 Linux 上运行：

```bash
./dist/svn-ai --help
./dist/svn-ai review --local --dry-run
```

如果想全局使用，可自行复制到 PATH 目录，例如：

```bash
sudo cp dist/svn-ai /usr/local/bin/
svn-ai --help
```

## 6. 运行时依赖说明

请注意，`svn-ai` 虽然会被打包成单文件程序，但目标 Linux 机器仍然需要安装：

- `svn` 命令行客户端

原因是本项目通过外部 `svn` 命令获取：

- 版本 diff
- 本地工作副本未提交代码差异
- 提交日志
- 工作副本状态

目标机器建议验证：

```bash
svn --version
./dist/svn-ai --version
```

## 7. 兼容性建议

- 尽量在“较老但仍受支持”的 Linux 环境中构建，以提升兼容性。
- 如果你在很新的 Linux 发行版上构建，放到较老系统运行时，可能会遇到 `glibc` 版本不兼容。
- 如果目标环境不确定，优先考虑在 Docker 中使用较通用的基础镜像构建。

例如，可考虑：

- Ubuntu 20.04 / 22.04
- Debian 11 / 12

## 8. WSL2 构建建议

如果你当前主要在 Windows 开发，推荐直接用 WSL2：

1. 在 Windows 安装 WSL2 和 Ubuntu
2. 在 WSL 中进入本项目目录
3. 按本文档执行 `./build.sh`

这样得到的产物是 Linux 可执行文件，而不是 Windows `.exe`。

## 9. Docker 构建示例

如果你更习惯 Docker，可以在 Linux 容器中构建：

```bash
docker run --rm -it \
  -v "$PWD":/workspace \
  -w /workspace \
  python:3.11-bullseye \
  bash -lc "apt-get update && apt-get install -y subversion && ./build.sh"
```

构建完成后，产物会出现在宿主机当前目录的 `dist/svn-ai`。

## 10. 常见问题

### Q1: 能不能在 Windows 上直接编译 Linux 可执行文件？

不建议。对当前项目和 `PyInstaller` 来说，更可靠的方式是在 Linux 环境中构建。

### Q2: Linux 可执行文件是否可以脱离 Python 运行？

通常可以，不需要目标机器额外安装 Python。

但仍需要目标机器安装 `svn` 命令行客户端。

### Q3: 为什么运行时报找不到 `svn`？

因为 `svn-ai` 会调用系统里的 `svn`。请先安装：

```bash
sudo apt install -y subversion
```

### Q4: 为什么在目标机器运行时提示 `glibc` 相关错误？

通常是构建环境太新、目标环境太旧造成的。请改用更老一点、更通用的 Linux 环境重新构建。

### Q5: `./build.sh` 提示 Python 太旧或没有 pip 怎么办？

你当前环境里的 Python 很可能低于 3.9，例如 3.4.2，这个版本不能用于本项目构建。

建议安装较新的 Python，然后显式检查：

```bash
python3.11 --version
python3.11 -m pip --version
```

如果没有 pip：

```bash
python3.11 -m ensurepip --upgrade
```
