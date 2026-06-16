#!/usr/bin/env python3
"""CLI 统一 API 路由"""
import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required

from backend.cli.command_registry import CommandRegistry, ALL_COMMANDS
from backend.cli.adapter import StructuredResult
from backend.cli.kubectl_adapter import KubectlAdapter
from backend.cli.arthas_adapter import ArthasAdapter

log = logging.getLogger(__name__)

cli_bp = Blueprint('cli', __name__, url_prefix='/api/cli')


def _make_adapter(cli: str):
    if cli == 'arthas':
        return ArthasAdapter()
    return KubectlAdapter()


@cli_bp.route('/commands', methods=['GET'])
@login_required
def list_commands():
    cli = request.args.get('cli', '').strip()
    if cli:
        if cli not in ALL_COMMANDS:
            return jsonify({'error': f'Unknown CLI: {cli}', 'valid': list(ALL_COMMANDS.keys())}), 400
        commands = CommandRegistry.get_commands(cli)
        return jsonify({'ok': True, 'cli': cli, 'commands': commands})
    result = {}
    for c in ALL_COMMANDS:
        result[c] = CommandRegistry.get_commands(c)
    return jsonify({'ok': True, 'commands': result})


@cli_bp.route('/execute', methods=['POST'])
@login_required
def execute():
    data = request.json or {}
    cli = data.get('cli', 'kubectl').strip()
    command = data.get('command', '').strip()
    params = data.get('params', {})

    if not command:
        return jsonify({'ok': False, 'error': 'command is required'}), 400

    adapter = _make_adapter(cli)
    result = adapter.execute(command, params)

    response = {
        'ok': result.ok,
        'command': result.command,
        'data': result.data,
        'health': result.health,
        'error': result.error,
        'error_detail': result.error_detail,
    }
    status = 200 if result.ok else 400
    return jsonify(response), status


@cli_bp.route('/health-check', methods=['POST'])
@login_required
def health_check():
    data = request.json or {}
    cli = data.get('cli', 'kubectl').strip()
    resource = data.get('resource', '')
    params = data.get('params', {})

    adapter = _make_adapter(cli)
    health = adapter.health_check(resource, params)
    return jsonify({'ok': True, 'health': health})


@cli_bp.route('/dry-run', methods=['POST'])
@login_required
def dry_run():
    data = request.json or {}
    cli = data.get('cli', 'kubectl').strip()
    command = data.get('command', '').strip()
    params = data.get('params', {})

    if not command:
        return jsonify({'ok': False, 'error': 'command is required'}), 400

    adapter = _make_adapter(cli)
    preview = adapter.dry_run(command, params)
    return jsonify({'ok': True, 'preview': preview})
