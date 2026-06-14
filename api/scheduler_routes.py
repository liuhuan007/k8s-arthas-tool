"""
Scheduler API 路由 — /api/scheduler/*
"""
import json
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required

from backend.scheduler.models import SchedulerDB
from backend.scheduler.executor import ScriptExecutor
from backend.scheduler.scheduler import SchedulerManager
from backend.config import Config

scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/api/scheduler')

# 单例
_db: SchedulerDB = None
_executor: ScriptExecutor = None
_manager: SchedulerManager = None


def _get_db() -> SchedulerDB:
    global _db
    if _db is None:
        _db = SchedulerDB(Config.DB_FILE)
        _db.init_tables()
    return _db


def _get_executor() -> ScriptExecutor:
    global _executor
    if _executor is None:
        _executor = ScriptExecutor()
    return _executor


def _get_manager() -> SchedulerManager:
    global _manager
    if _manager is None:
        _manager = SchedulerManager(_get_db(), _get_executor())
    return _manager


def init_scheduler():
    """初始化 scheduler 模块（在 server.py 中调用）"""
    db = _get_db()
    manager = _get_manager()
    manager.start()
    return db


# ── Tasks ──────────────────────────────────────────────────────────────────

@scheduler_bp.route('/tasks', methods=['GET'])
@login_required
def list_tasks():
    db = _get_db()
    tasks = db.list_tasks()
    return jsonify({'tasks': tasks})


@scheduler_bp.route('/tasks', methods=['POST'])
@login_required
def create_task():
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '任务名称必填'}), 400

    db = _get_db()
    data['created_by'] = current_user.id if current_user.is_authenticated else None
    task = db.create_task(data)
    return jsonify({'ok': True, 'task': task}), 201


@scheduler_bp.route('/tasks/<task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify({'task': task})


@scheduler_bp.route('/tasks/<task_id>', methods=['PUT', 'POST'])
@login_required
def update_task(task_id):
    data = request.json or {}
    db = _get_db()
    if not db.update_task(task_id, data):
        return jsonify({'error': '任务不存在'}), 404
    return jsonify({'ok': True, 'task': db.get_task(task_id)})


@scheduler_bp.route('/tasks/<task_id>', methods=['DELETE', 'POST'])
@login_required
def delete_task(task_id):
    db = _get_db()
    db.delete_task(task_id)
    return jsonify({'ok': True})


# ── Runs ───────────────────────────────────────────────────────────────────

@scheduler_bp.route('/tasks/<task_id>/run', methods=['POST'])
@login_required
def run_task(task_id):
    db = _get_db()
    task = db.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    manager = _get_manager()
    run = manager.trigger_now(task_id)
    return jsonify({'ok': True, 'run': run})


@scheduler_bp.route('/tasks/<task_id>/runs', methods=['GET'])
@login_required
def list_task_runs(task_id):
    db = _get_db()
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    runs = db.list_runs(task_id=task_id, limit=limit, offset=offset)
    return jsonify({'runs': runs})


@scheduler_bp.route('/runs/<run_id>', methods=['GET'])
@login_required
def get_run(run_id):
    db = _get_db()
    run = db.get_run(run_id)
    if not run:
        return jsonify({'error': '运行记录不存在'}), 404
    return jsonify({'run': run})


@scheduler_bp.route('/runs', methods=['GET'])
@login_required
def list_runs():
    db = _get_db()
    task_id = request.args.get('task_id')
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    runs = db.list_runs(task_id=task_id, status=status, limit=limit, offset=offset)
    return jsonify({'runs': runs})


# ── Schedules ──────────────────────────────────────────────────────────────

@scheduler_bp.route('/tasks/<task_id>/schedule', methods=['PUT', 'POST'])
@login_required
def update_schedule(task_id):
    data = request.json or {}
    db = _get_db()
    db.update_schedule(task_id, **data)
    return jsonify({'ok': True})


# ── Stats ──────────────────────────────────────────────────────────────────

@scheduler_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    db = _get_db()
    stats = db.get_stats()
    return jsonify(stats)
