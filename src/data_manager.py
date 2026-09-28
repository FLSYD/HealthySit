"""
数据管理模块
负责坐姿数据的存储、查询、导出和健康报告生成
"""

import sqlite3
import csv
import os
import json
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
import threading
from contextlib import closing

from src.runtime import get_app_base_dir

logger = logging.getLogger(__name__)


def get_app_data_dir() -> str:
    """获取应用数据目录。打包后使用 exe 同级目录，便于 U 盘或任意目录运行。"""
    return os.path.join(get_app_base_dir(), 'data')


class PostureLevel(Enum):
    """坐姿等级枚举"""
    EXCELLENT = "excellent"      # 优秀：90-100分
    GOOD = "good"                # 良好：75-89分
    FAIR = "fair"                # 一般：60-74分
    POOR = "poor"                # 较差：40-59分
    BAD = "bad"                  # 差：0-39分

    @classmethod
    def from_score(cls, score: float) -> "PostureLevel":
        if score >= 90:
            return cls.EXCELLENT
        elif score >= 75:
            return cls.GOOD
        elif score >= 60:
            return cls.FAIR
        elif score >= 40:
            return cls.POOR
        return cls.BAD

    @property
    def label_cn(self) -> str:
        labels = {
            "excellent": "优秀",
            "good": "良好",
            "fair": "一般",
            "poor": "较差",
            "bad": "差"
        }
        return labels.get(self.value, "未知")

    @property
    def label_en(self) -> str:
        labels = {
            "excellent": "Excellent",
            "good": "Good",
            "fair": "Fair",
            "poor": "Poor",
            "bad": "Bad"
        }
        return labels.get(self.value, "Unknown")


