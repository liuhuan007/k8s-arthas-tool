/**
 * agent-chat.js — AI Agent 对话组件
 *
 * 功能：
 * 1. 与后端 AI Agent 进行流式对话
 * 2. 展示用户消息和 AI 回复（含 Markdown 渲染）
 * 3. 支持快捷问题按钮
 * 4. 对话历史持久化到 localStorage
 * 5. 支持清空对话
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────
  let _messages = [];           // 对话历史 [{role, content}]
  let _isStreaming = false;
  let _abortController = null;
  let _sessionId = null;  // Agent SDK 会话 ID（Phase 7 新增）
  const _STORAGE_KEY = 'dc_agent_chat_history';
  const _MAX_MESSAGES = 50;

  // ════════════════════════════════════════════════════════════════════════
  // 公开 API
  // ════════════════════════════════════════════════════════════════════════

  /**
   * 发送消息
   */
  window.dcAgentSend = async function () {
    var input = document.getElementById('dcChatInput');
    if (!input) return;

    var message = input.value.trim();
    if (!message) return;
    if (_isStreaming) return;

    // 清空欢迎页
    var welcome = document.getElementById('dcChatWelcome');
    if (welcome) welcome.remove();

    // 添加用户消息
    input.value = '';
    input.style.height = 'auto';
    _addMessage('user', message);
    _messages.push({ role: 'user', content: message });
    _saveHistory();

    // 开始流式对话
    _isStreaming = true;
    var sendBtn = document.getElementById('dcChatSendBtn');
    if (sendBtn) sendBtn.disabled = true;

    var assistantEl = _addMessage('assistant', '', true);

    // 获取连接 ID
    var connId = '';
    if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnId === 'function') {
      connId = ConnectionStore.getCurrentConnId() || '';
    } else if (window._currentConnId) {
      connId = window._currentConnId;
    }

    try {
      _abortController = new AbortController();
      // 120 秒超时保护，防止 _isStreaming 卡死
      var _timeoutId = setTimeout(function() { _abortController.abort(); }, 120000);

      // Phase 7：调用 Agent SDK 接口
      var r = await fetch('/api/agent/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          message: message,
          session_id: _sessionId,
          connection_id: connId,
          stream: true,
        }),
        signal: _abortController.signal,
      });

      if (!r.ok) {
        var errBody = await r.json().catch(function () { return { error: 'HTTP ' + r.status }; });
        throw new Error(errBody.error || 'HTTP ' + r.status);
      }

      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var fullContent = '';
      var buffer = '';

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;

        buffer += decoder.decode(chunk.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (!line.startsWith('data: ')) continue;
          var dataStr = line.slice(6).trim();
          if (!dataStr) continue;

          try {
            var data = JSON.parse(dataStr);

            if (data.type === 'content') {
              fullContent += data.content;
              _updateMessage(assistantEl, fullContent, true);
            } else if (data.type === 'anomaly_events') {
              _renderAnomalyCards(assistantEl, data.events || []);
            } else if (data.type === 'tool_start') {
              fullContent += '\n\n🔧 执行工具: **' + (data.name || '') + '**\n';
              if (data.args && data.args.command) {
                fullContent += '📝 命令: `' + data.args.command + '`\n';
              }
              _updateMessage(assistantEl, fullContent, true);
            } else if (data.type === 'tool_result') {
              fullContent += '✓ 工具执行完成\n\n';
              _updateMessage(assistantEl, fullContent, true);
            } else if (data.type === 'done') {
              // 完成
            } else if (data.error) {
              fullContent += '\n\n❌ 错误: ' + data.error;
              _updateMessage(assistantEl, fullContent, true);
            }
          } catch (_) { /* 忽略解析错误 */ }
        }
      }

      _updateMessage(assistantEl, fullContent, false);
      _messages.push({ role: 'assistant', content: fullContent });
      _saveHistory();

    } catch (e) {
      if (e.name === 'AbortError') {
        _updateMessage(assistantEl, fullContent || '（已取消）', false);
      } else {
        _updateMessage(assistantEl, '❌ 请求失败: ' + e.message, false);
      }
    } finally {
      clearTimeout(_timeoutId);
      _isStreaming = false;
      if (sendBtn) sendBtn.disabled = false;
      _abortController = null;
    }
  };

  /**
   * 快捷问题
   */
  window.dcAgentQuickAsk = function (question) {
    var input = document.getElementById('dcChatInput');
    if (input) {
      input.value = question;
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }
    dcAgentSend();
  };

  /**
   * 清空对话
   */
  window.dcAgentClearChat = function () {
    _messages = [];
    _saveHistory();

    var container = document.getElementById('dcChatMessages');
    if (container) {
      container.innerHTML = '<div class="dc-chat-welcome" id="dcChatWelcome">'
        + '<div class="dc-chat-welcome-icon">🤖</div>'
        + '<div class="dc-chat-welcome-title">AI 诊断助手</div>'
        + '<div class="dc-chat-welcome-desc">我可以帮你分析 Java 应用性能问题，自动执行诊断并生成分析报告。</div>'
        + '<div class="dc-chat-quick-actions">'
        + '<button class="dc-chat-quick-btn" onclick="dcAgentQuickAsk(\'CPU 占用很高怎么排查？\')">🔥 CPU 飙高排查</button>'
        + '<button class="dc-chat-quick-btn" onclick="dcAgentQuickAsk(\'接口响应慢如何定位？\')">⏱️ 接口慢定位</button>'
        + '<button class="dc-chat-quick-btn" onclick="dcAgentQuickAsk(\'内存泄漏怎么排查？\')">💾 内存泄漏排查</button>'
        + '<button class="dc-chat-quick-btn" onclick="dcAgentQuickAsk(\'线程死锁怎么检测？\')">🔒 线程死锁检测</button>'
        + '</div></div>';
    }
  };

  /**
   * 停止当前流式响应
   */
  window.dcAgentStop = function () {
    if (_abortController) {
      _abortController.abort();
    }
  };

  /**
   * 初始化：加载历史对话
   */
  window.dcAgentInit = function () {
    _loadHistory();
  };

  // ════════════════════════════════════════════════════════════════════════
  // 异常事件卡片渲染
  // ════════════════════════════════════════════════════════════════════════

  var _SEVERITY_COLORS = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#3b82f6',
    info: '#6b7280',
  };

  function _renderAnomalyCards (assistantEl, events) {
    if (!assistantEl || !events || events.length === 0) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'dc-anomaly-cards';
    wrapper.style.cssText = 'margin-bottom:8px;display:flex;flex-wrap:wrap;gap:6px;';

    events.forEach(function (evt) {
      var color = _SEVERITY_COLORS[(evt.severity || '').toLowerCase()] || '#6b7280';
      var card = document.createElement('div');
      card.className = 'dc-anomaly-card';
      card.style.cssText = 'display:inline-flex;align-items:center;gap:6px;padding:4px 10px;'
        + 'border-radius:6px;font-size:12px;cursor:pointer;border:1px solid ' + color + '30;'
        + 'background:' + color + '15;color:' + color + ';transition:background 0.15s;';
      card.title = (evt.message || evt.rule_name || '') + '\n点击查看详情';

      card.innerHTML = '<span style="font-weight:600;">' + _esc((evt.severity || 'INFO').toUpperCase()) + '</span>'
        + '<span>' + _esc(evt.rule_name || '未知规则') + '</span>'
        + (evt.created_at ? '<span style="opacity:0.7;">' + _esc(evt.created_at.replace(/T/, ' ').substring(0, 19)) + '</span>' : '');

      card.addEventListener('mouseenter', function () { card.style.background = color + '30'; });
      card.addEventListener('mouseleave', function () { card.style.background = color + '15'; });
      card.addEventListener('click', function () {
        // 打开异常事件页面，按当前连接过滤
        var connId = '';
        if (window.ConnectionStore && typeof ConnectionStore.getCurrentConnectionId === 'function') {
          connId = ConnectionStore.getCurrentConnectionId() || '';
        }
        if (window.showAnomalyEvents) {
          window.showAnomalyEvents(connId);
        } else {
          // 回退：导航到异常事件页面
          window.open('/static/anomaly-events.html' + (connId ? '?connection_id=' + encodeURIComponent(connId) : ''), '_blank');
        }
      });

      wrapper.appendChild(card);
    });

    // 插入到 assistant 消息气泡中，内容区域之前
    var bubble = assistantEl.querySelector('.dc-chat-bubble');
    if (bubble) {
      var contentDiv = bubble.querySelector('.dc-chat-content');
      if (contentDiv) {
        bubble.insertBefore(wrapper, contentDiv);
      } else {
        bubble.insertBefore(wrapper, bubble.firstChild);
      }
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 消息渲染
  // ════════════════════════════════════════════════════════════════════════

  function _addMessage (role, content, streaming) {
    var container = document.getElementById('dcChatMessages');
    if (!container) return null;

    var div = document.createElement('div');
    div.className = 'dc-chat-msg ' + role;

    if (role === 'user') {
      div.innerHTML = '<div class="dc-chat-avatar">👤</div>'
        + '<div class="dc-chat-bubble">' + _esc(content) + '</div>';
    } else if (role === 'assistant') {
      div.innerHTML = '<div class="dc-chat-avatar">🤖</div>'
        + '<div class="dc-chat-bubble"><div class="dc-chat-content">' + _renderMd(content) + '</div>'
        + (streaming ? '<span class="dc-chat-typing"><span></span><span></span><span></span></span>' : '')
        + '</div>';
    } else {
      div.innerHTML = '<div class="dc-chat-bubble">' + _esc(content) + '</div>';
    }

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  function _updateMessage (el, content, streaming) {
    if (!el) return;
    var bubble = el.querySelector('.dc-chat-bubble');
    if (bubble) {
      var contentHtml = _renderMd(content)
        + (streaming ? '<span class="dc-chat-typing"><span></span><span></span><span></span></span>' : '');
      var contentDiv = bubble.querySelector('.dc-chat-content');
      if (contentDiv) {
        contentDiv.innerHTML = contentHtml;
      } else {
        bubble.innerHTML = contentHtml;
      }
    }
    var container = document.getElementById('dcChatMessages');
    if (container) container.scrollTop = container.scrollHeight;
  }

  // ════════════════════════════════════════════════════════════════════════
  // Markdown 渲染
  // ════════════════════════════════════════════════════════════════════════

  function _renderMd (text) {
    if (!text) return '';
    var html = _esc(text);
    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre>$2</pre>');
    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // 加粗
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // 换行
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  // ════════════════════════════════════════════════════════════════════════
  // 历史持久化
  // ════════════════════════════════════════════════════════════════════════

  function _saveHistory () {
    try {
      var trimmed = _messages.slice(-_MAX_MESSAGES).map(function (m) {
        return { role: m.role, content: (m.content || '').substring(0, 2000) };
      });
      localStorage.setItem(_STORAGE_KEY, JSON.stringify(trimmed));
    } catch (_) { /* 忽略存储错误 */ }
  }

  function _loadHistory () {
    try {
      var raw = localStorage.getItem(_STORAGE_KEY);
      if (!raw) return;
      var msgs = JSON.parse(raw);
      if (!Array.isArray(msgs) || msgs.length === 0) return;

      _messages = msgs;
      var container = document.getElementById('dcChatMessages');
      if (!container) return;

      // 移除欢迎页
      var welcome = document.getElementById('dcChatWelcome');
      if (welcome) welcome.remove();

      msgs.forEach(function (m) {
        _addMessage(m.role, m.content, false);
      });
    } catch (_) { /* 忽略解析错误 */ }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 工具
  // ════════════════════════════════════════════════════════════════════════

  function _esc (text) {
    if (text === null || text === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

  // 页面加载时初始化
  document.addEventListener('DOMContentLoaded', function () {
    if (typeof dcAgentInit === 'function') dcAgentInit();
  });

})();
