#!/usr/bin/env python3
"""Knowledge Base API - 诊断案例库 & 解决方案手册"""
from datetime import datetime
import json
import logging

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models.db import db
from services.audit_service import AuditService

log = logging.getLogger(__name__)

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/api/knowledge')

VALID_SEVERITIES = ('low', 'medium', 'high', 'critical')
VALID_STATUSES = ('draft', 'published', 'archived')


# ═══════════════════════════════════════════════════════════════════════════════
# Cases CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@knowledge_bp.route('/cases', methods=['GET'])
@login_required
def list_cases():
    """列出案例（支持 status/severity/capability_id/keyword 过滤）"""
    try:
        status = request.args.get('status')
        severity = request.args.get('severity')
        capability_id = request.args.get('capability_id')
        keyword = request.args.get('keyword', '').strip()
        page = max(int(request.args.get('page', 1)), 1)
        page_size = min(int(request.args.get('page_size', 20)), 100)
        offset = (page - 1) * page_size

        sql = 'SELECT * FROM diagnosis_cases WHERE 1=1'
        count_sql = 'SELECT COUNT(*) as cnt FROM diagnosis_cases WHERE 1=1'
        params = []

        if status:
            sql += ' AND status = ?'
            count_sql += ' AND status = ?'
            params.append(status)
        if severity:
            sql += ' AND severity = ?'
            count_sql += ' AND severity = ?'
            params.append(severity)
        if capability_id:
            sql += ' AND capability_id = ?'
            count_sql += ' AND capability_id = ?'
            params.append(capability_id)
        if keyword:
            like = f'%{keyword}%'
            sql += ' AND (title LIKE ? OR description LIKE ? OR symptoms LIKE ? OR root_cause LIKE ?)'
            count_sql += ' AND (title LIKE ? OR description LIKE ? OR symptoms LIKE ? OR root_cause LIKE ?)'
            params.extend([like, like, like, like])

        total = db.fetch_one(count_sql, tuple(params))
        total = total['cnt'] if total else 0

        sql += ' ORDER BY updated_at DESC LIMIT ? OFFSET ?'
        cases = db.fetch_all(sql, tuple(params) + (page_size, offset))

        return jsonify({
            'ok': True,
            'cases': cases,
            'total': total,
            'page': page,
            'page_size': page_size,
        })
    except Exception as e:
        log.error("List cases failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@knowledge_bp.route('/cases/<int:case_id>', methods=['GET'])
@login_required
def get_case(case_id):
    """获取单个案例详情"""
    try:
        case = db.fetch_one('SELECT * FROM diagnosis_cases WHERE id = ?', (case_id,))
        if not case:
            return jsonify({'ok': False, 'error': 'Case not found'}), 404
        return jsonify({'ok': True, 'case': case})
    except Exception as e:
        log.error("Get case failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@knowledge_bp.route('/cases', methods=['POST'])
@login_required
def create_case():
    """创建案例（仅管理员）"""
    if not current_user.is_admin:
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403
    try:
        data = request.get_json()
        if not data or not data.get('title'):
            return jsonify({'ok': False, 'error': 'title is required'}), 400

        severity = data.get('severity', 'medium')
        if severity not in VALID_SEVERITIES:
            return jsonify({'ok': False, 'error': f'Invalid severity: {severity}'}), 400

        status = data.get('status', 'draft')
        if status not in VALID_STATUSES:
            return jsonify({'ok': False, 'error': f'Invalid status: {status}'}), 400

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        case_id = db.insert('diagnosis_cases', {
            'title': data['title'],
            'description': data.get('description', ''),
            'symptoms': json.dumps(data['symptoms'], ensure_ascii=False) if isinstance(data.get('symptoms'), list) else data.get('symptoms', ''),
            'root_cause': data.get('root_cause', ''),
            'solution': data.get('solution', ''),
            'capability_id': data.get('capability_id', ''),
            'tags': json.dumps(data['tags'], ensure_ascii=False) if isinstance(data.get('tags'), list) else data.get('tags', ''),
            'severity': severity,
            'status': status,
            'match_count': 0,
            'created_by': current_user.id,
            'created_at': now,
            'updated_at': now,
        })

        AuditService.log_event(
            current_user.id, 'knowledge_case_created', 'diagnosis_case',
            str(case_id), f'Created case: {data["title"]}'
        )

        return jsonify({'ok': True, 'case_id': case_id}), 201
    except Exception as e:
        log.error("Create case failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@knowledge_bp.route('/cases/<int:case_id>', methods=['PUT'])
@login_required
def update_case(case_id):
    """更新案例（仅管理员）"""
    if not current_user.is_admin:
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403
    try:
        existing = db.fetch_one('SELECT id FROM diagnosis_cases WHERE id = ?', (case_id,))
        if not existing:
            return jsonify({'ok': False, 'error': 'Case not found'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'No data provided'}), 400

        allowed = ('title', 'description', 'symptoms', 'root_cause', 'solution',
                   'capability_id', 'tags', 'severity', 'status')
        updates = {}
        for field in allowed:
            if field in data:
                val = data[field]
                if field in ('symptoms', 'tags') and isinstance(val, list):
                    val = json.dumps(val, ensure_ascii=False)
                updates[field] = val

        if 'severity' in updates and updates['severity'] not in VALID_SEVERITIES:
            return jsonify({'ok': False, 'error': f'Invalid severity: {updates["severity"]}'}), 400
        if 'status' in updates and updates['status'] not in VALID_STATUSES:
            return jsonify({'ok': False, 'error': f'Invalid status: {updates["status"]}'}), 400

        if not updates:
            return jsonify({'ok': False, 'error': 'No valid fields to update'}), 400

        updates['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.update('diagnosis_cases', updates, 'id = ?', (case_id,))

        AuditService.log_event(
            current_user.id, 'knowledge_case_updated', 'diagnosis_case',
            str(case_id), f'Updated case fields: {list(updates.keys())}'
        )

        return jsonify({'ok': True, 'message': 'Case updated'})
    except Exception as e:
        log.error("Update case failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@knowledge_bp.route('/cases/<int:case_id>', methods=['DELETE'])
@login_required
def delete_case(case_id):
    """删除案例（仅管理员）"""
    if not current_user.is_admin:
        return jsonify({'ok': False, 'error': 'Admin access required'}), 403
    try:
        existing = db.fetch_one('SELECT id, title FROM diagnosis_cases WHERE id = ?', (case_id,))
        if not existing:
            return jsonify({'ok': False, 'error': 'Case not found'}), 404

        db.delete('diagnosis_cases', 'id = ?', (case_id,))

        AuditService.log_event(
            current_user.id, 'knowledge_case_deleted', 'diagnosis_case',
            str(case_id), f'Deleted case: {existing.get("title", "")}'
        )

        return jsonify({'ok': True, 'message': 'Case deleted'})
    except Exception as e:
        log.error("Delete case failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Match & Search
# ═══════════════════════════════════════════════════════════════════════════════

@knowledge_bp.route('/cases/<int:case_id>/match', methods=['POST'])
@login_required
def record_match(case_id):
    """记录一次案例匹配（递增 match_count）"""
    try:
        case = db.fetch_one('SELECT id, match_count FROM diagnosis_cases WHERE id = ?', (case_id,))
        if not case:
            return jsonify({'ok': False, 'error': 'Case not found'}), 404

        data = request.get_json() or {}
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        db.insert('case_matches', {
            'case_id': case_id,
            'execution_id': data.get('execution_id', ''),
            'match_score': data.get('match_score', 0),
            'matched_at': now,
        })

        db.update('diagnosis_cases', {
            'match_count': (case.get('match_count') or 0) + 1,
            'updated_at': now,
        }, 'id = ?', (case_id,))

        return jsonify({'ok': True, 'message': 'Match recorded'})
    except Exception as e:
        log.error("Record match failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@knowledge_bp.route('/search', methods=['GET'])
@login_required
def search_cases():
    """按症状/关键词模糊搜索案例"""
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({'ok': False, 'error': 'q (query) is required'}), 400

        like = f'%{q}%'
        sql = (
            'SELECT * FROM diagnosis_cases '
            'WHERE status = ? AND (title LIKE ? OR description LIKE ? OR symptoms LIKE ? '
            'OR root_cause LIKE ? OR solution LIKE ? OR tags LIKE ?) '
            'ORDER BY match_count DESC, updated_at DESC LIMIT 20'
        )
        cases = db.fetch_all(sql, ('published', like, like, like, like, like, like))

        return jsonify({'ok': True, 'cases': cases, 'total': len(cases), 'query': q})
    except Exception as e:
        log.error("Search cases failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@knowledge_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """知识库统计信息"""
    try:
        total = db.fetch_one('SELECT COUNT(*) as cnt FROM diagnosis_cases')
        total = total['cnt'] if total else 0

        by_severity = db.fetch_all(
            'SELECT severity, COUNT(*) as cnt FROM diagnosis_cases GROUP BY severity'
        )

        by_status = db.fetch_all(
            'SELECT status, COUNT(*) as cnt FROM diagnosis_cases GROUP BY status'
        )

        top_matched = db.fetch_all(
            'SELECT id, title, severity, match_count FROM diagnosis_cases '
            'WHERE status = ? ORDER BY match_count DESC LIMIT 10',
            ('published',)
        )

        return jsonify({
            'ok': True,
            'stats': {
                'total': total,
                'by_severity': {r['severity']: r['cnt'] for r in by_severity},
                'by_status': {r['status']: r['cnt'] for r in by_status},
                'top_matched': top_matched,
            }
        })
    except Exception as e:
        log.error("Get stats failed: %s", e)
        return jsonify({'ok': False, 'error': str(e)}), 500
