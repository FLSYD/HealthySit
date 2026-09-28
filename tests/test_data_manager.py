"""使用临时数据库验证会话、统计与导出。"""

import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from src.data_manager import DataManager


class DataManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.manager = DataManager(self.directory / 'test.db')

    def execute(self, sql, parameters=()):
        with sqlite3.connect(self.manager.db_path) as conn:
            return conn.execute(sql, parameters).fetchall()

    def complete(self, duration=100, violation=25, started=None):
        sid = self.manager.start_session()
        if started is not None:
            self.execute('UPDATE sessions SET start_time = ? WHERE id = ?',
                         (started.isoformat(), sid))
        self.assertTrue(self.manager.end_session(
            total_duration=duration, violation_duration=violation,
            total_violations=int(violation > 0)))
        return sid

    def test_lifecycle_does_not_orphan_or_double_count_sessions(self):
        sid = self.manager.start_session('测试会话')
        self.assertEqual(self.manager.start_session(), sid)
        violation = self.manager.log_violation('head_tilt', 30, 15)
        self.assertGreater(violation, 0)
        self.assertTrue(self.manager.resolve_violation(violation))
        self.assertTrue(self.manager.end_session(total_duration=100, violation_duration=25,
                                                 total_violations=1))
        self.assertFalse(self.manager.end_session(total_duration=100))
        self.assertEqual(self.manager.log_violation('head_tilt'), -1)
        detail = self.manager.get_session_detail(sid)
        self.assertEqual(detail['notes'], '测试会话')
        self.assertEqual(detail['posture_score'], 80.0)
        self.assertEqual(detail['normal_duration'], 75)
        self.assertEqual(detail['violations'][0]['status'], 'resolved')
        self.assertEqual(self.manager.get_today_stats()['total_sessions'], 1)

    def test_explicit_zero_duration_is_not_replaced_by_wall_clock(self):
        sid = self.manager.start_session()
        self.execute('UPDATE sessions SET start_time = ? WHERE id = ?',
                     ((datetime.now() - timedelta(hours=1)).isoformat(), sid))
        self.assertTrue(self.manager.end_session(total_duration=0))
        self.assertEqual(self.manager.get_session_detail(sid)['total_duration'], 0)

    def test_omitted_duration_is_resolved_before_scoring(self):
        sid = self.manager.start_session()
        self.execute('UPDATE sessions SET start_time = ? WHERE id = ?',
                     ((datetime.now() - timedelta(seconds=100)).isoformat(), sid))
        self.manager.end_session(violation_duration=50)
        detail = self.manager.get_session_detail(sid)
        self.assertAlmostEqual(detail['posture_score'], 60.0, delta=1.0)
        self.assertEqual(detail['normal_duration'] + detail['violation_duration'],
                         detail['total_duration'])

    def test_failed_summary_update_rolls_back_session_and_allows_retry(self):
        sid = self.manager.start_session()
        with mock.patch.object(self.manager, '_update_daily_stats_on_session_end',
                               side_effect=sqlite3.OperationalError('simulated failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.manager.end_session(total_duration=10)
        self.assertEqual(self.manager.get_session_detail(sid)['status'], 'active')
        self.assertEqual(self.manager.get_current_session_id(), sid)
        self.assertTrue(self.manager.end_session(total_duration=10))

    def test_cancel_only_active_sessions_and_discard_their_violations(self):
        completed = self.complete()
        self.assertFalse(self.manager.cancel_session(completed))
        self.assertFalse(self.manager.cancel_session(9999))
        active = self.manager.start_session()
        self.manager.log_violation('head_tilt')
        self.assertTrue(self.manager.cancel_session())
        self.assertEqual(self.manager.get_session_detail(active)['violations'], [])
        self.assertEqual(self.manager.get_all_stats()['total_sessions'], 1)

    def test_delete_session_recalculates_daily_totals_and_scores(self):
        first = self.complete(100, 0)
        second = self.complete(100, 100)
        self.assertEqual(self.manager.get_today_stats()['avg_posture_score'], 60)
        self.manager.delete_session(second)
        today = self.manager.get_today_stats()
        self.assertEqual(today['total_sessions'], 1)
        self.assertEqual(today['total_sitting_time'], 100)
        self.assertEqual(today['avg_posture_score'], 100)
        self.assertEqual(today['bad_sessions'], 0)
        self.manager.delete_session(first)
        self.assertEqual(self.manager.get_today_stats()['total_sessions'], 0)

    def test_session_crossing_midnight_uses_same_day_as_history(self):
        started = datetime.now() - timedelta(days=1)
        self.complete(100, 25, started)
        self.assertEqual(self.manager.get_today_stats()['total_sessions'], 0)
        self.assertEqual(self.execute('SELECT date FROM daily_stats'),
                         [(started.date().isoformat(),)])

    def test_report_respects_range_includes_final_day_and_uses_session_weight(self):
        self.complete(100, 0, datetime(2025, 1, 1, 9))
        self.complete(100, 0, datetime(2025, 1, 1, 10))
        sid = self.complete(100, 100, datetime(2025, 1, 2, 9))
        self.execute('''INSERT INTO violation_log(session_id, timestamp, violation_type)
                        VALUES (?, ?, ?)''', (sid, '2025-01-02T23:59:59', 'head_tilt'))
        self.complete(500, 0, datetime(2025, 2, 1, 9))
        report = self.manager.generate_health_report(
            'weekly', date(2025, 1, 1), date(2025, 1, 2))
        self.assertEqual(report['start_date'], '2025-01-01')
        self.assertEqual(report['end_date'], '2025-01-02')
        self.assertEqual(report['total_sessions'], 3)
        self.assertEqual(report['avg_posture_score'], 73.3)
        self.assertEqual(report['violation_breakdown'], [{'type': 'head_tilt', 'count': 1}])
        self.assertEqual(self.manager.get_monthly_stats(2025, 1)['avg_posture_score'], 73.3)
        with self.assertRaises(ValueError):
            self.manager.generate_health_report('daily', date(2025, 1, 2), date(2025, 1, 1))

    def test_csv_and_json_exports_use_database_directory_and_serialize_report(self):
        self.complete()
        csv_path = Path(self.manager.export_to_csv(all_time=True))
        self.assertEqual(csv_path.parent, self.directory)
        with csv_path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][8], '80.0')
        report = self.manager.generate_health_report('daily')
        json_path = Path(self.manager.export_report_to_json(report))
        self.assertEqual(json_path.parent, self.directory)
        self.assertEqual(json.loads(json_path.read_text(encoding='utf-8'))['posture_level'],
                         'good')
        for kind in ('daily', 'violations'):
            self.manager.export_to_csv(str(self.directory / f'{kind}.csv'),
                                       export_type=kind, all_time=True)

    def test_old_data_cleanup_preserves_active_session_and_removes_orphan_logs(self):
        started = datetime.now() - timedelta(days=100)
        old = self.complete(100, 25, started)
        active = self.manager.start_session()
        self.manager.log_violation('head_tilt')
        self.execute('UPDATE sessions SET start_time = ? WHERE id = ?',
                     (started.isoformat(), active))
        self.execute('''INSERT INTO violation_log(session_id, timestamp, violation_type)
                        VALUES (?, ?, ?)''', (old, started.isoformat(), 'head_tilt'))
        result = self.manager.clear_old_data(90)
        self.assertEqual(result['deleted_sessions'], 1)
        self.assertEqual(result['deleted_violations'], 1)
        self.assertEqual(self.manager.get_session_detail(active)['status'], 'active')
        self.assertEqual(self.manager.get_current_session_id(), active)

    def test_clear_all_resets_active_session_and_all_aggregates(self):
        self.complete()
        self.manager.start_session()
        self.manager.log_violation('head_tilt')
        self.assertEqual(self.manager.clear_all_sessions(), 2)
        self.assertIsNone(self.manager.get_current_session_id())
        self.assertEqual(self.manager.get_all_stats()['total_sessions'], 0)
        self.assertEqual(self.manager.get_violation_summary()['total_violations'], 0)

    def test_legacy_completed_sessions_remain_visible_after_migration(self):
        legacy_path = self.directory / 'legacy.db'
        with sqlite3.connect(legacy_path) as conn:
            conn.execute('''CREATE TABLE sessions (
                id INTEGER PRIMARY KEY, start_time TEXT NOT NULL, end_time TEXT,
                total_duration INTEGER DEFAULT 0, total_violations INTEGER DEFAULT 0,
                notes TEXT
            )''')
            conn.execute('''INSERT INTO sessions(id, start_time, end_time, total_duration)
                            VALUES (1, '2025-01-01T09:00:00', '2025-01-01T09:01:00', 60)''')
        migrated = DataManager(legacy_path)
        history = migrated.get_session_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['status'], 'completed')
        self.assertEqual(history[0]['total_duration'], 60)

    def test_negative_retention_is_rejected_without_deleting_sessions(self):
        sid = self.complete()
        with self.assertRaises(ValueError):
            self.manager.clear_old_data(-1)
        self.assertIsNotNone(self.manager.get_session_detail(sid))


if __name__ == '__main__':
    unittest.main()
