/**
 * 工具箱组件 - Tab布局 + Modal分发
 * 两类工具：二进制工具、脚本工具
 */
(function() {
  'use strict';

  // ═══════════════════════════════════════════════════════════════
  // State & Constants
  // ═══════════════════════════════════════════════════════════════

  let _allTools = { binary: [], script: [] };

  const RECENT_TARGETS_KEY = 'toolbox-recent-targets';
  const MAX_RECENT_TARGETS = 5;

  window.renderToolbox = async function() {
    _distClusterCache = null;
    await Promise.all([
      loadBinaryTools(),
      loadScriptTools()
    ]);
    initToolboxRealtimeRefresh();
  };

  // ═══════════════════════════════════════════════════════════════
  // Tab Switching & Search
  // ═══════════════════════════════════════════════════════════════

  window.switchToolboxTab = function(tab, btn) {
    document.querySelectorAll('.toolbox-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
  };

  window.filterBinaryTools = function(query) {
    query = query.toLowerCase();
    const filtered = _allTools.binary.filter(t =>
      !query || t.name?.toLowerCase().includes(query) ||
      t.file_name?.toLowerCase().includes(query) ||
      t.tool_type?.toLowerCase().includes(query)
    );
    renderBinaryToolCards(filtered);
    document.getElementById('countBinary').textContent = _allTools.binary.length;
  };

  window.filterScriptTools = function(query) {
    query = query.toLowerCase();
    const filtered = _allTools.script.filter(t =>
      !query || t.name?.toLowerCase().includes(query) ||
      t.runtime?.toLowerCase().includes(query)
    );
    renderScriptToolCards(filtered);
    document.getElementById('countScript').textContent = _allTools.script.length;
  };

  // ═══════════════════════════════════════════════════════════════
  // Recent Targets (localStorage)
  // ═══════════════════════════════════════════════════════════════

  function _loadRecentTargets() {
    try {
      const raw = localStorage.getItem(RECENT_TARGETS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function _saveRecentTarget(target) {
    const targets = _loadRecentTargets();
    const key = `${target.cluster}/${target.namespace}/${target.pod}/${target.container || ''}`;
    const existing = targets.findIndex(t =>
      `${t.cluster}/${t.namespace}/${t.pod}/${t.container || ''}` === key
    );
    if (existing >= 0) {
      targets.splice(existing, 1);
    }
    targets.unshift({ ...target, last_used: new Date().toISOString() });
    if (targets.length > MAX_RECENT_TARGETS) {
      targets.length = MAX_RECENT_TARGETS;
    }
    localStorage.setItem(RECENT_TARGETS_KEY, JSON.stringify(targets));
  }

  function _renderRecentTargets(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const targets = _loadRecentTargets();
    if (targets.length === 0) {
      container.innerHTML = '<div class="dist-recent-empty">暂无最近使用的目标</div>';
      return;
    }
    container.innerHTML = targets.map((t, i) => `
      <div class="dist-recent-item" data-index="${i}">
        <div class="dist-recent-target">
          <span>${esc(t.cluster)}</span>
          <span class="sep">/</span>
          <span>${esc(t.namespace)}</span>
          <span class="sep">/</span>
          <span>${esc(t.pod)}</span>
          ${t.container ? `<span class="sep">(${esc(t.container)})</span>` : ''}
        </div>
        <span class="dist-recent-select">选择</span>
      </div>
    `).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // Modal Management
  // ═══════════════════════════════════════════════════════════════

  window.openModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('hidden');
  };

  window.closeModal = function(modalId) {
    if (modalId) {
      const modal = document.getElementById(modalId);
      if (modal) modal.classList.add('hidden');
    } else {
      document.querySelectorAll('.modal-overlay').forEach(m => m.classList.add('hidden'));
      document.querySelectorAll('.dist-modal-overlay').forEach(m => m.remove());
    }
  };

  window.openDistributeHistory = function() {
    openModal('distHistoryModal');
    loadDistHistory();
  };

  let _distHistoryData = [];
  let _distHistoryFilter = 'all';
  let _distHistoryQuery = '';
  let _distHistoryPage = 1;
  let _distHistoryHasMore = false;

  async function loadDistHistory(page = 1) {
    const container = document.getElementById('distHistoryList');
    if (!container) return;
    _distHistoryPage = page;
    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--tx2)">加载中...</div>';

    try {
      const limit = 10;
      const offset = (page - 1) * limit;
      const data = await safeGet(`/tasks/tool-packages/distributions?limit=${limit}&offset=${offset}`);
      _distHistoryData = data.distributions || [];
      _distHistoryHasMore = _distHistoryData.length === limit;
      renderDistHistory(_distHistoryData);
    } catch (e) {
      container.innerHTML = `<div style="text-align:center;padding:40px;color:var(--a5)">加载失败：${esc(e.message)}</div>`;
      _distHistoryHasMore = false;
      renderDistHistoryPagination();
    }
  }

  function renderDistHistoryPagination() {
    const pages = document.getElementById('distHistoryPages');
    if (!pages) return;
    pages.innerHTML = `
      <button class="btn btn-g btn-sm" onclick="loadDistHistoryPage(${_distHistoryPage - 1})" ${_distHistoryPage <= 1 ? 'disabled' : ''}>上一页</button>
      <span style="display:inline-flex;align-items:center;padding:0 8px;font-size:11px;color:var(--tx2)">第 ${_distHistoryPage} 页</span>
      <button class="btn btn-g btn-sm" onclick="loadDistHistoryPage(${_distHistoryPage + 1})" ${_distHistoryHasMore ? '' : 'disabled'}>下一页</button>
    `;
  }

  window.loadDistHistoryPage = function(page) {
    if (page < 1) return;
    loadDistHistory(page);
  };

  function renderDistHistory(records) {
    const container = document.getElementById('distHistoryList');
    const countEl = document.getElementById('distHistoryCount');
    if (!container) return;

    let filtered = records;
    if (_distHistoryFilter !== 'all') {
      filtered = records.filter(r => r.status === _distHistoryFilter);
    }
    if (_distHistoryQuery) {
      filtered = filtered.filter(r => [
        r.tool_name, r.package_name, r.target_cluster, r.target_namespace,
        r.target_pod, r.target_container, r.install_path, r.error_message,
      ].some(value => (value || '').toLowerCase().includes(_distHistoryQuery)));
    }

    if (filtered.length === 0) {
      container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--tx2)">暂无分发记录</div>';
      if (countEl) countEl.textContent = '本页 0 条记录';
      renderDistHistoryPagination();
      return;
    }

    if (countEl) countEl.textContent = `本页 ${filtered.length} 条记录`;

    container.innerHTML = filtered.map(r => {
      const statusClass = r.status === 'success' ? 'running' : 'stopped';
      const statusText = r.status === 'success' ? '成功' : '失败';
      const recordTime = r.distributed_at || r.created_at;
      const time = recordTime ? new Date(recordTime).toLocaleString('zh-CN') : '-';
      const target = `${r.target_cluster || ''} / ${r.target_namespace || ''} / ${r.target_pod || ''}`;
      const duration = r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '-';
      const toolName = r.tool_name || r.package_name || r.tool_id || '-';
      const failReason = formatDistFailureReason(r);

      return `
        <div class="dist-history-row" style="display:grid;grid-template-columns:60px 130px minmax(160px,1fr) minmax(180px,1.2fr) 70px 70px 90px;gap:8px;padding:12px 16px;border-bottom:1px solid rgba(40,61,90,.2);font-size:12px;align-items:center">
          <div><span style="background:rgba(0,122,255,.15);color:var(--a);padding:2px 6px;border-radius:4px;font-size:10px">Pod</span></div>
          <div style="color:var(--tx2);font-size:11px">${esc(time)}</div>
          <div>
            <div style="font-weight:600">${esc(target)}</div>
            <div style="font-size:10px;color:var(--tx3)">${esc(toolName)}</div>
          </div>
          <div title="${esc(failReason.full)}" style="font-size:10px;color:${failReason.text === '-' ? 'var(--tx3)' : '#ff6b6b'};line-height:1.45;word-break:break-word">${esc(failReason.text)}</div>
          <div><span class="badge badge-${statusClass}">${statusText}</span></div>
          <div style="color:var(--tx2);font-size:11px">${duration}</div>
          <div>
            <button class="btn btn-g btn-sm" style="font-size:10px" onclick="openDistDetailModal(${r.id})">详情</button>
            ${r.status === 'failed' ? `<button class="btn btn-p btn-sm" style="font-size:10px" onclick="retryDist(${r.id})">重试</button>` : ''}
          </div>
        </div>
      `;
    }).join('');
    renderDistHistoryPagination();
  }

  function formatDistFailureReason(record) {
    const raw = [record.error_message, record.stderr].filter(Boolean).join('\n').trim();
    if (!raw) return { text: '-', full: '' };
    let reason = raw
      .replace(/^kubectl cp\s*失败[:：]?\s*/i, '')
      .replace(/^error:\s*/i, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (/one of src or dest must be a local file specification/i.test(reason)) {
      reason = 'kubectl cp 目标路径格式错误（已修复，重试即可）';
    }
    return { text: reason.length > 90 ? reason.slice(0, 90) + '…' : reason, full: raw };
  }

  window.filterDistHistory = function(query) {
    _distHistoryQuery = (query || '').trim().toLowerCase();
    renderDistHistory(_distHistoryData);
  };

  window.filterDistByStatus = function(status, btn) {
    _distHistoryFilter = status;
    btn.parentElement.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderDistHistory(_distHistoryData);
  };

  window.retryDist = async function(distId) {
    const record = _distHistoryData.find(item => item.id === distId);
    if (!record) { toast('当前页未找到这条分发记录，请刷新后重试', 'warn'); return; }
    if (!confirm(`确认将 ${record.package_name || '工具'} 重新分发到 ${record.target_cluster}/${record.target_namespace}/${record.target_pod}？`)) return;
    try {
      await safePost(`/tasks/tool-packages/${record.package_id}/distribute`, {
        cluster: record.target_cluster,
        namespace: record.target_namespace,
        pod: record.target_pod,
        container: record.target_container || '',
        install_path: record.install_path,
      });
      toast('重试成功', 'ok');
      loadDistHistory(_distHistoryPage);
    } catch (e) {
      toast(`重试失败: ${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 分发详情 Modal
  // ═══════════════════════════════════════════════════════════════

  window.openDistDetailModal = function(distId) {
    const record = _distHistoryData.find(item => item.id === distId);
    if (!record) { toast('当前页未找到这条分发记录，请刷新后重试', 'warn'); return; }
    document.getElementById(`distDetailModal-${distId}`)?.remove();
    const success = record.status === 'success';
    const statusText = success ? '分发成功' : '分发失败';
    const time = record.distributed_at || record.created_at;
    const fullHash = record.local_sha256 || '';
    const podHash = record.pod_sha256 || '';
    const modal = document.createElement('div');
    modal.className = 'dist-modal-overlay';
    modal.id = `distDetailModal-${distId}`;
    modal.innerHTML = `
      <div class="dist-modal" style="width:600px">
        <div class="dist-modal-header">
          <h3>分发详情</h3>
          <button class="btn-close" onclick="closeModal('distDetailModal-${distId}')">✕</button>
        </div>
        <div class="dist-modal-body">
          <div style="display:flex;align-items:center;gap:12px;padding:16px;background:${success ? 'rgba(52,199,89,.08)' : 'rgba(255,59,48,.08)'};border:1px solid ${success ? 'rgba(52,199,89,.2)' : 'rgba(255,59,48,.2)'};border-radius:8px;margin-bottom:20px">
            <span style="font-size:24px;color:${success ? '#34c759' : '#ff3b30'}">${success ? '✓' : '✕'}</span>
            <div>
              <div style="font-size:14px;font-weight:700;color:${success ? '#34c759' : '#ff3b30'}">${statusText}</div>
              <div style="font-size:12px;color:var(--tx2)">${esc(record.package_name || record.package_id || '工具包')}</div>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
            <div>
              <div style="font-size:11px;color:var(--tx2);margin-bottom:4px">分发时间</div>
              <div style="font-size:13px">${esc(time ? new Date(time).toLocaleString('zh-CN') : '-')}</div>
            </div>
            <div>
              <div style="font-size:11px;color:var(--tx2);margin-bottom:4px">分发 ID</div>
              <div style="font-size:13px;font-family:monospace">${esc(distId)}</div>
            </div>
          </div>

          <div style="margin-bottom:20px">
            <div style="font-size:12px;font-weight:600;color:var(--tx2);margin-bottom:10px">目标信息</div>
            <div style="background:rgba(0,0,0,.2);border-radius:8px;padding:12px">
              <div style="display:grid;grid-template-columns:100px 1fr;gap:8px;font-size:12px">
              <div style="color:var(--tx2)">集群</div><div>${esc(record.target_cluster || '-')}</div>
              <div style="color:var(--tx2)">Namespace</div><div>${esc(record.target_namespace || '-')}</div>
              <div style="color:var(--tx2)">Pod</div><div>${esc(record.target_pod || '-')}</div>
              <div style="color:var(--tx2)">容器</div><div>${esc(record.target_container || '默认容器')}</div>
              <div style="color:var(--tx2)">安装路径</div><div style="font-family:monospace;word-break:break-all">${esc(record.install_path || '-')}</div>
              </div>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
            <div style="font-size:11px;color:var(--tx2)">源文件 SHA256<br><code style="color:var(--tx);word-break:break-all">${esc(fullHash || '无记录')}</code></div>
            <div style="font-size:11px;color:var(--tx2)">目标文件 SHA256<br><code style="color:var(--tx);word-break:break-all">${esc(podHash || '未校验')}</code></div>
          </div>
          ${record.pod_check_status ? `<div style="font-size:11px;color:var(--tx2);margin-bottom:12px">目标校验状态：${esc(record.pod_check_status)}${record.pod_file_size ? ` · 文件大小 ${esc(record.pod_file_size)}` : ''}</div>` : ''}
          ${record.error_message || record.stderr ? `<div style="background:rgba(255,59,48,.06);border:1px solid rgba(255,59,48,.18);border-radius:8px;padding:12px;font-size:11px;white-space:pre-wrap;word-break:break-word;color:#ff8a80">${esc([record.error_message, record.stderr].filter(Boolean).join('\n'))}</div>` : ''}
        </div>
        <div class="dist-modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('distDetailModal-${distId}')">关闭</button>
          ${!success ? `<button class="btn btn-p btn-sm" onclick="retryDist(${distId})">重试</button>` : ''}
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  // ═══════════════════════════════════════════════════════════════
  // 重试 Modal
  // ═══════════════════════════════════════════════════════════════

  window.openRetryModal = function(distId, toolId, target) {
    const modal = document.createElement('div');
    modal.className = 'dist-modal-overlay';
    modal.id = `retryModal-${distId}`;
    modal.innerHTML = `
      <div class="dist-modal" style="width:560px">
        <div class="dist-modal-header">
          <h3>重试分发</h3>
          <button class="btn-close" onclick="closeModal('retryModal-${distId}')">✕</button>
        </div>
        <div class="dist-modal-body">
          <div style="background:rgba(255,59,48,.08);border:1px solid rgba(255,59,48,.2);border-radius:8px;padding:12px;margin-bottom:16px">
            <div style="font-size:11px;color:var(--tx2);margin-bottom:6px">失败记录</div>
            <div style="font-size:12px">
              <span style="color:var(--tx2)">目标:</span>
              <span style="font-weight:600">${esc(target || '未知')}</span>
            </div>
            <div style="font-size:11px;color:#ff3b30;margin-top:6px">错误: permission denied</div>
          </div>

          <div style="font-size:12px;font-weight:600;color:var(--tx2);margin-bottom:10px">确认重试目标</div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div style="display:flex;gap:12px">
              <div style="flex:1">
                <label style="font-size:12px;color:var(--tx2);display:block;margin-bottom:4px">集群</label>
                <select class="inp"><option>prod</option></select>
              </div>
              <div style="flex:1">
                <label style="font-size:12px;color:var(--tx2);display:block;margin-bottom:4px">Namespace</label>
                <select class="inp"><option>default</option></select>
              </div>
            </div>
            <div style="display:flex;gap:12px">
              <div style="flex:2">
                <label style="font-size:12px;color:var(--tx2);display:block;margin-bottom:4px">Pod</label>
                <select class="inp"><option>pod-d-9e1b3</option></select>
              </div>
              <div style="flex:1">
                <label style="font-size:12px;color:var(--tx2);display:block;margin-bottom:4px">容器</label>
                <select class="inp"><option>app</option></select>
              </div>
            </div>
          </div>
          <div style="background:rgba(255,149,0,.08);border:1px solid rgba(255,149,0,.2);border-radius:6px;padding:10px;font-size:11px;color:var(--tx2);margin-top:16px">
            💡 建议: 检查 Pod 写入权限，或尝试使用其他容器
          </div>
        </div>
        <div class="dist-modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('retryModal-${distId}')">取消</button>
          <button class="btn btn-p btn-sm" onclick="confirmRetry(${toolId})">确认重试</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.confirmRetry = function(toolId) {
    closeModal(`retryModal-*`);
    openDistributeModal(toolId, 'binary', '/app/arthas/arthas-boot.jar');
  };

  // ═══════════════════════════════════════════════════════════════
  // 执行 Modal（脚本）
  // ═══════════════════════════════════════════════════════════════

  window.openExecuteModal = function(toolId, toolName, command) {
    const modal = document.createElement('div');
    modal.className = 'dist-modal-overlay';
    modal.id = `executeModal-${toolId}`;
    modal.innerHTML = `
      <div class="dist-modal" style="width:560px">
        <div class="dist-modal-header">
          <h3>执行: ${esc(toolName)}</h3>
          <button class="btn-close" onclick="closeModal('executeModal-${toolId}')">✕</button>
        </div>
        <div class="dist-modal-body">
          <div style="margin-bottom:16px">
            <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">命令预览</label>
            <div style="background:rgba(0,0,0,.3);padding:10px;border-radius:6px;font-family:monospace;font-size:12px;color:var(--a2)">
              ${esc(command || 'echo "Hello"')}
            </div>
          </div>

          <div style="margin-bottom:16px">
            <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">目标 Pod</label>
            <div style="display:flex;gap:12px">
              <div style="flex:1">
                <select class="inp"><option>选择集群...</option></select>
              </div>
              <div style="flex:1">
                <select class="inp"><option>选择 Pod...</option></select>
              </div>
            </div>
          </div>

          <div id="execResult-${toolId}" style="display:none">
            <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">执行结果</label>
            <div style="background:rgba(0,0,0,.3);border:1px solid rgba(40,61,90,.4);border-radius:6px;padding:12px;font-family:monospace;font-size:11px;max-height:200px;overflow-y:auto">
              <div style="color:var(--tx3);margin-bottom:4px">$ ${esc(command || 'echo "Hello"')}</div>
              <div style="color:#34c759">Hello</div>
              <div style="color:var(--tx3);margin-top:8px">执行完成 (0.2s)</div>
            </div>
          </div>
        </div>
        <div class="dist-modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('executeModal-${toolId}')">取消</button>
          <button class="btn btn-p btn-sm" onclick="executeScript(${toolId})">执行</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.executeScript = function(toolId) {
    const resultEl = document.getElementById(`execResult-${toolId}`);
    if (resultEl) {
      resultEl.style.display = 'block';
      toast('脚本执行成功', 'ok');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 分发结果 Modal
  // ═══════════════════════════════════════════════════════════════

  window.openDistResultModal = function(results) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'distResultModal';

    const successCount = results.filter(r => r.status === 'success').length;
    const failedCount = results.filter(r => r.status === 'failed').length;

    modal.innerHTML = `
      <div class="modal" style="width:600px">
        <div class="modal-header">
          <h3>分发结果</h3>
          <button class="btn-close" onclick="closeModal('distResultModal')">✕</button>
        </div>
        <div class="modal-body">
          <div style="display:flex;gap:16px;margin-bottom:20px">
            <div style="flex:1;padding:12px;background:rgba(52,199,89,.1);border-radius:8px;text-align:center">
              <div style="font-size:24px;font-weight:700;color:#34c759">${successCount}</div>
              <div style="font-size:11px;color:var(--tx2)">成功</div>
            </div>
            <div style="flex:1;padding:12px;background:rgba(255,59,48,.1);border-radius:8px;text-align:center">
              <div style="font-size:24px;font-weight:700;color:#ff3b30">${failedCount}</div>
              <div style="font-size:11px;color:var(--tx2)">失败</div>
            </div>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px">
            ${results.map(r => `
              <div style="display:flex;align-items:center;gap:10px;padding:10px;background:${r.status === 'success' ? 'rgba(52,199,89,.08)' : 'rgba(255,59,48,.08)'};border:1px solid ${r.status === 'success' ? 'rgba(52,199,89,.2)' : 'rgba(255,59,48,.2)'};border-radius:6px">
                <span style="color:${r.status === 'success' ? '#34c759' : '#ff3b30'};font-size:14px">${r.status === 'success' ? '✓' : '✗'}</span>
                <div style="flex:1">
                  <div style="font-size:12px;font-weight:600">${esc(r.pod || '未知')}</div>
                  <div style="font-size:11px;color:var(--tx2)">${esc(r.cluster || '')} / ${esc(r.namespace || '')}</div>
                  ${r.error ? `<div style="font-size:10px;color:#ff3b30;margin-top:4px">${esc(r.error)}</div>` : ''}
                </div>
                <span class="badge badge-${r.status === 'success' ? 'running' : 'stopped'}" style="font-size:10px">${r.status === 'success' ? '成功' : '失败'}</span>
                ${r.status === 'failed' ? `<button class="btn btn-p btn-sm" style="font-size:10px" onclick="retrySingleDist(${r.id || 0})">重试</button>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('distResultModal')">关闭</button>
          ${failedCount > 0 ? `<button class="btn btn-p btn-sm" onclick="batchRetryFailed()">重试失败项 (${failedCount})</button>` : ''}
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.retrySingleDist = function(distId) {
    closeModal('distResultModal');
    // Open retry modal or directly retry
    toast('正在重试...', 'info');
  };

  window.batchRetryFailed = function() {
    closeModal('distResultModal');
    toast('批量重试功能开发中', 'info');
  };

  // ═══════════════════════════════════════════════════════════════
  // 批量重试 Modal
  // ═══════════════════════════════════════════════════════════════

  window.openBatchRetryModal = function(failedItems) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'batchRetryModal';
    modal.innerHTML = `
      <div class="modal" style="width:600px">
        <div class="modal-header">
          <h3>批量重试失败项</h3>
          <button class="btn-close" onclick="closeModal('batchRetryModal')">✕</button>
        </div>
        <div class="modal-body">
          <div style="font-size:12px;color:var(--tx2);margin-bottom:10px">以下分发失败，是否重试？</div>
          <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px">
            ${failedItems.map(item => `
              <div style="display:flex;align-items:center;gap:10px;padding:10px;background:rgba(255,59,48,.08);border:1px solid rgba(255,59,48,.2);border-radius:6px">
                <input type="checkbox" checked class="retry-check" value="${item.id}" style="width:14px;height:14px">
                <div style="flex:1">
                  <div style="font-size:12px;font-weight:600">${esc(item.pod || '未知')}</div>
                  <div style="font-size:11px;color:var(--tx3)">${esc(item.cluster || '')} / ${esc(item.namespace || '')} / ${esc(item.container || '')}</div>
                  <div style="font-size:10px;color:#ff3b30">${esc(item.error || '未知错误')}</div>
                </div>
              </div>
            `).join('')}
          </div>
          <div style="background:rgba(0,122,255,.08);border:1px solid rgba(0,122,255,.2);border-radius:6px;padding:10px;font-size:11px;color:var(--tx2)">
            💡 批量重试将使用相同的工具和安装路径，仅重新执行分发操作
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('batchRetryModal')">取消</button>
          <button class="btn btn-p btn-sm" onclick="executeBatchRetry()">重试选中项</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.executeBatchRetry = async function() {
    const checkboxes = document.querySelectorAll('.retry-check:checked');
    const ids = Array.from(checkboxes).map(cb => parseInt(cb.value));

    if (ids.length === 0) {
      toast('请选择要重试的项', 'warn');
      return;
    }

    closeModal('batchRetryModal');
    toast(`正在重试 ${ids.length} 项...`, 'info');

    try {
      const result = await safePost('/tasks/distributions/batch-retry', { dist_ids: ids });
      if (result.ok) {
        toast(`重试完成: ${result.summary.success} 成功, ${result.summary.failed} 失败`, 'ok');
        openDistResultModal(result.results);
      }
    } catch (e) {
      toast(`重试失败: ${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // Arthas 文档 Modal
  // ═══════════════════════════════════════════════════════════════

  window.openArthasDocModal = function(command) {
    const docs = {
      'jad': {
        title: 'jad - 反编译已运行代码',
        desc: '反编译指定类的源代码。可以用来查看正在运行的 Java 类的源码。',
        usage: 'jad [option] class-pattern [filter条件]',
        examples: [
          { comment: '反编译单个类', cmd: 'jad com.example.MyClass' },
          { comment: '反编译并输出到文件', cmd: 'jad -d /tmp arthas com.example.MyClass' },
          { comment: '只反编译指定方法', cmd: 'jad com.example.MyClass *testMethod*' },
        ],
        url: 'https://arthas.aliyun.com/doc/jad.html'
      },
      'thread': {
        title: 'thread - 线程堆栈',
        desc: '查看当前 JVM 线程堆栈信息。',
        usage: 'thread [option]',
        examples: [
          { comment: '查看所有线程', cmd: 'thread' },
          { comment: '查看最忙的3个线程', cmd: 'thread -n 3' },
          { comment: '查看指定线程', cmd: 'thread <id>' },
        ],
        url: 'https://arthas.aliyun.com/doc/thread.html'
      },
      'dashboard': {
        title: 'dashboard - 实时面板',
        desc: '实时展示 JVM 运行数据：线程、内存、GC、运行时信息。',
        usage: 'dashboard [option]',
        examples: [
          { comment: '查看实时面板', cmd: 'dashboard' },
          { comment: '只显示线程面板', cmd: 'dashboard -i 2000 -n 1' },
        ],
        url: 'https://arthas.aliyun.com/doc/dashboard.html'
      },
      'watch': {
        title: 'watch - 方法执行数据',
        desc: '观察方法执行的入参、返回值、异常等信息。',
        usage: 'watch class-pattern method-pattern [expressions]',
        examples: [
          { comment: '观察方法入参和返回值', cmd: 'watch com.example.MyClass myMethod "{params, returnObj}"' },
          { comment: '观察耗时超过100ms的调用', cmd: 'watch com.example.MyClass myMethod "#cost > 100"' },
        ],
        url: 'https://arthas.aliyun.com/doc/watch.html'
      },
      'trace': {
        title: 'trace - 方法调用链',
        desc: '跟踪方法内部调用路径和耗时。',
        usage: 'trace class-pattern method-pattern',
        examples: [
          { comment: '跟踪方法调用', cmd: 'trace com.example.MyClass myMethod' },
          { comment: '只显示耗时超过100ms的调用', cmd: 'trace com.example.MyClass myMethod "#cost > 100"' },
        ],
        url: 'https://arthas.aliyun.com/doc/trace.html'
      },
    };

    const doc = docs[command] || docs['jad'];

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'arthasDocModal';
    modal.innerHTML = `
      <div class="modal" style="width:640px">
        <div class="modal-header">
          <h3>Arthas 文档: ${esc(doc.title)}</h3>
          <button class="btn-close" onclick="closeModal('arthasDocModal')">✕</button>
        </div>
        <div class="modal-body">
          <div style="margin-bottom:16px">
            <p style="font-size:12px;color:var(--tx2);line-height:1.6">${esc(doc.desc)}</p>
          </div>
          <div style="margin-bottom:16px">
            <div style="font-size:13px;font-weight:600;margin-bottom:8px">用法</div>
            <div style="background:rgba(0,0,0,.3);padding:10px;border-radius:6px;font-family:monospace;font-size:12px;color:var(--a2)">
              ${esc(doc.usage)}
            </div>
          </div>
          <div style="margin-bottom:16px">
            <div style="font-size:13px;font-weight:600;margin-bottom:8px">示例</div>
            <div style="background:rgba(0,0,0,.3);padding:10px;border-radius:6px;font-family:monospace;font-size:11px">
              ${doc.examples.map(ex => `
                <div style="margin-bottom:8px">
                  <div style="color:var(--tx3);margin-bottom:4px"># ${esc(ex.comment)}</div>
                  <div style="color:var(--a2)">${esc(ex.cmd)}</div>
                </div>
              `).join('')}
            </div>
          </div>
          <a href="${doc.url}" target="_blank" style="color:var(--a);font-size:12px">查看完整文档 →</a>
        </div>
        <div class="modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('arthasDocModal')">关闭</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.openEditBinaryModal = function(toolId) {
    const tool = _allTools.binary.find(t => t.id === toolId);
    if (!tool) { toast('工具不存在', 'warn'); return; }

    const modal = document.createElement('div');
    modal.className = 'dist-modal-overlay';
    modal.id = `editBinaryModal-${toolId}`;
    modal.innerHTML = `
      <div class="dist-modal" style="width:560px">
        <div class="dist-modal-header">
          <h3>编辑工具: ${esc(tool.file_name || tool.name)}</h3>
          <button class="btn-close" onclick="closeModal('editBinaryModal-${toolId}')">✕</button>
        </div>
        <div class="dist-modal-body">
          <div style="display:flex;flex-direction:column;gap:14px">
            <div>
              <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">工具名称 *</label>
              <input id="editBinName-${toolId}" class="inp" value="${esc(tool.file_name || tool.name)}">
            </div>
            <div style="display:flex;gap:12px">
              <div style="flex:1">
                <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">工具类型</label>
                <select id="editBinType-${toolId}" class="inp">
                  <option value="arthas" ${tool.tool_type === 'arthas' ? 'selected' : ''}>Arthas</option>
                  <option value="async-profiler" ${tool.tool_type === 'async-profiler' ? 'selected' : ''}>async-profiler</option>
                  <option value="generic" ${tool.tool_type === 'generic' ? 'selected' : ''}>通用</option>
                </select>
              </div>
              <div style="flex:1">
                <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">版本</label>
                <input id="editBinVersion-${toolId}" class="inp" value="${esc(tool.version || '')}">
              </div>
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">安装路径 *</label>
              <input id="editBinPath-${toolId}" class="inp" value="${esc(tool.install_path || '')}">
              <div style="font-size:11px;color:var(--tx3);margin-top:4px">分发到 Pod 时的默认安装路径</div>
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">当前文件</label>
              <div style="background:rgba(0,0,0,.2);padding:10px;border-radius:6px;font-size:12px">
                <div style="color:var(--tx2);margin-bottom:4px">文件名: <span style="color:var(--tx)">${esc(tool.file_name || tool.name)}</span></div>
                <div style="color:var(--tx2);margin-bottom:4px">SHA256: <span style="color:var(--tx);font-family:monospace;font-size:11px">${esc(tool.sha256 ? tool.sha256.slice(0, 20) + '...' : '未校验')}</span></div>
              </div>
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">替换文件（可选）</label>
              <div style="display:flex;gap:8px;align-items:center">
                <button class="btn btn-g btn-sm" onclick="document.getElementById('editBinFile-${toolId}').click()">选择新文件</button>
                <span id="editBinFileName-${toolId}" style="font-size:12px;color:var(--tx3)">未选择文件</span>
                <input id="editBinFile-${toolId}" type="file" style="display:none" onchange="document.getElementById('editBinFileName-${toolId}').textContent=this.files?.[0]?.name||'未选择文件'">
              </div>
              <div style="font-size:11px;color:var(--tx3);margin-top:4px">选择新文件后将替换当前文件</div>
            </div>
          </div>
        </div>
        <div class="dist-modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('editBinaryModal-${toolId}')">取消</button>
          <button class="btn btn-p btn-sm" onclick="saveBinaryTool(${toolId})">保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.saveBinaryTool = async function(toolId) {
    const name = document.getElementById(`editBinName-${toolId}`)?.value;
    const toolType = document.getElementById(`editBinType-${toolId}`)?.value;
    const version = document.getElementById(`editBinVersion-${toolId}`)?.value;
    const installPath = document.getElementById(`editBinPath-${toolId}`)?.value;

    if (!name) { toast('请输入工具名称', 'warn'); return; }
    if (!installPath) { toast('请输入安装路径', 'warn'); return; }

    try {
      await safePut(`/tasks/tool-packages/${toolId}`, {
        name, tool_type: toolType, version, install_path: installPath
      });
      toast('保存成功', 'ok');
      closeModal(`editBinaryModal-${toolId}`);
      loadBinaryTools();
    } catch (e) {
      toast(`保存失败：${e.message}`, 'err');
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 二进制工具
  // ═══════════════════════════════════════════════════════════════

  async function loadBinaryTools() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      _allTools.binary = data.packages || [];
      renderBinaryToolCards(_allTools.binary);
      document.getElementById('countBinary').textContent = _allTools.binary.length;
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
      const statusText = p.status === 'active' ? '可用' : p.status === 'missing' ? '文件缺失' : '停用';
      const displayName = p.file_name || p.name;
      const fileSize = formatFileSize(p.file_size);
      const verifiedAt = p.last_verified_at
        ? new Date(p.last_verified_at).toLocaleString('zh-CN')
        : '尚未校验';
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
            <span>${esc(fileSize)}</span>
          </div>
          ${p.description ? `<div class="toolbox-card-meta toolbox-card-description" title="${esc(p.description)}">${esc(p.description)}</div>` : ''}
          <div class="toolbox-card-path">${esc(p.install_path || '-')}</div>
          <div class="toolbox-card-meta"><span>SHA256 ${esc(sha)}</span><span>校验 ${esc(verifiedAt)}</span></div>
          <div class="toolbox-card-actions">
            <button class="btn btn-g btn-sm" onclick="openEditBinaryModal(${p.id})">编辑</button>
            <button class="btn btn-g btn-sm" onclick="toolboxVerify(${p.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              校验
            </button>
            <button class="btn btn-p btn-sm" onclick="openDistributeModal(${p.id}, 'binary')" ${p.status === 'missing' ? 'disabled title="请先检查或重新上传工具文件"' : ''}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              分发→
            </button>
            ${!p.is_builtin ? `<button class="btn btn-s btn-sm" onclick="toolboxDeleteBinary(${p.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              删除
            </button>` : ''}
          </div>
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
      _allTools.script = data.tools || [];
      renderScriptToolCards(_allTools.script);
      document.getElementById('countScript').textContent = _allTools.script.length;
    } catch (e) {
      console.error('加载脚本工具失败:', e);
    }
  }

  window.openEditScriptModal = function(toolId) {
    const tool = _allTools.script.find(t => t.id === toolId);
    if (!tool) { toast('脚本不存在', 'warn'); return; }

    const modal = document.createElement('div');
    modal.className = 'dist-modal-overlay';
    modal.id = `editScriptModal-${toolId}`;
    modal.innerHTML = `
      <div class="dist-modal" style="width:640px">
        <div class="dist-modal-header">
          <h3>编辑脚本: ${esc(tool.name)}</h3>
          <button class="btn-close" onclick="closeModal('editScriptModal-${toolId}')">✕</button>
        </div>
        <div class="dist-modal-body">
          <!-- LLM Assist Box -->
          <div style="background:rgba(0,122,255,.08);border:1px solid rgba(0,122,255,.3);border-radius:8px;padding:12px;margin-bottom:16px">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
              <div style="width:24px;height:24px;background:var(--a);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px">🤖</div>
              <span style="font-size:12px;font-weight:600;color:var(--a)">AI 辅助优化脚本</span>
            </div>
            <div style="font-size:11px;color:var(--tx2);margin-bottom:10px">描述你想要的改进，AI 会帮你优化脚本</div>
            <div style="display:flex;gap:8px">
              <input id="llmOptimizeInput-${toolId}" class="inp" placeholder="例如：添加错误处理，支持多线程分析" style="flex:1">
              <button class="btn btn-p btn-sm" onclick="optimizeScriptWithLLM(${toolId})">优化</button>
            </div>
          </div>

          <div style="display:flex;flex-direction:column;gap:14px">
            <div>
              <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">脚本名称 *</label>
              <input id="editScrName-${toolId}" class="inp" value="${esc(tool.name)}">
            </div>
            <div style="display:flex;gap:12px">
              <div style="flex:1">
                <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">运行时</label>
                <select id="editScrRuntime-${toolId}" class="inp">
                  <option value="python" ${tool.runtime === 'python' ? 'selected' : ''}>Python</option>
                  <option value="shell" ${tool.runtime === 'shell' ? 'selected' : ''}>Shell</option>
                  <option value="node" ${tool.runtime === 'node' ? 'selected' : ''}>Node.js</option>
                </select>
              </div>
              <div style="flex:1">
                <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">风险等级</label>
                <select id="editScrRisk-${toolId}" class="inp">
                  <option value="low" ${tool.risk_level === 'low' ? 'selected' : ''}>低风险</option>
                  <option value="medium" ${tool.risk_level === 'medium' ? 'selected' : ''}>中风险</option>
                  <option value="high" ${tool.risk_level === 'high' ? 'selected' : ''}>高风险</option>
                </select>
              </div>
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:6px">脚本内容 *</label>
              <textarea id="editScrBody-${toolId}" class="inp" style="min-height:180px;font-family:monospace;font-size:12px;resize:vertical">${esc(tool.script_body || '')}</textarea>
            </div>
          </div>
        </div>
        <div class="dist-modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('editScriptModal-${toolId}')">取消</button>
          <button class="btn btn-p btn-sm" onclick="saveScriptTool(${toolId})">保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.saveScriptTool = async function(toolId) {
    const name = document.getElementById(`editScrName-${toolId}`)?.value;
    const runtime = document.getElementById(`editScrRuntime-${toolId}`)?.value;
    const riskLevel = document.getElementById(`editScrRisk-${toolId}`)?.value;
    const scriptBody = document.getElementById(`editScrBody-${toolId}`)?.value;

    if (!name) { toast('请输入脚本名称', 'warn'); return; }
    if (!scriptBody) { toast('请输入脚本内容', 'warn'); return; }

    try {
      await safePut(`/tasks/script-tools/${toolId}`, {
        name, runtime, risk_level: riskLevel, script_body: scriptBody
      });
      toast('保存成功', 'ok');
      closeModal(`editScriptModal-${toolId}`);
      loadScriptTools();
    } catch (e) {
      toast(`保存失败：${e.message}`, 'err');
    }
  };

  window.optimizeScriptWithLLM = async function(toolId) {
    const input = document.getElementById(`llmOptimizeInput-${toolId}`)?.value;
    const scriptBody = document.getElementById(`editScrBody-${toolId}`)?.value;

    if (!input) { toast('请输入优化需求', 'warn'); return; }

    toast('AI 正在优化脚本...', 'info');

    try {
      const result = await safePost('/ai/chat', {
        messages: [
          { role: 'system', content: '你是一个 Python/Shell 脚本优化助手。根据用户需求优化脚本，只返回优化后的代码，不要解释。' },
          { role: 'user', content: `当前脚本:\n\`\`\`\n${scriptBody}\n\`\`\`\n\n优化需求: ${input}` }
        ]
      });

      if (result.choices && result.choices[0]) {
        const newScript = result.choices[0].message.content.replace(/```[\s\S]*?```/g, '').trim();
        document.getElementById(`editScrBody-${toolId}`).value = newScript;
        toast('脚本已优化', 'ok');
      }
    } catch (e) {
      toast(`优化失败：${e.message}`, 'err');
    }
  };

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
            <button class="btn btn-g btn-sm" onclick="openEditScriptModal(${t.id})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              编辑
            </button>
            <button class="btn btn-p btn-sm" onclick="openExecuteModal(${t.id}, '${esc(t.name)}', '${esc(t.command_template || "")}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              执行→
            </button>
            <button class="btn btn-g btn-sm" onclick="openArthasDocModal('${esc(t.command_template || 'jad').split(' ')[0]}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              文档
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
        <div><label class="fl">工具类型</label><select id="tbUpType" class="inp"><option value="arthas">Arthas</option><option value="async-profiler">async-profiler</option><option value="generic">通用</option></select><div id="tbUpTypeHint" style="font-size:11px;color:var(--tx3);margin-top:4px"></div></div>
        <div><label class="fl">版本</label><input id="tbUpVer" class="inp" placeholder="可选"></div>
        <div><label class="fl">Pod 内安装路径</label><input id="tbUpPath" class="inp" value="/tmp/arthas/arthas-boot.jar"><div style="font-size:11px;color:var(--tx3);margin-top:4px">默认路径可修改；Arthas 文件必须使用 .jar 路径。</div></div>
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
    const typeEl = modal.querySelector('#tbUpType');
    const fileEl = modal.querySelector('#tbUpFile');
    const pathEl = modal.querySelector('#tbUpPath');
    const typeHint = modal.querySelector('#tbUpTypeHint');
    let installPathEdited = false;
    const updateUploadDefaults = () => {
      const fileName = (fileEl?.files?.[0]?.name || 'tool').split(/[\\/]/).pop();
      const safeName = fileName.replace(/[^A-Za-z0-9._-]/g, '_') || 'tool';
      const type = typeEl?.value || 'arthas';
      if (!installPathEdited) {
        pathEl.value = type === 'arthas'
          ? '/tmp/arthas/arthas-boot.jar'
          : type === 'async-profiler'
            ? `/tmp/async-profiler/${safeName}`
            : `/tmp/${safeName}`;
      }
      if (typeHint) {
        typeHint.textContent = type === 'arthas'
          ? 'Arthas 包会使用标准目录，上传文件应为 arthas-boot.jar。'
          : type === 'async-profiler'
            ? '工具将以文件形式复制到目标 Pod 的临时目录。'
            : '通用工具使用独立文件路径；请确认目标容器具备所需运行环境。';
      }
    };
    typeEl?.addEventListener('change', updateUploadDefaults);
    fileEl?.addEventListener('change', updateUploadDefaults);
    pathEl?.addEventListener('input', () => { installPathEdited = true; });
    updateUploadDefaults();
    modal.querySelector('#tbUpSubmitBtn').onclick = async () => {
      const fileEl = modal.querySelector('#tbUpFile');
      const file = fileEl?.files?.[0];
      if (!file) { toast('请选择文件', 'warn'); return; }
      const toolType = typeEl?.value || 'arthas';
      const installPath = pathEl?.value?.trim() || '';
      if (!installPath.startsWith('/') || installPath.split('/').includes('..')) {
        toast('请输入合法的 Pod 内绝对路径', 'warn');
        pathEl?.focus();
        return;
      }
      if (toolType === 'arthas' && !installPath.endsWith('.jar')) {
        toast('Arthas 安装路径必须以 .jar 结尾', 'warn');
        pathEl?.focus();
        return;
      }
      const submit = modal.querySelector('#tbUpSubmitBtn');
      submit.disabled = true;
      submit.textContent = '上传中...';
      const form = new FormData();
      form.append('file', file);
      form.append('name', modal.querySelector('#tbUpName')?.value?.trim() || file.name);
      form.append('tool_type', toolType);
      form.append('version', modal.querySelector('#tbUpVer')?.value?.trim() || '');
      form.append('install_path', installPath);
      form.append('description', modal.querySelector('#tbUpDesc')?.value?.trim() || '');
      try {
        await safeUploadToolPackage('/tasks/tool-packages/upload', form, 300000);
        toast('工具已上传', 'ok');
        modal.remove();
        loadBinaryTools();
      } catch (e) {
        toast(`上传失败：${e.message}`, 'err');
        submit.disabled = false;
        submit.textContent = '上传并登记';
      }
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
  const _distRequestIds = new Map();

  function _nextDistRequestId(toolId) {
    const requestId = (_distRequestIds.get(toolId) || 0) + 1;
    _distRequestIds.set(toolId, requestId);
    return requestId;
  }

  async function _loadDistClusters() {
    if (_distClusterCache) return _distClusterCache;
    const data = await safeGet('/clusters');
    _distClusterCache = data.clusters || [];
    return _distClusterCache;
  }

  window.openDistributeModal = async function(toolId, toolType, defaultPath) {
    // Remove existing modal if any
    const existing = document.getElementById(`distModal-${toolId}`);
    if (existing) existing.remove();

    // Get tool info from card
    const card = document.querySelector(`.toolbox-card[data-id="${toolId}"]`);
    const tool = _allTools.binary.find(item => item.id === toolId);
    const toolName = card?.querySelector('.toolbox-card-name')?.textContent || tool?.name || `Tool #${toolId}`;
    const installPath = defaultPath || tool?.install_path || '';

    // Load clusters
    let clusters;
    try {
      clusters = await _loadDistClusters();
    } catch (e) {
      toast(`加载集群失败：${e.message}`, 'err');
      return;
    }
    const clusterOptions = clusters.map(c =>
      `<option value="${esc(c.name)}">${esc(c.name)}</option>`
    ).join('');

    // Create modal
    const modal = document.createElement('div');
    modal.className = 'dist-modal-overlay';
    modal.id = `distModal-${toolId}`;
    modal.innerHTML = `
      <div class="dist-modal">
        <div class="dist-modal-header">
          <h3>分发工具: ${esc(toolName)}</h3>
          <button class="btn-close" onclick="closeModal('distModal-${toolId}')">✕</button>
        </div>
        <div class="dist-modal-body">
          <div class="dist-recent-section">
            <div class="dist-section-title">⭐ 最近使用</div>
            <div class="dist-recent-list" id="distRecentList-${toolId}"></div>
          </div>
          <div class="dist-divider">或手动选择目标</div>
          <div class="dist-form" style="display:flex;flex-direction:column;gap:12px">
            <div class="dist-form-row" style="display:flex;align-items:center;gap:10px">
              <label style="font-size:12px;color:var(--tx2);min-width:70px;font-weight:600">集群</label>
              <select id="dist-cluster-${toolId}" class="inp" onchange="distOnClusterChange(${toolId})">
                <option value="">${clusters.length ? '选择集群...' : '无可访问的集群'}</option>
                ${clusterOptions}
              </select>
            </div>
            <div class="dist-form-row" style="display:flex;align-items:center;gap:10px">
              <label style="font-size:12px;color:var(--tx2);min-width:70px;font-weight:600">Namespace</label>
              <select id="dist-ns-${toolId}" class="inp" onchange="distOnNsChange(${toolId})">
                <option value="">选择集群后加载</option>
              </select>
            </div>
            <div class="dist-form-row" style="display:flex;align-items:center;gap:10px">
              <label style="font-size:12px;color:var(--tx2);min-width:70px;font-weight:600">Pod</label>
              <div style="flex:1;display:flex;align-items:center;gap:8px">
                <select id="dist-pod-${toolId}" class="inp" style="flex:1" onchange="distOnPodChange(${toolId})">
                  <option value="">选择 Namespace 后加载</option>
                </select>
                <span id="dist-cap-${toolId}"></span>
              </div>
            </div>
            <div class="dist-form-row" style="display:flex;align-items:center;gap:10px">
              <label style="font-size:12px;color:var(--tx2);min-width:70px;font-weight:600">容器</label>
              <select id="dist-ctr-${toolId}" class="inp" onchange="distUpdateSubmitState(${toolId})">
                <option value="">选择 Pod 后加载</option>
              </select>
            </div>
            <div class="dist-form-row" style="display:flex;align-items:center;gap:10px">
              <label style="font-size:12px;color:var(--tx2);min-width:70px;font-weight:600">安装路径</label>
              <input id="dist-path-${toolId}" class="inp" value="${esc(installPath)}" oninput="distUpdateSubmitState(${toolId})">
            </div>
          </div>
        </div>
        <div class="dist-modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('distModal-${toolId}')">取消</button>
          <button class="btn btn-p btn-sm" id="dist-submit-${toolId}" onclick="confirmModalDistribute(${toolId}, '${toolType}')" disabled>
            确认分发
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    modal.addEventListener('click', event => { if (event.target === modal) modal.remove(); });

    // Render recent targets
    _renderRecentTargets(`distRecentList-${toolId}`);

    // Add click handlers for recent targets
    modal.querySelectorAll('.dist-recent-item').forEach(item => {
      item.onclick = () => {
        const idx = parseInt(item.dataset.index);
        const targets = _loadRecentTargets();
        if (targets[idx]) {
          _fillDistributeForm(toolId, targets[idx]);
        }
      };
    });
  };

  window.distOnClusterChange = async function(toolId) {
    const requestId = _nextDistRequestId(toolId);
    const clusterName = document.getElementById(`dist-cluster-${toolId}`)?.value;
    const nsSelect = document.getElementById(`dist-ns-${toolId}`);
    const podSelect = document.getElementById(`dist-pod-${toolId}`);
    const ctrSelect = document.getElementById(`dist-ctr-${toolId}`);
    if (!nsSelect) return;
    nsSelect.innerHTML = '<option value="">选择 Namespace...</option>';
    if (podSelect) podSelect.innerHTML = '<option value="">选择 Namespace 后加载</option>';
    if (ctrSelect) ctrSelect.innerHTML = '<option value="">选择 Pod 后加载</option>';
    distUpdateSubmitState(toolId);
    if (!clusterName) return;
    nsSelect.innerHTML = '<option value="">加载中...</option>';
    try {
      const nsData = await safeGet(`/clusters/${encodeURIComponent(clusterName)}/namespaces`);
      if (_distRequestIds.get(toolId) !== requestId ||
          document.getElementById(`dist-cluster-${toolId}`)?.value !== clusterName) return;
      const namespaces = nsData.namespaces || [];
      nsSelect.innerHTML = '<option value="">选择 Namespace...</option>' + namespaces.map(ns =>
        `<option value="${esc(ns)}">${esc(ns)}</option>`
      ).join('');
      if (!namespaces.length) nsSelect.innerHTML = '<option value="">无可访问的 Namespace</option>';
    } catch (e) {
      if (_distRequestIds.get(toolId) !== requestId) return;
      nsSelect.innerHTML = '<option value="">Namespace 加载失败</option>';
      toast(`加载 Namespace 失败：${e.message}`, 'err');
    }
  };

  window.distOnNsChange = async function(toolId) {
    const requestId = _nextDistRequestId(toolId);
    const clusterName = document.getElementById(`dist-cluster-${toolId}`)?.value;
    const ns = document.getElementById(`dist-ns-${toolId}`)?.value;
    const podSelect = document.getElementById(`dist-pod-${toolId}`);
    const ctrSelect = document.getElementById(`dist-ctr-${toolId}`);
    if (!podSelect) return;
    podSelect.innerHTML = '<option value="">选择 Namespace 后加载</option>';
    if (ctrSelect) ctrSelect.innerHTML = '<option value="">选择 Pod 后加载</option>';
    distUpdateSubmitState(toolId);
    if (!clusterName || !ns) return;
    podSelect.innerHTML = '<option value="">加载中...</option>';
    try {
      const podsData = await safeGet(`/clusters/${encodeURIComponent(clusterName)}/pods?namespace=${encodeURIComponent(ns)}`);
      if (_distRequestIds.get(toolId) !== requestId ||
          document.getElementById(`dist-cluster-${toolId}`)?.value !== clusterName ||
          document.getElementById(`dist-ns-${toolId}`)?.value !== ns) return;
      const pods = (podsData.pods || []).filter(p => p.phase === 'Running');
      podSelect.innerHTML = `<option value="">${pods.length ? '选择 Pod' : '此 Namespace 下没有 Running Pod'}</option>` +
        pods.map(p => {
          const ctrs = (p.containers || []).join(',');
          return `<option value="${esc(p.name)}" data-c="${esc(ctrs)}" data-phase="${esc(p.phase || '')}">${esc(p.name)} [${esc(p.phase || '')}]</option>`;
        }).join('');
      podSelect.onchange = function() {
        const opt = podSelect.options[podSelect.selectedIndex];
        const ctrs = (opt?.dataset.c || '').split(',').filter(Boolean);
        if (ctrSelect) {
          ctrSelect.innerHTML = ctrs.length > 1
            ? '<option value="">请选择容器...</option>' + ctrs.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')
            : '<option value="">默认容器</option>' + ctrs.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
          if (ctrs.length === 1) ctrSelect.value = ctrs[0];
        }
        distUpdateSubmitState(toolId);
        distOnPodChange(toolId);
      };
      distUpdateSubmitState(toolId);
    } catch (e) {
      if (_distRequestIds.get(toolId) !== requestId) return;
      podSelect.innerHTML = '<option value="">Pod 加载失败</option>';
      toast(`加载 Pod 失败：${e.message}`, 'err');
    }
  };

  window.distUpdateSubmitState = function(toolId) {
    const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value;
    const namespace = document.getElementById(`dist-ns-${toolId}`)?.value;
    const podSelect = document.getElementById(`dist-pod-${toolId}`);
    const containerSelect = document.getElementById(`dist-ctr-${toolId}`);
    const path = document.getElementById(`dist-path-${toolId}`)?.value?.trim() || '';
    const option = podSelect?.options[podSelect.selectedIndex];
    const containerCount = (option?.dataset.c || '').split(',').filter(Boolean).length;
    const container = containerSelect?.value || '';
    const ready = Boolean(cluster && namespace && podSelect?.value && path.startsWith('/') &&
      (containerCount <= 1 || container));
    const button = document.getElementById(`dist-submit-${toolId}`);
    if (button) button.disabled = !ready;
  };

  window.distOnPodChange = async function(toolId) {
    const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value;
    const ns = document.getElementById(`dist-ns-${toolId}`)?.value;
    const pod = document.getElementById(`dist-pod-${toolId}`)?.value;
    const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value;
    const capEl = document.getElementById(`dist-cap-${toolId}`);

    if (!capEl) return;
    capEl.innerHTML = '';

    distUpdateSubmitState(toolId);
    if (!cluster || !ns || !pod) return;

    try {
      const result = await safePost('/tasks/detect-capability', {
        cluster, namespace: ns, pod, container: ctr
      });
      if (document.getElementById(`dist-cluster-${toolId}`)?.value !== cluster ||
          document.getElementById(`dist-ns-${toolId}`)?.value !== ns ||
          document.getElementById(`dist-pod-${toolId}`)?.value !== pod) return;
      if (result.capability_level === 'pod+arthas') {
        capEl.innerHTML = '<span class="dist-cap-badge cap-ok">✅ Java + Arthas</span>';
      } else if (result.capability_level === 'pod-only') {
        capEl.innerHTML = `<span class="dist-cap-badge cap-warn">⚠️ ${result.java_version || 'Java'} (需 Arthas)</span>`;
      } else {
        capEl.innerHTML = '<span class="dist-cap-badge cap-error">❌ 不兼容</span>';
      }
    } catch (e) {
      if (document.getElementById(`dist-pod-${toolId}`)?.value === pod) {
        capEl.innerHTML = '<span class="dist-cap-badge cap-warn">能力检测暂不可用</span>';
      }
    }
  };

  function _fillDistributeForm(toolId, target) {
    const clusterEl = document.getElementById(`dist-cluster-${toolId}`);
    const nsEl = document.getElementById(`dist-ns-${toolId}`);
    const podEl = document.getElementById(`dist-pod-${toolId}`);
    const ctrEl = document.getElementById(`dist-ctr-${toolId}`);

    if (clusterEl) {
      clusterEl.value = target.cluster;
      distOnClusterChange(toolId).then(() => {
        if (nsEl) {
          nsEl.value = target.namespace;
          distOnNsChange(toolId).then(() => {
            if (podEl) {
              podEl.value = target.pod;
              podEl.onchange?.();
              if (ctrEl && target.container) ctrEl.value = target.container;
              distUpdateSubmitState(toolId);
            }
          });
        }
      });
    }
  }

  window.confirmModalDistribute = async function(toolId, toolType) {
    const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value || '';
    const ns = document.getElementById(`dist-ns-${toolId}`)?.value || 'default';
    const pod = document.getElementById(`dist-pod-${toolId}`)?.value || '';
    const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value || '';
    const path = document.getElementById(`dist-path-${toolId}`)?.value || '/tmp/arthas/arthas-boot.jar';
    const podOption = document.getElementById(`dist-pod-${toolId}`)?.selectedOptions?.[0];
    const containerCount = (podOption?.dataset.c || '').split(',').filter(Boolean).length;

    if (!cluster) { toast('请选择集群', 'warn'); return; }
    if (!ns) { toast('请选择 Namespace', 'warn'); return; }
    if (!pod) { toast('请选择 Pod', 'warn'); return; }
    if (containerCount > 1 && !ctr) { toast('此 Pod 有多个容器，请明确选择目标容器', 'warn'); return; }
    if (toolType === 'binary') {
      const tool = _allTools.binary.find(item => item.id === toolId);
      if (tool?.tool_type === 'arthas' && !path.trim().endsWith('.jar')) {
        toast('Arthas 安装路径必须以 .jar 结尾', 'warn');
        return;
      }
    }

    const payload = { tool_id: toolId, cluster, namespace: ns, pod, container: ctr, install_path: path };

    // Show progress modal
    const progressModal = document.createElement('div');
    progressModal.className = 'dist-modal-overlay';
    progressModal.id = 'distProgressModal';
    progressModal.innerHTML = `
      <div class="dist-modal" style="width:480px">
        <div class="dist-modal-header">
          <h3>分发进度</h3>
        </div>
        <div class="dist-modal-body">
          <div style="margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px">
              <span style="font-size:12px;color:var(--tx2)">正在分发到 ${esc(pod)}...</span>
              <span id="distProgressText" style="font-size:12px;color:var(--a)">进行中</span>
            </div>
            <div style="height:4px;background:rgba(0,0,0,.3);border-radius:2px;overflow:hidden">
              <div id="distProgressBar" style="height:100%;background:var(--a);border-radius:2px;width:60%;transition:width .3s"></div>
            </div>
          </div>
          <div id="distProgressLog" style="background:rgba(0,0,0,.3);border:1px solid rgba(40,61,90,.4);border-radius:6px;padding:12px;font-family:monospace;font-size:11px;max-height:150px;overflow-y:auto">
            <div style="color:var(--tx3);margin-bottom:4px">[${new Date().toLocaleTimeString()}] 开始分发...</div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(progressModal);
    closeModal(`distModal-${toolId}`);

    try {
      const startTime = Date.now();
      await safePost(`/tasks/tool-packages/${toolId}/distribute`, payload);
      const duration = ((Date.now() - startTime) / 1000).toFixed(1);

      _saveRecentTarget({ cluster, namespace: ns, pod, container: ctr });

      // Update progress
      const progressBar = document.getElementById('distProgressBar');
      const progressText = document.getElementById('distProgressText');
      const progressLog = document.getElementById('distProgressLog');

      if (progressBar) progressBar.style.width = '100%';
      if (progressText) { progressText.textContent = '成功'; progressText.style.color = '#34c759'; }
      if (progressLog) {
        progressLog.innerHTML += `<div style="color:#34c759">[${new Date().toLocaleTimeString()}] ✓ 分发完成 (${duration}s)</div>`;
      }

      setTimeout(() => {
        closeModal('distProgressModal');
        toast('分发成功', 'ok');
        loadDistHistory();
        loadBinaryTools();
      }, 1500);

    } catch (e) {
      const progressText = document.getElementById('distProgressText');
      const progressLog = document.getElementById('distProgressLog');

      if (progressText) { progressText.textContent = '失败'; progressText.style.color = '#ff3b30'; }
      if (progressLog) {
        progressLog.innerHTML += `<div style="color:#ff3b30">[${new Date().toLocaleTimeString()}] ✗ ${esc(e.message)}</div>`;
      }

      setTimeout(() => {
        closeModal('distProgressModal');
        toast(`分发失败：${e.message}`, 'err');
        loadDistHistory();
      }, 2000);
    }
  };

  // ═══════════════════════════════════════════════════════════════
  // 批量分发浮层
  // ═══════════════════════════════════════════════════════════════

  window.toolboxOpenBatchDistribute = function() {
    document.getElementById('batchDistModal')?.remove();
    _batchState = {selectedTools: [], selectedPods: []};
    _batchPodData = [];
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'batchDistModal';
    modal.innerHTML = `
      <div class="modal" style="width:680px;max-height:85vh">
        <div class="modal-header">
          <h3>批量分发工具</h3>
          <button class="btn-close" onclick="closeModal('batchDistModal')">✕</button>
        </div>
        <div class="modal-body">
          <!-- Step 1: 选择工具 -->
          <div style="margin-bottom:20px">
            <div style="font-size:12px;font-weight:600;color:var(--tx2);margin-bottom:10px;text-transform:uppercase">Step 1: 选择可分发工具包</div>
            <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(0,0,0,.2);border:1px solid rgba(40,61,90,.4);border-radius:6px;margin-bottom:10px">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input type="search" id="batchToolSearch" name="" placeholder="搜索工具..." oninput="filterBatchTools()" inputmode="search" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other" style="flex:1;background:none;border:none;color:var(--tx);font-size:12px;outline:none">
            </div>
            <div id="batchToolListBinary" style="display:flex;flex-direction:column;gap:8px">加载中...</div>
          </div>

          <!-- Step 2: 选择分发范围 -->
          <div style="margin-bottom:20px">
            <div style="font-size:12px;font-weight:600;color:var(--tx2);margin-bottom:10px;text-transform:uppercase">Step 2: 集群 → Namespace → Pod</div>
            <div id="batchTargetPod">
              <div style="display:flex;gap:12px;margin-bottom:10px">
                <div style="flex:1">
                  <label style="font-size:11px;color:var(--tx2);display:block;margin-bottom:4px">集群</label>
                  <select id="batchCluster" class="inp" onchange="batchOnClusterChange()"><option value="">选择集群...</option></select>
                </div>
                <div style="flex:1">
                  <label style="font-size:11px;color:var(--tx2);display:block;margin-bottom:4px">Namespace</label>
                  <select id="batchNamespace" class="inp" onchange="loadBatchPods()"><option value="">选择集群后加载</option></select>
                </div>
              </div>
              <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(0,0,0,.2);border:1px solid rgba(40,61,90,.4);border-radius:6px;margin-bottom:8px">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input type="search" id="batchPodSearch" name="" placeholder="搜索 Pod..." oninput="batchFilterPods()" inputmode="search" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" data-lpignore="true" data-1p-ignore="true" data-bwignore="true" data-form-type="other" style="flex:1;background:none;border:none;color:var(--tx);font-size:12px;outline:none">
              </div>
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                <button class="btn btn-g btn-sm" onclick="batchSelectVisible(true)">选择本页</button>
                <button class="btn btn-g btn-sm" onclick="batchSelectVisible(false)">清除本页</button>
                <span id="batchSelectedCount" style="margin-left:auto;font-size:11px;color:var(--tx2)">已选 0 个 Pod</span>
              </div>
              <div id="batchPodList" style="display:flex;flex-direction:column;gap:6px;max-height:200px;overflow-y:auto">
                <div style="text-align:center;color:var(--tx2);font-size:12px;padding:20px">请先选择集群和 Namespace</div>
              </div>
            </div>
          </div>

          <!-- 分发摘要 -->
          <div style="background:rgba(0,122,255,.08);border:1px solid rgba(0,122,255,.2);border-radius:8px;padding:12px">
            <div style="font-size:12px;font-weight:600;color:var(--a);margin-bottom:4px">分发摘要</div>
            <div id="batchSummary" style="font-size:12px;color:var(--tx2)">
              将 <b style="color:var(--tx)">0</b> 个工具分发到 <b style="color:var(--tx)">0</b> 个目标
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-g btn-sm" onclick="closeModal('batchDistModal')">取消</button>
          <button class="btn btn-p btn-sm" onclick="executeBatchDistribute()">确认分发</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    if (window.ConnectionPool && typeof ConnectionPool.hardenSearchInput === 'function') {
      modal.querySelectorAll('input[type=search][data-form-type="other"]').forEach(input => {
        ConnectionPool.hardenSearchInput(input);
      });
    }
    loadBatchToolLists();
    initBatchClusterSelects();
  };

  let _batchState = { selectedTools: [], selectedPods: [] };

  async function loadBatchToolLists() {
    try {
      const data = await safeGet('/tasks/tool-packages');
      const packages = data.packages || [];
      const render = items => items.map(p => `
        <label class="batch-item" data-search="${esc(`${p.file_name || p.name} ${p.tool_type} ${p.version || ''}`.toLowerCase())}">
          <input type="checkbox" value="${Number(p.id)}" data-name="${esc(p.file_name || p.name)}"
            ${p.status === 'missing' ? 'disabled title="工具文件缺失，请先校验或重新上传"' : ''}
            data-path="${esc(p.install_path || '')}" onchange="batchUpdateTools()">
          <span class="batch-item-name">${esc(p.file_name || p.name)}</span>
          <span class="batch-item-meta">${esc(p.tool_type)} · ${esc(p.version || '-')} · ${esc(p.install_path || '')}${p.status === 'missing' ? ' · 文件缺失' : ''}</span>
        </label>
      `).join('') || '<div class="sb-empty">暂无可分发工具</div>';
      const binary = document.getElementById('batchToolListBinary');
      if (binary) binary.innerHTML = render(packages);
    } catch (e) {
      console.error('加载工具列表失败:', e);
      toast(`加载工具列表失败: ${e.message}`, 'err');
    }
  }

  window.batchUpdateTools = function() {
    _batchState.selectedTools = Array.from(
      document.querySelectorAll('#batchDistModal #batchToolListBinary input:checked')
    ).map(input => ({
      id: Number(input.value),
      name: input.dataset.name || input.value,
      install_path: input.dataset.path || '',
    }));
    renderBatchSummary();
  };

  window.filterBatchTools = function() {
    const query = (document.getElementById('batchToolSearch')?.value || '').trim().toLowerCase();
    document.querySelectorAll('#batchDistModal .batch-item[data-search]').forEach(item => {
      item.style.display = !query || item.dataset.search.includes(query) ? '' : 'none';
    });
  };

  async function _loadBatchClusters() {
    const data = await safeGet('/clusters');
    return data.clusters || [];
  }

  async function _loadBatchNamespaces(cluster) {
    const data = await safeGet(`/clusters/${encodeURIComponent(cluster)}/namespaces`);
    return data.namespaces || [];
  }

  async function _loadBatchPods(cluster, namespace) {
    const data = await safeGet(`/clusters/${encodeURIComponent(cluster)}/pods?namespace=${encodeURIComponent(namespace)}`);
    return data.pods || [];
  }

  window.initBatchClusterSelects = async function() {
    const clusterSelect = document.getElementById('batchCluster');
    if (!clusterSelect) return;
    clusterSelect.innerHTML = '<option value="">加载集群...</option>';
    try {
      const clusters = await _loadBatchClusters();
      clusterSelect.innerHTML = '<option value="">选择集群...</option>' +
        clusters.map(c => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
      if (!clusters.length) clusterSelect.innerHTML = '<option value="">没有可访问的集群</option>';
    } catch (e) {
      clusterSelect.innerHTML = '<option value="">集群加载失败</option>';
      toast(`加载集群失败: ${e.message}`, 'err');
    }
  };

  window.batchOnClusterChange = async function() {
    const cluster = document.getElementById('batchCluster')?.value || '';
    const namespaceSelect = document.getElementById('batchNamespace');
    const podList = document.getElementById('batchPodList');
    if (!namespaceSelect || !podList) return;
    _batchPodRequestId++;
    namespaceSelect.innerHTML = '<option value="">加载 Namespace...</option>';
    podList.innerHTML = '<div class="sb-empty">请先选择 Namespace</div>';
    _batchPodData = [];
    try {
      const namespaces = cluster ? await _loadBatchNamespaces(cluster) : [];
      namespaceSelect.innerHTML = '<option value="">选择 Namespace...</option>' +
        namespaces.map(ns => `<option value="${esc(ns)}">${esc(ns)}</option>`).join('');
      if (cluster && namespaces.length === 0) {
        namespaceSelect.innerHTML = '<option value="">没有可访问的 Namespace</option>';
      }
    } catch (e) {
      namespaceSelect.innerHTML = '<option value="">Namespace 加载失败</option>';
      toast(`加载 Namespace 失败: ${e.message}`, 'err');
    }
  };

  window.loadBatchPods = function() {
    const cluster = document.getElementById('batchCluster')?.value || '';
    const namespace = document.getElementById('batchNamespace')?.value || '';
    if (cluster && namespace) {
      loadBatchPodList(cluster, namespace);
    } else {
      _batchPodRequestId++;
      _batchPodData = [];
      const podList = document.getElementById('batchPodList');
      if (podList) podList.innerHTML = '<div class="sb-empty">请先选择 Namespace</div>';
    }
  };

  window.executeBatchDistribute = function() {
    window.batchExecute();
  };

  let _batchPodData = [];
  let _batchPodRequestId = 0;

  async function loadBatchPodList(cluster, namespace) {
    const container = document.getElementById('batchPodList');
    if (!container) return;
    const requestId = ++_batchPodRequestId;
    container.innerHTML = '<div class="sb-empty">加载 Pod...</div>';
    try {
      const pods = await _loadBatchPods(cluster, namespace);
      if (requestId !== _batchPodRequestId) return;
      _batchPodData = pods.map(p => ({
        cluster,
        namespace,
        pod: p.name,
        phase: p.phase || 'Unknown',
        containers: p.containers || [],
      }));
      _renderBatchPodList(_batchPodData);
    } catch (e) {
      if (requestId !== _batchPodRequestId) return;
      _batchPodData = [];
      container.innerHTML = `<div class="sb-empty">加载 Pod 失败: ${esc(e.message)}</div>`;
      toast(`加载 Pod 失败: ${e.message}`, 'err');
    }
  }

  function _renderBatchPodList(pods) {
    const container = document.getElementById('batchPodList');
    if (!container) return;
    const query = (document.getElementById('batchPodSearch')?.value || '').trim().toLowerCase();
    const filtered = pods.filter(p => !query || p.pod.toLowerCase().includes(query));
    if (pods.length === 0) {
      container.innerHTML = '<div class="sb-empty">此 Namespace 下没有 Pod</div>';
      return;
    }
    const selected = new Map(_batchState.selectedPods.map(target => [
      `${target.cluster}/${target.namespace}/${target.pod}`, target
    ]));
    container.innerHTML = filtered.map(p => {
      const key = `${p.cluster}/${p.namespace}/${p.pod}`;
      const prior = selected.get(key);
      const target = {
        cluster: p.cluster,
        namespace: p.namespace,
        pod: p.pod,
        container: prior?.container || '',
        container_count: p.containers.length,
      };
      const options = p.containers.length > 1
        ? `        <select class="inp batch-pod-container" onclick="event.stopPropagation()" onchange="batchUpdatePods()">
             <option value="">选择容器...</option>
             ${p.containers.map(name => `<option value="${esc(name)}" ${target.container === name ? 'selected' : ''}>${esc(name)}</option>`).join('')}
           </select>`
        : '';
      if (p.containers.length === 1 && !target.container) target.container = p.containers[0];
      const eligible = p.phase === 'Running';
      return `
      <label class="batch-item" style="${eligible ? '' : 'opacity:.55'}">
        <input type="checkbox" value="${encodeURIComponent(JSON.stringify(target))}" ${prior ? 'checked' : ''} ${eligible ? '' : 'disabled'} onchange="batchUpdatePods()">
        <span class="batch-item-name">${esc(p.pod)}</span>
        <span class="batch-item-meta">${esc(p.phase)}${p.containers.length ? ` · ${p.containers.length} 容器` : ''}${eligible ? '' : ' · 不可分发'}</span>
        ${options}
      </label>
    `;
    }).join('') || '<div class="sb-empty">没有匹配的 Pod</div>';
  }

  window.batchFilterPods = function() {
    _renderBatchPodList(_batchPodData);
  };

  window.batchUpdatePods = function() {
    const renderedKeys = new Set(
      Array.from(document.querySelectorAll('#batchPodList input[type=checkbox]'))
        .map(input => {
          const target = JSON.parse(decodeURIComponent(input.value));
          return `${target.cluster}/${target.namespace}/${target.pod}`;
        })
    );
    const selectedElsewhere = _batchState.selectedPods.filter(target =>
      !renderedKeys.has(`${target.cluster}/${target.namespace}/${target.pod}`));
    const selectedHere = Array.from(document.querySelectorAll('#batchPodList input[type=checkbox]:checked'))
      .map(checkbox => {
        const target = JSON.parse(decodeURIComponent(checkbox.value));
        const containerSelect = checkbox.closest('label')?.querySelector('.batch-pod-container');
        if (containerSelect) target.container = containerSelect.value;
        return target;
      });
    _batchState.selectedPods = [...selectedElsewhere, ...selectedHere];
    const count = document.getElementById('batchSelectedCount');
    if (count) count.textContent = `已选 ${_batchState.selectedPods.length} 个 Pod`;
    renderBatchSummary();
  };

  window.batchSelectVisible = function(checked) {
    document.querySelectorAll('#batchPodList input[type=checkbox]:not(:disabled)').forEach(input => {
      input.checked = checked;
    });
    batchUpdatePods();
  };

  function renderBatchSummary() {
    const el = document.getElementById('batchSummary');
    if (!el) return;
    const toolCount = _batchState.selectedTools.length;
    const podCount = _batchState.selectedPods.length;
    const total = toolCount * podCount;
    const scopes = [...new Set(_batchState.selectedPods.map(
      target => `${target.cluster}/${target.namespace}`))];
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
      <div style="margin-top:8px">范围: ${esc(scopes.join('、') || '未选择')} · 单次上限 200 次分发</div>
    `;
  }

  window.batchExecute = async function() {
    const btn = document.querySelector('#batchDistModal .modal-footer .btn-p');
    const total = _batchState.selectedTools.length * _batchState.selectedPods.length;
    if (!_batchState.selectedTools.length) { toast('请至少选择一个工具', 'warn'); return; }
    if (!_batchState.selectedPods.length) { toast('请至少选择一个 Pod', 'warn'); return; }
    if (total > 200) { toast('单次最多分发 200 次，请缩小范围后重试', 'warn'); return; }
    const missingContainer = _batchState.selectedPods.find(target => {
      const pod = _batchPodData.find(p =>
        p.cluster === target.cluster && p.namespace === target.namespace && p.pod === target.pod);
      return target.container_count > 1 && !target.container;
    });
    if (missingContainer) {
      toast(`请为多容器 Pod ${missingContainer.pod} 选择目标容器`, 'warn');
      return;
    }
    const targetSummary = _batchState.selectedPods.map(target =>
      `${target.cluster}/${target.namespace}/${target.pod}${target.container ? `:${target.container}` : ''}`
    ).join('\n');
    if (!window.confirm(
      `即将分发 ${_batchState.selectedTools.length} 个工具到 ${_batchState.selectedPods.length} 个 Pod，共 ${total} 次操作。\n\n目标 Pod:\n${targetSummary}\n\n确认继续？`
    )) return;
    if (btn) { btn.disabled = true; btn.textContent = '分发中...'; }
    const progressEl = document.getElementById('batchSummary');
    if (progressEl) progressEl.innerHTML = '<div class="batch-progress-bar"><div class="batch-progress-fill" style="width:30%"></div></div>';
    try {
      const result = await safePost('/tasks/batch-distribute', {
        tool_ids: _batchState.selectedTools.map(t => t.id),
        targets: _batchState.selectedPods.map(({cluster, namespace, pod, container}) =>
          ({cluster, namespace, pod, container})),
        install_paths: Object.fromEntries(
          _batchState.selectedTools.map(tool => [tool.id, tool.install_path])
        ),
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
                  <span>${esc(r.tool)} → ${esc(r.cluster)}/${esc(r.namespace)}/${esc(r.pod)}${r.container ? ` (${esc(r.container)})` : ''}</span>
                  ${r.install_path ? `<span class="batch-path">${esc(r.install_path)}</span>` : ''}
                  ${r.error ? `<span class="batch-error">${esc(r.error)}</span>` : ''}
                  ${r.duration_ms ? `<span class="batch-duration">${r.duration_ms}ms</span>` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }
      if (result.summary?.failed) {
        toast(`批量分发完成：${result.summary.success || 0} 成功，${result.summary.failed} 失败`, 'warn');
      } else {
        toast('批量分发完成', 'ok');
      }
      loadDistHistory();
    } catch (e) {
      if (progressEl) progressEl.innerHTML = `<div style="display:flex;align-items:center;gap:6px;color:var(--a5);font-size:13px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ${esc(e.message)}</div>`;
      toast(`批量分发失败：${e.message}`, 'err');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '确认分发'; }
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

  function formatFileSize(bytes) {
    const size = Number(bytes);
    if (!Number.isFinite(size) || size <= 0) return '大小未知';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`;
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
