#!/usr/bin/env python3
"""工具箱 API - 诊断能力市场

路由:
  GET  /api/toolbox/capabilities           - 获取能力目录
  GET  /api/toolbox/capabilities/<id>      - 获取能力详情
  POST /api/toolbox/capabilities/<id>/execute - 执行诊断能力
"""
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models.db import db
from services.authorization_service import AuthorizationService
from services.audit_service import AuditService
from services.safety_service import SafetyService

log = logging.getLogger(__name__)

toolbox_bp = Blueprint('toolbox', __name__, url_prefix='/api/toolbox')


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def _error(message: str, status: int = 400):
    return jsonify({'error': message}), status


def _row_to_capability(row: Dict[str, Any]) -> Dict[str, Any]:
    """将数据库行转换为能力对象"""
    item = dict(row)
    item['parameters_schema'] = json.loads(item.get('parameters_schema') or '{}')
    item['prerequisites'] = json.loads(item.get('prerequisites') or '[]')
    item['related_capabilities'] = json.loads(item.get('related_capabilities') or '[]')
    if item.get('steps_json'):
        item['steps'] = json.loads(item['steps_json'])
    item.pop('steps_json', None)
    return item


def _validate_parameters(schema: list, params: dict) -> Optional[str]:
    """校验参数是否符合 schema 定义"""
    for field in schema:
        name = field['name']
        required = field.get('required', False)
        default = field.get('default')
        pattern = field.get('pattern')
        
        value = params.get(name, default)
        
        # 必填校验
        if required and not value:
            return f"缺少必填参数: {field.get('label', name)}"
        
        # 正则校验
        if value and pattern:
            if not re.match(pattern, str(value)):
                return f"参数 {field.get('label', name)} 格式不正确"
    
    return None


def _build_command(command_template: str, params: dict) -> str:
    """将参数替换到命令模板中"""
    command = command_template
    for key, value in params.items():
        placeholder = f"${{{key}}}"
        command = command.replace(placeholder, str(value))
    return command


def _get_connection(conn_id: str):
    """获取 Arthas 连接"""
    try:
        from server import _connections, _connections_lock
    except ImportError:
        return None, "服务未初始化"
    
    with _connections_lock:
        entry = _connections.get(conn_id)
        if not entry:
            # 模糊匹配
            for cid in _connections:
                if conn_id in cid or cid in conn_id:
                    entry = _connections[cid]
                    break
        
        if not entry:
            return None, "连接不存在"
        
        # 权限检查
        if not current_user.is_admin and entry.get('user_id') != current_user.id:
            return None, "无权操作此连接"
        
        conn = entry.get('conn')
        if not conn:
            return None, "连接对象为空"
        
        return conn, None


# ═══════════════════════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════════════════════

@toolbox_bp.route('/capabilities', methods=['GET'])
@login_required
def list_capabilities():
    """获取诊断能力目录,支持按 category/level 筛选"""
    category = request.args.get('category', '')
    level = request.args.get('level', '')
    
    where = "1=1"
    params = []
    
    if category:
        where += " AND category = ?"
        params.append(category)
    
    if level:
        where += " AND level = ?"
        params.append(int(level))
    
    rows = db.fetch_all(
        f"SELECT * FROM diagnosis_capabilities WHERE {where} ORDER BY level ASC, id ASC",
        tuple(params)
    )
    
    return jsonify({
        'capabilities': [_row_to_capability(row) for row in rows],
        'count': len(rows)
    })


@toolbox_bp.route('/capabilities/<int:cap_id>', methods=['GET'])
@login_required
def get_capability(cap_id: int):
    """获取能力详情(含参数定义、关联推荐)"""
    row = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    if not row:
        return _error('能力不存在', 404)
    
    return jsonify({'capability': _row_to_capability(row)})


