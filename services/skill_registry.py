#!/usr/bin/env python3
"""Skill Registry 服务 - 管理Skill的导入、校验、版本、发布"""
import json
import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class SkillRegistry:
    """Skill注册中心 - 管理态核心"""

    # Arthas 命令白名单
    ALLOWED_COMMANDS_LOW_RISK = [
        "dashboard", "thread", "jvm", "sysprop", "sysenv",
        "vmoption", "memory", "heap", "gc", "logger",
        "sc", "sm", "jad", "classloader", "perfcounter", "ss"
    ]

    ALLOWED_COMMANDS_MEDIUM_RISK = [
        "trace", "watch", "stack", "monitor", "tt",
        "profiler", "heapdump", "vmtool"
    ]

    FORBIDDEN_COMMANDS = [
        "redefine", "retransform",  # 修改代码
        "ognl", "reset", "shutdown"  # 高风险操作
    ]

    def __init__(self):
        from models.db import get_db
        self.db = get_db()

    def import_skill(self, skill_data: Dict[str, Any], created_by: int = None) -> int:
        """导入 Skill

        Args:
            skill_data: Skill数据字典
            created_by: 创建者ID

        Returns:
            int: Skill ID

        Raises:
            ValueError: 校验失败时抛出
        """
        # 1. 校验格式
        validated = self._validate_skill(skill_data)

        # 2. 检查版本冲突
        existing = self._find_skill_by_name(validated['name'])
        if existing:
            # 自动递增版本号
            validated['version'] = self._increment_version(
                validated.get('version', '1.0.0'),
                existing.get('version', '1.0.0')
            )

        # 3. 存储到 skill_registry
        skill_id = self._store_skill(validated, created_by)

        # 4. 记录审计日志
        self._log_audit("import_skill", skill_id, skill_data)

        return skill_id

    def import_from_file(self, file_path: str, created_by: int = None) -> int:
        """从文件导入 Skill

        Args:
            file_path: 文件路径
            created_by: 创建者ID

        Returns:
            int: Skill ID
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        content = path.read_text(encoding='utf-8')
        skill_data = self._parse_skill_file(content, path.suffix)

        return self.import_skill(skill_data, created_by)

    def import_from_directory(self, dir_path: str, created_by: int = None) -> List[int]:
        """从目录批量导入 Skills

        Args:
            dir_path: 目录路径
            created_by: 创建者ID

        Returns:
            List[int]: Skill ID列表
        """
        path = Path(dir_path)
        if not path.exists() or not path.is_dir():
            raise ValueError(f"目录不存在: {dir_path}")

        skill_ids = []
        for file in path.glob("*.*"):
            if file.suffix in ['.md', '.yaml', '.yml', '.json']:
                try:
                    skill_id = self.import_from_file(str(file), created_by)
                    skill_ids.append(skill_id)
                    log.info(f"导入Skill成功: {file.name} -> ID {skill_id}")
                except Exception as e:
                    log.error(f"导入Skill失败: {file.name}, 错误: {e}")

        return skill_ids

    def _parse_skill_file(self, content: str, suffix: str) -> Dict[str, Any]:
        """解析Skill文件

        Args:
            content: 文件内容
            suffix: 文件后缀

        Returns:
            Dict[str, Any]: Skill数据
        """
        if suffix in ['.yaml', '.yml']:
            return self._parse_yaml(content)
        elif suffix == '.json':
            return self._parse_json(content)
        elif suffix == '.md':
            return self._parse_markdown(content)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

    def _parse_yaml(self, content: str) -> Dict[str, Any]:
        """解析YAML格式"""
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            # 如果没有安装yaml库，使用简单的解析
            return self._parse_simple_yaml(content)

    def _parse_simple_yaml(self, content: str) -> Dict[str, Any]:
        """简单的YAML解析（不依赖yaml库）"""
        result = {}
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    result[key] = value
        return result

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """解析JSON格式"""
        return json.loads(content)

    def _parse_markdown(self, content: str) -> Dict[str, Any]:
        """解析Markdown格式（提取前置元数据）"""
        result = {}

        # 提取YAML前置元数据
        if content.startswith('---'):
            end_idx = content.find('---', 3)
            if end_idx > 0:
                yaml_content = content[3:end_idx].strip()
                result = self._parse_simple_yaml(yaml_content)
                return result

        # 如果没有前置元数据，尝试从内容中提取
        lines = content.split('\n')
        for line in lines[:20]:  # 只看前20行
            line = line.strip()
            if line.startswith('name:'):
                result['name'] = line.split(':', 1)[1].strip()
            elif line.startswith('version:'):
                result['version'] = line.split(':', 1)[1].strip()
            elif line.startswith('description:'):
                result['description'] = line.split(':', 1)[1].strip()
            elif line.startswith('category:'):
                result['category'] = line.split(':', 1)[1].strip()
            elif line.startswith('level:'):
                try:
                    result['level'] = int(line.split(':', 1)[1].strip())
                except ValueError:
                    pass

        # 如果没有找到name，使用第一个标题
        if 'name' not in result:
            for line in lines:
                if line.startswith('# '):
                    result['name'] = line[2:].strip().lower().replace(' ', '-')
                    break

        return result

    def _find_skill_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称查找Skill"""
        return self.db.fetch_one(
            "SELECT * FROM skill_registry WHERE name = ? ORDER BY version DESC LIMIT 1",
            (name,)
        )

    def _increment_version(self, new_version: str, existing_version: str) -> str:
        """递增版本号"""
        try:
            # 解析版本号
            new_parts = list(map(int, new_version.split('.')))
            existing_parts = list(map(int, existing_version.split('.')))

            # 如果新版本 <= 现有版本，自动递增
            if new_parts <= existing_parts:
                existing_parts[2] += 1  # 递增补丁版本
                return '.'.join(map(str, existing_parts))

            return new_version
        except (ValueError, IndexError):
            # 版本号格式错误，返回默认值
            return "1.0.0"

    def validate_skill(self, skill_id: int) -> Tuple[bool, List[str]]:
        """校验 Skill

        Returns:
            Tuple[bool, List[str]]: (是否通过, 错误信息列表)
        """
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        errors = []

        # 1. 校验参数 schema
        valid, msg = self._validate_parameters_schema(skill)
        if not valid:
            errors.append(f"参数Schema校验失败: {msg}")

        # 2. 校验命令白名单
        valid, msg = self._validate_command_whitelist(skill)
        if not valid:
            errors.append(f"命令白名单校验失败: {msg}")

        # 3. 校验DSL格式（如果有）
        if skill.get('dsl'):
            valid, msg = self._validate_dsl_format(skill['dsl'])
            if not valid:
                errors.append(f"DSL格式校验失败: {msg}")

        # 如果没有错误，更新状态
        if not errors:
            self._update_skill_status(skill_id, "validated")

        return len(errors) == 0, errors

    def _validate_dsl_format(self, dsl: str) -> Tuple[bool, str]:
        """校验DSL格式

        Returns:
            Tuple[bool, str]: (是否合法, 错误信息)
        """
        try:
            dsl_data = json.loads(dsl)

            # 检查是否有steps字段
            if 'steps' not in dsl_data:
                return False, "DSL必须包含steps字段"

            steps = dsl_data['steps']
            if not isinstance(steps, list):
                return False, "steps必须是数组"

            # 检查每个step
            for i, step in enumerate(steps):
                if 'command' not in step and 'handler' not in step:
                    return False, f"步骤{i+1}必须包含command或handler字段"

            return True, ""
        except json.JSONDecodeError as e:
            return False, f"DSL格式错误: {e}"

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

    def _validate_parameters_schema(self, skill: Dict[str, Any]) -> Tuple[bool, str]:
        """校验参数 Schema

        Returns:
            Tuple[bool, str]: (是否合法, 错误信息)
        """
        if not skill.get('parameters_schema'):
            return True, ""

        try:
            schema = json.loads(skill['parameters_schema'])

            # 校验 JSON Schema 格式
            if not isinstance(schema, (dict, list)):
                return False, "参数Schema必须是JSON对象或数组"

            # 空JSON对象是合法的
            if isinstance(schema, dict) and len(schema) == 0:
                return True, ""

            # 如果是对象且非空，检查是否有properties
            if isinstance(schema, dict) and len(schema) > 0:
                if 'properties' not in schema:
                    return False, "非空参数Schema对象必须包含properties字段"

            return True, ""
        except json.JSONDecodeError as e:
            return False, f"参数Schema格式错误: {e}"

    def _validate_command_whitelist(self, skill: Dict[str, Any]) -> Tuple[bool, str]:
        """校验命令白名单

        Returns:
            Tuple[bool, str]: (是否合法, 错误信息)
        """
        if not skill.get('arthas_command'):
            return True, ""

        # 提取命令名（第一个单词）
        command = skill['arthas_command'].split()[0]

        # 检查禁止的命令
        if command in self.FORBIDDEN_COMMANDS:
            return False, f"禁止的命令: {command}"

        # 检查低风险命令
        if command in self.ALLOWED_COMMANDS_LOW_RISK:
            return True, ""

        # 检查中风险命令
        if command in self.ALLOWED_COMMANDS_MEDIUM_RISK:
            # 中风险命令需要确认
            return True, f"中风险命令: {command}，需要二次确认"

        # 不在白名单中的命令
        return False, f"命令不在白名单中: {command}"

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
        from services.audit_service import AuditService
        AuditService.log_event(
            user_id=None,
            action=action,
            resource_type="skill_registry",
            resource_id=str(skill_id),
            details=json.dumps(details) if isinstance(details, dict) else str(details)
        )

    def get_skill_stats(self) -> Dict[str, Any]:
        """获取Skill统计信息"""
        stats = {}

        # 总数
        stats['total'] = self.db.count('skill_registry')

        # 按来源统计
        stats['by_source'] = {}
        for source in ['builtin', 'custom', 'imported']:
            stats['by_source'][source] = self.db.count(
                'skill_registry', 'source = ?', (source,)
            )

        # 按状态统计
        stats['by_status'] = {}
        for status in ['draft', 'validated', 'testing', 'published', 'archived']:
            stats['by_status'][status] = self.db.count(
                'skill_registry', 'status = ?', (status,)
            )

        # 按分类统计
        stats['by_category'] = {}
        for category in ['quick', 'tool', 'scenario', 'ai']:
            stats['by_category'][category] = self.db.count(
                'skill_registry', 'category = ?', (category,)
            )

        return stats

    def archive_skill(self, skill_id: int) -> bool:
        """归档 Skill"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        if skill['status'] != 'published':
            raise ValueError("只能归档已发布的Skill")

        self._update_skill_status(skill_id, "archived")
        self._log_audit("archive_skill", skill_id, {})
        return True

    def restore_skill(self, skill_id: int) -> bool:
        """恢复归档的 Skill"""
        skill = self._get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        if skill['status'] != 'archived':
            raise ValueError("只能恢复已归档的Skill")

        self._update_skill_status(skill_id, "published")
        self._log_audit("restore_skill", skill_id, {})
        return True

    def search_skills(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索 Skills"""
        query = """
            SELECT * FROM skill_registry
            WHERE name LIKE ? OR description LIKE ?
            ORDER BY category, level, name
        """
        keyword_pattern = f"%{keyword}%"
        return self.db.fetch_all(query, (keyword_pattern, keyword_pattern))

    def get_skill_by_name_version(self, name: str, version: str) -> Optional[Dict[str, Any]]:
        """根据名称和版本获取 Skill"""
        return self.db.fetch_one(
            "SELECT * FROM skill_registry WHERE name = ? AND version = ?",
            (name, version)
        )


# 全局实例
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取 SkillRegistry 单例"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
