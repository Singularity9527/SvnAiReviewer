#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# SVN AI Reviewer - Linux 编译脚本
# 使用 PyInstaller 将项目编译为 Linux 可执行文件 (svn-ai)
# ============================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$PROJECT_DIR/dist"
BUILD_DIR="$PROJECT_DIR/build"
SPEC_FILE="$PROJECT_DIR/svn-ai.spec"
OUTPUT_FILE="$DIST_DIR/svn-ai"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9

print_header() {
    printf '\n========================================\n'
    printf '  SVN AI Reviewer - Linux 编译脚本\n'
    printf '========================================\n\n'
}

print_error() {
    printf '\n========================================\n'
    printf '  编译失败！\n'
    printf '========================================\n\n'
    printf '[错误] %s\n' "$1"
}

ensure_command() {
    local command_name="$1"
    local hint="$2"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        print_error "未找到 $command_name，$hint"
        exit 1
    fi
}

find_python() {
    local candidates=(python3.12 python3.11 python3.10 python3.9 python3 python)
    local candidate
    for candidate in "${candidates[@]}"; do
        if ! command -v "$candidate" >/dev/null 2>&1; then
            continue
        fi

        if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3, 9) else 1)
PY
        then
            printf '%s' "$candidate"
            return 0
        fi
    done

    return 1
}

print_header

printf '[1/5] 检查 Python 环境...\n'
if PYTHON_BIN="$(find_python)"; then
    :
else
    print_error '未找到可用的 Python 3.9+，请安装 Python 3.9 及以上版本，并确保命令如 python3.9 / python3.10 / python3.11 可用'
    exit 1
fi
"$PYTHON_BIN" --version
printf '\n'

printf '[2/5] 检查 pip 环境...\n'
"$PYTHON_BIN" -m pip --version >/dev/null 2>&1 || {
    print_error "当前使用的 $PYTHON_BIN 缺少 pip。请先执行 '$PYTHON_BIN -m ensurepip --upgrade'，或通过系统包管理器安装 python3-pip"
    exit 1
}
"$PYTHON_BIN" -m pip --version
printf '\n'

printf '[3/5] 检查 PyInstaller...\n'
if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
    printf '      PyInstaller 未安装，正在安装...\n'
    "$PYTHON_BIN" -m pip install pyinstaller
fi
printf '      PyInstaller '
"$PYTHON_BIN" -m PyInstaller --version
printf '\n'

printf '[4/5] 安装项目依赖并清理旧产物...\n'
"$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt"
rm -f "$OUTPUT_FILE"
rm -rf "$BUILD_DIR/svn-ai"
printf '      依赖安装完成，旧产物已清理\n\n'

printf '[5/5] 开始编译...\n\n'
cd "$PROJECT_DIR"
"$PYTHON_BIN" -m PyInstaller "$SPEC_FILE" --clean --noconfirm

if [[ ! -f "$OUTPUT_FILE" ]]; then
    print_error '未生成 dist/svn-ai，请检查上方错误信息'
    exit 1
fi

chmod +x "$OUTPUT_FILE"

printf '\n========================================\n'
printf '  编译成功！\n'
printf '========================================\n\n'
printf '  输出文件: %s\n' "$OUTPUT_FILE"

if command -v stat >/dev/null 2>&1; then
    FILE_SIZE_BYTES="$(stat -c %s "$OUTPUT_FILE")"
    FILE_SIZE_MB="$((FILE_SIZE_BYTES / 1024 / 1024))"
    printf '  文件大小: %s MB\n' "$FILE_SIZE_MB"
fi

printf '\n提示：目标 Linux 机器仍需安装 svn 命令行客户端。\n\n'
