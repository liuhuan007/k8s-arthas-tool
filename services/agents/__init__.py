#!/usr/bin/env python3
"""Agents 包 - 提供多种 Agent 适配器

本包包含以下适配器：
- CodeBuddyAgent: CodeBuddy SDK 适配器
- FallbackAgent: 降级 Agent（基于 OpenAI 兼容 API）

Author: Kou (software-engineer)
Created: 2025-05-25
"""

from services.agents.codebuddy_agent import CodeBuddyAgent
from services.agents.fallback_agent import FallbackAgent

__all__ = ['CodeBuddyAgent', 'FallbackAgent']
