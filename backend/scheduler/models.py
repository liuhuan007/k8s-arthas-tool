"""
Scheduler 数据模型 — 独立于诊断中心的表结构
"""
import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


_lock = threading.Lock()


class SchedulerDB:
    """Scheduler 数据库操作"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_tables(self):
        """初始化 scheduler 相关表"""
        with _lock:
            conn = self._conn()
            try:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS scheduler_tasks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        script_source TEXT DEFAULT 'inline',
                        script_content TEXT DEFAULT '',
                        uploaded_file_name TEXT DEFAULT '',
                        runtime TEXT DEFAULT 'shell',
                        target_type TEXT DEFAULT 'node',
                        target_config_json TEXT DEFAULT '{}',
                        timeout_seconds INTEGER DEFAULT 300,
                        created_by INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS scheduler_runs (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        trigger_type TEXT DEFAULT 'manual',
                        status TEXT DEFAULT 'pending',
                        target_identifier TEXT DEFAULT '',
                        stdout TEXT DEFAULT '',
                        stderr TEXT DEFAULT '',
                        exit_code INTEGER,
                        error TEXT,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (task_id) REFERENCES scheduler_tasks(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS scheduler_schedules (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL UNIQUE,
                        schedule_type TEXT DEFAULT 'none',
                        cron_expr TEXT DEFAULT '',
                        interval_seconds INTEGER DEFAULT 0,
                        enabled INTEGER DEFAULT 1,
                        next_run_at TIMESTAMP,
                        last_run_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (task_id) REFERENCES scheduler_tasks(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_scheduler_runs_task ON scheduler_runs(task_id);
                    CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_runs(status);
                    CREATE INDEX IF NOT EXISTS idx_scheduler_schedules_task ON scheduler_schedules(task_id);
                ''')
                # 增量迁移: 添加 uploaded_file_name 列
                try:
                    conn.execute("ALTER TABLE scheduler_tasks ADD COLUMN uploaded_file_name TEXT DEFAULT ''")
                except Exception:
                    pass
                conn.commit()
            finally:
                conn.close()

    # ── Tasks CRUD ─────────────────────────────────────────────────────────

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        import uuid
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        with _lock:
            conn = self._conn()
            try:
                conn.execute('''
                    INSERT INTO scheduler_tasks (id, name, description, script_source, script_content,
                        uploaded_file_name, runtime, target_type, target_config_json, timeout_seconds, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id, data.get('name', ''), data.get('description', ''),
                    data.get('script_source', 'inline'), data.get('script_content', ''),
                    data.get('uploaded_file_name', ''),
                    data.get('runtime', 'shell'), data.get('target_type', 'node'),
                    json.dumps(data.get('target_config', {}), ensure_ascii=False),
                    data.get('timeout_seconds', 300), data.get('created_by'), now, now
                ))
                # 创建默认调度（手动执行）
                schedule_id = str(uuid.uuid4())[:8]
                conn.execute('''
                    INSERT INTO scheduler_schedules (id, task_id, schedule_type, enabled)
                    VALUES (?, ?, 'none', 1)
                ''', (schedule_id, task_id))
                conn.commit()
                return self.get_task(task_id)
            finally:
                conn.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute('SELECT * FROM scheduler_tasks WHERE id = ?', (task_id,)).fetchone()
            if not row:
                return None
            task = dict(row)
            task['target_config'] = json.loads(task.get('target_config_json', '{}'))
            del task['target_config_json']
            # 附加调度信息
            sched = conn.execute('SELECT * FROM scheduler_schedules WHERE task_id = ?', (task_id,)).fetchone()
            task['schedule'] = dict(sched) if sched else None
            # 附加上次运行
            last_run = conn.execute(
                'SELECT * FROM scheduler_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1',
                (task_id,)
            ).fetchone()
            task['last_run'] = dict(last_run) if last_run else None
            return task
        finally:
            conn.close()

    def list_tasks(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute('''
                SELECT t.*, s.schedule_type, s.cron_expr, s.interval_seconds, s.enabled as schedule_enabled,
                    s.next_run_at, s.last_run_at
                FROM scheduler_tasks t
                LEFT JOIN scheduler_schedules s ON t.id = s.task_id
                ORDER BY t.updated_at DESC
            ''').fetchall()
            tasks = []
            for row in rows:
                task = dict(row)
                task['target_config'] = json.loads(task.get('target_config_json', '{}'))
                del task['target_config_json']
                # 附加上次运行状态
                last_run = conn.execute(
                    'SELECT id, status, exit_code, completed_at FROM scheduler_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1',
                    (task['id'],)
                ).fetchone()
                task['last_run'] = dict(last_run) if last_run else None
                tasks.append(task)
            return tasks
        finally:
            conn.close()

    def update_task(self, task_id: str, data: Dict[str, Any]) -> bool:
        now = datetime.now().isoformat()
        fields = []
        values = []
        for key in ('name', 'description', 'script_source', 'script_content', 'uploaded_file_name', 'runtime',
                     'target_type', 'timeout_seconds'):
            if key in data:
                fields.append(f'{key} = ?')
                values.append(data[key])
        if 'target_config' in data:
            fields.append('target_config_json = ?')
            values.append(json.dumps(data['target_config'], ensure_ascii=False))
        fields.append('updated_at = ?')
        values.append(now)
        values.append(task_id)
        with _lock:
            conn = self._conn()
            try:
                conn.execute(f'UPDATE scheduler_tasks SET {", ".join(fields)} WHERE id = ?', values)
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    def delete_task(self, task_id: str) -> bool:
        with _lock:
            conn = self._conn()
            try:
                conn.execute('DELETE FROM scheduler_tasks WHERE id = ?', (task_id,))
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    # ── Runs ───────────────────────────────────────────────────────────────

    def create_run(self, task_id: str, trigger_type: str = 'manual',
                   target_identifier: str = '') -> Dict[str, Any]:
        import uuid
        run_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        with _lock:
            conn = self._conn()
            try:
                conn.execute('''
                    INSERT INTO scheduler_runs (id, task_id, trigger_type, status, target_identifier, created_at)
                    VALUES (?, ?, ?, 'pending', ?, ?)
                ''', (run_id, task_id, trigger_type, target_identifier, now))
                conn.commit()
                return dict(conn.execute('SELECT * FROM scheduler_runs WHERE id = ?', (run_id,)).fetchone())
            finally:
                conn.close()

    def update_run(self, run_id: str, **kwargs) -> bool:
        fields = []
        values = []
        for key, val in kwargs.items():
            fields.append(f'{key} = ?')
            values.append(val)
        values.append(run_id)
        with _lock:
            conn = self._conn()
            try:
                conn.execute(f'UPDATE scheduler_runs SET {", ".join(fields)} WHERE id = ?', values)
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute('SELECT * FROM scheduler_runs WHERE id = ?', (run_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_runs(self, task_id: str = None, status: str = None,
                  limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            query = 'SELECT r.*, t.name as task_name FROM scheduler_runs r LEFT JOIN scheduler_tasks t ON r.task_id = t.id WHERE 1=1'
            params = []
            if task_id:
                query += ' AND r.task_id = ?'
                params.append(task_id)
            if status:
                query += ' AND r.status = ?'
                params.append(status)
            query += ' ORDER BY r.created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            return [dict(row) for row in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    # ── Schedules ──────────────────────────────────────────────────────────

    def update_schedule(self, task_id: str, **kwargs) -> bool:
        fields = []
        values = []
        for key in ('schedule_type', 'cron_expr', 'interval_seconds', 'enabled', 'next_run_at', 'last_run_at'):
            if key in kwargs:
                fields.append(f'{key} = ?')
                values.append(kwargs[key])
        values.append(task_id)
        if not fields:
            return False
        with _lock:
            conn = self._conn()
            try:
                conn.execute(f'UPDATE scheduler_schedules SET {", ".join(fields)} WHERE task_id = ?', values)
                conn.commit()
                return conn.total_changes > 0
            finally:
                conn.close()

    def get_active_schedules(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute('''
                SELECT s.*, t.name as task_name, t.runtime, t.target_type
                FROM scheduler_schedules s
                JOIN scheduler_tasks t ON s.task_id = t.id
                WHERE s.enabled = 1 AND s.schedule_type != 'none'
            ''').fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ── Stats ──────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        conn = self._conn()
        try:
            total_tasks = conn.execute('SELECT COUNT(*) FROM scheduler_tasks').fetchone()[0]
            active_schedules = conn.execute(
                'SELECT COUNT(*) FROM scheduler_schedules WHERE enabled = 1 AND schedule_type != "none"'
            ).fetchone()[0]
            running = conn.execute(
                'SELECT COUNT(*) FROM scheduler_runs WHERE status = "running"'
            ).fetchone()[0]
            today = datetime.now().strftime('%Y-%m-%d')
            today_runs = conn.execute(
                'SELECT COUNT(*) FROM scheduler_runs WHERE created_at >= ?', (today,)
            ).fetchone()[0]
            today_success = conn.execute(
                'SELECT COUNT(*) FROM scheduler_runs WHERE created_at >= ? AND status = "success"', (today,)
            ).fetchone()[0]
            today_failed = conn.execute(
                'SELECT COUNT(*) FROM scheduler_runs WHERE created_at >= ? AND status = "failed"', (today,)
            ).fetchone()[0]
            return {
                'total_tasks': total_tasks,
                'active_schedules': active_schedules,
                'running_runs': running,
                'today_runs': today_runs,
                'today_success': today_success,
                'today_failed': today_failed,
            }
        finally:
            conn.close()
