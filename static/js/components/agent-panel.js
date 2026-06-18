/**
 * agent-panel.js — 多专业 Agent 对话面板
 *
 * 功能：
 * 1. Agent 选择器（Arthas / K8s / Ops / 自动路由）
 * 2. 模式切换（全自动 / 辅助模式）
 * 3. 流式对话 + 工具调用步骤展示
 * 4. 对话历史持久化
 */
(function () {
  'use strict';

  const API = '/api/agent-fw';
  const _STORAGE_KEY = 'arthas_agent_history';
  const _MAX_MESSAGES = 50;

  let _messages = [];
  let _isStreaming = false;
  let _abortController = null;
  let _currentAgent = null;  // null = 自动路由
  let _currentMode = 'auto'; // auto / assist

  // ═══════════════════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════════════════

  function renderAgentPanel(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    _loadHistory();
    container.innerHTML = `
      <div class="agent-panel">
        <div class="agent-panel-header">
          <div class="agent-selector" id="agentSelector">
            <button class="agent-tab active" data-agent="" onclick="agentPanelSelectAgent(this, '')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
              自动路由
            </button>
            <button class="agent-tab" data-agent="arthas" onclick="agentPanelSelectAgent(this, 'arthas')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
              Arthas
            </button>
            <button class="agent-tab" data-agent="k8s" onclick="agentPanelSelectAgent(this, 'k8s')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              K8s
            </button>
            <button class="agent-tab" data-agent="ops" onclick="agentPanelSelectAgent(this, 'ops')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
              Ops
            </button>
          </div>
          <div class="agent-mode-toggle">
            <button class="mode-btn active" data-mode="auto" onclick="agentPanelSetMode(this, 'auto')" title="全自动执行">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              自动
            </button>
            <button class="mode-btn" data-mode="assist" onclick="agentPanelSetMode(this, 'assist')" title="高风险操作需确认">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              辅助
            </button>
          </div>
        </div>
        <div class="agent-messages" id="agentMessages">
          <div class="agent-welcome" id="agentWelcome">
            <div class="agent-welcome-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
            </div>
            <div class="agent-welcome-title">AI 诊断助手</div>
            <div class="agent-welcome-desc">选择专业 Agent 或使用自动路由，描述你的问题即可开始诊断。</div>
            <div class="agent-welcome-tips">
              <button class="agent-quick-btn" onclick="agentPanelQuickAsk('CPU 占用很高怎么排查？')">🔥 CPU 飙高</button>
              <button class="agent-quick-btn" onclick="agentPanelQuickAsk('内存泄漏怎么排查？')">💾 内存泄漏</button>
              <button class="agent-quick-btn" onclick="agentPanelQuickAsk('Pod 一直重启怎么回事？')">🔄 Pod 重启</button>
              <button class="agent-quick-btn" onclick="agentPanelQuickAsk('接口响应慢如何定位？')">⏱️ 接口慢</button>
            </div>
          </div>
        </div>
        <div class="agent-input-area">
          <div class="agent-input-wrap">
            <textarea id="agentInput" class="agent-input" placeholder="描述你的问题..." rows="1"
              onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();agentPanelSend()}"
              oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px'"></textarea>
            <button class="agent-send-btn" id="agentSendBtn" onclick="agentPanelSend()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            </button>
          </div>
        </div>
      </div>
    `;
    _renderHistory();
  }

  // ═══════════════════════════════════════════════════════════════
  // 公开 API
  // ═══════════════════════════════════════════════════════════════

  window.agentPanelSelectAgent = function (btn, agentName) {
    document.querySelectorAll('#agentSelector .agent-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _currentAgent = agentName || null;
  };

  window.agentPanelSetMode = function (btn, mode) {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _currentMode = mode;
  };

  window.agentPanelQuickAsk = function (question) {
    const input = document.getElementById('agentInput');
    if (input) {
      input.value = question;
      agentPanelSend();
    }
  };

  window.agentPanelSend = async function () {
    const input = document.getElementById('agentInput');
    if (!input) return;
    const message = input.value.trim();
    if (!message || _isStreaming) return;

    // 清空欢迎
    const welcome = document.getElementById('agentWelcome');
    if (welcome) welcome.remove();

    input.value = '';
    input.style.height = 'auto';
    _addMessage('user', message);
    _messages.push({ role: 'user', content: message });
    _saveHistory();

    _isStreaming = true;
    const sendBtn = document.getElementById('agentSendBtn');
    if (sendBtn) sendBtn.disabled = true;

    const assistantEl = _addMessage('assistant', '', true);

    try {
      _abortController = new AbortController();
      const body = { message, mode: _currentMode };
      if (_currentAgent) body.agent = _currentAgent;

      const r = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
        signal: _abortController.signal,
      });

      const data = await r.json();

      if (!r.ok) {
        _updateMessage(assistantEl, `❌ ${data.error || '请求失败'}`);
        return;
      }

      // 渲染步骤
      let stepsHtml = '';
      if (data.steps && data.steps.length > 0) {
        stepsHtml = '<div class="agent-steps">' +
          data.steps.map(s =>
            `<div class="agent-step">
              <span class="agent-step-tool">${_esc(s.tool)}</span>
              <span class="agent-step-result">${_esc((s.result || '').substring(0, 150))}</span>
            </div>`
          ).join('') +
          '</div>';
      }

      _updateMessage(assistantEl, stepsHtml + _renderMarkdown(data.answer));

      _messages.push({ role: 'assistant', content: data.answer, agent: data.agent });
      _saveHistory();

    } catch (e) {
      if (e.name !== 'AbortError') {
        _updateMessage(assistantEl, `❌ ${e.message}`);
      }
    } finally {
      _isStreaming = false;
      if (sendBtn) sendBtn.disabled = false;
      _abortController = null;
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 消息渲染
  // ═══════════════════════════════════════════════════════════════

  function _addMessage(role, content, streaming) {
    const container = document.getElementById('agentMessages');
    if (!container) return null;
    const div = document.createElement('div');
    div.className = `agent-msg agent-msg-${role}`;
    if (streaming) div.classList.add('agent-msg-streaming');
    div.innerHTML = role === 'user'
      ? `<div class="agent-msg-content">${_esc(content)}</div>`
      : `<div class="agent-msg-avatar">
           <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
         </div><div class="agent-msg-content">${content || '<span class="agent-typing"></span>'}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  function _updateMessage(el, html) {
    if (!el) return;
    el.classList.remove('agent-msg-streaming');
    const content = el.querySelector('.agent-msg-content');
    if (content) content.innerHTML = html;
    const container = document.getElementById('agentMessages');
    if (container) container.scrollTop = container.scrollHeight;
  }

  function _renderHistory() {
    const container = document.getElementById('agentMessages');
    if (!container || !_messages.length) return;
    const welcome = document.getElementById('agentWelcome');
    if (welcome) welcome.remove();
    _messages.forEach(m => {
      const el = _addMessage(m.role, m.role === 'user' ? m.content : _renderMarkdown(m.content));
      if (el) el.classList.remove('agent-msg-streaming');
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // 工具函数
  // ═══════════════════════════════════════════════════════════════

  function _esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function _renderMarkdown(text) {
    if (!text) return '';
    return text
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="lang-$1">$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  function _saveHistory() {
    try {
      const toSave = _messages.slice(-_MAX_MESSAGES);
      localStorage.setItem(_STORAGE_KEY, JSON.stringify(toSave));
    } catch (e) { /* ignore */ }
  }

  function _loadHistory() {
    try {
      const saved = localStorage.getItem(_STORAGE_KEY);
      if (saved) _messages = JSON.parse(saved);
    } catch (e) { _messages = []; }
  }

  window.agentPanelClearChat = function () {
    _messages = [];
    _saveHistory();
    const container = document.getElementById('agentMessages');
    if (container) {
      container.innerHTML = `
        <div class="agent-welcome" id="agentWelcome">
          <div class="agent-welcome-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
          </div>
          <div class="agent-welcome-title">AI 诊断助手</div>
          <div class="agent-welcome-desc">选择专业 Agent 或使用自动路由，描述你的问题即可开始诊断。</div>
          <div class="agent-welcome-tips">
            <button class="agent-quick-btn" onclick="agentPanelQuickAsk('CPU 占用很高怎么排查？')">🔥 CPU 飙高</button>
            <button class="agent-quick-btn" onclick="agentPanelQuickAsk('内存泄漏怎么排查？')">💾 内存泄漏</button>
            <button class="agent-quick-btn" onclick="agentPanelQuickAsk('Pod 一直重启怎么回事？')">🔄 Pod 重启</button>
            <button class="agent-quick-btn" onclick="agentPanelQuickAsk('接口响应慢如何定位？')">⏱️ 接口慢</button>
          </div>
        </div>`;
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 导出
  // ═══════════════════════════════════════════════════════════════

  window.renderAgentPanel = renderAgentPanel;

})();
