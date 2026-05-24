#!/usr/bin/env python3
"""Skill Registry 服务 - 管理Skill的导入、校验、版本、发布"""
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

log = logging.getLogger(__name__)


class SkillRegistry:
    """Skill注册中心 - 管理态核心"""

    def __init__(self):
        from models.db import get_db
        self.db = get_db()

    def import_skill(self, skill_data: Dict[str, Any], created_by: int = None) -> int:
        """导入 Skill"""
        # 1. 校验格式
        validated = self._validate_skill(skill_data)

        # 2. 存储到 skill_registry
        skill_id = self._store_skill(validated, created_by)

        # 3. 记录审计日志
        self._log_audit("import_skill", skill_id, skill_data)

        return skill_id

    def validate_skill(self, skill_id: int) -> bool:
        """校验 Skill"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # 1. 校验参数 schema
        if not self._validate_parameters_schema(skill):
            return False

        # 2. 校验命令白名单
        if not self._validate_command_whitelist(skill):
            return False

        # 3. 更新状态
        self._update_skill_status(skill_id, "validated")

        return True

    def publish_skill(self, skill_id: int) -> int:
        """发布 Skill 到 diagnosis_capabilities"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # 1. 检查状态
        if skill['status'] not in ['validated', 'testing']:
            raise ValueError(f"Skill status must be 'validated' or 'testing', got '{skill['status']}'")

        # 2. 创建 diagnosis_capability
        capability_id = self._create_capability(skill)

        # 3. 更新状态
        self._update_skill_status(skill_id, "published")

        # 4. 记录审计日志
        self._log_audit("publish_skill", skill_id, {"capability_id": capability_id})

        return capability_id

    def get_skill(self, skill_id: int) -> Optional[Dict[str, Any]]:
        """获取单个 Skill"""
        return self._get_skill(skill_id)

    def list_skills(self, status: str = None, category: str = None, source: str = None) -> List[Dict[str, Any]]:
        """列出 Skills"""
        query = "SELECT * FROM skill_registry WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY category, level, name"
        return self.db.fetch_all(query, tuple(params))

    def update_skill(self, skill_id: int, updates: Dict[str, Any]) -> bool:
        """更新 Skill"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # 只允许更新草稿状态的Skill
        if skill['status'] not in ['draft', 'validated']:
            raise ValueError(f"Cannot update skill with status '{skill['status']}'")

        allowed_fields = ['description', 'category', 'level', 'risk_level', 'estimated_duration',
                         'dsl', 'parameters_schema', 'llm_prompt', 'arthas_command', 'handler']
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            return False

        set_clause = ', '.join([f"{k} = ?" for k in filtered_updates.keys()])
        query = f"UPDATE skill_registry SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        params = list(filtered_updates.values()) + [skill_id]

        self.db.execute(query, tuple(params))
        return True

    def delete_skill(self, skill_id: int) -> bool:
        """删除 Skill"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # 内置Skill不允许删除
        if skill['source'] == 'builtin':
            raise ValueError("Cannot delete builtin skill")

        self.db.execute("DELETE FROM skill_registry WHERE id = ?", (skill_id,))
        return True

    def _validate_skill(self, skill_data: Dict[str, Any]) -> Dict[str, Any]:
        """校验 Skill 格式"""
        required_fields = ["name", "version", "category", "level"]
        for field in required_fields:
            if field not in skill_data:
                raise ValueError(f"Missing required field: {field}")

        # 校验 category
        valid_categories = ["quick", "tool", "scenario", "ai"]
        if skill_data["category"] not in valid_categories:
            raise ValueError(f"Invalid category: {skill_data['category']}")

        # 校验 level
        if skill_data["level"] not in [1, 2, 3, 4]:
            raise ValueError(f"Invalid level: {skill_data['level']}")

        return skill_data

    def _validate_parameters_schema(self, skill: Dict[str, Any]) -> bool:
        """校验参数 Schema"""
        if not skill.get('parameters_schema'):
            return True

        try:
            schema = json.loads(skill['parameters_schema'])
            # 校验 JSON Schema 格式
            return isinstance(schema, (dict, list))
        except json.JSONDecodeError:
            return False

    def _validate_command_whitelist(self, skill: Dict[str, Any]) -> bool:
        """校验命令白名单"""
        if not skill.get('arthas_command'):
            return True

        # Arthas 命令白名单
        whitelist = [
            "dashboard", "thread", "jad", "watch", "trace", "stack",
            "monitor", "profiler", "heapdump", "vmoption", "sc", "sm",
            "vmtool", "ognl", "mc", "redefine", "retransform", "classloader",
            "logger", "heapdump", "jvm", "memory", "perfcounter", "ss"
        ]

        # 提取命令名（第一个单词）
        command = skill['arthas_command'].split()[0]
        return command in whitelist

    def _store_skill(self, skill_data: Dict[str, Any], created_by: int = None) -> int:
        """存储 Skill"""
        return self.db.insert('skill_registry', {
            'name': skill_data['name'],
            'version': skill_data['version'],
            'description': skill_data.get('description', ''),
            'category': skill_data['category'],
            'level': skill_data['level'],
            'risk_level': skill_data.get('risk_level', 'low'),
            'estimated_duration': skill_data.get('estimated_duration', 10),
            'source': skill_data.get('source', 'custom'),
            'status': 'draft',
            'dsl': skill_data.get('dsl'),
            'parameters_schema': skill_data.get('parameters_schema', '{}'),
            'llm_prompt': skill_data.get('llm_prompt'),
            'arthas_command': skill_data.get('arthas_command'),
            'handler': skill_data.get('handler'),
            'created_by': created_by,
        })

    def _get_skill(self, skill_id: int) -> Optional[Dict[str, Any]]:
        """获取 Skill"""
        return self.db.fetch_one("SELECT * FROM skill_registry WHERE id = ?", (skill_id,))

    def _update_skill_status(self, skill_id: int, status: str):
        """更新 Skill 状态"""
        self.db.execute(
            "UPDATE skill_registry SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, skill_id)
        )

    def _create_capability(self, skill: Dict[str, Any]) -> int:
        """创建 diagnosis_capability"""
        return self.db.insert('diagnosis_capabilities', {
            'name': skill['name'],
            'category': skill['category'],
            'level': skill.get('level', 1),
            'description': skill.get('description', ''),
            'arthas_command': skill.get('arthas_command'),
            'parameters_schema': skill.get('parameters_schema', '{}'),
            'risk_level': skill.get('risk_level', 'low'),
            'estimated_duration': skill.get('estimated_duration', 10),
            'handler': skill.get('handler'),
            'steps_json': skill.get('dsl'),
            'visibility': 'public',
            'created_by': skill.get('created_by'),
        })

    def _log_audit(self, action: str, skill_id: int, details: Any):
        """记录审计日志"""
        from services.audit_service import log_audit_action
        log_audit_action(
            action=action,
            resource_type="skill_registry",
            resource_id=str(skill_id),
            details=json.dumps(details) if isinstance(details, dict) else str(details)
        )


# 全局实例
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取 SkillRegistry 单例"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
