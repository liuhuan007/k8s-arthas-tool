/* ═══════════════════════════════════════════════════════════════════════════
 * Skill 市场管理页面 JS
 * API: /api/skills/marketplace (sources/browse/install/updates)
 * ═══════════════════════════════════════════════════════════════════════════ */

const MKT_API = '/api/skills/marketplace';

// ── Toast ──────────────────────────────────────────────────────────────────
function mktToast(msg, type) {
    type = type || 'info';
    var c = document.getElementById('toastContainer');
    if (!c) return;
    var d = document.createElement('div');
    d.className = 'toast toast-' + type;
    d.textContent = msg;
    c.appendChild(d);
    setTimeout(function () { d.remove(); }, 3500);
}

// ── Modal helpers ──────────────────────────────────────────────────────────
function openMktModal(id) { var el = document.getElementById(id); if (el) el.classList.add('open'); }
function closeMktModal(id) { var el = document.getElementById(id); if (el) el.classList.remove('open'); }

// ── Tab switching ──────────────────────────────────────────────────────────
function switchMarketTab(tab) {
    ['tab-sources', 'tab-browse'].forEach(function (t) {
        document.getElementById(t).style.display = t === 'tab-' + tab ? 'block' : 'none';
    });
    document.querySelectorAll('.mkt-tab').forEach(function (el) {
        el.classList.toggle('active', el.dataset.tab === tab);
    });
    if (tab === 'sources') loadSources();
    if (tab === 'browse') loadBrowse();
}

// ── Helper: escape HTML ────────────────────────────────────────────────────
function esc(s) {
    if (s == null) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
}
function showMktErr(id, msg) { var el = document.getElementById(id); if (el) { el.textContent = msg; el.classList.add('show'); } }

// ── 市场源管理 ──────────────────────────────────────────────────────────────
async function loadSources() {
    var tbody = document.getElementById('sourceTableBody');
    tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">加载中...</td></tr>';
    try {
        var resp = await fetch(MKT_API + '/sources', { credentials: 'include' });
        var data = await resp.json();
        if (!data.ok) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + esc(data.error) + '</td></tr>'; return; }
        var sources = data.sources || [];
        if (!sources.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">暂无市场源，点击上方添加</td></tr>'; return; }
        tbody.innerHTML = sources.map(function (s) {
            var lastSync = s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : '—';
            return '<tr>' +
                '<td><strong>' + esc(s.name) + '</strong></td>' +
                '<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><a href="' + esc(s.repo_url) + '" target="_blank">' + esc(s.repo_url) + '</a></td>' +
                '<td>' + esc(s.branch || 'main') + '</td>' +
                '<td>' + (s.skill_count != null ? s.skill_count : '—') + '</td>' +
                '<td>' + lastSync + '</td>' +
                '<td><div class="actions">' +
                '<button class="ab ab-g ab-sm" onclick="syncSource(' + s.id + ')">同步</button>' +
                '<button class="ab ab-g ab-sm" onclick="showEditSource(' + s.id + ')">编辑</button>' +
                '<button class="ab ab-d ab-sm" onclick="removeSource(' + s.id + ',\'' + esc(s.name) + '\')">删除</button>' +
                '</div></td></tr>';
        }).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">请求失败: ' + esc(e.message) + '</td></tr>';
    }
}

function showAddSourceModal() {
    document.getElementById('addSourceName').value = '';
    document.getElementById('addSourceUrl').value = '';
    document.getElementById('addSourceBranch').value = 'main';
    document.getElementById('addSourceError').classList.remove('show');
    openMktModal('addSourceModal');
}

async function addSource() {
    var name = document.getElementById('addSourceName').value.trim();
    var url = document.getElementById('addSourceUrl').value.trim();
    var branch = document.getElementById('addSourceBranch').value.trim() || 'main';
    if (!name || !url) { showMktErr('addSourceError', '名称和 URL 不能为空'); return; }
    try {
        var resp = await fetch(MKT_API + '/sources', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, repo_url: url, branch: branch })
        });
        var data = await resp.json();
        if (data.ok) {
            mktToast('市场源添加成功', 'success');
            closeMktModal('addSourceModal');
            loadSources();
        } else {
            showMktErr('addSourceError', data.error || '添加失败');
        }
    } catch (e) {
        showMktErr('addSourceError', '请求失败: ' + e.message);
    }
}

