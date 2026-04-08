#!/usr/bin/env python3
"""
AI 对话蓝图 — 方案 A：平台内配置大模型

架构：
  用户在界面内与 AI 对话
       │
       ▼
  Flask 后端 /api/ai/* (配置管理 + 对话代理)
       │  Function Calling
       ▼
  大模型 API (OpenAI 兼容：DeepSeek / 通义千问 / OpenAI / 月之暗面 ...)
       │  tool_calls
       ▼
  后端执行 Arthas 命令 / 查询 Pod 状态 / ...
       │
       ▼
  返回结果给 AI → AI 继续分析

核心功能：
  1. AI 配置管理 — 保存 API Key / Base URL / 模型名称（支持 Ollama 本地模型）
  2. 对话代理 — 转发用户消息到大模型，支持流式输出
  3. Function Calling — AI 可调用 Arthas 命令、查看 Pod 状态等
"""
import json
import logging
import secrets
import urllib.request
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user

from models.db import db

log = logging.getLogger(__name__)

ai_bp = Blueprint('ai_chat', __name__)

# ═══════════════════════════════════════════════════════════════════════════════
# AI 配置 API
# ═══════════════════════════════════════════════════════════════════════════════

@ai_bp.route('/api/ai/config', methods=['GET'])
@login_required
def get_ai_config():
    """获取当前用户的 AI 配置（API Key 脱敏）"""
    row = db.fetch_one('SELECT * FROM ai_config WHERE user_id = ?', (current_user.id,))
    if not row:
        return jsonify({"config": None})

    config = dict(row)
    # 脱敏 API Key
    if config.get('api_key'):
        k = config['api_key']
        config['api_key_masked'] = k[:6] + '***' + k[-4:] if len(k) > 10 else '***'
    else:
        config['api_key_masked'] = ''
    del config['api_key']  # 不返回原文

    return jsonify({"config": config})


