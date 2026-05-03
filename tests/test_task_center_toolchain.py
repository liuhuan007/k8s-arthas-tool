import hashlib
import pathlib
import sys

sys.path.insert(0, r'e:/tmp/k8s-arthas-tool')

from api import task_center

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK_CENTER = (ROOT / 'api' / 'task_center.py').read_text(encoding='utf-8')


def test_seed_builtin_arthas_tool_package_source_exists():
    assert 'builtin-arthas-offline' in TASK_CENTER
    assert "tool_type" in TASK_CENTER
    assert "arthas" in TASK_CENTER
    assert "arthas-boot.jar" in TASK_CENTER
    assert "install_path" in TASK_CENTER


def test_tool_package_upload_and_distribute_routes_exist():
    assert "@task_bp.route('/tool-packages/upload'" in TASK_CENTER
    assert "@task_bp.route('/tool-packages/<int:package_id>/distribute'" in TASK_CENTER
    assert "@task_bp.route('/tool-packages/<int:package_id>/verify'" in TASK_CENTER


def test_validate_tool_install_path_rejects_unsafe_paths():
    invalid_paths = ['../arthas.jar', 'tmp/arthas.jar', '/etc/passwd', '/bin/arthas.jar', '/usr/bin/arthas.jar', '/tmp/a\nb.jar']
    for path in invalid_paths:
        try:
            task_center._validate_tool_install_path(path)
        except ValueError:
            continue
        raise AssertionError(f'{path} should be rejected')


def test_validate_tool_install_path_accepts_safe_paths():
    assert task_center._validate_tool_install_path('/tmp/arthas/arthas-boot.jar') == '/tmp/arthas/arthas-boot.jar'
    assert task_center._validate_tool_install_path('/app/arthas/arthas-boot.jar') == '/app/arthas/arthas-boot.jar'


def test_sha256_helper_returns_expected_digest(tmp_path):
    f = tmp_path / 'arthas-boot.jar'
    f.write_bytes(b'arthas-offline-test')
    assert task_center._sha256_file(f) == hashlib.sha256(b'arthas-offline-test').hexdigest()


def test_retransform_and_pod_file_server_templates_are_seeded():
    assert 'Arthas jad/retransform 热更新工作流' in TASK_CENTER
    assert 'Arthas 上传源码覆盖并 retransform' in TASK_CENTER
    assert 'Pod Python 文件下载服务' in TASK_CENTER
    assert 'jad --source-only' in TASK_CENTER
    assert 'retransform' in TASK_CENTER
    assert 'python3 -m http.server' in TASK_CENTER


def test_arthas_user_case_product_templates_are_seeded():
    expected = [
        'CPU 高负载一键诊断',
        'Trace 调用链耗时分析',
        'Watch 方法现场观测',
        'Controller 请求入口定位',
        'TraceId 上下文提取',
        'Spring 事务配置生效诊断',
        'Logger 动态日志级别调整',
        'Heapdump 内存快照工具',
        'VMOption 运行时参数查看',
        'ClassLoader 类冲突排查',
    ]
    for name in expected:
        assert name in TASK_CENTER
    for command in ('thread -n 5', 'trace ', 'watch ', 'stack ', 'logger', 'heapdump', 'vmoption', 'classloader'):
        assert command in TASK_CENTER


def test_user_case_capability_metadata_exists():
    assert '_USER_CASE_CAPABILITIES' in TASK_CENTER
    assert 'github_issue' in TASK_CENTER
    assert 'product_stage' in TASK_CENTER
    assert 'spectre' in TASK_CENTER


def test_upload_source_route_and_safe_java_source_validation_exist():
    assert "@task_bp.route('/arthas/source-upload'" in TASK_CENTER
    assert '_validate_java_source_filename' in TASK_CENTER
    assert task_center._validate_java_source_filename('Demo.java') == 'Demo.java'
    for name in ('../Demo.java', 'Demo.txt', 'A/B.java', ''):
        try:
            task_center._validate_java_source_filename(name)
        except ValueError:
            continue
        raise AssertionError(f'{name} should be rejected')
