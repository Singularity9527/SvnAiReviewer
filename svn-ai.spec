# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - SVN AI 智能审查助手"""

import os

block_cipher = None

# 项目根目录
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['cli.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ('templates/*.md', 'templates'),
        ('config.yaml.example', '.'),
        ('README.md', '.'),
    ],
    hiddenimports=[
        'commands',
        'commands.review',
        'commands.config_cmd',
        'commands.generate_log_cmd',
        'models',
        'models.diff_data',
        'models.log_data',
        'ai_provider',
        'ai_provider.base',
        'ai_provider.cloud_provider',
        'ai_provider.local_provider',
        'ai_provider.factory',
        'config_manager',
        'svn_client',
        'prompt_builder',
        'report_generator',
        'batch_processor',
        'log_generator',
        'click',
        'rich',
        'rich.console',
        'rich.panel',
        'rich.table',
        'rich.syntax',
        'rich.progress',
        'rich.markdown',
        'yaml',
        'requests',
        'json',
        'logging',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pytest', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='svn-ai',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
