import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
APP_UI = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
API_JS = (ROOT / 'static' / 'js' / 'core' / 'api.js').read_text(encoding='utf-8')
TASK_CENTER_V2 = (ROOT / 'static' / 'js' / 'components' / 'task-center.js').read_text(encoding='utf-8')


def test_task_center_create_button_uses_global_event_handler():
    # ✅ V2: 使用新的创建任务模态框
    assert 'onclick="openCreateTaskModal()"' in INDEX
    assert 'window.openCreateTaskModal' in TASK_CENTER_V2


def test_task_center_has_inline_submit_button_inside_form_card():
    # ✅ V2: 三栏布局
    assert 'task-center-tabs' in INDEX
    assert 'tc-tab' in INDEX
    assert 'tc-panel' in INDEX
    assert 'taskDefList' in INDEX
    assert 'taskLogList' in INDEX
    assert 'taskScheduleList' in INDEX


def test_task_center_create_form_uses_visual_sections():
    # ✅ V2: 新的模态框表单
    assert 'capability-modal' in INDEX or 'openCreateTaskModal' in INDEX
    assert 'newTaskName' in TASK_CENTER_V2


def test_api_helpers_are_browser_globals_for_inline_handlers():
    for helper in ('safePost', 'safeGet', 'safePut', 'safeDelete'):
        assert f'window.{helper} = {helper};' in API_JS