@ai_bp.route('/api/ai/config', methods=['POST'])
@login_required
def save_ai_config():
    """保存/更新 AI 配置"""
    d = request.json or {}
    api_key = d.get('api_key', '').strip()
    base_url = d.get('base_url', '').strip()
    model = d.get('model', '').strip()
    system_prompt = d.get('system_prompt', '').strip()
    provider = d.get('provider', '').strip()  # openai / ollama

    if not base_url:
        return jsonify({"error": "API Base URL 不能为空"}), 400
    if not model:
        return jsonify({"error": "模型名称不能为空"}), 400

    # 确保 base_url 不以 / 结尾
    base_url = base_url.rstrip('/')

    existing = db.fetch_one('SELECT * FROM ai_config WHERE user_id = ?', (current_user.id,))

    # Ollama 本地模型不需要 API Key
    is_ollama = provider == 'ollama' or 'ollama' in base_url.lower()

    # 如果没有传 api_key 且已有配置，保留原来的 key
    if not api_key and existing and existing.get('api_key'):
        api_key = existing['api_key']

    # 非 Ollama 模式必须提供 API Key
    if not api_key and not is_ollama:
        return jsonify({"error": "API Key 不能为空（Ollama 本地模型可留空）"}), 400

    data = {
        'api_key': api_key or '',
        'base_url': base_url,
        'model': model,
        'system_prompt': system_prompt,
        'provider': provider or ('ollama' if is_ollama else 'openai'),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    if existing:
        db.update('ai_config', data, 'user_id = ?', (current_user.id,))
    else:
        data['user_id'] = current_user.id
        data['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.insert('ai_config', data)

    # 审计
    from services.audit_service import AuditService
    AuditService._log_raw(current_user.id, 'ai_config_saved', 'ai_config',
                          f'ai_config:user_{current_user.id}', f'更新 AI 配置: model={model}, provider={provider}, base_url={base_url}')

    return jsonify({"ok": True})


@ai_bp.route('/api/ai/config/test', methods=['POST'])
@login_required
def test_ai_config():
    """测试 AI 配置是否可用（发送一个简单请求验证连通性）"""
    d = request.json or {}
    api_key = d.get('api_key', '').strip()
    base_url = d.get('base_url', '').strip().rstrip('/')
    model = d.get('model', '').strip()

    if not base_url or not model:
        return jsonify({"error": "参数不完整"}), 400

    is_ollama = 'ollama' in base_url.lower() or 'localhost:11434' in base_url

    try:
        url = f"{base_url}/chat/completions"
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Hi, reply with just 'OK'."}],
            "max_tokens": 10,
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        if api_key:
            req.add_header('Authorization', f'Bearer {api_key}')

        with urllib.request.urlopen(req, timeout=30 if is_ollama else 15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            return jsonify({"ok": True, "response": content})

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace') if e.fp else ''
        return jsonify({"ok": False, "error": f"HTTP {e.code}: {body[:200]}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@ai_bp.route('/api/ai/providers', methods=['GET'])
@login_required
def get_ai_providers():
    """获取预设模型提供商列表"""
    providers = [
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "needs_key": True,
            "icon": "🧠",
            "desc": "DeepSeek-V3.2，性价比高，中文能力强，推荐 deepseek-chat",
        },
        {
            "id": "qwen",
            "name": "通义千问",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen3-max", "qwen3.6-plus", "qwen3.5-flash", "qwen-plus", "qwen-turbo", "qwen-long", "qwq-plus"],
            "needs_key": True,
            "icon": "☁️",
            "desc": "阿里云大模型，Qwen3系列，qwen3-max最强，qwen3.6-plus均衡推荐",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "o3-mini", "o1-mini", "gpt-4-turbo"],
            "needs_key": True,
            "icon": "🌐",
            "desc": "GPT-4o 效果最佳，o3-mini/o1-mini 推理模型，需海外网络",
        },
        {
            "id": "moonshot",
            "name": "月之暗面 (Kimi)",
            "base_url": "https://api.moonshot.cn/v1",
            "models": ["kimi-k2.5", "kimi-k2-thinking", "moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"],
            "needs_key": True,
            "icon": "🌙",
            "desc": "Kimi K2.5 最新旗舰，超强编码和工具调用，超长上下文",
        },
        {
            "id": "zhipu",
            "name": "智谱 AI (GLM)",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "models": ["glm-5", "glm-4.7", "glm-4.6", "glm-4.5", "glm-4.5-air", "glm-4-plus", "glm-4-flash", "glm-4-long"],
            "needs_key": True,
            "icon": "🔮",
            "desc": "GLM-5 最新旗舰推理模型，glm-4.5-air 性价比最高，支持 Function Calling",
        },
        {
            "id": "ollama",
            "name": "Ollama (本地)",
            "base_url": "http://localhost:11434/v1",
            "models": ["qwen2.5:7b", "llama3.1:8b", "deepseek-coder-v2:16b", "codestral:22b"],
            "needs_key": False,
            "icon": "🏠",
            "desc": "本地运行，无需 API Key，需安装 Ollama",
        },
    ]
    return jsonify({"providers": providers})


@ai_bp.route('/api/ai/ollama/models', methods=['GET'])
@login_required
def list_ollama_models():
    """获取本地 Ollama 已安装的模型列表"""
    base_url = request.args.get('base_url', 'http://localhost:11434').rstrip('/')

    try:
        url = f"{base_url}/api/tags"
        req = urllib.request.Request(url, method='GET')
        req.add_header('Accept', 'application/json')

        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            models = []
            for m in result.get('models', []):
                models.append({
                    'name': m.get('name', ''),
                    'size': m.get('size', 0),
                    'modified_at': m.get('modified_at', ''),
                })
            return jsonify({"ok": True, "models": models})

    except urllib.error.URLError as e:
        return jsonify({"ok": False, "error": f"无法连接 Ollama 服务 ({base_url})，请确认 Ollama 已启动"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ═══════════════════════════════════════════════════════════════════════════════
# Arthas 工具定义（供 Function Calling 使用）
# ═══════════════════════════════════════════════════════════════════════════════

ARTHAS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_arthas_command",
            "description": "在当前连接的 Pod 内执行 Arthas 诊断命令。常用命令: thread(线程分析), dashboard(实时面板), jad(反编译类), watch(方法观测), trace(调用链耗时), stack(调用栈), logger(日志配置), heapdump(堆转储), profiler(性能采样), sc(搜索类), sm(搜索方法), vmtool(对象查询)",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Arthas 命令，如 'thread -n 3', 'trace com.example.Service method', 'jad com.example.Service'"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod_status",
            "description": "获取当前 Pod 的运行状态信息（CPU、内存、进程列表等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "detail": {
                        "type": "string",
                        "enum": ["basic", "processes", "network"],
                        "description": "信息类型: basic=基本状态, processes=进程列表, network=网络信息"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_connection",
            "description": "检查当前 Arthas 连接状态，确认连接是否可用",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """你是一个 Java 应用性能诊断专家，帮助用户通过 Alibaba Arthas 诊断 Kubernetes Pod 中的 Java 应用问题。

你的工作流程：
1. 先了解用户遇到的问题
2. 使用 check_connection 确认 Arthas 连接状态
3. 根据问题类型选择合适的 Arthas 命令进行诊断
4. 分析命令输出，给出诊断结论和建议

常见诊断场景及推荐命令：
- CPU 飙高: `thread -n 3` 查看 CPU 占用最高的线程
- 内存泄漏: `heapdump` 导出堆转储，`vmtool` 查询对象
- 接口慢: `trace 类名 方法名` 追踪调用链耗时
- 方法异常: `watch 类名 方法名 '{params,throwExp}' -e -x 2` 观测异常
- 类冲突: `sc -d 类名` 查看类加载信息, `jad 类名` 反编译
- 线程死锁: `thread -b` 查找死锁
- GC 问题: `dashboard` 查看 GC 统计，`profiler start --event alloc` 分析内存分配

注意事项：
- 执行危险操作（heapdump、profiler）前需提醒用户
- 命令输出可能很长，重点提取关键信息
- 如遇连接断开，提醒用户重新连接
- 使用中文回复"""


# ═══════════════════════════════════════════════════════════════════════════════
# 对话 API（流式）
# ═══════════════════════════════════════════════════════════════════════════════

@ai_bp.route('/api/ai/chat', methods=['POST'])
@login_required
def ai_chat():
    """AI 对话（支持流式输出 + Function Calling）"""
    d = request.json or {}
    messages = d.get('messages', [])
    connection_id = d.get('connection_id', '')
    stream = d.get('stream', True)

    if not messages:
        return jsonify({"error": "消息不能为空"}), 400

    # 获取 AI 配置
    config = db.fetch_one('SELECT * FROM ai_config WHERE user_id = ?', (current_user.id,))
    if not config:
        return jsonify({"error": "请先配置 AI 模型（点击设置图标）"}), 400

    # Ollama 本地模型无需 API Key
    is_ollama = config.get('provider') == 'ollama' or 'ollama' in (config.get('base_url') or '').lower() or 'localhost:11434' in (config.get('base_url') or '')
    if not config.get('api_key') and not is_ollama:
        return jsonify({"error": "请先配置 AI 模型 API Key（点击设置图标）"}), 400

    # 构建上下文：添加连接信息
    conn_info = _get_connection_info(connection_id)
    system_msg = config.get('system_prompt') or DEFAULT_SYSTEM_PROMPT
    if conn_info:
        system_msg += f"\n\n当前诊断环境:\n{conn_info}"

    # 插入系统提示词
    full_messages = [{"role": "system", "content": system_msg}] + messages

    # 调用大模型
    if stream:
        return _stream_chat(config, full_messages, connection_id)
    else:
        return _sync_chat(config, full_messages, connection_id)


@ai_bp.route('/api/ai/chat/history', methods=['GET'])
@login_required
def get_chat_history():
    """获取当前用户的对话历史"""
    rows = db.fetch_all(
        'SELECT * FROM ai_chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 100',
        (current_user.id,)
    )
    return jsonify({"messages": rows or []})


@ai_bp.route('/api/ai/chat/history', methods=['DELETE'])
@login_required
def clear_chat_history():
    """清空对话历史"""
    db.delete('ai_chat_history', 'user_id = ?', (current_user.id,))
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════════
# 核心对话逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def _get_connection_info(connection_id: str) -> str:
    """获取当前连接信息，用于 AI 上下文"""
    if not connection_id:
        # 尝试使用当前用户的活跃连接（优先最近的）
        from server import _connections, _connections_lock
        with _connections_lock:
            alive_conns = []
            for cid, entry in _connections.items():
                if entry.get('user_id') == current_user.id:
                    conn = entry.get('conn')
                    if conn and conn.is_alive():
                        alive_conns.append((cid, conn))
            if alive_conns:
                connection_id = alive_conns[-1][0]

    if not connection_id:
        return "未连接到任何 Pod，请先在左侧面板连接目标 Pod。"

    from server import _connections, _connections_lock
    with _connections_lock:
        entry = _connections.get(connection_id)
        if not entry:
            return f"连接 {connection_id} 不存在。"

    conn = entry.get('conn')
    if not conn:
        return f"连接 {connection_id} 无效。"

    alive = conn.is_alive()
    mcp_status = entry.get('mcp_available', False)
    info = f"- 集群: {conn.target.cluster_name}\n"
    info += f"- 命名空间: {conn.target.namespace}\n"
    info += f"- Pod: {conn.target.pod_name}\n"
    if conn.target.container:
        info += f"- 容器: {conn.target.container}\n"
    info += f"- Java PID: {conn.java_pid or '未知'}\n"
    info += f"- Arthas HTTP 端口: {conn.local_port or '未建立'}\n"
    info += f"- 连接状态: {'活跃' if alive else '已断开'}\n"
    info += f"- MCP 端点: {'可用 (Arthas 4.1.8+)' if mcp_status else '不可用 (需 Arthas 4.1.8+)'}"

    return info


def _execute_tool(name: str, arguments: dict, connection_id: str) -> str:
    """执行 AI 调用的工具"""
    try:
        if name == 'execute_arthas_command':
            return _exec_arthas(arguments.get('command', ''), connection_id)
        elif name == 'get_pod_status':
            return _get_pod_status(arguments.get('detail', 'basic'), connection_id)
        elif name == 'check_connection':
            return _check_connection_status(connection_id)
        else:
            return json.dumps({"error": f"未知工具: {name}"})
    except Exception as e:
        log.error("Tool execution error: %s - %s", name, e, exc_info=True)
        return json.dumps({"error": str(e)})


def _exec_arthas(command: str, connection_id: str) -> str:
    """执行 Arthas 命令"""
    conn = _get_alive_connection(connection_id)
    if not conn:
        return json.dumps({"error": "Arthas 连接不可用，请在界面重新连接"})

    try:
        result = conn.http_client.exec_once(command, timeout_ms=60000)

        # 审计
        from services.audit_service import AuditService
        AuditService._log_raw(current_user.id, 'ai_arthas_exec', 'arthas_command',
                              connection_id or 'unknown', f'AI 执行 Arthas 命令: {command}')

        # 提取关键输出
        state = result.get('state', '')
        body = result.get('body', [])

        if isinstance(body, list):
            # body 可能是行列表，拼接输出
            output = '\n'.join(str(line) for line in body)
        else:
            output = str(body)

        # 截断过长输出
        if len(output) > 8000:
            output = output[:8000] + '\n... (输出已截断，共 {} 字符)'.format(len(output))

        return json.dumps({
            "state": state,
            "output": output,
            "command": command
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"执行失败: {str(e)}"})


def _get_pod_status(detail: str, connection_id: str) -> str:
    """获取 Pod 状态信息"""
    conn = _get_alive_connection(connection_id)
    if not conn:
        return json.dumps({"error": "连接不可用"})

    target = conn.target
    try:
        if detail == 'processes':
            rc, out, err = conn.agent_mgr._exec('ps aux --sort=-%cpu | head -20', timeout=10)
            return json.dumps({"processes": out[:3000] if rc == 0 else err}, ensure_ascii=False)
        elif detail == 'network':
            rc, out, err = conn.agent_mgr._exec('cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | wc -l; ss -tlnp 2>/dev/null | head -20', timeout=10)
            return json.dumps({"network": out[:3000] if rc == 0 else err}, ensure_ascii=False)
        else:
            # basic
            rc, out, err = conn.agent_mgr._exec(
                f'echo "=== Pod Status ==="; '
                f'cat /proc/1/status 2>/dev/null | grep -E "^(Name|State|VmRSS|Threads)"; '
                f'echo "=== CPU ==="; '
                f'top -bn1 | head -5; '
                f'echo "=== Memory ==="; '
                f'free -h 2>/dev/null || cat /proc/meminfo | head -5',
                timeout=10
            )
            return json.dumps({"status": out[:3000] if rc == 0 else err}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _check_connection_status(connection_id: str) -> str:
    """检查 Arthas 连接状态"""
    conn = _get_alive_connection(connection_id)
    if not conn:
        return json.dumps({"connected": False, "message": "连接不可用，请重新连接"})

    try:
        ok = conn.http_client.ping(retries=1, delay=0)
        return json.dumps({
            "connected": ok,
            "pod": conn.target.pod_name,
            "namespace": conn.target.namespace,
            "java_pid": conn.java_pid,
            "local_port": conn.local_port,
        })
    except Exception:
        return json.dumps({"connected": False, "message": "连接已断开"})


def _get_alive_connection(connection_id: str):
    """获取活跃的 Arthas 连接"""
    from server import _connections, _connections_lock

    # 如果没有指定 connection_id，尝试找当前用户的活跃连接
    if not connection_id:
        with _connections_lock:
            # 优先找第一个活跃连接（按最近连接时间排序，最新的在前）
            # Python 3.7+ dict 保持插入顺序，最新的连接在后面
            alive_conns = []
            for cid, entry in _connections.items():
                if entry.get('user_id') == current_user.id:
                    conn = entry.get('conn')
                    if conn and conn.is_alive():
                        alive_conns.append((cid, conn))
            if alive_conns:
                # 返回最后一个（最近连接的）
                return alive_conns[-1][1]
        return None

    with _connections_lock:
        entry = _connections.get(connection_id)
        if entry and entry.get('user_id') == current_user.id:
            conn = entry.get('conn')
            if conn and conn.is_alive():
                return conn
    return None


def _call_llm(config, messages, tools=None, stream=False):
    """调用大模型 API（OpenAI 兼容接口）"""
    base_url = config['base_url'].rstrip('/')
    url = f"{base_url}/chat/completions"

    payload = {
        "model": config['model'],
        "messages": messages,
        "stream": stream,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    if config.get('api_key'):
        req.add_header('Authorization', f"Bearer {config['api_key']}")

    return req, url


def _sync_chat(config, messages, connection_id):
    """非流式对话"""
    max_iterations = 5  # 最多 5 轮 tool calling
    current_messages = list(messages)

    for _ in range(max_iterations):
        req, url = _call_llm(config, current_messages, tools=ARTHAS_TOOLS, stream=False)

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return jsonify({"error": f"模型调用失败: {str(e)}"}), 500

        choice = result.get('choices', [{}])[0]
        assistant_msg = choice.get('message', {})
        finish_reason = choice.get('finish_reason', '')

        current_messages.append(assistant_msg)

        # 如果没有 tool_calls，直接返回
        if finish_reason != 'tool_calls' or not assistant_msg.get('tool_calls'):
            # 保存到历史
            _save_history(current_user.id, messages[-1].get('content', ''), assistant_msg.get('content', ''))
            return jsonify({
                "message": assistant_msg,
                "finish_reason": finish_reason,
            })

        # 处理 tool calls
        for tool_call in assistant_msg['tool_calls']:
            fn = tool_call.get('function', {})
            tool_name = fn.get('name', '')
            try:
                tool_args = json.loads(fn.get('arguments', '{}'))
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = _execute_tool(tool_name, tool_args, connection_id)

            current_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get('id', ''),
                "content": tool_result,
            })

    return jsonify({"error": "达到最大工具调用次数"}), 500


def _stream_chat(config, messages, connection_id):
    """流式对话（SSE）"""
    def generate():
        max_iterations = 5
        current_messages = list(messages)

        for iteration in range(max_iterations):
            req, url = _call_llm(config, current_messages, tools=ARTHAS_TOOLS, stream=True)

            try:
                resp = urllib.request.urlopen(req, timeout=120)
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', errors='replace') if e.fp else ''
                yield f"data: {json.dumps({'error': f'HTTP {e.code}: {body[:200]}'}, ensure_ascii=False)}\n\n"
                return
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                return

            # 解析 SSE 流
            assistant_content = ''
            tool_calls_map = {}  # index -> {id, name, arguments}
            finish_reason = ''

            try:
                buffer = ''
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk.decode('utf-8', errors='replace')

                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()

                        if not line or not line.startswith('data: '):
                            continue

                        data_str = line[6:]
                        if data_str == '[DONE]':
                            continue

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choice = data.get('choices', [{}])[0]
                        delta = choice.get('delta', {})
                        finish_reason = choice.get('finish_reason', '') or finish_reason

                        # 处理内容 delta
                        content = delta.get('content', '')
                        if content:
                            assistant_content += content
                            yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"

                        # 处理 tool_calls delta
                        if delta.get('tool_calls'):
                            for tc_delta in delta['tool_calls']:
                                idx = tc_delta.get('index', 0)
                                if idx not in tool_calls_map:
                                    tool_calls_map[idx] = {
                                        'id': tc_delta.get('id', ''),
                                        'type': 'function',
                                        'function': {'name': '', 'arguments': ''}
                                    }
                                fn_delta = tc_delta.get('function', {})
                                if fn_delta.get('name'):
                                    tool_calls_map[idx]['function']['name'] += fn_delta['name']
                                if fn_delta.get('arguments'):
                                    tool_calls_map[idx]['function']['arguments'] += fn_delta['arguments']
                                if tc_delta.get('id'):
                                    tool_calls_map[idx]['id'] = tc_delta['id']

            finally:
                resp.close()

            # 构建完整的 assistant 消息
            assistant_msg = {"role": "assistant", "content": assistant_content or None}
            if tool_calls_map:
                assistant_msg["tool_calls"] = [tool_calls_map[i] for i in sorted(tool_calls_map.keys())]

            current_messages.append(assistant_msg)

            # 如果没有 tool_calls，对话结束
            if finish_reason != 'tool_calls' or not tool_calls_map:
                # 保存历史
                _save_history(current_user.id, messages[-1].get('content', ''), assistant_content)
                yield f"data: {json.dumps({'type': 'done', 'finish_reason': finish_reason}, ensure_ascii=False)}\n\n"
                return

            # 执行工具调用
            for idx in sorted(tool_calls_map.keys()):
                tc = tool_calls_map[idx]
                fn = tc['function']
                tool_name = fn['name']
                try:
                    tool_args = json.loads(fn.get('arguments', '{}'))
                except json.JSONDecodeError:
                    tool_args = {}

                # 通知前端正在执行工具
                yield f"data: {json.dumps({'type': 'tool_start', 'name': tool_name, 'args': tool_args}, ensure_ascii=False)}\n\n"

                tool_result = _execute_tool(tool_name, tool_args, connection_id)

                # 通知前端工具执行结果
                yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'result': tool_result[:500]}, ensure_ascii=False)}\n\n"

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc['id'],
                    "content": tool_result,
                })

        yield f"data: {json.dumps({'type': 'done', 'finish_reason': 'max_iterations'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


