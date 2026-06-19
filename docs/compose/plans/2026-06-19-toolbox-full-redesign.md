# 工具箱 UI 全面重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the entire toolbox UI with modern layout, improved card design, Modal-based distribution, search/filter, and responsive support.

**Architecture:** Component-based redesign with separate concerns: layout (HTML), styling (CSS), and behavior (JS). Each task produces self-contained, testable changes.

**Tech Stack:** Vanilla JavaScript, CSS Grid, localStorage

---

## File Structure

| File | Responsibility |
|------|---------------|
| `static/index.html` | Page layout structure |
| `static/js/components/toolbox.js` | All toolbox logic |
| `static/css/app.css` | All toolbox styles |
| `tests/test_toolbox.py` | Test suite |

---

### Task 1: Redesign HTML Layout

**Covers:** [S2]

**Files:**
- Modify: `static/index.html` (lines 688-734)

- [ ] **Step 1: Replace hero section with compact header**

Find the hero section (lines 688-694) and replace with:

```html
<div class="toolbox-header">
  <div class="toolbox-header-left">
    <h2>工具箱</h2>
    <span class="toolbox-header-desc">诊断辅助工具集</span>
  </div>
  <div class="toolbox-header-actions">
    <button class="btn btn-g btn-sm" onclick="renderToolbox()">刷新</button>
    <button class="btn btn-p btn-sm" onclick="toolboxOpenBatchDistribute()">📦 批量分发</button>
  </div>
</div>
```

- [ ] **Step 2: Replace summary bar with toolbar**

Find the summary bar (lines 696-701) and replace with:

```html
<div class="toolbox-toolbar">
  <div class="toolbox-toolbar-left">
    <div class="toolbox-search">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" id="toolboxSearch" placeholder="搜索工具..." oninput="filterTools(this.value)">
    </div>
    <div class="toolbox-filter-tags">
      <button class="filter-tag active" data-filter="all" onclick="setFilter('all')">全部</button>
      <button class="filter-tag" data-filter="binary" onclick="setFilter('binary')">📦 二进制</button>
      <button class="filter-tag" data-filter="script" onclick="setFilter('script')">🐍 脚本</button>
      <button class="filter-tag" data-filter="quick" onclick="setFilter('quick')">⚡ 快捷</button>
    </div>
  </div>
  <div class="toolbox-toolbar-right">
    <button class="btn btn-g btn-sm" onclick="toolboxUploadBinary()">📦 上传工具</button>
    <button class="btn btn-g btn-sm" onclick="toolboxCreateScript()">📜 新建脚本</button>
    <button class="btn btn-g btn-sm" onclick="toolboxCreateQuick()">⚡ 新建操作</button>
  </div>
</div>
```

- [ ] **Step 3: Update section headers**

