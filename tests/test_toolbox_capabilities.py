"""诊断能力目录测试"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.core.diagnosis_capabilities import (
    QUICK_TOOLS, DIAGNOSIS_TOOLS, SCENARIOS, AI_DIAGNOSIS,
    _seed_capabilities, init_capabilities_table
)
from models.db import db


def test_quick_tools_count():
    """快捷工具数量校验"""
    assert len(QUICK_TOOLS) >= 5, f"快捷工具至少 5 个,实际 {len(QUICK_TOOLS)}"


def test_diagnosis_tools_count():
    """诊断模板数量校验"""
    assert len(DIAGNOSIS_TOOLS) >= 5, f"诊断模板至少 5 个,实际 {len(DIAGNOSIS_TOOLS)}"


def test_scenarios_count():
    """场景方案数量校验"""
    assert len(SCENARIOS) >= 3, f"场景方案至少 3 个,实际 {len(SCENARIOS)}"


def test_ai_diagnosis_count():
    """智能诊断数量校验"""
    assert len(AI_DIAGNOSIS) >= 1, f"智能诊断至少 1 个,实际 {len(AI_DIAGNOSIS)}"


def test_capability_fields():
    """能力字段完整性校验"""
    for cap in QUICK_TOOLS + DIAGNOSIS_TOOLS:
        assert 'name' in cap
        assert 'category' in cap
        assert 'level' in cap
        assert 'arthas_command' in cap
        assert cap['level'] in [1, 2]


def test_scenario_steps():
    """场景方案步骤校验"""
    for scenario in SCENARIOS:
        assert 'steps_json' in scenario
        steps = json.loads(scenario['steps_json'])
        assert len(steps) >= 2, f"场景 {scenario['name']} 至少 2 步"
        for step in steps:
            assert 'step' in step
            assert 'command' in step
            assert 'desc' in step


def test_risk_levels():
    """风险等级校验"""
    valid_levels = {'low', 'medium', 'high'}
    all_caps = QUICK_TOOLS + DIAGNOSIS_TOOLS + SCENARIOS + AI_DIAGNOSIS
    for cap in all_caps:
        assert cap.get('risk_level') in valid_levels, f"{cap['name']} 风险等级不合法"


def test_parameters_schema_valid():
    """参数 schema 合法性校验"""
    import re
    all_caps = QUICK_TOOLS + DIAGNOSIS_TOOLS + SCENARIOS
    for cap in all_caps:
        schema_str = cap.get('parameters_schema', '{}')
        if schema_str and schema_str != '{}':
            schema = json.loads(schema_str)
            assert isinstance(schema, list)
            for field in schema:
                assert 'name' in field
                assert 'label' in field


def test_seed_capabilities_idempotent():
    """数据初始化幂等性测试"""
    with db.connection() as conn:
        # 第一次初始化
        _seed_capabilities(conn)
        count1 = conn.execute("SELECT COUNT(*) FROM diagnosis_capabilities").fetchone()[0]
        
        # 第二次初始化(应该跳过)
        _seed_capabilities(conn)
        count2 = conn.execute("SELECT COUNT(*) FROM diagnosis_capabilities").fetchone()[0]
        
        assert count1 == count2, "初始化不是幂等的"


def test_init_capabilities_table():
    """完整初始化流程测试"""
    with db.connection() as conn:
        # 清空数据
        conn.execute("DELETE FROM diagnosis_capabilities")
        
        # 重新初始化
        init_capabilities_table(conn)
        
        # 校验数据
        count = conn.execute("SELECT COUNT(*) FROM diagnosis_capabilities").fetchone()[0]
        assert count > 0, "初始化后应该有能力数据"
        
        # 校验分类
        categories = conn.execute("SELECT DISTINCT category FROM diagnosis_capabilities").fetchall()
        category_names = [r[0] for r in categories]
        assert 'quick' in category_names
        assert 'tool' in category_names
        assert 'scenario' in category_names
        assert 'ai' in category_names


def test_capability_api_list():
    """API 列表接口测试"""
    # 确保数据已初始化
    with db.connection() as conn:
        init_capabilities_table(conn)
    
    # 查询所有能力
    all_caps = db.fetch_all("SELECT * FROM diagnosis_capabilities ORDER BY level, id")
    assert len(all_caps) > 0
    
    # 按分类查询
    quick_caps = db.fetch_all("SELECT * FROM diagnosis_capabilities WHERE category = 'quick'")
    assert len(quick_caps) >= 5
    
    tool_caps = db.fetch_all("SELECT * FROM diagnosis_capabilities WHERE category = 'tool'")
    assert len(tool_caps) >= 5


def test_related_capabilities_format():
    """关联能力格式校验"""
    with db.connection() as conn:
        rows = conn.execute("SELECT id, name, related_capabilities FROM diagnosis_capabilities").fetchall()
        for row in rows:
            related = json.loads(row[2])
            assert isinstance(related, list)
            for rel_id in related:
                assert isinstance(rel_id, int), f"{row[1]} 的关联能力 ID 应该是整数"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
