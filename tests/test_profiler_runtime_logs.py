#!/usr/bin/env python3
"""采样任务日志回归测试"""
import pathlib
import sys
import unittest

sys.path.insert(0, r'e:/tmp/k8s-arthas-tool')

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel_path):
    return (ROOT / rel_path).read_text(encoding='utf-8')


class TestProfilerRuntimeLogs(unittest.TestCase):
    """采样日志应来自后端真实执行进度"""

    def test_profiler_service_updates_task_message_during_workflow(self):
        """后台 Workflow 运行期间应持续回写最新日志到 profiler_tasks.message"""
        src = _read('services/profiler_service.py')

        assert 'progress_callback' in src
        assert 'workflow.run(' in src
        assert "'message': message" in src
        assert "update_data['progress'] = progress" in src

    def test_profiler_service_preserves_workflow_failure_status(self):
        """Workflow 返回失败时服务层不能把任务误标记为 completed"""
        src = _read('services/profiler_service.py')

        assert "result_status = result.get('status', 'completed')" in src
        assert "final_status = 'completed' if result_status == 'completed' else 'failed'" in src
        assert "final_progress = 100 if final_status == 'completed'" in src
        assert "'status': final_status" in src
        assert "self._write_to_diagnosis_history(task_id, task, result, final_status)" in src

    def test_profiler_workflow_accepts_progress_callback(self):
        """ProfilerWorkflow 应支持进度回调，便于服务层同步真实后台日志"""
        src = _read('backend/core/profiler.py')

        assert 'progress_callback=None' in src
        assert 'self.progress_callback' in src
        assert 'self.progress_callback(entry)' in src

    def test_async_profiler_start_is_verified_by_status(self):
        """profiler start 返回成功后应再查 profiler status，确认真的进入运行态"""
        src = _read('backend/core/profiler.py')
        run_profiler = src[src.index('def _run_profiler'):src.index('# ─────────────────────────────────────────────────────────────────────────\n    # JDK Flight Recorder')]

        assert 'client.exec_once(start_cmd' in run_profiler
        assert 'profiler status' in run_profiler
        assert '_profiler_is_running' in run_profiler
        assert 'profiler 未进入运行状态' in run_profiler

    def test_profile_status_returns_backend_message_not_client_saved_log(self):
        """旧 profile 状态接口应同时返回顶层 message 和兼容 logs"""
        src = _read('server.py')

        assert '"message": task.get(\'message\', \'\')' in src or '"message": task.get("message", "")' in src
        assert 'logs = [{"message": task[\'message\']' in src or 'logs = [{"message": task["message"]' in src

    def test_profile_start_uses_resolved_runtime_connection_id(self):
        """创建任务时应使用 _ensure_connection 返回的真实 connection_id，避免丢失 @u 后缀"""
        src = _read('server.py')

        assert "getattr(conn, 'connection_id', None) or conn_id" in src
        assert '"connection_id": conn_id' in src


class TestProfilerFrontendPolling(unittest.TestCase):
    """前端轮询不应制造无意义日志写入"""

    def test_pf_log_does_not_post_each_line_to_profile_logs(self):
        """pfLog 只负责渲染日志，不应 POST /api/profile/logs 造成误写和请求风暴"""
        src = _read('static/js/app-ui.js')
        pf_log = src[src.index('async function pfLog'):src.index('function pfClearLog')]

        assert '/profile/logs' not in pf_log
        assert 'fetch(' not in pf_log

    def test_gc_probe_does_not_start_profiler_poll_timer(self):
        """GC 探测只执行一次接口调用，不应启动采样任务轮询"""
        src = _read('static/js/app-ui.js')
        gc_fn = src[src.index('async function pfRunGcLog'):src.index('async function gcDownloadPath')]

        assert 'setInterval(pfPoll' not in gc_fn
        assert '_pfPollTimer' not in gc_fn

    def test_profiler_start_sends_current_connection_id(self):
        """采样启动请求必须携带当前连接 ID，避免后端重新建立错误连接"""
        src = _read('static/js/app-ui.js')

        assert 'function profilerTargetPayload' in src
        assert '_currentConnId || window._currentConnId' in src
        assert 'profilerTargetPayload(t)' in src

    def test_profiler_poll_timer_is_singleton(self):
        """启动/恢复轮询前应清理旧定时器，避免重复请求"""
        src = _read('static/js/app-ui.js')
        helper = src[src.index('function startProfilerPollTimer'):src.index('async function pfStart')]

        assert 'resetProfilerPollTimer();' in helper
        assert '_pfPollTimer = setInterval(pfPoll, intervalMs)' in helper

    def test_frontend_progress_uses_backend_progress(self):
        """前端进度条应由后端 progress 驱动，不再按本地 duration 预估完成"""
        src = _read('static/js/app-ui.js')
        poll_fn = src[src.index('async function pfPoll'):src.index('function _isQuickTask')]

        assert 'serverProgress' in poll_fn
        assert '后端仍在执行' in poll_fn
        assert '采样完成，下载中' not in poll_fn


if __name__ == '__main__':
    unittest.main()
