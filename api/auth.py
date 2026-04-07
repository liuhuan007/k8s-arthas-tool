#!/usr/bin/env python3
"""认证 API"""
from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required

from services.auth_service import AuthService

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    user, error = AuthService.login(username, password)
    
    if error:
        return jsonify({'error': error}), 401
    
    login_user(user)
    
    return jsonify({
        'ok': True,
        'user': user.to_dict()
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出（不要求 @login_required，确保已过期 session 也能正常登出）"""
    if current_user.is_authenticated:
        user_id = current_user.id
        username = current_user.username
        logout_user()
        AuthService.logout(user_id, username)
    else:
        logout_user()
    
    return jsonify({'ok': True})


@auth_bp.route('/current', methods=['GET'])
def current():
    """获取当前用户信息"""
    if not current_user.is_authenticated:
        return jsonify({'authenticated': False, 'user': None})
    
    return jsonify({
        'authenticated': True,
        'user': current_user.to_dict()
    })


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """修改当前用户密码"""
    data = request.json or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    error = AuthService.change_password(current_user.id, old_password, new_password)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({'ok': True})