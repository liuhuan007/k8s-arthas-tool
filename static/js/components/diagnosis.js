/**
 * 诊断能力主组件 - 能力卡片列表展示与执行
 * 
 * 功能：
 * 1. 从 /api/tasks/capabilities 加载能力目录
 * 2. 按层级/分类展示能力卡片
 * 3. 点击执行按钮触发诊断
 * 4. 联动 diagnosis-form.js / diagnosis-result.js
 */
(function() {
  'use strict';

  let _capabilities = [];
  let _currentFilter = { type: null, category: null, level: null };

  /**
   * 初始化诊断能力模块
   */
  window.diagCapInit = async function() {
    await loadCapabilities();
    renderCapabilityCards();
    setupFilterHandlers();
  };

  /**
   * 加载能力目录
   */
  async function loadCapabilities() {
    try {
      const params = {};
      if (_currentFilter.type) params.type = _currentFilter.type;
      if (_currentFilter.category) params.category = _currentFilter.category;
      if (_currentFilter.level) params.level = _currentFilter.level;
      if (typeof isAdmin === 'function' && isAdmin()) params.include_disabled = '1';

      const data = await safeGet('/tasks/capabilities', params);
      let capabilities = data.capabilities || [];
      
      // ✅ 新增: 根据连接状态过滤能力
      const connLevel = diagGetConnectionLevel();
      capabilities = filterCapabilitiesByConnection(capabilities, connLevel);
      
      _capabilities = capabilities;
    } catch (e) {
      console.error('加载诊断能力失败:', e);
      showError('加载诊断能力失败: ' + e.message);
    }
  }

  /**
   * 渲染能力卡片列表
   */
  function renderCapabilityCards() {
    const container = document.getElementById('diagnosisCapList');
    if (!container) {
      console.warn('diagnosisCapList 容器不存在');
      return;
    }

    if (_capabilities.length === 0) {
      container.innerHTML = renderEmptyState();
      return;
    }

    // 按 level 分组
    const grouped = groupByLevel(_capabilities);
    
    container.innerHTML = Object.keys(grouped).sort().map(level => `
      <div class="capability-level-group">
        <h3 class="level-title">${getLevelTitle(level)}</h3>
        <div class="capability-grid">
          ${grouped[level].map(cap => renderCapabilityCard(cap)).join('')}
        </div>
      </div>
    `).join('');
  }
  
  /**
   * ✅ P2: 渲染空状态引导
   */
  function renderEmptyState() {
    const connLevel = diagGetConnectionLevel();
    
    if (connLevel === 'none') {
      return `
        <div class="sb-empty">
          <div style="font-size:48px;margin-bottom:12px">🔌</div>
          <div style="font-size:16px;color:var(--text-primary);margin-bottom:8px">暂无可用诊断能力</div>
          <div style="font-size:14px;color:var(--text-secondary)">请先在「连接中心」建立 Pod 连接</div>
          <button class="btn btn-p" style="margin-top:16px" onclick="switchTab('connections')">前往连接中心</button>
        </div>
      `;
    }
    
    if (connLevel === 'pod') {
      return `
        <div class="sb-empty">
          <div style="font-size:48px;margin-bottom:12px">🔧</div>
          <div style="font-size:16px;color:var(--text-primary);margin-bottom:8px">当前仅有 Pod 连接</div>
          <div style="font-size:14px;color:var(--text-secondary)">需要启动 Arthas Agent 才能使用完整诊断能力</div>
          <button class="btn btn-p" style="margin-top:16px" onclick="switchTab('connections')">启动 Arthas</button>
        </div>
      `;
    }
    
    return `
      <div class="sb-empty">
        <div style="font-size:48px;margin-bottom:12px">📋</div>
        <div style="font-size:16px;color:var(--text-primary);margin-bottom:8px">暂无诊断能力</div>
        <div style="font-size:14px;color:var(--text-secondary)">管理员可在后台配置诊断能力</div>
      </div>
    `;
  }

  /**
   * 按层级分组
   */
  function groupByLevel(caps) {
    const groups = {};
    caps.forEach(cap => {
      const level = cap.level || 1;
      if (!groups[level]) groups[level] = [];
      groups[level].push(cap);
    });
    return groups;
  }

  /**
   * 获取层级标题
   */
  function getLevelTitle(level) {
    const titles = {
      1: 'L1 - 快速工具',
      2: 'L2 - 诊断工具',
      3: 'L3 - 场景方案',
      4: 'L4 - AI 诊断'
    };
    return titles[level] || `L${level}`;
  }

  /**
   * 渲染单个能力卡片
   */
  function renderCapabilityCard(cap) {
    const hasParams = cap.parameters_schema && cap.parameters_schema !== '{}' && cap.parameters_schema !== '[]';
    const riskBadge = getRiskBadge(cap.risk_level);
    const categoryLabel = getCategoryLabel(cap.category);
    const duration = cap.estimated_duration || 10;
    const adminActions = (typeof isAdmin === 'function' && isAdmin()) ? `
      <button class="btn btn-small" onclick="window.diagOpenCapabilityModal(${cap.id})">编辑</button>
      <button class="btn btn-small danger-text" onclick="window.diagDisableCapability(${cap.id})" ${cap.status === 'disabled' ? 'disabled' : ''}>禁用</button>
    ` : '';

    return `
      <div class="capability-card ${cap.status === 'disabled' ? 'is-disabled' : ''}" data-cap-id="${cap.id}" data-category="${cap.category}">
        <div class="capability-header">
          <h4 class="capability-name">${escapeHtml(cap.name)}</h4>
          <div class="capability-badges">
            ${riskBadge}
            <span class="badge badge-category">${categoryLabel}</span>
            ${cap.status === 'disabled' ? '<span class="badge badge-medium">已禁用</span>' : ''}
          </div>
        </div>
        
        <p class="capability-desc">${escapeHtml(cap.description || '')}</p>
        
        <div class="capability-meta">
          <span class="meta-item">⏱ 预计 ${duration}s</span>
          ${cap.related_capabilities ? `<span class="meta-item">🔗 关联 ${JSON.parse(cap.related_capabilities || '[]').length} 个能力</span>` : ''}
        </div>
        
        <div class="capability-actions">
          ${hasParams 
            ? `<button class="btn btn-config" onclick="window.diagShowCapForm(${cap.id})" ${cap.status === 'disabled' ? 'disabled' : ''}>配置参数</button>`
            : `<button class="btn btn-primary" onclick="window.diagExecuteCap(${cap.id})" ${cap.status === 'disabled' ? 'disabled' : ''}>执行诊断</button>`
          }
          ${adminActions}
        </div>
      </div>
    `;
  }

  window.diagOpenCapabilityModal = function(capId = null) {
    if (typeof isAdmin === 'function' && !isAdmin()) {
      showError('仅管理员可维护诊断能力');
      return;
    }
    const cap = capId ? _capabilities.find(item => item.id === capId) : null;
    const schemaText = cap ? normalizeSchemaForEdit(cap.parameters_schema) : '{}';
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.innerHTML = `
      <div class="capability-modal">
        <div class="modal-header">
          <h3>${cap ? '编辑能力' : '新建能力'}</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body">
          <form id="diagCapabilityEditForm" onsubmit="window.diagSubmitCapabilityForm(event, ${cap ? cap.id : 'null'})">
            <label>名称<input id="diagCapName" required value="${escapeAttr(cap?.name || '')}"></label>
            <label>分类
              <select id="diagCapCategory">
                ${['quick','tool','scenario','ai'].map(category => `<option value="${category}" ${cap?.category === category ? 'selected' : ''}>${getCategoryLabel(category)}</option>`).join('')}
              </select>
            </label>
            <label>层级<input id="diagCapLevel" type="number" min="1" max="4" value="${cap?.level || 1}"></label>
            <label>可见性
              <select id="diagCapVisibility">
                <option value="public" ${cap?.visibility !== 'private' ? 'selected' : ''}>public</option>
                <option value="private" ${cap?.visibility === 'private' ? 'selected' : ''}>private</option>
              </select>
            </label>
            <label>状态
              <select id="diagCapStatus">
                <option value="active" ${cap?.status !== 'disabled' ? 'selected' : ''}>active</option>
                <option value="disabled" ${cap?.status === 'disabled' ? 'selected' : ''}>disabled</option>
              </select>
            </label>
            <label>风险
              <select id="diagCapRisk">
                ${['low','medium','high'].map(risk => `<option value="${risk}" ${cap?.risk_level === risk ? 'selected' : ''}>${risk}</option>`).join('')}
              </select>
            </label>
            <label>预计耗时(s)<input id="diagCapDuration" type="number" min="0" value="${cap?.estimated_duration || 10}"></label>
            <label>描述<textarea id="diagCapDesc" rows="3">${escapeHtml(cap?.description || '')}</textarea></label>
            <label>Arthas 命令<textarea id="diagCapCommand" rows="2">${escapeHtml(cap?.arthas_command || '')}</textarea></label>
            <label>参数 Schema(JSON)<textarea id="diagCapSchema" rows="5">${escapeHtml(schemaText)}</textarea></label>
            <div class="diag-form-footer">
              <button type="button" class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
              <button type="submit" class="btn btn-p">保存</button>
            </div>
          </form>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.diagSubmitCapabilityForm = async function(event, capId = null) {
    event.preventDefault();
    let schema;
    try {
      schema = JSON.parse(document.getElementById('diagCapSchema').value || '{}');
    } catch (_) {
      showError('参数 Schema 必须是合法 JSON');
      return;
    }
    const payload = {
      name: document.getElementById('diagCapName').value.trim(),
      category: document.getElementById('diagCapCategory').value,
      level: Number(document.getElementById('diagCapLevel').value || 1),
      visibility: document.getElementById('diagCapVisibility').value,
      status: document.getElementById('diagCapStatus').value,
      risk_level: document.getElementById('diagCapRisk').value,
      estimated_duration: Number(document.getElementById('diagCapDuration').value || 0),
      description: document.getElementById('diagCapDesc').value.trim(),
      arthas_command: document.getElementById('diagCapCommand').value.trim(),
      parameters_schema: schema,
    };
    try {
      if (capId) {
        await safePut(`/tasks/capabilities/${capId}`, payload);
      } else {
        await safePost('/tasks/capabilities', payload);
      }
      document.querySelector('.capability-modal-overlay')?.remove();
      showSuccess(capId ? '能力已更新' : '能力已创建');
      await loadCapabilities();
      renderCapabilityCards();
    } catch (e) {
      showError('保存能力失败: ' + e.message);
    }
  };

  window.diagDisableCapability = async function(capId) {
    if (!confirm('确认禁用该能力？历史记录不会被删除。')) return;
    try {
      await safeDelete(`/tasks/capabilities/${capId}`);
      showSuccess('能力已禁用');
      await loadCapabilities();
      renderCapabilityCards();
    } catch (e) {
      showError('禁用能力失败: ' + e.message);
    }
  };

  function normalizeSchemaForEdit(schema) {
    if (!schema) return '{}';
    if (typeof schema === 'object') return JSON.stringify(schema, null, 2);
    try { return JSON.stringify(JSON.parse(schema), null, 2); } catch (_) { return schema; }
  }

  function escapeAttr(text) {
    return escapeHtml(text).replace(/"/g, '&quot;');
  }

  /**
   * 获取风险等级徽章
   */
  function getRiskBadge(riskLevel) {
    const config = {
      low: { class: 'badge-low', text: '低风险' },
      medium: { class: 'badge-medium', text: '中风险' },
      high: { class: 'badge-high', text: '高风险' }
    };
    const c = config[riskLevel] || config.low;
    return `<span class="badge ${c.class}">${c.text}</span>`;
  }

  /**
   * 获取分类标签
   */
  function getCategoryLabel(category) {
    const labels = {
      quick: '快速',
      tool: '工具',
      scenario: '场景',
      ai: 'AI'
    };
    return labels[category] || category;
  }

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * 显示能力参数表单
   */
  window.diagShowCapForm = function(capId) {
    if (window.diagShowParameterForm) {
      window.diagShowParameterForm(capId);
    } else {
      console.error('diagShowParameterForm 未定义');
    }
  };

  /**
   * 执行能力（无参数）
   */
  window.diagExecuteCap = async function(capId) {
    const cap = _capabilities.find(c => c.id === capId);
    if (!cap) {
      showError('能力不存在');
      return;
    }

    // 检查连接
    const connId = diagGetCurrentConnectionId();
    if (!connId) {
      showError('请先连接目标 Pod');
      return;
    }
    
    // ✅ 新增: 检查工具包是否已分发
    const toolCheck = await checkToolRequired(cap);
    if (!toolCheck.ok) {
      const goToolbox = confirm(`${toolCheck.message}\n\n是否前往工具箱分发工具？`);
      if (goToolbox) {
        switchTab('toolchain-center');
      }
      return;
    }

    // 高危能力确认
    if (cap.risk_level === 'high') {
      const confirmed = confirm(`此操作为高风险，是否继续？\n\n能力：${cap.name}\n描述：${cap.description}`);
      if (!confirmed) return;
    }

    // 执行诊断
    await executeCapability(capId, connId, {});
  };

  /**
   * 执行能力（带参数）
   */
  window.diagExecuteCapWithParams = async function(capId, params) {
    const connId = diagGetCurrentConnectionId();
    if (!connId) {
      showError('请先连接目标 Pod');
      return false;
    }

    return await executeCapability(capId, connId, params);
  };

  /**
   * 执行诊断
   */
  async function executeCapability(capId, connId, params) {
    const cap = _capabilities.find(c => c.id === capId);
    if (!cap) return;

    // 显示加载状态
    showLoading(`正在执行: ${cap.name}...`);

    try {
      const result = await safePost('/tasks/diagnosis/execute', {
        capability_id: capId,
        connection_id: connId,
        params: params
      }, 120000);

      hideLoading();

      if (result.ok) {
        const runId = result.run_id || result.execution_id || result.log_id;
        const isAsync = result.status === 'running';

        if (isAsync && runId) {
          // 异步执行（场景方案/AI 诊断）：注册后轮询
          if (window.DiagnosisContext) {
            const localId = `exec-${Date.now()}-${capId}`;
            DiagnosisContext.registerExecution(localId, capId, cap.name);
            DiagnosisContext.replaceLocalExecutionId(localId, runId);
          }
          showLoading(`正在执行: ${cap.name}（后台执行中）...`);
          return await pollAndShowResult(runId, cap);
        }

        // 同步完成
        if (window.DiagnosisContext) {
          const execId = runId || `exec-${Date.now()}-${capId}`;
          DiagnosisContext.completeExecution(execId, 'completed', result.result);
        }

        showDiagnosisResult(result.result, cap);
        return true;
      } else {
        if (window.DiagnosisContext) {
          const execId = result.run_id || `exec-${Date.now()}-${capId}`;
          DiagnosisContext.completeExecution(execId, 'failed');
        }
        showError(result.error || '诊断失败');
        return false;
      }
    } catch (e) {
      hideLoading();
      if (window.DiagnosisContext) {
        DiagnosisContext.completeExecution(`exec-${Date.now()}-${capId}`, 'failed');
      }
      if (e.message.includes('连接') || e.message.includes('connection')) {
        showError('Arthas 连接已断开，请重新建立连接后重试');
      } else {
        showError('诊断执行失败: ' + e.message);
      }
      return false;
    }
  }

  /**
   * 轮询异步执行状态并展示结果
   */
  async function pollAndShowResult(runId, cap) {
    try {
      if (window.DiagnosisContext && DiagnosisContext.pollExecution) {
        const run = await DiagnosisContext.pollExecution(runId, 2000);
        hideLoading();
        if (run) {
          if (run.status === 'cancelled') {
            showError('诊断已取消');
          } else if (run.status === 'failed') {
            showError(run.error_message || '诊断执行失败');
          } else {
            const result = run.result || {};
            showDiagnosisResult(result, cap);
          }
          if (window.DiagnosisContext) {
            DiagnosisContext.completeExecution(runId, run.status === 'success' || run.status === 'partial' ? 'completed' : 'failed', run.result);
          }
          return run.status !== 'failed' && run.status !== 'cancelled';
        }
        // fallback: 尝试直接查询
        const fallback = await safeGet(`/tasks/diagnosis/runs/${runId}`);
        if (fallback && fallback.ok && fallback.run) {
          const run = fallback.run;
          if (run.status === 'cancelled') {
            showError('诊断已取消');
          } else if (run.status === 'failed') {
            showError(run.error_message || '诊断执行失败');
          } else {
            showDiagnosisResult(run.result || {}, cap);
          }
          if (window.DiagnosisContext) {
            DiagnosisContext.completeExecution(runId, run.status === 'success' ? 'completed' : 'failed', run.result);
          }
          return true;
        }
        showError('轮询超时，请在诊断历史中查看结果');
        return false;
      }
    } catch (e) {
      hideLoading();
      showError('轮询状态失败: ' + e.message);
      return false;
    }
  }

  function showDiagnosisResult(result, cap) {
    if (typeof renderDiagnosisResult === 'function') {
      window.diagRenderResult(renderDiagnosisResult(result, cap), cap);
    } else if (window.diagRenderResult) {
      window.diagRenderResult(result, cap);
    } else {
      showSuccess('诊断完成');
      console.log('诊断结果:', result);
    }
  }
  
  /**
   * ✅ 新增: 构建命令（支持跨步数据传递）
   */
  function buildCommandWithStepOutputs(commandTemplate, params, stepOutputs) {
    let command = commandTemplate;
    
    // 替换用户参数
    for (const [key, value] of Object.entries(params)) {
      command = command.replace(`\${${key}}`, String(value));
    }
    
    // 替换步骤输出 ${step1.field}
    for (const [stepKey, stepOutput] of Object.entries(stepOutputs)) {
      const pattern = new RegExp(`\\$\\{${stepKey}\\.([\\w.]+)\\}`, 'g');
      command = command.replace(pattern, (match, fieldPath) => {
        return extractNestedValue(stepOutput, fieldPath) || match;
      });
    }
    
    return command;
  }
  
  /**
   * ✅ 新增: 提取嵌套值
   */
  function extractNestedValue(obj, path) {
    const parts = path.split('.');
    let current = obj;
    
    for (const part of parts) {
      if (current === null || current === undefined) return null;
      
      // 数组索引访问
      const arrayMatch = part.match(/(\w+)\[(\d+)\]/);
      if (arrayMatch) {
        current = current[arrayMatch[1]]?.[parseInt(arrayMatch[2])];
      } else {
        current = current[part];
      }
    }
    
    return current;
  }

  /**
   * 获取当前连接 ID
   */
  function diagGetCurrentConnectionId() {
    // 优先使用 ConnectionStore
    if (window.ConnectionStore) {
      return ConnectionStore.getCurrentConnectionId();
    }
    // 兼容旧版
    if (window._currentConnId) {
      return window._currentConnId;
    }
    return null;
  }
  
  /**
   * ✅ 新增: 检查诊断能力需要的工具包
   */
  async function checkToolRequired(capability) {
    // 从能力描述或元数据中判断是否需要特定工具
    const needsArthas = capability.type === 'arthas_command' || 
                        capability.category === 'tool' || 
                        capability.category === 'scenario';
    
    if (!needsArthas) {
      return { ok: true };
    }
    
    try {
      // 检查工具箱中是否有可用的 Arthas 包
      const data = await safeGet('/tasks/tool-packages');
      const packages = data.packages || [];
      const arthasPackages = packages.filter(p => 
        p.tool_type === 'arthas' && p.status === 'active'
      );
      
      if (arthasPackages.length === 0) {
        return { 
          ok: false, 
          message: '执行此诊断需要 Arthas 工具包，但工具箱中暂无可用工具' 
        };
      }
      
      return { ok: true };
    } catch (e) {
      console.warn('检查工具包失败:', e);
      return { ok: true }; // 失败时不阻塞
    }
  }
  
  /**
   * ✅ 新增: 根据连接状态过滤能力
   */
  function filterCapabilitiesByConnection(capabilities, connLevel) {
    return capabilities.filter(cap => {
      // arthas_ready: 所有能力可用
      if (connLevel === 'arthas') return true;
      
      // pod_connected: 仅 Pod 级能力（quick 类型且不需要 Arthas）
      if (connLevel === 'pod') {
        return cap.level === 1 && cap.type !== 'arthas_command';
      }
      
      // none: 无连接，不展示任何能力
      return false;
    });
  }
  
  /**
   * 获取当前连接层级
   */
  function diagGetConnectionLevel() {
    if (window.ConnectionGuard) return ConnectionGuard.getCurrentLevel();
    const cs = window._connState;
    if (cs === 'arthas_ready') return 'arthas';
    if (cs === 'pod_connected') return 'pod';
    return 'none';
  }

  /**
   * 设置筛选器事件
   */
  function setupFilterHandlers() {
    const filterBtns = document.querySelectorAll('.capability-filter-btn');
    filterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const type = btn.dataset.type;
        const category = btn.dataset.category;
        const level = btn.dataset.level;

        _currentFilter = { type, category, level };
        
        // 更新按钮激活状态
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // 重新加载
        loadCapabilities().then(renderCapabilityCards);
      });
    });
  }

  /**
   * 显示错误
   */
  function showError(msg) {
    if (window.showErrorNotification) {
      window.showErrorNotification(msg);
    } else {
      alert(msg);
    }
  }

  /**
   * 显示成功
   */
  function showSuccess(msg) {
    if (window.showSuccessNotification) {
      window.showSuccessNotification(msg);
    } else {
      alert(msg);
    }
  }

  /**
   * 显示加载
   */
  function showLoading(msg) {
    const overlay = document.getElementById('diagLoadingOverlay');
    if (overlay) {
      overlay.querySelector('.loading-text').textContent = msg;
      overlay.style.display = 'flex';
    }
  }

  /**
   * 隐藏加载
   */
  function hideLoading() {
    const overlay = document.getElementById('diagLoadingOverlay');
    if (overlay) {
      overlay.style.display = 'none';
    }
  }

})();