Replace each section header to remove duplicate action buttons (since they're now in toolbar):

Binary tools section (lines 703-712):
```html
<section class="toolbox-section" data-type="binary">
  <div class="toolbox-section-header">
    <h3>📦 二进制工具 <span class="section-count" id="countBinary">0</span></h3>
  </div>
  <div id="toolboxBinaryTools" class="toolbox-card-grid">
    <div class="sb-empty">加载中...</div>
  </div>
</section>
```

Script tools section (lines 714-723):
```html
<section class="toolbox-section" data-type="script">
  <div class="toolbox-section-header">
    <h3>🐍 脚本工具 <span class="section-count" id="countScript">0</span></h3>
  </div>
  <div id="toolboxScriptTools" class="toolbox-card-grid">
    <div class="sb-empty">加载中...</div>
  </div>
</section>
```

Quick actions section (lines 725-734):
```html
<section class="toolbox-section" data-type="quick">
  <div class="toolbox-section-header">
    <h3>⚡ 快捷操作 <span class="section-count" id="countQuick">0</span></h3>
  </div>
  <div id="toolboxQuickActions" class="toolbox-card-grid">
    <div class="sb-empty">加载中...</div>
  </div>
</section>
```

- [ ] **Step 4: Verify layout renders**

Open browser, verify the new layout displays correctly.

---

### Task 2: Add New CSS Styles

**Covers:** [S5], [S9]

**Files:**
- Modify: `static/css/app.css` (append after line ~3230)

- [ ] **Step 1: Add header and toolbar styles**

```css
/* ── Toolbox Header ── */
.toolbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.toolbox-header-left h2 {
  font-size: 20px;
  font-weight: 700;
  color: var(--tx);
  margin: 0;
}

.toolbox-header-desc {
  font-size: 13px;
  color: var(--tx2);
}

.toolbox-header-actions {
  display: flex;
  gap: 8px;
}

/* ── Toolbox Toolbar ── */
.toolbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  background: rgba(0,0,0,.2);
  border: 1px solid rgba(40,61,90,.4);
  border-radius: 10px;
  margin-bottom: 20px;
}

.toolbox-toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.toolbox-toolbar-right {
  display: flex;
  gap: 8px;
}

/* ── Search Box ── */
.toolbox-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(0,0,0,.3);
  border: 1px solid rgba(40,61,90,.5);
  border-radius: 8px;
  min-width: 200px;
}

.toolbox-search svg {
  color: var(--tx2);
  flex-shrink: 0;
}

.toolbox-search input {
  background: none;
  border: none;
  color: var(--tx);
  font-size: 13px;
  width: 100%;
  outline: none;
}

.toolbox-search input::placeholder {
  color: var(--tx3);
}

/* ── Filter Tags ── */
.toolbox-filter-tags {
  display: flex;
  gap: 6px;
}

.filter-tag {
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--tx2);
  background: rgba(0,0,0,.2);
  border: 1px solid rgba(40,61,90,.4);
  border-radius: 6px;
  cursor: pointer;
  transition: all .15s;
}

.filter-tag:hover {
  border-color: rgba(0,122,255,.4);
  color: var(--tx);
}

.filter-tag.active {
  background: rgba(0,122,255,.15);
  border-color: rgba(0,122,255,.5);
  color: var(--a);
}

/* ── Section Count Badge ── */
.section-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--a);
  background: rgba(0,122,255,.15);
  border-radius: 10px;
  margin-left: 8px;
}
```

- [ ] **Step 2: Add Modal styles**

```css
/* ── Distribute Modal ── */
.dist-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn .2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.dist-modal {
  width: 520px;
  max-height: 80vh;
  background: var(--bg2);
  border: 1px solid rgba(40,61,90,.6);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
  display: flex;
  flex-direction: column;
  animation: slideUp .25s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.dist-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(40,61,90,.4);
}

.dist-modal-header h3 {
  font-size: 14px;
  font-weight: 700;
  color: var(--tx);
  margin: 0;
}

.dist-modal-header .btn-close {
  background: none;
  border: none;
  color: var(--tx2);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all .15s;
}

.dist-modal-header .btn-close:hover {
  background: rgba(255,255,255,.1);
  color: var(--tx);
}

.dist-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.dist-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid rgba(40,61,90,.4);
}
```

- [ ] **Step 3: Add quick-select styles**

```css
/* ── Quick Select (Recent Targets) ── */
.dist-recent-section {
  margin-bottom: 16px;
}

.dist-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--tx2);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: .5px;
}

.dist-recent-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dist-recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(0,0,0,.2);
  border: 1px solid rgba(40,61,90,.4);
  border-radius: 8px;
  cursor: pointer;
  transition: all .15s;
}

.dist-recent-item:hover {
  border-color: rgba(0,122,255,.4);
  background: rgba(0,122,255,.05);
}

.dist-recent-target {
  font-size: 13px;
  color: var(--tx);
  display: flex;
  align-items: center;
  gap: 6px;
}

.dist-recent-target .sep {
  color: var(--tx2);
}

.dist-recent-select {
  font-size: 12px;
  color: var(--a);
  font-weight: 600;
}

.dist-recent-empty {
  font-size: 12px;
  color: var(--tx2);
  padding: 8px 0;
}

.dist-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--tx2);
  margin: 16px 0;
}

.dist-divider::before,
.dist-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(40,61,90,.4);
}
```

- [ ] **Step 4: Add capability badge styles**

```css
/* ── Capability Badge ── */
.dist-cap-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}

.dist-cap-badge.cap-ok {
  background: rgba(52,199,89,.15);
  color: #34c759;
}

.dist-cap-badge.cap-warn {
  background: rgba(255,149,0,.15);
  color: #ff9500;
}

.dist-cap-badge.cap-error {
  background: rgba(255,59,48,.15);
  color: #ff3b30;
}
```

- [ ] **Step 5: Add empty state styles**

```css
/* ── Empty State ── */
.toolbox-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  border: 2px dashed rgba(40,61,90,.4);
  border-radius: 12px;
  text-align: center;
}

.toolbox-empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.toolbox-empty-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--tx2);
  margin-bottom: 8px;
}

.toolbox-empty-desc {
  font-size: 12px;
  color: var(--tx3);
  margin-bottom: 16px;
}
```

- [ ] **Step 6: Verify styles load**

Open browser dev tools, check no CSS errors.

---

### Task 3: Add Search and Filter Logic

**Covers:** [S5]

**Files:**
- Modify: `static/js/components/toolbox.js` (add after line ~15)

- [ ] **Step 1: Add state variables and filter functions**

```javascript
// ═══════════════════════════════════════════════════════════════
// Search & Filter
// ═══════════════════════════════════════════════════════════════

let _currentFilter = 'all';
let _allTools = { binary: [], script: [], quick: [] };

window.setFilter = function(filter) {
  _currentFilter = filter;
  document.querySelectorAll('.filter-tag').forEach(tag => {
    tag.classList.toggle('active', tag.dataset.filter === filter);
  });
  _applyFilter();
};

window.filterTools = function(query) {
  _applyFilter(query);
};

function _applyFilter(query) {
  query = (query || document.getElementById('toolboxSearch')?.value || '').toLowerCase();
  
  // Filter binary tools
  const binaryContainer = document.getElementById('toolboxBinaryTools');
  if (binaryContainer && (_currentFilter === 'all' || _currentFilter === 'binary')) {
    const filtered = _allTools.binary.filter(t => 
      !query || t.name?.toLowerCase().includes(query) || 
      t.file_name?.toLowerCase().includes(query) ||
      t.tool_type?.toLowerCase().includes(query)
    );
    renderBinaryToolCards(filtered);
  } else if (binaryContainer) {
    binaryContainer.innerHTML = '';
  }

  // Filter script tools
  const scriptContainer = document.getElementById('toolboxScriptTools');
  if (scriptContainer && (_currentFilter === 'all' || _currentFilter === 'script')) {
    const filtered = _allTools.script.filter(t =>
      !query || t.name?.toLowerCase().includes(query) ||
      t.runtime?.toLowerCase().includes(query)
    );
    renderScriptToolCards(filtered);
  } else if (scriptContainer) {
    scriptContainer.innerHTML = '';
  }

  // Filter quick actions
  const quickContainer = document.getElementById('toolboxQuickActions');
  if (quickContainer && (_currentFilter === 'all' || _currentFilter === 'quick')) {
    const filtered = _allTools.quick.filter(t =>
      !query || t.name?.toLowerCase().includes(query) ||
      t.command_template?.toLowerCase().includes(query) ||
      t.category?.toLowerCase().includes(query)
    );
    renderQuickActionCards(filtered);
  } else if (quickContainer) {
    quickContainer.innerHTML = '';
  }

  // Update counts
  _updateCounts();
}

function _updateCounts() {
  const countBinary = document.getElementById('countBinary');
  const countScript = document.getElementById('countScript');
  const countQuick = document.getElementById('countQuick');
  
  if (countBinary) countBinary.textContent = _allTools.binary.length;
  if (countScript) countScript.textContent = _allTools.script.length;
  if (countQuick) countQuick.textContent = _allTools.quick.length;
}
```

- [ ] **Step 2: Update loadBinaryTools to cache data**

Find `loadBinaryTools` function (lines 21-29) and update:

```javascript
async function loadBinaryTools() {
  try {
    const data = await safeGet('/tasks/tool-packages');
    _allTools.binary = data.packages || [];
    renderBinaryToolCards(_allTools.binary);
    _updateCounts();
  } catch (e) {
    console.error('加载二进制工具失败:', e);
  }
}
```

- [ ] **Step 3: Update loadScriptTools to cache data**

Find `loadScriptTools` function (lines 83-91) and update:

```javascript
async function loadScriptTools() {
  try {
    const data = await safeGet('/tasks/script-tools');
    _allTools.script = data.tools || [];
    renderScriptToolCards(_allTools.script);
    _updateCounts();
  } catch (e) {
    console.error('加载脚本工具失败:', e);
  }
}
```

- [ ] **Step 4: Update loadQuickActions to cache data**

Find `loadQuickActions` function (lines 141-149) and update:

```javascript
async function loadQuickActions() {
  try {
    const data = await safeGet('/tasks/quick-actions');
    _allTools.quick = data.actions || [];
    renderQuickActionCards(_allTools.quick);
    _updateCounts();
  } catch (e) {
    console.error('加载快捷操作失败:', e);
  }
}
```

- [ ] **Step 5: Verify search works**

Open browser, type in search box, verify tools filter in real-time.

---

### Task 4: Add Recent Targets Functions

**Covers:** [S4]

**Files:**
- Modify: `static/js/components/toolbox.js` (add after filter functions)

- [ ] **Step 1: Add localStorage helper functions**

```javascript
// ═══════════════════════════════════════════════════════════════
// Recent Targets (localStorage)
// ═══════════════════════════════════════════════════════════════

const RECENT_TARGETS_KEY = 'toolbox-recent-targets';
const MAX_RECENT_TARGETS = 5;

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
```

- [ ] **Step 2: Verify localStorage functions**

Open browser console, check `_loadRecentTargets` is defined.

---

### Task 5: Add Modal Logic

**Covers:** [S4]

**Files:**
- Modify: `static/js/components/toolbox.js` (add after recent targets functions)

- [ ] **Step 1: Add Modal open function**

```javascript
// ═══════════════════════════════════════════════════════════════
// Distribute Modal
// ═══════════════════════════════════════════════════════════════

window.openDistributeModal = async function(toolId, toolType, defaultPath) {
  const existing = document.getElementById(`distModal-${toolId}`);
  if (existing) existing.remove();

  const card = document.querySelector(`.toolbox-card[data-id="${toolId}"]`);
  const toolName = card?.querySelector('.toolbox-card-name')?.textContent || `Tool #${toolId}`;

  const clusters = await _loadDistClusters();
  const clusterOptions = clusters.map(c =>
    `<option value="${esc(c.name)}">${esc(c.name)}</option>`
  ).join('');

  const modal = document.createElement('div');
  modal.className = 'dist-modal-overlay';
  modal.id = `distModal-${toolId}`;
  modal.innerHTML = `
    <div class="dist-modal">
      <div class="dist-modal-header">
        <h3>分发工具: ${esc(toolName)}</h3>
        <button class="btn-close" onclick="closeDistributeModal(${toolId})">✕</button>
      </div>
      <div class="dist-modal-body">
        <div class="dist-recent-section">
          <div class="dist-section-title">⭐ 最近使用</div>
          <div class="dist-recent-list" id="distRecentList-${toolId}"></div>
        </div>
        <div class="dist-divider">或手动选择目标</div>
        <div class="dist-form">
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
              <option value="">选择集群后加载</option>
            </select>
          </div>
          <div class="dist-form-row">
            <label>Pod</label>
            <div style="flex:1;display:flex;align-items:center;gap:8px">
              <select id="dist-pod-${toolId}" class="inp" style="flex:1" onchange="distOnPodChange(${toolId})">
                <option value="">选择 Namespace 后加载</option>
              </select>
              <span id="dist-cap-${toolId}"></span>
            </div>
          </div>
          <div class="dist-form-row">
            <label>容器</label>
            <select id="dist-ctr-${toolId}" class="inp">
              <option value="">默认容器</option>
            </select>
          </div>
          <div class="dist-form-row">
            <label>安装路径</label>
            <input id="dist-path-${toolId}" class="inp" value="${esc(defaultPath || '/tmp/arthas/arthas-boot.jar')}">
          </div>
        </div>
      </div>
      <div class="dist-modal-footer">
        <button class="btn btn-g btn-sm" onclick="closeDistributeModal(${toolId})">取消</button>
        <button class="btn btn-p btn-sm" onclick="confirmModalDistribute(${toolId}, '${toolType}')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          确认分发
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  _renderRecentTargets(`distRecentList-${toolId}`);

  modal.querySelectorAll('.dist-recent-item').forEach(item => {
    item.onclick = () => {
      const idx = parseInt(item.dataset.index);
      const targets = _loadRecentTargets();
      if (targets[idx]) {
        _fillDistributeForm(toolId, targets[idx]);
      }
    };
  });

  modal.onclick = (e) => {
    if (e.target === modal) closeDistributeModal(toolId);
  };
};
```

- [ ] **Step 2: Add Modal close function**

```javascript
window.closeDistributeModal = function(toolId) {
  const modal = document.getElementById(`distModal-${toolId}`);
  if (modal) modal.remove();
};
```

- [ ] **Step 3: Add form fill helper**

```javascript
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
            distOnPodChange(toolId).then(() => {
              if (ctrEl && target.container) {
                ctrEl.value = target.container;
              }
            });
          }
        });
      }
    });
  }
}
```

- [ ] **Step 4: Add Pod change handler with capability detection**

```javascript
window.distOnPodChange = async function(toolId) {
  const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value;
  const ns = document.getElementById(`dist-ns-${toolId}`)?.value;
  const pod = document.getElementById(`dist-pod-${toolId}`)?.value;
  const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value;
  const capEl = document.getElementById(`dist-cap-${toolId}`);

  if (!capEl) return;
  capEl.innerHTML = '';

  if (!cluster || !ns || !pod) return;

  try {
    const result = await safePost('/tasks/detect-capability', {
      cluster, namespace: ns, pod, container: ctr
    });
    if (result.capability_level === 'pod+arthas') {
      capEl.innerHTML = '<span class="dist-cap-badge cap-ok">✅ Java + Arthas</span>';
    } else if (result.capability_level === 'pod-only') {
      capEl.innerHTML = `<span class="dist-cap-badge cap-warn">⚠️ ${result.java_version || 'Java'} (需 Arthas)</span>`;
    } else {
      capEl.innerHTML = '<span class="dist-cap-badge cap-error">❌ 不兼容</span>';
    }
  } catch (e) {
    // Ignore capability detection errors
  }
};
```

- [ ] **Step 5: Add Modal confirm distribute function**

```javascript
window.confirmModalDistribute = async function(toolId, toolType) {
  const cluster = document.getElementById(`dist-cluster-${toolId}`)?.value || '';
  const ns = document.getElementById(`dist-ns-${toolId}`)?.value || 'default';
  const pod = document.getElementById(`dist-pod-${toolId}`)?.value || '';
  const ctr = document.getElementById(`dist-ctr-${toolId}`)?.value || '';
  const path = document.getElementById(`dist-path-${toolId}`)?.value || '/tmp/arthas/arthas-boot.jar';

  if (!cluster) { toast('请选择集群', 'warn'); return; }
  if (!pod) { toast('请选择 Pod', 'warn'); return; }

  const payload = { tool_id: toolId, cluster, namespace: ns, pod, container: ctr, install_path: path };

  try {
    await safePost('/tasks/distribute', payload);
    _saveRecentTarget({ cluster, namespace: ns, pod, container: ctr });
    toast('分发成功', 'ok');
    closeDistributeModal(toolId);
  } catch (e) {
    toast(`分发失败：${e.message}`, 'err');
  }
};
```

- [ ] **Step 6: Verify Modal opens**

Open browser, click distribute button on a tool card, verify Modal appears.

---

### Task 6: Update Card Buttons

**Covers:** [S3], [S4]

**Files:**
- Modify: `static/js/components/toolbox.js` (lines 60-76)

- [ ] **Step 1: Update distribute button onclick**

Find the distribute button in `renderBinaryToolCards` (line 64):

```javascript
<button class="btn btn-p btn-sm" onclick="toolboxSingleDistribute(${p.id}, 'binary', '${esc(p.install_path || '')}')">
```

Replace with:

```javascript
<button class="btn btn-p btn-sm" onclick="openDistributeModal(${p.id}, 'binary', '${esc(p.install_path || '')}')">
```

- [ ] **Step 2: Remove old inline form div**

Find and remove this line (line 73):

```javascript
<div class="toolbox-distribute-form" id="distForm-binary-${p.id}" style="display:none"></div>
```

- [ ] **Step 3: Verify button opens Modal**

Open browser, click distribute button, verify Modal opens instead of inline form.

---

### Task 7: Clean Up Old Code

**Covers:** [S6]

**Files:**
- Modify: `static/js/components/toolbox.js`

- [ ] **Step 1: Remove old toolboxSingleDistribute function**

Remove the entire `window.toolboxSingleDistribute` function (lines ~335-419).

- [ ] **Step 2: Remove old distToggleType function**

Remove the `window.distToggleType` function (lines ~421-429).

- [ ] **Step 3: Verify no references to removed functions**

Run: `grep -r "toolboxSingleDistribute\|distToggleType" static/js/`
Expected: No matches.

---

### Task 8: Add Tests

**Covers:** [S7]

**Files:**
- Modify: `tests/test_toolbox.py`

- [ ] **Step 1: Add test for page load**

```python
def test_toolbox_page_loads(self):
    """Toolbox page loads without errors."""
    resp = self.client.get('/tasks')
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_toolbox.py -v`
Expected: All tests pass.

---

### Task 9: Final Verification

**Covers:** All

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/test_toolbox.py tests/test_task_center_toolchain.py -v`
Expected: All tests pass.

- [ ] **Step 2: Manual browser verification**

1. Open toolbox page
2. Verify new layout with toolbar and search
3. Type in search box → verify tools filter
4. Click filter tags → verify section filtering
5. Click "分发" on a binary tool → verify Modal opens
6. Select a recent target → verify form auto-fills
7. Manually select cluster/namespace/pod → verify capability badge appears
8. Click "确认分发" → verify success toast and Modal closes
9. Re-open Modal → verify target appears in recent list
10. Test responsive layout at different widths

- [ ] **Step 3: Commit changes**

```bash
git add static/index.html static/js/components/toolbox.js static/css/app.css tests/test_toolbox.py docs/compose/specs/2026-06-19-toolbox-full-redesign.md docs/compose/plans/2026-06-19-toolbox-full-redesign.md
git commit -m "feat: comprehensive toolbox UI redesign

- Compact header with action buttons
- Toolbar with search and filter tags
- Modal-based distribution with quick-select
- Pod capability detection and badges
- Responsive grid layout
- Improved empty states"
```
