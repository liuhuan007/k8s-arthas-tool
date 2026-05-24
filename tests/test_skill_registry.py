#!/usr/bin/env python3
"""Skill Registry 单元测试"""
import pytest
import json
import sys
import os
import tempfile
import sqlite3

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockDatabase:
    """模拟数据库类，用于测试"""

    def __init__(self, db_path: str):
        self._db_file = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()):
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def insert(self, table: str, data: dict):
        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        cursor = self.conn.execute(sql, tuple(data.values()))
        self.conn.commit()
        return cursor.lastrowid

    def count(self, table: str, where: str = "1=1", params: tuple = ()):
        sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        row = self.conn.execute(sql, params).fetchone()
        return row['cnt'] if row else 0

    def initialize(self):
        """初始化数据库表结构"""
        # 创建 skill_registry 表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS skill_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                description TEXT,
                category TEXT,
                level INTEGER,
                risk_level TEXT,
                estimated_duration INTEGER,
                source TEXT DEFAULT 'custom',
                status TEXT DEFAULT 'draft',
                dsl TEXT,
                parameters_schema TEXT,
                llm_prompt TEXT,
                arthas_command TEXT,
                handler TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, version)
            )
        ''')

        # 创建 diagnosis_capabilities 表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                level INTEGER DEFAULT 1,
                description TEXT,
                arthas_command TEXT,
                parameters_schema TEXT DEFAULT '{}',
                risk_level TEXT DEFAULT 'low',
                estimated_duration INTEGER DEFAULT 10,
                handler TEXT,
                steps_json TEXT,
                visibility TEXT DEFAULT 'public',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建 task_logs 表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS task_logs (
                id TEXT PRIMARY KEY,
                capability_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                execution_mode TEXT DEFAULT 'manual',
                execution_type TEXT DEFAULT 'diagnosis',
                target_json TEXT,
                params_json TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                error_message TEXT
            )
        ''')

        # 创建 step_logs 表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS step_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_number INTEGER NOT NULL,
                step_name TEXT,
                step_type TEXT,
                command TEXT,
                output TEXT,
                status TEXT DEFAULT 'pending',
                duration_ms INTEGER,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建 users 表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建 audit_logs 表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.conn.commit()


