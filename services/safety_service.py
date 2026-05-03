#!/usr/bin/env python3
"""安全服务 — 路径校验、敏感信息脱敏、命令风险分级、文件哈希"""
import hashlib
import os
import re
from pathlib import Path


class SafetyService:
    """安全服务 — 提供静态方法用于安全校验与处理"""

    _SHELL_METACHARS = re.compile(r'[;|&$`\n\r]')

    _HIGH_RISK_COMMANDS = {
        'redefine', 'shutdown', 'stop', 'kill', 'rm', 'mv', 'dd'
    }
    _MEDIUM_RISK_COMMANDS = {
        'trace', 'watch', 'monitor', 'tt', 'heapdump', 'dump'
    }
    _LOW_RISK_COMMANDS = {
        'help', 'version', 'thread', 'dashboard', 'jvm',
        'sysprop', 'sysenv', 'vmoption', 'logger', 'mbean',
        'sc', 'sm', 'jad', 'mc', 'classloader', 'ognl'
    }

    @staticmethod
    def resolve_under_root(root: str, requested: str) -> str:
        """Resolve a requested path under a root directory, preventing path traversal attacks.

        Args:
            root: The root directory that must contain the resolved path.
            requested: The requested path (absolute or relative).

        Returns:
            The resolved absolute path.

        Raises:
            ValueError: If the path is invalid or escapes the root directory.
        """
        if '\x00' in requested:
            raise ValueError("Path contains null bytes")

        if '..' in requested:
            raise ValueError("Path contains directory traversal (..)")

        if SafetyService._SHELL_METACHARS.search(requested):
            raise ValueError("Path contains shell metacharacters")

        root_path = Path(root).resolve()
        requested_path = Path(requested)

        if requested_path.is_absolute():
            resolved = requested_path.resolve()
        else:
            resolved = (root_path / requested_path).resolve()

        try:
            resolved.relative_to(root_path)
        except ValueError:
            raise ValueError("Resolved path escapes root directory")

        return str(resolved)

    @staticmethod
    def mask_sensitive_output(output: str) -> str:
        """Mask sensitive information in command output.

        Args:
            output: Raw command output string.

        Returns:
            Masked output string.
        """
        # Passwords
        output = re.sub(
            r'password[:=]\s*\S+',
            'password: ***',
            output,
            flags=re.IGNORECASE
        )

        # Tokens
        output = re.sub(
            r'token[:=]\s*\S+',
            'token: ***',
            output,
            flags=re.IGNORECASE
        )

        # API keys
        output = re.sub(
            r'api[_-]?key[:=]\s*\S+',
            'api_key: ***',
            output,
            flags=re.IGNORECASE
        )

        # Private keys (PEM blocks)
        output = re.sub(
            r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
            '[PRIVATE_KEY_REDACTED]',
            output,
            flags=re.DOTALL | re.IGNORECASE
        )

        # IP addresses
        output = re.sub(
            r'\d+\.\d+\.\d+\.\d+',
            '***.***.***.***',
            output
        )

        return output

    @staticmethod
    def classify_arthas_command(command: str) -> dict:
        """Classify an Arthas command by risk level.

        Args:
            command: The Arthas command string.

        Returns:
            Dict with keys: risk_level, command, requires_confirmation.
        """
        base = command.strip().split()[0] if command.strip() else ''

        if base in SafetyService._HIGH_RISK_COMMANDS:
            return {
                "risk_level": "high",
                "command": base,
                "requires_confirmation": True
            }

        if base in SafetyService._MEDIUM_RISK_COMMANDS:
            return {
                "risk_level": "medium",
                "command": base,
                "requires_confirmation": False
            }

        if base in SafetyService._LOW_RISK_COMMANDS:
            return {
                "risk_level": "low",
                "command": base,
                "requires_confirmation": False
            }

        # Unknown commands default to high risk
        return {
            "risk_level": "high",
            "command": base,
            "requires_confirmation": True
        }

    @staticmethod
    def file_sha256(path: str) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            path: Path to the file.

        Returns:
            Hex digest string.
        """
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(65536)  # 64KB chunks
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
