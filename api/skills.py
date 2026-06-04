#!/usr/bin/env python3
"""Skill 管理 API - REST接口"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from services.skill_registry import get_skill_registry
from services.workflow_engine import get_workflow_engine
from services.agent_tool_gateway import get_agent_tool_gateway
import logging

log = logging.getLogger(__name__)

skills_bp = Blueprint('skills', __name__, url_prefix='/api/skills')


# ═══════════════════════════════════════════════════════════════════════════════
# Skill Registry API
# ═══════════════════════════════════════════════════════════════════════════════

@skills_bp.route('/registry', methods=['GET'])
@login_required
def list_skills():
    """列出 Skills"""
    try:
        registry = get_skill_registry()

        # 获取查询参数
        status = request.args.get('status')
        category = request.args.get('category')
        source = request.args.get('source')
        keyword = request.args.get('keyword')

        # 搜索或列表
        if keyword:
            skills = registry.search_skills(keyword)
        else:
            skills = registry.list_skills(status=status, category=category, source=source)

        return jsonify({
            'ok': True,
            'skills': skills,
            'total': len(skills)
        })
    except Exception as e:
        log.error(f"List skills failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/<int:skill_id>', methods=['GET'])
@login_required
def get_skill(skill_id):
    """获取 Skill 详情"""
    try:
        registry = get_skill_registry()
        skill = registry.get_skill(skill_id)

        if not skill:
            return jsonify({'ok': False, 'error': 'Skill not found'}), 404

        return jsonify({
            'ok': True,
            'skill': skill
        })
    except Exception as e:
        log.error(f"Get skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/import', methods=['POST'])
@login_required
def import_skill():
    """导入 Skill"""
    try:
        registry = get_skill_registry()

        # 检查是否是文件上传
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                # 保存到临时目录
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                    file.save(tmp.name)
                    skill_id = registry.import_from_file(tmp.name, current_user.id)
                    os.unlink(tmp.name)
                return jsonify({
                    'ok': True,
                    'skill_id': skill_id,
                    'message': 'Skill imported successfully'
                }), 201

        # JSON格式导入
        skill_data = request.get_json()
        if not skill_data:
            return jsonify({'ok': False, 'error': 'No skill data provided'}), 400

        skill_id = registry.import_skill(skill_data, current_user.id)

        return jsonify({
            'ok': True,
            'skill_id': skill_id,
            'message': 'Skill imported successfully'
        }), 201

    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Import skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/<int:skill_id>/validate', methods=['POST'])
@login_required
def validate_skill(skill_id):
    """校验 Skill"""
    try:
        registry = get_skill_registry()
        is_valid, errors = registry.validate_skill(skill_id)

        if is_valid:
            return jsonify({
                'ok': True,
                'message': 'Skill validation passed'
            })
        else:
            return jsonify({
                'ok': False,
                'errors': errors
            }), 400

    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except Exception as e:
        log.error(f"Validate skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/<int:skill_id>/publish', methods=['POST'])
@login_required
def publish_skill(skill_id):
    """发布 Skill"""
    try:
        registry = get_skill_registry()
        capability_id = registry.publish_skill(skill_id, current_user.id)

        return jsonify({
            'ok': True,
            'capability_id': capability_id,
            'message': 'Skill published successfully'
        })

    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Publish skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/<int:skill_id>', methods=['PUT'])
@login_required
def update_skill(skill_id):
    """更新 Skill"""
    try:
        registry = get_skill_registry()
        updates = request.get_json()

        if not updates:
            return jsonify({'ok': False, 'error': 'No updates provided'}), 400

        success = registry.update_skill(skill_id, updates)

        if success:
            return jsonify({
                'ok': True,
                'message': 'Skill updated successfully'
            })
        else:
            return jsonify({
                'ok': False,
                'message': 'No changes made'
            })

    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Update skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/<int:skill_id>', methods=['DELETE'])
@login_required
def delete_skill(skill_id):
    """删除 Skill"""
    try:
        registry = get_skill_registry()
        success = registry.delete_skill(skill_id)

        if success:
            return jsonify({
                'ok': True,
                'message': 'Skill deleted successfully'
            })
        else:
            return jsonify({
                'ok': False,
                'message': 'Failed to delete skill'
            }), 500

    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Delete skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/stats', methods=['GET'])
@login_required
def get_stats():
    """获取 Skill 统计信息"""
    try:
        registry = get_skill_registry()
        stats = registry.get_skill_stats()

        return jsonify({
            'ok': True,
            'stats': stats
        })
    except Exception as e:
        log.error(f"Get stats failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow Engine API
# ═══════════════════════════════════════════════════════════════════════════════

@skills_bp.route('/orchestrator/execute', methods=['POST'])
@login_required
def execute_skill():
    """执行 Skill"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No data provided'}), 400

        capability_id = data.get('capability_id')
        connection_id = data.get('connection_id')
        params = data.get('params', {})

        if not capability_id:
            return jsonify({'ok': False, 'error': 'capability_id is required'}), 400
        if not connection_id:
            return jsonify({'ok': False, 'error': 'connection_id is required'}), 400

        engine = get_workflow_engine()
        run_id = engine.execute_skill(
            capability_id=capability_id,
            params=params,
            connection_id=connection_id,
            user_id=current_user.id
        )

        return jsonify({
            'ok': True,
            'run_id': run_id,
            'message': 'Skill execution started'
        }), 201

    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Execute skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/orchestrator/runs/<run_id>/status', methods=['GET'])
