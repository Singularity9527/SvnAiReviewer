@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
:: SVN AI Reviewer - 一键发布脚本
:: 编译 exe + 打包 wheel/sdist + 归档到 release 目录
:: ============================================================

set "PROJECT_DIR=%~dp0"
set "DIST_DIR=%PROJECT_DIR%dist"
set "RELEASE_DIR=%PROJECT_DIR%release"
set "INSTALLER_DIR=%PROJECT_DIR%installer"

:: 从 pyproject.toml 读取版本号
for /f "tokens=2 delims==" %%v in ('findstr /C:"version" "%PROJECT_DIR%pyproject.toml"') do (
    set "RAW_VER=%%v"
    set "VERSION=!RAW_VER: =!"
    set "VERSION=!VERSION:"=!"
    goto :got_version
)
:got_version

echo.
echo ========================================
echo   SVN AI Reviewer - 一键发布
echo   版本: %VERSION%
echo ========================================
echo.

:: --- 第一步：编译 exe ---
echo [阶段 1/3] 编译可执行文件...
echo ----------------------------------------
call "%PROJECT_DIR%build.bat"
if errorlevel 1 (
    echo [错误] 编译阶段失败，发布中止
    goto :error
)
echo.

:: --- 第二步：打包 Python 安装包 ---
echo [阶段 2/3] 打包 Python 安装包...
echo ----------------------------------------
call "%PROJECT_DIR%package.bat"
if errorlevel 1 (
    echo [错误] 打包阶段失败，发布中止
    goto :error
)
echo.

:: --- 第三步：归档发布产物 ---
echo [阶段 3/3] 归档发布产物...
echo ----------------------------------------
echo.

:: 创建版本发布目录
set "VER_DIR=%RELEASE_DIR%\v%VERSION%"
if not exist "%VER_DIR%" mkdir "%VER_DIR%"

:: 复制 exe
if exist "%DIST_DIR%\svn-ai.exe" (
    copy /y "%DIST_DIR%\svn-ai.exe" "%VER_DIR%\" >nul
    echo   [已归档] svn-ai.exe
)

:: 复制 wheel 和 sdist
for %%F in ("%DIST_DIR%\*.whl") do (
    copy /y "%%F" "%VER_DIR%\" >nul
    echo   [已归档] %%~nxF
)
for %%F in ("%DIST_DIR%\*.tar.gz") do (
    copy /y "%%F" "%VER_DIR%\" >nul
    echo   [已归档] %%~nxF
)

:: 复制配置文件示例
if exist "%PROJECT_DIR%config.yaml.example" (
    copy /y "%PROJECT_DIR%config.yaml.example" "%VER_DIR%\" >nul
    echo   [已归档] config.yaml.example
)

:: 复制 README
if exist "%PROJECT_DIR%README.md" (
    copy /y "%PROJECT_DIR%README.md" "%VER_DIR%\" >nul
    echo   [已归档] README.md
)

:: 同步到 installer 目录（用于分发）
if not exist "%INSTALLER_DIR%" mkdir "%INSTALLER_DIR%"
if exist "%DIST_DIR%\svn-ai.exe" (
    copy /y "%DIST_DIR%\svn-ai.exe" "%INSTALLER_DIR%\" >nul
)
if exist "%PROJECT_DIR%config.yaml.example" (
    copy /y "%PROJECT_DIR%config.yaml.example" "%INSTALLER_DIR%\" >nul
)

echo.
echo ========================================
echo   发布完成！ v%VERSION%
echo ========================================
echo.
echo   发布目录: %VER_DIR%
echo.
echo   目录内容:
for %%F in ("%VER_DIR%\*") do (
    for %%A in ("%%F") do (
        set "fsize=%%~zA"
        set /a "fKB=!fsize! / 1024"
        echo     %%~nxF  (!fKB! KB^)
    )
)
echo.
echo   安装器目录: %INSTALLER_DIR%
echo.

goto :end

:error
echo.
echo ========================================
echo   发布失败！
echo ========================================
echo.
exit /b 1

:end
endlocal
