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
import os
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


task_bp = Blueprint('task_center', __name__, url_prefix='/api/tasks')

_ALLOWED_RUNTIMES = {'python', 'shell'}
_ALLOWED_EXECUTION_MODES = {'node', 'pod'}
_DEFAULT_TIMEOUT_SECONDS = 60
_MAX_TIMEOUT_SECONDS = 600
_OUTPUT_ROOT = Path(Config.OUTPUT_DIR) / 'task_runs'
_TOOL_PACKAGE_ROOT = Path(Config.OUTPUT_DIR) / 'tool_packages'
_TOOL_TYPES = {'arthas', 'async-profiler', 'jattach', 'generic'}
_BUILTIN_ARTHAS_PATH = '/app/arthas/arthas-boot.jar'
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
    except Exception:
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


def _validate_tool_install_path(value: Any) -> str:
    path = (value or '').strip() or _DEFAULT_ARTHAS_INSTALL_PATH
    if not path.startswith('/'):
        raise ValueError('安装路径必须是 Pod 内绝对路径')
    if '..' in Path(path).parts or '\n' in path or '\r' in path or '\x00' in path:
        raise ValueError('安装路径包含非法字符')
    blocked = ('/etc', '/bin', '/sbin', '/usr/bin', '/usr/sbin')
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
    from server import _load_clusters

    clusters = _load_clusters()
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


def _create_run_record(task: Dict[str, Any], user_id: int) -> str:
    run_id = uuid.uuid4().hex
    db.insert('task_runs', {
        'id': run_id,
        'task_id': task.get('id'),
        'user_id': user_id,
        'status': 'running',
        'execution_mode': task.get('execution_mode'),
        'target_json': task.get('target_json') or '{}',
        'started_at': _now_text(),
    })
    return run_id


