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
            <span class="toolbox-card-icon">📦</span>
            <span class="toolbox-card-name">${esc(displayName)}</span>
            ${p.is_builtin ? '<span class="badge badge-low">内置</span>' : ''}
            <span class="badge ${statusClass}">${statusText}</span>
          </div>
          <div class="toolbox-card-meta">
            类型：${esc(p.tool_type)} · 版本：${esc(p.version || '-')} · SHA：${sha}
          </div>
          <div class="toolbox-card-path">${esc(p.install_path || '-')}</div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="toolboxVerify(${p.id})">校验</button>
            <button class="btn btn-p btn-sm" onclick="toolboxSingleDistribute(${p.id}, 'binary', '${esc(p.install_path || '')}')">分发→</button>
            ${!p.is_builtin ? `<button class="btn btn-g btn-sm danger-text" onclick="toolboxDeleteBinary(${p.id})">删除</button>` : ''}
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
    container.innerHTML = tools.map(t => {
      const runtimeIcon = { python: '🐍', shell: '⚙️', node: '🟢' }[t.runtime] || '📄';
      return `
        <div class="toolbox-card toolbox-card-script" data-id="${t.id}">
          <div class="toolbox-card-header">
            <span class="toolbox-card-icon">${runtimeIcon}</span>
            <span class="toolbox-card-name">${esc(t.name)}</span>
            <span class="badge badge-${t.risk_level || 'low'}">${riskText(t.risk_level)}</span>
          </div>
          <div class="toolbox-card-meta">
            运行时：${esc(t.runtime)}${t.capability_id ? ' · 关联诊断能力' : ''}
          </div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="toolboxEditScript(${t.id})">编辑</button>
            <button class="btn btn-p btn-sm" onclick="toolboxExecuteScript(${t.id})">执行→</button>
            <button class="btn btn-g btn-sm danger-text" onclick="toolboxDeleteScript(${t.id})">删除</button>
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
          <span class="toolbox-card-icon">⚡</span>
          <span class="toolbox-card-name">${esc(a.name)}</span>
          <span class="badge badge-${a.risk_level || 'low'}">${riskText(a.risk_level)}</span>
        </div>
        <div class="toolbox-card-meta">${esc(a.category || '通用')}</div>
        <div class="toolbox-card-command"><code>${esc(a.command_template)}</code></div>
        <div class="toolbox-card-actions">
          <button class="btn btn-p btn-sm" onclick="toolboxExecuteQuick(${a.id})">执行→</button>
          ${a.arthas_doc_url ? `<a href="${esc(a.arthas_doc_url)}" target="_blank" class="btn btn-g btn-sm">文档</a>` : ''}
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

  window.toolboxSingleDistribute = function(toolId, toolType, defaultPath) {
    const formId = `distForm-${toolType}-${toolId}`;
    const form = document.getElementById(formId);
    if (!form) return;
    if (form.style.display !== 'none') {
      form.style.display = 'none';
      return;
    }
    const conn = window.getCurrentConnection ? window.getCurrentConnection() : {};
    form.innerHTML = `
      <div class="dist-form-inner">
        <div class="dist-form-title">分发到 Pod</div>
        <div class="dist-form-row">
          <label>集群</label>
          <input id="dist-cluster-${toolId}" class="inp" value="${esc(conn.cluster || '')}">
        </div>
        <div class="dist-form-row">
          <label>Namespace</label>
          <input id="dist-ns-${toolId}" class="inp" value="${esc(conn.namespace || 'default')}">
        </div>
        <div class="dist-form-row">
          <label>Pod</label>
          <input id="dist-pod-${toolId}" class="inp" value="${esc(conn.pod || '')}">
        </div>
        <div class="dist-form-row">
          <label>容器</label>
          <input id="dist-ctr-${toolId}" class="inp" placeholder="可选">
        </div>
        <div class="dist-form-row">
          <label>安装路径</label>
          <input id="dist-path-${toolId}" class="inp" value="${esc(defaultPath || '/tmp/arthas/arthas-boot.jar')}">
        </div>
        <div class="dist-form-actions">
          <button class="btn btn-p btn-sm" onclick="toolboxConfirmDistribute(${toolId}, '${toolType}')">确认分发</button>
          <button class="btn btn-g btn-sm" onclick="document.getElementById('${formId}').style.display='none'">取消</button>
        </div>
        <div id="dist-progress-${toolId}" style="display:none;margin-top:8px"></div>
      </div>
    `;
    form.style.display = 'block';
  };

  window.toolboxConfirmDistribute = async function(toolId, toolType) {
    const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value || '';
    const ns = document.getElementById(`dist-ns-${toolId}`)?.value || 'default';
    const pod = document.getElementById(`dist-pod-${toolId}`)?.value || '';
    const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value || '';
    const path = document.getElementById(`dist-path-${toolId}`)?.value || '/tmp/arthas/arthas-boot.jar';
    if (!pod) { toast('请输入 Pod 名称', 'warn'); return; }
    const progressEl = document.getElementById(`dist-progress-${toolId}`);
    if (progressEl) {
      progressEl.style.display = 'block';
      progressEl.innerHTML = '<span class="spinner"></span> 分发中...';
    }
    try {
      await safePost('/tasks/distribute', {
        tool_id: toolId, cluster, namespace: ns, pod, container: ctr, install_path: path
      });
      if (progressEl) progressEl.innerHTML = '<span style="color:var(--green)">✅ 分发成功</span>';
      toast('分发成功', 'ok');
    } catch (e) {
      if (progressEl) progressEl.innerHTML = `<span style="color:var(--red)">❌ ${esc(e.message)}</span>`;
      toast(`分发失败：${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 批量分发浮层
  // ═══════════════════════════════════════════════════════════════

  window.toolboxOpenBatchDistribute = function() {
    const modal = document.createElement('div');
    modal.className = 'capability-modal-overlay';
    modal.id = 'batchDistModal';
    modal.innerHTML = `
      <div class="capability-modal" style="max-width:700px">
        <div class="modal-header">
          <h3>批量分发工具</h3>
          <button class="btn-close" onclick="this.closest('.capability-modal-overlay').remove()">✕</button>
        </div>
        <div class="modal-body" style="padding:20px">
          <div id="batchStep1">
            <h4 style="margin-bottom:12px">Step 1: 选择工具包</h4>
            <div id="batchToolList" class="batch-tool-list">加载中...</div>
          </div>
          <div id="batchStep2" style="display:none;margin-top:20px">
            <h4 style="margin-bottom:12px">Step 2: 选择目标 Pod</h4>
            <div class="batch-filter-bar">
              <button class="btn btn-g btn-sm" onclick="batchFilterPods('all')">全部</button>
              <button class="btn btn-g btn-sm" onclick="batchFilterPods('java')">仅 Java Pod</button>
            </div>
            <div id="batchPodList" class="batch-pod-list">加载中...</div>
          </div>
          <div id="batchStep3" style="display:none;margin-top:20px">
            <h4 style="margin-bottom:12px">Step 3: 确认分发</h4>
            <div id="batchSummary"></div>
            <div id="batchProgress" style="margin-top:12px"></div>
          </div>
        </div>
        <div class="modal-footer" style="padding:16px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:flex-end;gap:8px">
          <button class="btn btn-g" onclick="this.closest('.capability-modal-overlay').remove()">取消</button>
          <button class="btn btn-p" id="batchNextBtn" onclick="batchNextStep()">下一步</button>
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
      container.innerHTML = packages.map(p => `
        <label class="batch-item">
          <input type="checkbox" value="${p.id}" data-name="${esc(p.name)}" data-path="${esc(p.install_path || '')}" onchange="batchUpdateTools()">
          <span>${esc(p.name)}</span>
          <span class="batch-item-meta">${esc(p.tool_type)} · ${esc(p.version || '-')}</span>
        </label>
      `).join('');
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

  window.batchNextStep = function() {
    if (_batchState.step === 1) {
      if (_batchState.selectedTools.length === 0) { toast('请选择至少一个工具', 'warn'); return; }
      _batchState.step = 2;
      document.getElementById('batchStep1').style.display = 'none';
      document.getElementById('batchStep2').style.display = 'block';
      loadBatchPodList();
    } else if (_batchState.step === 2) {
      if (_batchState.selectedPods.length === 0) { toast('请选择至少一个 Pod', 'warn'); return; }
      _batchState.step = 3;
      document.getElementById('batchStep2').style.display = 'none';
      document.getElementById('batchStep3').style.display = 'block';
      renderBatchSummary();
      document.getElementById('batchNextBtn').textContent = '确认分发';
      document.getElementById('batchNextBtn').onclick = batchExecute;
    }
  };

  async function loadBatchPodList() {
    try {
      const data = await safeGet('/clusters');
      const clusters = data.clusters || [];
      const container = document.getElementById('batchPodList');
      if (!container) return;
      let html = '';
      for (const c of clusters) {
        try {
          const podsData = await safeGet(`/clusters/${c.name}/pods`);
          const pods = podsData.pods || [];
          for (const pod of pods) {
            html += `
              <label class="batch-item">
                <input type="checkbox" value="${esc(c.name)}:${esc(pod.namespace)}:${esc(pod.name)}" onchange="batchUpdatePods()">
                <span>${esc(pod.name)}</span>
                <span class="batch-item-meta">${esc(c.name)}/${esc(pod.namespace)} · ${esc(pod.status)}</span>
              </label>
            `;
          }
        } catch (e) { /* skip cluster */ }
      }
      container.innerHTML = html || '<div class="sb-empty">无可用 Pod</div>';
    } catch (e) {
      console.error('加载 Pod 列表失败:', e);
    }
  }

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
    const total = _batchState.selectedTools.length * _batchState.selectedPods.length;
    el.innerHTML = `<p>将 <strong>${_batchState.selectedTools.length}</strong> 个工具分发到 <strong>${_batchState.selectedPods.length}</strong> 个 Pod (共 <strong>${total}</strong> 次分发操作)</p>`;
  }

  window.batchExecute = async function() {
    const btn = document.getElementById('batchNextBtn');
    if (btn) btn.disabled = true;
    const progressEl = document.getElementById('batchProgress');
    if (progressEl) progressEl.innerHTML = '<span class="spinner"></span> 分发中...';
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
            <p>✅ 成功: ${summary.success || 0} | ❌ 失败: ${summary.failed || 0}</p>
            ${(result.results || []).map(r => `
              <div class="batch-result-item ${r.status}">
                ${r.status === 'success' ? '✅' : '❌'} ${esc(r.tool)} → ${esc(r.pod)}
                ${r.error ? `<span class="batch-error">${esc(r.error)}</span>` : ''}
                ${r.duration_ms ? `<span class="batch-duration">${r.duration_ms}ms</span>` : ''}
              </div>
            `).join('')}
          </div>
        `;
      }
      toast('批量分发完成', 'ok');
    } catch (e) {
      if (progressEl) progressEl.innerHTML = `<span style="color:var(--red)">❌ ${esc(e.message)}</span>`;
      toast(`批量分发失败：${e.message}`, 'err');
    } finally {
      if (btn) btn.disabled = false;
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