var _editSourceId = null;

function showEditSource(id) {
    _editSourceId = id;
    document.getElementById('editSourceError').classList.remove('show');
    // Fetch current source data
    fetch(MKT_API + '/sources', { credentials: 'include' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok) return;
            var src = (data.sources || []).find(function (s) { return s.id === id; });
            if (!src) return;
            document.getElementById('editSourceName').value = src.name || '';
            document.getElementById('editSourceUrl').value = src.repo_url || '';
            document.getElementById('editSourceBranch').value = src.branch || 'main';
            openMktModal('editSourceModal');
        });
}

async function saveSourceEdit() {
    var name = document.getElementById('editSourceName').value.trim();
    var url = document.getElementById('editSourceUrl').value.trim();
    var branch = document.getElementById('editSourceBranch').value.trim() || 'main';
    if (!name || !url) { showMktErr('editSourceError', '名称和 URL 不能为空'); return; }
    try {
        var resp = await fetch(MKT_API + '/sources/' + _editSourceId, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, repo_url: url, branch: branch })
        });
        var data = await resp.json();
        if (data.ok) {
            mktToast('市场源已更新', 'success');
            closeMktModal('editSourceModal');
            _editSourceId = null;
            loadSources();
        } else {
            showMktErr('editSourceError', data.error || '更新失败');
        }
    } catch (e) {
        showMktErr('editSourceError', '请求失败: ' + e.message);
    }
}

