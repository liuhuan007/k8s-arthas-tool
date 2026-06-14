#!/usr/bin/env python3
"""诊断能力 API - 统一诊断执行入口

提供以下 API：
  POST /api/diagnosis/execute           - 执行诊断能力（同步 / 异步）
  GET  /api/diagnosis/status/<exec_id>  - 查询执行状态（轮询）
  POST /api/diagnosis/cancel/<exec_id>  - 取消执行
  POST /api/diagnosis/execute-skill     - 执行预制 Skill
  GET  /api/diagnosis/connections/<id>/info - 获取连接摘要信息
  POST /api/diagnosis/batch-execute     - 批量执行（场景方案步骤）
"""
from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Dict, Optional

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from backend.core.arthas_executor import (
    ArthasCommandExecutor,
    ExecutionStatus,
    _is_safe_command,
)
from backend.core.connection_selector import (
    ConnectionSelector,
    ConnectionType,
)
from backend.core.command_builder import build_command
from backend.core.parameter_validator import ParameterValidator

log = logging.getLogger(__name__)

diagnosis_bp = Blueprint('diagnosis', __name__, url_prefix='/api/diagnosis')


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _get_user_id() -> Optional[int]:
    """安全获取当前用户 ID"""
    try:
        if current_user and current_user.is_authenticated:
            return current_user.id
    except Exception:
        pass
    return None


def _get_arthas_connection(connection_id: str):
    """根据连接 ID 获取 ArthasConnection 实例

    优先从内存连接管理器获取活跃连接，
    如果不存在则尝试从数据库重建。

    Returns:
        ArthasConnection 或 None
    """
    try:
        from backend.app_context import connections  # 全局活跃连接字典
        if connections and connection_id in connections:
            return connections[connection_id]
    except (ImportError, AttributeError):
        pass

    # 尝试从 app context 获取
    try:
        from flask import current_app
        manager = current_app.config.get('connection_manager')
        if manager:
            return manager.get(connection_id)
    except Exception:
        pass

    return None


def _get_capability(capability_id: int) -> Optional[Dict[str, Any]]:
    """获取能力定义"""
    try:
        from models.db import get_db
        db = get_db()
        return db.fetch_one(
            'SELECT * FROM diagnosis_capabilities WHERE id = ?',
            (capability_id,)
        )
    except Exception as e:
        log.error("Failed to fetch capability %d: %s", capability_id, e)
        return None


