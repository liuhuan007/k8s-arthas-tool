import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER = (ROOT / 'server.py').read_text(encoding='utf-8')
POD_APIS = (ROOT / 'api' / 'pod_apis.py').read_text(encoding='utf-8')
APP_UI = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
MONITOR_COMPONENT = (ROOT / 'static' / 'js' / 'components' / 'monitor.js').read_text(encoding='utf-8')
TWO_STEP = (ROOT / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')
CONNECTION = (ROOT / 'backend' / 'core' / 'connection.py').read_text(encoding='utf-8')
ARTHAS_AGENT = (ROOT / 'backend' / 'core' / 'arthas_agent.py').read_text(encoding='utf-8')


def test_monitor_pod_route_registered_once_in_server_only():
    assert "@app.route('/api/monitor/pod'" in SERVER
    assert "@app.route('/api/monitor/pod'" not in POD_APIS


def test_main_monitor_process_renderer_supports_pod_diagnose_process_shape():
    assert 'snap.processes' in APP_UI
    assert 'p.cpu_percent' in APP_UI
    assert 'p.mem_percent' in APP_UI
    assert 'p.name' in APP_UI
    assert 'p.status' in APP_UI


def test_component_monitor_process_renderer_supports_pod_diagnose_process_shape():
    assert 'snap.processes' in MONITOR_COMPONENT
    assert 'p.cpu_percent' in MONITOR_COMPONENT
    assert 'p.mem_percent' in MONITOR_COMPONENT
    assert 'p.name' in MONITOR_COMPONENT
    assert 'p.status' in MONITOR_COMPONENT


def test_arthas_upgrade_reuse_returns_actionable_state_and_does_not_mischeck_mcp_port():
    assert '_http_reachable()' in ARTHAS_AGENT
    assert 'Arthas 已在运行，直接复用' in ARTHAS_AGENT
    assert 'mcp_available = arthas_conn.agent_mgr._check_mcp_available(arthas_conn.target.arthas_http_port)' in POD_APIS
    assert 'entry.get(\'mcp_available\', False)' in POD_APIS
    assert 'mcp_available = conn.agent_mgr._check_mcp_available(conn.target.arthas_http_port)' in SERVER
    assert 'is_reused' in POD_APIS
    assert 'reused' in TWO_STEP


def test_failed_port_forward_releases_allocated_port_for_retry():
    assert 'self._release_port(self.local_port)' in CONNECTION
    assert 'self.local_port = 0' in CONNECTION
