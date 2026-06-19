# 工具箱 UI 全面重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the toolbox UI with tab-based navigation, modal interactions, LLM-assisted script creation, and comprehensive distribution management.

**Architecture:** Tab-based layout (Binary Tools + Script Tools) with modal-driven interactions. Distribution history accessible via toolbar button. Quick actions moved to workspace/diagnosis area.

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

## Design Decisions (from brainstorming)

1. **Tab navigation** — Binary Tools + Script Tools only (no Quick Actions)
2. **Quick Actions** — Moved to workspace/diagnosis area (needs Pod + Arthas connection)
3. **Distribution** — Modal with quick-select from recent targets
4. **Script creation** — LLM-assisted generation
5. **Distribution history** — Toolbar button → modal (not tab)
6. **Target dimensions** — Pod, Node, Namespace, Label selector
7. **Search/Filter** — In all lists with pagination/load-more
8. **Progress feedback** — Progress modal → Result modal with retry
9. **Edit capabilities** — Both binary (metadata + file replace) and script tools

---

### Task 1: Redesign HTML Layout

**Covers:** Tab navigation, header, toolbar

**Files:**
- Modify: `static/index.html` (lines 688-734)

- [ ] **Step 1: Replace hero section with compact header**

Find the hero section and replace with:

```html
<div class="toolbox-header">
  <div class="toolbox-header-left">
    <h2>工具箱</h2>
    <span class="toolbox-header-desc">诊断辅助工具集</span>
  </div>
  <div class="toolbox-header-actions">
    <button class="btn btn-g btn-sm" onclick="renderToolbox()">刷新</button>
    <button class="btn btn-g btn-sm" onclick="openDistributeHistory()">📋 查看记录</button>
    <button class="btn btn-p btn-sm" onclick="toolboxOpenBatchDistribute()">📦 批量分发</button>
  </div>
</div>
```

- [ ] **Step 2: Replace summary bar with tabs**

Replace the summary bar with:

```html
<div class="toolbox-tabs">
  <button class="toolbox-tab active" data-tab="binary" onclick="switchToolboxTab('binary', this)">
    📦 二进制工具 <span class="tab-count" id="countBinary">0</span>
  </button>
  <button class="toolbox-tab" data-tab="script" onclick="switchToolboxTab('script', this)">
    🐍 脚本工具 <span class="tab-count" id="countScript">0</span>
  </button>
</div>
```

- [ ] **Step 3: Wrap tool sections in tab content divs**

Wrap binary tools section:
```html
<div class="tab-content active" id="tab-binary">
  <div class="toolbox-toolbar">
    <div class="toolbox-toolbar-left">
      <div class="toolbox-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="searchBinary" placeholder="搜索二进制工具..." oninput="filterBinaryTools(this.value)">
      </div>
    </div>
    <div class="toolbox-toolbar-right">
      <button class="btn btn-g btn-sm" onclick="toolboxUploadBinary()">上传工具</button>
    </div>
  </div>
  <section class="toolbox-section">
    <div id="toolboxBinaryTools" class="toolbox-card-grid">
      <div class="sb-empty">加载中...</div>
    </div>
  </section>
</div>
```

Wrap script tools section:
```html
<div class="tab-content" id="tab-script">
  <div class="toolbox-toolbar">
    <div class="toolbox-toolbar-left">
      <div class="toolbox-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="searchScript" placeholder="搜索脚本工具..." oninput="filterScriptTools(this.value)">
      </div>
    </div>
    <div class="toolbox-toolbar-right">
      <button class="btn btn-g btn-sm" onclick="toolboxCreateScript()">+ 新建脚本</button>
    </div>
  </div>
  <section class="toolbox-section">
    <div id="toolboxScriptTools" class="toolbox-card-grid">
      <div class="sb-empty">加载中...</div>
    </div>
  </section>
</div>
```

- [ ] **Step 4: Verify layout renders**

Open browser, verify tabs and toolbar display correctly.

---

### Task 2: Add New CSS Styles

**Covers:** Tabs, toolbar, modal, quick-select, capability badge

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

/* ── Toolbox Tabs ── */
.toolbox-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: rgba(0,0,0,.2);
  border: 1px solid rgba(40,61,90,.4);
  border-radius: 10px;
  margin-bottom: 20px;
}

.toolbox-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--tx2);
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all .15s;
}

.toolbox-tab:hover {
  color: var(--tx);
  background: rgba(255,255,255,.05);
}

.toolbox-tab.active {
  color: var(--a);
  background: rgba(0,122,255,.15);
}

.toolbox-tab .tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 10px;
  font-weight: 700;
  color: var(--a);
  background: rgba(0,122,255,.2);
  border-radius: 9px;
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

/* ── Tab Content ── */
.tab-content {
  display: none;
}

