"""
PyInstaller hook: 强制包含 PIL 所有 Python 源文件
PIL hook 默认只收集 .pyd 编译模块，漏掉了 .py 纯源码（如 ImageSequence、PngImagePlugin 等）
"""
from PyInstaller.utils.hooks import collect_data_files, collect_all

# 收集 PIL 所有文件和目录（递归）
datas, binaries, hiddenimports = collect_all('PIL')