def _save_history(user_id: int, user_msg: str, ai_msg: str):
    """保存对话历史"""
    try:
        db.insert('ai_chat_history', {
            'user_id': user_id,
            'role': 'user',
            'content': user_msg[:4000],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        db.insert('ai_chat_history', {
            'user_id': user_id,
            'role': 'assistant',
            'content': (ai_msg or '')[:4000],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
    except Exception:
        pass  # 历史保存失败不影响对话


# ═══════════════════════════════════════════════════════════════════════════════
# 数据库表初始化
# ═══════════════════════════════════════════════════════════════════════════════

def init_ai_tables():
    """初始化 AI 相关数据库表"""
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                api_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT DEFAULT 'openai',
                system_prompt TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_config_user ON ai_config(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ai_chat_user ON ai_chat_history(user_id, created_at)')

        # 迁移：为旧表添加 provider 字段
        try:
            cursor.execute("SELECT provider FROM ai_config LIMIT 1")
        except Exception:
            cursor.execute("ALTER TABLE ai_config ADD COLUMN provider TEXT DEFAULT 'openai'")

        # 迁移：api_key 允许空字符串（Ollama 无需 key）
        try:
            cursor.execute("UPDATE ai_config SET api_key = '' WHERE api_key IS NULL")
        except Exception:
            pass
