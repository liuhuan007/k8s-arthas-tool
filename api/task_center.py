#!/usr/bin/env python3
"""通用脚本 / 工具任务中心 API。

M1 范围：
- 工具包、脚本模板、任务定义、执行记录基础表
- Node 本机执行器最小闭环
- Pod 内执行器最小闭环
- 定时调度、OSS 同步仅预留模型字段，后续迭代实现
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from backend import Config
from models.db import db
from services.authorization_service import AuthorizationService
from backend.core.parameter_validator import ParameterValidator
from backend.core.command_builder import build_command
from services.audit_service import AuditService


task_bp = Blueprint('task_center', __name__, url_prefix='/api/tasks')
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 诊断能力 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/capabilities', methods=['GET'])
@login_required
def list_capabilities():
    """查询诊断能力目录"""
    type_filter = request.args.get('type')
    category_filter = request.args.get('category') or type_filter  # type 是 category 的别名
    level_filter = request.args.get('level')
    keyword = request.args.get('keyword', '').strip()
    include_disabled = request.args.get('include_disabled') == '1'

    where_clauses = []
    params = []

    if category_filter:
        where_clauses.append('category = ?')
        params.append(category_filter)
    if level_filter:
        try:
            where_clauses.append('level = ?')
            params.append(int(level_filter))
        except (ValueError, TypeError):
            return _error('level 参数必须是整数')
    if keyword:
        where_clauses.append('(name LIKE ? OR description LIKE ?)')
        params.extend([f'%{keyword}%', f'%{keyword}%'])

    if not include_disabled:
        where_clauses.append("COALESCE(status, 'active') = 'active'")
    
    # ✅ Phase 5: 权限过滤
    user_role = current_user.role if hasattr(current_user, 'role') else 'user'
    if user_role != 'admin':
        user_id = current_user.id
        where_clauses.append(
            '(visibility = ? OR (visibility = ? AND created_by = ?) OR id IN ('
            '  SELECT capability_id FROM capability_user_groups WHERE group_id IN ('
            '    SELECT group_id FROM user_group_members WHERE user_id = ?'
            '  )'
            '))'
        )
        params.extend(['public', 'private', user_id, user_id])
    
    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
    
    rows = db.fetch_all(
        f'SELECT * FROM diagnosis_capabilities WHERE {where_sql} ORDER BY level, category, id',
        tuple(params)
    )
    
    capabilities = []
    for row in rows:
        cap = dict(row)
        # 加载扩展数据
        cap['extension'] = load_extension(cap['category'], cap['id'])
        capabilities.append(cap)
    
    return jsonify({'capabilities': capabilities})


@task_bp.route('/capabilities/<int:cap_id>', methods=['GET'])
@login_required
def get_capability(cap_id: int):
    """获取单个诊断能力详情"""
    cap = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    if not cap:
        return jsonify({'error': '能力不存在'}), 404
    
    result = dict(cap)
    result['extension'] = load_extension(cap['category'], cap_id)
    return jsonify({'capability': result})



def load_extension(cap_type: str, capability_id: int) -> dict:
    """加载能力扩展数据。

    cap_type is the product category: quick/tool/scenario/ai.
    arthas_command_templates, diagnosis_scenario_steps, ai_diagnosis_handlers
    已移除（空壳表），返回空 extension。
    """
    return {}


_CAPABILITY_CATEGORIES = {'quick', 'tool', 'scenario', 'ai', 'mcp'}
_CAPABILITY_STATUSES = {'active', 'disabled'}
_CAPABILITY_VISIBILITIES = {'public', 'private'}


def _is_admin_user() -> bool:
    return bool(getattr(current_user, 'is_admin', False) or getattr(current_user, 'role', '') == 'admin')


def _require_admin():
    if not _is_admin_user():
        return _error('仅管理员可维护诊断能力', 403)
    return None


def _normalize_capability_level(value: Any) -> int:
    if value in ('pod', 'quick'):
        return 1
    if value in ('arthas', 'tool'):
        return 2
    if value == 'scenario':
        return 3
    if value == 'ai':
        return 4
    try:
        level = int(value or 1)
    except Exception:
        raise ValueError('level 必须是整数或 pod/arthas/scenario/ai')
    return max(1, min(level, 4))


def _validate_capability_payload(data: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    if not partial or 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            raise ValueError('能力名称不能为空')
        fields['name'] = name

    if not partial or 'category' in data:
        category = (data.get('category') or '').strip().lower()
        if category not in _CAPABILITY_CATEGORIES:
            raise ValueError('category 只能是 quick/tool/scenario/ai/mcp')
        fields['category'] = category

    if 'level' in data:
        fields['level'] = _normalize_capability_level(data.get('level'))
    elif not partial:
        fields['level'] = _normalize_capability_level(data.get('level') or 1)

    if 'description' in data or not partial:
        fields['description'] = (data.get('description') or '').strip()

    if 'arthas_command' in data:
        fields['arthas_command'] = (data.get('arthas_command') or '').strip()

    if 'parameters_schema' in data or not partial:
        schema = data.get('parameters_schema') if 'parameters_schema' in data else {}
        if isinstance(schema, str):
            _json_loads(schema, {})
            fields['parameters_schema'] = schema or '{}'
        else:
            fields['parameters_schema'] = _json_dumps(schema or {})

    if 'risk_level' in data:
        risk_level = (data.get('risk_level') or 'low').strip().lower()
        if risk_level not in {'low', 'medium', 'high'}:
            raise ValueError('risk_level 只能是 low/medium/high')
        fields['risk_level'] = risk_level

    if 'estimated_duration' in data:
        fields['estimated_duration'] = max(0, int(data.get('estimated_duration') or 0))

    if 'prerequisites' in data:
        fields['prerequisites'] = _json_dumps(data.get('prerequisites') or [])

    if 'related_capabilities' in data:
        fields['related_capabilities'] = _json_dumps(data.get('related_capabilities') or [])

    if 'confirm_required' in data:
        fields['confirm_required'] = 1 if data.get('confirm_required') else 0

    if 'visibility' in data or not partial:
        visibility = (data.get('visibility') or 'public').strip().lower()
        if visibility not in _CAPABILITY_VISIBILITIES:
            raise ValueError('visibility 只能是 public/private')
        fields['visibility'] = visibility

    if 'status' in data or not partial:
        status = (data.get('status') or 'active').strip().lower()
        if status not in _CAPABILITY_STATUSES:
            raise ValueError('status 只能是 active/disabled')
        fields['status'] = status

    if 'sort_order' in data:
        fields['sort_order'] = int(data.get('sort_order') or 0)

    if 'handler_key' in data:
        fields['handler_key'] = (data.get('handler_key') or '').strip()

    return fields


@task_bp.route('/capabilities', methods=['POST'])
@login_required
def create_capability():
    """管理员创建诊断能力。"""
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    data = request.json or {}
    try:
        fields = _validate_capability_payload(data)
    except (ValueError, TypeError) as exc:
        return _error(str(exc))

    fields.update({
        'is_builtin': 0,
        'version': 1,
        'created_by': current_user.id,
        'created_at': _now_text(),
        'updated_at': _now_text(),
    })
    cap_id = db.insert('diagnosis_capabilities', fields)
    cap = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    return jsonify({'ok': True, 'capability': dict(cap)}), 201


@task_bp.route('/capabilities/<int:cap_id>', methods=['PUT'])
@login_required
def update_capability(cap_id: int):
    """管理员更新诊断能力，并递增版本号。"""
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    capability = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    if not capability:
        return _error('能力不存在', 404)

    data = request.json or {}
    try:
        fields = _validate_capability_payload(data, partial=True)
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    if not fields:
        return _error('没有可更新字段')

    fields['version'] = int(capability.get('version') or 1) + 1
    fields['updated_at'] = _now_text()
    db.update('diagnosis_capabilities', fields, 'id = ?', (cap_id,))
    cap = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    return jsonify({'ok': True, 'capability': dict(cap)})


@task_bp.route('/capabilities/<int:cap_id>', methods=['DELETE'])
@login_required
def disable_capability(cap_id: int):
    """管理员禁用诊断能力，避免破坏历史快照。"""
    admin_error = _require_admin()
    if admin_error:
        return admin_error

    capability = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    if not capability:
        return _error('能力不存在', 404)

    db.update('diagnosis_capabilities', {
        'status': 'disabled',
        'version': int(capability.get('version') or 1) + 1,
        'updated_at': _now_text(),
    }, 'id = ?', (cap_id,))
    return jsonify({'ok': True, 'id': cap_id, 'status': 'disabled'})


def _get_active_arthas_connection(connection_id: str, connection_row: Optional[Dict[str, Any]] = None):
    """Return active ArthasConnection from server runtime state.

    Diagnosis execution must use ArthasConnection because ArthasCommandExecutor
    depends on `connection.http_client.exec_once()`. DB rows or PodConnection are
    metadata only and cannot execute Arthas HTTP commands.
    """
    server_mod = sys.modules.get('server')
    if server_mod is None:
        raise ValueError('服务运行态不可用，无法获取连接对象')

    runtime_connections = getattr(server_mod, '_connections', None)
    if runtime_connections is None:
        raise ValueError('连接运行态不可用')

    candidates = [connection_id]
    if connection_row:
        base_id = f"{connection_row.get('cluster_name')}/{connection_row.get('namespace')}/{connection_row.get('pod_name')}"
        if base_id not in candidates:
            candidates.append(base_id)
        user_id = connection_row.get('user_id') or getattr(current_user, 'id', None)
        if user_id:
            user_scoped = f"{base_id}@u{user_id}"
            if user_scoped not in candidates:
                candidates.insert(0, user_scoped)

    for cid in candidates:
        entry = runtime_connections.get(cid)
        if not entry:
            continue
        if not getattr(current_user, 'is_admin', False) and entry.get('user_id') != current_user.id:
            continue
        conn = entry.get('conn')
        if conn and getattr(conn, 'http_client', None):
            return conn

    raise ValueError('Arthas 连接不可用或已断开，请重新建立连接')


_ALLOWED_RUNTIMES = {'python', 'shell'}
_ALLOWED_EXECUTION_MODES = {'node', 'pod'}
_DEFAULT_TIMEOUT_SECONDS = 60
_MAX_TIMEOUT_SECONDS = 600
_OUTPUT_ROOT = Path('data/task_runs')
_TOOL_PACKAGE_ROOT = Path('data/tool_packages')
_TOOL_TYPES = {'arthas', 'async-profiler', 'jattach', 'generic'}
_BUILTIN_ARTHAS_PATH = str(Path(__file__).resolve().parent.parent / 'tools' / 'arthas' / 'arthas-boot.jar')
_DEFAULT_ARTHAS_INSTALL_PATH = '/tmp/arthas/arthas-boot.jar'
_SCHEDULER_STARTED = False
_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_POLL_SECONDS = 5
_MIN_INTERVAL_SECONDS = 60
_MAX_INTERVAL_SECONDS = 86400

_USER_CASE_CAPABILITIES = [
    {
        'name': 'CPU 高负载一键诊断',
        'github_issue': '#1202/#569',
        'product_stage': 'M1',
        'category': 'runtime-diagnosis',
        'script': 'thread -n 5\nprofiler start --event cpu --duration 30\nprofiler stop\ntrace ${CLASS_PATTERN:-com.example.*} ${METHOD_PATTERN:-*} --skipJDKMethod false',
        'description': '来自 Arthas user-case：高 CPU 线程定位、热点方法分析和 profiler 采样组合。',
    },
    {
        'name': 'Trace 调用链耗时分析',
        'github_issue': '#597/#764/#729',
        'product_stage': 'M1',
        'category': 'trace',
        'script': 'trace ${CLASS_NAME:-com.example.Service} ${METHOD_NAME:-*} --skipJDKMethod false',
        'description': '把 trace 调用树、慢调用和 Controller/Service/DAO 分层耗时产品化。',
    },
    {
        'name': 'Watch 方法现场观测',
        'github_issue': '#764/#772',
        'product_stage': 'M1',
        'category': 'watch',
        'script': 'watch ${CLASS_NAME:-com.example.Service} ${METHOD_NAME:-*} "{params,returnObj,throwExp}" -x 3 -n 5',
        'description': '观测入参、返回值、异常和 OGNL 表达式，沉淀为方法现场观测器。',
    },
    {
        'name': 'Controller 请求入口定位',
        'github_issue': '#729',
        'product_stage': 'M1',
        'category': 'web',
        'script': 'stack ${CONTROLLER_PATTERN:-*Controller} ${METHOD_NAME:-*} -n 5\ntrace ${CONTROLLER_PATTERN:-*Controller} ${METHOD_NAME:-*}',
        'description': '定位某个请求由哪个 Controller/Interceptor/Service 处理。',
    },
    {
        'name': 'TraceId 上下文提取',
        'github_issue': '#1244',
        'product_stage': 'M2',
        'category': 'observability',
        'script': 'ognl "@org.slf4j.MDC@getCopyOfContextMap()"\nthread -n 3',
        'description': '从 MDC、ThreadLocal 或 RPC 上下文中提取 traceId，打通日志和链路。',
    },
    {
        'name': 'Spring 事务配置生效诊断',
        'github_issue': '#764',
        'product_stage': 'M1',
        'category': 'spring',
        'script': 'sc -d ${TX_CLASS:-*Service}\ntrace ${TX_CLASS:-*Service} ${TX_METHOD:-*}\nwatch ${TX_CLASS:-*Service} ${TX_METHOD:-*} "{params,returnObj,throwExp}" -x 2 -n 3',
        'description': '组合 sc/trace/watch 验证事务代理、超时和传播行为是否生效。',
    },
    {
        'name': 'Logger 动态日志级别调整',
        'github_issue': '#849',
        'product_stage': 'M1',
        'category': 'logging',
        'script': 'logger\nlogger --name ${LOGGER_NAME:-root} --level ${LEVEL:-DEBUG}',
        'description': '在线查看和调整 logger 级别，排查完成后可恢复。',
    },
    {
        'name': 'Heapdump 内存快照工具',
        'github_issue': '#849',
        'product_stage': 'M1',
        'category': 'memory',
        'script': 'heapdump ${DUMP_PATH:-/tmp/arthas-heapdump.hprof}',
        'description': '生成 heapdump，并与文件下载服务组合导出分析。',
    },
    {
        'name': 'VMOption 运行时参数查看',
        'github_issue': '#849',
        'product_stage': 'M1',
        'category': 'jvm',
        'script': 'vmoption\nvmoption ${OPTION_NAME:-PrintGC} ${OPTION_VALUE:-true}',
        'description': '查看/调整 HotSpot Diagnostic Options，附带风险提示。',
    },
    {
        'name': 'ClassLoader 类冲突排查',
        'github_issue': '#763/#1003',
        'product_stage': 'M1',
        'category': 'classloader',
        'script': 'sc -d ${CLASS_NAME:-com.example.Demo}\nclassloader -t\njad --source-only ${CLASS_NAME:-com.example.Demo}',
        'description': '定位类来源、ClassLoader hash、线上实际字节码和源码差异。',
    },
    {
        'name': '在线反编译 jad',
        'github_issue': '#763/#1003',
        'product_stage': 'M1',
        'category': 'decompile',
        'script': 'jad --source-only ${CLASS_NAME:-com.example.Demo}',
        'description': '在线反编译类字节码为 Java 源码，用于查看线上实际代码。',
    },
    {
        'name': 'CPU 火焰图',
        'github_issue': '#1202/#569',
        'product_stage': 'M1',
        'category': 'profiler',
        'script': 'profiler start --event cpu --duration ${DURATION:-30}\nprofiler stop --format html\nprofiler getSamples',
        'description': '生成 CPU 火焰图，可视化热点方法和调用栈。',
    },
    {
        'name': 'Spectre 热替换工作台',
        'github_issue': 'spectre/retransform.png',
        'product_stage': 'M2',
        'category': 'hotfix',
        'script': 'sc -d ${CLASS_NAME}\njad --source-only ${CLASS_NAME}\nmc --classLoaderHash ${CLASS_LOADER_HASH} ${JAVA_FILE} -d /tmp/arthas-classes\nretransform ${CLASS_FILE}',
        'description': '借鉴 spectre，把 jad → 编辑 → mc → retransform 封装为热替换工作台。',
    },
]


def _now_text() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _json_dumps(data: Any) -> str:
    return json.dumps(data if data is not None else {}, ensure_ascii=False)


def _json_loads(text: Optional[str], default: Any = None) -> Any:
    if not text:
        return {} if default is None else default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        log.warning('JSON 解析失败: %s (input=%s...)', exc, str(text)[:80])
        return {} if default is None else default


def _row_to_task(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item['params'] = _json_loads(item.pop('params_json', None), {})
    item['target'] = _json_loads(item.pop('target_json', None), {})
    item['has_inline_script'] = bool(item.get('script_body'))
    item.pop('script_body', None)
    return item


def _row_to_template(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item['parameters_schema'] = _json_loads(item.get('parameters_schema'), {})
    return item


def _row_to_tool_package(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item['is_builtin'] = bool(item.get('is_builtin'))
    item['file_size'] = item.get('file_size') or 0
    item['template_count'] = item.get('template_count') or 0
    return item


def _normalize_tool_type(value: Any) -> str:
    tool_type = (value or 'generic').strip().lower()
    return tool_type if tool_type in _TOOL_TYPES else 'generic'


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_tool_file_path(tool_row: Dict[str, Any]) -> Optional[Path]:
    """解析工具包本地文件路径，兼容历史内置 Arthas 记录。"""
    file_path = tool_row.get('file_path') or ''
    path = Path(file_path) if file_path else None
    if path and path.exists():
        return path
    is_builtin_arthas = (
        bool(tool_row.get('is_builtin'))
        or tool_row.get('source_type') == 'builtin'
    ) and (
        tool_row.get('tool_type') == 'arthas'
        or tool_row.get('file_name') == 'arthas-boot.jar'
        or tool_row.get('name') == 'builtin-arthas-offline'
    )
    builtin_path = Path(_BUILTIN_ARTHAS_PATH)
    if is_builtin_arthas and builtin_path.exists():
        return builtin_path
    return path


def _validate_tool_install_path(value: Any) -> str:
    path = (value or '').strip() or _DEFAULT_ARTHAS_INSTALL_PATH
    if not path.startswith('/'):
        raise ValueError('安装路径必须是 Pod 内绝对路径')
    if '..' in Path(path).parts or '\n' in path or '\r' in path or '\x00' in path:
        raise ValueError('安装路径包含非法字符')
    blocked = ('/etc', '/bin', '/sbin', '/usr/bin', '/usr/sbin', '/root', '/home', '/proc', '/sys', '/dev', '/var', '/boot', '/lib', '/lib64')
    if path in blocked or any(path.startswith(prefix + '/') for prefix in blocked):
        raise ValueError('安装路径不能位于系统敏感目录')
    return path


def _safe_pod_path(path: str) -> str:
    return shlex.quote(_validate_tool_install_path(path))


def _validate_java_source_filename(value: Any) -> str:
    name = secure_filename((value or '').strip())
    if not name or name != (value or '').strip() or '/' in name or '\\' in name:
        raise ValueError('Java 源码文件名不合法')
    if not name.endswith('.java'):
        raise ValueError('仅支持上传 .java 源码文件')
    return name


def _row_to_run(row: Dict[str, Any], include_logs: bool = False) -> Dict[str, Any]:
    item = dict(row)
    item['target'] = _json_loads(item.pop('target_json', None), {})
    if not include_logs:
        item.pop('stdout', None)
        item.pop('stderr', None)
    return item


def _row_to_schedule(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item['schedule_config'] = _json_loads(item.pop('schedule_config_json', None), {})
    return item


def _error(message: str, status: int = 400):
    return jsonify({'error': message}), status


def _normalize_timeout(value: Any) -> int:
    try:
        timeout = int(value or _DEFAULT_TIMEOUT_SECONDS)
    except Exception:
        timeout = _DEFAULT_TIMEOUT_SECONDS
    return max(1, min(timeout, _MAX_TIMEOUT_SECONDS))


def _normalize_schedule_interval(value: Any) -> int:
    try:
        seconds = int(value or _MIN_INTERVAL_SECONDS)
    except Exception:
        seconds = _MIN_INTERVAL_SECONDS
    return max(_MIN_INTERVAL_SECONDS, min(seconds, _MAX_INTERVAL_SECONDS))


def _parse_time_text(value: Optional[str]) -> datetime:
    if value:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return datetime.now()


def _compute_next_run_at(interval_seconds: Any, from_time: Optional[str] = None) -> str:
    base = _parse_time_text(from_time)
    next_time = base + timedelta(seconds=_normalize_schedule_interval(interval_seconds))
    return next_time.strftime('%Y-%m-%d %H:%M:%S')


def _validate_runtime(runtime: str) -> Optional[str]:
    runtime = (runtime or '').strip().lower()
    return runtime if runtime in _ALLOWED_RUNTIMES else None


def _validate_execution_mode(mode: str) -> Optional[str]:
    mode = (mode or '').strip().lower()
    return mode if mode in _ALLOWED_EXECUTION_MODES else None


def _validate_pod_target(target: Any) -> Dict[str, str]:
    if not isinstance(target, dict):
        raise ValueError('Pod 执行目标格式不正确')

    normalized = {
        'cluster_name': (target.get('cluster_name') or target.get('cluster') or '').strip(),
        'namespace': (target.get('namespace') or 'default').strip(),
        'pod_name': (target.get('pod_name') or target.get('pod') or '').strip(),
        'container': (target.get('container') or '').strip(),
    }
    if not normalized['cluster_name']:
        raise ValueError('Pod 执行目标缺少集群')
    if not normalized['pod_name']:
        raise ValueError('Pod 执行目标缺少 Pod 名称')
    return normalized


def _get_template(template_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if not template_id:
        return None
    return db.fetch_one('SELECT * FROM script_templates WHERE id = ?', (template_id,))


def _resolve_task_script(task: Dict[str, Any]) -> tuple[str, str, int]:
    """返回 runtime, script_body, timeout_seconds。"""
    template = _get_template(task.get('template_id'))
    runtime = _validate_runtime(task.get('runtime') or (template or {}).get('runtime'))
    if not runtime:
        raise ValueError('脚本运行时不支持，仅支持 python / shell')

    script_body = (task.get('script_body') or '').strip()
    if not script_body and template:
        script_body = (template.get('script_body') or '').strip()
    if not script_body:
        raise ValueError('任务没有可执行脚本内容')

    timeout = _normalize_timeout(task.get('timeout_seconds') or (template or {}).get('default_timeout'))
    return runtime, script_body, timeout


def _write_script_file(run_dir: Path, runtime: str, script_body: str) -> Path:
    suffix = '.py' if runtime == 'python' else '.sh'
    script_path = run_dir / f'script{suffix}'
    script_path.write_text(script_body, encoding='utf-8', newline='\n')
    if os.name != 'nt':
        script_path.chmod(0o700)
    return script_path


def _build_command(runtime: str, script_path: Path) -> list[str]:
    if runtime == 'python':
        return [sys.executable, str(script_path)]

    if os.name == 'nt':
        bash = shutil.which('bash')
        if bash:
            return [bash, str(script_path)]
        raise RuntimeError('当前 Windows 环境未找到 bash，shell 脚本请在 Linux 节点执行，或改用 python 运行时')

    shell = shutil.which('sh') or '/bin/sh'
    return [shell, str(script_path)]


def _run_node_task(run_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
    runtime, script_body, timeout = _resolve_task_script(task)
    run_dir = (_OUTPUT_ROOT / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = _write_script_file(run_dir, runtime, script_body)
    command = _build_command(runtime, script_path)

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            encoding='utf-8',
            errors='replace',
        )
        duration_ms = int((time.time() - started) * 1000)
        status = 'success' if completed.returncode == 0 else 'failed'
        return {
            'status': status,
            'stdout': completed.stdout[-200000:],
            'stderr': completed.stderr[-200000:],
            'exit_code': completed.returncode,
            'duration_ms': duration_ms,
            'error_message': '' if completed.returncode == 0 else f'进程退出码 {completed.returncode}',
            'work_dir': str(run_dir),
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.time() - started) * 1000)
        return {
            'status': 'timeout',
            'stdout': (exc.stdout or '')[-200000:] if isinstance(exc.stdout, str) else '',
            'stderr': (exc.stderr or '')[-200000:] if isinstance(exc.stderr, str) else '',
            'exit_code': -1,
            'duration_ms': duration_ms,
            'error_message': f'执行超时，超过 {timeout} 秒',
            'work_dir': str(run_dir),
        }


def _get_cluster_config(cluster_name: str) -> Dict[str, str]:
    """复用 server.py 的集群配置和用户权限校验逻辑，避免在任务中心重复维护集群权限。"""
    from backend.app_context import load_clusters

    clusters = load_clusters()
    cluster = next((c for c in clusters if c.get('name') == cluster_name), None)
    if not cluster:
        raise ValueError('集群不存在')

    if not current_user.is_admin:
        user_clusters = db.fetch_all(
            'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
            (current_user.id,)
        )
        allowed = {r['cluster_id'] for r in user_clusters}
        if cluster.get('id') not in allowed:
            raise ValueError('无权访问此集群')
    return cluster


def _build_pod_shell_command(runtime: str, script_body: str) -> str:
    encoded = base64.b64encode(script_body.encode('utf-8')).decode('ascii')
    if runtime == 'python':
        script_path = f'/tmp/task-center-{uuid.uuid4().hex}.py'
        interpreter = 'python3'
    else:
        script_path = f'/tmp/task-center-{uuid.uuid4().hex}.sh'
        interpreter = 'sh'

    quoted_path = shlex.quote(script_path)
    quoted_interpreter = shlex.quote(interpreter)
    return (
        f"cat <<'TASK_CENTER_B64' | base64 -d > {quoted_path}\n"
        f"{encoded}\n"
        f"TASK_CENTER_B64\n"
        f"chmod 700 {quoted_path} 2>/dev/null || true\n"
        f"{quoted_interpreter} {quoted_path}\n"
        f"rc=$?\n"
        f"rm -f {quoted_path}\n"
        f"exit $rc"
    )


def _run_pod_task(run_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
    runtime, script_body, timeout = _resolve_task_script(task)
    target = _validate_pod_target(_json_loads(task.get('target_json'), {}))
    cluster = _get_cluster_config(target['cluster_name'])
    auth_err, auth_code = AuthorizationService.require_namespace_access(
        current_user, target['cluster_name'], target['namespace'])
    if auth_err:
        raise ValueError(auth_err['error'])

    from backend import KubectlExecutor

    runner = KubectlExecutor(kubeconfig=cluster.get('kubeconfig', ''), context=cluster.get('context', ''))
    shell_cmd = _build_pod_shell_command(runtime, script_body)
    started = time.time()
    rc, stdout, stderr = runner.exec_pod(
        target['namespace'],
        target['pod_name'],
        target['container'],
        shell_cmd,
        timeout=timeout,
    )
    duration_ms = int((time.time() - started) * 1000)
    timeout_hit = rc == -1 and '超时' in (stderr or '')
    status = 'timeout' if timeout_hit else ('success' if rc == 0 else 'failed')
    target_text = f"{target['cluster_name']}/{target['namespace']}/{target['pod_name']}"
    if target.get('container'):
        target_text += f"/{target['container']}"
    return {
        'status': status,
        'stdout': (stdout or '')[-200000:],
        'stderr': (stderr or '')[-200000:],
        'exit_code': rc,
        'duration_ms': duration_ms,
        'error_message': '' if rc == 0 else (stderr or stdout or f'Pod 命令退出码 {rc}')[:1000],
        'work_dir': f'pod://{target_text}',
    }


def _execute_task(run_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
    mode = task.get('execution_mode') or 'node'
    if mode == 'node':
        return _run_node_task(run_id, task)
    if mode == 'pod':
        return _run_pod_task(run_id, task)
    raise ValueError('执行位置仅支持 node / pod')


def _task_result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'stdout': result.get('stdout', ''),
        'stderr': result.get('stderr', ''),
        'exit_code': result.get('exit_code'),
        'work_dir': result.get('work_dir', ''),
    }


def _create_run_record(task: Dict[str, Any], user_id: int, execution_mode: str = 'manual') -> str:
    run_id = uuid.uuid4().hex
    db.insert('task_logs', {
        'id': run_id,
        'task_id': task.get('id'),
        'user_id': user_id,
        'status': 'running',
        'execution_mode': execution_mode,
        'execution_type': 'script',
        'run_type': 'script',
        'target_json': task.get('target_json') or '{}',
        'params_json': task.get('params_json') or '{}',
        'capability_name': task.get('name'),
        'rendered_command': task.get('script_body') or '',
        'started_at': _now_text(),
    })
    return run_id


def _finish_run_record(run_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    current = db.fetch_one('SELECT status FROM task_logs WHERE id = ?', (run_id,))
    if current and current.get('status') == 'cancelled':
        return db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))
    db.update('task_logs', {
        'status': result['status'],
        'stdout': result['stdout'],
        'stderr': result['stderr'],
        'exit_code': result['exit_code'],
        'duration_ms': result['duration_ms'],
        'result_json': _json_dumps(_task_result_payload(result)),
        'finished_at': _now_text(),
        'error_message': result['error_message'],
        'work_dir': result['work_dir'],
    }, 'id = ?', (run_id,))
    return db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))


def _execute_task_definition(task: Dict[str, Any], user_id: int, execution_mode: str = 'manual') -> Dict[str, Any]:
    run_id = _create_run_record(task, user_id, execution_mode)
    try:
        result = _execute_task(run_id, task)
    except Exception as exc:
        result = {
            'status': 'failed',
            'stdout': '',
            'stderr': '',
            'exit_code': -1,
            'duration_ms': 0,
            'error_message': str(exc),
            'work_dir': '',
        }
    run_record = _finish_run_record(run_id, result)

    # 审计日志
    task_name = task.get('name', '')
    target = _json_loads(task.get('target_json'), {})
    target_str = f"{target.get('cluster_name', '')}/{target.get('namespace', '')}/{target.get('pod_name', '')}" if target else ''
    AuditService.log_task_executed(
        user_id, task.get('id', 0), task_name,
        execution_mode, target_str, run_record.get('status', 'unknown')
    )

    return run_record


def _create_failed_task_log(task_id: Optional[int], user_id: int, execution_mode: str, error_message: str) -> str:
    run_id = uuid.uuid4().hex
    db.insert('task_logs', {
        'id': run_id,
        'task_id': task_id,
        'user_id': user_id,
        'status': 'failed',
        'execution_mode': execution_mode,
        'execution_type': 'script',
        'run_type': 'script',
        'target_json': '{}',
        'params_json': '{}',
        'result_json': _json_dumps({'error': error_message}),
        'started_at': _now_text(),
        'finished_at': _now_text(),
        'error_message': error_message,
    })
    return run_id


def _seed_default_templates(conn):
    conn.execute(
        '''
        INSERT OR IGNORE INTO tool_packages (
            name, description, source_type, tool_type, file_path, file_name,
            file_size, sha256, install_path, is_builtin, status, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'builtin', '系统内置工具包，用于任务中心最小闭环验证', 'builtin', 'generic',
            '', '', 0, '', '', 1, 'active', None
        )
    )
    conn.execute(
        '''
        INSERT OR IGNORE INTO tool_packages (
            name, description, source_type, tool_type, file_path, file_name,
            file_size, sha256, install_path, is_builtin, status, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'builtin-arthas-offline',
            '系统内置 Arthas 离线工具。Pod 未预装 Arthas 时，可从这里分发 arthas-boot.jar。',
            'builtin',
            'arthas',
            _BUILTIN_ARTHAS_PATH,
            'arthas-boot.jar',
            0,
            '',
            _DEFAULT_ARTHAS_INSTALL_PATH,
            1,
            'active' if Path(_BUILTIN_ARTHAS_PATH).exists() else 'inactive',
            None,
        )
    )

    package_id = conn.execute('SELECT id FROM tool_packages WHERE name = ?', ('builtin',)).fetchone()[0]
    arthas_package_id = conn.execute('SELECT id FROM tool_packages WHERE name = ?', ('builtin-arthas-offline',)).fetchone()[0]
    
    # ✅ 停用旧版种子数据（全新架构无需兼容）
    # 旧版：15 个 user-case 脚本模板 + Arthas 工具脚本
    # 新版：脚本模板由用户手动创建，关联 diagnosis_capabilities
    if False:  # 永久停用旧版种子数据
        pass
    if conn.execute('SELECT COUNT(*) FROM script_templates').fetchone()[0] == 0:
        script = '''#!/usr/bin/env python3
import os
import platform
import sys
from datetime import datetime

print("任务中心 Node 本机执行检查")
print("time=", datetime.now().isoformat(timespec="seconds"))
print("python=", sys.version.split()[0])
print("platform=", platform.platform())
print("cwd=", os.getcwd())
'''.strip()
        conn.execute(
            '''
            INSERT INTO script_templates (
                name, runtime, script_body, default_timeout, description,
                parameters_schema, tool_package_id, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                'Node 本机环境检查', 'python', script, 30,
                '内置 Python 脚本，用于验证 Node 本机执行器、日志采集和执行记录闭环。',
                '{}', package_id, None,
            )
        )

    arthas_check_script = '''#!/bin/sh
set -eu
ARTHAS_JAR="${ARTHAS_JAR:-/tmp/arthas/arthas-boot.jar}"
echo "Arthas offline jar path: $ARTHAS_JAR"
if [ -f "$ARTHAS_JAR" ]; then
  ls -lh "$ARTHAS_JAR"
  echo "OK: arthas jar exists"
else
  echo "MISS: arthas jar not found"
  exit 2
fi
'''.strip()
    conn.execute(
        '''
        INSERT OR IGNORE INTO script_templates (
            name, runtime, script_body, default_timeout, description,
            parameters_schema, tool_package_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'Pod 内 Arthas JAR 检查', 'shell', arthas_check_script, 30,
            '检查 Pod 内指定路径是否已分发 arthas-boot.jar。',
            '{}', arthas_package_id, None,
        )
    )

    arthas_start_script = '''#!/bin/sh
set -eu
ARTHAS_JAR="${ARTHAS_JAR:-/tmp/arthas/arthas-boot.jar}"
echo "Use Arthas jar: $ARTHAS_JAR"
if [ ! -f "$ARTHAS_JAR" ]; then
  echo "Arthas jar not found, please distribute it from Toolchain first."
  exit 2
fi
java -jar "$ARTHAS_JAR" --help | head -80
'''.strip()
    conn.execute(
        '''
        INSERT OR IGNORE INTO script_templates (
            name, runtime, script_body, default_timeout, description,
            parameters_schema, tool_package_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'Pod 内 Arthas 快速启动脚本', 'shell', arthas_start_script, 60,
            '验证 Pod 内 Arthas JAR 可被 Java 启动；真正诊断连接仍走现有 Arthas 连接流程。',
            '{}', arthas_package_id, None,
        )
    )

    retransform_workflow_script = '''#!/bin/sh
set -eu
CLASS_NAME="${CLASS_NAME:-com.example.DemoService}"
SOURCE_DIR="${SOURCE_DIR:-/tmp/arthas-sources}"
CLASS_DIR="${CLASS_DIR:-/tmp/arthas-classes}"
echo "1) jad --source-only $CLASS_NAME > $SOURCE_DIR/${CLASS_NAME##*.}.java"
echo "2) edit source or upload replacement .java from Toolchain"
echo "3) mc -d $CLASS_DIR $SOURCE_DIR/${CLASS_NAME##*.}.java"
echo "4) retransform $CLASS_DIR/${CLASS_NAME//./\\/}.class"
echo "Arthas commands: jad --source-only, mc, retransform"
'''.strip()
    conn.execute(
        '''
        INSERT OR IGNORE INTO script_templates (
            name, runtime, script_body, default_timeout, description,
            parameters_schema, tool_package_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'Arthas jad/retransform 热更新工作流', 'shell', retransform_workflow_script, 60,
            '规划 jad 反编译、源码修改、mc 编译和 retransform 生效的热更新步骤。',
            '{}', arthas_package_id, None,
        )
    )

    source_override_script = '''#!/bin/sh
set -eu
SOURCE_DIR="${SOURCE_DIR:-/tmp/arthas-sources}"
CLASS_DIR="${CLASS_DIR:-/tmp/arthas-classes}"
JAVA_FILE="${JAVA_FILE:-Demo.java}"
CLASS_FILE="${CLASS_FILE:-}"
mkdir -p "$SOURCE_DIR" "$CLASS_DIR"
echo "Uploaded source should be placed at $SOURCE_DIR/$JAVA_FILE"
echo "Compile: mc -d $CLASS_DIR $SOURCE_DIR/$JAVA_FILE"
echo "Apply: retransform ${CLASS_FILE:-$CLASS_DIR/<package>/<Class>.class}"
'''.strip()
    conn.execute(
        '''
        INSERT OR IGNORE INTO script_templates (
            name, runtime, script_body, default_timeout, description,
            parameters_schema, tool_package_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'Arthas 上传源码覆盖并 retransform', 'shell', source_override_script, 60,
            '配合工具链源码上传，把修改后的 .java 放入 Pod 后使用 mc + retransform 生效。',
            '{}', arthas_package_id, None,
        )
    )

    file_server_script = '''#!/bin/sh
set -eu
SERVE_DIR="${SERVE_DIR:-/tmp/arthas-share}"
PORT="${PORT:-18080}"
mkdir -p "$SERVE_DIR"
echo "Starting Python file server: http://0.0.0.0:$PORT/"
echo "Put files into $SERVE_DIR, then use kubectl port-forward to expose the URL."
cd "$SERVE_DIR"
python3 -m http.server "$PORT" --bind 0.0.0.0
'''.strip()
    conn.execute(
        '''
        INSERT OR IGNORE INTO script_templates (
            name, runtime, script_body, default_timeout, description,
            parameters_schema, tool_package_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'Pod Python 文件下载服务', 'shell', file_server_script, 3600,
            '在 Pod 内启动 python3 -m http.server，快速暴露文件下载 URL。',
            '{}', arthas_package_id, None,
        )
    )
    for capability in _USER_CASE_CAPABILITIES:
        conn.execute(
            '''
            INSERT OR IGNORE INTO script_templates (
                name, runtime, script_body, default_timeout, description,
                parameters_schema, tool_package_id, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                capability['name'], 'shell', capability['script'], 120,
                capability['description'],
                _json_dumps({
                    'github_issue': capability['github_issue'],
                    'product_stage': capability['product_stage'],
                    'category': capability['category'],
                    'source': 'arthas user-case + spectre',
                }),
                arthas_package_id,
                None,
            )
        )


def init_task_tables():
    """初始化通用任务平台表结构。"""
    with db.connection() as conn:
        cursor = conn.cursor()
        from backend.core.diagnosis_capabilities import init_capabilities_table, init_skill_registry

        init_capabilities_table(conn)
        # Phase 7 T01: 初始化 skill_registry 内置 Skill（含 Profiler skills）
        init_skill_registry(conn)
        # Phase 7 T04: 初始化默认市场源
        try:
            from services.skill_marketplace import get_skill_marketplace
            mkt = get_skill_marketplace()
            existing = mkt.list_sources()
            if not existing:
                mkt.add_source(
                    name="K8s Arthas Tool 官方市场",
                    repo_url="https://github.com/k8s-arthas-tool/skill-marketplace"
                )
                log.info("Default marketplace source created")
        except Exception as e:
            log.warning("Failed to init default marketplace source: %s", e)
        for column, ddl in {
            'status': "ALTER TABLE diagnosis_capabilities ADD COLUMN status TEXT DEFAULT 'active'",
            'is_builtin': 'ALTER TABLE diagnosis_capabilities ADD COLUMN is_builtin INTEGER DEFAULT 1',
            'sort_order': 'ALTER TABLE diagnosis_capabilities ADD COLUMN sort_order INTEGER DEFAULT 0',
            'handler_key': 'ALTER TABLE diagnosis_capabilities ADD COLUMN handler_key TEXT',
        }.items():
            try:
                cursor.execute(f'SELECT {column} FROM diagnosis_capabilities LIMIT 1')
            except Exception:
                cursor.execute(ddl)
        # tool_packages 表由 models/db.py 统一创建，此处不重复

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS script_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                runtime TEXT NOT NULL DEFAULT 'python',
                script_body TEXT NOT NULL,
                default_timeout INTEGER DEFAULT 60,
                description TEXT,
                parameters_schema TEXT DEFAULT '{}',
                tool_package_id INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tool_package_id) REFERENCES tool_packages(id) ON DELETE SET NULL,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        # 迁移: script_templates 扩展 capability_id
        try:
            cursor.execute('ALTER TABLE script_templates ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id)')
            log.info("Schema migrated: script_templates.capability_id added")
        except Exception:
            pass  # 列已存在

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                execution_mode TEXT NOT NULL DEFAULT 'node',
                template_id INTEGER,
                runtime TEXT,
                script_body TEXT,
                timeout_seconds INTEGER DEFAULT 60,
                params_json TEXT DEFAULT '{}',
                target_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'active',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (template_id) REFERENCES script_templates(id) ON DELETE SET NULL,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        # task_logs 表由 models/db.py 统一创建，此处只做增量列迁移
        for column, ddl in {
            'capability_id': 'ALTER TABLE task_logs ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id)',
            'execution_type': "ALTER TABLE task_logs ADD COLUMN execution_type TEXT DEFAULT 'script'",
            'run_type': "ALTER TABLE task_logs ADD COLUMN run_type TEXT DEFAULT 'script'",
            'params_json': "ALTER TABLE task_logs ADD COLUMN params_json TEXT DEFAULT '{}'",
            'result_json': 'ALTER TABLE task_logs ADD COLUMN result_json TEXT',
            'stdout': 'ALTER TABLE task_logs ADD COLUMN stdout TEXT',
            'stderr': 'ALTER TABLE task_logs ADD COLUMN stderr TEXT',
            'exit_code': 'ALTER TABLE task_logs ADD COLUMN exit_code INTEGER',
            'work_dir': 'ALTER TABLE task_logs ADD COLUMN work_dir TEXT',
            'capability_name': 'ALTER TABLE task_logs ADD COLUMN capability_name TEXT',
            'capability_version': 'ALTER TABLE task_logs ADD COLUMN capability_version INTEGER',
            'rendered_command': 'ALTER TABLE task_logs ADD COLUMN rendered_command TEXT',
            'connection_snapshot_json': 'ALTER TABLE task_logs ADD COLUMN connection_snapshot_json TEXT',
            'capability_snapshot_json': 'ALTER TABLE task_logs ADD COLUMN capability_snapshot_json TEXT',
            'log_path': 'ALTER TABLE task_logs ADD COLUMN log_path TEXT',
            'retention_days': 'ALTER TABLE task_logs ADD COLUMN retention_days INTEGER DEFAULT 30',
            'is_archived': 'ALTER TABLE task_logs ADD COLUMN is_archived INTEGER DEFAULT 0',
        }.items():
            try:
                cursor.execute(f'SELECT {column} FROM task_logs LIMIT 1')
            except Exception:
                cursor.execute(ddl)
        # task_artifacts 表已移除（空壳表，无 INSERT 操作）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_package_distributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                package_id INTEGER NOT NULL,
                user_id INTEGER,
                target_cluster TEXT NOT NULL,
                target_namespace TEXT NOT NULL,
                target_pod TEXT NOT NULL,
                target_container TEXT,
                install_path TEXT NOT NULL,
                local_sha256 TEXT,
                pod_sha256 TEXT,
                pod_file_size TEXT,
                pod_check_status TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                stderr TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (package_id) REFERENCES tool_packages(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_distributions_package
            ON tool_package_distributions(package_id, created_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_distributions_user
            ON tool_package_distributions(user_id, created_at DESC)
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_logs_user_created ON task_logs(user_id, created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_logs_task_created ON task_logs(task_id, created_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_logs_status_started ON task_logs(status, started_at DESC)')
        # 复合索引：step_logs 按 run_id + step_number 排序（替代单列 run_id 索引）
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_step_logs_run_step ON step_logs(run_id, step_number)')
        # 复合索引：能力目录按 level + category 排序
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_diag_caps_level_category ON diagnosis_capabilities(level, category, id)')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                user_id INTEGER,
                name TEXT NOT NULL,
                schedule_type TEXT NOT NULL DEFAULT 'interval',
                interval_seconds INTEGER NOT NULL DEFAULT 3600,
                schedule_config_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'active',
                last_run_at TIMESTAMP,
                next_run_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES task_definitions(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        for column, ddl in {
            'tool_type': "ALTER TABLE tool_packages ADD COLUMN tool_type TEXT DEFAULT 'generic'",
            'file_path': 'ALTER TABLE tool_packages ADD COLUMN file_path TEXT',
            'file_name': 'ALTER TABLE tool_packages ADD COLUMN file_name TEXT',
            'file_size': 'ALTER TABLE tool_packages ADD COLUMN file_size INTEGER DEFAULT 0',
            'sha256': 'ALTER TABLE tool_packages ADD COLUMN sha256 TEXT',
            'install_path': 'ALTER TABLE tool_packages ADD COLUMN install_path TEXT',
            'is_builtin': 'ALTER TABLE tool_packages ADD COLUMN is_builtin INTEGER DEFAULT 0',
            'last_verified_at': 'ALTER TABLE tool_packages ADD COLUMN last_verified_at TIMESTAMP',
        }.items():
            try:
                cursor.execute(f'SELECT {column} FROM tool_packages LIMIT 1')
            except Exception:
                cursor.execute(ddl)
        _seed_default_templates(conn)


@task_bp.route('/overview', methods=['GET'])
@login_required
def overview():
    run_where = "user_id = ? AND execution_type = 'script'"
    return jsonify({
        'templates': db.count('script_templates'),
        'tasks': db.count('task_definitions', 'created_by = ?', (current_user.id,)),
        'runs': db.count('task_logs', run_where, (current_user.id,)),
        'running': db.count('task_logs', run_where + ' AND status = ?', (current_user.id, 'running')),
        'schedules': db.count('task_schedules', 'user_id = ?', (current_user.id,)),
    })


@task_bp.route('/tool-packages', methods=['GET'])
@login_required
def list_tool_packages():
    rows = db.fetch_all('''
        SELECT p.*, COUNT(t.id) AS template_count
        FROM tool_packages p
        LEFT JOIN script_templates t ON t.tool_package_id = p.id
        GROUP BY p.id
        ORDER BY p.is_builtin DESC, p.updated_at DESC, p.id DESC
    ''')
    return jsonify({'packages': [_row_to_tool_package(row) for row in rows]})


@task_bp.route('/tool-packages', methods=['POST'])
@login_required
def create_tool_package():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return _error('工具包名称不能为空')
    install_path = data.get('install_path') or (_DEFAULT_ARTHAS_INSTALL_PATH if data.get('tool_type') == 'arthas' else '')
    try:
        install_path = _validate_tool_install_path(install_path) if install_path else ''
    except ValueError as exc:
        return _error(str(exc))
    package_id = db.insert('tool_packages', {
        'name': name,
        'description': (data.get('description') or '').strip(),
        'source_type': (data.get('source_type') or 'local').strip(),
        'source_url': (data.get('source_url') or '').strip(),
        'version': (data.get('version') or '').strip(),
        'tool_type': _normalize_tool_type(data.get('tool_type')),
        'file_path': (data.get('file_path') or '').strip(),
        'file_name': (data.get('file_name') or '').strip(),
        'file_size': int(data.get('file_size') or 0),
        'sha256': (data.get('sha256') or '').strip(),
        'install_path': install_path,
        'is_builtin': 0,
        'status': (data.get('status') or 'active').strip(),
        'created_by': current_user.id,
    })
    return jsonify({'ok': True, 'id': package_id}), 201


@task_bp.route('/tool-packages/upload', methods=['POST'])
@login_required
def upload_tool_package():
    file = request.files.get('file')
    if not file or not file.filename:
        return _error('请选择要上传的离线工具文件')
    name = (request.form.get('name') or '').strip() or Path(file.filename).stem
    tool_type = _normalize_tool_type(request.form.get('tool_type') or 'arthas')
    try:
        install_path = _validate_tool_install_path(request.form.get('install_path') or _DEFAULT_ARTHAS_INSTALL_PATH)
    except ValueError as exc:
        return _error(str(exc))
    safe_name = secure_filename(file.filename) or f'tool-{uuid.uuid4().hex}'
    target_dir = _TOOL_PACKAGE_ROOT / tool_type
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f'{uuid.uuid4().hex}-{safe_name}'
    file.save(str(target_path))
    sha256 = _sha256_file(target_path)
    package_id = db.insert('tool_packages', {
        'name': name,
        'description': (request.form.get('description') or '').strip(),
        'source_type': 'upload',
        'version': (request.form.get('version') or '').strip(),
        'tool_type': tool_type,
        'file_path': str(target_path),
        'file_name': safe_name,
        'file_size': target_path.stat().st_size,
        'sha256': sha256,
        'install_path': install_path,
        'is_builtin': 0,
        'status': 'active',
        'last_verified_at': _now_text(),
        'created_by': current_user.id,
    })
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    # 审计日志
    AuditService.log_tool_package_uploaded(
        current_user.id, package_id, row.get('name', ''), tool_type
    )
    return jsonify({'ok': True, 'package': _row_to_tool_package(row)}), 201


@task_bp.route('/tool-packages/<int:package_id>', methods=['PUT'])
@login_required
def update_tool_package(package_id: int):
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    if not row:
        return _error('工具包不存在', 404)
    data = request.json or {}
    updates: Dict[str, Any] = {'updated_at': _now_text()}
    for key in ('name', 'description', 'source_url', 'version', 'status'):
        if key in data:
            updates[key] = (data.get(key) or '').strip()
    if 'tool_type' in data:
        updates['tool_type'] = _normalize_tool_type(data.get('tool_type'))
    if 'install_path' in data:
        try:
            updates['install_path'] = _validate_tool_install_path(data.get('install_path'))
        except ValueError as exc:
            return _error(str(exc))
    db.update('tool_packages', updates, 'id = ?', (package_id,))
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    return jsonify({'ok': True, 'package': _row_to_tool_package(row)})


@task_bp.route('/tool-packages/<int:package_id>', methods=['DELETE'])
@login_required
def delete_tool_package(package_id: int):
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    if not row:
        return _error('工具包不存在', 404)
    if row.get('is_builtin'):
        return _error('内置工具包不能删除')
    file_path = row.get('file_path') or ''
    if row.get('source_type') == 'upload' and file_path:
        try:
            path = Path(file_path)
            if path.exists() and _TOOL_PACKAGE_ROOT.resolve() in path.resolve().parents:
                path.unlink()
        except Exception:
            pass
    db.execute('DELETE FROM tool_packages WHERE id = ?', (package_id,))
    # 审计日志
    AuditService.log_tool_package_deleted(
        current_user.id, package_id, row.get('name', '')
    )
    return jsonify({'ok': True})


@task_bp.route('/tool-packages/<int:package_id>/verify', methods=['POST'])
@login_required
def verify_tool_package(package_id: int):
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    if not row:
        return _error('工具包不存在', 404)
    file_path = row.get('file_path') or ''
    path = Path(file_path) if file_path else None
    exists = bool(path and path.exists())
    result = {'exists': exists, 'file_size': 0, 'sha256': ''}
    status = 'missing'
    if exists and path:
        result['file_size'] = path.stat().st_size
        result['sha256'] = _sha256_file(path)
        status = 'active'
        db.update('tool_packages', {
            'file_size': result['file_size'],
            'sha256': result['sha256'],
            'status': status,
            'last_verified_at': _now_text(),
            'updated_at': _now_text(),
        }, 'id = ?', (package_id,))
    elif row.get('source_type') == 'builtin':
        db.update('tool_packages', {'status': 'inactive', 'updated_at': _now_text()}, 'id = ?', (package_id,))
    return jsonify({'ok': exists, 'result': result})


@task_bp.route('/tool-packages/<int:package_id>/distribute', methods=['POST'])
@login_required
def distribute_tool_package(package_id: int):
    """分发工具包到 Pod，并记录分发历史和校验结果。"""
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    if not row:
        return _error('工具包不存在', 404)
    if row.get('status') not in ('active', 'inactive'):
        return _error('工具包状态不可分发')

    data = request.json or {}
    try:
        target = _validate_pod_target(data)
        install_path = _validate_tool_install_path(
            data.get('install_path') or row.get('install_path') or _DEFAULT_ARTHAS_INSTALL_PATH
        )
    except ValueError as exc:
        return _error(str(exc))

    local_path = _resolve_tool_file_path(row)
    if not local_path or not local_path.exists():
        _record_tool_distribution(
            row, target, install_path, 'failed',
            f"工具文件不存在: {row.get('file_path') or ''}",
            row.get('file_path') or '',
        )
        return _error('离线工具文件不存在，请先上传或检查服务器内置路径', 404)
    if row.get('tool_type') == 'arthas' and not install_path.endswith('.jar'):
        return _error('Arthas 工具必须分发为 .jar 文件')

    # 计算本地文件 sha256
    local_sha256 = _sha256_file(local_path)

    cluster = _get_cluster_config(target['cluster_name'])
    auth_err, auth_code = AuthorizationService.require_namespace_access(
        current_user, target['cluster_name'], target['namespace'])
    if auth_err:
        return _error(auth_err['error'], auth_code)

    from backend import KubectlExecutor
    runner = KubectlExecutor(kubeconfig=cluster.get('kubeconfig', ''), context=cluster.get('context', ''))

    install_dir = str(Path(install_path).parent).replace('\\', '/')

    # 1. 创建目标目录
    rc_mkdir, out_mkdir, err_mkdir = runner.exec_pod(
        target['namespace'], target['pod_name'], target['container'],
        f'mkdir -p {_safe_pod_path(install_dir)}', timeout=30
    )
    if rc_mkdir != 0:
        _record_distribution(
            package_id, target, install_path, local_sha256,
            'failed', f'创建 Pod 目录失败: {err_mkdir or out_mkdir}',
            err_mkdir or '',
            package_name=row.get('name', '')
        )
        return _error(f'创建 Pod 目录失败: {err_mkdir or out_mkdir}', 500)

    # 2. 复制文件到 Pod
    rc_cp, out_cp, err_cp = runner.cp_to_pod(
        target['namespace'], target['pod_name'], target['container'],
        str(local_path), install_path
    )
    if rc_cp != 0:
        _record_distribution(
            package_id, target, install_path, local_sha256,
            'failed', f'分发文件失败: {err_cp or out_cp}',
            err_cp or '',
            package_name=row.get('name', '')
        )
        return _error(f'分发文件失败: {err_cp or out_cp}', 500)

    # 3. 校验 Pod 内文件
    rc_check, out_check, err_check = runner.exec_pod(
        target['namespace'], target['pod_name'], target['container'],
        f'ls -lh {_safe_pod_path(install_path)} && (sha256sum {_safe_pod_path(install_path)} 2>/dev/null || true)',
        timeout=30,
    )

    # 解析 Pod 校验结果
    pod_sha256 = ''
    pod_file_size = ''
    pod_check_status = 'unknown'
    if rc_check == 0 and out_check:
        lines = out_check.strip().split('\n')
        for line in lines:
            if 'sha256sum' in line.lower() or len(line.strip()) == 64:
                # 可能是 sha256 输出
                parts = line.strip().split()
                if len(parts) >= 1 and len(parts[0]) == 64:
                    pod_sha256 = parts[0]
                    pod_check_status = 'verified'
                    break
            if line and not line.startswith('ls '):
                pod_file_size = line
                pod_check_status = 'exists'

    # 记录分发历史
    distribution_status = 'success' if rc_check == 0 else 'failed'
    error_msg = '' if rc_check == 0 else (err_check or out_check or 'Pod 内文件校验失败')
    stderr = '\n'.join(x for x in (err_mkdir, err_cp, err_check) if x)

    _record_distribution(
        package_id, target, install_path, local_sha256,
        distribution_status, error_msg, stderr,
        pod_sha256, pod_file_size, pod_check_status,
        package_name=row.get('name', '')
    )

    # 审计日志已在 _record_distribution 中记录

    # 返回标准化结果
    return jsonify({
        'ok': rc_check == 0,
        'package_id': package_id,
        'target': target,
        'install_path': install_path,
        'local_sha256': local_sha256,
        'pod_sha256': pod_sha256,
        'pod_file_size': pod_file_size,
        'pod_check_status': pod_check_status,
        'sha256_match': local_sha256 == pod_sha256 if pod_sha256 else None,
        'stdout': '\n'.join(x for x in (out_mkdir, out_cp, out_check) if x),
        'stderr': stderr,
        'error_message': error_msg,
    })


def _record_distribution(
    package_id: int,
    target: Dict[str, str],
    install_path: str,
    local_sha256: str,
    status: str,
    error_message: str,
    stderr: str,
    pod_sha256: str = '',
    pod_file_size: str = '',
    pod_check_status: str = '',
    package_name: str = '',
) -> None:
    """记录工具包分发历史。"""
    try:
        db.insert('tool_package_distributions', {
            'package_id': package_id,
            'user_id': current_user.id,
            'target_cluster': target.get('cluster_name', ''),
            'target_namespace': target.get('namespace', ''),
            'target_pod': target.get('pod_name', ''),
            'target_container': target.get('container', ''),
            'install_path': install_path,
            'local_sha256': local_sha256,
            'pod_sha256': pod_sha256,
            'pod_file_size': pod_file_size,
            'pod_check_status': pod_check_status,
            'status': status,
            'error_message': error_message,
            'stderr': stderr,
        })

        # 审计日志
        target_str = f"{target.get('cluster_name', '')}/{target.get('namespace', '')}/{target.get('pod_name', '')}"
        AuditService.log_tool_package_distributed(
            current_user.id, package_id, package_name or '',
            target_str, install_path, status
        )
    except Exception as exc:
        log.warning('记录分发历史失败: %s', exc)


def _record_tool_distribution(tool_row: Dict[str, Any], target: Dict[str, str], install_path: str,
                              status: str, error_message: str = '', stderr: str = '') -> None:
    """把工具分发结果统一写入分发历史。"""
    local_sha256 = ''
    file_path = tool_row.get('file_path') or ''
    if file_path and Path(file_path).exists():
        local_sha256 = _sha256_file(Path(file_path))
    _record_distribution(
        int(tool_row.get('id') or 0),
        target,
        install_path,
        local_sha256,
        status,
        error_message,
        stderr,
        package_name=tool_row.get('name', ''),
    )


@task_bp.route('/tool-packages/distributions', methods=['GET'])
@login_required
def list_distributions():
    """查询工具包分发历史。"""
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    package_id = request.args.get('package_id', type=int)

    where_clauses = ['1=1']
    params = []

    if not getattr(current_user, 'is_admin', False):
        where_clauses.append('user_id = ?')
        params.append(current_user.id)

    if package_id:
        where_clauses.append('package_id = ?')
        params.append(package_id)

    where_sql = ' AND '.join(where_clauses)
    rows = db.fetch_all(
        f'''
        SELECT d.*,
               p.name AS package_name,
               p.tool_type AS package_tool_type
        FROM tool_package_distributions d
        LEFT JOIN tool_packages p ON p.id = d.package_id
        WHERE {where_sql}
        ORDER BY d.created_at DESC
        LIMIT ? OFFSET ?
        ''',
        tuple(params + [limit, offset])
    )

    distributions = []
    for row in rows:
        item = dict(row)
        distributions.append(item)

    return jsonify({
        'ok': True,
        'distributions': distributions,
        'count': len(distributions),
    })


@task_bp.route('/distributions/<int:dist_id>', methods=['GET'])
@login_required
def get_distribution_detail(dist_id):
    """获取单条分发记录详情"""
    row = db.fetch_one('SELECT * FROM tool_distributions WHERE id = ?', (dist_id,))
    if not row:
        return _error('记录不存在', 404)
    return jsonify({'ok': True, 'distribution': dict(row)})


@task_bp.route('/distributions/retry', methods=['POST'])
@login_required
def retry_distribution():
    """重试分发"""
    data = request.json or {}
    dist_id = data.get('dist_id')
    if not dist_id:
        return _error('缺少 dist_id')

    row = db.fetch_one('SELECT * FROM tool_distributions WHERE id = ?', (dist_id,))
    if not row:
        return _error('记录不存在', 404)

    tool_row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (row['tool_id'],))
    if not tool_row:
        return _error('工具不存在', 404)

    cluster = data.get('cluster') or row['target_cluster']
    namespace = data.get('namespace') or row['target_namespace']
    pod = data.get('pod') or row['target_pod']
    container = data.get('container') or row['target_container'] or ''
    install_path = data.get('install_path') or row['install_path']

    try:
        start_time = time.time()
        _do_distribute(tool_row, cluster, namespace, pod, container, install_path)
        duration_ms = int((time.time() - start_time) * 1000)
        db.insert('tool_distributions', {
            'tool_type': row['tool_type'],
            'tool_id': row['tool_id'],
            'tool_name': row['tool_name'],
            'target_cluster': cluster,
            'target_namespace': namespace,
            'target_pod': pod,
            'target_container': container,
            'install_path': install_path,
            'status': 'success',
            'duration_ms': duration_ms,
            'distributed_by': current_user.id if hasattr(current_user, 'id') else None,
        })
        return jsonify({'ok': True, 'duration_ms': duration_ms})
    except Exception as e:
        db.insert('tool_distributions', {
            'tool_type': row['tool_type'],
            'tool_id': row['tool_id'],
            'tool_name': row['tool_name'],
            'target_cluster': cluster,
            'target_namespace': namespace,
            'target_pod': pod,
            'target_container': container,
            'install_path': install_path,
            'status': 'failed',
            'error_message': str(e),
            'distributed_by': current_user.id if hasattr(current_user, 'id') else None,
        })
        return _error(f'重试失败: {e}', 500)


@task_bp.route('/distributions/batch-retry', methods=['POST'])
@login_required
def batch_retry_distributions():
    """批量重试分发"""
    data = request.json or {}
    dist_ids = data.get('dist_ids', [])
    if not dist_ids:
        return _error('缺少 dist_ids')

    results = []
    for dist_id in dist_ids:
        row = db.fetch_one('SELECT * FROM tool_distributions WHERE id = ?', (dist_id,))
        if not row:
            results.append({'id': dist_id, 'status': 'skipped', 'error': '记录不存在'})
            continue

        tool_row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (row['tool_id'],))
        if not tool_row:
            results.append({'id': dist_id, 'status': 'skipped', 'error': '工具不存在'})
            continue

        try:
            start_time = time.time()
            _do_distribute(tool_row, row['target_cluster'], row['target_namespace'],
                          row['target_pod'], row['target_container'] or '', row['install_path'])
            duration_ms = int((time.time() - start_time) * 1000)
            db.insert('tool_distributions', {
                'tool_type': row['tool_type'],
                'tool_id': row['tool_id'],
                'tool_name': row['tool_name'],
                'target_cluster': row['target_cluster'],
                'target_namespace': row['target_namespace'],
                'target_pod': row['target_pod'],
                'target_container': row['target_container'],
                'install_path': row['install_path'],
                'status': 'success',
                'duration_ms': duration_ms,
                'distributed_by': current_user.id if hasattr(current_user, 'id') else None,
            })
            results.append({'id': dist_id, 'status': 'success', 'duration_ms': duration_ms})
        except Exception as e:
            db.insert('tool_distributions', {
                'tool_type': row['tool_type'],
                'tool_id': row['tool_id'],
                'tool_name': row['tool_name'],
                'target_cluster': row['target_cluster'],
                'target_namespace': row['target_namespace'],
                'target_pod': row['target_pod'],
                'target_container': row['target_container'],
                'install_path': row['install_path'],
                'status': 'failed',
                'error_message': str(e),
                'distributed_by': current_user.id if hasattr(current_user, 'id') else None,
            })
            results.append({'id': dist_id, 'status': 'failed', 'error': str(e)})

    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    return jsonify({
        'ok': True,
        'results': results,
        'summary': {'success': success_count, 'failed': failed_count, 'total': len(results)}
    })


# ═══════════════════════════════════════════════════════════════════════════════
# 脚本工具 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/script-tools', methods=['GET'])
@login_required
def list_script_tools():
    """查询脚本工具列表"""
    runtime_filter = request.args.get('runtime')
    where_clauses = []
    params = []
    if runtime_filter:
        where_clauses.append('runtime = ?')
        params.append(runtime_filter)
    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
    rows = db.fetch_all(
        f'SELECT * FROM script_tools WHERE {where_sql} ORDER BY id DESC',
        tuple(params)
    )
    return jsonify({'tools': [dict(r) for r in rows]})


@task_bp.route('/script-tools', methods=['POST'])
@login_required
def create_script_tool():
    """创建脚本工具"""
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    script_body = data.get('script_body', '').strip()
    if not name or not script_body:
        return _error('名称和脚本内容不能为空')
    tool_id = db.insert('script_tools', {
        'name': name,
        'runtime': data.get('runtime', 'python'),
        'script_body': script_body,
        'risk_level': data.get('risk_level', 'low'),
        'parameters_schema': data.get('parameters_schema'),
        'capability_id': data.get('capability_id'),
        'description': data.get('description', ''),
        'created_by': current_user.id if hasattr(current_user, 'id') else None,
    })
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    return jsonify({'ok': True, 'tool': dict(row)}), 201


@task_bp.route('/script-tools/<int:tool_id>', methods=['PUT'])
@login_required
def update_script_tool(tool_id: int):
    """更新脚本工具"""
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    if not row:
        return _error('脚本工具不存在', 404)
    data = request.get_json(force=True)
    updates = {}
    for key in ('name', 'runtime', 'script_body', 'risk_level', 'parameters_schema', 'capability_id', 'description'):
        if key in data:
            updates[key] = data[key]
    if updates:
        updates['updated_at'] = _now_text()
        db.update('script_tools', updates, 'id = ?', (tool_id,))
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    return jsonify({'ok': True, 'tool': dict(row)})


@task_bp.route('/script-tools/<int:tool_id>', methods=['DELETE'])
@login_required
def delete_script_tool(tool_id: int):
    """删除脚本工具"""
    row = db.fetch_one('SELECT * FROM script_tools WHERE id = ?', (tool_id,))
    if not row:
        return _error('脚本工具不存在', 404)
    db.execute('DELETE FROM script_tools WHERE id = ?', (tool_id,))
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# 快捷操作 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/quick-actions', methods=['GET'])
@login_required
def list_quick_actions():
    """查询快捷操作列表"""
    category_filter = request.args.get('category')
    where_clauses = []
    params = []
    if category_filter:
        where_clauses.append('category = ?')
        params.append(category_filter)
    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
    rows = db.fetch_all(
        f'SELECT * FROM quick_actions WHERE {where_sql} ORDER BY category, id',
        tuple(params)
    )
    return jsonify({'actions': [dict(r) for r in rows]})


@task_bp.route('/quick-actions', methods=['POST'])
@login_required
def create_quick_action():
    """创建快捷操作"""
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    command_template = data.get('command_template', '').strip()
    if not name or not command_template:
        return _error('名称和命令模板不能为空')
    action_id = db.insert('quick_actions', {
        'name': name,
        'category': data.get('category'),
        'command_template': command_template,
        'risk_level': data.get('risk_level', 'low'),
        'parameters_schema': data.get('parameters_schema'),
        'description': data.get('description', ''),
        'arthas_doc_url': data.get('arthas_doc_url'),
        'created_by': current_user.id if hasattr(current_user, 'id') else None,
    })
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    return jsonify({'ok': True, 'action': dict(row)}), 201


@task_bp.route('/quick-actions/<int:action_id>', methods=['PUT'])
@login_required
def update_quick_action(action_id: int):
    """更新快捷操作"""
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    if not row:
        return _error('快捷操作不存在', 404)
    data = request.get_json(force=True)
    updates = {}
    for key in ('name', 'category', 'command_template', 'risk_level', 'parameters_schema', 'description', 'arthas_doc_url'):
        if key in data:
            updates[key] = data[key]
    if updates:
        updates['updated_at'] = _now_text()
        db.update('quick_actions', updates, 'id = ?', (action_id,))
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    return jsonify({'ok': True, 'action': dict(row)})


@task_bp.route('/quick-actions/<int:action_id>', methods=['DELETE'])
@login_required
def delete_quick_action(action_id: int):
    """删除快捷操作"""
    row = db.fetch_one('SELECT * FROM quick_actions WHERE id = ?', (action_id,))
    if not row:
        return _error('快捷操作不存在', 404)
    db.execute('DELETE FROM quick_actions WHERE id = ?', (action_id,))
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# Pod 能力检测 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/detect-capability', methods=['POST'])
@login_required
def detect_pod_capability():
    """检测 Pod 能力（Java/Go/Python，Arthas 状态）"""
    data = request.get_json(force=True)
    cluster = data.get('cluster')
    namespace = data.get('namespace', 'default')
    pod = data.get('pod')
    container = data.get('container', '')
    if not cluster or not pod:
        return _error('cluster 和 pod 不能为空')

    result = {
        'has_java': False,
        'java_version': None,
        'has_arthas': False,
        'arthas_version': None,
        'has_exec': True,
        'capability_level': 'unknown',
    }

    try:
        cmd_parts = ['kubectl', 'exec', '-n', namespace, pod]
        if container:
            cmd_parts.extend(['-c', container])
        cmd_parts.extend(['--', 'java', '-version'])

        proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            result['has_java'] = True
            version_match = re.search(r'"(\d+\.\d+\.\d+)', proc.stderr or proc.stdout)
            if version_match:
                result['java_version'] = version_match.group(1)

            arthas_paths = ['/app/arthas/arthas-boot.jar', '/opt/arthas/arthas-boot.jar',
                           '/arthas/arthas-boot.jar', '/home/admin/arthas-boot.jar']
            for arthas_path in arthas_paths:
                check_cmd = cmd_parts[:-3] + ['--', 'ls', '-la', arthas_path]
                check_proc = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
                if check_proc.returncode == 0 and 'arthas-boot.jar' in (check_proc.stdout or ''):
                    result['has_arthas'] = True
                    break
        elif 'exec' in (proc.stderr or '').lower() or 'forbidden' in (proc.stderr or '').lower():
            result['has_exec'] = False
    except subprocess.TimeoutExpired:
        result['has_exec'] = False
    except Exception as e:
        log.warning(f"能力检测失败: {e}")

    if result['has_java'] and result['has_arthas']:
        result['capability_level'] = 'pod+arthas'
    elif result['has_java']:
        result['capability_level'] = 'pod-only'
    elif result['has_exec']:
        result['capability_level'] = 'non-java'
    else:
        result['capability_level'] = 'no-exec'

    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 单工具分发 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/distribute', methods=['POST'])
@login_required
def distribute_single_tool():
    """分发单个工具到指定 Pod（前端 toolboxConfirmDistribute 调用）"""
    data = request.json or {}
    tool_id = data.get('tool_id')
    if not tool_id:
        return _error('缺少 tool_id')

    tool_row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (tool_id,))
    if not tool_row:
        return _error('工具不存在', 404)
    if tool_row.get('status') not in ('active', 'inactive'):
        return _error('工具状态不可分发')

    try:
        target = _validate_pod_target(data)
        install_path = _validate_tool_install_path(
            data.get('install_path') or tool_row.get('install_path') or _DEFAULT_ARTHAS_INSTALL_PATH
        )
    except ValueError as exc:
        return _error(str(exc))

    auth_err, auth_code = AuthorizationService.require_namespace_access(
        current_user, target['cluster_name'], target['namespace'])
    if auth_err:
        return _error(auth_err['error'], auth_code)
    dist_target = {
        'cluster_name': target['cluster_name'],
        'namespace': target['namespace'],
        'pod_name': target['pod_name'],
        'container': target['container'],
    }

    try:
        start_time = time.time()
        _do_distribute(tool_row, target['cluster_name'], target['namespace'],
                       target['pod_name'], target['container'], install_path)
        duration_ms = int((time.time() - start_time) * 1000)
        _record_tool_distribution(tool_row, dist_target, install_path, 'success')
        return jsonify({'ok': True, 'duration_ms': duration_ms})
    except Exception as e:
        _record_tool_distribution(tool_row, dist_target, install_path, 'failed', str(e), str(e))
        return _error(f'分发失败: {e}', 500)


# ═══════════════════════════════════════════════════════════════════════════════
# 批量分发 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/batch-distribute', methods=['POST'])
@login_required
def batch_distribute():
    """批量分发工具到多个 Pod"""
    data = request.get_json(force=True)
    tool_ids = data.get('tool_ids', [])
    tool_type = data.get('tool_type', 'binary')
    targets = data.get('targets', [])
    install_path = data.get('install_path', '/tmp/arthas/arthas-boot.jar')

    if not tool_ids or not targets:
        return _error('请选择工具和目标 Pod')

    batch_id = f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    results = []

    for tool_id in tool_ids:
        tool_row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (tool_id,))
        if not tool_row:
            continue
        tool_name = tool_row.get('name', f'tool-{tool_id}')

        for target in targets:
            cluster = target.get('cluster', '')
            namespace = target.get('namespace', 'default')
            pod = target.get('pod', '')
            container = target.get('container', '')
            dist_target = {
                'cluster_name': cluster,
                'namespace': namespace,
                'pod_name': pod,
                'container': container,
            }

            # 执行分发
            try:
                start_time = time.time()
                _do_distribute(tool_row, cluster, namespace, pod, container, install_path)
                duration_ms = int((time.time() - start_time) * 1000)
                _record_tool_distribution(tool_row, dist_target, install_path, 'success')
                results.append({
                    'tool': tool_name,
                    'pod': pod,
                    'status': 'success',
                    'duration_ms': duration_ms,
                })
            except Exception as e:
                _record_tool_distribution(tool_row, dist_target, install_path, 'failed', str(e), str(e))
                results.append({
                    'tool': tool_name,
                    'pod': pod,
                    'status': 'failed',
                    'error': str(e),
                })

    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = sum(1 for r in results if r['status'] == 'failed')

    return jsonify({
        'batch_id': batch_id,
        'total': len(results),
        'results': results,
        'summary': {
            'success': success_count,
            'failed': failed_count,
            'skipped': 0,
        }
    })


def _do_distribute(tool_row, cluster, namespace, pod, container, install_path):
    """执行单次分发（从现有 distribute 逻辑提取）"""
    local_path = _resolve_tool_file_path(tool_row)
    if not local_path or not local_path.exists():
        raise ValueError(f"工具文件不存在: {tool_row.get('file_path', '')}")

    cluster_cfg = _get_cluster_config(cluster)
    from backend import KubectlExecutor
    runner = KubectlExecutor(kubeconfig=cluster_cfg.get('kubeconfig', ''), context=cluster_cfg.get('context', ''))
    install_dir = str(Path(install_path).parent).replace('\\', '/')

    # 先在 Pod 内创建目录；kubectl cp 的目标只允许 pod:path 或 namespace/pod:path，不能拼接集群名。
    rc_mkdir, out_mkdir, err_mkdir = runner.exec_pod(
        namespace, pod, container,
        f'mkdir -p {_safe_pod_path(install_dir)}', timeout=30,
    )
    if rc_mkdir != 0:
        raise RuntimeError(f"创建 Pod 目录失败: {err_mkdir or out_mkdir}")

    rc_cp, out_cp, err_cp = runner.cp_to_pod(namespace, pod, container, str(local_path), install_path)
    if rc_cp != 0:
        raise RuntimeError(f"kubectl cp 失败: {err_cp or out_cp}")


@task_bp.route('/arthas/source-upload', methods=['POST'])
@login_required
def upload_arthas_source():
    file = request.files.get('file')
    if not file or not file.filename:
        return _error('请选择要上传的 Java 源码文件')
    try:
        filename = _validate_java_source_filename(file.filename)
        target = _validate_pod_target(request.form)
        source_dir = _validate_tool_install_path(request.form.get('source_dir') or '/tmp/arthas-sources')
    except ValueError as exc:
        return _error(str(exc))
    cluster = _get_cluster_config(target['cluster_name'])
    auth_err, auth_code = AuthorizationService.require_namespace_access(
        current_user, target['cluster_name'], target['namespace'])
    if auth_err:
        return _error(auth_err['error'], auth_code)
    tmp_dir = _TOOL_PACKAGE_ROOT / 'source_uploads'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local_path = tmp_dir / f'{uuid.uuid4().hex}-{filename}'
    file.save(str(local_path))
    from backend import KubectlExecutor
    runner = KubectlExecutor(kubeconfig=cluster.get('kubeconfig', ''), context=cluster.get('context', ''))
    pod_path = f"{source_dir.rstrip('/')}/{filename}"
    rc_mkdir, out_mkdir, err_mkdir = runner.exec_pod(
        target['namespace'], target['pod_name'], target['container'],
        f'mkdir -p {_safe_pod_path(source_dir)}', timeout=30
    )
    if rc_mkdir != 0:
        return _error(f'创建源码目录失败: {err_mkdir or out_mkdir}', 500)
    rc_cp, out_cp, err_cp = runner.cp_to_pod(
        target['namespace'], target['pod_name'], target['container'], str(local_path), pod_path
    )
    try:
        local_path.unlink()
    except Exception:
        pass
    if rc_cp != 0:
        return _error(f'上传源码到 Pod 失败: {err_cp or out_cp}', 500)
    return jsonify({
        'ok': True,
        'target': target,
        'source_path': pod_path,
        'next_steps': [
            f'jad --source-only <class> > {pod_path}',
            f'mc -d /tmp/arthas-classes {pod_path}',
            'retransform /tmp/arthas-classes/<package>/<Class>.class',
        ],
    })


@task_bp.route('/templates', methods=['GET'])
@login_required
def list_templates():
    rows = db.fetch_all('''
        SELECT t.*, p.name AS tool_package_name
        FROM script_templates t
        LEFT JOIN tool_packages p ON p.id = t.tool_package_id
        ORDER BY t.updated_at DESC, t.id DESC
    ''')
    return jsonify({'templates': [_row_to_template(row) for row in rows]})


@task_bp.route('/templates', methods=['POST'])
@login_required
def create_template():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    runtime = _validate_runtime(data.get('runtime') or 'python')
    script_body = (data.get('script_body') or '').strip()
    if not name:
        return _error('模板名称不能为空')
    if not runtime:
        return _error('运行时仅支持 python / shell')
    if not script_body:
        return _error('脚本内容不能为空')

    template_id = db.insert('script_templates', {
        'name': name,
        'runtime': runtime,
        'script_body': script_body,
        'default_timeout': _normalize_timeout(data.get('default_timeout')),
        'description': (data.get('description') or '').strip(),
        'parameters_schema': _json_dumps(data.get('parameters_schema') or {}),
        'tool_package_id': data.get('tool_package_id'),
        'created_by': current_user.id,
    })
    return jsonify({'ok': True, 'id': template_id}), 201


@task_bp.route('/definitions', methods=['GET'])
@login_required
def list_definitions():
    rows = db.fetch_all('''
        SELECT d.*, t.name AS template_name
        FROM task_definitions d
        LEFT JOIN script_templates t ON t.id = d.template_id
        WHERE d.created_by = ?
        ORDER BY d.updated_at DESC, d.id DESC
    ''', (current_user.id,))
    return jsonify({'tasks': [_row_to_task(row) for row in rows]})


@task_bp.route('/definitions', methods=['POST'])
@login_required
def create_definition():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    execution_mode = _validate_execution_mode(data.get('execution_mode') or 'node')
    runtime = _validate_runtime(data.get('runtime') or '') if data.get('runtime') else None
    template_id = data.get('template_id') or None
    script_body = (data.get('script_body') or '').strip()

    if not name:
        return _error('任务名称不能为空')
    if not execution_mode:
        return _error('执行位置仅支持 node / pod')
    # 安全限制：node 模式下在服务器本地执行脚本，仅限 admin
    if execution_mode == 'node' and not _is_admin_user():
        return _error('Node 本机执行仅限管理员', 403)
    if not template_id and not script_body:
        return _error('请选择脚本模板或填写内联脚本')
    try:
        target = _validate_pod_target(data.get('target') or {}) if execution_mode == 'pod' else {}
        if execution_mode == 'pod':
            auth_err, auth_code = AuthorizationService.require_namespace_access(
                current_user, target['cluster_name'], target['namespace'])
            if auth_err:
                return _error(auth_err['error'], auth_code)
    except ValueError as exc:
        return _error(str(exc))

    if template_id:
        template = _get_template(int(template_id))
        if not template:
            return _error('脚本模板不存在', 404)
        runtime = runtime or _validate_runtime(template.get('runtime'))

    if not runtime:
        return _error('运行时仅支持 python / shell')

    task_id = db.insert('task_definitions', {
        'name': name,
        'execution_mode': execution_mode,
        'template_id': template_id,
        'runtime': runtime,
        'script_body': script_body,
        'timeout_seconds': _normalize_timeout(data.get('timeout_seconds')),
        'params_json': _json_dumps(data.get('params') or {}),
        'target_json': _json_dumps(target),
        'status': 'active',
        'created_by': current_user.id,
    })
    return jsonify({'ok': True, 'id': task_id}), 201


@task_bp.route('/definitions/<int:task_id>/run', methods=['POST'])
@task_bp.route('/definitions/<int:task_id>/execute', methods=['POST'])
@login_required
def run_definition(task_id: int):
    task = db.fetch_one('SELECT * FROM task_definitions WHERE id = ? AND created_by = ?', (task_id, current_user.id))
    if not task:
        return _error('任务不存在或无权限', 404)
    if task.get('status') != 'active':
        return _error('任务不是 active 状态，不能执行')
    if not _validate_execution_mode(task.get('execution_mode') or 'node'):
        return _error('执行位置仅支持 node / pod')
    # 安全限制：node 模式下在服务器本地执行脚本，仅限 admin
    if task.get('execution_mode') == 'node' and not _is_admin_user():
        return _error('Node 本机执行仅限管理员', 403)

    run = _execute_task_definition(task, current_user.id)
    return jsonify({'ok': True, 'run': _row_to_run(run, include_logs=True)})


@task_bp.route('/definitions/<int:task_id>', methods=['DELETE'])
@login_required
def delete_definition(task_id: int):
    """删除任务定义，关联调度会级联删除。"""
    row = db.fetch_one(
        'SELECT * FROM task_definitions WHERE id = ? AND created_by = ?',
        (task_id, current_user.id)
    )
    if not row:
        return _error('任务不存在或无权限', 404)
    db.execute('DELETE FROM task_definitions WHERE id = ?', (task_id,))
    return jsonify({'ok': True})


@task_bp.route('/runs', methods=['GET'])
@login_required
def list_runs():
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    total = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM task_logs WHERE user_id = ? AND execution_type = 'script'",
        (current_user.id,)
    )
    rows = db.fetch_all('''
        SELECT r.*, d.name AS task_name
        FROM task_logs r
        LEFT JOIN task_definitions d ON d.id = r.task_id
        WHERE r.user_id = ? AND r.execution_type = 'script'
        ORDER BY r.created_at DESC
        LIMIT ? OFFSET ?
    ''', (current_user.id, limit, offset))
    return jsonify({
        'runs': [_row_to_run(row) for row in rows],
        'total': total['cnt'] if total else 0,
        'limit': limit,
        'offset': offset,
    })


@task_bp.route('/runs/<run_id>/logs', methods=['GET'])
@login_required
def get_run_logs(run_id: str):
    """查询执行记录详情。"""
    row = db.fetch_one('''
        SELECT t.*, d.name AS task_name, c.name AS capability_name, c.category AS capability_category
        FROM task_logs t
        LEFT JOIN task_definitions d ON d.id = t.task_id
        LEFT JOIN diagnosis_capabilities c ON c.id = t.capability_id
        WHERE t.id = ? AND t.user_id = ?
    ''', (run_id, current_user.id))
    if not row:
        return _error('执行记录不存在或无权限', 404)
    item = dict(row)
    item['task_name'] = item.get('task_name') or item.get('capability_name') or '即时诊断'
    item['target'] = _json_loads(item.pop('target_json', None), {})
    item['params'] = _json_loads(item.pop('params_json', None), {})
    item['result'] = _json_loads(item.pop('result_json', None), None)
    item['connection_snapshot'] = _json_loads(item.pop('connection_snapshot_json', None), {})
    item['capability_snapshot'] = _json_loads(item.pop('capability_snapshot_json', None), {})
    item['run_id'] = item.get('id')
    item['execution_id'] = item.get('id')
    return jsonify({'run': item})


@task_bp.route('/runs/<run_id>/cancel', methods=['POST'])
@login_required
def cancel_task_run(run_id: str):
    """取消诊断/任务执行记录。

    P0 阶段先做状态取消：running/pending -> cancelled。
    后续可接入 DiagnosisExecutorPool 的主动中断能力。
    """
    row = db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))
    if not row:
        return _error('执行记录不存在', 404)
    if row.get('user_id') != current_user.id and not getattr(current_user, 'is_admin', False):
        return _error('无权取消该执行记录', 403)
    if row.get('status') not in ('pending', 'running'):
        return _error('当前状态不可取消', 400)

    db.update(
        'task_logs',
        {'status': 'cancelled', 'finished_at': _now_text(), 'error_message': '用户取消执行'},
        'id = ?',
        (run_id,),
    )

    # 通知 DiagnosisExecutorPool 设置取消信号（加速场景方案步骤中断）
    try:
        from backend.core.diagnosis_executor_pool import get_diagnosis_executor_pool
        pool = get_diagnosis_executor_pool()
        pool.cancel_execution(run_id)
    except Exception:
        pass  # 任务可能不在 pool 中（如手动任务），忽略错误

    return jsonify({'ok': True, 'run_id': run_id, 'status': 'cancelled'})


@task_bp.route('/diagnosis/history', methods=['GET'])
@login_required
def diagnosis_history():
    """查询诊断执行历史（仅 diagnosis 类型记录）。"""
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    status_filter = request.args.get('status', '').strip()

    where_sql = "t.execution_type = 'diagnosis'"
    params = []
    if not getattr(current_user, 'is_admin', False):
        where_sql += ' AND t.user_id = ?'
        params.append(current_user.id)
    if status_filter:
        where_sql += ' AND t.status = ?'
        params.append(status_filter)

    total = db.fetch_one(
        f'SELECT COUNT(*) AS cnt FROM task_logs t WHERE {where_sql}',
        tuple(params)
    )

    rows = db.fetch_all(f'''
        SELECT
            t.id,
            t.capability_id,
            t.user_id,
            t.execution_mode,
            t.execution_type,
            t.target_json,
            t.params_json,
            t.status,
            t.result_json,
            t.error_message,
            t.duration_ms,
            t.started_at,
            t.finished_at,
            t.created_at,
            c.name AS capability_name,
            c.category AS capability_category,
            c.level AS capability_level,
            c.risk_level AS risk_level
        FROM task_logs t
        LEFT JOIN diagnosis_capabilities c ON c.id = t.capability_id
        WHERE {where_sql}
        ORDER BY COALESCE(t.started_at, t.created_at) DESC
        LIMIT ? OFFSET ?
    ''', tuple(params + [limit, offset]))

    history = []
    for row in rows:
        item = dict(row)
        item['target'] = _json_loads(item.pop('target_json', None), {})
        item['params'] = _json_loads(item.pop('params_json', None), {})
        item['result'] = _json_loads(item.pop('result_json', None), None)
        history.append(item)

    return jsonify({
        'ok': True,
        'history': history,
        'count': len(history),
        'total': total['cnt'] if total else 0,
        'limit': limit,
        'offset': offset,
    })


# ─────────────────────────────────────────────────────────────
# 调度路由
# ─────────────────────────────────────────────────────────────

@task_bp.route('/schedules', methods=['GET'])
@login_required
def list_schedules():
    rows = db.fetch_all('''
        SELECT s.*, d.name AS task_name
        FROM task_schedules s
        LEFT JOIN task_definitions d ON d.id = s.task_id
        WHERE s.user_id = ?
        ORDER BY s.updated_at DESC, s.id DESC
    ''', (current_user.id,))
    return jsonify({'schedules': [_row_to_schedule(row) for row in rows]})


@task_bp.route('/schedules', methods=['POST'])
@login_required
def create_schedule():
    data = request.json or {}
    task_id = data.get('task_id')
    name = (data.get('name') or '').strip()
    interval_seconds = _normalize_schedule_interval(data.get('interval_seconds') or 3600)

    if not task_id:
        return _error('task_id 不能为空')
    if not name:
        return _error('调度名称不能为空')

    task = db.fetch_one(
        'SELECT * FROM task_definitions WHERE id = ? AND created_by = ? AND status = ?',
        (int(task_id), current_user.id, 'active')
    )
    if not task:
        return _error('任务不存在、无权限或已停用', 404)

    now = _now_text()
    next_run_at = _compute_next_run_at(interval_seconds, now)
    schedule_config = data.get('schedule_config') or {}

    schedule_id = db.insert('task_schedules', {
        'task_id': int(task_id),
        'user_id': current_user.id,
        'name': name,
        'schedule_type': 'interval',
        'interval_seconds': interval_seconds,
        'schedule_config_json': _json_dumps(schedule_config),
        'status': 'active',
        'next_run_at': next_run_at,
    })
    row = db.fetch_one('SELECT * FROM task_schedules WHERE id = ?', (schedule_id,))
    return jsonify({'ok': True, 'schedule': _row_to_schedule(row)}), 201


@task_bp.route('/schedules/<int:schedule_id>', methods=['PUT'])
@login_required
def update_schedule(schedule_id: int):
    """暂停 / 恢复调度，或修改 interval / name。"""
    row = db.fetch_one(
        'SELECT * FROM task_schedules WHERE id = ? AND user_id = ?',
        (schedule_id, current_user.id)
    )
    if not row:
        return _error('调度不存在或无权限', 404)

    data = request.json or {}
    updates: Dict[str, Any] = {'updated_at': _now_text()}

    if 'status' in data:
        new_status = (data['status'] or '').strip().lower()
        if new_status not in ('active', 'paused'):
            return _error('status 只能是 active 或 paused')
        updates['status'] = new_status
        # 恢复 active 时重新计算 next_run_at
        if new_status == 'active':
            updates['next_run_at'] = _compute_next_run_at(
                data.get('interval_seconds') or row['interval_seconds']
            )

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return _error('调度名称不能为空')
        updates['name'] = name

    if 'interval_seconds' in data:
        updates['interval_seconds'] = _normalize_schedule_interval(data['interval_seconds'])
        if updates.get('status', row['status']) == 'active':
            updates['next_run_at'] = _compute_next_run_at(updates['interval_seconds'])

    db.update('task_schedules', updates, 'id = ?', (schedule_id,))
    row = db.fetch_one('SELECT * FROM task_schedules WHERE id = ?', (schedule_id,))
    return jsonify({'ok': True, 'schedule': _row_to_schedule(row)})


@task_bp.route('/schedules/<int:schedule_id>', methods=['DELETE'])
@login_required
def delete_schedule(schedule_id: int):
    row = db.fetch_one(
        'SELECT id FROM task_schedules WHERE id = ? AND user_id = ?',
        (schedule_id, current_user.id)
    )
    if not row:
        return _error('调度不存在或无权限', 404)
    db.execute('DELETE FROM task_schedules WHERE id = ?', (schedule_id,))
    return jsonify({'ok': True})


# ─────────────────────────────────────────────────────────────
# 后台调度器
# ─────────────────────────────────────────────────────────────

_sched_log = logging.getLogger('task_scheduler')


def _run_due_schedules_once() -> int:
    """执行所有到期的调度任务，返回本次执行的数量。"""
    now = _now_text()
    schedules = db.fetch_all(
        "SELECT * FROM task_schedules WHERE status = 'active' AND next_run_at <= ?",
        (now,)
    )
    count = 0
    for schedule in schedules:
        task = db.fetch_one(
            "SELECT * FROM task_definitions WHERE id = ? AND status = 'active'",
            (schedule['task_id'],)
        )
        if not task:
            _sched_log.warning('调度 %s: 任务 %s 不存在或已停用，跳过', schedule['id'], schedule['task_id'])
            continue

        user_id = schedule.get('user_id') or task.get('created_by') or 0
        _sched_log.info('调度 %s 触发: task=%s user=%s', schedule['id'], task['id'], user_id)
        try:
            _execute_task_definition(task, user_id, execution_mode='scheduled')
        except Exception as exc:
            _sched_log.error('调度 %s 执行异常: %s', schedule['id'], exc)
            _create_failed_task_log(task.get('id'), user_id, 'scheduled', str(exc))

        next_run = _compute_next_run_at(schedule['interval_seconds'])
        db.update('task_schedules', {
            'last_run_at': now,
            'next_run_at': next_run,
            'updated_at': _now_text(),
        }, 'id = ?', (schedule['id'],))
        count += 1
    return count


def _scheduler_loop():
    _sched_log.info('任务调度器启动，轮询间隔 %ss', _SCHEDULER_POLL_SECONDS)
    while True:
        try:
            fired = _run_due_schedules_once()
            if fired:
                _sched_log.info('本轮触发 %s 个调度', fired)
        except Exception as exc:
            _sched_log.error('调度轮询异常: %s', exc)
        time.sleep(_SCHEDULER_POLL_SECONDS)


def start_task_scheduler():
    """启动后台调度线程（幂等，多次调用无副作用）。"""
    global _SCHEDULER_STARTED
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        thread = threading.Thread(
            target=_scheduler_loop,
            name='task-scheduler',
            daemon=True,
        )
        thread.start()
        _SCHEDULER_STARTED = True
        _sched_log.info('任务调度线程已启动 (daemon=True)')


# ═══════════════════════════════════════════════════════════════════════════════
# 即时诊断执行 API
# ═══════════════════════════════════════════════════════════════════════════════

def _build_connection_snapshot(connection_row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'id': connection_row.get('id'),
        'cluster_name': connection_row.get('cluster_name'),
        'namespace': connection_row.get('namespace'),
        'pod_name': connection_row.get('pod_name'),
        'container_name': connection_row.get('container_name'),
        'level': connection_row.get('level'),
        'status': connection_row.get('status'),
        'local_port': connection_row.get('local_port'),
        'java_pid': connection_row.get('java_pid'),
        'arthas_version': connection_row.get('arthas_version'),
        'user_id': connection_row.get('user_id') or connection_row.get('owner_user_id'),
        'captured_at': _now_text(),
    }


def _build_capability_snapshot(capability: Dict[str, Any], extension: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = dict(capability)
    snapshot['extension'] = extension or {}
    return snapshot


def _resolve_rendered_command(capability: Dict[str, Any], extension: Dict[str, Any], params: Dict[str, Any], step_outputs: Optional[Dict[str, Any]] = None) -> str:
    category = capability.get('category')
    if category in ('quick', 'tool'):
        template = (extension or {}).get('template', {})
        command_template = template.get('arthas_command') or capability.get('arthas_command', '')
        return build_command(command_template, params, step_outputs or {})
    if category == 'scenario':
        commands = []
        for step in (extension or {}).get('steps', []):
            commands.append({
                'step_order': step.get('step_order'),
                'command': build_command(step.get('command', ''), params, step_outputs or {}),
            })
        return _json_dumps(commands)
    return ''


def _create_task_log_for_diagnosis(
    run_id: str,
    capability: Dict[str, Any],
    extension: Dict[str, Any],
    connection: Dict[str, Any],
    params: Dict[str, Any],
    user_id: int,
    rendered_command: str,
) -> None:
    db.insert('task_logs', {
        'id': run_id,
        'task_id': None,
        'capability_id': capability.get('id'),
        'user_id': user_id,
        'execution_mode': 'immediate',
        'execution_type': 'diagnosis',
        'run_type': 'diagnosis',
        'capability_name': capability.get('name'),
        'capability_version': capability.get('version') or 1,
        'rendered_command': rendered_command,
        'status': 'running',
        'target_json': _json_dumps({
            'connection_id': connection.get('id'),
            'cluster_name': connection.get('cluster_name'),
            'namespace': connection.get('namespace'),
            'pod_name': connection.get('pod_name'),
            'container_name': connection.get('container_name'),
        }),
        'params_json': _json_dumps(params),
        'connection_snapshot_json': _json_dumps(_build_connection_snapshot(connection)),
        'capability_snapshot_json': _json_dumps(_build_capability_snapshot(capability, extension)),
        'started_at': _now_text(),
    })


def _update_task_log_success(run_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current = db.fetch_one('SELECT status FROM task_logs WHERE id = ?', (run_id,))
    if current and current.get('status') == 'cancelled':
        return db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))
    status = result.get('status') or 'success'
    if status == 'completed':
        status = 'success'
    db.update('task_logs', {
        'status': status,
        'result_json': _json_dumps(result),
        'duration_ms': result.get('duration_ms', result.get('total_duration_ms', 0)),
        'finished_at': _now_text(),
        'error_message': result.get('error_message') or result.get('error') or '',
    }, 'id = ?', (run_id,))
    return db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))


def _update_task_log_failed(run_id: str, error: Any) -> Optional[Dict[str, Any]]:
    current = db.fetch_one('SELECT status FROM task_logs WHERE id = ?', (run_id,))
    if current and current.get('status') == 'cancelled':
        return db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))
    db.update('task_logs', {
        'status': 'failed',
        'error_message': str(error),
        'finished_at': _now_text(),
    }, 'id = ?', (run_id,))
    return db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))


def _is_task_log_cancelled(run_id: str) -> bool:
    row = db.fetch_one('SELECT status FROM task_logs WHERE id = ?', (run_id,))
    return bool(row and row.get('status') == 'cancelled')


def _row_to_diagnosis_run(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    item['target'] = _json_loads(item.pop('target_json', None), {})
    item['params'] = _json_loads(item.pop('params_json', None), {})
    item['result'] = _json_loads(item.pop('result_json', None), None)
    item['connection_snapshot'] = _json_loads(item.pop('connection_snapshot_json', None), {})
    item['capability_snapshot'] = _json_loads(item.pop('capability_snapshot_json', None), {})
    item['run_id'] = item.get('id')
    item['execution_id'] = item.get('id')
    return item


def _ensure_connection_ready_for_capability(connection: Dict[str, Any], capability: Dict[str, Any]) -> None:
    category = capability.get('category')
    required_arthas = category in ('quick', 'tool', 'scenario', 'ai') or int(capability.get('level') or 1) >= 2
    if required_arthas and connection.get('level') != 'arthas':
        raise ValueError('当前能力需要 Arthas Ready 连接，请升级连接')
    if not required_arthas and connection.get('level') not in ('pod', 'arthas'):
        raise ValueError('当前能力需要 Pod 连接')
    status = (connection.get('status') or '').lower()
    allowed_statuses = {'ready', 'active', 'connected'} if required_arthas else {'ready', 'active', 'connected', 'pod_ready'}
    if status and status not in allowed_statuses:
        raise ValueError('Arthas 连接状态不可用，请重新建立连接')


def _ensure_arthas_connection_ready(connection: Dict[str, Any]) -> None:
    _ensure_connection_ready_for_capability(connection, {'category': 'tool', 'level': 2})


def _run_diagnosis_execution(
    run_id: str,
    connection_id: str,
    capability: Dict[str, Any],
    extension: Dict[str, Any],
    params: Dict[str, Any],
    active_conn: Any,
    connection: Dict[str, Any],
    user_id: int,
    cleanup,
    cancel_event=None,
) -> Dict[str, Any]:
    from backend.core.connection_aware_executor import get_connection_aware_executor

    connection_executor = get_connection_aware_executor()

    def _execute_diagnosis():
        if capability['category'] in ('quick', 'tool'):
            return _execute_arthas_command(capability, extension, params, active_conn)
        if capability['category'] == 'scenario':
            return _execute_scenario(capability, extension, params, active_conn, run_id=run_id, cancel_event=cancel_event)
        if capability['category'] == 'ai':
            return _execute_ai_diagnosis(capability, extension, params, connection)
        if capability['category'] == 'mcp':
            return _execute_mcp_skill(capability, params, active_conn)
        raise ValueError(f'不支持的能力类型: {capability["category"]}')

    try:
        result = connection_executor.execute_with_connection_guard(
            connection_id=connection_id,
            capability_id=capability['id'],
            params=params,
            user_id=user_id,
            execution_func=_execute_diagnosis,
            execution_id=run_id,
        )
        cleanup(status='completed')
        _update_task_log_success(run_id, result)
        return result
    except Exception as exc:
        cleanup(status='failed', error=str(exc))
        _update_task_log_failed(run_id, exc)
        log.error('诊断执行失败: %s', exc, exc_info=True)
        raise


@task_bp.route('/diagnosis/execute', methods=['POST'])
@login_required
def execute_diagnosis():
    """即时诊断执行。quick/tool 同步返回结果；scenario/ai 后台执行并通过 run_id 轮询。"""
    data = request.json or {}
    capability_id = data.get('capability_id')
    params = data.get('params') or {}
    connection_id = data.get('connection_id')

    if not capability_id:
        return _error('capability_id 不能为空')
    if not connection_id:
        return _error('connection_id 不能为空')

    capability = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (capability_id,))
    if not capability:
        return _error('诊断能力不存在', 404)

    user_role = current_user.role if hasattr(current_user, 'role') else 'user'
    if user_role != 'admin':
        visible = capability.get('visibility') == 'public' or capability.get('created_by') == current_user.id
        if not visible:
            return _error('无权执行该诊断能力', 403)

    extension = load_extension(capability['category'], capability_id)
    error = ParameterValidator.validate(capability.get('parameters_schema', '{}'), params)
    if error:
        return _error(error)

    connection = db.fetch_one('SELECT * FROM connections WHERE id = ?', (connection_id,))
    if not connection:
        return _error('连接不存在', 404)
    if connection.get('user_id') not in (None, current_user.id) and not getattr(current_user, 'is_admin', False):
        return _error('无权使用该连接', 403)

    try:
        _ensure_connection_ready_for_capability(connection, capability)
        active_conn = _get_active_arthas_connection(connection_id, connection)
    except ValueError as exc:
        return _error(str(exc), 409)

    from backend.core.diagnosis_executor_pool import get_diagnosis_executor_pool, ConcurrencyError

    run_id = uuid.uuid4().hex
    rendered_command = _resolve_rendered_command(capability, extension, params)
    pool = get_diagnosis_executor_pool()
    try:
        submit_result = pool.submit_diagnosis(
            connection_id=connection_id,
            capability_id=capability_id,
            params=params,
            user_id=current_user.id,
            execution_id=run_id,
        )
    except ConcurrencyError as exc:
        return _error(str(exc), 429)

    if not submit_result.get('ok'):
        return _error(submit_result.get('error', '提交失败'))

    _create_task_log_for_diagnosis(
        run_id=run_id,
        capability=capability,
        extension=extension,
        connection=connection,
        params=params,
        user_id=current_user.id,
        rendered_command=rendered_command,
    )

    cleanup = submit_result['cleanup']
    cancel_event = submit_result.get('cancel_event')
    if capability['category'] in ('scenario', 'ai'):
        thread = threading.Thread(
            target=lambda: _run_diagnosis_execution(
                run_id, connection_id, capability, extension, params,
                active_conn, connection, current_user.id, cleanup,
                cancel_event=cancel_event,
            ),
            name=f'diagnosis-{run_id[:8]}',
            daemon=True,
        )
        thread.start()
        return jsonify({'ok': True, 'run_id': run_id, 'execution_id': run_id, 'status': 'running'})

    try:
        result = _run_diagnosis_execution(
            run_id, connection_id, capability, extension, params,
            active_conn, connection, current_user.id, cleanup,
            cancel_event=cancel_event,
        )
    except Exception as exc:
        return _error(f'诊断执行失败: {str(exc)}', 500)

    return jsonify({'ok': True, 'run_id': run_id, 'execution_id': run_id, 'log_id': run_id, 'result': result})


@task_bp.route('/diagnosis/executions/<run_id>/status', methods=['GET'])
@task_bp.route('/diagnosis/runs/<run_id>', methods=['GET'])
@login_required
def get_diagnosis_run_status(run_id: str):
    row = db.fetch_one('SELECT * FROM task_logs WHERE id = ?', (run_id,))
    if not row:
        return _error('执行记录不存在', 404)
    if row.get('user_id') != current_user.id and not getattr(current_user, 'is_admin', False):
        return _error('无权查看该执行记录', 403)
    return jsonify({'ok': True, 'run': _row_to_diagnosis_run(row)})


@task_bp.route('/diagnosis/runs/<run_id>/cancel', methods=['POST'])
@login_required
def cancel_diagnosis_run(run_id: str):
    return cancel_task_run(run_id)


def _execute_arthas_command(capability, extension, params, connection):
    """执行单条 Arthas 命令"""
    from backend.core.arthas_executor import ArthasCommandExecutor

    if not connection or not getattr(connection, 'http_client', None):
        raise ValueError('Arthas 连接不可用，请重新建立连接')
    
    # 获取命令模板
    template = extension.get('template', {})
    command_template = template.get('arthas_command') or capability.get('arthas_command', '')
    
    # 构建命令
    command = build_command(command_template, params)
    
    # 执行命令
    result = ArthasCommandExecutor.execute(
        connection,
        command,
        skip_audit=False,
        skip_history=False,
    )
    
    return {
        'status': 'success' if result.get('state') == 'SUCCEEDED' else 'failed',
        'result': result,
        'duration_ms': result.get('duration_ms', 0),
    }


def _execute_scenario(capability, extension, params, connection, run_id=None, cancel_event=None):
    """执行场景方案（多步骤）"""
    from backend.core.arthas_executor import ArthasCommandExecutor

    if not connection or not getattr(connection, 'http_client', None):
        raise ValueError('Arthas 连接不可用，请重新建立连接')

    # 解析步骤
    steps = extension.get('steps', [])
    if not steps:
        raise ValueError('场景方案未配置步骤')

    # 执行步骤（支持跨步数据传递）
    step_outputs = {}
    step_results = []
    total_duration = 0

    cancelled = False

    for step in steps:
        # 检查取消信号：优先检查内存中的 cancel_event（更快），其次查 DB
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break
        if run_id and _is_task_log_cancelled(run_id):
            cancelled = True
            break
        # 构建命令（支持 ${stepN.field} 语法）
        command = build_command(step['command'], params, step_outputs)
        
        # 执行命令
        try:
            result = ArthasCommandExecutor.execute(
                connection,
                command,
                timeout_ms=step.get('timeout_ms'),
                skip_audit=True,
                skip_history=True,
            )
            
            success = result.get('state') == 'SUCCEEDED'
            
            # 记录步骤输出（供后续步骤引用）
            step_outputs[f"step{step['step_order']}"] = result
            
            step_results.append({
                'step_order': step['step_order'],
                'command': command,
                'desc': step.get('desc', ''),
                'success': success,
                'result': result,
            })
            
            total_duration += result.get('duration_ms', 0)
            
            # fail_fast 控制
            if not success and step.get('fail_fast', 1):
                break
            
        except Exception as e:
            step_results.append({
                'step_order': step['step_order'],
                'command': command,
                'desc': step.get('desc', ''),
                'success': False,
                'error': str(e),
            })
            
            # fail_fast 控制
            if step.get('fail_fast', 1):
                break
    
    # 判断整体状态
    all_success = all(r.get('success') for r in step_results)
    status = 'cancelled' if cancelled else ('success' if all_success else 'partial')
    
    return {
        'status': status,
        'total_steps': len(steps),
        'completed_steps': len(step_results),
        'cancelled': cancelled,
        'steps': step_results,
        'duration_ms': total_duration,
    }


def _execute_ai_diagnosis(capability, extension, params, connection):
    """执行 AI 诊断

    Dispatch order (Phase 7 T02):
    1. handler_key-based routing via AISkillHandler (new AI skills)
    2. Legacy extension['handler'] routing via performance_diagnose (backward compat)
    """
    # Phase 7 T02: handler_key-based dispatch for new AI skills
    handler_key = (capability.get('handler_key') or '').strip()
    if handler_key:
        from services.ai_skill_handler import execute_ai_skill
        skill_params = dict(params)
        skill_params['handler_key'] = handler_key
        skill_params['user_id'] = connection.get('user_id')
        result = execute_ai_skill(skill_params, connection['id'])
        if not result.get('ok'):
            raise ValueError(result.get('error', 'AI 技能执行失败'))
        return {
            'status': 'success',
            'result': result,
            'duration_ms': 0,
        }

    # Legacy: extension-based handler dispatch (backward compatibility)
    handler = extension.get('handler', {})
    handler_name = handler.get('handler', '')

    if not handler_name:
        raise ValueError('AI 诊断未配置处理器')

    # 调用 performance_diagnose 模块
    if handler_name.startswith('performance_diagnose.'):
        from api.performance_diagnose import run_diagnosis
        result = run_diagnosis(connection['id'], params)
        return {
            'status': 'success',
            'result': result,
            'duration_ms': result.get('duration_ms', 0),
        }
    
    raise ValueError(f'不支持的 AI 诊断处理器: {handler_name}')


def _execute_mcp_skill(capability, params, active_conn):
    """Execute an MCP-category skill via MCPSkillHandler bridge.

    Dispatches based on capability['handler_key'] to the appropriate
    handler in services/mcp_skill_handler.py.
    """
    from services.mcp_skill_handler import get_mcp_skill_handler

    handler_key = capability.get('handler_key', '')
    if not handler_key:
        raise ValueError(f'MCP 能力未配置 handler_key: {capability["name"]}')

    handler = get_mcp_skill_handler()
    result = handler.execute(handler_key, params, connection=active_conn)

    if not result.get('ok'):
        raise ValueError(result.get('error', 'MCP skill execution failed'))

    return {
        'status': 'success',
        'result': result.get('result', {}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 脚本模板 API
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/script-templates', methods=['GET'])
@login_required
def list_script_templates():
    """查询脚本模板列表"""
    templates = db.fetch_all(
        'SELECT * FROM script_templates ORDER BY created_at DESC'
    )
    return jsonify({
        'ok': True,
        'templates': [dict(t) for t in templates]
    })


@task_bp.route('/script-templates', methods=['POST'])
@login_required
def create_script_template():
    """创建脚本模板"""
    data = request.get_json()
    
    name = data.get('name', '').strip()
    runtime = data.get('runtime', 'python').strip()
    script_body = data.get('script_body', '').strip()
    capability_id = data.get('capability_id')
    description = data.get('description', '').strip()
    
    if not name:
        return jsonify({'ok': False, 'message': '模板名称不能为空'}), 400
    if not script_body:
        return jsonify({'ok': False, 'message': '脚本内容不能为空'}), 400
    
    template_id = db.insert('script_templates', {
        'name': name,
        'runtime': runtime,
        'script_body': script_body,
        'capability_id': capability_id,
        'description': description,
        'created_by': current_user.id if hasattr(current_user, 'id') else None,
    })
    
    return jsonify({
        'ok': True,
        'id': template_id,
        'message': '脚本模板创建成功'
    }), 201


@task_bp.route('/script-templates/<int:template_id>', methods=['GET'])
@login_required
def get_script_template(template_id):
    """获取脚本模板详情"""
    template = db.fetch_one(
        'SELECT * FROM script_templates WHERE id = ?',
        (template_id,)
    )
    
    if not template:
        return jsonify({'ok': False, 'message': '模板不存在'}), 404
    
    return jsonify({
        'ok': True,
        'template': dict(template)
    })


@task_bp.route('/script-templates/<int:template_id>', methods=['PUT'])
@login_required
def update_script_template(template_id):
    """更新脚本模板（仅创建者或 admin）"""
    template = db.fetch_one(
        'SELECT * FROM script_templates WHERE id = ?',
        (template_id,)
    )
    if not template:
        return jsonify({'ok': False, 'message': '模板不存在'}), 404
    if template.get('created_by') != current_user.id and not _is_admin_user():
        return jsonify({'ok': False, 'message': '无权修改此模板'}), 403

    data = request.get_json()
    
    fields = {}
    if 'name' in data:
        fields['name'] = data['name'].strip()
    if 'runtime' in data:
        fields['runtime'] = data['runtime'].strip()
    if 'script_body' in data:
        fields['script_body'] = data['script_body'].strip()
    if 'capability_id' in data:
        fields['capability_id'] = data['capability_id']
    if 'description' in data:
        fields['description'] = data['description'].strip()
    
    if not fields:
        return jsonify({'ok': False, 'message': '无更新内容'}), 400
    
    db.update('script_templates', fields, 'id = ?', (template_id,))
    
    return jsonify({
        'ok': True,
        'message': '脚本模板更新成功'
    })


@task_bp.route('/script-templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_script_template(template_id):
    """删除脚本模板（仅创建者或 admin）"""
    template = db.fetch_one(
        'SELECT * FROM script_templates WHERE id = ?',
        (template_id,)
    )

    if not template:
        return jsonify({'ok': False, 'message': '模板不存在'}), 404
    if template.get('created_by') != current_user.id and not _is_admin_user():
        return jsonify({'ok': False, 'message': '无权删除此模板'}), 403

    db.execute('DELETE FROM script_templates WHERE id = ?', (template_id,))
    
    return jsonify({
        'ok': True,
        'message': '脚本模板已删除'
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ✅ Phase 6: 任务中心增强
# ═══════════════════════════════════════════════════════════════════════════════

@task_bp.route('/health/connections', methods=['GET'])
@login_required
def check_connections_health():
    """检查当前用户的 Arthas 连接健康状态"""
    from backend.core.connection import ArthasConnection

    if getattr(current_user, 'is_admin', False):
        connections = db.fetch_all('SELECT * FROM connections WHERE status = ?', ('active',))
    else:
        connections = db.fetch_all(
            'SELECT * FROM connections WHERE status = ? AND user_id = ?',
            ('active', current_user.id)
        )
    
    health_results = []
    for conn in connections:
        conn_id = dict(conn)['id']
        try:
            # 尝试 ping Arthas
            arthas_conn = ArthasConnection(conn_id)
            is_healthy = arthas_conn.ping(timeout=5)
            
            health_results.append({
                'connection_id': conn_id,
                'healthy': is_healthy,
                'last_checked': datetime.now().isoformat(),
            })
            
            # 更新连接状态
            if not is_healthy:
                db.update('connections', {'status': 'unhealthy'}, 'id = ?', (conn_id,))
        except Exception as e:
            health_results.append({
                'connection_id': conn_id,
                'healthy': False,
                'error': str(e),
                'last_checked': datetime.now().isoformat(),
            })
            db.update('connections', {'status': 'unhealthy'}, 'id = ?', (conn_id,))
    
    return jsonify({
        'ok': True,
        'connections': health_results,
        'total': len(health_results),
        'healthy_count': sum(1 for r in health_results if r['healthy']),
    })
