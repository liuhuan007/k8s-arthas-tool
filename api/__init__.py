#!/usr/bin/env python3
"""API 蓝图注册中心"""
from flask import Flask


def register_blueprints(app: Flask):
    """注册所有 API 蓝图"""
    from api.auth import auth_bp
    from api.users import users_bp
    from api.clusters import clusters_bp
    from api.audit import audit_bp
    from api.mcp_proxy import mcp_bp
    from api.ai_chat import ai_bp
    from api.performance_diagnose import diag_bp
    from api.task_center import task_bp
    from api.hotfix import hotfix_bp
    from api.skills import skills_bp
    from api.diagnosis import diagnosis_bp
    from api.connection_detail import connection_detail_bp
    from api.profiler import profiler_bp
    from api.anomaly import anomaly_bp
    from api.agent import agent_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(clusters_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(mcp_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(diag_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(hotfix_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(diagnosis_bp)
    app.register_blueprint(connection_detail_bp)
    app.register_blueprint(profiler_bp)
    app.register_blueprint(anomaly_bp)
    app.register_blueprint(agent_bp)
