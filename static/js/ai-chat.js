/**
 * AI 对话模块 — 方案 A：平台内配置大模型
 */
(function() {
  'use strict';

  const API = '';
  let _aiMessages = []; // 对话历史
  let _aiStreaming = false;
  let _aiAbortController = null;
  let _aiProviders = []; // 供应商列表

  // 预设供应商配置（本地备份，避免每次请求）
  // 模型列表基于各官网最新资料更新 (2026-04)
  const _presetProviders = {
    deepseek: {
      name: 'DeepSeek',
      base_url: 'https://api.deepseek.com/v1',
      models: ['deepseek-chat', 'deepseek-reasoner'],
      needs_key: true,
      default_model: 'deepseek-chat'
    },
    qwen: {
      name: '通义千问',
      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      models: ['qwen3-max', 'qwen3.6-plus', 'qwen3.5-flash', 'qwen-plus', 'qwen-turbo', 'qwen-long', 'qwq-plus'],
      needs_key: true,
      default_model: 'qwen3.6-plus'
    },
    openai: {
      name: 'OpenAI',
      base_url: 'https://api.openai.com/v1',
      models: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'o1-mini', 'gpt-4-turbo'],
      needs_key: true,
      default_model: 'gpt-4o'
    },
    moonshot: {
      name: '月之暗面 (Kimi)',
      base_url: 'https://api.moonshot.cn/v1',
      models: ['kimi-k2.5', 'kimi-k2-thinking', 'moonshot-v1-128k', 'moonshot-v1-32k', 'moonshot-v1-8k'],
      needs_key: true,
      default_model: 'kimi-k2.5'
    },
    zhipu: {
      name: '智谱 AI',
      base_url: 'https://open.bigmodel.cn/api/paas/v4',
      models: ['glm-5', 'glm-4.7', 'glm-4.6', 'glm-4.5', 'glm-4.5-air', 'glm-4-plus', 'glm-4-flash', 'glm-4-long'],
      needs_key: true,
      default_model: 'glm-4.5-air'
    },
    ollama: {
      name: 'Ollama (本地)',
      base_url: 'http://localhost:11434/v1',
      models: [],
      needs_key: false,
      default_model: ''
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════════════════

  window.aiInit = function() {
    const input = document.getElementById('aiInput');
    if (input) {
      input.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
      });
    }
    aiLoadConfig();
    aiRefreshConnSelect();
    aiLoadProviders();
  };

  // 加载供应商列表
  async function aiLoadProviders() {
    try {
      const r = await fetch(`${API}/api/ai/providers`, {credentials: 'include'});
      const d = await r.json();
      if (d.providers) {
        _aiProviders = d.providers;
      }
    } catch(e) {}
  }

  // ═══════════════════════════════════════════════════════════════
  // 供应商选择
  // ═══════════════════════════════════════════════════════════════

  window.onProviderChange = function(providerId, skipFillDefaults = false) {
    const provider = _presetProviders[providerId];
    if (!provider) {
      // 清空表单
      document.getElementById('aiBaseUrl').value = '';
      document.getElementById('aiModel').value = '';
      document.getElementById('aiDetectOllama').style.display = 'none';
      document.getElementById('aiApiKeyGroup').style.display = '';
      return;
    }

    // 填充默认 URL（仅在非加载模式时）
    if (!skipFillDefaults) {
      document.getElementById('aiBaseUrl').value = provider.base_url;
      document.getElementById('aiModel').value = provider.default_model;
    }

    // 更新模型选择下拉
    const modelSelect = document.getElementById('aiModelSelect');
    if (provider.models && provider.models.length > 0) {
      modelSelect.innerHTML = provider.models.map(m => `<option value="${m}">${m}</option>`).join('');
      modelSelect.style.display = 'block';
    } else {
      modelSelect.style.display = 'none';
    }

    // Ollama 特殊处理
    const isOllama = providerId === 'ollama';
    document.getElementById('aiDetectOllama').style.display = isOllama ? 'block' : 'none';
    document.getElementById('aiApiKeyGroup').style.display = isOllama ? 'none' : '';
    document.getElementById('aiKeyHint').textContent = isOllama ? 'Ollama 本地模型无需 API Key' : '从模型服务商获取';

    // 更新提示信息
    const urlHint = document.getElementById('aiUrlHint');
    const modelHint = document.getElementById('aiModelHint');
    if (isOllama) {
      urlHint.textContent = 'Ollama 默认地址，如使用其他端口请修改';
      modelHint.textContent = '点击「检测模型」按钮获取已安装的本地模型';
    } else {
      urlHint.textContent = `${provider.name} API 地址，通常无需修改`;
      modelHint.textContent = `推荐模型: ${provider.models.join(', ')}`;
    }
  };

  // 检测 Ollama 本地模型
  window.detectOllamaModels = async function() {
    const baseUrl = document.getElementById('aiBaseUrl').value.trim().replace(/\/v1$/, '');
    const modelSelect = document.getElementById('aiModelSelect');
    const modelInput = document.getElementById('aiModel');
    const errEl = document.getElementById('aiModalErr');

    try {
      const r = await fetch(`${API}/api/ai/ollama/models?base_url=${encodeURIComponent(baseUrl)}`, {credentials: 'include'});
      const d = await r.json();

      if (d.ok && d.models && d.models.length > 0) {
        modelSelect.innerHTML = d.models.map(m => `<option value="${m.name}">${m.name} (${formatSize(m.size)})</option>`).join('');
        modelSelect.style.display = 'block';
        modelInput.value = d.models[0].name;
        errEl.textContent = `✓ 检测到 ${d.models.length} 个本地模型`;
        errEl.style.color = 'var(--a3)';
        errEl.style.display = 'block';
      } else {
        errEl.textContent = d.error || '未检测到已安装的模型，请先使用 ollama pull 安装模型';
        errEl.style.color = 'var(--a6)';
        errEl.style.display = 'block';
      }
    } catch(e) {
      errEl.textContent = '检测失败: ' + e.message;
      errEl.style.color = 'var(--a5)';
      errEl.style.display = 'block';
    }
  };

  function formatSize(bytes) {
    if (!bytes) return '';
    const gb = bytes / (1024 * 1024 * 1024);
    if (gb >= 1) return gb.toFixed(1) + ' GB';
    const mb = bytes / (1024 * 1024);
    return mb.toFixed(0) + ' MB';
  }

  // ═══════════════════════════════════════════════════════════════
  // 配置管理
  // ═══════════════════════════════════════════════════════════════

  window.aiOpenSettings = async function() {
    const modal = document.getElementById('aiModal');
    modal.style.display = 'flex';

    // 加载已保存的配置
    try {
      const r = await fetch(`${API}/api/ai/config`, {credentials: 'include'});
      const d = await r.json();
      if (d.config) {
        document.getElementById('aiBaseUrl').value = d.config.base_url || '';
        document.getElementById('aiApiKey').value = ''; // 不回填 key
        document.getElementById('aiApiKey').placeholder = d.config.api_key_masked || 'sk-xxxxxxxx';
        document.getElementById('aiModel').value = d.config.model || '';
        document.getElementById('aiSystemPrompt').value = d.config.system_prompt || '';

        // 根据 base_url 推断并选中供应商
        const providerSelect = document.getElementById('aiProvider');
        const provider = inferProvider(d.config.base_url, d.config.provider);
        if (provider) {
          providerSelect.value = provider;
          onProviderChange(provider, true);  // true = 不覆盖已保存的值
        }
      }
    } catch(e) {}
  };

  // 根据 URL 推断供应商
  function inferProvider(baseUrl, savedProvider) {
    if (savedProvider && _presetProviders[savedProvider]) {
      return savedProvider;
    }
    if (!baseUrl) return '';

    const url = baseUrl.toLowerCase();
    if (url.includes('deepseek')) return 'deepseek';
    if (url.includes('dashscope') || url.includes('aliyun')) return 'qwen';
    if (url.includes('openai.com')) return 'openai';
    if (url.includes('moonshot')) return 'moonshot';
    if (url.includes('bigmodel') || url.includes('zhipu')) return 'zhipu';
    if (url.includes('ollama') || url.includes('localhost:11434')) return 'ollama';

    return '';
  }

  window.closeAiModal = function() {
    document.getElementById('aiModal').style.display = 'none';
    document.getElementById('aiModalErr').style.display = 'none';
  };

  window.saveAiConfig = async function() {
    const provider = document.getElementById('aiProvider').value;
    const apiKey = document.getElementById('aiApiKey').value.trim();
    const baseUrl = document.getElementById('aiBaseUrl').value.trim();
    const model = document.getElementById('aiModel').value.trim();
    const systemPrompt = document.getElementById('aiSystemPrompt').value.trim();

    const errEl = document.getElementById('aiModalErr');

    if (!baseUrl) {
      errEl.textContent = 'API Base URL 不能为空';
      errEl.style.display = 'block';
      return;
    }
    if (!model) {
      errEl.textContent = '模型名称不能为空';
      errEl.style.display = 'block';
      return;
    }

    // Ollama 不需要 API Key
    const isOllama = provider === 'ollama';

    // 如果 key 为空且 placeholder 是脱敏值，说明用户没修改 key，不传 api_key
    const payload = { base_url: baseUrl, model: model, system_prompt: systemPrompt, provider: provider };
    if (apiKey) {
      payload.api_key = apiKey;
    }

    try {
      const r = await fetch(`${API}/api/ai/config`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      const d = await r.json();

      if (d.ok) {
        toast('AI 配置已保存', 'success');
        window._aiConfigured = true;
        closeAiModal();
      } else {
        errEl.textContent = d.error || '保存失败';
        errEl.style.display = 'block';
      }
    } catch(e) {
      errEl.textContent = '保存失败: ' + e.message;
      errEl.style.display = 'block';
    }
  };

  window.testAiConfig = async function() {
    const provider = document.getElementById('aiProvider').value;
    const apiKey = document.getElementById('aiApiKey').value.trim();
    const baseUrl = document.getElementById('aiBaseUrl').value.trim();
    const model = document.getElementById('aiModel').value.trim();
    const errEl = document.getElementById('aiModalErr');
    const btn = document.getElementById('aiTestBtn');
    const isOllama = provider === 'ollama';

    if (!baseUrl || !model) {
      errEl.textContent = '请填写 Base URL 和模型名称';
      errEl.style.display = 'block';
      return;
    }

    // Ollama 不需要 API Key
    if (!isOllama && !apiKey) {
      errEl.textContent = '请填写 API Key（Ollama 本地模型可留空）';
      errEl.style.display = 'block';
      return;
    }

    btn.disabled = true;
    btn.textContent = '测试中...';

    try {
      const r = await fetch(`${API}/api/ai/config/test`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({api_key: apiKey, base_url: baseUrl, model: model}),
      });
      const d = await r.json();

      if (d.ok) {
        errEl.textContent = '✓ 连接成功! 模型回复: ' + (d.response || '').substring(0, 50);
        errEl.style.color = 'var(--a3)';
        errEl.style.display = 'block';
      } else {
        errEl.textContent = '✗ 连接失败: ' + (d.error || '未知错误');
        errEl.style.color = 'var(--a5)';
        errEl.style.display = 'block';
      }
    } catch(e) {
      errEl.textContent = '✗ 请求失败: ' + e.message;
      errEl.style.color = 'var(--a5)';
      errEl.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = '测试连接';
    }
  };

  async function aiLoadConfig() {
    try {
      const r = await fetch(`${API}/api/ai/config`, {credentials: 'include'});
      const d = await r.json();
      console.log('[AI] Config loaded:', d);
      window._aiConfigured = !!d.config;
      console.log('[AI] _aiConfigured:', window._aiConfigured);
    } catch(e) {
      console.log('[AI] Config load error:', e);
      window._aiConfigured = false;
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // 连接选择
  // ═══════════════════════════════════════════════════════════════

  window.aiRefreshConnSelect = function() {
    const sel = document.getElementById('aiConnSelect');
    if (sel) {
      const currentVal = sel.value;
      sel.innerHTML = '<option value="">自动选择活跃连接</option>';
      if (window._connections) {
        window._connections.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c.id;
          const statusTag = c.status === 'connected' ? '' : ' (离线)';
          opt.textContent = `${c.pod_name || c.pod} (${c.cluster_name || c.cluster}/${c.namespace})${statusTag}`;
          if (c.id === currentVal) opt.selected = true;
          sel.appendChild(opt);
        });
      }
      // 优先使用左侧面板当前选中的连接，而非空字符串
      if (!currentVal && window._currentConnId) {
        sel.value = window._currentConnId;
      }
    }

    // 更新连接指示器
    aiUpdateConnIndicator();
  };

  function aiUpdateConnIndicator() {
    const dot = document.getElementById('aiConnDot');
    const label = document.getElementById('aiConnLabel');
    const dropdown = document.getElementById('aiConnDropdown');
    if (!dot || !label) return;

    const conns = window._connections || [];
    const currentId = document.getElementById('aiConnSelect')?.value || window._currentConnId || '';
    const health = window._connHealth || {};

    // 更新当前连接显示
    if (!currentId) {
      dot.innerHTML = '<span style="font-size:11px;opacity:0.5">🔹</span>';
      label.textContent = conns.length ? `自动选择 (${conns.length})` : '未连接';
    } else {
      const c = conns.find(x => x.id === currentId);
      if (c) {
        const h = health[currentId];
        // 【修复】使用与左侧面板一致的 Unicode 符号图标
        let statusIcon = '🔹', statusStyle = '';
        if (h) {
          if (h.pod_exists === false) {
            statusIcon = '⚠'; statusStyle = 'color:var(--a5)';
          } else if (h.reason === 'cluster_unavailable') {
            statusIcon = '⊘'; statusStyle = 'color:var(--a5)';
          } else if (h.alive === false) {
            statusIcon = '◈'; statusStyle = 'color:#f59e0b';
          } else if (h.reason && h.reason.startsWith('pod_')) {
            statusIcon = '◉'; statusStyle = 'color:#f59e0b';
          } else if (h.alive !== false) {
            statusIcon = '●'; statusStyle = 'color:var(--a3)';
          }
        } else {
          statusIcon = c.status === 'connected' ? '●' : '🔹';
          statusStyle = c.status === 'connected' ? 'color:var(--a3)' : '';
        }
        dot.innerHTML = `<span style="font-size:11px;${statusStyle}">${statusIcon}</span>`;
        label.textContent = `${c.namespace}/${c.pod_name || c.pod}`;
      } else {
        dot.innerHTML = '<span style="font-size:11px;opacity:0.5">🔹</span>';
        label.textContent = currentId;
      }
    }

    // 更新下拉列表
    if (dropdown) {
      const autoItem = `<div class="ai-conn-dd-item ${!currentId ? 'active' : ''}" onclick="aiSelectConn('')">
        <span style="font-size:11px;opacity:0.5">🔹</span> 自动选择活跃连接
      </div>`;
      const connItems = conns.map(c => {
        const h = health[c.id];
        // 【修复】使用与左侧面板一致的 Unicode 符号图标
        let statusIcon = '🔹', statusStyle = '', hint = '';
        if (h) {
          if (h.pod_exists === false) {
            statusIcon = '⚠'; statusStyle = 'color:var(--a5)'; hint = 'Pod 不存在';
          } else if (h.reason === 'cluster_unavailable') {
            statusIcon = '⊘'; statusStyle = 'color:var(--a5)'; hint = '集群不可用';
          } else if (h.alive === false) {
            statusIcon = '◈'; statusStyle = 'color:#f59e0b'; hint = 'Arthas 断开';
          } else if (h.reason && h.reason.startsWith('pod_')) {
            statusIcon = '◉'; statusStyle = 'color:#f59e0b'; hint = `Pod: ${h.pod_phase || h.reason}`;
          } else if (h.alive !== false) {
            statusIcon = '●'; statusStyle = 'color:var(--a3)'; hint = '正常';
          }
        } else {
          statusIcon = c.status === 'connected' ? '●' : '🔹';
          statusStyle = c.status === 'connected' ? 'color:var(--a3)' : '';
          hint = c.status === 'connected' ? '正常' : '离线';
        }
        const isActive = c.id === currentId;
        return `<div class="ai-conn-dd-item ${isActive ? 'active' : ''}" onclick="aiSelectConn('${esc(c.id)}')">
          <span style="font-size:11px;${statusStyle}" title="${hint}">${statusIcon}</span>
          <div class="dd-info">
            <div class="dd-pod">${esc(c.pod_name || c.pod)}</div>
            <div class="dd-meta">${esc(c.cluster_name || c.cluster)} / ${esc(c.namespace)}${hint ? ' · ' + hint : ''}</div>
          </div>
        </div>`;
      }).join('');
      dropdown.innerHTML = autoItem + connItems;
    }
  }

  window.aiToggleConnDropdown = function() {
    const dd = document.getElementById('aiConnDropdown');
    if (!dd) return;
    if (dd.style.display === 'none') {
      aiUpdateConnIndicator();
      dd.style.display = 'block';
      // 点击外部关闭
      setTimeout(() => document.addEventListener('click', aiCloseConnDropdown, {once: true}), 0);
    } else {
      dd.style.display = 'none';
    }
  };

  function aiCloseConnDropdown(e) {
    const dd = document.getElementById('aiConnDropdown');
    const indicator = document.getElementById('aiConnIndicator');
    if (dd && !dd.contains(e.target) && !indicator?.contains(e.target)) {
      dd.style.display = 'none';
    }
  }

  window.aiSelectConn = function(connId) {
    const sel = document.getElementById('aiConnSelect');
    if (sel) sel.value = connId;
    document.getElementById('aiConnDropdown').style.display = 'none';
    aiUpdateConnIndicator();

    // 如果选择了具体连接，切换左侧面板的活跃连接
    if (connId && window._currentConnId !== connId && typeof switchConnection === 'function') {
      switchConnection(connId);
    }
  };

  // 监听左侧面板连接切换事件，自动同步 AI 面板
  document.addEventListener('connection-changed', function(e) {
    const sel = document.getElementById('aiConnSelect');
    if (sel && e.detail && e.detail.connId) {
      sel.value = e.detail.connId;
    }
    aiUpdateConnIndicator();
  });

  // ═══════════════════════════════════════════════════════════════
  // 对话
  // ═══════════════════════════════════════════════════════════════

  window.aiSend = async function() {
    console.log('[AI] aiSend called, _aiStreaming:', _aiStreaming, '_aiConfigured:', window._aiConfigured);
    if (_aiStreaming) return;

    const input = document.getElementById('aiInput');
    const msg = input.value.trim();
    if (!msg) return;

    // 检查是否配置了 AI
    if (!window._aiConfigured) {
      console.log('[AI] Not configured, showing settings');
      aiAddSystemMessage('⚠️ 请先配置 AI 模型，点击顶部「⚙️ 配置大模型」');
      aiOpenSettings();
      return;
    }

    // 清空欢迎页
    const welcome = document.querySelector('.ai-welcome');
    if (welcome) welcome.remove();

    // 添加用户消息
    input.value = '';
    input.style.height = 'auto';
    aiAddMessage('user', msg);
    _aiMessages.push({role: 'user', content: msg});
    saveChatToStorage();

    // 获取连接 ID：优先使用下拉选择，否则使用左侧面板当前连接
    const connId = document.getElementById('aiConnSelect')?.value || window._currentConnId || '';

    // 开始流式对话
    _aiStreaming = true;
    document.getElementById('aiSendBtn').disabled = true;

    const assistantEl = aiAddMessage('assistant', '', true);

    try {
      console.log('[AI] Sending request to /api/ai/chat');
      const r = await fetch(`${API}/api/ai/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({
          messages: _aiMessages,
          connection_id: connId,
          stream: true,
        }),
      });

      console.log('[AI] Response status:', r.status);
      if (!r.ok) {
        const err = await r.json().catch(() => ({error: `HTTP ${r.status}`}));
        console.log('[AI] Error response:', err);
        throw new Error(err.error || `HTTP ${r.status}`);
      }

      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';
      let buffer = '';

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const dataStr = line.slice(6).trim();
          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);
            console.log('[AI] SSE event:', data.type || data.error ? 'error' : 'content');

            if (data.type === 'content') {
              fullContent += data.content;
              aiUpdateMessage(assistantEl, fullContent, true);
            } else if (data.type === 'tool_start') {
              fullContent += `\n\n🔧 执行工具: **${data.name}**\n`;
              if (data.args && data.args.command) {
                fullContent += `📝 命令: \`${data.args.command}\`\n`;
              }
              aiUpdateMessage(assistantEl, fullContent, true);
            } else if (data.type === 'tool_result') {
              fullContent += `✓ 工具执行完成\n\n`;
              aiUpdateMessage(assistantEl, fullContent, true);
            } else if (data.type === 'done') {
              console.log('[AI] Stream done');
            } else if (data.error) {
              console.log('[AI] Error in stream:', data.error);
              fullContent += `\n\n❌ 错误: ${data.error}`;
              aiUpdateMessage(assistantEl, fullContent, true);
            }
          } catch(e) {
            console.log('[AI] Parse error:', e);
          }
        }
      }

      console.log('[AI] Stream complete, fullContent length:', fullContent.length);
      aiUpdateMessage(assistantEl, fullContent, false);
      _aiMessages.push({role: 'assistant', content: fullContent});
      saveChatToStorage();

    } catch(e) {
      aiUpdateMessage(assistantEl, `❌ 请求失败: ${e.message}`, false);
    } finally {
      _aiStreaming = false;
      document.getElementById('aiSendBtn').disabled = false;
    }
  };

  window.aiQuickAsk = function(question) {
    const input = document.getElementById('aiInput');
    input.value = question;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    aiSend();
  };

  window.aiKeyDown = function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      aiSend();
    }
  };

  window.aiAutoResize = function(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  };

  window.aiClearChat = function() {
    _aiMessages = [];
    localStorage.removeItem(_CHAT_STORAGE_KEY);
    const container = document.getElementById('aiMessages');
    container.innerHTML = `
      <div class="ai-welcome">
        <div class="ai-welcome-icon">🤖</div>
        <div class="ai-welcome-title">Java 诊断 AI 助手</div>
        <div class="ai-welcome-desc">我可以帮你分析 Java 应用性能问题，通过 Arthas 命令自动诊断 Pod 中的应用。</div>
        <div class="ai-welcome-tips">
          <div class="ai-tip" onclick="aiQuickAsk('CPU 占用很高怎么排查？')">🔥 CPU 飙高排查</div>
          <div class="ai-tip" onclick="aiQuickAsk('接口响应慢如何定位？')">⏱️ 接口慢定位</div>
          <div class="ai-tip" onclick="aiQuickAsk('内存泄漏怎么排查？')">💾 内存泄漏排查</div>
          <div class="ai-tip" onclick="aiQuickAsk('线程死锁怎么检测？')">🔒 线程死锁检测</div>
        </div>
      </div>`;
  };

  // ═══════════════════════════════════════════════════════════════
  // 消息渲染
  // ═══════════════════════════════════════════════════════════════

  function aiAddMessage(role, content, streaming = false) {
    const container = document.getElementById('aiMessages');
    const div = document.createElement('div');
    div.className = `ai-msg ai-msg-${role}`;

    if (role === 'user') {
      div.innerHTML = `
        <div class="ai-msg-avatar">👤</div>
        <div class="ai-msg-body"><div class="ai-msg-text">${esc(content)}</div></div>`;
    } else {
      div.innerHTML = `
        <div class="ai-msg-avatar">🤖</div>
        <div class="ai-msg-body"><div class="ai-msg-text">${renderMd(content)}${streaming ? '<span class="ai-cursor">▊</span>' : ''}</div></div>`;
    }

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  function aiUpdateMessage(el, content, streaming) {
    const textEl = el.querySelector('.ai-msg-text');
    if (textEl) {
      textEl.innerHTML = renderMd(content) + (streaming ? '<span class="ai-cursor">▊</span>' : '');
    }
    const container = document.getElementById('aiMessages');
    container.scrollTop = container.scrollHeight;
  }

  function aiAddSystemMessage(msg) {
    const container = document.getElementById('aiMessages');
    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-system';
    div.innerHTML = `<div class="ai-msg-text">${esc(msg)}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  // 简单 Markdown 渲染
  function renderMd(text) {
    if (!text) return '';
    let html = esc(text);
    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="ai-code"><code>$2</code></pre>');
    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');
    // 加粗
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // 换行
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  // ═══════════════════════════════════════════════════════════════
  // 聊天历史持久化（localStorage）
  // ═══════════════════════════════════════════════════════════════

  const _CHAT_STORAGE_KEY = 'arthas_ai_messages';

  function saveChatToStorage() {
    try {
      // 只保存最近 50 条消息，每条截断到 2000 字符
      const trimmed = _aiMessages.slice(-50).map(m => ({
        role: m.role,
        content: (m.content || '').substring(0, 2000)
      }));
      localStorage.setItem(_CHAT_STORAGE_KEY, JSON.stringify(trimmed));
    } catch(e) {}
  }

  function loadChatFromStorage() {
    try {
      const raw = localStorage.getItem(_CHAT_STORAGE_KEY);
      if (!raw) return;
      const msgs = JSON.parse(raw);
      if (!Array.isArray(msgs) || msgs.length === 0) return;

      _aiMessages = msgs;
      const container = document.getElementById('aiMessages');
      container.innerHTML = '';
      msgs.forEach(m => aiAddMessage(m.role, m.content));
    } catch(e) {}
  }

  // 页面加载时初始化
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      aiInit();
      loadChatFromStorage();  // 恢复聊天历史
    }, 500);
  });

  // ═══════════════════════════════════════════════════════════════
  // MCP 配置模态框
  // ═══════════════════════════════════════════════════════════════

  let _mcpConnections = [];
  let _mcpSelectedConn = '';
  let _mcpCurrentConfigs = null;
  let _mcpCurrentClientType = 'cherry_studio_cline';

  window.openMcpModal = function() {
    document.getElementById('mcpModal').style.display = 'flex';
    // 自动选择当前左侧面板选中的连接
    _mcpSelectedConn = window._currentConnId || '';
    // 触发健康检查，确保状态最新（如果函数存在）
    if (typeof checkConnectionsHealth === 'function') {
      checkConnectionsHealth();
    }
    mcpLoadConnections();
    mcpLoadTokens();
  };

  window.closeMcpModal = function() {
    document.getElementById('mcpModal').style.display = 'none';
  };

  async function mcpLoadConnections() {
    const el = document.getElementById('mcp-conn-list');
    
    // 【关键修复】优先使用 window._connections（与左侧面板同步）
    // 这确保 MCP Modal 和左侧面板显示一致的状态
    const localConns = window._connections || [];
    const localHealth = window._connHealth || {};
    
    // 如果本地有连接数据，直接使用本地数据（避免状态不一致）
    if (localConns.length > 0) {
      _mcpConnections = localConns.map(c => {
        // 合并健康检查状态
        const h = localHealth[c.id] || {};
        const isAlive = h.alive !== false && h.pod_exists !== false && c.status === 'connected';
        return {
          id: c.id,
          pod: c.pod_name || c.pod,
          namespace: c.namespace,
          cluster: c.cluster_name || c.cluster,
          local_port: c.local_port || 0,
          alive: isAlive,
          status: isAlive ? 'connected' : 'disconnected',
          mcp_available: c.mcp_available || false,
        };
      });
    } else {
      // 本地没有数据时，才从后端接口获取
      try {
        const r = await fetch('/api/mcp/connections', {credentials: 'include'});
        const d = await r.json();
        _mcpConnections = d.connections || [];
      } catch(e) {
        el.innerHTML = '<div style="text-align:center;padding:16px;color:var(--a5);font-size:12px">加载失败</div>';
        return;
      }
    }

    if (!_mcpConnections.length) {
      el.innerHTML = '<div style="text-align:center;padding:16px;color:var(--tx3);font-size:12px">暂无可用连接<br><span style="font-size:11px">请先在左侧面板连接 Pod</span></div>';
      return;
    }

    // 如果没有选中连接，自动选中第一个活跃连接或当前左侧面板连接
    if (!_mcpSelectedConn) {
      const activeConn = _mcpConnections.find(c => c.alive);
      _mcpSelectedConn = (activeConn && activeConn.id) || (window._currentConnId) || (_mcpConnections[0] && _mcpConnections[0].id) || '';
    }

    el.innerHTML = _mcpConnections.map(c => {
      const label = c.pod ? `${c.namespace || ''}/${c.pod}` : c.id;
      const meta = c.cluster ? `${c.cluster}` : `port: ${c.local_port}`;
      // 【修复】使用与左侧面板一致的 Unicode 符号图标
      const localHealth = window._connHealth || {};
      const h = localHealth[c.id];
      let statusIcon = '🔹', statusStyle = '', statusText = '离线';
      if (h) {
        if (h.pod_exists === false) {
          statusIcon = '⚠'; statusStyle = 'color:var(--a5)'; statusText = 'Pod 不存在';
        } else if (h.reason === 'cluster_unavailable') {
          statusIcon = '⊘'; statusStyle = 'color:var(--a5)'; statusText = '集群不可用';
        } else if (h.alive === false) {
          statusIcon = '◈'; statusStyle = 'color:#f59e0b'; statusText = 'Arthas 断开';
        } else if (h.reason && h.reason.startsWith('pod_')) {
          statusIcon = '◉'; statusStyle = 'color:#f59e0b'; statusText = `Pod: ${h.pod_phase || h.reason}`;
        } else if (h.pod_exists === true && h.alive !== false) {
          statusIcon = '●'; statusStyle = 'color:var(--a3)'; statusText = '已连接';
        }
      } else if (c.alive) {
        statusIcon = '●'; statusStyle = 'color:var(--a3)'; statusText = '已连接';
      }
      // MCP 标记
      const mcpBadge = c.mcp_available 
        ? '<span style="font-size:9px;padding:1px 4px;border-radius:4px;background:rgba(63,185,80,.15);color:#3fb950;margin-left:4px">MCP</span>' 
        : '';
      // 是否为当前选中/绑定状态
      const boundIds = window._mcpBoundConnectionIds || [];
      const isBound = boundIds.includes(c.id);
      const isSelected = (_mcpSelectedConn === c.id) || isBound;
      // 当前左侧面板连接标记
      const isLeftActive = c.id === (window._currentConnId || '');
      const leftBadge = isLeftActive ? '<span style="font-size:9px;padding:1px 4px;border-radius:4px;background:rgba(122,162,247,.15);color:#7aa2f7;margin-left:4px">当前</span>' : '';
      
      return `<div class="mcp-conn-opt ${isSelected ? 'sel' : ''}" onclick="mcpSelectConn('${esc(c.id)}')">
        <span style="font-size:12px;${statusStyle}" title="${statusText}">${statusIcon}</span>
        <div style="flex:1;font-size:12px">
          <div style="font-family:var(--mono);font-size:11px">${esc(label)}${mcpBadge}${leftBadge}</div>
          <div style="font-size:10px;color:var(--tx3);margin-top:2px">${esc(meta)} · ${statusText}</div>
        </div>
        ${isSelected ? `<button class="btn btn-g btn-sm" style="padding:2px 6px;font-size:10px" onclick="event.stopPropagation();switchToLeftPanel('${esc(c.id)}')" title="切换左侧面板选中">↙ 切换</button>` : ''}
      </div>`;
    }).join('');
  }
  
  // 切换到左侧面板选中
  window.switchToLeftPanel = function(connId) {
    if (typeof switchConnection === 'function') {
      switchConnection(connId);
      // 刷新 MCP 列表以更新高亮
      _mcpSelectedConn = connId;
      mcpLoadConnections();
    }
  };

  window.mcpSelectConn = function(connId) {
    _mcpSelectedConn = connId;
    mcpLoadConnections();  // 重新渲染高亮
  };

  window.mcpUseCurrentConn = function() {
    // 快捷选择：使用左侧面板当前选中的连接
    const currentId = window._currentConnId;
    if (!currentId) {
      toast('左侧面板暂无选中连接，请先连接 Pod', 'warn');
      return;
    }
    _mcpSelectedConn = currentId;
    mcpLoadConnections();
    toast('已选中当前连接', 'success');
  };

  window.mcpCreateToken = async function() {
    if (!_mcpSelectedConn) {
      toast('请先选择一个连接', 'warn');
      return;
    }

    // 检查选中连接是否活跃
    const selectedConn = _mcpConnections.find(c => c.id === _mcpSelectedConn);
    if (selectedConn && !selectedConn.alive) {
      if (!confirm('选中的连接当前未激活，MCP 代理将无法正常工作。建议先在 Web 界面连接 Pod。\n\n确定要继续创建 Token 吗？')) {
        return;
      }
    }

    const name = document.getElementById('mcpTokenName').value.trim();
    try {
      const r = await fetch('/api/mcp/tokens', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({name: name || undefined, connection_id: _mcpSelectedConn}),
      });
      const d = await r.json();
      if (d.error) { toast(d.error, 'error'); return; }

      // 显示 Token 原文（仅此一次）
      const token = d.token || '';
      if (token) {
        prompt('请复制 Token（关闭后无法再次查看）：', token);
      }

      // 显示警告（如果有）
      if (d.warning) {
        toast(d.warning, 'warn');
      } else {
        toast('Token 创建成功！', 'success');
      }

      mcpLoadTokens();
      document.getElementById('mcpTokenName').value = '';
    } catch(e) {
      toast('创建失败: ' + e.message, 'error');
    }
  };

  async function mcpLoadTokens() {
    const el = document.getElementById('mcp-token-list');
    try {
      const r = await fetch('/api/mcp/tokens', {credentials: 'include'});
      const d = await r.json();
      const tokens = d.tokens || [];

      // 缓存 Token 的连接绑定集合
      window._mcpBoundConnectionIds = tokens.map(x => x.connection_id).filter(Boolean);

      if (!tokens.length) {
        el.innerHTML = '<div style="text-align:center;padding:12px;color:var(--tx3);font-size:12px">暂无 Token，请先创建</div>';
        return;
      }

      el.innerHTML = tokens.map(t => {
        const createdAt = t.created_at ? t.created_at.substring(0, 16).replace('T', ' ') : '';
        // 友好化连接ID显示
        const connInfo = _mcpConnections.find(c => c.id === t.connection_id);
        const connDisplay = connInfo 
          ? `${connInfo.namespace || ''}/${connInfo.pod || connInfo.id}` 
          : (t.connection_id ? t.connection_id.substring(0, 40) : '未绑定');
        return `
        <div class="mcp-token-row">
          <span class="name">${esc(t.name)}</span>
          <span class="time" style="color:var(--tx3);font-size:10px;min-width:90px">${createdAt}</span>
          <span class="conn" title="${esc(t.connection_id)}">${esc(connDisplay)}</span>
          <span class="badge ${t.is_active ? 'active' : 'inactive'}">${t.is_active ? '启用' : '禁用'}</span>
          <button class="ib" style="font-size:10px;padding:2px 6px" onclick="mcpShowConfig(${t.id})">📋 配置</button>
          <button class="ib" style="font-size:10px;padding:2px 6px" onclick="mcpBindToken(${t.id})">↗ 绑定</button>
          <button class="ib" style="font-size:10px;padding:2px 6px" onclick="mcpToggleToken(${t.id})">${t.is_active ? '禁用' : '启用'}</button>
          <button class="ib" style="font-size:10px;padding:2px 6px;color:var(--a5)" onclick="mcpDeleteToken(${t.id})">删除</button>
        </div>
      `}).join('');
    } catch(e) {
      el.innerHTML = '<div style="text-align:center;padding:12px;color:var(--a5);font-size:12px">加载失败</div>';
    }
  }

  window.mcpShowConfig = async function(tokenId) {
    try {
      const r = await fetch(`/api/mcp/config/${tokenId}`, {credentials: 'include'});
      const d = await r.json();
      if (d.error) { toast(d.error, 'error'); return; }
      _mcpCurrentConfigs = d.configs;
      mcpRenderConfig(_mcpCurrentClientType);
      document.getElementById('mcp-config-section').style.display = '';

      // 显示连接状态提示
      const hintEl = document.getElementById('mcp-config-hint');
      if (hintEl) {
        const connId = d.connection_id || '';
        const connInfo = _mcpConnections.find(c => c.id === connId);
        const isActive = d.is_active !== false;
        const connAlive = connInfo && connInfo.alive;
        let hintHtml = '';
        if (!isActive) {
          hintHtml = '<span style="color:var(--a5)">⚠️ Token 已禁用，AI 客户端无法连接</span>';
        } else if (!connAlive) {
          hintHtml = `<span style="color:var(--a6)">⚠️ 绑定连接 (${esc(connId)}) 未激活，请先在 Web 界面连接 Pod</span>`;
        } else {
          hintHtml = `<span style="color:var(--a3)">✓ 绑定连接正常 (${esc(connId)})</span>`;
        }
        if (d.hint) {
          hintHtml += `<br><span style="color:var(--tx3);font-size:10px">${esc(d.hint)}</span>`;
        }
        hintEl.innerHTML = hintHtml;
        hintEl.style.display = '';
      }
    } catch(e) {
      toast('加载配置失败', 'error');
    }
  };

  function mcpRenderConfig(clientType) {
    if (!_mcpCurrentConfigs || !_mcpCurrentConfigs[clientType]) return;
    document.getElementById('mcpConfigJson').textContent = JSON.stringify(_mcpCurrentConfigs[clientType], null, 2);
  }

  window.mcpSwitchClient = function(el) {
    document.querySelectorAll('.mcp-ct').forEach(t => t.classList.remove('on'));
    el.classList.add('on');
    _mcpCurrentClientType = el.dataset.client;
    mcpRenderConfig(_mcpCurrentClientType);
  };

  window.mcpCopyConfig = function() {
    const text = document.getElementById('mcpConfigJson').textContent;
    navigator.clipboard.writeText(text).then(() => toast('已复制到剪贴板', 'success'));
  };

  window.mcpToggleToken = async function(tokenId) {
    try {
      const r = await fetch(`/api/mcp/tokens/${tokenId}/toggle`, {method: 'POST', credentials: 'include'});
      const d = await r.json();
      if (d.error) { toast(d.error, 'error'); return; }
      toast(d.is_active ? '已启用' : '已禁用', 'success');
      mcpLoadTokens();
    } catch(e) { toast('操作失败', 'error'); }
  };

  window.mcpBindToken = async function(tokenId) {
    try {
      const connId = _mcpSelectedConn || window._currentConnId;
      if (!tokenId) return;
      if (!connId) { toast('请在左侧面板先选择一个连接'); return; }
      const r = await fetch(`/api/mcp/tokens/${tokenId}/bind`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'include',
        body: JSON.stringify({connection_id: connId})
      });
      const d = await r.json();
      if (d.error) { toast(d.error, 'error'); return; }
      toast('绑定成功', 'success');
      // 同步左侧面板状态：绑定成功后切换到绑定的连接以保持一致性
      if (typeof window.switchConnection === 'function' && connId) {
        window.switchConnection(connId);
      }
      // 重新加载 token 列表以刷新绑定信息
      mcpLoadTokens();
    } catch(e) {
      toast('绑定失败: ' + (e && e.message ? e.message : ''), 'error');
    }
  };

  window.mcpDeleteToken = async function(tokenId) {
    if (!confirm('确定删除此 Token？删除后 AI 客户端将无法连接')) return;
    try {
      const r = await fetch(`/api/mcp/tokens/${tokenId}`, {method: 'DELETE', credentials: 'include'});
      const d = await r.json();
      if (d.error) { toast(d.error, 'error'); return; }
      toast('已删除', 'success');
      mcpLoadTokens();
      document.getElementById('mcp-config-section').style.display = 'none';
    } catch(e) { toast('删除失败', 'error'); }
  };

})();
