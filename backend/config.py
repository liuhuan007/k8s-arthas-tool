#!/usr/bin/env python3
"""配置管理模块"""
import os
import secrets
import warnings


class Config:
    """应用配置"""

    # 基础路径
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 数据库
    DB_FILE = os.environ.get('DB_FILE', os.path.join(BASE_DIR, 'data', 'db', 'arthas.db'))

    # 配置文件
    CLUSTERS_FILE = os.environ.get('CLUSTERS_FILE', os.path.join(BASE_DIR, 'data', 'conf', 'clusters.json'))
    EXTERNAL_LINKS_FILE = os.environ.get('EXTERNAL_LINKS_FILE', os.path.join(BASE_DIR, 'data', 'conf', 'external_links.json'))

    # Flask - 未设置环境变量时自动生成随机密钥
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    STATIC_FOLDER = 'static'
    STATIC_URL_PATH = ''  # 空字符串：从根路径提供静态文件 (如 /js/core/api.js)
    
    # 默认页面
    DEFAULT_PAGE = 'login.html'
    
    # 服务器
    DEFAULT_PORT = int(os.environ.get('PORT', 5001))
    DEFAULT_HOST = os.environ.get('HOST', '127.0.0.1')
    
    # 输出目录
    OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'data/profiler')
    
    # 认证
    MIN_PASSWORD_LENGTH = 6
    
    # 分页
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 500

    # ── Phase 5: 健康检查配置 ──────────────────────────────────────────────
    # 健康检查后台线程扫描间隔（秒），默认 30 秒
    HEALTH_CHECK_INTERVAL_SECONDS = int(os.environ.get('HEALTH_CHECK_INTERVAL_SECONDS', '30'))
    # TTL 清理扫描间隔（秒），默认 300 秒（5 分钟）
    TTL_CLEANUP_INTERVAL_SECONDS = int(os.environ.get('TTL_CLEANUP_INTERVAL_SECONDS', '300'))
    # 默认 TTL 过期阈值（分钟），当连接未设置自定义 TTL 时使用此值，0 表示不自动过期
    DEFAULT_TTL_THRESHOLD_MINUTES = int(os.environ.get('DEFAULT_TTL_THRESHOLD_MINUTES', '30'))
    # 健康检查日志保留天数
    HEALTH_CHECK_LOG_RETENTION_DAYS = int(os.environ.get('HEALTH_CHECK_LOG_RETENTION_DAYS', '7'))

    @classmethod
    def validate_production(cls):
        """启动时校验生产环境安全配置"""
        if not os.environ.get('SECRET_KEY'):
            warnings.warn(
                "⚠ SECRET_KEY 未设置，当前使用随机生成值（重启后会话失效）。生产环境请设置 SECRET_KEY 环境变量！",
                stacklevel=2
            )