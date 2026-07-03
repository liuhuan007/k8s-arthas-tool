from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_skill_management_search_inputs_disable_browser_autofill():
    html = read_text("static/skill-management.html")

    for input_id in ["searchInput", "browseSearch"]:
        start = html.index(f'id="{input_id}"')
        snippet = html[max(0, start - 160):start + 500]
        assert 'type="search"' in snippet
        assert 'name=""' in snippet
        assert 'autocomplete="off"' in snippet
        assert 'autocorrect="off"' in snippet
        assert 'autocapitalize="off"' in snippet
        assert 'spellcheck="false"' in snippet
        assert 'data-lpignore="true"' in snippet
        assert 'data-1p-ignore="true"' in snippet
        assert 'data-bwignore="true"' in snippet
        assert 'data-form-type="other"' in snippet

    assert "function hardenSkillSearchInputs()" in html
    assert "input.readOnly = true" in html
    assert "value.includes('@')" in html


def test_toolbox_batch_search_inputs_use_connection_pool_hardening():
    js = read_text("static/js/components/toolbox.js")

    for placeholder in ["搜索工具", "搜索 Pod", "搜索 Node", "搜索 Namespace"]:
        start = js.index(f'placeholder="{placeholder}..."')
        snippet = js[start - 120:start + 500]
        assert 'type="search"' in snippet
        assert 'name=""' in snippet
        assert 'autocomplete="off"' in snippet
        assert 'data-lpignore="true"' in snippet
        assert 'data-1p-ignore="true"' in snippet
        assert 'data-bwignore="true"' in snippet
        assert 'data-form-type="other"' in snippet

    assert "ConnectionPool.hardenSearchInput(input)" in js