def _validate_and_build_command(
    arthas_command: str,
    parameters_schema: Optional[str],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """校验参数并构建命令

    Returns:
        {'ok': True, 'command': '构建后的命令'} 或
        {'ok': False, 'error': '错误信息'}
    """
    # 1. 参数校验
    if parameters_schema:
        validation_error = ParameterValidator.validate(parameters_schema, params)
        if validation_error:
            return {'ok': False, 'error': validation_error}

    # 2. 构建命令
    try:
        command = build_command(arthas_command, params)
    except Exception as e:
        return {'ok': False, 'error': f'命令构建失败: {str(e)}'}

    # 3. 命令注入检查（安全层）
    if not _is_safe_command(command):
        return {'ok': False, 'error': '命令包含不安全的字符或模式'}

    return {'ok': True, 'command': command}


# ═══════════════════════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════════════════════

@diagnosis_bp.route('/execute', methods=['POST'])
@login_required
def execute_diagnosis():
    """执行诊断能力

    请求体:
        {
            "capability_id": 1,
            "connection_id": "conn-xxx",
            "params": {"class": "com.example.Service"},
            "mode": "sync"   // sync | async (默认 sync)
        }

    响应（sync）:
        {
            "ok": true,
            "result": { "state": "SUCCEEDED", "body": {...} }
        }

    响应（async）:
        {
            "ok": true,
            "execution_id": "exec-xxxxxxxx",
            "mode": "async"
        }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': '请求体不能为空'}), 400

        capability_id = data.get('capability_id')
        connection_id = data.get('connection_id')
        params = data.get('params', {})
        mode = data.get('mode', 'sync')

        # 参数验证
        if not capability_id:
            return jsonify({'ok': False, 'error': 'capability_id 不能为空'}), 400
        if not connection_id:
            return jsonify({'ok': False, 'error': 'connection_id 不能为空'}), 400

        # 1. 获取能力定义
        capability = _get_capability(capability_id)
        if not capability:
            return jsonify({'ok': False, 'error': f'能力 {capability_id} 不存在'}), 404

        # 2. 权限检查
        from backend.core.diagnosis_capabilities import check_capability_permission
        user_id = _get_user_id()
        user_role = getattr(current_user, 'role', 'user')
        if not check_capability_permission(capability_id, user_id, user_role):
            return jsonify({'ok': False, 'error': '无权限执行此诊断能力'}), 403

        # 3. 获取连接
        connection = _get_arthas_connection(connection_id)
        if not connection:
            return jsonify({
                'ok': False,
                'error': '连接不存在或已断开，请重新建立连接',
            }), 400

        # 4. 选择连接类型并验证
        conn_type = ConnectionSelector.resolve_type(capability)
        validation_error = ConnectionSelector.validate_connection(connection, conn_type)
        if validation_error:
            return jsonify({'ok': False, 'error': validation_error}), 400

        # 5. 根据能力类型执行
        category = capability.get('category', '')

        # 场景方案（多步骤）
        if capability.get('steps_json') and category == 'scenario':
            return _execute_scenario(capability, connection, params, mode, user_id)

        # AI 诊断（handler）
        if capability.get('handler') and category == 'ai':
            return _execute_handler(capability, connection, params, mode, user_id)

        # 快捷工具 / 诊断模板（单命令）
        if capability.get('arthas_command'):
            return _execute_single_command(capability, connection, params, mode, user_id)

        return jsonify({'ok': False, 'error': '能力定义不完整，缺少执行入口'}), 400

    except Exception as e:
        log.error("Execute diagnosis failed: %s\n%s", e, traceback.format_exc())
        return jsonify({'ok': False, 'error': f'执行失败: {str(e)}'}), 500


@diagnosis_bp.route('/status/<execution_id>', methods=['GET'])
@login_required
def poll_status(execution_id: str):
    """查询执行状态（轮询）

    响应:
        {
            "ok": true,
            "status": {
                "execution_id": "exec-xxx",
                "status": "running|succeeded|failed|cancelled|timeout",
                "result": {...},
                "duration_ms": 1234,
                ...
            }
        }
    """
    try:
        connection_id = request.args.get('connection_id')
        connection = None
        if connection_id:
            connection = _get_arthas_connection(connection_id)

        status = ArthasCommandExecutor.poll_execution(
            execution_id, connection=connection
        )

        if status is None:
            return jsonify({'ok': False, 'error': '执行记录不存在'}), 404

        return jsonify({'ok': True, 'status': status})

    except Exception as e:
        log.error("Poll status failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@diagnosis_bp.route('/cancel/<execution_id>', methods=['POST'])
@login_required
def cancel_execution(execution_id: str):
    """取消执行

    请求体（可选）:
        {
            "connection_id": "conn-xxx"
        }

    响应:
        {
            "ok": true,
            "message": "执行已取消"
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        connection_id = data.get('connection_id')
        connection = None
        if connection_id:
            connection = _get_arthas_connection(connection_id)

        success = ArthasCommandExecutor.cancel_execution(
            execution_id, connection=connection
        )

        if success:
            return jsonify({'ok': True, 'message': '执行已取消'})
        else:
            # 检查是否是已结束的执行
            record = ArthasCommandExecutor.get_execution(execution_id)
            if record:
                return jsonify({
                    'ok': False,
                    'error': f'执行已处于 {record["status"]} 状态，无法取消',
                }), 400
            return jsonify({'ok': False, 'error': '执行记录不存在'}), 404

    except Exception as e:
        log.error("Cancel execution failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@diagnosis_bp.route('/execute-skill', methods=['POST'])
@login_required
def execute_skill():
    """执行预制 Skill

    请求体:
        {
            "skill_id": 1,
            "connection_id": "conn-xxx",
            "params": {"class": "com.example.Service", "method": "doWork"},
            "confirmed": false
        }

    响应:
        {
            "ok": true,
            "execution_id": "exec-xxx",
            "result": {...}  // 同步模式
        }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': '请求体不能为空'}), 400

        skill_id = data.get('skill_id')
        connection_id = data.get('connection_id')
        params = data.get('params', {})
        confirmed = data.get('confirmed', False)

        if not skill_id:
            return jsonify({'ok': False, 'error': 'skill_id 不能为空'}), 400
        if not connection_id:
            return jsonify({'ok': False, 'error': 'connection_id 不能为空'}), 400

        # 1. 获取 Skill 定义
        try:
            from models.db import get_db
            db = get_db()
            skill = db.fetch_one(
                'SELECT * FROM skill_registry WHERE id = ?',
                (skill_id,)
            )
        except Exception as e:
            return jsonify({'ok': False, 'error': f'查询 Skill 失败: {e}'}), 500

        if not skill:
            return jsonify({'ok': False, 'error': f'Skill {skill_id} 不存在'}), 404

        # 2. 获取连接
        connection = _get_arthas_connection(connection_id)
        if not connection:
            return jsonify({
                'ok': False,
                'error': '连接不存在或已断开',
            }), 400

        # 3. 参数校验 + 命令构建
        arthas_command = skill.get('arthas_command', '')
        parameters_schema = skill.get('parameters_schema', '{}')

        if arthas_command:
            build_result = _validate_and_build_command(
                arthas_command, parameters_schema, params
            )
            if not build_result['ok']:
                return jsonify({'ok': False, 'error': build_result['error']}), 400

            command = build_result['command']

            # 4. 检查高危命令
            cmd_name = ArthasCommandExecutor._parse_command_name(command)
            from backend.core.arthas_executor import _HIGH_RISK_COMMANDS
            if cmd_name in _HIGH_RISK_COMMANDS and not confirmed:
                return jsonify({
                    'ok': False,
                    'error': f'命令 {cmd_name} 为高危操作，需要 confirmed=true 确认',
                    'require_confirm': True,
                    'command': command,
                }), 400

            # 5. 执行
            user_id = _get_user_id()
            result = ArthasCommandExecutor.execute(
                connection,
                command,
                skip_audit=False,
                skip_history=False,
                confirmed=confirmed,
            )

            exec_id = f"exec-skill-{skill_id}"
            return jsonify({
                'ok': True,
                'execution_id': exec_id,
                'skill_name': skill.get('name', ''),
                'command': command,
                'result': result,
            })

        elif skill.get('dsl'):
            # 场景方案 → 使用 WorkflowEngine
            try:
                from services.workflow_engine import get_workflow_engine
                engine = get_workflow_engine()
                run_id = engine.execute_skill(
                    capability_id=skill_id,
                    params=params,
                    connection_id=connection_id,
                    user_id=_get_user_id(),
                )
                return jsonify({
                    'ok': True,
                    'execution_id': run_id,
                    'skill_name': skill.get('name', ''),
                    'mode': 'workflow',
                }), 201
            except Exception as e:
                return jsonify({'ok': False, 'error': f'工作流执行失败: {e}'}), 500

        else:
            return jsonify({
                'ok': False,
                'error': 'Skill 没有配置执行入口（arthas_command 或 dsl）',
            }), 400

    except Exception as e:
        log.error("Execute skill failed: %s\n%s", e, traceback.format_exc())
        return jsonify({'ok': False, 'error': f'执行失败: {str(e)}'}), 500


@diagnosis_bp.route('/connections/<connection_id>/info', methods=['GET'])
@login_required
def get_connection_info(connection_id: str):
    """获取连接摘要信息

    响应:
        {
            "ok": true,
            "info": {
                "type": "arthas",
                "cluster_name": "...",
                "namespace": "...",
                "pod_name": "...",
                "arthas_ready": true,
                "local_port": 32001,
                ...
            }
        }
    """
    try:
        connection = _get_arthas_connection(connection_id)
        if not connection:
            return jsonify({
                'ok': False,
                'error': '连接不存在或已断开',
            }), 404

        info = ConnectionSelector.get_connection_info(connection)
        return jsonify({'ok': True, 'info': info})

    except Exception as e:
        log.error("Get connection info failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@diagnosis_bp.route('/batch-execute', methods=['POST'])
@login_required
def batch_execute():
    """批量执行（场景方案步骤）

    请求体:
        {
            "connection_id": "conn-xxx",
            "commands": [
                {"command": "trace ${class} ${method}", "desc": "Trace 调用链"},
                {"command": "watch ${class} ${method}", "desc": "观察入参"}
            ],
            "params": {"class": "com.example.Service", "method": "doWork"},
            "fail_fast": true
        }

    响应:
        {
            "ok": true,
            "results": [
                {"step": 1, "command": "...", "desc": "...", "result": {...}, "success": true},
                ...
            ]
        }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': '请求体不能为空'}), 400

        connection_id = data.get('connection_id')
        commands = data.get('commands', [])
        params = data.get('params', {})
        fail_fast = data.get('fail_fast', True)

        if not connection_id:
            return jsonify({'ok': False, 'error': 'connection_id 不能为空'}), 400
        if not commands:
            return jsonify({'ok': False, 'error': 'commands 不能为空'}), 400

        # 1. 获取连接
        connection = _get_arthas_connection(connection_id)
        if not connection:
            return jsonify({
                'ok': False,
                'error': '连接不存在或已断开',
            }), 400

        # 2. 验证连接类型
        validation_error = ConnectionSelector.validate_connection(
            connection, ConnectionType.ARTHAS
        )
        if validation_error:
            return jsonify({'ok': False, 'error': validation_error}), 400

        # 3. 构建所有命令
        built_commands = []
        for cmd_def in commands:
            raw_command = cmd_def.get('command', '')
            desc = cmd_def.get('desc', '')
            timeout = cmd_def.get('timeout_ms')

            # 参数替换
            try:
                command = build_command(raw_command, params)
            except Exception as e:
                return jsonify({
                    'ok': False,
                    'error': f'命令构建失败 (desc={desc}): {e}',
                }), 400

            # 安全检查
            if not _is_safe_command(command):
                return jsonify({
                    'ok': False,
                    'error': f'命令包含不安全字符 (desc={desc})',
                }), 400

            built_cmd = {'command': command, 'desc': desc}
            if timeout:
                built_cmd['timeout_ms'] = timeout
            built_commands.append(built_cmd)

        # 4. 批量执行
        results = ArthasCommandExecutor.execute_batch(
            connection,
            built_commands,
            fail_fast=fail_fast,
        )

        return jsonify({
            'ok': True,
            'results': results,
            'total': len(results),
            'success_count': sum(1 for r in results if r.get('success')),
            'fail_count': sum(1 for r in results if not r.get('success')),
        })

    except Exception as e:
        log.error("Batch execute failed: %s\n%s", e, traceback.format_exc())
        return jsonify({'ok': False, 'error': f'批量执行失败: {str(e)}'}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# 内部执行函数
# ═══════════════════════════════════════════════════════════════════════════════

def _execute_single_command(
    capability: Dict[str, Any],
    connection,
    params: Dict[str, Any],
    mode: str,
    user_id: Optional[int],
):
    """执行单命令能力（快捷工具 / 诊断模板）"""
    arthas_command = capability.get('arthas_command', '')
    parameters_schema = capability.get('parameters_schema', '{}')

    # 参数校验 + 命令构建
    build_result = _validate_and_build_command(
        arthas_command, parameters_schema, params
    )
    if not build_result['ok']:
        return jsonify({'ok': False, 'error': build_result['error']}), 400

    command = build_result['command']

    # 检查高危命令
    cmd_name = ArthasCommandExecutor._parse_command_name(command)
    from backend.core.arthas_executor import _HIGH_RISK_COMMANDS
    if cmd_name in _HIGH_RISK_COMMANDS:
        return jsonify({
            'ok': False,
            'error': f'命令 {cmd_name} 为高危操作，需要 confirmed=true',
            'require_confirm': True,
            'command': command,
        }), 400

    # 异步模式
    if mode == 'async':
        exec_id = ArthasCommandExecutor.execute_async(
            connection, command, user_id=user_id
        )
        return jsonify({
            'ok': True,
            'execution_id': exec_id,
            'mode': 'async',
            'command': command,
        }), 202

    # 同步模式
    result = ArthasCommandExecutor.execute(
        connection,
        command,
        skip_audit=False,
        skip_history=False,
    )

    return jsonify({
        'ok': True,
        'result': result,
        'command': command,
        'capability': capability.get('name', ''),
    })


def _execute_scenario(
    capability: Dict[str, Any],
    connection,
    params: Dict[str, Any],
    mode: str,
    user_id: Optional[int],
):
    """执行场景方案（多步骤 DSL）"""
    steps_json = capability.get('steps_json', '{}')
    parameters_schema = capability.get('parameters_schema', '{}')

    try:
        steps = json.loads(steps_json).get('steps', [])
    except (json.JSONDecodeError, TypeError):
        return jsonify({'ok': False, 'error': 'DSL 格式错误'}), 400

    if not steps:
        return jsonify({'ok': False, 'error': 'DSL 中未定义步骤'}), 400

    # 校验全局参数
    if parameters_schema:
        validation_error = ParameterValidator.validate(parameters_schema, params)
        if validation_error:
            return jsonify({'ok': False, 'error': validation_error}), 400

    # 构建所有步骤命令
    built_steps = []
    step_outputs = {}
    for idx, step in enumerate(steps, start=1):
        raw_cmd = step.get('command', '')
        desc = step.get('desc', f'Step {idx}')

        try:
            command = build_command(raw_cmd, params, step_outputs)
        except Exception as e:
            return jsonify({
                'ok': False,
                'error': f'步骤 {idx} 命令构建失败: {e}',
            }), 400

        if not _is_safe_command(command):
            return jsonify({
                'ok': False,
                'error': f'步骤 {idx} 命令包含不安全字符',
            }), 400

        built_steps.append({
            'command': command,
            'desc': desc,
            'timeout_ms': step.get('timeout_ms'),
        })

    # 异步模式：通过 WorkflowEngine 异步执行
    if mode == 'async':
        try:
            from services.workflow_engine import get_workflow_engine
            engine = get_workflow_engine()
            run_id = engine.execute_skill(
                capability_id=capability['id'],
                params=params,
                connection_id=getattr(connection, 'connection_id', ''),
                user_id=user_id,
            )
            return jsonify({
                'ok': True,
                'execution_id': run_id,
                'mode': 'async',
            }), 202
        except Exception as e:
            return jsonify({'ok': False, 'error': f'异步执行启动失败: {e}'}), 500

    # 同步模式：批量执行
    results = ArthasCommandExecutor.execute_batch(
        connection,
        built_steps,
        fail_fast=True,
    )

    return jsonify({
        'ok': True,
        'results': results,
        'total': len(results),
        'success_count': sum(1 for r in results if r.get('success')),
        'fail_count': sum(1 for r in results if not r.get('success')),
        'capability': capability.get('name', ''),
    })


def _execute_handler(
    capability: Dict[str, Any],
    connection,
    params: Dict[str, Any],
    mode: str,
    user_id: Optional[int],
):
    """执行 AI 诊断（handler）"""
    handler_path = capability.get('handler', '')
    if not handler_path:
        return jsonify({'ok': False, 'error': '能力未配置 handler'}), 400

    # 通过 WorkflowEngine 执行 handler
    try:
        from services.workflow_engine import get_workflow_engine
        engine = get_workflow_engine()
        run_id = engine.execute_skill(
            capability_id=capability['id'],
            params=params,
            connection_id=getattr(connection, 'connection_id', ''),
            user_id=user_id,
        )
        return jsonify({
            'ok': True,
            'execution_id': run_id,
            'mode': 'async',
            'handler': handler_path,
        }), 202
    except Exception as e:
        log.error("Execute handler failed: %s", e)
        return jsonify({'ok': False, 'error': f'Handler 执行失败: {e}'}), 500
