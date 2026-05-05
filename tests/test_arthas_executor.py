"""统一 Arthas 执行器测试"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.core.arthas_executor import (
    ArthasCommandExecutor,
    _COMMAND_TIMEOUT_CONFIG,
    _HIGH_RISK_COMMANDS,
    _READ_ONLY_COMMANDS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 命令配置测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_command_timeout_config():
    """测试命令超时配置完整性"""
    # 常用命令都应该有超时配置
    essential_commands = [
        'dashboard', 'thread', 'trace', 'watch', 'stack', 'monitor',
        'profiler', 'heapdump', 'jfr', 'jad', 'sc', 'sm',
        'logger', 'vmoption', 'ognl', 'redefine', 'retransform',
    ]
    
    for cmd in essential_commands:
        assert cmd in _COMMAND_TIMEOUT_CONFIG, f"命令 {cmd} 缺少超时配置"
        timeout = _COMMAND_TIMEOUT_CONFIG[cmd]
        assert isinstance(timeout, int), f"命令 {cmd} 的超时配置应该是整数"
        assert timeout > 0, f"命令 {cmd} 的超时配置应该大于 0"


def test_high_risk_commands():
    """测试高危命令列表"""
    # 这些命令应该是高危的
    expected_high_risk = {
        'redefine',      # 类重新定义
        'retransform',   # 类热替换
        'heapdump',      # 堆Dump
        'profiler',      # 性能采样
        'logger',        # 日志级别修改
        'vmoption',      # JVM参数修改
    }
    
    for cmd in expected_high_risk:
        assert cmd in _HIGH_RISK_COMMANDS, f"命令 {cmd} 应该被标记为高危"


def test_read_only_commands():
    """测试只读命令列表"""
    # 这些命令应该是只读的
    expected_read_only = {
        'dashboard', 'thread', 'jvm', 'sysprop', 'sysenv',
        'sc', 'sm', 'jad', 'classloader', 'logger',
        'trace', 'watch', 'stack', 'monitor',
    }
    
    for cmd in expected_read_only:
        assert cmd in _READ_ONLY_COMMANDS, f"命令 {cmd} 应该被标记为只读"


# ═══════════════════════════════════════════════════════════════════════════════
# 命令解析测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_parse_command_name():
    """测试命令名称解析"""
    test_cases = [
        ("dashboard -n 1", "dashboard"),
        ("trace com.example.Service * -n 5", "trace"),
        ("watch com.example.Service login '{params}'", "watch"),
        ("thread -n 5", "thread"),
        ("profiler start --event cpu --duration 30", "profiler"),
        ("  jad --source-only com.example.Service  ", "jad"),
        ("", ""),
    ]
    
    for command, expected in test_cases:
        result = ArthasCommandExecutor._parse_command_name(command)
        assert result == expected, f"命令解析失败: {command} -> {result} (期望 {expected})"


def test_get_timeout():
    """测试超时配置获取"""
    # 有配置的命令
    assert ArthasCommandExecutor._get_timeout('dashboard') == 15000
    assert ArthasCommandExecutor._get_timeout('trace') == 60000
    assert ArthasCommandExecutor._get_timeout('profiler') == 120000
    
    # 没有配置的命令（默认 30 秒）
    assert ArthasCommandExecutor._get_timeout('unknown_command') == 30000


# ═══════════════════════════════════════════════════════════════════════════════
# 命令分类测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_is_read_only():
    """测试只读命令判断"""
    assert ArthasCommandExecutor.is_read_only('dashboard -n 1') is True
    assert ArthasCommandExecutor.is_read_only('thread -n 5') is True
    assert ArthasCommandExecutor.is_read_only('trace com.example.Service *') is True
    
    assert ArthasCommandExecutor.is_read_only('redefine /tmp/Service.class') is False
    assert ArthasCommandExecutor.is_read_only('heapdump /tmp/heap.hprof') is False


def test_is_high_risk():
    """测试高危命令判断"""
    assert ArthasCommandExecutor.is_high_risk('redefine /tmp/Service.class') is True
    assert ArthasCommandExecutor.is_high_risk('heapdump /tmp/heap.hprof') is True
    assert ArthasCommandExecutor.is_high_risk('profiler start') is True
    assert ArthasCommandExecutor.is_high_risk('logger --name root --level DEBUG') is True
    
    assert ArthasCommandExecutor.is_high_risk('dashboard -n 1') is False
    assert ArthasCommandExecutor.is_high_risk('thread -n 5') is False
    assert ArthasCommandExecutor.is_high_risk('trace com.example.Service *') is False


def test_get_command_info():
    """测试命令信息获取"""
    info = ArthasCommandExecutor.get_command_info('dashboard -n 1')
    assert info['name'] == 'dashboard'
    assert info['timeout_ms'] == 15000
    assert info['is_read_only'] is True
    assert info['is_high_risk'] is False
    assert info['risk_level'] == 'low'
    
    info = ArthasCommandExecutor.get_command_info('redefine /tmp/Service.class')
    assert info['name'] == 'redefine'
    assert info['timeout_ms'] == 60000
    assert info['is_read_only'] is False
    assert info['is_high_risk'] is True
    assert info['risk_level'] == 'high'


# ═══════════════════════════════════════════════════════════════════════════════
# Mock 执行测试
# ═══════════════════════════════════════════════════════════════════════════════

class MockConnection:
    """模拟 ArthasConnection"""
    
    def __init__(self):
        self.id = 'test-conn-001'
        self.user_id = 1
        self.cluster_name = 'test-cluster'
        self.namespace = 'default'
        self.pod_name = 'test-pod'
        self.http_client = MockHttpClient()


class MockHttpClient:
    """模拟 ArthasHttpClient"""
    
    def exec_once(self, command: str, timeout_ms: int = 30000) -> dict:
        """模拟执行命令"""
        return {
            'state': 'SUCCEEDED',
            'body': {
                'results': [{'output': f'Mock output for: {command}'}]
            },
            'duration_ms': 100,
        }


def test_execute_success():
    """测试成功执行"""
    connection = MockConnection()
    result = ArthasCommandExecutor.execute(
        connection,
        'dashboard -n 1',
        skip_audit=True,  # 测试时跳过审计
        skip_history=True,  # 测试时跳过历史
    )
    
    assert result['state'] == 'SUCCEEDED'
    assert 'duration_ms' in result
    # duration_ms 是实际执行耗时，由执行器计算，至少为 0
    assert result['duration_ms'] >= 0


def test_execute_high_risk_require_confirm():
    """测试高危命令需要确认"""
    connection = MockConnection()
    
    # 未确认的高危命令
    result = ArthasCommandExecutor.execute(
        connection,
        'redefine /tmp/Service.class',
        skip_audit=True,
        skip_history=True,
        confirmed=False,  # 未确认
    )
    
    assert result['state'] == 'REQUIRE_CONFIRM'
    assert 'risk_level' in result
    assert result['risk_level'] == 'high'
    
    # 已确认的高危命令
    result = ArthasCommandExecutor.execute(
        connection,
        'redefine /tmp/Service.class',
        skip_audit=True,
        skip_history=True,
        confirmed=True,  # 已确认
    )
    
    assert result['state'] == 'SUCCEEDED'


def test_execute_custom_timeout():
    """测试自定义超时"""
    connection = MockConnection()
    result = ArthasCommandExecutor.execute(
        connection,
        'dashboard -n 1',
        timeout_ms=5000,  # 自定义 5 秒
        skip_audit=True,
        skip_history=True,
    )
    
    assert result['state'] == 'SUCCEEDED'


# ═══════════════════════════════════════════════════════════════════════════════
# 批量执行测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_execute_batch_success():
    """测试批量执行成功"""
    connection = MockConnection()
    
    commands = [
        {'command': 'dashboard -n 1', 'desc': 'JVM Dashboard'},
        {'command': 'thread -n 5', 'desc': '线程快照'},
        {'command': 'trace com.example.Service *', 'desc': 'Trace 调用链'},
    ]
    
    results = ArthasCommandExecutor.execute_batch(
        connection,
        commands,
        fail_fast=True,
    )
    
    assert len(results) == 3
    
    # 验证每步结果
    for idx, result in enumerate(results, start=1):
        assert result['step'] == idx
        assert result['success'] is True
        assert 'command' in result
        assert 'desc' in result
        assert 'result' in result
    
    # 验证步骤描述
    assert results[0]['desc'] == 'JVM Dashboard'
    assert results[1]['desc'] == '线程快照'
    assert results[2]['desc'] == 'Trace 调用链'


def test_execute_batch_fail_fast():
    """测试批量执行快速失败"""
    connection = MockConnection()
    
    # 模拟第二步失败
    class MockFailingHttpClient:
        def exec_once(self, command: str, timeout_ms: int = 30000) -> dict:
            if 'thread' in command:
                return {
                    'state': 'FAILED',
                    'message': 'Thread command failed',
                    'duration_ms': 50,
                }
            return {
                'state': 'SUCCEEDED',
                'body': {'results': []},
                'duration_ms': 100,
            }
    
    connection.http_client = MockFailingHttpClient()
    
    commands = [
        {'command': 'dashboard -n 1', 'desc': 'Step 1'},
        {'command': 'thread -n 5', 'desc': 'Step 2 (will fail)'},
        {'command': 'trace com.example.Service *', 'desc': 'Step 3 (should not run)'},
    ]
    
    results = ArthasCommandExecutor.execute_batch(
        connection,
        commands,
        fail_fast=True,  # 快速失败
    )
    
    # 应该只执行了前两步
    assert len(results) == 2
    assert results[0]['success'] is True
    assert results[1]['success'] is False


def test_execute_batch_continue_on_failure():
    """测试批量执行失败后继续"""
    connection = MockConnection()
    
    # 模拟第二步失败
    class MockFailingHttpClient:
        def exec_once(self, command: str, timeout_ms: int = 30000) -> dict:
            if 'thread' in command:
                return {
                    'state': 'FAILED',
                    'message': 'Thread command failed',
                    'duration_ms': 50,
                }
            return {
                'state': 'SUCCEEDED',
                'body': {'results': []},
                'duration_ms': 100,
            }
    
    connection.http_client = MockFailingHttpClient()
    
    commands = [
        {'command': 'dashboard -n 1', 'desc': 'Step 1'},
        {'command': 'thread -n 5', 'desc': 'Step 2 (will fail)'},
        {'command': 'trace com.example.Service *', 'desc': 'Step 3'},
    ]
    
    results = ArthasCommandExecutor.execute_batch(
        connection,
        commands,
        fail_fast=False,  # 失败后继续
    )
    
    # 应该执行了所有三步
    assert len(results) == 3
    assert results[0]['success'] is True
    assert results[1]['success'] is False
    assert results[2]['success'] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
