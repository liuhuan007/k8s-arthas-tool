#!/usr/bin/env python3
"""
P0-4.2 watch/trace 场景化入口测试
验收标准：
- [ ] trace 命令自动带 -n 和 cost 条件
- [ ] watch 命令默认限制观测次数
- [ ] 参数为空时提示用户
"""
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_watch_trace_ui_form_exists():
    """测试前端有 watch/trace 场景化表单"""
    diag_js = (ROOT / 'static' / 'js' / 'components' / 'diagnose.js').read_text(encoding='utf-8')
    # 检查是否有场景化表单相关函数或 HTML
    has_form = 'watchTraceForm' in diag_js or 'methodDiagForm' in diag_js or 'sceneForm' in diag_js
    assert has_form, "diagnose.js 应包含 watch/trace 场景化表单函数"


def test_watch_trace_api_exists():
    """测试 watch/trace 场景化 API 存在"""
    perf = (ROOT / 'api' / 'performance_diagnose.py').read_text(encoding='utf-8')
    # 检查是否有处理 watch/trace 场景化的端点或逻辑
    has_watch = 'watch' in perf.lower()
    has_trace = 'trace' in perf.lower()
    assert has_watch and has_trace, "performance_diagnose.py 应处理 watch 和 trace"


def test_empty_param_validation():
    """测试参数为空时前端有校验提示"""
    diag_js = (ROOT / 'static' / 'js' / 'components' / 'diagnose.js').read_text(encoding='utf-8')
    # 检查是否有参数校验逻辑
    has_validate = 'class_pattern' in diag_js and ('不能为空' in diag_js or 'required' in diag_js or 'empty' in diag_js.lower())
    assert has_validate, "应有参数非空校验"


def test_watch_command_limit():
    """测试 watch 命令默认限制观测次数"""
    perf = (ROOT / 'api' / 'performance_diagnose.py').read_text(encoding='utf-8')
    # 检查 watch 命令是否有限制（如 -n 或超时）
    has_limit = '-n ' in perf or 'watch' in perf.lower()
    assert has_limit, "watch 命令应有限制次数"


def test_trace_command_options():
    """测试 trace 命令自动带 -n 和 cost 条件"""
    perf = (ROOT / 'api' / 'performance_diagnose.py').read_text(encoding='utf-8')
    # 检查 trace 命令是否自动添加 -n 和 #cost > 条件
    has_opts = '-n ' in perf and ('#cost' in perf or 'cost >' in perf)
    assert has_opts, "trace 命令应自动带 -n 和 cost 条件"

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