.tab-content.active {
  display: block;
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

- [ ] **Step 5: Verify styles load**

Open browser dev tools, check no CSS errors.

---

### Task 3: Add Tab Switching and Search Logic

**Covers:** Tab navigation, search/filter

**Files:**
- Modify: `static/js/components/toolbox.js` (add after line ~15)

- [ ] **Step 1: Add state variables and tab switching**

```javascript
// ═══════════════════════════════════════════════════════════════
// Tab Switching & Search
// ═══════════════════════════════════════════════════════════════

let _allTools = { binary: [], script: [] };

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
```

- [ ] **Step 2: Update loadBinaryTools to cache data**

Find `loadBinaryTools` function and update:

```javascript
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
```

- [ ] **Step 3: Update loadScriptTools to cache data**

Find `loadScriptTools` function and update:

```javascript
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
```

- [ ] **Step 4: Verify search works**

Open browser, type in search box, verify tools filter in real-time.

---

### Task 4: Add Recent Targets Functions

**Covers:** Quick-select from recent targets

**Files:**
- Modify: `static/js/components/toolbox.js` (add after search functions)

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

**Covers:** Distribute modal, edit modals, history modal

**Files:**
- Modify: `static/js/components/toolbox.js` (add after recent targets functions)

- [ ] **Step 1: Add Modal open/close functions**

```javascript
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
  }
};

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.add('hidden');
  }
});
```

- [ ] **Step 2: Add Distribute Modal function**

```javascript
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
        <button class="btn-close" onclick="closeModal('distModal-${toolId}')">✕</button>
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
        <button class="btn btn-g btn-sm" onclick="closeModal('distModal-${toolId}')">取消</button>
        <button class="btn btn-p btn-sm" onclick="confirmModalDistribute(${toolId}, '${toolType}')">
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
};
```

- [ ] **Step 3: Add Pod change handler with capability detection**

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

- [ ] **Step 4: Add confirm distribute function**

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
    closeModal(`distModal-${toolId}`);
  } catch (e) {
    toast(`分发失败：${e.message}`, 'err');
  }
};
```

- [ ] **Step 5: Add form fill helper**

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

- [ ] **Step 6: Verify Modal opens**

Open browser, click distribute button, verify Modal appears.

---

### Task 6: Update Card Buttons

**Covers:** Distribute button, edit buttons

**Files:**
- Modify: `static/js/components/toolbox.js` (lines 60-76)

- [ ] **Step 1: Update distribute button onclick**

Find the distribute button in `renderBinaryToolCards`:

```javascript
<button class="btn btn-p btn-sm" onclick="toolboxSingleDistribute(${p.id}, 'binary', '${esc(p.install_path || '')}')">
```

Replace with:

```javascript
<button class="btn btn-p btn-sm" onclick="openDistributeModal(${p.id}, 'binary', '${esc(p.install_path || '')}')">
```

- [ ] **Step 2: Add edit button to binary cards**

Add edit button before distribute button:

```javascript
<button class="btn btn-g btn-sm" onclick="openEditBinaryModal(${p.id})">编辑</button>
```

- [ ] **Step 3: Add edit button to script cards**

Add edit button to script cards:

```javascript
<button class="btn btn-g btn-sm" onclick="openEditScriptModal(${t.id})">编辑</button>
```

- [ ] **Step 4: Verify buttons work**

Open browser, click edit and distribute buttons, verify modals open.

---

### Task 7: Clean Up Old Code

**Covers:** Remove inline form code

**Files:**
- Modify: `static/js/components/toolbox.js`

- [ ] **Step 1: Remove old toolboxSingleDistribute function**

Remove the entire `window.toolboxSingleDistribute` function.

- [ ] **Step 2: Remove old distToggleType function**

Remove the `window.distToggleType` function.

- [ ] **Step 3: Remove old inline form div**

Remove the toolbox-distribute-form div from renderBinaryToolCards.

- [ ] **Step 4: Verify no references to removed functions**

Run: `grep -r "toolboxSingleDistribute\|distToggleType" static/js/`
Expected: No matches.

---

### Task 8: Add Tests

**Covers:** Test coverage

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
2. Verify tab switching works
3. Verify search filters tools
4. Click "分发" on a binary tool → verify Modal opens
5. Select a recent target → verify form auto-fills
6. Manually select cluster/namespace/pod → verify capability badge appears
7. Click "确认分发" → verify success toast
8. Click "编辑" on tools → verify edit modals open
9. Click "查看记录" → verify history modal opens

- [ ] **Step 3: Commit changes**

```bash
git add static/index.html static/js/components/toolbox.js static/css/app.css tests/test_toolbox.py docs/compose/specs/2026-06-19-toolbox-full-redesign.md docs/compose/plans/2026-06-19-toolbox-full-redesign.md
git commit -m "feat: comprehensive toolbox UI redesign

- Tab-based navigation (Binary + Script tools)
- Modal-based distribution with quick-select
- Search/filter in all lists
- Pod capability detection
- Recent targets in localStorage
- Edit modals for binary and script tools
- Distribution history modal
- LLM-assisted script creation"
```
