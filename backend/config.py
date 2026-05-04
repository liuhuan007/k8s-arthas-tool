#!/usr/bin/env python3
"""配置管理模块"""
import os
import warnings

_DEFAULT_SECRET = 'dev-secret-key-change-in-production'


class Config:
    """应用配置"""
    
    # 基础路径
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 数据库
    DB_FILE = os.environ.get('DB_FILE', os.path.join(BASE_DIR, 'config', 'db', 'arthas.db'))
    
    # 配置文件
    CLUSTERS_FILE = os.environ.get('CLUSTERS_FILE', os.path.join(BASE_DIR, 'config', 'data', 'clusters.json'))
    EXTERNAL_LINKS_FILE = os.environ.get('EXTERNAL_LINKS_FILE', os.path.join(BASE_DIR, 'config', 'data', 'external_links.json'))
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', _DEFAULT_SECRET)
    STATIC_FOLDER = 'static'
    STATIC_URL_PATH = ''  # 空字符串：从根路径提供静态文件 (如 /js/core/api.js)
    
    # 默认页面
    DEFAULT_PAGE = 'login.html'
    
    # 服务器
    DEFAULT_PORT = int(os.environ.get('PORT', 5001))
    DEFAULT_HOST = os.environ.get('HOST', '127.0.0.1')
    
    # 输出目录
    OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'profiler_output')
    
    # 认证
    MIN_PASSWORD_LENGTH = 6
    
    # 分页
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 500

    @classmethod
    def validate_production(cls):
        """启动时校验生产环境安全配置"""
        if cls.SECRET_KEY == _DEFAULT_SECRET:
            warnings.warn(
                "⚠ SECRET_KEY 使用默认值，生产环境必须设置 SECRET_KEY 环境变量！",
                stacklevel=2
            )