@toolbox_bp.route('/capabilities/<int:cap_id>/execute', methods=['POST'])
@login_required
def execute_capability(cap_id: int):
    """执行诊断能力
    
    - level 1/2: 直接调用 Arthas HTTP API
    - level 3: 按 steps 顺序执行,返回中间结果
    - level 4: 调用智能诊断引擎
    """
    row = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (cap_id,))
    if not row:
        return _error('能力不存在', 404)
    
    capability = _row_to_capability(row)
    data = request.json or {}
    
    # 获取连接
    conn_id = data.get('connection_id', '')
    if not conn_id:
        return _error('connection_id 为必填项')
    
    conn, err = _get_connection(conn_id)
    if err:
        return _error(err)
    
    # 高危能力二次确认
    if capability.get('risk_level') == 'high' and not data.get('confirmed'):
        return jsonify({
            'error': '此操作为高危操作,需要二次确认',
            'require_confirm': True,
            'capability': capability,
        }), 400
    
    # 参数校验
    params = data.get('params', {})
    if capability.get('parameters_schema'):
        error = _validate_parameters(capability['parameters_schema'], params)
        if error:
            return _error(error)
    
    # 执行能力
    started_at = time.time()
    try:
        if capability['level'] <= 2:
            # 单步执行:直接调用 Arthas HTTP API
            result = _execute_single_step(conn, capability, params)
        elif capability['level'] == 3:
            # 多步执行:场景方案
            result = _execute_multi_steps(conn, capability, params)
        elif capability['level'] == 4:
            # 智能诊断
            result = _execute_ai_diagnosis(conn, capability, params)
        else:
            return _error(f'不支持的能力层级: {capability["level"]}')
        
        duration_ms = int((time.time() - started_at) * 1000)
        result['duration_ms'] = duration_ms
        result['capability_id'] = cap_id
        result['capability_name'] = capability['name']
        
        # 记录审计
        try:
            AuditService.log_event(
                user_id=current_user.id,
                action='toolbox_capability_execute',
                resource_type='diagnosis_capability',
                resource_id=str(cap_id),
                details=f"执行能力: {capability['name']}, 耗时: {duration_ms}ms"
            )
        except Exception:
            pass
        
        return jsonify({'ok': True, 'result': result})
    
    except Exception as e:
        log.error(f"执行能力 {cap_id} 失败: {e}", exc_info=True)
        duration_ms = int((time.time() - started_at) * 1000)
        return _error(f'执行失败: {str(e)}', 500)


def _execute_single_step(conn, capability: dict, params: dict) -> dict:
    """执行单步能力(level 1/2)"""
    command_template = capability.get('arthas_command', '')
    if not command_template:
        raise ValueError('能力未定义 Arthas 命令')
    
    # 构建命令
    command = _build_command(command_template, params)
    
    # 执行 Arthas 命令
    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        client = conn.http_client
        response = ArthasCommandExecutor.execute(conn, command, timeout_ms=30000)
        
        # 脱敏输出
        output = json.dumps(response, ensure_ascii=False)
        masked_output = SafetyService.mask_sensitive_output(output)
        
        return {
            'command': command,
            'output': response,
            'masked_output': masked_output,
            'status': 'success',
            'related_capabilities': capability.get('related_capabilities', []),
        }
    except Exception as e:
        return {
            'command': command,
            'error': str(e),
            'status': 'failed',
        }


def _execute_multi_steps(conn, capability: dict, params: dict) -> dict:
    """执行多步能力(level 3 - 场景方案)"""
    steps = capability.get('steps', [])
    if not steps:
        raise ValueError('场景方案未定义执行步骤')
    
    results = []
    
    for step in steps:
        step_num = step.get('step', 0)
        command = _build_command(step.get('command', ''), params)
        desc = step.get('desc', '')
        
        try:
            from backend.core.arthas_executor import ArthasCommandExecutor
            client = conn.http_client
            response = ArthasCommandExecutor.execute(conn, command, timeout_ms=60000)
            
            output = json.dumps(response, ensure_ascii=False)
            masked_output = SafetyService.mask_sensitive_output(output)
            
            results.append({
                'step': step_num,
                'desc': desc,
                'command': command,
                'output': response,
                'masked_output': masked_output,
                'status': 'success',
            })
        except Exception as e:
            results.append({
                'step': step_num,
                'desc': desc,
                'command': command,
                'error': str(e),
                'status': 'failed',
            })
            # 某步失败不中断后续步骤
    
    return {
        'steps': results,
        'total_steps': len(steps),
        'success_steps': len([r for r in results if r['status'] == 'success']),
        'related_capabilities': capability.get('related_capabilities', []),
    }


def _execute_ai_diagnosis(conn, capability: dict, params: dict) -> dict:
    """执行智能诊断(level 4)"""
    handler = capability.get('handler', '')
    
    if handler == 'performance_diagnose.run_diagnosis':
        from api.performance_diagnose import _run_diagnosis
        
        target = params.get('target', 'general')
        class_pattern = params.get('class_pattern', '')
        method_pattern = params.get('method_pattern', '')
        
        diagnosis = _run_diagnosis(conn, target, class_pattern, method_pattern)
        
        return {
            'diagnosis': diagnosis,
            'type': 'ai_diagnosis',
            'related_capabilities': capability.get('related_capabilities', []),
        }
    else:
        raise ValueError(f'不支持的智能诊断处理器: {handler}')
