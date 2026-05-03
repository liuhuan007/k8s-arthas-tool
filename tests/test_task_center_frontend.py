import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
APP_UI = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
API_JS = (ROOT / 'static' / 'js' / 'core' / 'api.js').read_text(encoding='utf-8')


def test_task_center_create_button_uses_global_event_handler():
    assert 'onclick="createTaskDefinitionFromForm()"' in INDEX
    assert 'window.createTaskDefinitionFromForm = createTaskDefinitionFromForm;' in APP_UI


def test_task_center_has_inline_submit_button_inside_form_card():
    form_match = re.search(
        r'<section class="task-card task-form-card">(?P<body>.*?)</section>',
        INDEX,
        re.S,
    )
    assert form_match, 'task form card should exist'
    body = form_match.group('body')
    assert 'task-form-submit' in body
    assert 'onclick="createTaskDefinitionFromForm()"' in body


def test_task_center_create_form_uses_visual_sections():
    assert 'task-form-shell' in INDEX
    assert 'task-form-section' in INDEX
    assert 'task-form-section-title' in INDEX
    assert 'task-mode-option' in INDEX


def test_api_helpers_are_browser_globals_for_inline_handlers():
    for helper in ('safePost', 'safeGet', 'safePut', 'safeDelete'):
        assert f'window.{helper} = {helper};' in API_JS