def _finish_run_record(run_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    db.update('task_runs', {
        'status': result['status'],
        'stdout': result['stdout'],
        'stderr': result['stderr'],
        'exit_code': result['exit_code'],
        'duration_ms': result['duration_ms'],
        'finished_at': _now_text(),
        'error_message': result['error_message'],
        'work_dir': result['work_dir'],
    }, 'id = ?', (run_id,))
    return db.fetch_one('SELECT * FROM task_runs WHERE id = ?', (run_id,))


def _execute_task_definition(task: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    run_id = _create_run_record(task, user_id)
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
    return _finish_run_record(run_id, result)


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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                source_type TEXT DEFAULT 'local',
                source_url TEXT,
                version TEXT,
                checksum TEXT,
                tool_type TEXT DEFAULT 'generic',
                file_path TEXT,
                file_name TEXT,
                file_size INTEGER DEFAULT 0,
                sha256 TEXT,
                install_path TEXT,
                is_builtin INTEGER DEFAULT 0,
                last_verified_at TIMESTAMP,
                status TEXT DEFAULT 'active',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_runs (
                id TEXT PRIMARY KEY,
                task_id INTEGER,
                user_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                execution_mode TEXT NOT NULL,
                target_json TEXT DEFAULT '{}',
                stdout TEXT,
                stderr TEXT,
                exit_code INTEGER,
                duration_ms INTEGER,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                error_message TEXT,
                work_dir TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES task_definitions(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES task_runs(id) ON DELETE CASCADE
            )
        ''')
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
    return jsonify({
        'templates': db.count('script_templates'),
        'tasks': db.count('task_definitions', 'created_by = ?', (current_user.id,)),
        'runs': db.count('task_runs', 'user_id = ?', (current_user.id,)),
        'running': db.count('task_runs', 'user_id = ? AND status = ?', (current_user.id, 'running')),
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
    row = db.fetch_one('SELECT * FROM tool_packages WHERE id = ?', (package_id,))
    if not row:
        return _error('工具包不存在', 404)
    if row.get('status') not in ('active', 'inactive'):
        return _error('工具包状态不可分发')
    data = request.json or {}
    try:
        target = _validate_pod_target(data)
        install_path = _validate_tool_install_path(data.get('install_path') or row.get('install_path') or _DEFAULT_ARTHAS_INSTALL_PATH)
    except ValueError as exc:
        return _error(str(exc))
    file_path = row.get('file_path') or ''
    local_path = Path(file_path)
    if not file_path or not local_path.exists():
        return _error('离线工具文件不存在，请先上传或检查服务器内置路径', 404)
    if row.get('tool_type') == 'arthas' and not install_path.endswith('.jar'):
        return _error('Arthas 工具必须分发为 .jar 文件')

    cluster = _get_cluster_config(target['cluster_name'])
    auth_err, auth_code = AuthorizationService.require_namespace_access(
        current_user, target['cluster_name'], target['namespace'])
    if auth_err:
        return _error(auth_err['error'], auth_code)
    from backend import KubectlExecutor
    runner = KubectlExecutor(kubeconfig=cluster.get('kubeconfig', ''), context=cluster.get('context', ''))
    install_dir = str(Path(install_path).parent).replace('\\', '/')
    rc_mkdir, out_mkdir, err_mkdir = runner.exec_pod(
        target['namespace'], target['pod_name'], target['container'],
        f'mkdir -p {_safe_pod_path(install_dir)}', timeout=30
    )
    if rc_mkdir != 0:
        return _error(f'创建 Pod 目录失败: {err_mkdir or out_mkdir}', 500)
    rc_cp, out_cp, err_cp = runner.cp_to_pod(
        target['namespace'], target['pod_name'], target['container'], str(local_path), install_path
    )
    if rc_cp != 0:
        return _error(f'分发文件失败: {err_cp or out_cp}', 500)
    rc_check, out_check, err_check = runner.exec_pod(
        target['namespace'], target['pod_name'], target['container'],
        f'ls -lh {_safe_pod_path(install_path)} && (sha256sum {_safe_pod_path(install_path)} 2>/dev/null || true)',
        timeout=30,
    )
    return jsonify({
        'ok': rc_check == 0,
        'target': target,
        'install_path': install_path,
        'stdout': '\n'.join(x for x in (out_mkdir, out_cp, out_check) if x),
        'stderr': '\n'.join(x for x in (err_mkdir, err_cp, err_check) if x),
    })


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
@login_required
def run_definition(task_id: int):
    task = db.fetch_one('SELECT * FROM task_definitions WHERE id = ? AND created_by = ?', (task_id, current_user.id))
    if not task:
        return _error('任务不存在或无权限', 404)
    if task.get('status') != 'active':
        return _error('任务不是 active 状态，不能执行')
    if not _validate_execution_mode(task.get('execution_mode') or 'node'):
        return _error('执行位置仅支持 node / pod')

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
    rows = db.fetch_all('''
        SELECT r.*, d.name AS task_name
        FROM task_runs r
        LEFT JOIN task_definitions d ON d.id = r.task_id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
        LIMIT ? OFFSET ?
    ''', (current_user.id, limit, offset))
    return jsonify({'runs': [_row_to_run(row) for row in rows]})


@task_bp.route('/runs/<run_id>/logs', methods=['GET'])
@login_required
def get_run_logs(run_id: str):
    row = db.fetch_one('''
        SELECT r.*, d.name AS task_name
        FROM task_runs r
        LEFT JOIN task_definitions d ON d.id = r.task_id
        WHERE r.id = ? AND r.user_id = ?
    ''', (run_id, current_user.id))
    if not row:
        return _error('执行记录不存在或无权限', 404)
    return jsonify({'run': _row_to_run(row, include_logs=True)})


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

import logging as _logging
_sched_log = _logging.getLogger('task_scheduler')


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
            _execute_task_definition(task, user_id)
        except Exception as exc:
            _sched_log.error('调度 %s 执行异常: %s', schedule['id'], exc)

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
