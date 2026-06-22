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


# ═══════════════════════════════════════════════════════════════════════════════
# Skill Marketplace API
# ═══════════════════════════════════════════════════════════════════════════════

@skills_bp.route('/marketplace/sources', methods=['GET'])
@login_required
def list_marketplace_sources():
    """列出市场源"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        sources = get_skill_marketplace().list_sources()
        return jsonify({'ok': True, 'sources': sources, 'total': len(sources)})
    except Exception as e:
        log.error(f"List marketplace sources failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/sources', methods=['POST'])
@login_required
def add_marketplace_source():
    """添加市场源"""
    try:
        data = request.get_json()
        if not data or not data.get('name') or not data.get('repo_url'):
            return jsonify({'ok': False, 'error': 'name and repo_url are required'}), 400

        from services.skill_marketplace import get_skill_marketplace
        source_id = get_skill_marketplace().add_source(
            name=data['name'],
            repo_url=data['repo_url'],
            branch=data.get('branch', 'main')
        )
        return jsonify({'ok': True, 'source_id': source_id, 'message': 'Source added'}), 201
    except Exception as e:
        log.error(f"Add marketplace source failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/sources/<int:source_id>', methods=['PUT'])
@login_required
def update_marketplace_source(source_id):
    """更新市场源"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'no data'}), 400
        if data.get('name') is not None and not data['name'].strip():
            return jsonify({'ok': False, 'error': 'name cannot be empty'}), 400
        if data.get('repo_url') is not None and not data['repo_url'].strip():
            return jsonify({'ok': False, 'error': 'repo_url cannot be empty'}), 400

        from services.skill_marketplace import get_skill_marketplace
        get_skill_marketplace().update_source(
            source_id,
            name=data.get('name'),
            repo_url=data.get('repo_url'),
            branch=data.get('branch')
        )
        return jsonify({'ok': True, 'message': 'Source updated'})
    except Exception as e:
        log.error(f"Update marketplace source failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/sources/<int:source_id>', methods=['DELETE'])
@login_required
def remove_marketplace_source(source_id):
    """删除市场源"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        get_skill_marketplace().remove_source(source_id)
        return jsonify({'ok': True, 'message': 'Source removed'})
    except Exception as e:
        log.error(f"Remove marketplace source failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/sources/<int:source_id>/sync', methods=['POST'])
@login_required
def sync_marketplace_source(source_id):
    """异步同步市场源（立即返回，后台执行）"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        status = get_skill_marketplace().sync_source_async(source_id)
        return jsonify({'ok': True, 'sync_status': status})
    except Exception as e:
        log.error(f"Sync marketplace source failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/sources/<int:source_id>/sync-status', methods=['GET'])
@login_required
def sync_marketplace_status(source_id):
    """查询同步状态"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        status = get_skill_marketplace().get_sync_status(source_id)
        return jsonify({'ok': True, 'sync_status': status})
    except Exception as e:
        log.error(f"Sync status check failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/browse', methods=['GET'])
@login_required
def browse_marketplace():
    """浏览市场技能"""
    try:
        source_id = request.args.get('source_id', type=int)
        keyword = request.args.get('keyword')
        category = request.args.get('category')

        from services.skill_marketplace import get_skill_marketplace
        skills = get_skill_marketplace().browse(source_id=source_id, keyword=keyword, category=category)
        return jsonify({'ok': True, 'skills': skills, 'total': len(skills)})
    except Exception as e:
        log.error(f"Browse marketplace failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/install/<int:source_id>/<skill_name>', methods=['POST'])
@login_required
def install_marketplace_skill(source_id, skill_name):
    """安装市场技能"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        skill_id = get_skill_marketplace().install(source_id, skill_name, current_user.id)
        return jsonify({'ok': True, 'skill_id': skill_id, 'message': f'Skill "{skill_name}" installed'}), 201
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Install marketplace skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/updates', methods=['GET'])
@login_required
def check_marketplace_updates():
    """检查可更新技能"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        updates = get_skill_marketplace().check_updates()
        return jsonify({'ok': True, 'updates': updates, 'total': len(updates)})
    except Exception as e:
        log.error(f"Check marketplace updates failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/marketplace/update/<int:skill_id>', methods=['POST'])
@login_required
def update_marketplace_skill(skill_id):
    """更新市场技能"""
    try:
        from services.skill_marketplace import get_skill_marketplace
        new_skill_id = get_skill_marketplace().update_skill(skill_id, current_user.id)
        return jsonify({'ok': True, 'skill_id': new_skill_id, 'message': 'Skill updated'})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Update marketplace skill failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@skills_bp.route('/registry/import-from-github', methods=['POST'])
@login_required
def import_from_github():
    """从 GitHub 仓库直接导入 skill（不经过市场）"""
    try:
        data = request.get_json()
        if not data or not data.get('repo_url'):
            return jsonify({'ok': False, 'error': 'repo_url is required'}), 400

        repo_url = data['repo_url']
        branch = data.get('branch', 'main')
        selected = data.get('selected_skills')  # None 表示全部

        import tempfile, os, subprocess, shutil
        from pathlib import Path
        from services.skill_marketplace import SkillMarketplace

        temp_dir = tempfile.mkdtemp(prefix="github_import_")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "-b", branch, repo_url, temp_dir],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

            scanner = SkillMarketplace()
            discovered = scanner._scan_repo(temp_dir)

            if selected:
                discovered = [s for s in discovered if s.get("name") in selected]

            registry = get_skill_registry()
            imported = []
            for skill_meta in discovered:
                skill_dir = Path(temp_dir) / skill_meta.get("path", skill_meta.get("name", ""))
                skill_data = scanner._load_skill_file(skill_dir)
                if not skill_data:
                    continue
                skill_data["source"] = "imported"
                try:
                    sid = registry.import_skill(skill_data, current_user.id)
                    imported.append({"name": skill_data.get("name"), "skill_id": sid})
                except Exception as e:
                    log.warning("Import skill '%s' failed: %s", skill_data.get("name"), e)

            return jsonify({'ok': True, 'imported': imported, 'total': len(imported)})

        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        log.error(f"Import from GitHub failed: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
