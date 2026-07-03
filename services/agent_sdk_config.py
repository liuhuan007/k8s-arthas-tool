#!/usr/bin/env python3
"""
Agent SDK配置管理器 - 复用数据库ai_config表
"""

from typing import Dict, Any, Optional
from models.db import db

class AgentSDKConfig:
    """Agent SDK配置管理"""
    
    # Agent SDK默认配置
    DEFAULT_CONFIG = {
        "permission_mode": "bypassPermissions",
        "max_turns": 50,
        "setting_sources": ["project"]
    }
    
    @staticmethod
    def get_config(user_id: int) -> Dict[str, Any]:
        """获取用户的Agent SDK配置"""
        
        # 从数据库读取LLM配置
        ai_config = db.fetch_one(
            'SELECT * FROM ai_config WHERE user_id = ?',
            (user_id,)
        )
        
        if not ai_config:
            return AgentSDKConfig.DEFAULT_CONFIG
        
        # 构建Agent SDK配置
        config = {
            # 复用ai_config中的配置
            "model": ai_config.get("model", "deepseek-v3.1"),
            "api_key": ai_config.get("api_key", ""),
            "base_url": ai_config.get("base_url", ""),
            "provider": ai_config.get("provider", "openai"),
            
            # Agent SDK特有配置（使用默认值）
            "permission_mode": AgentSDKConfig.DEFAULT_CONFIG["permission_mode"],
            "max_turns": AgentSDKConfig.DEFAULT_CONFIG["max_turns"],
            "setting_sources": AgentSDKConfig.DEFAULT_CONFIG["setting_sources"]
        }
        
        return config
    
    @staticmethod
    def get_agent_sdk_options(user_id: int) -> Dict[str, Any]:
        """获取Agent SDK初始化选项"""
        
        config = AgentSDKConfig.get_config(user_id)
        
        # 根据provider构建不同的options
        if config["provider"] == "codebuddy":
            # CodeBuddy Agent SDK
            return {
                "model": config["model"],
                "permission_mode": config["permission_mode"],
                "max_turns": config["max_turns"],
                "env": {
                    "CODEBUDDY_API_KEY": config["api_key"],
                    "CODEBUDDY_INTERNET_ENVIRONMENT": "internal"
                }
            }
        else:
            # OpenAI兼容API（作为备用）
            return {
                "model": config["model"],
                "api_key": config["api_key"],
                "base_url": config["base_url"]
            }
    
    @staticmethod
    def is_agent_sdk_available(user_id: int) -> bool:
        """检查Agent SDK是否可用"""
        
        config = AgentSDKConfig.get_config(user_id)
        
        # 检查是否有API Key
        if not config.get("api_key"):
            return False
        
        # 检查provider是否支持Agent SDK
        if config.get("provider") in ["codebuddy", "openai", "newapi", "openai-compatible"]:
            return True
        
        return False


# 全局实例
agent_sdk_config = AgentSDKConfig()
