from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_diag_quick_tools_render_before_scenarios():
    html = read_text("static/index.html")
    panel = html[html.index('id="panel-diag"'):html.index('id="panel-diagnosis-cap"')]

    assert panel.index(">快速工具<") < panel.index(">诊断场景<")


def test_diag_cards_have_inline_execute_actions():
    html = read_text("static/index.html")
    js = read_text("static/js/components/diagnose.js")
    css = read_text("static/css/app.css")

    assert "window.diagRunTool" in js
    assert "window.diagRunScene" in js
    assert ".diag-inline-action" in css

    for tool in ["sys_cpu", "sys_mem", "sys_disk", "sys_net", "sys_proc", "jvm", "threads", "trace"]:
        assert f"diagRunTool(event,'{tool}')" in html

    for scene in ["system", "general", "method_slow", "thread_block", "oom"]:
        assert f"diagRunScene(event,'{scene}')" in html


def test_diag_jvm_quick_tool_uses_jvm_overview():
    html = read_text("static/index.html")
    js = read_text("static/js/components/diagnose.js")
    api = read_text("api/performance_diagnose.py")

    assert "diagQuickTool('jvm')" in html
    assert 'id="diagBtnJvm"' in html
    assert "JVM 概览" in html
    assert "jvm: 'JVM 概览'" in js
    assert "ArthasCommandExecutor.execute(conn, \"jvm\"" in api


def test_newapi_provider_is_exposed_in_frontend_and_backend():
    html = read_text("static/index.html")
    js = read_text("static/js/ai-chat.js")
    ai_api = read_text("api/ai_chat.py")

    assert '<option value="newapi">' in html
    assert "newapi:" in js
    assert "NewAPI / OpenAI 兼容中转站" in js
    assert '"id": "newapi"' in ai_api
    assert "http://127.0.0.1:3000/v1" in ai_api


def test_newapi_works_with_openai_compatible_agent_paths():
    factory = read_text("services/agent_factory.py")
    sdk_config = read_text("services/agent_sdk_config.py")
    llm_client = read_text("backend/agent/llm_client.py")

    assert '"newapi"' in factory
    assert '"openai-compatible"' in factory
    assert '"newapi"' in sdk_config
    assert '"openai-compatible"' in sdk_config
    assert '"newapi": "http://127.0.0.1:3000/v1"' in llm_client
    assert '"openai-compatible": "http://127.0.0.1:3000/v1"' in llm_client
