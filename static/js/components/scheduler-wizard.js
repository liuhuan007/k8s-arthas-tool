/**
 * scheduler-wizard.js — 3 步任务创建向导
 * Step 1: 基本信息 + 执行目标
 * Step 2: 脚本配置
 * Step 3: 调度设置
 */
(function () {
  'use strict';

  var _step = 1;
  var _formData = {};
  var _overlay = null;

  // ── 公开入口 ──────────────────────────────────────────────────────────
  window.scOpenWizard = function (editTask) {
    _step = 1;
    _formData = editTask ? Object.assign({}, editTask) : {
      name: '',
      description: '',
      runtime: 'shell',
      target_type: 'node',
      target_config: {},
      script_source: 'inline',
      script_content: '',
      timeout_seconds: 300,
      schedule_type: 'none',
      cron_expr: '0 2 * * *',
      interval_seconds: 3600,
    };
    _render();
  };

  window.scCloseWizard = function () {
    if (_overlay && _overlay.parentNode) {
      _overlay.parentNode.removeChild(_overlay);
    }
    _overlay = null;
  };

  // ── 渲染 ──────────────────────────────────────────────────────────────
  function _render() {
    if (_overlay && _overlay.parentNode) _overlay.parentNode.removeChild(_overlay);
    _overlay = document.createElement('div');
    _overlay.className = 'sc-wizard-overlay';
    _overlay.onclick = function (e) { if (e.target === _overlay) scCloseWizard(); };

    var wizard = document.createElement('div');
    wizard.className = 'sc-wizard';
    wizard.innerHTML = '<div class="sc-wizard-title">' + (_formData.id ? '编辑任务' : '新建任务') + '</div>'
      + _renderSteps()
      + (_step === 1 ? _renderStep1() : _step === 2 ? _renderStep2() : _renderStep3());

    _overlay.appendChild(wizard);
    document.body.appendChild(_overlay);

    // 绑定事件
    _bindEvents();
    // 初始显示正确的区域
    if (_step === 2 && _formData.script_source === 'upload') {
      var fileArea = document.getElementById('sc-wiz-file-area');
      var editorArea = document.getElementById('sc-wiz-editor-area');
      if (fileArea) fileArea.style.display = '';
      if (editorArea) editorArea.style.display = 'none';
    }
  }

  function _renderSteps() {
    return '<div class="sc-steps">'
      + '<div class="sc-step-bar ' + (_step >= 1 ? 'active' : '') + (_step > 1 ? ' done' : '') + '"></div>'
      + '<div class="sc-step-bar ' + (_step >= 2 ? 'active' : '') + (_step > 2 ? ' done' : '') + '"></div>'
      + '<div class="sc-step-bar ' + (_step >= 3 ? 'active' : '') + '"></div>'
    + '</div>';
  }

  function _renderStep1() {
    return ''
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">任务名称 *</div>'
      + '  <input class="sc-field-input" id="sc-wiz-name" value="' + _esc(_formData.name || '') + '" placeholder="如: k8s_scan 集群巡检">'
      + '</div>'
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">说明</div>'
      + '  <input class="sc-field-input" id="sc-wiz-desc" value="' + _esc(_formData.description || '') + '" placeholder="简要描述任务用途">'
      + '</div>'
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">运行时</div>'
      + '  <div class="sc-option-group" id="sc-wiz-runtime">'
      + '    <div class="sc-option-btn' + (_formData.runtime === 'shell' ? ' active' : '') + '" data-val="shell">Shell</div>'
      + '    <div class="sc-option-btn' + (_formData.runtime === 'python' ? ' active' : '') + '" data-val="python">Python</div>'
      + '    <div class="sc-option-btn' + (_formData.runtime === 'binary' ? ' active' : '') + '" data-val="binary">Binary</div>'
      + '  </div>'
      + '</div>'
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">执行目标</div>'
      + '  <div class="sc-option-group" id="sc-wiz-target">'
      + '    <div class="sc-option-btn' + (_formData.target_type === 'node' ? ' active' : '') + '" data-val="node">🖥 Node 本机</div>'
      + '    <div class="sc-option-btn' + (_formData.target_type === 'pod' ? ' active' : '') + '" data-val="pod">📌 指定 Pod</div>'
      + '    <div class="sc-option-btn' + (_formData.target_type === 'namespace' ? ' active' : '') + '" data-val="namespace">🌐 按 NS</div>'
      + '  </div>'
      + (_formData.target_type === 'node'
        ? '<div class="sc-hint">Node 模式：脚本在服务器本机执行，无需选择 Pod</div>'
        : '<div class="sc-field" style="margin-top:8px">'
          + '  <div class="sc-field-label">目标配置 (JSON)</div>'
          + '  <textarea class="sc-field-input" id="sc-wiz-target-config" rows="3" placeholder=\'{"namespace":"default","pod_name":"my-pod"}\'>' + _esc(JSON.stringify(_formData.target_config || {})) + '</textarea>'
          + '</div>')
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">超时时间 (秒)</div>'
      + '  <div style="display:flex;align-items:center;gap:8px">'
      + '    <input class="sc-field-input" id="sc-wiz-timeout" type="number" value="' + (_formData.timeout_seconds || 300) + '" style="width:100px;text-align:center" min="1" max="3600">'
      + '    <span style="font-size:11px;color:var(--tx3)">秒 (1~3600)</span>'
      + '  </div>'
      + '</div>'
      + '<div class="sc-wizard-actions">'
      + '  <button class="sc-btn-cancel" onclick="scCloseWizard()">取消</button>'
      + '  <button class="sc-btn-next" onclick="scWizardNext()">下一步 →</button>'
      + '</div>';
  }

  function _renderStep2() {
    return ''
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">脚本来源</div>'
      + '  <div class="sc-option-group" id="sc-wiz-script-source">'
      + '    <div class="sc-option-btn' + (_formData.script_source === 'inline' ? ' active' : '') + '" data-val="inline">✏️ 在线编写</div>'
      + '    <div class="sc-option-btn' + (_formData.script_source === 'upload' ? ' active' : '') + '" data-val="upload">📁 上传文件</div>'
      + '    <div class="sc-option-btn' + (_formData.script_source === 'path' ? ' active' : '') + '" data-val="path">🔗 工具路径</div>'
      + '  </div>'
      + '</div>'
      + '<div class="sc-field" id="sc-wiz-editor-area">'
      + '  <div class="sc-field-label">脚本内容</div>'
      + '  <textarea class="sc-field-input" id="sc-wiz-script" rows="8" style="font-family:var(--mono);line-height:1.7" placeholder="#!/bin/bash\necho Hello">' + _esc(_formData.script_content || '') + '</textarea>'
      + '</div>'
      + '<div class="sc-field" id="sc-wiz-file-area" style="display:none">'
      + '  <div class="sc-field-label" id="sc-wiz-file-label">选择文件</div>'
      + '  <input type="file" id="sc-wiz-file-input" style="display:none" accept=".sh,.py,.bin,.txt,.bash">'
      + '  <div onclick="document.getElementById(\'sc-wiz-file-input\').click()" style="padding:20px;border:2px dashed var(--ln2);border-radius:8px;text-align:center;cursor:pointer;color:var(--tx3);font-size:12px;transition:border-color .15s" onmouseover="this.style.borderColor=\'#007AFF\'" onmouseout="this.style.borderColor=\'\'">'
      + '    <div style="font-size:24px;margin-bottom:8px">📁</div>'
      + '    <div>点击选择文件，或将文件拖拽到此处</div>'
      + '    <div style="font-size:10px;margin-top:4px;color:var(--tx3)">支持 .sh .py .bin .txt 格式</div>'
      + '  </div>'
      + '  <div id="sc-wiz-file-name" style="margin-top:8px;font-size:11px;color:var(--tx2);' + (_formData.uploaded_file_name ? '' : 'display:none') + '">'
      + (_formData.uploaded_file_name ? '已上传: ' + _esc(_formData.uploaded_file_name) : '')
      + '</div>'
      + '</div>'
      + '<div class="sc-field" id="sc-wiz-path-area" style="display:none">'
      + '  <div class="sc-field-label">工具路径</div>'
      + '  <input class="sc-field-input" id="sc-wiz-tool-path" placeholder="/opt/tools/k8s_scan" value="' + _esc(_formData.tool_path || '') + '">'
      + '</div>'
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">环境变量 (可选)</div>'
      + '  <div id="sc-wiz-env-list">'
      + _renderEnvRows()
      + '  </div>'
      + '  <div class="sc-env-add" onclick="scWizardAddEnv()">+ 添加变量</div>'
      + '</div>'
      + '<div class="sc-wizard-actions">'
      + '  <button class="sc-btn-cancel" onclick="scCloseWizard()">取消</button>'
      + '  <button class="sc-btn-next" onclick="scWizardPrev()">← 上一步</button>'
      + '  <button class="sc-btn-next" onclick="scWizardNext()">下一步 →</button>'
      + '</div>';
  }

  function _renderEnvRows() {
    var envs = _formData._envs || [];
    if (envs.length === 0) {
      return '<div class="sc-env-row">'
        + '<input class="sc-field-input sc-env-key" placeholder="KEY" data-idx="0">'
        + '<input class="sc-field-input sc-env-val" placeholder="VALUE" data-idx="0">'
      + '</div>';
    }
    return envs.map(function (e, i) {
      return '<div class="sc-env-row">'
        + '<input class="sc-field-input sc-env-key" value="' + _esc(e.key) + '" data-idx="' + i + '">'
        + '<input class="sc-field-input sc-env-val" value="' + _esc(e.val) + '" data-idx="' + i + '">'
      + '</div>';
    }).join('');
  }

  function _renderStep3() {
    var cronPresets = [
      { label: '每小时', expr: '0 * * * *' },
      { label: '每天 02:00', expr: '0 2 * * *' },
      { label: '每周一', expr: '0 9 * * 1' },
      { label: '每月1号', expr: '0 9 1 * *' },
    ];
    return ''
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">执行方式</div>'
      + '  <div class="sc-option-group" id="sc-wiz-schedule">'
      + '    <div class="sc-option-btn orange' + (_formData.schedule_type === 'cron' ? ' active' : '') + '" data-val="cron">⏱ Cron 定时</div>'
      + '    <div class="sc-option-btn' + (_formData.schedule_type === 'interval' ? ' active' : '') + '" data-val="interval">🔁 固定间隔</div>'
      + '    <div class="sc-option-btn' + (_formData.schedule_type === 'none' ? ' active' : '') + '" data-val="none">☝ 仅手动</div>'
      + '  </div>'
      + '</div>'
      + (_formData.schedule_type === 'cron'
        ? '<div class="sc-field">'
          + '  <div class="sc-field-label">Cron 表达式</div>'
          + '  <div style="display:flex;gap:8px;align-items:center">'
          + '    <input class="sc-field-input" id="sc-wiz-cron" value="' + _esc(_formData.cron_expr || '0 2 * * *') + '" style="width:160px;font-family:var(--mono);color:#FF9500">'
          + '    <span style="font-size:11px;color:var(--tx3)">= ' + _cronDesc(_formData.cron_expr || '0 2 * * *') + '</span>'
          + '  </div>'
          + '  <div class="sc-cron-quick" id="sc-wiz-cron-quick">'
          + cronPresets.map(function (p) {
            return '<div class="sc-cron-tag' + (p.expr === _formData.cron_expr ? ' active' : '') + '" data-expr="' + p.expr + '">' + p.label + '</div>';
          }).join('')
          + '  </div>'
          + '  <div class="sc-next-run" id="sc-wiz-next-run">下次执行: ' + _cronNextPreview(_formData.cron_expr || '0 2 * * *') + '</div>'
          + '</div>'
        : '')
      + (_formData.schedule_type === 'interval'
        ? '<div class="sc-field">'
          + '  <div class="sc-field-label">间隔 (秒)</div>'
          + '  <input class="sc-field-input" id="sc-wiz-interval" type="number" value="' + (_formData.interval_seconds || 3600) + '" style="width:120px" min="60">'
          + '</div>'
        : '')
      + '<div class="sc-field">'
      + '  <div class="sc-field-label">失败告警</div>'
      + '  <label style="display:flex;align-items:center;gap:6px;cursor:pointer">'
      + '    <input type="checkbox" id="sc-wiz-alert" checked style="accent-color:#007AFF">'
      + '    <span style="font-size:11px;color:var(--tx)">执行失败时发送告警通知</span>'
      + '  </label>'
      + '</div>'
      + '<div class="sc-wizard-actions">'
      + '  <button class="sc-btn-cancel" onclick="scCloseWizard()">取消</button>'
      + '  <button class="sc-btn-next" onclick="scWizardPrev()">← 上一步</button>'
      + '  <button class="sc-btn-submit" onclick="scWizardSubmit()">✓ ' + (_formData.id ? '保存' : '创建任务') + '</button>'
      + '</div>';
  }

  // ── 事件绑定 ──────────────────────────────────────────────────────────
  function _bindEvents() {
    // Runtime 选项
    _bindOptionGroup('sc-wiz-runtime', function (val) { _formData.runtime = val; });
    _bindOptionGroup('sc-wiz-target', function (val) {
      _formData.target_type = val;
      _render();
    });
    _bindOptionGroup('sc-wiz-script-source', function (val) {
      _formData.script_source = val;
      var fileArea = document.getElementById('sc-wiz-file-area');
      var editorArea = document.getElementById('sc-wiz-editor-area');
      if (val === 'upload') {
        if (fileArea) fileArea.style.display = '';
        if (editorArea) editorArea.style.display = 'none';
      } else if (val === 'path') {
        if (fileArea) fileArea.style.display = '';
        if (editorArea) editorArea.style.display = 'none';
      } else {
        if (fileArea) fileArea.style.display = 'none';
        if (editorArea) editorArea.style.display = '';
      }
    });
    _bindOptionGroup('sc-wiz-schedule', function (val) {
      _formData.schedule_type = val;
      _render();
    });

    // 文件上传
    var fileInput = document.getElementById('sc-wiz-file-input');
    if (fileInput) {
      fileInput.onchange = function () {
        var file = this.files[0];
        if (!file) return;
        _formData.uploaded_file_name = file.name;
        var nameEl = document.getElementById('sc-wiz-file-name');
        if (nameEl) { nameEl.textContent = '已选择: ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)'; nameEl.style.display = ''; }
        var reader = new FileReader();
        reader.onload = function (e) {
          _formData.script_content = e.target.result;
          var scriptEl = document.getElementById('sc-wiz-script');
          if (scriptEl) scriptEl.value = _formData.script_content;
        };
        reader.readAsText(file);
      };
    }

    // Cron 快捷标签
    var cronQuick = document.getElementById('sc-wiz-cron-quick');
    if (cronQuick) {
      cronQuick.onclick = function (e) {
        var tag = e.target.closest('.sc-cron-tag');
        if (!tag) return;
        var expr = tag.dataset.expr;
        _formData.cron_expr = expr;
        var input = document.getElementById('sc-wiz-cron');
        if (input) input.value = expr;
        cronQuick.querySelectorAll('.sc-cron-tag').forEach(function (t) { t.classList.remove('active'); });
        tag.classList.add('active');
        var preview = document.getElementById('sc-wiz-next-run');
        if (preview) preview.textContent = '下次执行: ' + _cronNextPreview(expr);
      };
    }
  }

  function _bindOptionGroup(id, onChange) {
    var el = document.getElementById(id);
    if (!el) return;
    el.onclick = function (e) {
      var btn = e.target.closest('.sc-option-btn');
      if (!btn) return;
      el.querySelectorAll('.sc-option-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      if (onChange) onChange(btn.dataset.val);
    };
  }

  // ── 步骤导航 ──────────────────────────────────────────────────────────
  window.scWizardNext = function () {
    _collectStepData();
    if (_step === 1 && !_formData.name.trim()) {
      alert('请输入任务名称');
      return;
    }
    if (_step < 3) { _step++; _render(); }
  };

  window.scWizardPrev = function () {
    _collectStepData();
    if (_step > 1) { _step--; _render(); }
  };

  function _collectStepData() {
    if (_step === 1) {
      var nameEl = document.getElementById('sc-wiz-name');
      var descEl = document.getElementById('sc-wiz-desc');
      var timeoutEl = document.getElementById('sc-wiz-timeout');
      var configEl = document.getElementById('sc-wiz-target-config');
      if (nameEl) _formData.name = nameEl.value;
      if (descEl) _formData.description = descEl.value;
      if (timeoutEl) _formData.timeout_seconds = parseInt(timeoutEl.value, 10) || 300;
      if (configEl) {
        try { _formData.target_config = JSON.parse(configEl.value); } catch (_) {}
      }
    }
    if (_step === 2) {
      var scriptEl = document.getElementById('sc-wiz-script');
      if (scriptEl) _formData.script_content = scriptEl.value;
      // 路径模式
      if (_formData.script_source === 'path') {
        var pathEl = document.getElementById('sc-wiz-tool-path');
        if (pathEl) _formData.tool_path = pathEl.value;
      }
      // 收集环境变量
      var envRows = document.querySelectorAll('#sc-wiz-env-list .sc-env-row');
      var envs = [];
      envRows.forEach(function (row) {
        var k = row.querySelector('.sc-env-key');
        var v = row.querySelector('.sc-env-val');
        if (k && v && k.value.trim()) envs.push({ key: k.value.trim(), val: v.value });
      });
      _formData._envs = envs;
    }
    if (_step === 3) {
      var cronEl = document.getElementById('sc-wiz-cron');
      var intervalEl = document.getElementById('sc-wiz-interval');
      if (cronEl) _formData.cron_expr = cronEl.value;
      if (intervalEl) _formData.interval_seconds = parseInt(intervalEl.value, 10) || 3600;
    }
  }

  window.scWizardAddEnv = function () {
    if (!_formData._envs) _formData._envs = [];
    _formData._envs.push({ key: '', val: '' });
    var list = document.getElementById('sc-wiz-env-list');
    if (list) list.innerHTML = _renderEnvRows();
  };

  // ── 提交 ──────────────────────────────────────────────────────────────
  window.scWizardSubmit = async function () {
    _collectStepData();
    if (!_formData.name.trim()) { alert('请输入任务名称'); return; }

    var payload = {
      name: _formData.name,
      description: _formData.description,
      runtime: _formData.runtime,
      target_type: _formData.target_type,
      target_config: _formData.target_config || {},
      script_source: _formData.script_source,
      script_content: _formData.script_content,
      uploaded_file_name: _formData.uploaded_file_name || '',
      timeout_seconds: _formData.timeout_seconds,
    };

    try {
      var result;
      if (_formData.id) {
        result = await safePost('/scheduler/tasks/' + _formData.id, payload);
      } else {
        result = await safePost('/scheduler/tasks', payload);
      }
      // 更新调度
      var taskId = (result && result.task && result.task.id) || _formData.id;
      if (taskId && _formData.schedule_type !== undefined) {
        await safePost('/scheduler/tasks/' + taskId + '/schedule', {
          schedule_type: _formData.schedule_type,
          cron_expr: _formData.cron_expr || '',
          interval_seconds: _formData.interval_seconds || 0,
        });
      }
      scCloseWizard();
      if (typeof scLoadTasks === 'function') scLoadTasks();
      if (typeof toast === 'function') toast(_formData.id ? '任务已更新' : '任务已创建', 'success');
    } catch (e) {
      alert('操作失败: ' + e.message);
    }
  };

  // ── 工具 ──────────────────────────────────────────────────────────────
  function _esc(s) {
    var d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  var _cronDescMap = {
    '0 * * * *': '每小时',
    '0 2 * * *': '每天凌晨 2:00',
    '0 9 * * 1': '每周一 9:00',
    '0 9 1 * *': '每月1号 9:00',
  };
  function _cronDesc(expr) { return _cronDescMap[expr] || expr; }

  function _cronNextPreview(expr) {
    var now = new Date();
    var parts = expr.split(' ');
    if (parts.length !== 5) return '(无法解析)';
    var next = new Date(now);
    var minute = parseInt(parts[0], 10);
    var hour = parseInt(parts[1], 10);
    if (!isNaN(minute)) next.setMinutes(minute);
    if (!isNaN(hour)) next.setHours(hour);
    next.setSeconds(0);
    if (next <= now) next.setDate(next.getDate() + 1);
    return next.toLocaleString('zh-CN') + ' (约 ' + Math.round((next - now) / 3600000) + ' 小时后)';
  }

})();
