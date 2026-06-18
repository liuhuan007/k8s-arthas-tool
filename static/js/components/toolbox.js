/**
 * 工具箱组件 - 卡片布局 + 分发功能
 * 三类工具：二进制工具、脚本工具、快捷操作
 */
(function() {
  'use strict';

  window.renderToolbox = async function() {
    await Promise.all([
      loadBinaryTools(),
      loadScriptTools(),
      loadQuickActions()
    ]);
    initToolboxRealtimeRefresh();
  };

  // ═══════════════════════════════════════════════════════════════
  // 二进制工具
  // ═══════════════════════════════════════════════════════════════

  async function loadBinaryTools() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      renderBinaryToolCards(data.packages || []);
      updateSummary('statBinary', (data.packages || []).length);
    } catch (e) {
      console.error('加载二进制工具失败:', e);
    }
  }

  function renderBinaryToolCards(packages) {
    const container = document.getElementById('toolboxBinaryTools');
    if (!container) return;
    if (packages.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无二进制工具<br>点击"上传工具"添加</div>';
      return;
    }
    container.innerHTML = packages.map(p => {
      const sha = p.sha256 ? `${p.sha256.slice(0, 12)}...` : '未校验';
      const statusClass = p.status === 'active' ? 'running' : 'stopped';
      const statusText = p.status === 'active' ? '可用' : '停用';
      const displayName = p.file_name || p.name;
      return `
        <div class="toolbox-card toolbox-card-binary" data-id="${p.id}">
          <div class="toolbox-card-header">
            <div class="toolbox-card-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
            </div>
            <span class="toolbox-card-name">${esc(displayName)}</span>
            ${p.is_builtin ? '<span class="badge badge-low">内置</span>' : ''}
            <span class="badge ${statusClass}">${statusText}</span>
          </div>
          <div class="toolbox-card-meta">
            <span>类型 ${esc(p.tool_type)}</span>
            <span>版本 ${esc(p.version || '-')}</span>
            <span>SHA ${sha}</span>
          </div>
          <div class="toolbox-card-path">${esc(p.install_path || '-')}</div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="toolboxVerify(${p.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              校验
            </button>
            <button class="btn btn-p btn-sm" onclick="toolboxSingleDistribute(${p.id}, 'binary', '${esc(p.install_path || '')}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              分发
            </button>
            ${!p.is_builtin ? `<button class="btn btn-s btn-sm" onclick="toolboxDeleteBinary(${p.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              删除
            </button>` : ''}
          </div>
          <div class="toolbox-distribute-form" id="distForm-binary-${p.id}" style="display:none"></div>
        </div>
      `;
    }).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // 脚本工具
  // ═══════════════════════════════════════════════════════════════

  async function loadScriptTools() {
    try {
      const data = await safeGet('/tasks/script-tools');
      renderScriptToolCards(data.tools || []);
      updateSummary('statScript', (data.tools || []).length);
    } catch (e) {
      console.error('加载脚本工具失败:', e);
    }
  }

  function renderScriptToolCards(tools) {
    const container = document.getElementById('toolboxScriptTools');
    if (!container) return;
    if (tools.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无脚本工具<br>点击"+ 新建"添加</div>';
      return;
    }
    const runtimeIcons = {
      python: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
      shell: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
      node: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    };
    container.innerHTML = tools.map(t => {
      const icon = runtimeIcons[t.runtime] || '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
      return `
        <div class="toolbox-card toolbox-card-script" data-id="${t.id}">
          <div class="toolbox-card-header">
            <div class="toolbox-card-icon">${icon}</div>
            <span class="toolbox-card-name">${esc(t.name)}</span>
            <span class="badge badge-${t.risk_level || 'low'}">${riskText(t.risk_level)}</span>
          </div>
          <div class="toolbox-card-meta">
            <span>运行时 ${esc(t.runtime)}</span>
            ${t.capability_id ? '<span>关联诊断能力</span>' : ''}
          </div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="toolboxEditScript(${t.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              编辑
            </button>
            <button class="btn btn-p btn-sm" onclick="toolboxExecuteScript(${t.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              执行
            </button>
            <button class="btn btn-s btn-sm" onclick="toolboxDeleteScript(${t.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              删除
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // 快捷操作
  // ═══════════════════════════════════════════════════════════════

  async function loadQuickActions() {
    try {
      const data = await safeGet('/tasks/quick-actions');
      renderQuickActionCards(data.actions || []);
      updateSummary('statQuick', (data.actions || []).length);
    } catch (e) {
      console.error('加载快捷操作失败:', e);
    }
  }

  function renderQuickActionCards(actions) {
    const container = document.getElementById('toolboxQuickActions');
    if (!container) return;
    if (actions.length === 0) {
      container.innerHTML = '<div class="sb-empty">暂无快捷操作<br>点击"+ 新建"添加</div>';
      return;
    }
    container.innerHTML = actions.map(a => `
      <div class="toolbox-card toolbox-card-quick" data-id="${a.id}">
        <div class="toolbox-card-header">
          <div class="toolbox-card-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          </div>
          <span class="toolbox-card-name">${esc(a.name)}</span>
          <span class="badge badge-${a.risk_level || 'low'}">${riskText(a.risk_level)}</span>
        </div>
        <div class="toolbox-card-meta"><span>${esc(a.category || '通用')}</span></div>
        <div class="toolbox-card-command"><code>${esc(a.command_template)}</code></div>
        <div class="toolbox-card-actions">
          <button class="btn btn-p btn-sm" onclick="toolboxExecuteQuick(${a.id})">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            执行
          </button>
          ${a.arthas_doc_url ? `<a href="${esc(a.arthas_doc_url)}" target="_blank" class="btn btn-g btn-sm">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            文档
          </a>` : ''}
        </div>
      </div>
    `).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // 新建/上传弹窗
  // ═══════════════════════════════════════════════════════════════

  function _openModal(title, bodyHtml, footerHtml) {
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.innerHTML = `
      <div class="capability-modal" style="max-width:560px">
        <div class="modal-header">
          <h3>${title}</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:20px">${bodyHtml}</div>
        ${footerHtml ? `<div class="modal-footer" style="padding:16px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:flex-end;gap:8px">${footerHtml}</div>` : ''}
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    return modal;
  }

  window.toolboxUploadBinary = function() {
    const body = `
      <div style="display:flex;flex-direction:column;gap:12px">
        <div><label class="fl">工具名称</label><input id="tbUpName" class="inp" placeholder="例如：arthas-boot-3.7.2"></div>
        <div><label class="fl">工具类型</label><select id="tbUpType" class="inp"><option value="arthas">Arthas</option><option value="async-profiler">async-profiler</option><option value="generic">通用</option></select></div>
        <div><label class="fl">版本</label><input id="tbUpVer" class="inp" placeholder="可选"></div>
        <div><label class="fl">安装路径</label><input id="tbUpPath" class="inp" value="/tmp/arthas/arthas-boot.jar"></div>
        <div><label class="fl">说明</label><input id="tbUpDesc" class="inp" placeholder="可选"></div>
        <div>
          <label class="fl">二进制文件</label>
          <div class="toolchain-file-picker">
            <input id="tbUpFile" class="inp toolchain-file-input" type="file" onchange="document.getElementById('tbUpFileName').textContent=this.files?.[0]?.name||'未选择文件'">
            <button class="btn btn-g" type="button" onclick="document.getElementById('tbUpFile')?.click()">选择文件</button>
            <span id="tbUpFileName">未选择文件</span>
          </div>
        </div>
      </div>
    `;
    const footer = `
      <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
      <button class="btn btn-p" id="tbUpSubmitBtn">上传并登记</button>
    `;
    const modal = _openModal('上传二进制工具', body, footer);
    modal.querySelector('#tbUpSubmitBtn').onclick = async () => {
      const fileEl = modal.querySelector('#tbUpFile');
      const file = fileEl?.files?.[0];
      if (!file) { toast('请选择文件', 'warn'); return; }
      const form = new FormData();
      form.append('file', file);
      form.append('name', modal.querySelector('#tbUpName')?.value?.trim() || file.name);
      form.append('tool_type', modal.querySelector('#tbUpType')?.value || 'arthas');
      form.append('version', modal.querySelector('#tbUpVer')?.value?.trim() || '');
      form.append('install_path', modal.querySelector('#tbUpPath')?.value?.trim() || '/tmp/arthas/arthas-boot.jar');
      form.append('description', modal.querySelector('#tbUpDesc')?.value?.trim() || '');
      try {
        await safeUploadToolPackage('/tasks/tool-packages/upload', form, 300000);
        toast('工具已上传', 'ok');
        modal.remove();
        loadBinaryTools();
      } catch (e) { toast(`上传失败：${e.message}`, 'err'); }
    };
  };

  window.toolboxCreateScript = function() {
    const body = `
      <div style="display:flex;flex-direction:column;gap:12px">
        <div><label class="fl">脚本名称</label><input id="tbScrName" class="inp" placeholder="例如：GC日志分析"></div>
        <div><label class="fl">运行时</label><select id="tbScrRuntime" class="inp"><option value="python">Python</option><option value="shell">Shell</option><option value="node">Node.js</option></select></div>
        <div><label class="fl">风险等级</label><select id="tbScrRisk" class="inp"><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option></select></div>
        <div><label class="fl">说明</label><input id="tbScrDesc" class="inp" placeholder="可选"></div>
        <div><label class="fl">脚本内容</label><textarea id="tbScrBody" class="inp" rows="8" placeholder="#!/usr/bin/env python\nimport sys\n..." style="font-family:monospace;font-size:12px;resize:vertical"></textarea></div>
      </div>
    `;
    const footer = `
      <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
      <button class="btn btn-p" id="tbScrSubmitBtn">创建</button>
    `;
    const modal = _openModal('新建脚本工具', body, footer);
    modal.querySelector('#tbScrSubmitBtn').onclick = async () => {
      const name = modal.querySelector('#tbScrName')?.value?.trim();
      const script_body = modal.querySelector('#tbScrBody')?.value?.trim();
      if (!name) { toast('请填写脚本名称', 'warn'); return; }
      if (!script_body) { toast('请填写脚本内容', 'warn'); return; }
      try {
        await safePost('/tasks/script-tools', {
          name,
          runtime: modal.querySelector('#tbScrRuntime')?.value || 'python',
          risk_level: modal.querySelector('#tbScrRisk')?.value || 'low',
          description: modal.querySelector('#tbScrDesc')?.value?.trim() || '',
          script_body,
        });
        toast('脚本工具已创建', 'ok');
        modal.remove();
        loadScriptTools();
      } catch (e) { toast(`创建失败：${e.message}`, 'err'); }
    };
  };

  window.toolboxCreateQuick = function() {
    const body = `
      <div style="display:flex;flex-direction:column;gap:12px">
        <div><label class="fl">操作名称</label><input id="tbQkName" class="inp" placeholder="例如：查看线程堆栈"></div>
        <div><label class="fl">分类</label><input id="tbQkCat" class="inp" placeholder="例如：诊断、GC、线程"></div>
        <div><label class="fl">风险等级</label><select id="tbQkRisk" class="inp"><option value="low">低风险</option><option value="medium">中风险</option><option value="high">高风险</option></select></div>
        <div><label class="fl">说明</label><input id="tbQkDesc" class="inp" placeholder="可选"></div>
        <div><label class="fl">命令模板</label><textarea id="tbQkCmd" class="inp" rows="4" placeholder="thread -n 3" style="font-family:monospace;font-size:12px;resize:vertical"></textarea></div>
        <div><label class="fl">Arthas 文档链接</label><input id="tbQkUrl" class="inp" placeholder="可选，https://arthas.aliyun.com/..."></div>
      </div>
    `;
    const footer = `
      <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
      <button class="btn btn-p" id="tbQkSubmitBtn">创建</button>
    `;
    const modal = _openModal('新建快捷操作', body, footer);
    modal.querySelector('#tbQkSubmitBtn').onclick = async () => {
      const name = modal.querySelector('#tbQkName')?.value?.trim();
      const command_template = modal.querySelector('#tbQkCmd')?.value?.trim();
      if (!name) { toast('请填写操作名称', 'warn'); return; }
      if (!command_template) { toast('请填写命令模板', 'warn'); return; }
      try {
        await safePost('/tasks/quick-actions', {
          name,
          category: modal.querySelector('#tbQkCat')?.value?.trim() || '',
          risk_level: modal.querySelector('#tbQkRisk')?.value || 'low',
          description: modal.querySelector('#tbQkDesc')?.value?.trim() || '',
          command_template,
          arthas_doc_url: modal.querySelector('#tbQkUrl')?.value?.trim() || '',
        });
        toast('快捷操作已创建', 'ok');
        modal.remove();
        loadQuickActions();
      } catch (e) { toast(`创建失败：${e.message}`, 'err'); }
    };
  };

  // ═══════════════════════════════════════════════════════════════
  // 单个分发
  // ═══════════════════════════════════════════════════════════════

  let _distClusterCache = null;

  async function _loadDistClusters() {
    if (_distClusterCache) return _distClusterCache;
    try {
      const data = await safeGet('/clusters');
      _distClusterCache = data.clusters || [];
    } catch (e) { _distClusterCache = []; }
    return _distClusterCache;
  }

  window.toolboxSingleDistribute = async function(toolId, toolType, defaultPath) {
    const formId = `distForm-${toolType}-${toolId}`;
    const form = document.getElementById(formId);
    if (!form) return;
    if (form.style.display !== 'none') {
      form.style.display = 'none';
      return;
    }
    const conn = window.getCurrentConnection ? window.getCurrentConnection() : {};
    const clusters = await _loadDistClusters();
    const clusterOptions = clusters.map(c =>
      `<option value="${esc(c.name)}" ${c.name === conn.cluster ? 'selected' : ''}>${esc(c.name)}</option>`
    ).join('');

    form.innerHTML = `
      <div class="dist-form-inner">
        <div class="dist-form-title">分发工具</div>
        <div class="dist-form targetType-bar">
          <button class="btn btn-sm dist-type-btn active" data-type="pod" onclick="distToggleType(${toolId}, 'pod', '${toolType}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
            分发到 Pod
          </button>
          <button class="btn btn-sm dist-type-btn" data-type="node" onclick="distToggleType(${toolId}, 'node', '${toolType}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/><line x1="10" y1="6" x2="14" y2="6"/><line x1="10" y1="18" x2="14" y2="18"/></svg>
            分发到 Node
          </button>
        </div>
        <div id="distTargetPod-${toolId}">
          <div class="dist-form-row">
            <label>集群</label>
            <select id="dist-cluster-${toolId}" class="inp" onchange="distOnClusterChange(${toolId})">
              <option value="">选择集群</option>
              ${clusterOptions}
            </select>
          </div>
          <div class="dist-form-row">
            <label>Namespace</label>
            <select id="dist-ns-${toolId}" class="inp" onchange="distOnNsChange(${toolId})">
              <option value="">加载中...</option>
            </select>
          </div>
          <div class="dist-form-row">
            <label>Pod</label>
            <select id="dist-pod-${toolId}" class="inp">
              <option value="">先选择集群和 Namespace</option>
            </select>
          </div>
          <div class="dist-form-row">
            <label>容器</label>
            <select id="dist-ctr-${toolId}" class="inp">
              <option value="">默认容器</option>
            </select>
          </div>
        </div>
        <div id="distTargetNode-${toolId}" style="display:none">
          <div class="dist-form-row">
            <label>集群</label>
            <select id="dist-node-cluster-${toolId}" class="inp">
              <option value="">选择集群</option>
              ${clusterOptions}
            </select>
          </div>
          <div class="dist-form-row">
            <label>Node</label>
            <input id="dist-node-${toolId}" class="inp" placeholder="Node 名称（如 node-1）">
          </div>
          <div class="dist-form-hint">Node 分发通过 kubectl debug 临时容器执行，需要集群 RBAC 权限。</div>
        </div>
        <div class="dist-form-row">
          <label>安装路径</label>
          <input id="dist-path-${toolId}" class="inp" value="${esc(defaultPath || '/tmp/arthas/arthas-boot.jar')}">
        </div>
        <div class="dist-form-actions">
          <button class="btn btn-p btn-sm" onclick="toolboxConfirmDistribute(${toolId}, '${toolType}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            确认分发
          </button>
          <button class="btn btn-g btn-sm" onclick="document.getElementById('${formId}').style.display='none'">取消</button>
        </div>
        <div id="dist-progress-${toolId}" style="display:none;margin-top:8px"></div>
      </div>
    `;
    form.style.display = 'block';
    if (conn.cluster) distOnClusterChange(toolId);
  };

  window.distToggleType = function(toolId, type, toolType) {
    const bar = document.querySelector(`#distForm-${toolType}-${toolId} .targetType-bar`);
    if (!bar) return;
    bar.querySelectorAll('.dist-type-btn').forEach(b => b.classList.toggle('active', b.dataset.type === type));
    const podDiv = document.getElementById(`distTargetPod-${toolId}`);
    const nodeDiv = document.getElementById(`distTargetNode-${toolId}`);
    if (podDiv) podDiv.style.display = type === 'pod' ? 'block' : 'none';
    if (nodeDiv) nodeDiv.style.display = type === 'node' ? 'block' : 'none';
  };

  window.distOnClusterChange = async function(toolId) {
    const clusterName = document.getElementById(`dist-cluster-${toolId}`)?.value;
    const nsSelect = document.getElementById(`dist-ns-${toolId}`);
    if (!clusterName || !nsSelect) return;
    nsSelect.innerHTML = '<option value="">加载中...</option>';
    try {
      const nsData = await safeGet(`/clusters/${encodeURIComponent(clusterName)}/namespaces`);
      const namespaces = nsData.namespaces || ['default'];
      nsSelect.innerHTML = namespaces.map(ns =>
        `<option value="${esc(ns)}">${esc(ns)}</option>`
      ).join('');
      distOnNsChange(toolId);
    } catch (e) {
      nsSelect.innerHTML = '<option value="default">default</option>';
    }
  };

  window.distOnNsChange = async function(toolId) {
    const clusterName = document.getElementById(`dist-cluster-${toolId}`)?.value;
    const ns = document.getElementById(`dist-ns-${toolId}`)?.value;
    const podSelect = document.getElementById(`dist-pod-${toolId}`);
    const ctrSelect = document.getElementById(`dist-ctr-${toolId}`);
    if (!clusterName || !ns || !podSelect) return;
    podSelect.innerHTML = '<option value="">加载中...</option>';
    try {
      const podsData = await safeGet(`/clusters/${encodeURIComponent(clusterName)}/pods?namespace=${encodeURIComponent(ns)}`);
      const pods = podsData.pods || [];
      podSelect.innerHTML = '<option value="">选择 Pod</option>' +
        pods.map(p => {
          const ctrs = (p.containers || []).join(',');
          return `<option value="${esc(p.name)}" data-c="${esc(ctrs)}" data-phase="${esc(p.phase || '')}">${esc(p.name)} [${esc(p.phase || '')}]</option>`;
        }).join('');
      podSelect.onchange = function() {
        const opt = podSelect.options[podSelect.selectedIndex];
        const ctrs = (opt?.dataset.c || '').split(',').filter(Boolean);
        if (ctrSelect) {
          ctrSelect.innerHTML = '<option value="">默认容器</option>' + ctrs.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
          if (ctrs.length === 1) ctrSelect.value = ctrs[0];
        }
      };
      podSelect.onchange();
    } catch (e) {
      podSelect.innerHTML = '<option value="">加载失败</option>';
    }
  };

  window.toolboxConfirmDistribute = async function(toolId, toolType) {
    const formId = `distForm-${toolType}-${toolId}`;
    const activeType = document.querySelector(`#${formId} .dist-type-btn.active`)?.dataset.type || 'pod';
    const path = document.getElementById(`dist-path-${toolId}`)?.value || '/tmp/arthas/arthas-boot.jar';
    let payload;
    if (activeType === 'node') {
      const cluster = document.getElementById(`dist-node-cluster-${toolId}`)?.value || '';
      const node = document.getElementById(`dist-node-${toolId}`)?.value || '';
      if (!cluster) { toast('请选择集群', 'warn'); return; }
      if (!node) { toast('请输入 Node 名称', 'warn'); return; }
      payload = { tool_id: toolId, cluster, node, install_path: path, target_type: 'node' };
    } else {
      const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value || '';
      const ns = document.getElementById(`dist-ns-${toolId}`)?.value || 'default';
      const pod = document.getElementById(`dist-pod-${toolId}`)?.value || '';
      const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value || '';
      if (!cluster) { toast('请选择集群', 'warn'); return; }
      if (!pod) { toast('请选择 Pod', 'warn'); return; }
      payload = { tool_id: toolId, cluster, namespace: ns, pod, container: ctr, install_path: path };
    }
    const progressEl = document.getElementById(`dist-progress-${toolId}`);
    if (progressEl) {
      progressEl.style.display = 'block';
      progressEl.innerHTML = '<div class="batch-progress-bar"><div class="batch-progress-fill" style="width:60%"></div></div><span style="font-size:12px;color:var(--tx2)">分发中...</span>';
    }
    try {
      await safePost('/tasks/distribute', payload);
      if (progressEl) progressEl.innerHTML = '<div style="display:flex;align-items:center;gap:6px;color:var(--a3);font-size:12px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 分发成功</div>';
      toast('分发成功', 'ok');
    } catch (e) {
      if (progressEl) progressEl.innerHTML = `<div style="display:flex;align-items:center;gap:6px;color:var(--a5);font-size:12px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ${esc(e.message)}</div>`;
      toast(`分发失败：${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 批量分发浮层
  // ═══════════════════════════════════════════════════════════════

  window.toolboxOpenBatchDistribute = function() {
    _batchState = { step: 1, selectedTools: [], selectedPods: [] };
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.id = 'batchDistModal';
    modal.innerHTML = `
      <div class="capability-modal" style="max-width:720px">
        <div class="modal-header">
          <h3>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
            批量分发工具
          </h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:24px">
          <div class="batch-wizard-steps" id="batchWizardSteps">
            <div class="batch-step-indicator active" data-step="1">
              <div class="batch-step-dot">1</div>
              <span class="batch-step-label">选择工具</span>
            </div>
            <div class="batch-step-line"></div>
            <div class="batch-step-indicator" data-step="2">
              <div class="batch-step-dot">2</div>
              <span class="batch-step-label">选择 Pod</span>
            </div>
            <div class="batch-step-line"></div>
            <div class="batch-step-indicator" data-step="3">
              <div class="batch-step-dot">3</div>
              <span class="batch-step-label">确认分发</span>
            </div>
          </div>
          <div id="batchStep1">
            <div id="batchToolList" class="batch-tool-list">加载中...</div>
          </div>
          <div id="batchStep2" style="display:none">
            <div class="batch-filter-bar">
              <button class="btn btn-g btn-sm active-filter" onclick="batchFilterPods('all')" id="batchFilterAll">全部</button>
              <button class="btn btn-g btn-sm" onclick="batchFilterPods('java')" id="batchFilterJava">仅 Java Pod</button>
            </div>
            <div id="batchPodList" class="batch-pod-list">加载中...</div>
          </div>
          <div id="batchStep3" style="display:none">
            <div id="batchSummary"></div>
            <div id="batchProgress" style="margin-top:16px"></div>
          </div>
        </div>
        <div class="modal-footer" style="padding:16px 24px;border-top:1px solid rgba(40,61,90,.5);display:flex;justify-content:flex-end;gap:10px">
          <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
          <button class="btn btn-p" id="batchNextBtn" onclick="batchNextStep()">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            下一步
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    loadBatchToolList();
  };

  let _batchState = { step: 1, selectedTools: [], selectedPods: [] };

  async function loadBatchToolList() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      const packages = data.packages || [];
      const container = document.getElementById('batchToolList');
      if (!container) return;
      container.innerHTML = packages.map(p => {
        const toolDisplayName = p.file_name || p.name;
        return `
        <label class="batch-item">
          <input type="checkbox" value="${p.id}" data-name="${esc(toolDisplayName)}" data-path="${esc(p.install_path || '')}" onchange="batchUpdateTools()">
          <span class="batch-item-name">${esc(toolDisplayName)}</span>
          <span class="batch-item-meta">${esc(p.tool_type)} · ${esc(p.version || '-')}</span>
        </label>
      `}).join('');
    } catch (e) {
      console.error('加载工具列表失败:', e);
    }
  }

  window.batchUpdateTools = function() {
    const checkboxes = document.querySelectorAll('#batchToolList input[type=checkbox]:checked');
    _batchState.selectedTools = Array.from(checkboxes).map(cb => ({
      id: parseInt(cb.value),
      name: cb.dataset.name,
      install_path: cb.dataset.path,
    }));
  };

  function _updateBatchStepIndicator(step) {
    const indicators = document.querySelectorAll('#batchWizardSteps .batch-step-indicator');
    const lines = document.querySelectorAll('#batchWizardSteps .batch-step-line');
    indicators.forEach((el, i) => {
      const s = i + 1;
      el.classList.remove('active', 'done');
      if (s < step) el.classList.add('done');
      else if (s === step) el.classList.add('active');
    });
    lines.forEach((el, i) => {
      el.classList.toggle('done', i + 1 < step);
    });
  }

  window.batchNextStep = function() {
    if (_batchState.step === 1) {
      if (_batchState.selectedTools.length === 0) { toast('请选择至少一个工具', 'warn'); return; }
      _batchState.step = 2;
      document.getElementById('batchStep1').style.display = 'none';
      document.getElementById('batchStep2').style.display = 'block';
      _updateBatchStepIndicator(2);
      loadBatchPodList();
    } else if (_batchState.step === 2) {
      if (_batchState.selectedPods.length === 0) { toast('请选择至少一个 Pod', 'warn'); return; }
      _batchState.step = 3;
      document.getElementById('batchStep2').style.display = 'none';
      document.getElementById('batchStep3').style.display = 'block';
      _updateBatchStepIndicator(3);
      renderBatchSummary();
      document.getElementById('batchNextBtn').innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> 确认分发';
      document.getElementById('batchNextBtn').onclick = batchExecute;
    }
  };

  let _batchPodData = [];

  async function loadBatchPodList() {
    try {
      const data = await safeGet('/clusters');
      const clusters = data.clusters || [];
      const container = document.getElementById('batchPodList');
      if (!container) return;
      container.innerHTML = '<div class="sb-empty">加载中...</div>';
      _batchPodData = [];
      for (const c of clusters) {
        let namespaces = ['default'];
        try {
          const nsData = await safeGet(`/clusters/${c.name}/namespaces`);
          if (nsData.namespaces && nsData.namespaces.length) namespaces = nsData.namespaces;
        } catch (e) { /* use default */ }
        for (const ns of namespaces) {
          try {
            const podsData = await safeGet(`/clusters/${c.name}/pods?namespace=${encodeURIComponent(ns)}`);
            const pods = podsData.pods || [];
            for (const pod of pods) {
              _batchPodData.push({
                cluster: c.name,
                namespace: ns,
                pod: pod.name,
                phase: pod.phase || '',
              });
            }
          } catch (e) { /* skip namespace */ }
        }
      }
      _renderBatchPodList(_batchPodData);
    } catch (e) {
      console.error('加载 Pod 列表失败:', e);
    }
  }

  function _renderBatchPodList(pods) {
    const container = document.getElementById('batchPodList');
    if (!container) return;
    if (pods.length === 0) {
      container.innerHTML = '<div class="sb-empty">无可用 Pod</div>';
      return;
    }
    container.innerHTML = pods.map(p => `
      <label class="batch-item">
        <input type="checkbox" value="${esc(p.cluster)}:${esc(p.namespace)}:${esc(p.pod)}" onchange="batchUpdatePods()">
        <span class="batch-item-name">${esc(p.pod)}</span>
        <span class="batch-item-meta">${esc(p.cluster)}/${esc(p.namespace)} · ${esc(p.phase)}</span>
      </label>
    `).join('');
  }

  window.batchFilterPods = function(filter) {
    document.getElementById('batchFilterAll')?.classList.toggle('active-filter', filter === 'all');
    document.getElementById('batchFilterJava')?.classList.toggle('active-filter', filter === 'java');
    if (filter === 'java') {
      _renderBatchPodList(_batchPodData.filter(p => /java|jvm|jdk|jre/i.test(p.pod)));
    } else {
      _renderBatchPodList(_batchPodData);
    }
  };

  window.batchUpdatePods = function() {
    const checkboxes = document.querySelectorAll('#batchPodList input[type=checkbox]:checked');
    _batchState.selectedPods = Array.from(checkboxes).map(cb => {
      const [cluster, namespace, pod] = cb.value.split(':');
      return { cluster, namespace, pod };
    });
  };

  function renderBatchSummary() {
    const el = document.getElementById('batchSummary');
    if (!el) return;
    const toolCount = _batchState.selectedTools.length;
    const podCount = _batchState.selectedPods.length;
    const total = toolCount * podCount;
    el.innerHTML = `
      <div class="batch-summary-card">
        <div class="batch-summary-stat">
          <div class="num">${toolCount}</div>
          <div class="label">工具</div>
        </div>
        <div class="batch-summary-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </div>
        <div class="batch-summary-stat">
          <div class="num">${podCount}</div>
          <div class="label">Pod</div>
        </div>
        <div class="batch-summary-icon">=</div>
        <div class="batch-summary-stat">
          <div class="num">${total}</div>
          <div class="label">次分发</div>
        </div>
      </div>
    `;
  }

  window.batchExecute = async function() {
    const btn = document.getElementById('batchNextBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin"><circle cx="12" cy="12" r="10"/></svg> 分发中...'; }
    const progressEl = document.getElementById('batchProgress');
    if (progressEl) progressEl.innerHTML = '<div class="batch-progress-bar"><div class="batch-progress-fill" style="width:30%"></div></div>';
    try {
      const result = await safePost('/tasks/batch-distribute', {
        tool_ids: _batchState.selectedTools.map(t => t.id),
        tool_type: 'binary',
        targets: _batchState.selectedPods,
        install_path: _batchState.selectedTools[0]?.install_path || '/tmp/arthas/arthas-boot.jar',
      });
      if (progressEl) {
        const summary = result.summary || {};
        progressEl.innerHTML = `
          <div class="batch-result">
            <div class="batch-result-header">
              <span class="batch-result-badge ok">✓ 成功 ${summary.success || 0}</span>
              <span class="batch-result-badge fail">✕ 失败 ${summary.failed || 0}</span>
            </div>
            <div class="batch-result-list">
              ${(result.results || []).map(r => `
                <div class="batch-result-item ${r.status}">
                  ${r.status === 'success'
                    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
                    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'}
                  <span>${esc(r.tool)} → ${esc(r.pod)}</span>
                  ${r.error ? `<span class="batch-error">${esc(r.error)}</span>` : ''}
                  ${r.duration_ms ? `<span class="batch-duration">${r.duration_ms}ms</span>` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }
      toast('批量分发完成', 'ok');
    } catch (e) {
      if (progressEl) progressEl.innerHTML = `<div style="display:flex;align-items:center;gap:6px;color:var(--a5);font-size:13px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ${esc(e.message)}</div>`;
      toast(`批量分发失败：${e.message}`, 'err');
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> 确认分发'; }
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 工具操作
  // ═══════════════════════════════════════════════════════════════

  window.toolboxVerify = async function(id) {
    try {
      await safePost(`/tasks/tool-packages/${id}/verify`);
      toast('校验完成', 'ok');
      loadBinaryTools();
    } catch (e) { toast(`校验失败：${e.message}`, 'err'); }
  };

  window.toolboxDeleteBinary = async function(id) {
    if (!confirm('确认删除此工具包？')) return;
    try {
      await safeDelete(`/tasks/tool-packages/${id}`);
      toast('已删除', 'ok');
      loadBinaryTools();
    } catch (e) { toast(`删除失败：${e.message}`, 'err'); }
  };

  window.toolboxDeleteScript = async function(id) {
    if (!confirm('确认删除此脚本工具？')) return;
    try {
      await safeDelete(`/tasks/script-tools/${id}`);
      toast('已删除', 'ok');
      loadScriptTools();
    } catch (e) { toast(`删除失败：${e.message}`, 'err'); }
  };

  // ═══════════════════════════════════════════════════════════════
  // 工具函数
  // ═══════════════════════════════════════════════════════════════

  function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function riskText(level) {
    return { low: '低风险', medium: '中风险', high: '高风险' }[level] || '低风险';
  }

  function updateSummary(elId, count) {
    const el = document.getElementById(elId);
    if (el) el.textContent = count;
  }

  // ═══════════════════════════════════════════════════════════════
  // 实时刷新
  // ═══════════════════════════════════════════════════════════════

  let _refreshInterval = null;

  function initToolboxRealtimeRefresh() {
    if (_refreshInterval) clearInterval(_refreshInterval);
    _refreshInterval = setInterval(() => {
      const panel = document.getElementById('panel-toolchain-center');
      if (panel && panel.style.display !== 'none') {
        loadBinaryTools();
      }
    }, 30000);
  }

  window.addEventListener('beforeunload', () => {
    if (_refreshInterval) clearInterval(_refreshInterval);
  });

})();