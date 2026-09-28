"""打包程序的运行缓存与持久数据路径。"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def is_ascii_path(path: str) -> bool:
    """判断路径是否只包含 ASCII 字符。"""
    return path.isascii()


def get_app_base_dir() -> str:
    """数据始终保存在原程序旁，不随运行缓存切换。"""
    if getattr(sys, 'frozen', False):
        return os.path.abspath(os.environ.get('HEALTHYSIT_APP_BASE_DIR')
                               or os.path.dirname(sys.executable))
    return str(Path(__file__).resolve().parent.parent)


def _runtime_files(source: Path):
    """记录程序版本；排除会持续变化的用户数据与日志。"""
    files = []
    for root, dirs, names in os.walk(source):
        if Path(root) == source:
            dirs[:] = [name for name in dirs if name not in ('data', 'logs')]
        for name in sorted(names):
            path = Path(root) / name
            stat = path.stat()
            files.append((path.relative_to(source).as_posix(), stat.st_size,
                          stat.st_mtime_ns))
    return sorted(files)


def _cache_complete(path: Path, fingerprint: str, files) -> bool:
    """只有复制结束且文件齐全的缓存才能启动。"""
    try:
        if (path / '.ready').read_text(encoding='ascii') != fingerprint:
            return False
        return all((path / name).is_file() and (path / name).stat().st_size == size
                   for name, size, _ in files)
    except (OSError, UnicodeError):
        return False


def ensure_ascii_runtime() -> None:
    """中文路径下从独立的完整缓存启动，绝不删除正在运行的版本。"""
    if not getattr(sys, 'frozen', False):
        return

    exe_path = Path(os.path.abspath(sys.executable))
    source = exe_path.parent
    if is_ascii_path(str(source)):
        return

    cache_root = Path(tempfile.gettempdir()) / 'HealthySitRuntime'
    if not is_ascii_path(str(cache_root)):
        raise RuntimeError('临时目录包含非英文字符，请将程序放到纯英文路径后重试。')
    cache_root.mkdir(parents=True, exist_ok=True)

    files = _runtime_files(source)
    version = json.dumps([str(source), files], ensure_ascii=True).encode('ascii')
    fingerprint = hashlib.sha256(version).hexdigest()[:24]
    prefix = f'HealthySit-{fingerprint}-'
    target = next((path for path in sorted(cache_root.glob(prefix + '*'))
                   if _cache_complete(path, fingerprint, files)), None)

    if target is None:
        # 每次复制使用自己的目录；并发启动也不会互相覆盖或清理。
        target = Path(tempfile.mkdtemp(prefix=prefix, dir=str(cache_root)))
        try:
            def ignore_data(directory, names):
                return [name for name in ('data', 'logs') if name in names] \
                    if Path(directory) == source else []

            shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore_data)
            if files != _runtime_files(source):
                raise RuntimeError('程序文件在启动期间发生变化，请等待更新完成后重试。')
            # 最后写入标记。其他启动器不会使用复制到一半的目录。
            (target / '.ready').write_text(fingerprint, encoding='ascii')
            if not _cache_complete(target, fingerprint, files):
                raise RuntimeError('运行文件复制不完整，请重试。')
        except BaseException:
            # 只回收本次创建、尚未启动的目录，保留所有已有缓存。
            shutil.rmtree(target, ignore_errors=True)
            raise

    env = os.environ.copy()
    env['HEALTHYSIT_APP_BASE_DIR'] = str(source)
    env['HEALTHYSIT_ASCII_RUNTIME'] = '1'
    # 新进程应从自己的 _internal 加载资源，不能继承原启动器的解包位置。
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    subprocess.Popen([str(target / exe_path.name), *sys.argv[1:]],
                     cwd=str(target), env=env)
    sys.exit(0)
