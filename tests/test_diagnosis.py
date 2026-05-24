#!/usr/bin/env python3
"""诊断能力执行引擎 - 单元测试

测试范围：
1. ArthasCommandExecutor 异步执行、状态轮询、取消
2. ConnectionSelector 连接类型选择
3. 参数替换安全机制
4. API 路由基本逻辑
"""
import json
import sys
import time
import threading
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.core.arthas_executor import (
    ArthasCommandExecutor,
    ExecutionRecord,
    ExecutionStatus,
    _execution_store,
    _execution_store_lock,
    _store_execution,
    _get_execution,
    _is_safe_command,
)
from backend.core.connection_selector import (
    ConnectionSelector,
    ConnectionType,
)
from backend.core.command_builder import build_command
from backend.core.parameter_validator import ParameterValidator


# ═══════════════════════════════════════════════════════════════════════════════
# Mock 对象
# ═══════════════════════════════════════════════════════════════════════════════

class MockHttpClient:
    """模拟 ArthasHttpClient"""

    def __init__(self):
        self.exec_calls = []
        self._session_counter = 0
        self._async_command_submitted = False

    def ping(self, retries=1, delay=0):
        return True

    def exec_once(self, command, timeout_ms=30000):
        self.exec_calls.append(command)
        return {
            'state': 'SUCCEEDED',
            'body': {'results': [{'output': f'Output for: {command}'}]},
        }

    def init_session(self):
        self._session_counter += 1
        return {'sessionId': f'session-{self._session_counter}'}

    def exec_async(self, session_id, command):
        self._async_command_submitted = True
        self.exec_calls.append(command)
        return {'state': 'SUCCEEDED', 'sessionId': session_id}

    def pull_results(self, session_id, consumer_id):
        if self._async_command_submitted:
            self._async_command_submitted = False
            return {
                'state': 'SUCCEEDED',
                'body': {'results': [{'output': 'Async output'}]},
            }
        return {'state': 'WAITING'}

    def interrupt_job(self, session_id):
        return {'state': 'SUCCEEDED'}

    def close_session(self, session_id):
        return {'state': 'SUCCEEDED'}


class MockFailingHttpClient:
    """模拟失败的 ArthasHttpClient"""

    def ping(self, retries=1, delay=0):
        return False

    def exec_once(self, command, timeout_ms=30000):
        raise ConnectionError("Arthas 连接已断开")

    def init_session(self):
        raise ConnectionError("无法建立 Session")


class MockConnection:
    """模拟 ArthasConnection"""

    def __init__(self, client=None):
        self.connection_id = 'test-conn-001'
        self.user_id = 1
        self.cluster_name = 'test-cluster'
        self.namespace = 'default'
        self.pod_name = 'test-pod'
        self.http_client = client or MockHttpClient()
        self._arthas_ready = True
        self._pf_proc = None
        self.local_port = 32001
        self.arthas_version = '3.7.1'

    @property
    def target(self):
        class Target:
            cluster_name = 'test-cluster'
            namespace = 'default'
            pod_name = 'test-pod'
        return Target()


class MockPodConnection:
    """模拟 PodConnection"""

    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive


