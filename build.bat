@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
:: SVN AI Reviewer - 编译脚本
:: 使用 PyInstaller 将项目编译为独立可执行文件 (svn-ai.exe)
:: ============================================================

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist"
set "BUILD_DIR=%PROJECT_DIR%build"
set "SPEC_FILE=%PROJECT_DIR%svn-ai.spec"

echo.
echo ========================================
echo   SVN AI Reviewer - 编译脚本
echo ========================================
echo.

:: --- 检查 Python 环境 ---
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请确保 Python 已安装并添加到 PATH
    goto :error
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo       %%i
echo.

:: --- 检查 PyInstaller ---
echo [2/5] 检查 PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo       PyInstaller 未安装，正在安装...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败
        goto :error
    )
)
for /f "tokens=*" %%i in ('python -m PyInstaller --version 2^>^&1') do echo       PyInstaller %%i
echo.

:: --- 安装项目依赖 ---
echo [3/5] 安装项目依赖...
python -m pip install -r "%PROJECT_DIR%requirements.txt" --quiet
if errorlevel 1 (
    echo [错误] 依赖安装失败
    goto :error
)
echo       依赖安装完成
echo.

:: --- 清理旧的构建产物 ---
echo [4/5] 清理旧的构建产物...
if exist "%DIST_DIR%\svn-ai.exe" del /f /q "%DIST_DIR%\svn-ai.exe"
if exist "%BUILD_DIR%\svn-ai" rd /s /q "%BUILD_DIR%\svn-ai"
echo       清理完成
echo.

:: --- 执行 PyInstaller 编译 ---
echo [5/5] 开始编译...
echo.
cd /d "%PROJECT_DIR%"
python -m PyInstaller "%SPEC_FILE%" --clean --noconfirm
if not exist "%DIST_DIR%\svn-ai.exe" (
    echo.
    echo [错误] 编译失败！未生成 svn-ai.exe，请检查上方错误信息
    goto :error
)

echo.
echo ========================================
echo   编译成功！
echo ========================================
echo.
echo   输出文件: %DIST_DIR%\svn-ai.exe
echo.

:: 显示文件大小
for %%A in ("%DIST_DIR%\svn-ai.exe") do (
    set "size=%%~zA"
    set /a "sizeMB=!size! / 1048576"
    echo   文件大小: !sizeMB! MB
)
echo.

goto :end

:error
echo.
echo ========================================
echo   编译失败！
echo ========================================
echo.
exit /b 1

:end
endlocal
