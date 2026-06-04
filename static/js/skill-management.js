/* ═══════════════════════════════════════════════════════════════════════════
 * Skill 管理页面 JS
 * API: /api/skills/registry (CRUD) + /api/skills/registry/import,validate,publish
 * ═══════════════════════════════════════════════════════════════════════════ */

const API = '/api/skills/registry';
let _selectedFile = null;

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(msg, type) {
    type = type || 'info';
    const c = document.getElementById('toastContainer');
    if (!c) return;
    const d = document.createElement('div');
    d.className = 'toast toast-' + type;
    d.textContent = msg;
    c.appendChild(d);
    setTimeout(function() { d.remove(); }, 3500);
}

// ── Modal helpers ──────────────────────────────────────────────────────────
function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('open');
}
function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('open');
}

// ── Stats ──────────────────────────────────────────────────────────────────
async function loadStats() {
    try {
        var resp = await fetch(API + '/stats', { credentials: 'include' });
        var data = await resp.json();
        if (!data.ok) return;
        var s = data.stats || {};
        document.getElementById('statTotal').textContent = s.total ?? '—';
        document.getElementById('statDraft').textContent = s.by_status?.draft ?? '—';
        document.getElementById('statPublished').textContent = s.by_status?.published ?? '—';
        document.getElementById('statArchived').textContent = s.by_status?.archived ?? '—';
    } catch (e) {
        console.error('loadStats', e);
    }
}

// ── List ───────────────────────────────────────────────────────────────────
async function loadSkills() {
    var tbody = document.getElementById('skillTableBody');
    tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">加载中...</td></tr>';

    try {
        var params = new URLSearchParams();
        var cat = document.getElementById('filterCategory').value;
        var st = document.getElementById('filterStatus').value;
        var src = document.getElementById('filterSource').value;
        var kw = document.getElementById('searchInput').value.trim();
        if (cat) params.set('category', cat);
        if (st) params.set('status', st);
        if (src) params.set('source', src);
        if (kw) params.set('keyword', kw);

        var resp = await fetch(API + '?' + params.toString(), { credentials: 'include' });
        var data = await resp.json();
        if (!data.ok) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">加载失败: ' + (data.error || '未知错误') + '</td></tr>';
            return;
        }

        var skills = data.skills || [];
        if (!skills.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">暂无 Skill 数据</td></tr>';
            return;
        }

        tbody.innerHTML = skills.map(function(s) {
            var stCls = 'bg-' + (s.status || 'draft');
            var catLabel = { quick:'快速诊断', tool:'工具', scenario:'场景方案', ai:'智能诊断' }[s.category] || s.category || '—';
            return '<tr>' +
                '<td><strong>' + esc(s.name || '—') + '</strong></td>' +
                '<td><span class="badge bg-cat">' + esc(catLabel) + '</span></td>' +
                '<td>Lv.' + (s.level || '—') + '</td>' +
                '<td><span class="badge ' + stCls + '">' + esc(s.status || '—') + '</span></td>' +
                '<td>' + esc(s.source || '—') + '</td>' +
                '<td>' + esc(s.version || '—') + '</td>' +
                '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(s.description || '') + '</td>' +
                '<td><div class="actions">' + renderActions(s) + '</div></td>' +
                '</tr>';
        }).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">请求失败: ' + esc(e.message) + '</td></tr>';
    }
}

function renderActions(s) {
    var id = s.id;
    var parts = [];
    parts.push('<button class="ab ab-g ab-sm" onclick="viewSkill(' + id + ')">详情</button>');
    if (s.status === 'draft' || s.status === 'validated') {
        parts.push('<button class="ab ab-g ab-sm" onclick="validateSkill(' + id + ')">校验</button>');
    }
    if (s.status !== 'published' && s.status !== 'archived') {
        parts.push('<button class="ab ab-p ab-sm" onclick="publishSkill(' + id + ')">发布</button>');
    }
    if (s.status !== 'archived') {
        parts.push('<button class="ab ab-w ab-sm" onclick="archiveSkill(' + id + ')">归档</button>');
    } else {
        parts.push('<button class="ab ab-g ab-sm" onclick="restoreSkill(' + id + ')">恢复</button>');
    }
    parts.push('<button class="ab ab-d ab-sm" onclick="deleteSkill(' + id + ',\'' + esc(s.name || '') + '\')">删除</button>');
    return parts.join('');
}

