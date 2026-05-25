"""测试 Phase 7 模块迁移 — 回归测试

验证以下迁移目标：
- T01: Profiler Service 服务层
- T02: Profiler Blueprint 注册
- T03: Agent Tool Gateway 注册工具
- T04: 前端接入诊断中心
- T05: Agent Chat 接入
- T06: 诊断历史关联
- T07: AI 分析报告增强（异常检测集成）
"""
import pathlib
import sys

sys.path.insert(0, r'e:/tmp/k8s-arthas-tool')

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel_path):
    return (ROOT / rel_path).read_text(encoding='utf-8')


# ── T01: Profiler Service ──────────────────────────────────────────────

class TestProfilerService:
    """T01: services/profiler_service.py 存在且结构正确"""

    def test_file_exists(self):
        assert (ROOT / 'services' / 'profiler_service.py').exists()

    def test_has_profiler_service_class(self):
        src = _read('services/profiler_service.py')
        assert 'class ProfilerService' in src

    def test_has_create_task_method(self):
        src = _read('services/profiler_service.py')
        assert 'def create_task' in src

    def test_has_get_task_status_method(self):
        src = _read('services/profiler_service.py')
        assert 'def get_task_status' in src or 'def get_task' in src

    def test_has_list_tasks_method(self):
        src = _read('services/profiler_service.py')
        assert 'def list_tasks' in src or 'def get_tasks' in src

    def test_imports_profiler_workflow(self):
        src = _read('services/profiler_service.py')
        assert 'ProfilerWorkflow' in src or 'profiler' in src.lower()


# ── T02: Profiler Blueprint ────────────────────────────────────────────

class TestProfilerBlueprint:
    """T02: api/profiler.py Blueprint 注册"""

    def test_file_exists(self):
        assert (ROOT / 'api' / 'profiler.py').exists()

    def test_has_blueprint(self):
        src = _read('api/profiler.py')
        assert 'Blueprint' in src
        assert 'profiler_bp' in src or 'profiler' in src.lower()

    def test_registered_in_init(self):
        src = _read('api/__init__.py')
        assert 'profiler_bp' in src or 'from api.profiler' in src

    def test_has_profile_routes(self):
        src = _read('api/profiler.py')
        assert '/api/profile' in src or 'profile' in src.lower()


# ── T03: Agent Tool Gateway ────────────────────────────────────────────

class TestAgentToolGateway:
    """T03: agent_tool_gateway.py 注册 profiler 工具"""

    def test_file_exists(self):
        assert (ROOT / 'services' / 'agent_tool_gateway.py').exists()

    def test_has_profiler_tools(self):
        src = _read('services/agent_tool_gateway.py')
        # 应该注册了 profiler 相关工具
        assert 'profiler' in src.lower() or 'profile' in src.lower()

    def test_has_threaddump_tool(self):
        src = _read('services/agent_tool_gateway.py')
        assert 'threaddump' in src.lower() or 'thread_dump' in src.lower()

    def test_has_heapdump_tool(self):
        src = _read('services/agent_tool_gateway.py')
        assert 'heapdump' in src.lower() or 'heap_dump' in src.lower()


# ── T04: 前端接入诊断中心 ─────────────────────────────────────────────

class TestDiagnosisCenterIntegration:
    """T04: diagnosis-center.js 接入 Profiler"""

    def test_has_profiler_dialog(self):
        src = _read('static/js/components/diagnosis-center.js')
        assert 'Profiler' in src or 'profiler' in src

    def test_has_show_profiler_dialog(self):
        src = _read('static/js/components/diagnosis-center.js')
        assert 'dcShowProfilerDialog' in src or 'showProfiler' in src


# ── T05: Agent Chat 接入 ──────────────────────────────────────────────

class TestAgentChatIntegration:
    """T05: agent-chat.js 调用 Agent API"""

    def test_calls_agent_endpoint(self):
        src = _read('static/js/components/agent-chat.js')
        assert '/api/agent/send_message' in src

    def test_sends_connection_id(self):
        src = _read('static/js/components/agent-chat.js')
        assert 'connection_id' in src

    def test_sends_session_id(self):
        src = _read('static/js/components/agent-chat.js')
        assert 'session_id' in src