@login_required
def get_run_status(run_id):
    """查询执行状态"""
    try:
        engine = get_workflow_engine()
        status = engine.get_run_status(run_id)

        if not status:
            return jsonify({'ok': False, 'error': 'Run not found'}), 404

        return jsonify({
            'ok': True,
            'status': status
        })
    except Exception as e:
        log.error(f"Get run status failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/orchestrator/runs/<run_id>/steps', methods=['GET'])
@login_required
def get_step_logs(run_id):
    """获取步骤日志"""
    try:
        engine = get_workflow_engine()
        steps = engine.get_step_logs(run_id)

        return jsonify({
            'ok': True,
            'steps': steps,
            'total': len(steps)
        })
    except Exception as e:
        log.error(f"Get step logs failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/orchestrator/runs/<run_id>/cancel', methods=['POST'])
@login_required
def cancel_run(run_id):
    """取消执行"""
    try:
        engine = get_workflow_engine()
        success = engine.cancel_run(run_id)

        if success:
            return jsonify({
                'ok': True,
                'message': 'Run cancelled successfully'
            })
        else:
            return jsonify({
                'ok': False,
                'message': 'Failed to cancel run'
            }), 400

    except Exception as e:
        log.error(f"Cancel run failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Tool Gateway API
# ═══════════════════════════════════════════════════════════════════════════════

@skills_bp.route('/agent/tools', methods=['GET'])
@login_required
def list_agent_tools():
    """列出可用工具"""
    try:
        gateway = get_agent_tool_gateway()
        tools = gateway.get_tool_definitions()

        return jsonify({
            'ok': True,
            'tools': tools,
            'total': len(tools)
        })
    except Exception as e:
        log.error(f"List agent tools failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/agent/tools/<tool_name>/execute', methods=['POST'])
@login_required
def execute_agent_tool(tool_name):
    """执行工具（Agent调用）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No data provided'}), 400

        params = data.get('params', {})
        context = data.get('context', {})

        # 添加用户信息到上下文
        context['user_id'] = current_user.id

        gateway = get_agent_tool_gateway()
        result = gateway.execute_tool(
            tool_name=tool_name,
            params=params,
            user_id=current_user.id,
            context=context
        )

        if result.get('success'):
            return jsonify({
                'ok': True,
                'result': result.get('result')
            })
        else:
            return jsonify({
                'ok': False,
                'error': result.get('error', 'Unknown error')
            }), 400

    except Exception as e:
        log.error(f"Execute agent tool failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
