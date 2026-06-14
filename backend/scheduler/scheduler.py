"""
调度管理器 — Cron 调度 + 任务触发
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


class SchedulerManager:
    """管理定时调度，检查并触发到期任务"""

    def __init__(self, db, executor):
        self.db = db
        self.executor = executor
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval = 60  # 检查间隔（秒）

    def start(self):
        """启动调度器"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='scheduler-loop')
        self._thread.start()
        log.info("Scheduler manager started")

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Scheduler manager stopped")

    def _run_loop(self):
        """主循环：检查到期任务并执行"""
        while self._running:
            try:
                self._check_and_run()
            except Exception as e:
                log.error("Scheduler check error: %s", e)
            time.sleep(self._interval)

    def _check_and_run(self):
        """检查到期的调度任务"""
        now = datetime.now().isoformat()
        schedules = self.db.get_active_schedules()
        for sched in schedules:
            next_run = sched.get('next_run_at')
            if not next_run or next_run > now:
                continue
            # 触发执行
            task_id = sched['task_id']
            log.info("Triggering scheduled task: %s (schedule: %s)", task_id, sched['id'])
            self._trigger_run(task_id, 'cron')
            # 更新下次执行时间
            self._update_next_run(sched)

    def _trigger_run(self, task_id: str, trigger_type: str = 'manual'):
        """触发一次执行"""
        task = self.db.get_task(task_id)
        if not task:
            log.warning("Task not found: %s", task_id)
            return

        # 创建运行记录
        run = self.db.create_run(task_id, trigger_type)

        # 在新线程中执行
        t = threading.Thread(
            target=self._execute_run,
            args=(run['id'], task),
            daemon=True
        )
        t.start()
        return run

    def _execute_run(self, run_id: str, task: dict):
        """执行脚本并更新运行状态"""
        self.db.update_run(run_id, status='running', started_at=datetime.now().isoformat())
        try:
            exit_code, stdout, stderr = self.executor.execute(
                script_content=task.get('script_content', ''),
                runtime=task.get('runtime', 'shell'),
                target_type=task.get('target_type', 'node'),
                target_config=task.get('target_config', {}),
                timeout=task.get('timeout_seconds', 300),
            )
            status = 'success' if exit_code == 0 else 'failed'
            self.db.update_run(
                run_id,
                status=status,
                stdout=stdout[:65536],  # 限制大小
                stderr=stderr[:65536],
                exit_code=exit_code,
                completed_at=datetime.now().isoformat(),
            )
            log.info("Run %s completed: status=%s, exit_code=%s", run_id, status, exit_code)
        except Exception as e:
            self.db.update_run(
                run_id,
                status='failed',
                error=str(e),
                completed_at=datetime.now().isoformat(),
            )
            log.error("Run %s failed: %s", run_id, e)

    def _update_next_run(self, schedule: dict):
        """更新下次执行时间"""
        schedule_type = schedule.get('schedule_type', 'none')
        if schedule_type == 'none':
            return

        now = datetime.now()
        if schedule_type == 'interval':
            interval = schedule.get('interval_seconds', 3600)
            next_run = now + timedelta(seconds=interval)
        elif schedule_type == 'cron':
            next_run = self._parse_cron_next(schedule.get('cron_expr', ''), now)
        else:
            return

        if next_run:
            self.db.update_schedule(schedule['task_id'], next_run_at=next_run.isoformat())

    def _parse_cron_next(self, cron_expr: str, now: datetime) -> Optional[datetime]:
        """简单解析 cron 表达式，返回下次执行时间"""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return None

        minute, hour, day, month, dow = parts
        next_run = now.replace(second=0, microsecond=0)

        # 简单实现：只处理 "每小时"、"每天 HH:MM" 等常见模式
        if minute != '*':
            next_run = next_run.replace(minute=int(minute))
        if hour != '*':
            next_run = next_run.replace(hour=int(hour))

        if next_run <= now:
            next_run += timedelta(days=1)

        return next_run

    def trigger_now(self, task_id: str) -> dict:
        """手动触发执行"""
        return self._trigger_run(task_id, 'manual')