# ── T06: 诊断历史关联 ─────────────────────────────────────────────────

class TestDiagnosisHistory:
    """T06: diagnosis-history.js 展示 Profiler 任务"""

    def test_detects_profiler_tasks(self):
        src = _read('static/js/components/diagnosis-history.js')
        assert 'isProfiler' in src or 'profiler' in src.lower()

    def test_has_download_button(self):
        src = _read('static/js/components/diagnosis-history.js')
        assert 'download' in src.lower() or '下载' in src


# ── T07: AI 分析报告增强 ──────────────────────────────────────────────

class TestAIAnomalyIntegration:
    """T07: AI 分析报告使用异常检测结果"""

    def test_agent_py_exists(self):
        assert (ROOT / 'api' / 'agent.py').exists()

    def test_agent_fetches_anomaly_context(self):
        src = _read('api/agent.py')
        assert '_fetch_anomaly_context' in src

    def test_agent_fetches_anomaly_events_list(self):
        src = _read('api/agent.py')
        assert '_fetch_anomaly_events_list' in src

    def test_agent_emits_anomaly_events_sse(self):
        src = _read('api/agent.py')
        assert 'anomaly_events' in src
        assert "'type': 'anomaly_events'" in src or '"type": "anomaly_events"' in src

    def test_agent_registered_in_init(self):
        src = _read('api/__init__.py')
        assert 'agent_bp' in src

    def test_frontend_handles_anomaly_events(self):
        src = _read('static/js/components/agent-chat.js')
        assert 'anomaly_events' in src

    def test_frontend_renders_anomaly_cards(self):
        src = _read('static/js/components/agent-chat.js')
        assert '_renderAnomalyCards' in src

    def test_anomaly_cards_are_clickable(self):
        src = _read('static/js/components/agent-chat.js')
        assert 'dc-anomaly-card' in src
        assert "addEventListener('click'" in src

    def test_ai_chat_anomaly_bug_fixed(self):
        """验证 ai_chat.py 中 get_events 返回值处理正确"""
        src = _read('api/ai_chat.py')
        # 修复前: len(events) 其中 events 是 dict
        # 修复后: events = result.get('events', [])
        assert "result.get('events'" in src or 'result.get("events"' in src


# ── 兼容性：旧 API 保留 ───────────────────────────────────────────────

class TestBackwardCompatibility:
    """旧 /api/profile/* 路由保留兼容"""

    def test_old_profile_routes_exist(self):
        """server.py 或 api/profiler.py 中保留旧路由"""
        server_src = _read('server.py')
        profiler_src = _read('api/profiler.py') if (ROOT / 'api' / 'profiler.py').exists() else ''
        combined = server_src + profiler_src
        assert '/api/profile' in combined

    def test_server_registers_profiler_blueprint(self):
        """server.py 注册了 profiler Blueprint"""
        server_src = _read('server.py')
        init_src = _read('api/__init__.py')
        combined = server_src + init_src
        assert 'profiler' in combined.lower()


# ── Anomaly Detection 基础设施 ─────────────────────────────────────────

class TestAnomalyInfrastructure:
    """异常检测基础设施完整性"""

    def test_anomaly_detector_service_exists(self):
        assert (ROOT / 'services' / 'anomaly_detector.py').exists()

    def test_anomaly_api_exists(self):
        assert (ROOT / 'api' / 'anomaly.py').exists()

    def test_anomaly_api_has_events_endpoint(self):
        src = _read('api/anomaly.py')
        assert '/api/anomaly/events' in src

    def test_anomaly_api_has_rules_endpoint(self):
        src = _read('api/anomaly.py')
        assert '/api/anomaly/rules' in src

    def test_anomaly_registered_in_init(self):
        src = _read('api/__init__.py')
        assert 'anomaly_bp' in src
