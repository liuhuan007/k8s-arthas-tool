#!/usr/bin/env python3
"""API 蓝图注册中心"""
from flask import Flask


def register_blueprints(app: Flask):
    """注册所有 API 蓝图"""
    from api.auth import auth_bp
    from api.users import users_bp
    from api.clusters import clusters_bp
    from api.audit import audit_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(clusters_bp)
    app.register_blueprint(audit_bp)
    
    # 其他 API 蓝图可以在此添加
    # from api.arthas import arthas_bp
    # app.register_blueprint(arthas_bp)