async function syncSource(id) {
    try {
        var resp = await fetch(MKT_API + '/sources/' + id + '/sync', {
            method: 'POST', credentials: 'include'
        });
        var data = await resp.json();
        if (data.ok) {
            mktToast('同步成功，发现 ' + (data.result?.skill_count || 0) + ' 个技能', 'success');
            loadSources();
        } else {
            mktToast('同步失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        mktToast('请求失败: ' + e.message, 'error');
    }
}

async function removeSource(id, name) {
    if (!confirm('确定要删除市场源 "' + name + '" 吗？')) return;
    try {
        var resp = await fetch(MKT_API + '/sources/' + id, { method: 'DELETE', credentials: 'include' });
        var data = await resp.json();
        if (data.ok) {
            mktToast('已删除', 'success');
            loadSources();
        } else {
            mktToast('删除失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        mktToast('请求失败: ' + e.message, 'error');
    }
}

// ── 浏览市场 ────────────────────────────────────────────────────────────────
async function loadBrowse() {
    var container = document.getElementById('browseContainer');
    container.innerHTML = '<div class="empty-msg">加载中...</div>';
    try {
        var keyword = document.getElementById('browseSearch').value.trim();
        var category = document.getElementById('browseCategory').value;
        var params = new URLSearchParams();
        if (keyword) params.set('keyword', keyword);
        if (category) params.set('category', category);

        var resp = await fetch(MKT_API + '/browse?' + params.toString(), { credentials: 'include' });
        var data = await resp.json();
        if (!data.ok) { container.innerHTML = '<div class="empty-msg">' + esc(data.error) + '</div>'; return; }

        var skills = data.skills || [];
        var countEl = document.getElementById('browseCount');
        if (countEl) countEl.textContent = '共 ' + skills.length + ' 个技能';

        if (!skills.length) {
            container.innerHTML = '<div class="empty-msg">暂无可用技能，请先添加并同步市场源</div>';
            return;
        }

        var catLabel = { quick: '快速诊断', tool: '工具', scenario: '场景方案', ai: '智能诊断' };

        container.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">' +
            skills.map(function (s) {
                var cat = catLabel[s.category] || s.category || '—';
                var statusHtml = '';
                var actionHtml = '';
                if (s.installed) {
                    if (s.latest) {
                        statusHtml = '<span class="badge bg-testing" style="font-size:10px">⚠ v' + esc(s.current || s.version) + ' → v' + esc(s.latest) + '</span>';
                        actionHtml = '<button class="ab ab-w ab-sm" onclick="updateMarketSkill(' + s.skill_id + ')">⬆ 更新</button>' +
                            ' <button class="ab ab-g ab-sm" onclick="mktToast(\'编辑功能请在本地技能面板操作\',\'info\')">✏ 编辑</button>';
                    } else {
                        statusHtml = '<span class="badge bg-published" style="font-size:10px">✓ v' + esc(s.version) + '</span>';
                        actionHtml = '<button class="ab ab-g ab-sm" onclick="mktToast(\'编辑功能请在本地技能面板操作\',\'info\')">✏ 编辑</button>';
                    }
                } else {
                    actionHtml = '<button class="ab ab-p ab-sm" onclick="installSkill(' + s.source_id + ',\'' + esc(s.name) + '\')">安装</button>';
                }
                return '<div style="background:var(--bg1);border:1px solid var(--ln);border-radius:6px;padding:14px">' +
                    '<div style="font-size:13px;font-weight:600;color:var(--tx);margin-bottom:4px">' + esc(s.name || '—') + '</div>' +
                    '<div style="font-size:10px;color:var(--tx3);margin-bottom:8px">' +
                    '<span class="badge bg-cat">' + cat + '</span>' +
                    ' <span style="color:var(--tx3)">v' + esc(s.version || '—') + '</span>' +
                    ' <span style="color:var(--tx3)">| ' + esc(s.source_name || '') + '</span>' +
                    ' ' + statusHtml +
                    '</div>' +
                    '<div style="font-size:11px;color:var(--tx2);margin-bottom:10px;min-height:28px">' + esc((s.description || '').substring(0, 80)) + '</div>' +
                    '<div class="actions">' + actionHtml + '</div>' +
                    '</div>';
            }).join('') + '</div>';
    } catch (e) {
        container.innerHTML = '<div class="empty-msg">请求失败: ' + esc(e.message) + '</div>';
    }
}

async function installSkill(sourceId, skillName) {
    try {
        var resp = await fetch(MKT_API + '/install/' + sourceId + '/' + encodeURIComponent(skillName), {
            method: 'POST', credentials: 'include'
        });
        var data = await resp.json();
        if (data.ok) {
            mktToast('安装成功: ' + skillName, 'success');
            loadBrowse();
            // Also trigger local list refresh if loaded
            if (typeof loadSkills === 'function') loadSkills();
        } else {
            mktToast('安装失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        mktToast('请求失败: ' + e.message, 'error');
    }
}

async function updateMarketSkill(skillId) {
    try {
        var resp = await fetch(MKT_API + '/update/' + skillId, {
            method: 'POST', credentials: 'include'
        });
        var data = await resp.json();
        if (data.ok) {
            mktToast('更新成功', 'success');
            loadBrowse();
        } else {
            mktToast('更新失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        mktToast('请求失败: ' + e.message, 'error');
    }
}

// ── GitHub 直接导入 ─────────────────────────────────────────────────────────
function showGitHubImportModal() {
    document.getElementById('ghRepoUrl').value = '';
    document.getElementById('ghBranch').value = 'main';
    document.getElementById('ghImportError').classList.remove('show');
    document.getElementById('ghPreviewArea').innerHTML = '';
    openMktModal('gitHubImportModal');
}

async function previewGitHubRepo() {
    var url = document.getElementById('ghRepoUrl').value.trim();
    var branch = document.getElementById('ghBranch').value.trim() || 'main';
    if (!url) { showMktErr('ghImportError', '请输入仓库 URL'); return; }

    document.getElementById('ghPreviewArea').innerHTML = '<div class="empty-msg">扫描中...</div>';

    try {
        var resp = await fetch('/api/skills/registry/import-from-github', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url: url, branch: branch, selected_skills: [] })
        });
        var data = await resp.json();
        if (!data.ok) {
            document.getElementById('ghPreviewArea').innerHTML = '<div class="err-box show">' + esc(data.error) + '</div>';
            return;
        }
        var imported = data.imported || [];
        document.getElementById('ghPreviewArea').innerHTML = imported.length
            ? '<div class="ok-box show">扫描完成，发现 ' + imported.length + ' 个技能</div>'
            : '<div class="empty-msg">未发现可导入的技能，请检查仓库结构</div>';
    } catch (e) {
        document.getElementById('ghPreviewArea').innerHTML = '<div class="err-box show">请求失败: ' + esc(e.message) + '</div>';
    }
}