class DataManager:
    """坐姿数据管理器

    完整的会话生命周期管理：
      start_session → end_session
      + 自动计算坐姿评分
      + 每日/每周健康报告
      + CSV / JSON 导出

    数据库设计：
      sessions         - 监测会话表（每次开始→结束为一个会话）
      daily_stats      - 每日健康统计表（由会话结束时自动汇总更新）
      violation_log    - 违规事件详细记录（记录每次违规的时间和类型）
      health_reports   - 健康报告表（周报/月报快照）
      settings_log     - 设置变更日志（记录参数调整历史）
    """

    # ---- 数据库版本控制 ----
    SCHEMA_VERSION = 3

    def __init__(self, db_path: str = None):
        """
        初始化数据管理器

        Args:
            db_path: 数据库文件路径，默认为 data/posture.db
        """
        if db_path is None:
            db_path = os.path.join(get_app_data_dir(), 'posture.db')

        db_path = os.path.abspath(os.fspath(db_path))
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self._write_lock = threading.Lock()
        self._ending_session = False

        self._init_database()
        self._current_session_id: Optional[int] = None
        self._session_start: Optional[datetime] = None

        logger.info(f"数据管理器初始化完成，数据库路径: {db_path}")

    # ============================================================
    #  数据库初始化
    # ============================================================

    def _init_database(self):
        """初始化/升级数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ---- 会话记录表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                total_duration INTEGER DEFAULT 0,
                total_violations INTEGER DEFAULT 0,
                normal_duration INTEGER DEFAULT 0,
                violation_duration INTEGER DEFAULT 0,
                posture_score REAL DEFAULT 100.0,
                posture_level TEXT,
                avg_neck_angle REAL,
                avg_torso_angle REAL,
                avg_head_forward_angle REAL,
                avg_shoulder_diff REAL,
                sitting_view TEXT DEFAULT 'front',
                status TEXT DEFAULT 'active',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ---- 每日统计表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                total_sitting_time INTEGER DEFAULT 0,
                total_violations INTEGER DEFAULT 0,
                total_sessions INTEGER DEFAULT 0,
                avg_posture_score REAL DEFAULT 100.0,
                posture_level TEXT,
                normal_time INTEGER DEFAULT 0,
                violation_time INTEGER DEFAULT 0,
                excellent_sessions INTEGER DEFAULT 0,
                good_sessions INTEGER DEFAULT 0,
                fair_sessions INTEGER DEFAULT 0,
                poor_sessions INTEGER DEFAULT 0,
                bad_sessions INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ---- 违规事件详细记录表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS violation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                violation_type TEXT NOT NULL,
                violation_value REAL,
                threshold_value REAL,
                duration_seconds INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                resolved_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ---- 健康报告表（周报/月报快照）----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                report_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_sitting_time INTEGER DEFAULT 0,
                total_violations INTEGER DEFAULT 0,
                total_sessions INTEGER DEFAULT 0,
                avg_posture_score REAL DEFAULT 100.0,
                posture_level TEXT,
                normal_time INTEGER DEFAULT 0,
                violation_time INTEGER DEFAULT 0,
                daily_breakdown TEXT,
                violation_breakdown TEXT,
                recommendations TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ---- 设置变更日志表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ---- 元数据表（存储版本信息等）----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 设置当前数据库版本
        cursor.execute(
            'INSERT OR REPLACE INTO meta (key, value, updated_at) VALUES (?, ?, ?)',
            ('schema_version', str(self.SCHEMA_VERSION), datetime.now().isoformat())
        )

        conn.commit()

        # ---- 数据库迁移（处理已有数据库缺少新列的情况）----
        self._migrate_database(conn)

        conn.close()
        logger.info("数据库表初始化完成")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接，启用 WAL 模式并设置超时以支持并发访问"""
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=20000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _migrate_database(self, conn: sqlite3.Connection):
        """数据库迁移：为旧数据库补充缺失的列"""
        cursor = conn.cursor()

        def _add_missing_columns(table: str, columns: list):
            """安全添加缺失列，失败时记录警告"""
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                existing = {row[1] for row in cursor.fetchall()}
            except Exception:
                existing = set()
            for col, col_type in columns:
                if col in existing:
                    continue
                try:
                    cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
                    logger.info(f"迁移 {table} 表：新增列 {col}")
                except sqlite3.OperationalError as e:
                    logger.warning(f"迁移 {table} 表列 {col} 失败: {e}")
            return existing

        # sessions 表缺失列
        sessions_new_columns = [
            ('normal_duration', 'INTEGER DEFAULT 0'),
            ('violation_duration', 'INTEGER DEFAULT 0'),
            ('posture_score', 'REAL DEFAULT 100.0'),
            ('posture_level', 'TEXT'),
            ('avg_neck_angle', 'REAL'),
            ('avg_torso_angle', 'REAL'),
            ('avg_head_forward_angle', 'REAL'),
            ('avg_shoulder_diff', 'REAL'),
            ('sitting_view', 'TEXT DEFAULT "front"'),
            ('status', 'TEXT DEFAULT "active"'),
        ]
        original_session_columns = _add_missing_columns('sessions', sessions_new_columns)
        if 'status' not in original_session_columns:
            cursor.execute("UPDATE sessions SET status = 'completed' WHERE end_time IS NOT NULL")

        # daily_stats 表缺失列
        daily_new_columns = [
            ('total_sessions', 'INTEGER DEFAULT 0'),
            ('normal_time', 'INTEGER DEFAULT 0'),
            ('violation_time', 'INTEGER DEFAULT 0'),
            ('excellent_sessions', 'INTEGER DEFAULT 0'),
            ('good_sessions', 'INTEGER DEFAULT 0'),
            ('fair_sessions', 'INTEGER DEFAULT 0'),
            ('poor_sessions', 'INTEGER DEFAULT 0'),
            ('bad_sessions', 'INTEGER DEFAULT 0'),
            ('posture_level', 'TEXT'),
        ]
        _add_missing_columns('daily_stats', daily_new_columns)

        conn.commit()
        logger.info("数据库迁移完成")

    # ============================================================
    #  会话管理（完整的生命周期）
    # ============================================================

    def start_session(self, notes: str = None) -> int:
        """开始新会话，返回会话ID（线程安全）"""
        acquired = self._write_lock.acquire(timeout=5.0)
        if not acquired:
            raise RuntimeError("无法获取数据库写入锁，请稍后重试")
        conn = None
        try:
            if self._current_session_id is not None:
                return self._current_session_id
            conn = self._get_connection()
            cursor = conn.cursor()

            start_time = datetime.now().isoformat()
            cursor.execute(
                'INSERT INTO sessions (start_time, status, notes) VALUES (?, ?, ?)',
                (start_time, 'active', notes)
            )
            session_id = cursor.lastrowid

            conn.commit()
            conn.close()

            self._current_session_id = session_id
            self._session_start = datetime.now()
            logger.info(f"开始新会话，会话ID: {session_id}")
            return session_id
        finally:
            if conn is not None:
                conn.close()
            self._write_lock.release()

    def end_session(self,
                   posture_status: str = "normal",
                   total_duration: Optional[int] = None,
                   total_violations: int = 0,
                   normal_duration: int = 0,
                   violation_duration: int = 0,
                   avg_neck_angle: float = None,
                   avg_torso_angle: float = None,
                   avg_head_forward_angle: float = None,
                   avg_shoulder_diff: float = None,
                   sitting_view: str = "front",
                   notes: str = None) -> bool:
        """结束当前会话，写入会话统计数据（线程安全）"""
        acquired = self._write_lock.acquire(timeout=5.0)
        if not acquired:
            logger.warning("结束会话失败：数据库被占用")
            return False

        conn = None
        try:
            self._ending_session = True

            if self._current_session_id is None:
                logger.warning("没有活动的会话，无法结束")
                return False

            session_id = self._current_session_id
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT start_time FROM sessions WHERE id = ? AND status = ?',
                (session_id, 'active')
            )
            result = cursor.fetchone()
            if result is None:
                conn.close()
                logger.warning(f"会话 {session_id} 不存在或已结束")
                return False

            start_time = datetime.fromisoformat(result[0])
            end_time = datetime.now()

            if total_duration is None:
                total_duration = int((end_time - start_time).total_seconds())
            total_duration = max(0, int(total_duration))
            violation_duration = min(total_duration, max(0, int(violation_duration)))
            normal_duration = total_duration - violation_duration
            total_violations = max(0, int(total_violations))

            if total_duration > 0:
                violation_rate = violation_duration / total_duration
                posture_score = max(0.0, 100.0 - violation_rate * 80.0)
            else:
                posture_score = 100.0
            posture_score = round(posture_score, 1)
            posture_level = PostureLevel.from_score(posture_score)

            cursor.execute('''
                UPDATE sessions
                SET end_time = ?,
                    total_duration = ?,
                    total_violations = ?,
                    normal_duration = ?,
                    violation_duration = ?,
                    posture_score = ?,
                    posture_level = ?,
                    avg_neck_angle = ?,
                    avg_torso_angle = ?,
                    avg_head_forward_angle = ?,
                    avg_shoulder_diff = ?,
                    sitting_view = ?,
                    status = ?,
                    notes = COALESCE(?, notes)
                WHERE id = ?
            ''', (
                end_time.isoformat(),
                total_duration,
                total_violations,
                normal_duration,
                violation_duration,
                posture_score,
                posture_level.value,
                avg_neck_angle,
                avg_torso_angle,
                avg_head_forward_angle,
                avg_shoulder_diff,
                sitting_view,
                'completed',
                notes,
                session_id
            ))

            self._update_daily_stats_on_session_end(
                total_duration, total_violations,
                normal_duration, violation_duration,
                posture_score, posture_level.value, sitting_view,
                conn=conn, stats_date=start_time.date().isoformat()
            )

            conn.commit()
            conn.close()

            logger.info(
                f"会话 {session_id} 已结束，总时长: {total_duration}秒，"
                f"违规: {total_violations}次，评分: {posture_score:.1f}分 ({posture_level.label_cn})"
            )

            self._current_session_id = None
            self._session_start = None
            return True
        finally:
            if conn is not None:
                conn.close()
            self._ending_session = False
            self._write_lock.release()

    def get_current_session_id(self) -> Optional[int]:
        """获取当前活动会话ID"""
        return self._current_session_id

    def cancel_session(self, session_id: int = None) -> bool:
        """取消会话（不计入统计）"""
        with self._write_lock:
            sid = session_id if session_id is not None else self._current_session_id
            if sid is None:
                return False
            with closing(self._get_connection()) as conn, conn:
                cursor = conn.execute(
                    'UPDATE sessions SET status = ? WHERE id = ? AND status = ?',
                    ('cancelled', sid, 'active')
                )
                cancelled = cursor.rowcount > 0
                if cancelled:
                    conn.execute('DELETE FROM violation_log WHERE session_id = ?', (sid,))
            if cancelled and sid == self._current_session_id:
                self._current_session_id = None
                self._session_start = None
            return cancelled

    # ============================================================
    #  违规事件日志
    # ============================================================

    def log_violation(self,
                     violation_type: str,
                     violation_value: float = None,
                     threshold_value: float = None,
                     duration_seconds: int = 0) -> int:
        """记录一次违规事件（线程安全）"""
        if self._current_session_id is None or self._ending_session:
            return -1

        acquired = self._write_lock.acquire(timeout=0.5)
        if not acquired:
            return -1
        conn = None
        try:
            if self._current_session_id is None or self._ending_session:
                return -1
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO violation_log
                (session_id, timestamp, violation_type, violation_value,
                 threshold_value, duration_seconds, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                self._current_session_id,
                datetime.now().isoformat(),
                violation_type,
                violation_value,
                threshold_value,
                duration_seconds,
                'active'
            ))

            vid = cursor.lastrowid
            conn.commit()
            conn.close()
            return vid
        finally:
            if conn is not None:
                conn.close()
            self._write_lock.release()

    def resolve_violation(self, violation_id: int) -> bool:
        """标记违规事件为已解决（线程安全）"""
        acquired = self._write_lock.acquire(timeout=2.0)
        if not acquired:
            return False
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE violation_log
                SET status = ?, resolved_at = ?
                WHERE id = ?
            ''', ('resolved', datetime.now().isoformat(), violation_id))

            affected = cursor.rowcount
            conn.commit()
            conn.close()
            return affected > 0
        finally:
            if conn is not None:
                conn.close()
            self._write_lock.release()

    # ============================================================
    #  查询接口
    # ============================================================

    def get_session_history(self, limit: int = 50) -> List[Dict]:
        """获取会话历史"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, start_time, end_time, total_duration,
                   total_violations, normal_duration, violation_duration,
                   posture_score, posture_level, avg_neck_angle,
                   avg_torso_angle, avg_head_forward_angle, avg_shoulder_diff,
                   sitting_view, status, notes
            FROM sessions
            WHERE status = 'completed'
            ORDER BY start_time DESC
            LIMIT ?
        ''', (limit,))

        sessions = self._rows_to_dict(cursor.fetchall(), [
            'id', 'start_time', 'end_time', 'total_duration',
            'total_violations', 'normal_duration', 'violation_duration',
            'posture_score', 'posture_level', 'avg_neck_angle',
            'avg_torso_angle', 'avg_head_forward_angle', 'avg_shoulder_diff',
            'sitting_view', 'status', 'notes'
        ])
        conn.close()
        return sessions

    def get_session_detail(self, session_id: int) -> Optional[Dict]:
        """获取单个会话的详细信息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, start_time, end_time, total_duration,
                   total_violations, normal_duration, violation_duration,
                   posture_score, posture_level, avg_neck_angle,
                   avg_torso_angle, avg_head_forward_angle, avg_shoulder_diff,
                   sitting_view, status, notes
            FROM sessions WHERE id = ?
        ''', (session_id,))

        row = cursor.fetchone()
        if row is None:
            conn.close()
            return None

        session = dict(zip([
            'id', 'start_time', 'end_time', 'total_duration',
            'total_violations', 'normal_duration', 'violation_duration',
            'posture_score', 'posture_level', 'avg_neck_angle',
            'avg_torso_angle', 'avg_head_forward_angle', 'avg_shoulder_diff',
            'sitting_view', 'status', 'notes'
        ], row))

        # 附加违规日志
        cursor.execute('''
            SELECT id, timestamp, violation_type, violation_value,
                   threshold_value, duration_seconds, status, resolved_at
            FROM violation_log WHERE session_id = ? ORDER BY timestamp ASC
        ''', (session_id,))
        session['violations'] = self._rows_to_dict(cursor.fetchall(), [
            'id', 'timestamp', 'violation_type', 'violation_value',
            'threshold_value', 'duration_seconds', 'status', 'resolved_at'
        ])

        conn.close()
        return session

    def get_violation_summary(self,
                               session_id: int = None,
                               start_date: datetime = None,
                               end_date: datetime = None) -> Dict:
        """获取违规汇总统计"""
        conn = self._get_connection()
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if session_id is not None:
            where_clauses.append("session_id = ?")
            params.append(session_id)
        if start_date:
            where_clauses.append("timestamp >= ?")
            params.append(start_date.isoformat())
        if end_date:
            where_clauses.append("timestamp <= ?")
            params.append(end_date.isoformat())

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        cursor.execute(f'''
            SELECT
                violation_type,
                COUNT(*) as count,
                AVG(violation_value) as avg_value,
                SUM(duration_seconds) as total_duration
            FROM violation_log
            WHERE {where_sql}
            GROUP BY violation_type
            ORDER BY count DESC
        ''', params)

        rows = cursor.fetchall()
        total_count = sum(r[1] for r in rows)
        total_duration = sum(r[3] or 0 for r in rows)

        conn.close()

        return {
            'total_violations': total_count,
            'total_duration': total_duration,
            'by_type': [
                {
                    'type': r[0],
                    'count': r[1],
                    'avg_value': round(r[2], 2) if r[2] is not None else None,
                    'total_duration': r[3] or 0,
                    'percentage': round(r[1] / total_count * 100, 1) if total_count > 0 else 0
                }
                for r in rows
            ]
        }

    # ============================================================
    #  统计分析
    # ============================================================

    def _update_daily_stats_on_session_end(self,
                                           total_duration: int,
                                           total_violations: int,
                                           normal_duration: int,
                                           violation_duration: int,
                                           posture_score: float,
                                           posture_level: str,
                                           sitting_view: str,
                                           conn: sqlite3.Connection = None,
                                           stats_date: str = None):
        """会话结束时更新每日统计（可使用外部传入的连接，在锁内共用）"""
        own_conn = False
        if conn is None:
            conn = self._get_connection()
            own_conn = True
        cursor = conn.cursor()

        try:
            today = stats_date or date.today().isoformat()

            cursor.execute(
                'SELECT id, total_sitting_time, total_violations, total_sessions, '
                'normal_time, violation_time, avg_posture_score, posture_level, '
                'excellent_sessions, good_sessions, fair_sessions, poor_sessions, bad_sessions '
                'FROM daily_stats WHERE date = ?',
                (today,)
            )
            result = cursor.fetchone()

            if result:
                existing = {
                    'total_sitting_time': result[1],
                    'total_violations': result[2],
                    'total_sessions': result[3],
                    'normal_time': result[4],
                    'violation_time': result[5],
                    'avg_posture_score': result[6],
                    'posture_level': result[7],
                    'excellent': result[8],
                    'good': result[9],
                    'fair': result[10],
                    'poor': result[11],
                    'bad': result[12],
                }

                new_total_time = existing['total_sitting_time'] + total_duration
                new_total_viol = existing['total_violations'] + total_violations
                new_sessions = existing['total_sessions'] + 1
                new_normal_time = existing['normal_time'] + normal_duration
                new_violation_time = existing['violation_time'] + violation_duration

                new_avg_score = (
                    (existing['avg_posture_score'] * existing['total_sessions'] + posture_score)
                    / new_sessions
                )

                new_level = PostureLevel.from_score(new_avg_score)

                level_counts = {
                    'excellent': existing['excellent'],
                    'good': existing['good'],
                    'fair': existing['fair'],
                    'poor': existing['poor'],
                    'bad': existing['bad'],
                }
                level_counts[posture_level] = level_counts.get(posture_level, 0) + 1

                cursor.execute('''
                    UPDATE daily_stats
                    SET total_sitting_time = ?,
                        total_violations = ?,
                        total_sessions = ?,
                        normal_time = ?,
                        violation_time = ?,
                        avg_posture_score = ?,
                        posture_level = ?,
                        excellent_sessions = ?,
                        good_sessions = ?,
                        fair_sessions = ?,
                        poor_sessions = ?,
                        bad_sessions = ?
                    WHERE date = ?
                ''', (
                    new_total_time, new_total_viol, new_sessions,
                    new_normal_time, new_violation_time,
                    new_avg_score, new_level.value,
                    level_counts['excellent'], level_counts['good'],
                    level_counts['fair'], level_counts['poor'], level_counts['bad'],
                    today
                ))
            else:
                new_level = PostureLevel.from_score(posture_score)
                level_counts = {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0, 'bad': 0}
                level_counts[posture_level] = 1

                cursor.execute('''
                    INSERT INTO daily_stats
                    (date, total_sitting_time, total_violations, total_sessions,
                     normal_time, violation_time, avg_posture_score, posture_level,
                     excellent_sessions, good_sessions, fair_sessions, poor_sessions, bad_sessions)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    today, total_duration, total_violations, 1,
                    normal_duration, violation_duration,
                    posture_score, new_level.value,
                    level_counts['excellent'], level_counts['good'],
                    level_counts['fair'], level_counts['poor'], level_counts['bad']
                ))
            if own_conn:
                conn.commit()
        finally:
            if own_conn:
                conn.close()

    def get_today_stats(self) -> Dict:
        """获取今日统计"""
        conn = self._get_connection()
        cursor = conn.cursor()

        today = date.today().isoformat()
        cursor.execute('''
            SELECT total_sitting_time, total_violations, total_sessions,
                   avg_posture_score, posture_level, normal_time, violation_time,
                   excellent_sessions, good_sessions, fair_sessions, poor_sessions, bad_sessions
            FROM daily_stats WHERE date = ?
        ''', (today,))

        result = cursor.fetchone()

        if result:
            stats = {
                'date': today,
                'total_sitting_time': result[0],
                'total_violations': result[1],
                'total_sessions': result[2],
                'avg_posture_score': result[3],
                'posture_level': result[4],
                'normal_time': result[5],
                'violation_time': result[6],
                'excellent_sessions': result[7],
                'good_sessions': result[8],
                'fair_sessions': result[9],
                'poor_sessions': result[10],
                'bad_sessions': result[11],
            }
        else:
            stats = {
                'date': today,
                'total_sitting_time': 0,
                'total_violations': 0,
                'total_sessions': 0,
                'avg_posture_score': 100.0,
                'posture_level': 'excellent',
                'normal_time': 0,
                'violation_time': 0,
                'excellent_sessions': 0,
                'good_sessions': 0,
                'fair_sessions': 0,
                'poor_sessions': 0,
                'bad_sessions': 0,
            }

        # 同时查询今日会话列表
        cursor.execute('''
            SELECT id, start_time, end_time, total_duration, total_violations,
                   posture_score, posture_level, status
            FROM sessions
            WHERE date(start_time) = ? AND status = 'completed'
            ORDER BY start_time DESC
        ''', (today,))
        stats['today_sessions'] = self._rows_to_dict(cursor.fetchall(), [
            'id', 'start_time', 'end_time', 'total_duration', 'total_violations',
            'posture_score', 'posture_level', 'status'
        ])

        conn.close()
        return stats

    def get_all_stats(self) -> Dict:
        """获取所有会话的汇总统计（跨所有时间）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total_sessions,
                COALESCE(SUM(total_duration), 0) as total_time,
                COALESCE(SUM(total_violations), 0) as total_violations,
                COALESCE(AVG(posture_score), 100.0) as avg_score
            FROM sessions
            WHERE status = 'completed'
        ''')

        row = cursor.fetchone()
        conn.close()

        return {
            'total_sessions': row[0] if row else 0,
            'total_time': row[1] if row else 0,
            'total_violations': row[2] if row else 0,
            'avg_score': row[3] if row and row[3] is not None else 100.0,
        }

    def get_recent_trend(self, count: int = 10) -> List[Dict]:
        """获取最近 N 条已完成会话的坐姿趋势"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, start_time, total_duration, total_violations,
                   posture_score, posture_level
            FROM sessions
            WHERE status = 'completed'
            ORDER BY start_time DESC
            LIMIT ?
        ''', (count,))

        rows = cursor.fetchall()
        conn.close()

        # 按时间正序返回（最早在前）
        rows.reverse()
        return self._rows_to_dict(rows, [
            'id', 'start_time', 'total_duration', 'total_violations',
            'posture_score', 'posture_level'
        ])

    def get_weekly_stats(self) -> List[Dict]:
        """获取本周统计（每天一条）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        cursor.execute('''
            SELECT date, total_sitting_time, total_violations, total_sessions,
                   avg_posture_score, posture_level, normal_time, violation_time,
                   excellent_sessions, good_sessions, fair_sessions, poor_sessions, bad_sessions
            FROM daily_stats
            WHERE date >= ?
            ORDER BY date ASC
        ''', (week_start.isoformat(),))

        rows = cursor.fetchall()
        conn.close()

        stats = []
        current = week_start
        while current <= today:
            found = next((r for r in rows if r[0] == current.isoformat()), None)
            if found:
                stats.append({
                    'date': found[0],
                    'total_sitting_time': found[1],
                    'total_violations': found[2],
                    'total_sessions': found[3],
                    'avg_posture_score': found[4],
                    'posture_level': found[5],
                    'normal_time': found[6],
                    'violation_time': found[7],
                    'excellent': found[8],
                    'good': found[9],
                    'fair': found[10],
                    'poor': found[11],
                    'bad': found[12],
                })
            else:
                stats.append({
                    'date': current.isoformat(),
                    'total_sitting_time': 0,
                    'total_violations': 0,
                    'total_sessions': 0,
                    'avg_posture_score': None,
                    'posture_level': None,
                    'normal_time': 0,
                    'violation_time': 0,
                })
            current += timedelta(days=1)

        return stats

    def get_monthly_stats(self, year: int = None, month: int = None) -> Dict:
        """获取指定月份的统计数据"""
        if year is None or month is None:
            today = date.today()
            year, month = today.year, today.month

        conn = self._get_connection()
        cursor = conn.cursor()

        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        cursor.execute('''
            SELECT
                SUM(total_sitting_time) as total_time,
                SUM(total_violations) as total_viol,
                SUM(total_sessions) as total_sess,
                SUM(avg_posture_score * total_sessions) / NULLIF(SUM(total_sessions), 0) as avg_score,
                SUM(normal_time) as normal_t,
                SUM(violation_time) as viol_t,
                SUM(excellent_sessions) as ex,
                SUM(good_sessions) as gd,
                SUM(fair_sessions) as fr,
                SUM(poor_sessions) as pr,
                SUM(bad_sessions) as bd
            FROM daily_stats
            WHERE date >= ? AND date < ?
        ''', (start_date, end_date))

        row = cursor.fetchone()
        conn.close()

        return {
            'year': year,
            'month': month,
            'start_date': start_date,
            'total_sitting_time': row[0] or 0,
            'total_violations': row[1] or 0,
            'total_sessions': row[2] or 0,
            'avg_posture_score': round(row[3], 1) if row[3] is not None else 100.0,
            'normal_time': row[4] or 0,
            'violation_time': row[5] or 0,
            'excellent_sessions': row[6] or 0,
            'good_sessions': row[7] or 0,
            'fair_sessions': row[8] or 0,
            'poor_sessions': row[9] or 0,
            'bad_sessions': row[10] or 0,
        }

    # ============================================================
    #  健康报告
    # ============================================================

    def generate_health_report(self,
                               report_type: str = "weekly",
                               start_date: date = None,
                               end_date: date = None) -> Dict:
        """
        生成健康报告

        Args:
            report_type: 报告类型 ("daily", "weekly", "monthly")
            start_date: 开始日期（周报/月报使用）
            end_date: 结束日期

        Returns:
            健康报告字典
        """
        today = date.today()

        if report_type == "daily":
            start = end = today
        elif report_type == "weekly":
            end = today
            start = end - timedelta(days=6)
        elif report_type == "monthly":
            end = today
            start = end.replace(day=1)
            if start > end:
                start = end.replace(month=start.month - 1) if start.month > 1 else start.replace(year=start.year - 1, month=12)
        else:
            start = end = today

        if start_date is not None:
            start = start_date.date() if isinstance(start_date, datetime) else start_date
        if end_date is not None:
            end = end_date.date() if isinstance(end_date, datetime) else end_date
        if start > end:
            raise ValueError('开始日期不能晚于结束日期')

        conn = self._get_connection()
        cursor = conn.cursor()

        # 汇总统计
        cursor.execute('''
            SELECT
                SUM(total_sitting_time) as total_time,
                SUM(total_violations) as total_viol,
                SUM(total_sessions) as total_sess,
                SUM(avg_posture_score * total_sessions) / NULLIF(SUM(total_sessions), 0) as avg_score,
                SUM(normal_time) as normal_t,
                SUM(violation_time) as viol_t
            FROM daily_stats
            WHERE date >= ? AND date <= ?
        ''', (start.isoformat(), end.isoformat()))
        row = cursor.fetchone()

        total_time = row[0] or 0
        total_viol = row[1] or 0
        total_sess = row[2] or 0
        avg_score = round(row[3], 1) if row[3] is not None else 100.0
        normal_time = row[4] or 0
        viol_time = row[5] or 0

        posture_level = PostureLevel.from_score(avg_score)

        # 每日明细
        cursor.execute('''
            SELECT date, total_sitting_time, total_violations,
                   total_sessions, avg_posture_score, posture_level
            FROM daily_stats
            WHERE date >= ? AND date <= ?
            ORDER BY date ASC
        ''', (start.isoformat(), end.isoformat()))
        daily_rows = cursor.fetchall()

        daily_breakdown = [
            {
                'date': r[0],
                'total_time': r[1],
                'total_violations': r[2],
                'total_sessions': r[3],
                'avg_score': round(r[4], 1) if r[4] is not None else None,
                'level': r[5],
            }
            for r in daily_rows
        ]

        # 违规类型分析
        cursor.execute('''
            SELECT violation_type, COUNT(*) as cnt
            FROM violation_log
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY violation_type
            ORDER BY cnt DESC
        ''', (start.isoformat(), (end + timedelta(days=1)).isoformat()))
        viol_rows = cursor.fetchall()

        violation_breakdown = [
            {'type': r[0], 'count': r[1]}
            for r in viol_rows
        ]

        # 生成建议
        recommendations = self._generate_recommendations(
            avg_score, total_viol, total_time, violation_breakdown
        )

        # 保存报告
        cursor.execute('''
            INSERT INTO health_reports
            (report_date, report_type, start_date, end_date,
             total_sitting_time, total_violations, total_sessions,
             avg_posture_score, posture_level, normal_time, violation_time,
             daily_breakdown, violation_breakdown, recommendations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            today.isoformat(),
            report_type,
            start.isoformat(),
            end.isoformat(),
            total_time, total_viol, total_sess,
            avg_score, posture_level.value,
            normal_time, viol_time,
            json.dumps(daily_breakdown, ensure_ascii=False),
            json.dumps(violation_breakdown, ensure_ascii=False),
            json.dumps(recommendations, ensure_ascii=False),
        ))
        report_id = cursor.lastrowid

        conn.commit()
        conn.close()

        report = {
            'id': report_id,
            'report_date': today.isoformat(),
            'report_type': report_type,
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'total_sitting_time': total_time,
            'total_violations': total_viol,
            'total_sessions': total_sess,
            'avg_posture_score': avg_score,
            'posture_level': posture_level.value,
            'normal_time': normal_time,
            'violation_time': viol_time,
            'daily_breakdown': daily_breakdown,
            'violation_breakdown': violation_breakdown,
            'recommendations': recommendations,
        }

        logger.info(f"健康报告已生成: {report_type} ({start} ~ {end}), 评分: {avg_score}分")
        return report

    def _generate_recommendations(self,
                                   avg_score: float,
                                   total_violations: int,
                                   total_time: int,
                                   violation_breakdown: List[Dict]) -> List[Dict]:
        """根据统计数据生成健康建议"""
        recommendations = []
        level = PostureLevel.from_score(avg_score)

        # 总体评分建议
        if avg_score >= 90:
            recommendations.append({
                'category': 'overall',
                'priority': 'low',
                'title': '坐姿优秀',
                'content': '您的坐姿保持得非常棒，继续保持当前的好习惯！',
                'icon': 'star'
            })
        elif avg_score >= 75:
            recommendations.append({
                'category': 'overall',
                'priority': 'info',
                'title': '坐姿良好',
                'content': '您的坐姿整体不错，偶尔有小问题，注意保持。',
                'icon': 'thumbsup'
            })
        elif avg_score >= 60:
            recommendations.append({
                'category': 'overall',
                'priority': 'medium',
                'title': '坐姿一般',
                'content': '您的坐姿需要改善，建议留意系统提示并及时调整。',
                'icon': 'warning'
            })
        else:
            recommendations.append({
                'category': 'overall',
                'priority': 'high',
                'title': '坐姿需改进',
                'content': '您的坐姿问题较多，请务必关注系统提醒，必要时请咨询专业医生。',
                'icon': 'alert'
            })

        # 久坐时间建议
        hours = total_time / 3600
        if hours >= 4:
            recommendations.append({
                'category': 'sedentary',
                'priority': 'high',
                'title': '注意休息',
                'content': f'今日累计坐姿时间约 {hours:.1f} 小时，建议每 45 分钟起身活动 3-5 分钟。',
                'icon': 'clock'
            })
        elif hours >= 2:
            recommendations.append({
                'category': 'sedentary',
                'priority': 'medium',
                'title': '适时活动',
                'content': f'已坐约 {hours:.1f} 小时，请记得中途起身活动一下。',
                'icon': 'clock'
            })

        # 违规类型建议
        if violation_breakdown:
            top_violation = violation_breakdown[0]
            vt = top_violation['type']
            if vt in ('hunchback', 'torso'):
                recommendations.append({
                    'category': 'hunchback',
                    'priority': 'medium',
                    'title': '挺直腰背',
                    'content': '弯腰驼背是最常见的违规类型，建议使用腰部支撑垫，每隔 20 分钟检查坐姿。',
                    'icon': 'back'
                })
            elif vt in ('head_forward', 'head_forward'):
                recommendations.append({
                    'category': 'head_forward',
                    'priority': 'medium',
                    'title': '头部位置',
                    'content': '头部前倾较多，建议将显示器顶部与眼睛平齐，保持头部正直。',
                    'icon': 'head'
                })
            elif vt in ('head_tilt', 'neck'):
                recommendations.append({
                    'category': 'head_tilt',
                    'priority': 'low',
                    'title': '头部居中',
                    'content': '头部侧倾问题，建议工作时保持头部居中，避免歪头。',
                    'icon': 'head'
                })
            elif vt in ('shoulder_tilt', 'shoulder'):
                recommendations.append({
                    'category': 'shoulder_tilt',
                    'priority': 'low',
                    'title': '肩膀平衡',
                    'content': '肩膀倾斜建议检查键盘鼠标位置，保持肩膀放松自然下垂。',
                    'icon': 'shoulder'
                })

        # 运动建议
        if total_violations >= 10:
            recommendations.append({
                'category': 'exercise',
                'priority': 'high',
                'title': '肩颈放松',
                'content': '建议每天做 3 组肩颈放松操：点头仰头各 10 次，左右侧头各 10 次，耸肩放松 10 次。',
                'icon': 'exercise'
            })

        return recommendations

    def get_saved_reports(self,
                           report_type: str = None,
                           limit: int = 10) -> List[Dict]:
        """获取已保存的健康报告"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if report_type:
            cursor.execute('''
                SELECT id, report_date, report_type, start_date, end_date,
                       total_sitting_time, total_violations, total_sessions,
                       avg_posture_score, posture_level, recommendations
                FROM health_reports
                WHERE report_type = ?
                ORDER BY report_date DESC
                LIMIT ?
            ''', (report_type, limit))
        else:
            cursor.execute('''
                SELECT id, report_date, report_type, start_date, end_date,
                       total_sitting_time, total_violations, total_sessions,
                       avg_posture_score, posture_level, recommendations
                FROM health_reports
                ORDER BY report_date DESC
                LIMIT ?
            ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        reports = []
        for r in rows:
            reports.append({
                'id': r[0],
                'report_date': r[1],
                'report_type': r[2],
                'start_date': r[3],
                'end_date': r[4],
                'total_sitting_time': r[5],
                'total_violations': r[6],
                'total_sessions': r[7],
                'avg_posture_score': r[8],
                'posture_level': r[9],
                'recommendations': json.loads(r[10]) if r[10] else [],
            })
        return reports

    # ============================================================
    #  数据导出
    # ============================================================

    def export_to_csv(self,
                      file_path: str = None,
                      start_date: datetime = None,
                      end_date: datetime = None,
                      export_type: str = "sessions",
                      all_time: bool = False) -> str:
        """
        导出数据到 CSV 文件

        Args:
            file_path: 导出文件路径
            start_date: 开始日期
            end_date: 结束日期
            export_type: 导出类型 ("sessions", "daily", "violations")
            all_time: 是否导出所有时间的数据（忽略日期限制）

        Returns:
            导出文件路径
        """
        if file_path is None:
            today = datetime.now().strftime('%Y%m%d')
            file_path = os.path.join(os.path.dirname(self.db_path), f'posture_export_{today}.csv')

        if all_time:
            start_date = datetime(2000, 1, 1)
            end_date = datetime(2099, 12, 31)
        else:
            if start_date is None:
                start_date = datetime.now() - timedelta(days=30)
            if end_date is None:
                end_date = datetime.now()

        conn = self._get_connection()
        cursor = conn.cursor()

        if export_type == "sessions":
            cursor.execute('''
                SELECT id, start_time, end_time, total_duration,
                       total_violations, normal_duration, violation_duration,
                       posture_score, posture_level, sitting_view, notes
                FROM sessions
                WHERE status = 'completed'
                  AND start_time >= ? AND start_time <= ?
                ORDER BY start_time DESC
            ''', (start_date.isoformat(), end_date.isoformat()))

            fieldnames = [
                '会话ID', '开始时间', '结束时间', '总时长(秒)', '总时长(分钟)',
                '违规次数', '正常时长(秒)', '违规时长(秒)',
                '坐姿评分', '坐姿等级', '坐姿视角', '备注'
            ]

            def row_formatter(row):
                mins = round(row[3] / 60, 1) if row[3] else 0
                return [
                    row[0], row[1], row[2], row[3], mins,
                    row[4], row[5], row[6],
                    row[7], row[8], row[9], row[10] or ''
                ]

        elif export_type == "daily":
            cursor.execute('''
                SELECT date, total_sitting_time, total_violations, total_sessions,
                       avg_posture_score, posture_level, normal_time, violation_time,
                       excellent_sessions, good_sessions, fair_sessions, poor_sessions, bad_sessions
                FROM daily_stats
                WHERE date >= ? AND date <= ?
                ORDER BY date DESC
            ''', (start_date.date().isoformat(), end_date.date().isoformat()))

            fieldnames = [
                '日期', '总坐姿时间(秒)', '总违规次数', '总会话数',
                '平均评分', '坐姿等级', '正常时长(秒)', '违规时长(秒)',
                '优秀会话', '良好会话', '一般会话', '较差会话', '差会话'
            ]

            def row_formatter(row):
                return list(row)

        elif export_type == "violations":
            cursor.execute('''
                SELECT id, session_id, timestamp, violation_type,
                       violation_value, threshold_value, duration_seconds, status, resolved_at
                FROM violation_log
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp DESC
            ''', (start_date.isoformat(), end_date.isoformat()))

            fieldnames = [
                '违规ID', '会话ID', '时间', '违规类型',
                '实测值', '阈值', '持续时长(秒)', '状态', '解决时间'
            ]

            def row_formatter(row):
                return list(row)

        else:
            conn.close()
            raise ValueError(f"未知的导出类型: {export_type}")

        rows = cursor.fetchall()
        conn.close()

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(fieldnames)
            for row in rows:
                writer.writerow(row_formatter(row))

        logger.info(f"数据已导出到: {file_path} ({export_type}), 共 {len(rows)} 条记录")
        return file_path

    def export_report_to_json(self, report: Dict, file_path: str = None) -> str:
        """导出健康报告为 JSON 文件"""
        if file_path is None:
            today = date.today().isoformat()
            rtype = report.get('report_type', 'report')
            file_path = os.path.join(os.path.dirname(self.db_path), f'health_report_{rtype}_{today}.json')

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"健康报告已导出: {file_path}")
        return file_path

    # ============================================================
    #  数据清理
    # ============================================================

    def clear_old_data(self, days: int = 90) -> Dict:
        """
        清理旧数据

        Args:
            days: 保留最近多少天的数据

        Returns:
            清理结果统计
        """
        if days < 0:
            raise ValueError('保留天数不能为负数')
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        cutoff_date_only = (date.today() - timedelta(days=days)).isoformat()
        with self._write_lock:
            with closing(self._get_connection()) as conn, conn:
                old_days = conn.execute('''
                    SELECT DISTINCT date(start_time) FROM sessions
                    WHERE start_time < ? AND status != 'active'
                ''', (cutoff_date,)).fetchall()
                deleted_violations = conn.execute('''
                    DELETE FROM violation_log WHERE session_id IN (
                        SELECT id FROM sessions WHERE start_time < ? AND status != 'active'
                    )
                ''', (cutoff_date,)).rowcount
                deleted_sessions = conn.execute('''
                    DELETE FROM sessions WHERE start_time < ? AND status != 'active'
                ''', (cutoff_date,)).rowcount
                deleted_daily = conn.execute(
                    'DELETE FROM daily_stats WHERE date < ?', (cutoff_date_only,)).rowcount
                for (day,) in old_days:
                    self._refresh_daily_stats(conn, day)
                deleted_reports = conn.execute(
                    'DELETE FROM health_reports WHERE start_date < ?',
                    (cutoff_date_only,)).rowcount

        result = {
            'deleted_records': 0,
            'deleted_violations': deleted_violations,
            'deleted_sessions': deleted_sessions,
            'deleted_daily': deleted_daily,
            'deleted_reports': deleted_reports,
            'cutoff_date': cutoff_date_only,
        }

        logger.info(f"已清理数据: {result}")
        return result

    def get_database_stats(self) -> Dict:
        """获取数据库统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM sessions WHERE status = ?', ('completed',))
        total_sessions = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM violation_log')
        total_violations = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM daily_stats')
        total_daily = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM health_reports')
        total_reports = cursor.fetchone()[0]

        cursor.execute('SELECT SUM(total_sitting_time) FROM daily_stats')
        total_time = cursor.fetchone()[0] or 0

        cursor.execute('''SELECT SUM(avg_posture_score * total_sessions)
                          / NULLIF(SUM(total_sessions), 0) FROM daily_stats''')
        avg_score = cursor.fetchone()[0]
        if avg_score is None:
            avg_score = 100.0

        # 数据库文件大小
        try:
            db_size = os.path.getsize(self.db_path)
        except:
            db_size = 0

        conn.close()

        return {
            'total_sessions': total_sessions,
            'total_violations': total_violations,
            'total_daily_stats': total_daily,
            'total_reports': total_reports,
            'total_sitting_time': total_time,
            'avg_posture_score': round(avg_score, 1),
            'database_size_bytes': db_size,
            'database_size_mb': round(db_size / (1024 * 1024), 2),
        }

    def vacuum(self):
        """整理数据库（清理空隙，减小文件大小）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('VACUUM')
        conn.close()
        logger.info("数据库 VACUUM 完成")

    def delete_session(self, session_id: int):
        """删除指定会话及其相关违规记录"""
        with self._write_lock:
            with closing(self._get_connection()) as conn, conn:
                row = conn.execute('SELECT date(start_time) FROM sessions WHERE id = ?',
                                   (session_id,)).fetchone()
                conn.execute('DELETE FROM violation_log WHERE session_id = ?', (session_id,))
                conn.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
                if row:
                    self._refresh_daily_stats(conn, row[0])
            if session_id == self._current_session_id:
                self._current_session_id = None
                self._session_start = None
        logger.info(f"会话已删除: id={session_id}")

    def _refresh_daily_stats(self, conn: sqlite3.Connection, day: str):
        """删除或清理会话后，按剩余会话重算当天汇总。"""
        row = conn.execute('''
            SELECT COUNT(*), SUM(total_duration), SUM(total_violations),
                   SUM(normal_duration), SUM(violation_duration), AVG(posture_score),
                   SUM(posture_level = 'excellent'), SUM(posture_level = 'good'),
                   SUM(posture_level = 'fair'), SUM(posture_level = 'poor'),
                   SUM(posture_level = 'bad')
            FROM sessions WHERE date(start_time) = ? AND status = 'completed'
        ''', (day,)).fetchone()
        if not row[0]:
            conn.execute('DELETE FROM daily_stats WHERE date = ?', (day,))
            return
        conn.execute('''
            INSERT INTO daily_stats
                (date, total_sessions, total_sitting_time, total_violations,
                 normal_time, violation_time, avg_posture_score, posture_level,
                 excellent_sessions, good_sessions, fair_sessions, poor_sessions, bad_sessions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_sessions = excluded.total_sessions,
                total_sitting_time = excluded.total_sitting_time,
                total_violations = excluded.total_violations,
                normal_time = excluded.normal_time,
                violation_time = excluded.violation_time,
                avg_posture_score = excluded.avg_posture_score,
                posture_level = excluded.posture_level,
                excellent_sessions = excluded.excellent_sessions,
                good_sessions = excluded.good_sessions,
                fair_sessions = excluded.fair_sessions,
                poor_sessions = excluded.poor_sessions,
                bad_sessions = excluded.bad_sessions
        ''', (day, *row[:6], PostureLevel.from_score(row[5]).value, *row[6:]))

    def _fmt_time(self, ts: str) -> str:
        """格式化 ISO 时间字符串为 YYYY-MM-DD HH:MM:SS，未知时显示 --:--:--"""
        if not ts:
            return '--:--:--'
        return ts[:19].replace('T', ' ')

    def _fmt_val(self, value, fmt: str = '{:.1f}') -> str:
        """安全格式化数值，None 或无法解析时返回 '--'，0 正常显示"""
        if value is None:
            return '--'
        try:
            return fmt.format(float(value))
        except (ValueError, TypeError):
            return '--'

    def _level_cn(self, level: str) -> str:
        """将英文等级转为中文，未知返回 '--'"""
        if not level:
            return '--'
        try:
            return PostureLevel(level).label_cn
        except ValueError:
            return '--'

    def export_session_to_csv(self, session: Dict, file_path: str):
        """将单个会话导出为 CSV"""
        rows = [
            ('开始时间', self._fmt_time(session.get('start_time', ''))),
            ('结束时间', self._fmt_time(session.get('end_time', ''))),
            ('总时长(秒)', session.get('total_duration', 0)),
            ('违规次数', session.get('total_violations', 0)),
            ('正常时长(秒)', session.get('normal_duration', 0)),
            ('违规时长(秒)', session.get('violation_duration', 0)),
            ('坐姿评分', self._fmt_val(session.get('posture_score', 0), '{:.1f}')),
            ('坐姿等级', self._level_cn(session.get('posture_level', ''))),
            ('头部侧倾(°)', self._fmt_val(session.get('avg_neck_angle'), '{:.1f}')),
            ('肩膀倾斜(°)', self._fmt_val(session.get('avg_shoulder_diff'), '{:.1f}')),
            ('头部前倾(°)', self._fmt_val(session.get('avg_head_forward_angle'), '{:.1f}')),
            ('躯干倾斜(°)', self._fmt_val(session.get('avg_torso_angle'), '{:.1f}')),
        ]
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([r[0] for r in rows])
            writer.writerow([r[1] for r in rows])
        logger.info(f"单个会话已导出: {file_path}")

    def export_all_sessions_to_csv(self, file_path: str):
        """将所有会话导出为一个 CSV 文件"""
        sessions = self.get_session_history(limit=99999)
        if not sessions:
            raise ValueError("没有可导出的会话记录")

        rows = [
            ('开始时间', '结束时间', '总时长(秒)', '违规次数',
             '正常时长(秒)', '违规时长(秒)', '坐姿评分', '坐姿等级',
             '头部侧倾(°)', '肩膀倾斜(°)', '头部前倾(°)', '躯干倾斜(°)')
        ]
        for s in sessions:
            rows.append((
                self._fmt_time(s.get('start_time', '')),
                self._fmt_time(s.get('end_time', '')),
                s.get('total_duration', 0),
                s.get('total_violations', 0),
                s.get('normal_duration', 0),
                s.get('violation_duration', 0),
                self._fmt_val(s.get('posture_score', 0), '{:.1f}'),
                self._level_cn(s.get('posture_level', '')),
                self._fmt_val(s.get('avg_neck_angle'), '{:.1f}'),
                self._fmt_val(s.get('avg_shoulder_diff'), '{:.1f}'),
                self._fmt_val(s.get('avg_head_forward_angle'), '{:.1f}'),
                self._fmt_val(s.get('avg_torso_angle'), '{:.1f}'),
            ))
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        logger.info(f"全部会话已导出，共 {len(sessions)} 条: {file_path}")

    def clear_all_sessions(self) -> int:
        """清空所有会话记录及相关数据"""
        with self._write_lock:
            with closing(self._get_connection()) as conn, conn:
                count = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
                conn.execute('DELETE FROM violation_log')
                conn.execute('DELETE FROM daily_stats')
                conn.execute('DELETE FROM health_reports')
                conn.execute('DELETE FROM sessions')
            self._current_session_id = None
            self._session_start = None
        logger.info(f"已清空全部会话记录，共 {count} 条")
        return count

    # ============================================================
    #  辅助方法
    # ============================================================

    def _rows_to_dict(self, rows: List, columns: List[str]) -> List[Dict]:
        """将查询结果行转换为字典列表"""
        return [dict(zip(columns, row)) for row in rows]

    def close(self):
        """关闭数据管理器（清理资源）"""
        logger.info("数据管理器已关闭")


def create_data_manager(db_path: str = None) -> DataManager:
    """创建数据管理器的工厂函数"""
    return DataManager(db_path)
