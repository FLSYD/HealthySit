"""运行缓存与持久数据目录的回归测试，不加载图形界面。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

from src import runtime
from src.data_manager import get_app_data_dir


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source = self.temp / '中文程序'
        self.source.mkdir()
        self.payload = {
            'HealthySit.exe': b'fake-executable',
            '_internal/library.dll': b'fake-library',
            '_internal/models/pose.task': b'fake-model',
            '_internal/data/resource.bin': b'bundled-resource',
            'assets/icon.ico': b'fake-icon',
        }
        for name, contents in self.payload.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        for name in ('data/posture.db', 'logs/healthysit.log'):
            path = self.source / name
            path.parent.mkdir()
            path.write_bytes(b'private-user-data')
        self.cache_root = self.temp / 'HealthySitRuntime'
        self.stack.enter_context(mock.patch.object(sys, 'frozen', True, create=True))
        self.stack.enter_context(mock.patch.object(
            sys, 'executable', str(self.source / 'HealthySit.exe')))
        self.stack.enter_context(mock.patch.object(
            sys, 'argv', ['HealthySit.exe', '--profile', '坐姿配置', '--debug']))
        self.stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
        self.stack.enter_context(mock.patch.object(
            runtime.tempfile, 'gettempdir', return_value=str(self.temp)))
        self.popen = self.stack.enter_context(mock.patch.object(
            runtime.subprocess, 'Popen'))

    def launch(self):
        with self.assertRaises(SystemExit) as exited:
            runtime.ensure_ascii_runtime()
        self.assertEqual(exited.exception.code, 0)
        return Path(self.popen.call_args.kwargs['cwd'])

    def assert_complete(self, target):
        self.assertTrue((target / '.ready').is_file())
        self.assertTrue((target / '.ready').read_text(encoding='ascii'))
        for name, contents in self.payload.items():
            self.assertEqual((target / name).read_bytes(), contents)
        self.assertFalse((target / 'data').exists())
        self.assertFalse((target / 'logs').exists())

    def test_development_does_not_migrate(self):
        with mock.patch.object(sys, 'frozen', False):
            runtime.ensure_ascii_runtime()
        self.popen.assert_not_called()
        self.assertFalse(self.cache_root.exists())

    def test_ascii_executable_path_does_not_migrate(self):
        with mock.patch.object(sys, 'executable', str(self.temp / 'HealthySit.exe')):
            runtime.ensure_ascii_runtime()
        self.popen.assert_not_called()
        self.assertFalse(self.cache_root.exists())

    def test_locked_legacy_cache_is_preserved_and_arguments_are_forwarded(self):
        legacy = self.cache_root / 'HealthySit'
        legacy.mkdir(parents=True)
        legacy_file = legacy / 'HealthySit.exe'
        legacy_file.write_bytes(b'old-running-process')
        original_stat = legacy_file.stat()
        original_rmtree = shutil.rmtree

        def protect_legacy(path, *args, **kwargs):
            if Path(path) == legacy:
                raise PermissionError('legacy executable is locked')
            return original_rmtree(path, *args, **kwargs)

        with mock.patch.object(runtime.shutil, 'rmtree', side_effect=protect_legacy):
            target = self.launch()

        self.assertEqual(target.parent, self.cache_root)
        self.assertRegex(target.name, r'^HealthySit-[0-9a-f]+-.+$')
        self.assert_complete(target)
        self.assertEqual(legacy_file.read_bytes(), b'old-running-process')
        self.assertEqual(legacy_file.stat().st_mtime_ns, original_stat.st_mtime_ns)
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], [str(target / 'HealthySit.exe'),
                                  '--profile', '坐姿配置', '--debug'])
        self.assertEqual(kwargs['env']['HEALTHYSIT_APP_BASE_DIR'], str(self.source))
        self.assertEqual(kwargs['env']['HEALTHYSIT_ASCII_RUNTIME'], '1')
        self.assertEqual(kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        with mock.patch.object(sys, 'executable', str(target / 'HealthySit.exe')):
            with mock.patch.dict(os.environ, kwargs['env']):
                self.assertEqual(runtime.get_app_base_dir(), str(self.source))
                self.assertEqual(get_app_data_dir(), str(self.source / 'data'))

    def test_complete_cache_is_reused_without_copying(self):
        original = self.launch()
        with mock.patch.object(runtime.shutil, 'copytree') as copytree:
            reused = self.launch()
        self.assertEqual(reused, original)
        copytree.assert_not_called()
        self.assert_complete(reused)

    def test_user_data_changes_do_not_create_a_new_version(self):
        original = self.launch()
        (self.source / 'data' / 'posture.db').write_bytes(b'new-sitting-session')
        (self.source / 'logs' / 'healthysit.log').write_bytes(b'new-log-entry')
        with mock.patch.object(runtime.shutil, 'copytree') as copytree:
            reused = self.launch()
        self.assertEqual(reused, original)
        copytree.assert_not_called()

    def test_concurrent_initializers_launch_only_complete_independent_caches(self):
        barrier = threading.Barrier(2)
        original_copytree = shutil.copytree
        launched = []
        lock = threading.Lock()

        def concurrent_copy(source, target, *args, **kwargs):
            if Path(source) == self.source:
                barrier.wait(timeout=10)
            return original_copytree(source, target, *args, **kwargs)

        def verify_launch(command, *, cwd, env):
            target = Path(cwd)
            self.assert_complete(target)
            self.assertEqual(Path(command[0]), target / 'HealthySit.exe')
            with lock:
                launched.append(target)
            return mock.Mock()

        def initialize():
            try:
                runtime.ensure_ascii_runtime()
            except SystemExit as exited:
                return exited.code
            self.fail('中文目录中的打包程序没有重启')

        self.popen.side_effect = verify_launch
        with mock.patch.object(runtime.shutil, 'copytree', side_effect=concurrent_copy):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(initialize) for _ in range(2)]
                self.assertEqual([future.result(timeout=20) for future in futures], [0, 0])
        self.assertEqual(len(launched), 2)
        self.assertEqual(len(set(launched)), 2)
        for target in launched:
            self.assert_complete(target)

    def test_source_mtime_change_creates_new_version(self):
        original = self.launch()
        executable = self.source / 'HealthySit.exe'
        before = executable.stat()
        os.utime(executable, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
        updated = self.launch()
        self.assertNotEqual(updated, original)
        self.assert_complete(original)
        self.assert_complete(updated)

    def test_source_size_change_creates_new_version(self):
        original = self.launch()
        executable = self.source / 'HealthySit.exe'
        before = executable.stat()
        executable.write_bytes(b'new-larger-executable-version')
        os.utime(executable, ns=(before.st_atime_ns, before.st_mtime_ns))
        updated = self.launch()
        self.assertNotEqual(updated, original)
        self.assertEqual((original / 'HealthySit.exe').read_bytes(), b'fake-executable')
        self.assertEqual((updated / 'HealthySit.exe').read_bytes(), executable.read_bytes())

    def test_source_relative_path_change_creates_new_version(self):
        original = self.launch()
        model = self.source / '_internal' / 'models' / 'pose.task'
        renamed = model.with_name('pose-v2.task')
        model.rename(renamed)
        updated = self.launch()
        self.assertNotEqual(updated, original)
        self.assertTrue((original / '_internal' / 'models' / 'pose.task').is_file())
        self.assertTrue((updated / '_internal' / 'models' / 'pose-v2.task').is_file())

    def test_different_source_directory_has_a_separate_version(self):
        original = self.launch()
        second_source = self.temp / '另一份程序'
        shutil.copytree(self.source, second_source)
        with mock.patch.object(sys, 'executable', str(second_source / 'HealthySit.exe')):
            updated = self.launch()
        self.assertNotEqual(updated, original)
        self.assertEqual(self.popen.call_args.kwargs['env']['HEALTHYSIT_APP_BASE_DIR'],
                         str(second_source))
        self.assert_complete(original)
        self.assert_complete(updated)

    def test_copy_failure_cleans_only_its_own_unpublished_cache(self):
        legacy = self.cache_root / 'HealthySit'
        legacy.mkdir(parents=True)
        (legacy / 'HealthySit.exe').write_bytes(b'locked-legacy')
        incomplete = self.cache_root / 'HealthySit-previous-partial'
        incomplete.mkdir()
        (incomplete / 'partial.dll').write_bytes(b'other-initializer')

        def fail_copy(source, target, *args, **kwargs):
            (Path(target) / 'partial.dll').write_bytes(b'partial-copy')
            raise PermissionError('simulated copy failure')

        with mock.patch.object(runtime.shutil, 'copytree', side_effect=fail_copy):
            with self.assertRaisesRegex(PermissionError, 'simulated copy failure'):
                runtime.ensure_ascii_runtime()
        self.popen.assert_not_called()
        self.assertEqual(set(self.cache_root.iterdir()), {legacy, incomplete})
        self.assertEqual((legacy / 'HealthySit.exe').read_bytes(), b'locked-legacy')
        self.assertEqual((incomplete / 'partial.dll').read_bytes(), b'other-initializer')

    def test_incomplete_or_invalid_cache_is_never_launched(self):
        for damage in ('missing-marker', 'invalid-marker', 'missing-file', 'wrong-size'):
            with self.subTest(damage=damage):
                original = self.launch()
                marker = original / '.ready'
                library = original / '_internal' / 'library.dll'
                if damage == 'missing-marker':
                    marker.unlink()
                elif damage == 'invalid-marker':
                    marker.write_text('invalid-version', encoding='ascii')
                elif damage == 'missing-file':
                    library.unlink()
                else:
                    library.write_bytes(b'truncated')
                self.popen.reset_mock()
                updated = self.launch()
                self.assertNotEqual(updated, original)
                self.assert_complete(updated)
                self.assertTrue(original.is_dir())
                if damage == 'missing-marker':
                    self.assertFalse(marker.exists())
                elif damage == 'invalid-marker':
                    self.assertEqual(marker.read_text(encoding='ascii'), 'invalid-version')
                elif damage == 'missing-file':
                    self.assertFalse(library.exists())
                else:
                    self.assertEqual(library.read_bytes(), b'truncated')

    def test_non_ascii_corrupted_marker_is_skipped(self):
        original = self.launch()
        (original / '.ready').write_bytes(b'\xff\xfeinvalid-marker')
        updated = self.launch()
        self.assertNotEqual(updated, original)
        self.assert_complete(updated)
        self.assertEqual((original / '.ready').read_bytes(), b'\xff\xfeinvalid-marker')

    def test_source_changed_during_copy_is_not_published(self):
        original_copytree = shutil.copytree

        def changing_copy(source, target, *args, **kwargs):
            result = original_copytree(source, target, *args, **kwargs)
            if Path(source) == self.source:
                (self.source / 'HealthySit.exe').write_bytes(b'updated-during-copy')
            return result

        with mock.patch.object(runtime.shutil, 'copytree', side_effect=changing_copy):
            with self.assertRaisesRegex(RuntimeError, '启动期间发生变化'):
                runtime.ensure_ascii_runtime()
        self.popen.assert_not_called()
        self.assertEqual(list(self.cache_root.iterdir()), [])

    def test_packaged_data_directory_defaults_to_executable_directory(self):
        self.assertEqual(runtime.get_app_base_dir(), str(self.source))
        self.assertEqual(get_app_data_dir(), str(self.source / 'data'))

    def test_development_data_directory_ignores_packaged_environment(self):
        expected = Path(runtime.__file__).resolve().parent.parent
        with mock.patch.object(sys, 'frozen', False):
            with mock.patch.dict(os.environ, {'HEALTHYSIT_APP_BASE_DIR': str(self.source)}):
                self.assertEqual(runtime.get_app_base_dir(), str(expected))
                self.assertEqual(get_app_data_dir(), str(expected / 'data'))


if __name__ == '__main__':
    unittest.main()