class MockArthasConnectionWithPod:
    """模拟带 Pod 连接的 ArthasConnection"""

    def __init__(self):
        self.connection_id = 'test-conn-pod'
        self.user_id = 1
        self.http_client = MockHttpClient()
        self.pod_conn = MockPodConnection(alive=True)
        self._pod_connected = True
        self._arthas_ready = True
        self._pf_proc = None
        self.local_port = 32002

    @property
    def target(self):
        class Target:
            cluster_name = 'test-cluster'
            namespace = 'default'
            pod_name = 'test-pod'
        return Target()


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutionRecord 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecutionRecord:
    """执行记录单元测试"""

    def test_create_record(self):
        """创建执行记录"""
        record = ExecutionRecord(
            execution_id='exec-test-001',
            connection_id='conn-001',
            command='dashboard -n 1',
            user_id=1,
        )
        assert record.execution_id == 'exec-test-001'
        assert record.status == ExecutionStatus.PENDING
        assert record.result is None
        assert record.created_at > 0

    def test_mark_running(self):
        """标记为运行中"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard')
        record.mark_running(session_id='session-123', consumer_id='consumer-456')

        assert record.status == ExecutionStatus.RUNNING
        assert record.session_id == 'session-123'
        assert record.consumer_id == 'consumer-456'
        assert record.started_at is not None
        # duration_ms 在 running 状态下会计算当前耗时（>0），finished_at 为 None 时用 time.time()
        assert record.duration_ms is not None
        assert record.duration_ms >= 0

    def test_mark_succeeded(self):
        """标记为成功"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard')
        record.mark_running()
        time.sleep(0.01)
        record.mark_succeeded({'state': 'SUCCEEDED', 'body': {}})

        assert record.status == ExecutionStatus.SUCCEEDED
        assert record.result is not None
        assert record.finished_at is not None
        assert record.duration_ms is not None
        assert record.duration_ms >= 0

    def test_mark_failed(self):
        """标记为失败"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard')
        record.mark_running()
        record.mark_failed("连接超时")

        assert record.status == ExecutionStatus.FAILED
        assert record.error == "连接超时"

    def test_mark_cancelled(self):
        """标记为取消"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard')
        record.mark_running()
        record.mark_cancelled()

        assert record.status == ExecutionStatus.CANCELLED
        assert record.finished_at is not None

    def test_mark_timeout(self):
        """标记为超时"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard')
        record.mark_running()
        record.mark_timeout()

        assert record.status == ExecutionStatus.TIMEOUT

    def test_to_dict(self):
        """序列化为字典"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard', user_id=1)
        record.mark_running()
        record.mark_succeeded({'state': 'SUCCEEDED'})

        d = record.to_dict()
        assert d['execution_id'] == 'exec-001'
        assert d['connection_id'] == 'conn-001'
        assert d['command'] == 'dashboard'
        assert d['user_id'] == 1
        assert d['status'] == 'succeeded'
        assert d['result'] is not None
        assert 'created_at' in d
        assert 'duration_ms' in d

    def test_elapsed_ms(self):
        """总耗时计算"""
        record = ExecutionRecord('exec-001', 'conn-001', 'dashboard')
        time.sleep(0.01)
        assert record.elapsed_ms >= 10  # 至少 10ms