class TestSkillRegistry:
    """SkillRegistry 单元测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        # 创建临时数据库文件
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        # 初始化数据库
        self.db = MockDatabase(self.temp_db_path)
        self.db.initialize()

        # 创建 SkillRegistry 实例并注入数据库
        from services.skill_registry import SkillRegistry
        self.registry = SkillRegistry()
        self.registry.db = self.db

    def teardown_method(self):
        """每个测试方法后执行"""
        # 关闭数据库连接
        if hasattr(self, 'db') and hasattr(self.db, 'conn'):
            self.db.conn.close()
        # 删除临时数据库文件
        if os.path.exists(self.temp_db_path):
            try:
                os.unlink(self.temp_db_path)
            except:
                pass

    def test_import_skill_success(self):
        """测试导入 Skill 成功"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "description": "测试Skill"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)
        assert skill_id > 0

        # 验证导入成功
        skill = self.registry.get_skill(skill_id)
        assert skill is not None
        assert skill['name'] == 'test-skill'
        assert skill['version'] == '1.0.0'
        assert skill['status'] == 'draft'

    def test_import_skill_missing_name(self):
        """测试导入 Skill 缺少 name 字段"""
        skill_data = {
            "version": "1.0.0",
            "category": "quick",
            "level": 1
        }

        with pytest.raises(ValueError, match="Missing required field: name"):
            self.registry.import_skill(skill_data)

    def test_import_skill_missing_version(self):
        """测试导入 Skill 缺少 version 字段"""
        skill_data = {
            "name": "test-skill",
            "category": "quick",
            "level": 1
        }

        with pytest.raises(ValueError, match="Missing required field: version"):
            self.registry.import_skill(skill_data)

    def test_import_skill_invalid_category(self):
        """测试导入 Skill 无效的 category"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "invalid",
            "level": 1
        }

        with pytest.raises(ValueError, match="Invalid category: invalid"):
            self.registry.import_skill(skill_data)

    def test_import_skill_invalid_level(self):
        """测试导入 Skill 无效的 level"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 5
        }

        with pytest.raises(ValueError, match="Invalid level: 5"):
            self.registry.import_skill(skill_data)

    def test_validate_skill_success(self):
        """测试校验 Skill 成功"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "description": "测试Skill"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)
        is_valid, errors = self.registry.validate_skill(skill_id)

        assert is_valid is True
        assert len(errors) == 0

        # 验证状态更新
        skill = self.registry.get_skill(skill_id)
        assert skill['status'] == 'validated'

    def test_validate_skill_with_invalid_command(self):
        """测试校验 Skill 包含无效命令"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "arthas_command": "forbidden_command"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)
        is_valid, errors = self.registry.validate_skill(skill_id)

        assert is_valid is False
        assert len(errors) > 0

    def test_publish_skill_success(self):
        """测试发布 Skill 成功"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "arthas_command": "dashboard -n 1"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)
        self.registry.validate_skill(skill_id)

        capability_id = self.registry.publish_skill(skill_id)

        assert capability_id > 0

        # 验证状态更新
        skill = self.registry.get_skill(skill_id)
        assert skill['status'] == 'published'

    def test_publish_skill_invalid_status(self):
        """测试发布 Skill 状态无效"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)

        with pytest.raises(ValueError, match="Skill status must be"):
            self.registry.publish_skill(skill_id)

    def test_list_skills(self):
        """测试列出 Skills"""
        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        # 导入多个 Skill
        for i in range(3):
            skill_data = {
                "name": f"test-skill-{i}",
                "version": "1.0.0",
                "category": "quick",
                "level": 1
            }
            self.registry.import_skill(skill_data)

        skills = self.registry.list_skills()
        assert len(skills) == 3

    def test_list_skills_by_category(self):
        """测试按分类列出 Skills"""
        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        # 导入不同分类的 Skill
        categories = ["quick", "tool", "scenario"]
        for cat in categories:
            skill_data = {
                "name": f"test-skill-{cat}",
                "version": "1.0.0",
                "category": cat,
                "level": 1
            }
            self.registry.import_skill(skill_data)

        quick_skills = self.registry.list_skills(category="quick")
        assert len(quick_skills) == 1
        assert quick_skills[0]['category'] == 'quick'

    def test_update_skill(self):
        """测试更新 Skill"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "description": "原始描述"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)

        # 更新描述
        success = self.registry.update_skill(skill_id, {"description": "更新后的描述"})
        assert success is True

        # 验证更新
        skill = self.registry.get_skill(skill_id)
        assert skill['description'] == '更新后的描述'

    def test_delete_skill(self):
        """测试删除 Skill"""
        skill_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "source": "custom"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)

        success = self.registry.delete_skill(skill_id)
        assert success is True

        # 验证删除
        skill = self.registry.get_skill(skill_id)
        assert skill is None

    def test_delete_builtin_skill(self):
        """测试删除内置 Skill"""
        skill_data = {
            "name": "builtin-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "source": "builtin"
        }

        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        skill_id = self.registry.import_skill(skill_data)

        with pytest.raises(ValueError, match="Cannot delete builtin skill"):
            self.registry.delete_skill(skill_id)

    def test_search_skills(self):
        """测试搜索 Skills"""
        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        # 导入测试数据
        skill_data = {
            "name": "cpu-high-diagnosis",
            "version": "1.0.0",
            "category": "quick",
            "level": 1,
            "description": "CPU飙高诊断"
        }
        self.registry.import_skill(skill_data)

        # 搜索
        results = self.registry.search_skills("cpu")
        assert len(results) == 1
        assert results[0]['name'] == 'cpu-high-diagnosis'

    def test_get_skill_stats(self):
        """测试获取统计信息"""
        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        # 导入测试数据
        for i in range(5):
            skill_data = {
                "name": f"test-skill-{i}",
                "version": "1.0.0",
                "category": "quick",
                "level": 1,
                "source": "custom"
            }
            self.registry.import_skill(skill_data)

        stats = self.registry.get_skill_stats()
        assert stats['total'] == 5
        assert stats['by_source']['custom'] == 5

    def test_import_from_file(self):
        """测试从文件导入"""
        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        # 创建临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "name": "file-skill",
                "version": "1.0.0",
                "category": "quick",
                "level": 1
            }, f)
            temp_path = f.name

        try:
            skill_id = self.registry.import_from_file(temp_path)
            assert skill_id > 0
        finally:
            os.unlink(temp_path)

    def test_version_increment(self):
        """测试版本号自动递增"""
        # 跳过审计日志
        self.registry._log_audit = lambda *args: None

        # 导入同名 Skill
        skill_data1 = {
            "name": "test-skill",
            "version": "1.0.0",
            "category": "quick",
            "level": 1
        }
        self.registry.import_skill(skill_data1)

        skill_data2 = {
            "name": "test-skill",
            "version": "1.0.0",  # 相同版本
            "category": "quick",
            "level": 1
        }
        skill_id2 = self.registry.import_skill(skill_data2)

        skill2 = self.registry.get_skill(skill_id2)
        assert skill2['version'] == '1.0.1'  # 自动递增


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