// ── Search ─────────────────────────────────────────────────────────────────
function onSearchKeyup(e) {
    if (e.key === 'Enter') loadSkills();
}

function clearFilters() {
    document.getElementById('filterCategory').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('filterSource').value = '';
    document.getElementById('searchInput').value = '';
    loadSkills();
}

// ── View Detail ────────────────────────────────────────────────────────────
async function viewSkill(id) {
    openModal('detailModal');
    document.getElementById('detailBody').innerHTML = '<div class="empty-msg">加载中...</div>';
    document.getElementById('detailTitle').textContent = 'Skill 详情';

    try {
        var resp = await fetch(API + '/' + id, { credentials: 'include' });
        var data = await resp.json();
        if (!data.ok) {
            document.getElementById('detailBody').innerHTML = '<div class="err-box show">' + esc(data.error || '加载失败') + '</div>';
            return;
        }
        var s = data.skill;
        document.getElementById('detailTitle').textContent = 'Skill: ' + (s.name || id);

        var html = '';
        html += '<div class="detail-section">';
        html += '<h3>基本信息</h3>';
        html += detailRow('名称', s.name);
        html += detailRow('分类', s.category);
        html += detailRow('等级', 'Level ' + (s.level || '—'));
        html += detailRow('状态', s.status);
        html += detailRow('来源', s.source);
        html += detailRow('版本', s.version);
        html += detailRow('描述', s.description || '—');
        html += detailRow('创建时间', s.created_at || '—');
        html += detailRow('更新时间', s.updated_at || '—');
        html += '</div>';

        if (s.arthas_command) {
            html += '<div class="detail-section"><h3>Arthas 命令</h3>';
            html += '<div class="detail-json">' + esc(s.arthas_command) + '</div></div>';
        }

        if (s.parameters_schema && (typeof s.parameters_schema === 'object' ? Object.keys(s.parameters_schema).length : s.parameters_schema)) {
            html += '<div class="detail-section"><h3>参数定义</h3>';
            html += '<div class="detail-json">' + esc(JSON.stringify(s.parameters_schema, null, 2)) + '</div></div>';
        }

        if (s.steps && Array.isArray(s.steps) && s.steps.length) {
            html += '<div class="detail-section"><h3>执行步骤</h3>';
            html += '<div class="detail-json">' + esc(JSON.stringify(s.steps, null, 2)) + '</div></div>';
        }

        if (s.prerequisites && s.prerequisites.length) {
            html += '<div class="detail-section"><h3>前置条件</h3>';
            html += '<div class="detail-json">' + esc(JSON.stringify(s.prerequisites, null, 2)) + '</div></div>';
        }

        document.getElementById('detailBody').innerHTML = html;
    } catch (e) {
        document.getElementById('detailBody').innerHTML = '<div class="err-box show">请求失败: ' + esc(e.message) + '</div>';
    }
}

function detailRow(label, value) {
    return '<div class="detail-row"><span class="lbl">' + esc(label) + '</span><span class="val">' + esc(value ?? '—') + '</span></div>';
}

// ── Import ─────────────────────────────────────────────────────────────────
function showImportModal() {
    _selectedFile = null;
    document.getElementById('importJson').value = '';
    document.getElementById('fileInput').value = '';
    document.getElementById('fileDropText').textContent = '点击或拖拽文件到此处（支持 JSON / YAML）';
    hide('importError'); hide('importOk');
    openModal('importModal');
}

function onFileSelected(e) {
    var files = e.target.files || e.dataTransfer.files;
    if (files.length) {
        _selectedFile = files[0];
        document.getElementById('fileDropText').textContent = '已选择: ' + _selectedFile.name + ' (' + formatSize(_selectedFile.size) + ')';
    }
}

async function importSkill() {
    hide('importError'); hide('importOk');

    try {
        var resp;

        if (_selectedFile) {
            var form = new FormData();
            form.append('file', _selectedFile);
            resp = await fetch(API + '/import', { method: 'POST', credentials: 'include', body: form });
        } else {
            var jsonText = document.getElementById('importJson').value.trim();
            if (!jsonText) {
                showErr('importError', '请选择文件或粘贴 JSON');
                return;
            }
            var parsed;
            try { parsed = JSON.parse(jsonText); } catch (e) {
                showErr('importError', 'JSON 格式错误: ' + e.message);
                return;
            }
            resp = await fetch(API + '/import', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(parsed)
            });
        }

        var data = await resp.json();
        if (data.ok) {
            showOk('importOk', '导入成功! Skill ID: ' + (data.skill_id || '—'));
            toast('Skill 导入成功', 'success');
            loadStats(); loadSkills();
            setTimeout(function() { closeModal('importModal'); }, 1200);
        } else {
            showErr('importError', data.error || '导入失败');
        }
    } catch (e) {
        showErr('importError', '请求失败: ' + e.message);
    }
}

