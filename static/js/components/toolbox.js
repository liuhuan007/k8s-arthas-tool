/**
 * 工具箱组件 - 双栏布局
 * 左栏：工具包管理
 * 右栏：诊断能力目录
 */
(function() {
  'use strict';

  /**
   * 渲染工具箱双栏布局
   */
  window.renderToolboxDualLayout = async function() {
    await Promise.all([
      loadToolPackages(),
      loadToolboxDiagCaps(),
      loadScriptTemplates()
    ]);
    
    // ✅ Phase 8: 启动实时刷新
    initToolboxRealtimeRefresh();
  };

  /**
   * 加载工具包列表
   */
  async function loadToolPackages() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      const packages = data.packages || [];
      renderToolPackageList(packages);
    } catch (e) {
      console.error('加载工具包失败:', e);
    }
  }

  /**
   * 渲染工具包列表
   */
  function renderToolPackageList(packages) {
    const container = document.getElementById('toolPackageList');
    if (!container) return;

    if (packages.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无工具包<br>上传 arthas-boot.jar 开始使用</div>';
      return;
    }

    container.innerHTML = packages.map(p => {
      const sha = p.sha256 ? `${p.sha256.slice(0, 12)}...` : '未校验';
      const statusClass = p.status === 'active' ? 'running' : 'stopped';
      const statusText = p.status === 'active' ? '可用' : '停用';

      return `
        <div class="tool-package-item">
          <div class="tool-package-main">
            <div>
              <div class="task-item-name">${escapeHtml(p.name)} ${p.is_builtin ? '<span class="task-status running">内置</span>' : ''}</div>
              <div class="task-item-meta">类型：${p.tool_type} · 版本：${escapeHtml(p.version || '-')} · SHA256：${sha}</div>
            </div>
            <div class="task-item-actions">
              <span class="task-status ${statusClass}">${statusText}</span>
              <button class="btn btn-g" onclick="verifyToolPackage(${p.id})">校验</button>
              <button class="btn btn-p" onclick="distributeToolPackage(${p.id})">分发到 Pod</button>
              ${!p.is_builtin ? `<button class="btn btn-g danger-text" onclick="deleteToolPackage(${p.id})">删除</button>` : ''}
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * 加载工具箱诊断能力
   */
  async function loadToolboxDiagCaps() {
    try {
      const data = await safeGet('/tasks/capabilities', { limit: 6 });
      const capabilities = data.capabilities || [];
      renderToolboxDiagCaps(capabilities);
    } catch (e) {
      console.error('加载诊断能力失败:', e);
    }
  }

  /**
   * 渲染工具箱诊断能力卡片
   */
  function renderToolboxDiagCaps(capabilities) {
    const container = document.getElementById('toolchainDiagCaps');
    if (!container) return;

    if (capabilities.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无诊断能力</div>';
      return;
    }

    container.innerHTML = capabilities.map(cap => {
      const riskBadge = getRiskBadgeHtml(cap.risk_level);
      const hasParams = cap.parameters_schema && cap.parameters_schema !== '{}' && cap.parameters_schema !== '[]';

      return `
        <div class="toolbox-cap-item">
          <div class="toolbox-cap-header">
            <h4>${escapeHtml(cap.name)}</h4>
            ${riskBadge}
          </div>
          <p class="toolbox-cap-desc">${escapeHtml(cap.description || '')}</p>
          <div class="toolbox-cap-actions">
            ${hasParams
              ? `<button class="btn btn-g" onclick="window.diagShowCapForm(${cap.id})">配置参数</button>`
              : `<button class="btn btn-p" onclick="window.diagExecuteCap(${cap.id})">执行诊断</button>`
            }
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * 获取风险等级徽章 HTML
   */
  function getRiskBadgeHtml(riskLevel) {
    const config = {
      low: { class: 'badge-low', text: '低风险' },
      medium: { class: 'badge-medium', text: '中风险' },
      high: { class: 'badge-high', text: '高风险' }
    };
    const c = config[riskLevel] || config.low;
    return `<span class="badge ${c.class}">${c.text}</span>`;
  }

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  /**
   * 加载脚本模板列表
   */
  async function loadScriptTemplates() {
    try {
      const data = await safeGet('/tasks/script-templates');
      const templates = data.templates || [];
      renderScriptTemplateList(templates);
    } catch (e) {
      console.error('加载脚本模板失败:', e);
      document.getElementById('scriptTemplateList').innerHTML = '<div class="sb-empty">加载失败</div>';
    }
  }
  
  /**
   * 渲染脚本模板列表
   */
  function renderScriptTemplateList(templates) {
    const container = document.getElementById('scriptTemplateList');
    if (!container) return;
    
    if (templates.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无脚本模板<br>点击右上角"+ 新建模板"创建</div>';
      return;
    }
    
    container.innerHTML = templates.map(t => `
      <div class="script-template-item">
        <div class="template-main">
          <div>
            <div class="template-name">${escapeHtml(t.name)}</div>
            <div class="template-meta">
              运行时: ${t.runtime} · 
              ${t.capability_id ? '关联诊断能力' : '独立模板'}
            </div>
          </div>
          <div class="template-actions">
            <button class="btn btn-g" onclick="editScriptTemplate(${t.id})">编辑</button>
            <button class="btn btn-g danger-text" onclick="deleteScriptTemplate(${t.id})">删除</button>
          </div>
        </div>
      </div>
    `).join('');
  }
  
  /**
   * 打开创建脚本模板模态框
   */
  window.openCreateScriptTemplateModal = function() {
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.innerHTML = `
      <div class="capability-modal">
        <div class="modal-header">
          <h3>创建脚本模板</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:20px">
          <div class="form-group">
            <label class="form-label">模板名称 <span class="required">*</span></label>
            <input id="newTemplateName" class="form-input" placeholder="例如：CPU 分析脚本">
          </div>
          <div class="form-group">
            <label class="form-label">运行时</label>
            <select id="newTemplateRuntime" class="form-input">
              <option value="python">Python</option>
              <option value="shell">Shell</option>
              <option value="node">Node.js</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">关联诊断能力（可选）</label>
            <select id="newTemplateCapability" class="form-input">
              <option value="">无（独立模板）</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">脚本内容 <span class="required">*</span></label>
            <textarea id="newTemplateScript" class="form-input" rows="8" placeholder="print('hello')"></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <textarea id="newTemplateDesc" class="form-input" rows="2" placeholder="模板说明"></textarea>
          </div>
        </div>
        <div class="modal-footer" style="padding:16px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:flex-end;gap:8px">
          <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
          <button class="btn btn-p" onclick="submitCreateScriptTemplate()">创建</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    
    // 加载诊断能力列表
    loadCapabilitiesForSelect();
    
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  };
  
  /**
   * 加载诊断能力列表到下拉框
   */
  async function loadCapabilitiesForSelect() {
    try {
      const data = await safeGet('/tasks/capabilities', { limit: 100 });
      const capabilities = data.capabilities || [];
      const select = document.getElementById('newTemplateCapability');
      if (!select) return;
      
      capabilities.forEach(cap => {
        const option = document.createElement('option');
        option.value = cap.id;
        option.textContent = `${cap.name} (${cap.type})`;
        select.appendChild(option);
      });
    } catch (e) {
      console.warn('加载诊断能力列表失败:', e);
    }
  }
  
  /**
   * 提交创建脚本模板
   */
  window.submitCreateScriptTemplate = async function() {
    const name = document.getElementById('newTemplateName').value.trim();
    const script = document.getElementById('newTemplateScript').value.trim();
    
    if (!name || !script) {
      toast('请填写模板名称和脚本内容', 'warn');
      return;
    }
    
    try {
      const payload = {
        name: name,
        runtime: document.getElementById('newTemplateRuntime').value,
        script_body: script,
        description: document.getElementById('newTemplateDesc').value
      };
      
      const capabilityId = document.getElementById('newTemplateCapability').value;
      if (capabilityId) {
        payload.capability_id = parseInt(capabilityId);
      }
      
      await safePost('/tasks/script-templates', payload);
      
      toast('脚本模板创建成功', 'ok');
      document.querySelector('.capability-modal-overlay')?.remove();
      loadScriptTemplates();
    } catch (e) {
      toast(`创建失败：${e.message}`, 'err');
    }
  };
  
  /**
   * 编辑脚本模板
   */
  window.editScriptTemplate = async function(templateId) {
    try {
      const data = await safeGet(`/tasks/script-templates/${templateId}`);
      const t = data.template || data;

      const modal = document.createElement('div');
      modal.className = 'capability-modal-overlay';
      modal.innerHTML = `
        <div class="capability-modal">
          <div class="modal-header">
            <h3>编辑脚本模板</h3>
            <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
          </div>
          <div class="modal-body" style="padding:20px">
            <div class="form-group">
              <label class="form-label">模板名称 <span class="required">*</span></label>
              <input id="editTemplateName" class="form-input" value="${escapeHtml(t.name || '')}">
            </div>
            <div class="form-group">
              <label class="form-label">运行时</label>
              <select id="editTemplateRuntime" class="form-input">
                <option value="python" ${t.runtime === 'python' ? 'selected' : ''}>Python</option>
                <option value="shell" ${t.runtime === 'shell' ? 'selected' : ''}>Shell</option>
                <option value="node" ${t.runtime === 'node' ? 'selected' : ''}>Node.js</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">脚本内容 <span class="required">*</span></label>
              <textarea id="editTemplateScript" class="form-input" rows="8">${escapeHtml(t.script_body || '')}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">描述</label>
              <textarea id="editTemplateDesc" class="form-input" rows="2">${escapeHtml(t.description || '')}</textarea>
            </div>
          </div>
          <div class="modal-footer" style="padding:16px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:flex-end;gap:8px">
            <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
            <button class="btn btn-p" onclick="submitEditScriptTemplate(${templateId})">保存</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    } catch (e) {
      toast(`加载模板失败：${e.message}`, 'err');
    }
  };

  /**
   * 提交编辑脚本模板
   */
  window.submitEditScriptTemplate = async function(templateId) {
    const name = document.getElementById('editTemplateName').value.trim();
    const script = document.getElementById('editTemplateScript').value.trim();

    if (!name || !script) {
      toast('请填写模板名称和脚本内容', 'warn');
      return;
    }

    try {
      const payload = {
        name: name,
        runtime: document.getElementById('editTemplateRuntime').value,
        script_body: script,
        description: document.getElementById('editTemplateDesc').value
      };

      await safePut(`/tasks/script-templates/${templateId}`, payload);

      toast('脚本模板已更新', 'ok');
      document.querySelector('.capability-modal-overlay')?.remove();
      loadScriptTemplates();
    } catch (e) {
      toast(`更新失败：${e.message}`, 'err');
    }
  };
  
  /**
   * 删除脚本模板
   */
  window.deleteScriptTemplate = async function(templateId) {
    if (!confirm('确认删除此脚本模板？')) return;
    
    try {
      await safeDelete(`/tasks/script-templates/${templateId}`);
      toast('脚本模板已删除', 'ok');
      loadScriptTemplates();
    } catch (e) {
      toast(`删除失败：${e.message}`, 'err');
    }
  };
  
  /**
   * ✅ Phase 8: 工具箱实时刷新
   */
  let _toolboxRefreshInterval = null;
  
  function initToolboxRealtimeRefresh() {
    // 清除旧定时器
    if (_toolboxRefreshInterval) {
      clearInterval(_toolboxRefreshInterval);
    }
    
    // 每 30 秒刷新工具包状态
    _toolboxRefreshInterval = setInterval(() => {
      if (document.getElementById('panel-toolchain-center')?.style.display !== 'none') {
        loadToolPackages();  // 静默刷新
      }
    }, 30000);
    
    // 监听 WebSocket 状态更新（如果有）
    if (window.ws && window.ws.addEventListener) {
      window.ws.addEventListener('tool_package_status', (data) => {
        loadToolPackages();
      });
    }
  }
  
  // 页面卸载时清理定时器
  window.addEventListener('beforeunload', () => {
    if (_toolboxRefreshInterval) {
      clearInterval(_toolboxRefreshInterval);
    }
  });

})();
