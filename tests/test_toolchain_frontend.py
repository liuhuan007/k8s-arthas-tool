import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
APP_UI = (ROOT / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')


def test_toolchain_page_has_upload_and_package_list_ui():
    assert 'toolchain-page' in INDEX
    assert 'toolPackageFile' in INDEX
    assert 'toolPackageList' in INDEX
    assert 'uploadToolPackageFromForm()' in INDEX
    assert 'distributeToolPackage' in INDEX


def test_toolchain_frontend_exports_inline_handlers():
    for name in (
        'loadToolchainCenter',
        'uploadToolPackageFromForm',
        'distributeToolPackage',
        'verifyToolPackage',
        'deleteToolPackage',
    ):
        assert f'window.{name} = {name};' in APP_UI


def test_task_template_options_show_tool_package_name():
    assert 'tool_package_name' in APP_UI
    assert 'toolPackageName' in APP_UI


def test_toolchain_upload_button_targets_real_file_input_and_uses_safe_multipart_helper():
    assert 'document.getElementById(\'toolPackageFile\')?.click()' in INDEX
    assert 'safeUploadToolPackage' in APP_UI
    assert 'credentials: \'include\'' in APP_UI
    assert 'if (r.status === 401)' in APP_UI


def test_toolchain_inputs_use_dark_upload_styles():
    assert 'class="inp toolchain-file-input" type="file"' in INDEX
    assert '.inp,' in (ROOT / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert '.toolchain-file-input' in (ROOT / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert 'color:var(--tx)' in (ROOT / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')


def test_toolchain_exposes_source_upload_handlers():
    for name in ('uploadArthasSourceFromForm', 'renderToolQuickPlans'):
        assert f'window.{name} = {name};' in APP_UI
    assert 'arthasSourceFile' in INDEX
    assert 'toolQuickPlanList' in INDEX


def test_user_case_capability_frontend_panel_exists():
    assert 'arthasUserCaseList' in INDEX
    assert 'renderArthasUserCaseCapabilities' in APP_UI
    assert 'CPU 高负载一键诊断' in APP_UI
    assert 'Spectre 热替换工作台' in APP_UI
    assert 'window.renderArthasUserCaseCapabilities = renderArthasUserCaseCapabilities;' in APP_UI


def test_toolchain_ops_tech_theme_tokens_exist():
    css = (ROOT / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert '--ops-cyan' in css
    assert '--ops-green' in css
    assert '--ops-grid' in css
    assert 'opsScan' in css
    assert '.toolchain-page::before' in css
    assert '.toolchain-package-item::before' in css
