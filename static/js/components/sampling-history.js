/**
 * Sampling History — Redesigned history panel for profiler task records.
 *
 * Design: "Ops Control Terminal" — data-dense, monospace, with SVG icons,
 * search/filter toolbar, date-grouped sections, expandable detail rows.
 *
 * Usage:
 *   SamplingHistory.mount(containerEl, { mode: 'global' | 'inline', connectionId? })
 *   SamplingHistory.refresh()
 *   SamplingHistory.destroy()
 */

const SamplingHistory = (() => {
  // ── SVG Icons ──────────────────────────────────────────────────────────
  const ICON = {
    search: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/></svg>`,
    filter: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>`,
    refresh: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
    check: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M20 6 9 17l-5-5"/></svg>`,
    x: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`,
    loader: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>`,
    clock: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    download: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
    stop: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`,
    chevron: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>`,
    calendar: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    empty: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" opacity=".25"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>`,
    sort: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/><path d="m21 16-4 4-4-4"/><path d="M17 20V4"/></svg>`,
    cpu: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>`,
    flame: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>`,
    layers: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
    box: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
  };

  // ── Status / Type Config ───────────────────────────────────────────────
  const STATUS = {
    completed: { icon: ICON.check, label: '完成', cls: 'sh-st-ok' },
    failed:    { icon: ICON.x,     label: '失败', cls: 'sh-st-fail' },
    running:   { icon: ICON.loader, label: '运行中', cls: 'sh-st-run', spin: true },
    starting:  { icon: ICON.loader, label: '启动中', cls: 'sh-st-run', spin: true },
    stopped:   { icon: ICON.stop,  label: '已中断', cls: 'sh-st-stop' },
    pending:   { icon: ICON.clock,  label: '等待中', cls: 'sh-st-pend' },
  };

  const TYPE_ICON = {
    profiler: ICON.flame,
    jfr: ICON.layers,
    threaddump: ICON.cpu,
    heapdump: ICON.box,
  };

  const EVENT_LABELS = {
    threaddump: '线程转储', heapdump: '堆转储', cpu: 'CPU 采样',
    alloc: '内存分配', lock: '锁竞争', wall: 'Wall 时间',
    default: 'JFR 默认', profile: 'JFR Profile',
  };

  const MODE_LABELS = {
    profiler: 'Profiler', jfr: 'JFR', threaddump: 'Thread Dump', heapdump: 'Heap Dump',
  };

  // ── State ──────────────────────────────────────────────────────────────
  let _root = null;        // root container element
  let _mode = 'global';    // 'global' | 'inline'
  let _connId = null;       // connection filter (inline mode)
  let _allTasks = [];       // raw task data from API
  let _filtered = [];       // after search/filter
  let _page = 0;
  let _pageSize = 20;
  let _search = '';
  let _statusFilter = 'all';
  let _typeFilter = 'all';
  let _expandedId = null;   // currently expanded task id
  let _sortField = 'created_at';
  let _sortDir = 'desc';
  let _selectedIds = new Set(); // selected task ids for batch operations
  let _batchMode = false;   // batch mode enabled
  let _focusedIndex = -1;   // keyboard focused row index
  let _showShortcuts = false; // show shortcuts panel

  // ── Helpers ────────────────────────────────────────────────────────────
  const esc = s => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  function fmtTsShort(input) {
    if (!input) return '—';
    try {
      const d = new Date(isNaN(Number(input)) ? input : (Number(input) > 1e12 ? Number(input) : Number(input) * 1000));
      if (isNaN(d.getTime())) return String(input);
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
      if (d.toDateString() === now.toDateString()) return `今天 ${hm}`;
      const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
      if (d.toDateString() === yesterday.toDateString()) return `昨天 ${hm}`;
      return `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
    } catch { return String(input); }
  }

  function fmtTsFull(input) {
    if (!input) return '—';
    try {
      const d = new Date(isNaN(Number(input)) ? input : (Number(input) > 1e12 ? Number(input) : Number(input) * 1000));
      if (isNaN(d.getTime())) return String(input);
      const pad = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } catch { return String(input); }
  }

  function dateKey(input) {
    if (!input) return '未知日期';
    try {
      const d = new Date(isNaN(Number(input)) ? input : (Number(input) > 1e12 ? Number(input) : Number(input) * 1000));
      if (isNaN(d.getTime())) return '未知日期';
      const now = new Date();
      if (d.toDateString() === now.toDateString()) return '今天';
      const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
      if (d.toDateString() === yesterday.toDateString()) return '昨天';
      const pad = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    } catch { return '未知日期'; }
  }

  function durationDisplay(t) {
    const mode = t.config?.mode || t.mode || 'profiler';
    const dur = t.config?.duration || t.duration || 0;
    if (mode === 'threaddump' || mode === 'heapdump' || dur === 0) return '—';
    if (dur >= 60) return `${Math.floor(dur / 60)}m${dur % 60 ? `${dur % 60}s` : ''}`;
    return `${dur}s`;
  }

  function formatDisplay(t) {
    const mode = t.config?.mode || t.mode || 'profiler';
    const fmt = t.config?.format || t.format || 'html';
    if (mode === 'threaddump') return 'TXT';
    if (mode === 'heapdump') return 'HPROF';
    return fmt.toUpperCase();
  }

  // ── Filter + Sort Pipeline ─────────────────────────────────────────────
  function applyFilterSort() {
    let tasks = [..._allTasks];

    // Status filter
    if (_statusFilter !== 'all') {
      tasks = tasks.filter(t => t.status === _statusFilter);
    }

    // Type filter
    if (_typeFilter !== 'all') {
      tasks = tasks.filter(t => (t.config?.mode || 'profiler') === _typeFilter);
    }

    // Search
    if (_search) {
      const q = _search.toLowerCase();
      tasks = tasks.filter(t => {
        const pod = (t.config?.pod || t.pod_name || '').toLowerCase();
        const ns = (t.config?.namespace || t.namespace || '').toLowerCase();
        const cluster = (t.config?.cluster || t.cluster_name || '').toLowerCase();
        const event = (t.config?.event || '').toLowerCase();
        const mode = (t.config?.mode || '').toLowerCase();
        const id = (t.id || '').toLowerCase();
        const user = (t.username || '').toLowerCase();
        return pod.includes(q) || ns.includes(q) || cluster.includes(q) ||
               event.includes(q) || mode.includes(q) || id.includes(q) || user.includes(q);
      });
    }

    // Sort
    tasks.sort((a, b) => {
      let va, vb;
      if (_sortField === 'created_at') {
        va = new Date(a.created_at || 0).getTime();
        vb = new Date(b.created_at || 0).getTime();
      } else if (_sortField === 'status') {
        const order = { running: 0, starting: 0, pending: 1, completed: 2, failed: 3, stopped: 4 };
        va = order[a.status] ?? 5;
        vb = order[b.status] ?? 5;
      } else if (_sortField === 'type') {
        va = (a.config?.mode || 'profiler');
        vb = (b.config?.mode || 'profiler');
      } else if (_sortField === 'duration') {
        va = a.config?.duration || a.duration || 0;
        vb = b.config?.duration || b.duration || 0;
      } else {
        va = a[_sortField] || '';
        vb = b[_sortField] || '';
      }
      if (va < vb) return _sortDir === 'asc' ? -1 : 1;
      if (va > vb) return _sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    _filtered = tasks;
    _page = 0;
  }

  // ── Group tasks by date ────────────────────────────────────────────────
  function groupByDate(tasks) {
    const groups = new Map();
    for (const t of tasks) {
      const key = dateKey(t.created_at);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(t);
    }
    return groups;
  }

  // ── Update batch bar visibility ───────────────────────────────────────
  function updateBatchBar() {
    const batchBar = _root.querySelector('.sh-batch-bar');
    const selectAll = _root.querySelector('#shSelectAll');

    if (_selectedIds.size > 0 && !batchBar) {
      render(); // Re-render to show batch bar
    } else if (_selectedIds.size === 0 && batchBar) {
      render(); // Re-render to hide batch bar
    }

    // Update select all checkbox state
    if (selectAll) {
      selectAll.checked = _selectedIds.size === _filtered.length && _filtered.length > 0;
      selectAll.indeterminate = _selectedIds.size > 0 && _selectedIds.size < _filtered.length;
    }
  }

  // ── Render: Toolbar ────────────────────────────────────────────────────
  function renderToolbar() {
    const statusBtns = [
      { val: 'all', label: '全部' },
      { val: 'completed', label: '完成' },
      { val: 'running', label: '运行中' },
      { val: 'failed', label: '失败' },
    ];

    const typeOptions = [
      { val: 'all', label: '全部类型' },
      { val: 'profiler', label: 'Profiler' },
      { val: 'jfr', label: 'JFR' },
      { val: 'threaddump', label: 'Thread Dump' },
      { val: 'heapdump', label: 'Heap Dump' },
    ];

    const hasSelection = _selectedIds.size > 0;

    return `
      <div class="sh-toolbar" role="toolbar" aria-label="筛选和搜索工具">
        <div class="sh-toolbar-row">
          <div class="sh-batch-toggle">
            <button class="sh-btn-batch ${_batchMode ? 'on' : ''}" id="shBatchToggle" title="批量操作模式" aria-pressed="${_batchMode}">
              ${ICON.filter}
              <span>批量</span>
            </button>
          </div>
          <div class="sh-search" role="search">
            <span class="sh-search-icon" aria-hidden="true">${ICON.search}</span>
            <input type="text" class="sh-search-input" id="shSearchInput"
              placeholder="搜索 Pod / 命名空间 / 集群..." value="${esc(_search)}"
              spellcheck="false" autocomplete="new-password" name="sh-search-filter"
              aria-label="搜索任务" />
            ${_search ? '<button class="sh-search-clear" id="shSearchClear" aria-label="清除搜索">&times;</button>' : ''}
          </div>
          <div class="sh-toolbar-actions">
            <select class="sh-select" id="shTypeFilter">
              ${typeOptions.map(o => `<option value="${o.val}" ${_typeFilter === o.val ? 'selected' : ''}>${o.label}</option>`).join('')}
            </select>
            <button class="sh-btn-icon" id="shRefreshBtn" title="刷新">${ICON.refresh}</button>
          </div>
        </div>

        ${_batchMode && hasSelection ? `
          <div class="sh-batch-bar">
            <div class="sh-batch-info">
              <span class="sh-batch-count">${_selectedIds.size}</span> 个任务已选中
            </div>
            <div class="sh-batch-actions">
              <button class="sh-btn-batch-action sh-btn-batch-export" id="shBatchExport">
                ${ICON.download} 导出选中
              </button>
              <button class="sh-btn-batch-action sh-btn-batch-delete" id="shBatchDelete">
                ${ICON.x} 删除选中
              </button>
              <button class="sh-btn-batch-action sh-btn-batch-clear" id="shBatchClear">
                取消选择
              </button>
            </div>
          </div>
        ` : ''}

        <div class="sh-toolbar-row">
          <div class="sh-status-tabs" id="shStatusTabs">
            ${statusBtns.map(b => `
              <button class="sh-status-tab ${_statusFilter === b.val ? 'on' : ''}" data-val="${b.val}">
                ${b.label}
                ${b.val !== 'all' ? `<span class="sh-status-count" data-status-count="${b.val}">0</span>` : ''}
              </button>
            `).join('')}
          </div>
          <div class="sh-sort-group">
            <button class="sh-sort-btn ${_sortField === 'created_at' ? 'on' : ''}" data-sort="created_at">
              时间 ${_sortField === 'created_at' ? (_sortDir === 'desc' ? '↓' : '↑') : ''}
            </button>
            <button class="sh-sort-btn ${_sortField === 'status' ? 'on' : ''}" data-sort="status">
              状态 ${_sortField === 'status' ? (_sortDir === 'desc' ? '↓' : '↑') : ''}
            </button>
          </div>
          ${_batchMode ? `
            <div class="sh-select-all">
              <label class="sh-checkbox-label">
                <input type="checkbox" id="shSelectAll" ${_selectedIds.size === _filtered.length && _filtered.length > 0 ? 'checked' : ''} />
                <span>全选</span>
              </label>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  // ── Render: Task Row ───────────────────────────────────────────────────
  function renderTaskRow(t) {
    const st = STATUS[t.status] || STATUS.pending;
    const mode = t.config?.mode || 'profiler';
    const event = t.config?.event || '';
    const typeIcon = TYPE_ICON[mode] || ICON.flame;
    const modeLabel = MODE_LABELS[mode] || mode;
    const eventLabel = EVENT_LABELS[event] || event;
    const pod = t.config?.pod || t.pod_name || '—';
    const ns = t.config?.namespace || t.namespace || '—';
    const cluster = t.config?.cluster || t.cluster_name || '—';
    const isExpanded = _expandedId === t.id;
    const isRunning = t.status === 'running' || t.status === 'starting';
    const isFailed = t.status === 'failed';
    const isSelected = _selectedIds.has(t.id);

    // Determine row classes
    let rowClasses = 'sh-row';
    if (isExpanded) rowClasses += ' expanded';
    if (isRunning) rowClasses += ' sh-row-active sh-row-running';
    if (isFailed) rowClasses += ' sh-row-failed';
    if (isSelected) rowClasses += ' sh-row-selected';

    // Status label class
    const statusLabelClass = t.status === 'completed' ? 'ok' :
                             t.status === 'failed' ? 'fail' :
                             isRunning ? 'run' : 'pend';

    // Primary row
    let html = `
      <div class="${rowClasses}" data-task-id="${esc(t.id)}" role="listitem" aria-label="${modeLabel} 任务 - ${esc(pod)} - ${st.label}" ${isExpanded ? 'aria-expanded="true"' : ''}>
        <div class="sh-row-main" role="button" tabindex="0" aria-label="展开任务详情">
          ${_batchMode ? `
            <label class="sh-checkbox-wrapper" onclick="event.stopPropagation()">
              <input type="checkbox" class="sh-checkbox sh-row-checkbox" data-id="${esc(t.id)}" ${isSelected ? 'checked' : ''} aria-label="选择任务" />
            </label>
          ` : ''}
          <span class="sh-chevron ${isExpanded ? 'open' : ''}" aria-hidden="true">${ICON.chevron}</span>
          <span class="sh-status-dot ${st.cls} ${st.spin ? 'spin' : ''}" title="${st.label}" aria-label="状态: ${st.label}">${st.icon}</span>
          <span class="sh-type-badge" title="${modeLabel}" aria-label="类型: ${modeLabel}">
            ${typeIcon}
            <span>${modeLabel}</span>
          </span>
          <span class="sh-pod" title="${esc(pod)}">${esc(pod)}</span>
          <span class="sh-status-label ${statusLabelClass}" aria-label="状态: ${st.label}">${st.label}</span>
          <span class="sh-event-tag">${esc(eventLabel)}</span>
          <span class="sh-duration">${durationDisplay(t)}</span>
          <span class="sh-time">${fmtTsShort(t.created_at)}</span>
          <span class="sh-row-actions">
            ${t.has_file ? `<button class="sh-btn-dl" data-dl="${esc(t.id)}" data-fn="${esc(t.file_name || 'output')}" title="下载 ${esc(t.file_name || '')}" aria-label="下载文件">${ICON.download}</button>` : ''}
            ${isRunning ? `<button class="sh-btn-stop" data-stop="${esc(t.id)}" title="中断任务" aria-label="中断任务">${ICON.stop}</button>` : ''}
          </span>
        </div>`;

    // Expanded detail
    if (isExpanded) {
      html += `
        <div class="sh-row-detail">
          <div class="sh-detail-header">
            <span class="sh-detail-kicker">任务详情</span>
            <span class="sh-detail-id">#${esc(t.id.substring(0, 8))}</span>
          </div>
          <div class="sh-detail-grid">
            <div class="sh-detail-item">
              <span class="sh-detail-label">集群</span>
              <span class="sh-detail-value sh-cluster">${esc(cluster)}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">命名空间</span>
              <span class="sh-detail-value">${esc(ns)}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">Pod</span>
              <span class="sh-detail-value sh-mono">${esc(pod)}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">采样事件</span>
              <span class="sh-detail-value sh-event">${esc(eventLabel)}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">输出格式</span>
              <span class="sh-detail-value sh-tag">${esc(formatDisplay(t))}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">采样时长</span>
              <span class="sh-detail-value">${durationDisplay(t)}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">创建时间</span>
              <span class="sh-detail-value">${fmtTsFull(t.created_at)}</span>
            </div>
            <div class="sh-detail-item">
              <span class="sh-detail-label">更新时间</span>
              <span class="sh-detail-value">${fmtTsFull(t.updated_at)}</span>
            </div>
            ${t.username ? `<div class="sh-detail-item">
              <span class="sh-detail-label">操作人</span>
              <span class="sh-detail-value sh-user">@${esc(t.username)}</span>
            </div>` : ''}
            ${t.message ? `<div class="sh-detail-item sh-detail-full">
              <span class="sh-detail-label">消息</span>
              <span class="sh-detail-value sh-msg ${t.status === 'failed' ? 'sh-msg-err' : ''}">${esc(t.message)}</span>
            </div>` : ''}
            ${t.has_file ? `<div class="sh-detail-item sh-detail-full">
              <span class="sh-detail-label">输出文件</span>
              <span class="sh-detail-value sh-mono sh-file">${esc(t.file_name || t.output_path || '—')}</span>
            </div>` : ''}
          </div>
          <div class="sh-detail-actions">
            ${t.has_file ? `<button class="sh-btn-action sh-btn-dl-action" data-dl="${esc(t.id)}" data-fn="${esc(t.file_name || 'output')}">
              ${ICON.download} 下载结果
            </button>` : ''}
            ${isRunning ? `<button class="sh-btn-action sh-btn-stop-action" data-stop="${esc(t.id)}">
              ${ICON.stop} 中断任务
            </button>` : ''}
          </div>
        </div>`;
    }

    html += `</div>`;
    return html;
  }

  // ── Render: Data List ──────────────────────────────────────────────────
  function renderList() {
    const total = _filtered.length;
    const totalPages = Math.ceil(total / _pageSize) || 1;
    const start = _page * _pageSize;
    const end = Math.min(start + _pageSize, total);
    const pageTasks = _filtered.slice(start, end);

    // Empty state
    if (total === 0) {
      const hasFilter = _search || _statusFilter !== 'all' || _typeFilter !== 'all';
      return `
        <div class="sh-empty">
          ${ICON.empty}
          <div class="sh-empty-title">${hasFilter ? '没有匹配的任务' : '暂无采样任务'}</div>
          <div class="sh-empty-sub">${hasFilter ? '尝试调整筛选条件' : '在采样中心创建任务后，记录将显示在这里'}</div>
          ${hasFilter ? '<button class="sh-btn-action" id="shClearFilters">清除筛选</button>' : ''}
        </div>
      `;
    }

    // Group by date
    const groups = groupByDate(pageTasks);
    let html = '<div class="sh-list">';

    for (const [dateLabel, tasks] of groups) {
      html += `
        <div class="sh-date-group">
          <div class="sh-date-header">
            <span class="sh-date-icon">${ICON.calendar}</span>
            <span class="sh-date-label">${esc(dateLabel)}</span>
            <span class="sh-date-count">${tasks.length} 条</span>
          </div>
          ${tasks.map(renderTaskRow).join('')}
        </div>
      `;
    }

    html += '</div>';

    // Pagination
    html += `
      <div class="sh-pagination">
        <div class="sh-page-info">
          显示 <strong>${start + 1}–${end}</strong> / 共 <strong>${total}</strong> 条
        </div>
        <div class="sh-page-controls">
          <select class="sh-select sh-page-size" id="shPageSize">
            <option value="10" ${_pageSize === 10 ? 'selected' : ''}>10 条/页</option>
            <option value="20" ${_pageSize === 20 ? 'selected' : ''}>20 条/页</option>
            <option value="50" ${_pageSize === 50 ? 'selected' : ''}>50 条/页</option>
          </select>
          <button class="sh-page-btn" id="shPagePrev" ${_page <= 0 ? 'disabled' : ''}>&lsaquo;</button>
          <span class="sh-page-num">${_page + 1} / ${totalPages}</span>
          <button class="sh-page-btn" id="shPageNext" ${_page >= totalPages - 1 ? 'disabled' : ''}>&rsaquo;</button>
        </div>
      </div>
    `;

    return html;
  }

  // ── Render: Stats Bar ──────────────────────────────────────────────────
  function renderStats() {
    const counts = { all: _allTasks.length, completed: 0, running: 0, failed: 0, stopped: 0, starting: 0, pending: 0 };
    const typeCounts = { profiler: 0, jfr: 0, threaddump: 0, heapdump: 0 };

    for (const t of _allTasks) {
      if (counts[t.status] !== undefined) counts[t.status]++;
      const mode = t.config?.mode || 'profiler';
      if (typeCounts[mode] !== undefined) typeCounts[mode]++;
    }
    counts.running += counts.starting; // merge running + starting

    return { counts, typeCounts };
  }

  // ── Render: Stats Dashboard ───────────────────────────────────────────
  function renderStatsDashboard(stats) {
    if (!stats || _allTasks.length === 0) return '';

    const { counts, typeCounts } = stats;
    const successRate = counts.all > 0 ? Math.round((counts.completed / counts.all) * 100) : 0;

    return `
      <div class="sh-stats" role="region" aria-label="任务统计">
        <div class="sh-stats-row">
          <div class="sh-stat-card sh-stat-total" role="status" aria-label="总任务数: ${counts.all}">
            <div class="sh-stat-icon" aria-hidden="true">${ICON.box}</div>
            <div class="sh-stat-info">
              <span class="sh-stat-value">${counts.all}</span>
              <span class="sh-stat-label">总任务</span>
            </div>
          </div>
          <div class="sh-stat-card sh-stat-success" role="status" aria-label="成功任务: ${counts.completed}, 成功率 ${successRate}%">
            <div class="sh-stat-icon" aria-hidden="true">${ICON.check}</div>
            <div class="sh-stat-info">
              <span class="sh-stat-value">${counts.completed}</span>
              <span class="sh-stat-label">成功</span>
            </div>
            <div class="sh-stat-badge">${successRate}%</div>
          </div>
          <div class="sh-stat-card sh-stat-running" role="status" aria-label="运行中任务: ${counts.running}">
            <div class="sh-stat-icon" aria-hidden="true">${ICON.loader}</div>
            <div class="sh-stat-info">
              <span class="sh-stat-value">${counts.running}</span>
              <span class="sh-stat-label">运行中</span>
            </div>
          </div>
          <div class="sh-stat-card sh-stat-failed" role="status" aria-label="失败任务: ${counts.failed}">
            <div class="sh-stat-icon" aria-hidden="true">${ICON.x}</div>
            <div class="sh-stat-info">
              <span class="sh-stat-value">${counts.failed}</span>
              <span class="sh-stat-label">失败</span>
            </div>
          </div>
        </div>
        <div class="sh-stats-row">
          <div class="sh-type-distribution">
            <span class="sh-type-title">任务类型分布</span>
            <div class="sh-type-bars">
              ${typeCounts.profiler > 0 ? `<div class="sh-type-bar" style="width: ${(typeCounts.profiler / counts.all) * 100}%" title="Profiler: ${typeCounts.profiler}"><span>P</span></div>` : ''}
              ${typeCounts.jfr > 0 ? `<div class="sh-type-bar sh-type-jfr" style="width: ${(typeCounts.jfr / counts.all) * 100}%" title="JFR: ${typeCounts.jfr}"><span>J</span></div>` : ''}
              ${typeCounts.threaddump > 0 ? `<div class="sh-type-bar sh-type-thread" style="width: ${(typeCounts.threaddump / counts.all) * 100}%" title="Thread: ${typeCounts.threaddump}"><span>T</span></div>` : ''}
              ${typeCounts.heapdump > 0 ? `<div class="sh-type-bar sh-type-heap" style="width: ${(typeCounts.heapdump / counts.all) * 100}%" title="Heap: ${typeCounts.heapdump}"><span>H</span></div>` : ''}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // ── Full Render ────────────────────────────────────────────────────────
  function render() {
    if (!_root) return;
    applyFilterSort();

    const stats = renderStats();

    _root.innerHTML = `
      <div class="sh-container" role="region" aria-label="采样历史记录">
        ${renderToolbar()}
        ${renderStatsDashboard(stats)}
        <div class="sh-body" role="list" aria-label="任务列表">
          ${renderList()}
        </div>
        ${renderShortcutsPanel()}
      </div>
    `;

    // Update status counts
    const countEls = _root.querySelectorAll('[data-status-count]');
    countEls.forEach(el => {
      const st = el.dataset.statusCount;
      el.textContent = stats.counts[st] || 0;
    });

    bindEvents();

    // Force-sync search input value (browser may preserve old value across innerHTML replacement)
    const searchEl = _root.querySelector('#shSearchInput');
    if (searchEl && searchEl.value !== _search) searchEl.value = _search;
  }

  // ── Event Binding ──────────────────────────────────────────────────────
  function bindEvents() {
    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboardShortcuts);

    // Batch toggle
    const batchToggle = _root.querySelector('#shBatchToggle');
    if (batchToggle) {
      batchToggle.addEventListener('click', () => {
        _batchMode = !_batchMode;
        if (!_batchMode) _selectedIds.clear();
        render();
      });
    }

    // Select all checkbox
    const selectAll = _root.querySelector('#shSelectAll');
    if (selectAll) {
      selectAll.addEventListener('change', () => {
        if (selectAll.checked) {
          _filtered.forEach(t => _selectedIds.add(t.id));
        } else {
          _selectedIds.clear();
        }
        render();
      });
    }

    // Row checkboxes
    _root.querySelectorAll('.sh-row-checkbox').forEach(cb => {
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        const id = cb.dataset.id;
        if (cb.checked) {
          _selectedIds.add(id);
        } else {
          _selectedIds.delete(id);
        }
        updateBatchBar();
      });
    });

    // Batch export
    const batchExport = _root.querySelector('#shBatchExport');
    if (batchExport) {
      batchExport.addEventListener('click', () => {
        const selectedTasks = _allTasks.filter(t => _selectedIds.has(t.id));
        if (typeof downloadProfilerTask === 'function') {
          selectedTasks.forEach(t => {
            if (t.has_file) downloadProfilerTask(t.id, t.file_name || 'output');
          });
        }
      });
    }

    // Batch delete
    const batchDelete = _root.querySelector('#shBatchDelete');
    if (batchDelete) {
      batchDelete.addEventListener('click', () => {
        if (confirm(`确定要删除选中的 ${_selectedIds.size} 个任务吗？`)) {
          // TODO: Implement batch delete API call
          console.log('Batch delete:', [..._selectedIds]);
          _selectedIds.clear();
          loadAndRender();
        }
      });
    }

    // Batch clear
    const batchClear = _root.querySelector('#shBatchClear');
    if (batchClear) {
      batchClear.addEventListener('click', () => {
        _selectedIds.clear();
        render();
      });
    }

    // Search
    const searchInput = _root.querySelector('#shSearchInput');
    if (searchInput) {
      let debounce = null;
      searchInput.addEventListener('input', () => {
        _search = searchInput.value.trim(); // Always sync immediately
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          render();
          // Restore focus + cursor
          const newInput = _root.querySelector('#shSearchInput');
          if (newInput) { newInput.focus(); newInput.setSelectionRange(newInput.value.length, newInput.value.length); }
        }, 250);
      });
      searchInput.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
          clearTimeout(debounce);
          _search = '';
          render();
        }
      });
    }

    // Search clear
    const clearBtn = _root.querySelector('#shSearchClear');
    if (clearBtn) clearBtn.addEventListener('click', () => { _search = ''; render(); });

    // Status filter tabs
    const statusTabs = _root.querySelector('#shStatusTabs');
    if (statusTabs) {
      statusTabs.addEventListener('click', e => {
        const tab = e.target.closest('.sh-status-tab');
        if (!tab) return;
        _statusFilter = tab.dataset.val;
        render();
      });
    }

    // Type filter
    const typeSelect = _root.querySelector('#shTypeFilter');
    if (typeSelect) {
      typeSelect.addEventListener('change', () => { _typeFilter = typeSelect.value; render(); });
    }

    // Sort buttons
    _root.querySelectorAll('.sh-sort-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const field = btn.dataset.sort;
        if (_sortField === field) { _sortDir = _sortDir === 'desc' ? 'asc' : 'desc'; }
        else { _sortField = field; _sortDir = 'desc'; }
        render();
      });
    });

    // Refresh
    const refreshBtn = _root.querySelector('#shRefreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => loadAndRender());

    // Clear filters (empty state)
    const clearFilters = _root.querySelector('#shClearFilters');
    if (clearFilters) clearFilters.addEventListener('click', () => { _search = ''; _statusFilter = 'all'; _typeFilter = 'all'; render(); });

    // Pagination
    const prevBtn = _root.querySelector('#shPagePrev');
    const nextBtn = _root.querySelector('#shPageNext');
    if (prevBtn) prevBtn.addEventListener('click', () => { if (_page > 0) { _page--; render(); } });
    if (nextBtn) nextBtn.addEventListener('click', () => {
      const totalPages = Math.ceil(_filtered.length / _pageSize) || 1;
      if (_page < totalPages - 1) { _page++; render(); }
    });

    const pageSizeSelect = _root.querySelector('#shPageSize');
    if (pageSizeSelect) pageSizeSelect.addEventListener('change', () => { _pageSize = parseInt(pageSizeSelect.value); _page = 0; render(); });

    // Row expand
    _root.querySelectorAll('.sh-row-main').forEach(row => {
      row.addEventListener('click', e => {
        // Ignore clicks on buttons
        if (e.target.closest('.sh-btn-dl') || e.target.closest('.sh-btn-stop') || e.target.closest('button')) return;
        const taskRow = row.closest('.sh-row');
        const taskId = taskRow?.dataset.taskId;
        if (!taskId) return;
        _expandedId = _expandedId === taskId ? null : taskId;
        render();
      });
    });

    // Download buttons
    _root.querySelectorAll('[data-dl]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const taskId = btn.dataset.dl;
        const filename = btn.dataset.fn;
        if (typeof downloadProfilerTask === 'function') {
          downloadProfilerTask(taskId, filename);
        }
      });
    });

    // Stop buttons
    _root.querySelectorAll('[data-stop]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const taskId = btn.dataset.stop;
        if (typeof cancelProfilerTask === 'function') {
          cancelProfilerTask(taskId);
        }
      });
    });
  }

  // ── Keyboard Shortcuts ────────────────────────────────────────────────
  function handleKeyboardShortcuts(e) {
    // Ignore if focus is on input elements
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      // Only handle Escape in input
      if (e.key === 'Escape') {
        e.target.blur();
        _search = '';
        render();
      }
      return;
    }

    const pageTasks = _filtered.slice(_page * _pageSize, (_page + 1) * _pageSize);

    switch(e.key) {
      case '/':
        e.preventDefault();
        const searchInput = _root.querySelector('#shSearchInput');
        if (searchInput) searchInput.focus();
        break;

      case 'ArrowDown':
      case 'j':
        e.preventDefault();
        if (_focusedIndex < pageTasks.length - 1) {
          _focusedIndex++;
          updateFocusedRow();
        }
        break;

      case 'ArrowUp':
      case 'k':
        e.preventDefault();
        if (_focusedIndex > 0) {
          _focusedIndex--;
          updateFocusedRow();
        }
        break;

      case 'Enter':
        e.preventDefault();
        if (_focusedIndex >= 0 && _focusedIndex < pageTasks.length) {
          const taskId = pageTasks[_focusedIndex].id;
          _expandedId = _expandedId === taskId ? null : taskId;
          render();
        }
        break;

      case 'Delete':
      case 'Backspace':
        if (_batchMode && _selectedIds.size > 0) {
          e.preventDefault();
          if (confirm(`确定要删除选中的 ${_selectedIds.size} 个任务吗？`)) {
            console.log('Batch delete:', [..._selectedIds]);
            _selectedIds.clear();
            loadAndRender();
          }
        }
        break;

      case 'Escape':
        e.preventDefault();
        if (_showShortcuts) {
          _showShortcuts = false;
          render();
        } else if (_expandedId) {
          _expandedId = null;
          render();
        } else if (_search || _statusFilter !== 'all' || _typeFilter !== 'all') {
          _search = '';
          _statusFilter = 'all';
          _typeFilter = 'all';
          render();
        }
        break;

      case '?':
        e.preventDefault();
        _showShortcuts = !_showShortcuts;
        render();
        break;
    }
  }

  function updateFocusedRow() {
    _root.querySelectorAll('.sh-row').forEach((row, i) => {
      row.classList.toggle('sh-row-focused', i === _focusedIndex);
    });

    // Scroll focused row into view
    const focusedRow = _root.querySelector('.sh-row-focused');
    if (focusedRow) {
      focusedRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  // ── Render: Shortcuts Panel ──────────────────────────────────────────
  function renderShortcutsPanel() {
    if (!_showShortcuts) return '';

    return `
      <div class="sh-shortcuts-panel" id="shShortcutsPanel">
        <div class="sh-shortcuts-header">
          <span class="sh-shortcuts-title">键盘快捷键</span>
          <button class="sh-shortcuts-close" id="shShortcutsClose">&times;</button>
        </div>
        <div class="sh-shortcuts-grid">
          <div class="sh-shortcut-item">
            <kbd>/</kbd>
            <span>聚焦搜索</span>
          </div>
          <div class="sh-shortcut-item">
            <kbd>↑</kbd> <kbd>↓</kbd>
            <span>导航任务</span>
          </div>
          <div class="sh-shortcut-item">
            <kbd>Enter</kbd>
            <span>展开详情</span>
          </div>
          <div class="sh-shortcut-item">
            <kbd>Esc</kbd>
            <span>关闭/清除</span>
          </div>
          <div class="sh-shortcut-item">
            <kbd>?</kbd>
            <span>显示帮助</span>
          </div>
        </div>
      </div>
    `;
  }

  // ── Data Loading ───────────────────────────────────────────────────────
  async function loadAndRender() {
    try {
      // Show skeleton loading
      if (_root && _allTasks.length === 0) {
        _root.innerHTML = `
          <div class="sh-container">
            <div class="sh-skeleton sh-skeleton-stat"></div>
            <div class="sh-body" style="padding:14px">
              <div class="sh-skeleton sh-skeleton-row"></div>
              <div class="sh-skeleton sh-skeleton-row"></div>
              <div class="sh-skeleton sh-skeleton-row"></div>
              <div class="sh-skeleton sh-skeleton-row"></div>
              <div class="sh-skeleton sh-skeleton-row"></div>
            </div>
          </div>
        `;
      }

      const r = await fetch(`${API}/profile/tasks`, { credentials: 'include' });
      let tasks = await r.json();

      // Inline mode: filter by connection
      if (_mode === 'inline' && _connId && typeof _connections !== 'undefined') {
        const conn = _connections.find(c => c.id === _connId);
        if (conn) {
          tasks = tasks.filter(t =>
            t.config.cluster === conn.cluster_name &&
            t.config.namespace === conn.namespace &&
            t.config.pod === conn.pod_name
          );
        }
      }

      _allTasks = tasks;
      render();

      // Update global count badge
      const badge = document.getElementById('cntPfTasks');
      if (badge) badge.textContent = _allTasks.length;
    } catch (e) {
      console.error('[SamplingHistory] Failed to load tasks:', e);
      if (_root) {
        _root.innerHTML = `
          <div class="sh-empty">
            ${ICON.x}
            <div class="sh-empty-title">加载失败</div>
            <div class="sh-empty-sub">${esc(e.message)}</div>
            <button class="sh-btn-action" onclick="SamplingHistory.refresh()">重试</button>
          </div>
        `;
      }
    }
  }

  // ── Public API ─────────────────────────────────────────────────────────
  function mount(container, opts = {}) {
    _root = typeof container === 'string' ? document.querySelector(container) : container;
    if (!_root) { console.warn('[SamplingHistory] Container not found'); return; }
    _mode = opts.mode || 'global';
    _connId = opts.connectionId || null;
    _root.classList.add('sh-host');
    loadAndRender();
  }

  function refresh() { loadAndRender(); }

  function updateConnection(connId) {
    _connId = connId;
    if (_mode === 'inline') loadAndRender();
  }

  function destroy() {
    if (_root) { _root.innerHTML = ''; _root.classList.remove('sh-host'); }
    _root = null;
    _allTasks = [];
    _filtered = [];
    _expandedId = null;
  }

  return { mount, refresh, updateConnection, destroy };
})();