# ═══════════════════════════════════════════════════════════════════════════════
# ArthasCommandExecutor 异步执行测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAsyncExecution:
    """异步执行引擎测试"""

    def setup_method(self):
        """每个测试前清理执行记录"""
        _execution_store.clear()

    def test_execute_async_success(self):
        """异步执行成功"""
        connection = MockConnection()
        exec_id = ArthasCommandExecutor.execute_async(
            connection, 'dashboard -n 1', user_id=1
        )

        assert exec_id.startswith('exec-')
        record = _get_execution(exec_id)
        assert record is not None
        assert record.command == 'dashboard -n 1'

        # 等待后台线程完成
        time.sleep(0.5)

        # 轮询结果
        status = ArthasCommandExecutor.poll_execution(exec_id)
        assert status is not None
        assert status['status'] in ('running', 'succeeded')
        # 后台线程可能已完成
        if status['status'] == 'succeeded':
            assert status['result']['state'] == 'SUCCEEDED'

    def test_execute_async_high_risk_no_confirm(self):
        """异步执行高危命令（未确认）"""
        connection = MockConnection()
        exec_id = ArthasCommandExecutor.execute_async(
            connection, 'retransform com.example.Service',
            user_id=1, confirmed=False,
        )

        record = _get_execution(exec_id)
        assert record.status == ExecutionStatus.REQUIRE_CONFIRM
        assert record.error is not None
        assert '高危' in record.error

        # 轮询确认状态
        status = ArthasCommandExecutor.poll_execution(exec_id)
        assert status['status'] == 'require_confirm'

    def test_execute_async_high_risk_confirmed(self):
        """异步执行高危命令（已确认）"""
        connection = MockConnection()
        exec_id = ArthasCommandExecutor.execute_async(
            connection, 'retransform com.example.Service',
            user_id=1, confirmed=True,
        )

        assert exec_id.startswith('exec-')
        record = _get_execution(exec_id)
        assert record.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING)

    def test_execute_async_no_http_client(self):
        """异步执行时 http_client 为空"""
        connection = MockConnection()
        connection.http_client = None
        exec_id = ArthasCommandExecutor.execute_async(
            connection, 'dashboard -n 1', user_id=1,
        )

        # 等待后台线程
        time.sleep(0.3)

        record = _get_execution(exec_id)
        assert record.status == ExecutionStatus.FAILED

    def test_execute_async_connection_error(self):
        """异步执行时连接错误"""
        connection = MockConnection(client=MockFailingHttpClient())
        exec_id = ArthasCommandExecutor.execute_async(
            connection, 'dashboard -n 1', user_id=1,
        )

        # 等待后台线程
        time.sleep(0.3)

        record = _get_execution(exec_id)
        assert record.status == ExecutionStatus.FAILED

    def test_poll_nonexistent(self):
        """轮询不存在的执行"""
        status = ArthasCommandExecutor.poll_execution('exec-nonexistent')
        assert status is None

    def test_cancel_execution(self):
        """取消执行"""
        connection = MockConnection()
        exec_id = ArthasCommandExecutor.execute_async(
            connection, 'profiler start --event cpu --duration 120',
            user_id=1,
        )

        # 确保还没完成
        record = _get_execution(exec_id)
        if record and record.status == ExecutionStatus.RUNNING:
            success = ArthasCommandExecutor.cancel_execution(exec_id, connection)
            assert success is True
            assert record.status == ExecutionStatus.CANCELLED
        else:
            # 如果执行已经很快完成了，测试取消已完成的执行
            success = ArthasCommandExecutor.cancel_execution(exec_id, connection)
            # 已完成的执行不可取消
            assert success is False

    def test_cancel_nonexistent(self):
        """取消不存在的执行"""
        success = ArthasCommandExecutor.cancel_execution('exec-nonexistent')
        assert success is False

    def test_cancel_already_finished(self):
        """取消已结束的执行"""
        record = ExecutionRecord('exec-finished', 'conn-001', 'dashboard')
        record.mark_succeeded({'state': 'SUCCEEDED'})
        _store_execution(record)

        success = ArthasCommandExecutor.cancel_execution('exec-finished')
        assert success is False  # 已结束不可取消

    def test_get_execution(self):
        """获取执行记录"""
        record = ExecutionRecord('exec-get', 'conn-001', 'thread -n 5')
        _store_execution(record)

        result = ArthasCommandExecutor.get_execution('exec-get')
        assert result is not None
        assert result['execution_id'] == 'exec-get'
        assert result['command'] == 'thread -n 5'

    def test_get_nonexistent_execution(self):
        """获取不存在的执行记录"""
        result = ArthasCommandExecutor.get_execution('exec-nonexistent')
        assert result is None

    def test_execution_store_thread_safety(self):
        """执行记录存储的线程安全测试"""
        errors = []

        def _create_records(thread_id):
            try:
                for i in range(50):
                    eid = f'exec-t{thread_id}-{i}'
                    record = ExecutionRecord(eid, f'conn-{thread_id}', f'cmd-{i}')
                    _store_execution(record)
                    retrieved = _get_execution(eid)
                    assert retrieved is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_create_records, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Thread safety errors: {errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# ConnectionSelector 测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionSelector:
    """连接选择器测试"""

    def test_resolve_type_none_capability(self):
        """空能力 → NONE"""
        assert ConnectionSelector.resolve_type(None) == ConnectionType.NONE
        assert ConnectionSelector.resolve_type({}) == ConnectionType.NONE

    def test_resolve_type_scenario(self):
        """场景方案 → ARTHAS"""
        cap = {
            'category': 'scenario',
            'steps_json': json.dumps({
                'steps': [{'command': 'trace ${class} ${method}', 'desc': 'test'}]
            }),
        }
        assert ConnectionSelector.resolve_type(cap) == ConnectionType.ARTHAS

    def test_resolve_type_quick_tool(self):
        """快捷工具 → ARTHAS"""
        cap = {
            'category': 'quick',
            'arthas_command': 'dashboard -n 1',
        }
        assert ConnectionSelector.resolve_type(cap) == ConnectionType.ARTHAS

    def test_resolve_type_tool_with_arthas_command(self):
        """诊断模板（有 arthas_command）→ ARTHAS"""
        cap = {
            'category': 'tool',
            'arthas_command': 'trace ${class} ${method}',
        }
        assert ConnectionSelector.resolve_type(cap) == ConnectionType.ARTHAS

    def test_resolve_type_pod_only(self):
        """Pod 监控 → POD"""
        cap = {
            'category': 'pod_monitor',
        }
        assert ConnectionSelector.resolve_type(cap) == ConnectionType.POD

    def test_resolve_type_ai_handler(self):
        """AI 诊断（有 handler）→ ARTHAS"""
        cap = {
            'category': 'ai',
            'handler': 'performance_diagnose.run_diagnosis',
        }
        assert ConnectionSelector.resolve_type(cap) == ConnectionType.ARTHAS

    def test_resolve_type_for_command_arthas(self):
        """Arthas 命令 → ARTHAS"""
        assert ConnectionSelector.resolve_type_for_command('dashboard -n 1') == ConnectionType.ARTHAS
        assert ConnectionSelector.resolve_type_for_command('trace com.example.Service *') == ConnectionType.ARTHAS
        assert ConnectionSelector.resolve_type_for_command('thread -n 5') == ConnectionType.ARTHAS
        assert ConnectionSelector.resolve_type_for_command('jad --source-only com.example.Foo') == ConnectionType.ARTHAS

    def test_resolve_type_for_command_empty(self):
        """空命令 → NONE"""
        assert ConnectionSelector.resolve_type_for_command('') == ConnectionType.NONE

    def test_resolve_type_for_command_unknown(self):
        """未知命令 → NONE"""
        assert ConnectionSelector.resolve_type_for_command('unknown_command') == ConnectionType.NONE

    def test_validate_connection_none(self):
        """验证空连接"""
        error = ConnectionSelector.validate_connection(None, ConnectionType.ARTHAS)
        assert error is not None
        assert '不存在' in error

    def test_validate_connection_none_type(self):
        """NONE 类型不需要连接"""
        error = ConnectionSelector.validate_connection(None, ConnectionType.NONE)
        assert error is None

    def test_validate_connection_valid(self):
        """验证有效 Arthas 连接"""
        conn = MockConnection()
        error = ConnectionSelector.validate_connection(conn, ConnectionType.ARTHAS)
        assert error is None

    def test_validate_connection_no_http_client(self):
        """验证无 http_client 的连接"""
        conn = MockConnection()
        conn.http_client = None
        error = ConnectionSelector.validate_connection(conn, ConnectionType.ARTHAS)
        assert error is not None
        assert 'HTTP 客户端' in error

    def test_validate_pod_connection_alive(self):
        """验证存活的 Pod 连接"""
        conn = MockArthasConnectionWithPod()
        error = ConnectionSelector.validate_connection(conn, ConnectionType.POD)
        assert error is None

    def test_validate_pod_connection_dead(self):
        """验证不可用的 Pod 连接"""
        conn = MockArthasConnectionWithPod()
        conn.pod_conn = MockPodConnection(alive=False)
        error = ConnectionSelector.validate_connection(conn, ConnectionType.POD)
        assert error is not None

    def test_get_connection_info(self):
        """获取连接信息"""
        conn = MockConnection()
        info = ConnectionSelector.get_connection_info(conn)
        assert info['type'] == 'arthas'
        assert info['cluster_name'] == 'test-cluster'
        assert info['namespace'] == 'default'
        assert info['pod_name'] == 'test-pod'
        assert info['arthas_ready'] is True
        assert info['local_port'] == 32001

    def test_get_connection_info_none(self):
        """获取空连接信息"""
        info = ConnectionSelector.get_connection_info(None)
        assert info['type'] == 'none'
        assert info['status'] == 'not_connected'


# ═══════════════════════════════════════════════════════════════════════════════
# 命令安全检查测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommandSafety:
    """命令安全机制测试"""

    def test_safe_commands(self):
        """安全的 Arthas 命令"""
        safe_cmds = [
            'dashboard -n 1',
            'thread -n 15',
            'trace com.example.Service *',
            'watch com.example.Service login params',
            'jad --source-only com.example.Service',
            'sc -d com.example.Service',
            'profiler start --event cpu --duration 30',
        ]
        for cmd in safe_cmds:
            assert _is_safe_command(cmd), f"命令应该被认为是安全的: {cmd}"

    def test_unsafe_semicolon(self):
        """分号不安全"""
        assert not _is_safe_command('dashboard; rm -rf /')

    def test_unsafe_pipe(self):
        """管道不安全"""
        assert not _is_safe_command('dashboard | cat')

    def test_unsafe_ampersand(self):
        """& 不安全"""
        assert not _is_safe_command('dashboard & cat')

    def test_unsafe_backtick(self):
        """反引号不安全"""
        assert not _is_safe_command('`whoami`')

    def test_unsafe_dollar_paren(self):
        """$(...) 不安全"""
        assert not _is_safe_command('$(whoami)')

    def test_unsafe_redirect(self):
        """重定向不安全"""
        assert not _is_safe_command('dashboard > /tmp/output')

    def test_unsafe_newline(self):
        """换行不安全"""
        assert not _is_safe_command('dashboard\nrm -rf /')

    def test_unsafe_empty(self):
        """空命令不安全"""
        assert not _is_safe_command('')
        assert not _is_safe_command('   ')

    def test_unsafe_too_long(self):
        """过长命令不安全"""
        assert not _is_safe_command('x' * 2000)

    def test_safe_with_param_substitution(self):
        """${param} 替换后是安全的"""
        # ${class} 在替换后会变成实际类名
        cmd = 'trace com.example.Service doWork'
        assert _is_safe_command(cmd)


# ═══════════════════════════════════════════════════════════════════════════════
# 参数验证 + 命令构建集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestParameterIntegration:
    """参数验证 + 命令构建集成测试"""

    def test_trace_command_build(self):
        """构建 trace 命令"""
        template = 'trace ${class} ${method} -n 10'
        params = {'class': 'com.example.Service', 'method': 'doWork'}
        result = build_command(template, params)
        assert result == 'trace com.example.Service doWork -n 10'

    def test_watch_command_with_default(self):
        """带默认值的 watch 命令"""
        template = "watch ${class} ${method:-*} '{params}' -x 3"
        params = {'class': 'com.example.Service'}
        result = build_command(template, params)
        assert result == "watch com.example.Service * '{params}' -x 3"

    def test_validate_required_param(self):
        """校验必填参数"""
        schema = json.dumps([
            {'name': 'class', 'label': '类名', 'required': True, 'pattern': '^[A-Za-z_$][\\w.$*]*$'}
        ])
        # 缺失必填参数
        error = ParameterValidator.validate(schema, {})
        assert error is not None
        assert '缺少必填参数' in error

        # 提供必填参数
        error = ParameterValidator.validate(schema, {'class': 'com.example.Service'})
        assert error is None

    def test_validate_pattern_reject(self):
        """正则校验拒绝非法值"""
        schema = json.dumps([
            {'name': 'class', 'label': '类名', 'pattern': '^[A-Za-z_$][\\w.$*]*$'}
        ])
        error = ParameterValidator.validate(schema, {'class': '123bad'})
        assert error is not None
        assert '格式不正确' in error

    def test_full_flow_validate_and_build(self):
        """完整流程：校验 → 构建"""
        from api.diagnosis import _validate_and_build_command

        schema = json.dumps([
            {'name': 'class', 'label': '类名', 'required': True, 'pattern': '^[A-Za-z_$][\\w.$*]*$'},
            {'name': 'method', 'label': '方法名', 'default': '*', 'pattern': '^[\\w.*]*$'}
        ])
        template = 'trace ${class} ${method} -n 10'

        # 成功流程
        result = _validate_and_build_command(template, schema, {
            'class': 'com.example.Service',
            'method': 'doWork',
        })
        assert result['ok'] is True
        assert result['command'] == 'trace com.example.Service doWork -n 10'

        # 参数校验失败
        result = _validate_and_build_command(template, schema, {})
        assert result['ok'] is False
        assert '缺少必填参数' in result['error']

        # 正则校验失败
        result = _validate_and_build_command(template, schema, {
            'class': '123bad',
        })
        assert result['ok'] is False
        assert '格式不正确' in result['error']


# ═══════════════════════════════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
