# 工具分发交互重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline distribute form with a Modal dialog featuring quick-select from recent targets and Pod capability awareness.

**Architecture:** Modal-based distribution flow with localStorage-backed recent targets. Replaces the cramped inline form in each toolbox card with a spacious modal that offers one-click target selection.

**Tech Stack:** Vanilla JavaScript, CSS animations, localStorage

---

## File Structure

| File | Responsibility |
|------|---------------|
| `static/js/components/toolbox.js` | Modal logic, recent targets, distribute flow |
| `static/css/app.css` | Modal and quick-select styles |
| `tests/test_toolbox.py` | Test Modal interaction |

---

### Task 1: Add Modal CSS Styles

**Covers:** [S5]

**Files:**
- Modify: `static/css/app.css` (append after line ~3230)

- [ ] **Step 1: Add Modal overlay and container styles**

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

- [ ] **Step 2: Add quick-select section styles**

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

- [ ] **Step 3: Add capability badge styles**

```css
/* ── Capability Badge ── */
.dist-cap-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
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

- [ ] **Step 4: Verify styles load**

Run: Open browser dev tools, check no CSS errors in console.

---

### Task 2: Add Recent Targets JavaScript Functions

**Covers:** [S3]

**Files:**
- Modify: `static/js/components/toolbox.js` (add after line ~333, before `toolboxSingleDistribute`)

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

- [ ] **Step 2: Verify functions are defined**

Run: Open browser console, check `_loadRecentTargets` is defined.

---

### Task 3: Add Modal Open/Close Logic

**Covers:** [S2], [S4]

**Files:**
- Modify: `static/js/components/toolbox.js` (add after recent target functions)

- [ ] **Step 1: Add Modal open function**

```javascript
// ═══════════════════════════════════════════════════════════════
// Distribute Modal
// ═══════════════════════════════════════════════════════════════

window.openDistributeModal = async function(toolId, toolType, defaultPath) {
  // Remove existing modal if any
  const existing = document.getElementById(`distModal-${toolId}`);
  if (existing) existing.remove();

  // Get tool info from card
  const card = document.querySelector(`.toolbox-card[data-id="${toolId}"]`);
  const toolName = card?.querySelector('.toolbox-card-name')?.textContent || `Tool #${toolId}`;

  // Load clusters
  const clusters = await _loadDistClusters();
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

  // Close on overlay click
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

Run: Open browser, click distribute button on a tool card, verify Modal appears.

---

### Task 4: Update Card Button to Use Modal

**Covers:** [S2]

**Files:**
- Modify: `static/js/components/toolbox.js` (line ~64)

- [ ] **Step 1: Update distribute button onclick**

Find the line:
```javascript
<button class="btn btn-p btn-sm" onclick="toolboxSingleDistribute(${p.id}, 'binary', '${esc(p.install_path || '')}')">
```

Replace with:
```javascript
<button class="btn btn-p btn-sm" onclick="openDistributeModal(${p.id}, 'binary', '${esc(p.install_path || '')}')">
```

- [ ] **Step 2: Remove old inline form div**

Find and remove this line:
```javascript
<div class="toolbox-distribute-form" id="distForm-binary-${p.id}" style="display:none"></div>
```

- [ ] **Step 3: Verify button opens Modal**

Run: Open browser, click distribute button, verify Modal opens instead of inline form.

---

### Task 5: Clean Up Old Inline Form Code

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

### Task 6: Add Tests

**Covers:** [S7]

**Files:**
- Modify: `tests/test_toolbox.py`

- [ ] **Step 1: Add test for Modal endpoint availability**

```python
def test_distribute_modal_page_loads(self):
    """Toolbox page loads without errors."""
    resp = self.client.get('/tasks')
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_toolbox.py -v`
Expected: All tests pass.

---

### Task 7: Final Verification

**Covers:** All

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/test_toolbox.py tests/test_task_center_toolchain.py -v`
Expected: All tests pass.

- [ ] **Step 2: Manual browser verification**

1. Open toolbox page
2. Click "分发" on a binary tool
3. Verify Modal opens with recent targets section
4. Select a recent target → verify form auto-fills
5. Manually select cluster/namespace/pod → verify capability badge appears
6. Click "确认分发" → verify success toast and Modal closes
7. Re-open Modal → verify target appears in recent list

- [ ] **Step 3: Commit changes**

```bash
git add static/js/components/toolbox.js static/css/app.css tests/test_toolbox.py docs/compose/specs/2026-06-19-distribute-interaction-redesign.md docs/compose/plans/2026-06-19-distribute-interaction-redesign.md
git commit -m "feat: replace inline distribute form with Modal dialog

- Modal with quick-select from recent targets
- Pod capability detection and badge display
- localStorage-backed recent targets (max 5)
- Removed old inline form code"
```