// ── Create ─────────────────────────────────────────────────────────────────
function showCreateModal() {
    document.getElementById('createName').value = '';
    document.getElementById('createCategory').value = 'quick';
    document.getElementById('createLevel').value = '1';
    document.getElementById('createDescription').value = '';
    document.getElementById('createCommand').value = '';
    document.getElementById('createVersion').value = '1.0.0';
    hide('createError');
    openModal('createModal');
}

async function createSkill() {
    hide('createError');
    var name = document.getElementById('createName').value.trim();
    if (!name) { showErr('createError', '名称不能为空'); return; }

    var body = {
        name: name,
        category: document.getElementById('createCategory').value,
        level: parseInt(document.getElementById('createLevel').value, 10),
        description: document.getElementById('createDescription').value.trim(),
        arthas_command: document.getElementById('createCommand').value.trim(),
        version: document.getElementById('createVersion').value.trim() || '1.0.0',
        status: 'draft',
        source: 'custom'
    };

    try {
        var resp = await fetch(API + '/import', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        var data = await resp.json();
        if (data.ok) {
            toast('Skill 创建成功', 'success');
            closeModal('createModal');
            loadStats(); loadSkills();
        } else {
            showErr('createError', data.error || '创建失败');
        }
    } catch (e) {
        showErr('createError', '请求失败: ' + e.message);
    }
}

// ── Actions ────────────────────────────────────────────────────────────────
async function validateSkill(id) {
    try {
        var resp = await fetch(API + '/' + id + '/validate', { method: 'POST', credentials: 'include' });
        var data = await resp.json();
        if (data.ok) {
            toast('校验通过', 'success');
            loadSkills(); loadStats();
        } else {
            var errMsg = (data.errors || []).join('; ') || data.error || '校验失败';
            toast('校验失败: ' + errMsg, 'error');
        }
    } catch (e) {
        toast('请求失败: ' + e.message, 'error');
    }
}

async function publishSkill(id) {
    try {
        var resp = await fetch(API + '/' + id + '/publish', { method: 'POST', credentials: 'include' });
        var data = await resp.json();
        if (data.ok) {
            toast('发布成功! 能力 ID: ' + (data.capability_id || '—'), 'success');
            loadSkills(); loadStats();
        } else {
            toast('发布失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        toast('请求失败: ' + e.message, 'error');
    }
}

async function archiveSkill(id) {
    try {
        var resp = await fetch(API + '/' + id, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'archived' })
        });
        var data = await resp.json();
        if (data.ok) {
            toast('已归档', 'success');
            loadSkills(); loadStats();
        } else {
            toast('归档失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        toast('请求失败: ' + e.message, 'error');
    }
}

async function restoreSkill(id) {
    try {
        var resp = await fetch(API + '/' + id, {
            method: 'PUT', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'draft' })
        });
        var data = await resp.json();
        if (data.ok) {
            toast('已恢复为草稿', 'success');
            loadSkills(); loadStats();
        } else {
            toast('恢复失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        toast('请求失败: ' + e.message, 'error');
    }
}

async function deleteSkill(id, name) {
    if (!confirm('确定要删除 Skill "' + name + '" 吗？此操作不可恢复。')) return;
    try {
        var resp = await fetch(API + '/' + id, { method: 'DELETE', credentials: 'include' });
        var data = await resp.json();
        if (data.ok) {
            toast('已删除', 'success');
            loadSkills(); loadStats();
        } else {
            toast('删除失败: ' + (data.error || ''), 'error');
        }
    } catch (e) {
        toast('请求失败: ' + e.message, 'error');
    }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) {
    if (s == null) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function showErr(id, msg) { var el = document.getElementById(id); if (el) { el.textContent = msg; el.classList.add('show'); } }
function showOk(id, msg) { var el = document.getElementById(id); if (el) { el.textContent = msg; el.classList.add('show'); } }
function hide(id) { var el = document.getElementById(id); if (el) el.classList.remove('show'); }
