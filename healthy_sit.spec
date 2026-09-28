# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import sysconfig
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

PROJECT_ROOT = os.path.abspath(SPECPATH)
SITE_PACKAGES = sysconfig.get_paths()['purelib']
PYTHON_BASE = sys.base_prefix if getattr(sys, 'base_prefix', None) else os.path.dirname(sys.executable)
SYSTEM32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')

NUMPY_LIBS = os.path.join(SITE_PACKAGES, 'numpy.libs')
SCIPY_LIBS = os.path.join(SITE_PACKAGES, 'scipy.libs')
MEDIAPIPE_DIR = os.path.join(SITE_PACKAGES, 'mediapipe')
POSE_LANDMARK_DIR = os.path.join(MEDIAPIPE_DIR, 'modules', 'pose_landmark')
HOOKS_DIR = os.path.join(PROJECT_ROOT, 'hooks')
ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')

mediapipe_datas = collect_data_files('mediapipe') if os.path.isdir(MEDIAPIPE_DIR) else []

binaries = [
    (os.path.join(PYTHON_BASE, 'python3.dll'), '.'),
    (os.path.join(PYTHON_BASE, f'python{sys.version_info.major}{sys.version_info.minor}.dll'), '.'),
    (os.path.join(SYSTEM32, 'msvcp140.dll'), '.'),
    (os.path.join(SYSTEM32, 'msvcp140_1.dll'), '.'),
    (os.path.join(SYSTEM32, 'msvcp140_2.dll'), '.'),
    (os.path.join(SYSTEM32, 'msvcp140_atomic_wait.dll'), '.'),
    (os.path.join(SYSTEM32, 'msvcp140_clr0400.dll'), '.'),
    (os.path.join(SYSTEM32, 'msvcp140_codecvt_ids.dll'), '.'),
    (os.path.join(SYSTEM32, 'vcruntime140.dll'), '.'),
    (os.path.join(SYSTEM32, 'vcruntime140_1.dll'), '.'),
    (os.path.join(SYSTEM32, 'vcruntime140_1_clr0400.dll'), '.'),
    (os.path.join(SYSTEM32, 'vcruntime140_clr0400.dll'), '.'),
    (os.path.join(SYSTEM32, 'vcruntime140_threads.dll'), '.'),
    (os.path.join(SYSTEM32, 'concrt140.dll'), '.'),
]

# 不同 Windows/Python 安装的运行库集合不同，由依赖分析补齐实际所需项。
binaries = [(path, target) for path, target in binaries if os.path.isfile(path)]

if os.path.isdir(NUMPY_LIBS):
    binaries.append((NUMPY_LIBS, 'numpy.libs'))
if os.path.isdir(SCIPY_LIBS):
    binaries.append((SCIPY_LIBS, 'scipy.libs'))

if os.path.isfile(os.path.join(POSE_LANDMARK_DIR, 'pose_landmark_cpu.binarypb')):
    mediapipe_datas.append(
        (os.path.join(POSE_LANDMARK_DIR, 'pose_landmark_cpu.binarypb'), 'mediapipe/modules/pose_landmark')
    )
if os.path.isfile(os.path.join(POSE_LANDMARK_DIR, 'pose_landmark_full.tflite')):
    mediapipe_datas.append(
        (os.path.join(POSE_LANDMARK_DIR, 'pose_landmark_full.tflite'), 'mediapipe/modules/pose_landmark')
    )

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    # 数据库和日志仅在运行时创建，发布包不携带本机用户记录。
    datas=([(ASSETS_DIR, 'assets')] if os.path.isdir(ASSETS_DIR) else []) + mediapipe_datas,
    hiddenimports=[
        'PIL._tkinter_finder',
        'matplotlib.backends.backend_tkagg',
        'scipy.interpolate',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'PIL.ImageSequence',
        'numpy._core',
        'numpy.linalg',
        'mediapipe',
        'mediapipe.python',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.pose',
        'mediapipe.tasks.python',
    ],
    hookspath=[HOOKS_DIR],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy._core.tests',
        'scipy.tests',
        'matplotlib.tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HealthySit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HealthySit',
)
