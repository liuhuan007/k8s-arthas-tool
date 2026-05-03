#!/usr/bin/env python3
"""下载安全合同测试 — 验证 SafetyService 路径安全、脱敏、风险分级、哈希。"""
import hashlib
import os
import tempfile

import pytest
from pathlib import Path

from backend.config import Config  # noqa: F401 — must import first to avoid circular imports
from services.safety_service import SafetyService


# ═══════════════════════════════════════════════════════════════════════════
# 测试：路径遍历防护
# ═══════════════════════════════════════════════════════════════════════════

class TestPathTraversal:
    @pytest.fixture
    def temp_root(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir

    def test_rejects_double_dot_traversal(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, '../../etc/passwd')
        assert 'traversal' in str(exc_info.value).lower()

    def test_rejects_absolute_traversal(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, '/tmp/../etc/passwd')
        assert 'traversal' in str(exc_info.value).lower()

    def test_rejects_null_bytes(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file\x00.txt')
        assert 'null' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_semicolon(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file;rm -rf /')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_pipe(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file|cat')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_ampersand(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file&&echo')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_dollar(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file$HOME')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_backtick(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file`whoami`')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_newline(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file\necho')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_shell_metacharacters_carriage_return(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, 'file\recho')
        assert 'shell' in str(exc_info.value).lower()

    def test_rejects_path_escaping_root(self, temp_root):
        with pytest.raises(ValueError) as exc_info:
            SafetyService.resolve_under_root(temp_root, os.path.join(temp_root, '..', 'etc', 'passwd'))
        assert 'escapes' in str(exc_info.value).lower() or 'traversal' in str(exc_info.value).lower()

    def test_resolves_valid_relative_path(self, temp_root):
        resolved_root = str(Path(temp_root).resolve())
        result = SafetyService.resolve_under_root(temp_root, 'file.txt')
        assert result == os.path.join(resolved_root, 'file.txt')

    def test_resolves_nested_valid_path(self, temp_root):
        resolved_root = str(Path(temp_root).resolve())
        subdir = os.path.join(temp_root, 'subdir')
        os.makedirs(subdir)
        result = SafetyService.resolve_under_root(temp_root, 'subdir/file.txt')
        assert result == os.path.join(resolved_root, 'subdir', 'file.txt')

    def test_resolves_valid_absolute_path_under_root(self, temp_root):
        resolved_root = str(Path(temp_root).resolve())
        result = SafetyService.resolve_under_root(temp_root, os.path.join(temp_root, 'file.txt'))
        assert result == os.path.join(resolved_root, 'file.txt')


# ═══════════════════════════════════════════════════════════════════════════
# 测试：敏感信息脱敏
# ═══════════════════════════════════════════════════════════════════════════

class TestMaskSensitiveOutput:
    def test_masks_password(self):
        raw = 'password: supersecret123'
        masked = SafetyService.mask_sensitive_output(raw)
        assert 'password: ***' in masked
        assert 'supersecret123' not in masked

    def test_masks_password_with_equals(self):
        raw = 'password=supersecret123'
        masked = SafetyService.mask_sensitive_output(raw)
        assert 'password: ***' in masked
        assert 'supersecret123' not in masked

    def test_masks_token(self):
        raw = 'token: abcdef123456'
        masked = SafetyService.mask_sensitive_output(raw)
        assert 'token: ***' in masked
        assert 'abcdef123456' not in masked

    def test_masks_api_key(self):
        raw = 'api_key: sk-1234567890'
        masked = SafetyService.mask_sensitive_output(raw)
        assert 'api_key: ***' in masked
        assert 'sk-1234567890' not in masked

    def test_masks_apikey_variant(self):
        raw = 'apikey=sk-1234567890'
        masked = SafetyService.mask_sensitive_output(raw)
        assert 'api_key: ***' in masked
        assert 'sk-1234567890' not in masked

    def test_masks_api_key_hyphen(self):
        raw = 'api-key: sk-1234567890'
        masked = SafetyService.mask_sensitive_output(raw)
        assert 'api_key: ***' in masked
        assert 'sk-1234567890' not in masked

    def test_masks_private_key_pem(self):
        raw = '-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n-----END PRIVATE KEY-----'
        masked = SafetyService.mask_sensitive_output(raw)
        assert '[PRIVATE_KEY_REDACTED]' in masked
        assert 'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...' not in masked

    def test_masks_ip_address(self):
        raw = 'Server running on 192.168.1.1:8080'
        masked = SafetyService.mask_sensitive_output(raw)
        assert '***.***.***.***:8080' in masked
        assert '192.168.1.1' not in masked

    def test_masks_multiple_ips(self):
        raw = 'IPs: 10.0.0.1 and 172.16.0.1'
        masked = SafetyService.mask_sensitive_output(raw)
        assert masked.count('***.***.***.***') == 2


# ═══════════════════════════════════════════════════════════════════════════
# 测试：Arthas 命令风险分级
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyArthasCommand:
    def test_high_risk_redefine(self):
        result = SafetyService.classify_arthas_command('redefine /tmp/Test.class')
        assert result['risk_level'] == 'high'
        assert result['command'] == 'redefine'
        assert result['requires_confirmation'] is True

    def test_high_risk_shutdown(self):
        result = SafetyService.classify_arthas_command('shutdown')
        assert result['risk_level'] == 'high'
        assert result['requires_confirmation'] is True

    def test_high_risk_stop(self):
        result = SafetyService.classify_arthas_command('stop')
        assert result['risk_level'] == 'high'
        assert result['requires_confirmation'] is True

    def test_high_risk_kill(self):
        result = SafetyService.classify_arthas_command('kill 12345')
        assert result['risk_level'] == 'high'
        assert result['requires_confirmation'] is True

    def test_medium_risk_trace(self):
        result = SafetyService.classify_arthas_command('trace com.example.Service hello')
        assert result['risk_level'] == 'medium'
        assert result['command'] == 'trace'
        assert result['requires_confirmation'] is False

    def test_medium_risk_watch(self):
        result = SafetyService.classify_arthas_command('watch com.example.Service hello params')
        assert result['risk_level'] == 'medium'
        assert result['requires_confirmation'] is False

    def test_medium_risk_heapdump(self):
        result = SafetyService.classify_arthas_command('heapdump')
        assert result['risk_level'] == 'medium'
        assert result['requires_confirmation'] is False

    def test_low_risk_help(self):
        result = SafetyService.classify_arthas_command('help')
        assert result['risk_level'] == 'low'
        assert result['command'] == 'help'
        assert result['requires_confirmation'] is False

    def test_low_risk_dashboard(self):
        result = SafetyService.classify_arthas_command('dashboard')
        assert result['risk_level'] == 'low'
        assert result['requires_confirmation'] is False

    def test_unknown_command_defaults_high(self):
        result = SafetyService.classify_arthas_command('unknown_cmd')
        assert result['risk_level'] == 'high'
        assert result['command'] == 'unknown_cmd'
        assert result['requires_confirmation'] is True


# ═══════════════════════════════════════════════════════════════════════════
# 测试：SHA256 文件哈希
# ═══════════════════════════════════════════════════════════════════════════

class TestFileSha256:
    def test_sha256_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'')
            path = f.name
        try:
            expected = hashlib.sha256(b'').hexdigest()
            assert SafetyService.file_sha256(path) == expected
        finally:
            os.unlink(path)

    def test_sha256_known_content(self):
        content = b'Hello, World!'
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            path = f.name
        try:
            expected = hashlib.sha256(content).hexdigest()
            assert SafetyService.file_sha256(path) == expected
        finally:
            os.unlink(path)

    def test_sha256_large_file(self):
        content = b'A' * (65536 * 3 + 12345)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            path = f.name
        try:
            expected = hashlib.sha256(content).hexdigest()
            assert SafetyService.file_sha256(path) == expected
        finally:
            os.unlink(path)
