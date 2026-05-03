#!/usr/bin/env python3
"""
P0-4.1 线程诊断页结构化测试
验收标准：
- [ ] 支持 thread -n <N> 热点线程
- [ ] 支持 thread -b 死锁检测
- [ ] 点击线程显示完整堆栈
"""
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def test_thread_api_endpoint_exists():
    """测试线程诊断 API 端点存在"""
    source = (ROOT / 'api' / 'performance_diagnose.py').read_text(encoding='utf-8')
    # 检查是否有处理 thread 工具的端点
    assert 'threads' in source, "performance_diagnose.py 应处理 threads 工具"


def test_thread_diagnosis_frontend_function():
    """测试前端有渲染线程诊断的 JS 函数"""
    app_ui = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
    # 检查是否有 renderThreadDiagnosis 或类似函数
    has_render = 'renderThread' in app_ui or 'renderThreads' in app_ui
    assert has_render, "app-ui.js 应包含 renderThread 相关函数"


def test_thread_panel_html_exists():
    """测试 index.html 包含线程诊断面板或入口"""
    index = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
    # 检查是否有线程诊断面板
    has_panel = 'panel-thread' in index or 'thread-diagnosis' in index or '线程' in index
    assert has_panel, "index.html 应包含线程诊断面板或入口"


def test_thread_deadlock_check():
    """测试死锁检测功能存在"""
    source = (ROOT / 'api' / 'performance_diagnose.py').read_text(encoding='utf-8')
    # 检查是否有 thread -b 的调用
    assert 'thread -b' in source or 'deadlock' in source.lower(), "应支持死锁检测"


def test_thread_stack_clickable():
    """测试点击线程可显示堆栈"""
    app_ui = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
    # 检查是否有显示堆栈的函数
    has_stack = 'showStack' in app_ui or 'renderStack' in app_ui or 'threadStack' in app_ui
    assert has_stack, "应支持点击线程显示堆栈"

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
