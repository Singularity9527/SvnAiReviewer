@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
:: SVN AI Reviewer - 打包脚本
:: 生成 Python 安装包 (wheel + sdist)
:: ============================================================

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist"

echo.
echo ========================================
echo   SVN AI Reviewer - 打包脚本
echo ========================================
echo.

:: --- 检查 Python 环境 ---
echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请确保 Python 已安装并添加到 PATH
    goto :error
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo       %%i
echo.

:: --- 检查并安装 build 工具 ---
echo [2/4] 检查 build 工具...
python -m build --version >nul 2>&1
if errorlevel 1 (
    echo       build 模块未安装，正在安装...
    python -m pip install build
    if errorlevel 1 (
        echo [错误] build 模块安装失败
        goto :error
    )
)
echo       build 工具就绪
echo.

:: --- 清理旧的打包产物 ---
echo [3/4] 清理旧的打包产物...
if exist "%DIST_DIR%\*.whl" del /f /q "%DIST_DIR%\*.whl"
if exist "%DIST_DIR%\*.tar.gz" del /f /q "%DIST_DIR%\*.tar.gz"
if exist "%PROJECT_DIR%svn_ai_reviewer.egg-info" rd /s /q "%PROJECT_DIR%svn_ai_reviewer.egg-info"
echo       清理完成
echo.

:: --- 执行打包 ---
echo [4/4] 开始打包...
echo.
cd /d "%PROJECT_DIR%"
python -m build
if errorlevel 1 (
    echo.
    echo [错误] 打包失败！请检查上方错误信息
    goto :error
)

echo.
echo ========================================
echo   打包成功！
echo ========================================
echo.
echo   输出目录: %DIST_DIR%
echo.
echo   生成的文件:
for %%F in ("%DIST_DIR%\*.whl") do (
    echo     [wheel] %%~nxF
)
for %%F in ("%DIST_DIR%\*.tar.gz") do (
    echo     [sdist] %%~nxF
)
echo.
echo   安装方式:
echo     pip install dist\svn_ai_reviewer-1.0.0-py3-none-any.whl
echo.

goto :end

:error
echo.
echo ========================================
echo   打包失败！
echo ========================================
echo.
exit /b 1

:end
endlocal
