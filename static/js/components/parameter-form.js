/**
 * parameter-form.js — 通用参数表单组件
 *
 * 功能：
 * 1. 根据 parameters_schema JSON 动态渲染输入字段
 * 2. 支持 text / number / select / textarea / boolean / password 字段类型
 * 3. 前端校验（必填、正则、范围、长度）
 * 4. 提供 open / close / submit 三段式 API
 * 5. 与 diagnosis.js 的 diagShowParameterForm 互为补充
 */
(function () {
  'use strict';

  // ── 状态 ──────────────────────────────────────────────────────────────
  let _currentSchema = null;   // 当前表单 schema 数组
  let _currentCapability = null; // 当前能力对象

  // ════════════════════════════════════════════════════════════════════════
  // 公开 API
  // ════════════════════════════════════════════════════════════════════════

  /**
   * 打开参数表单
   * @param {object} capability - 能力对象（含 parameters_schema）
   * @param {Function} onSubmit - 提交回调 (params: Record<string, any>)
   */
  window.paramFormOpen = function (capability, onSubmit) {
    _currentCapability = capability;
    _currentSchema = _parseSchema(capability.parameters_schema);

    if (!_currentSchema || _currentSchema.length === 0) {
      // 无参数，直接调用提交
      if (typeof onSubmit === 'function') onSubmit({});
      return;
    }

    _render(capability, onSubmit);
    _showModal();
  };

  /**
   * 关闭表单
   */
  window.paramFormClose = function () {
    _hideModal();
    _currentSchema = null;
    _currentCapability = null;
  };

  /**
   * 通过能力 ID 打开表单（从后端拉取详情）
   * @param {number} capId
   * @param {Function} onSubmit
   */
  window.paramFormOpenById = async function (capId, onSubmit) {
    try {
      const data = await safeGet('/tasks/capabilities/' + capId);
      const cap = data.capability;
      if (!cap) {
        _showErr('能力不存在');
        return;
      }
      paramFormOpen(cap, onSubmit);
    } catch (e) {
      _showErr('加载能力详情失败: ' + e.message);
    }
  };

  // ════════════════════════════════════════════════════════════════════════
  // Schema 解析
  // ════════════════════════════════════════════════════════════════════════

  function _parseSchema (schemaStr) {
    if (!schemaStr || schemaStr === '{}' || schemaStr === '[]') return [];
    try {
      const schema = typeof schemaStr === 'string' ? JSON.parse(schemaStr) : schemaStr;
      return Array.isArray(schema) ? schema : [];
    } catch (e) {
      console.error('[paramForm] 解析 schema 失败:', e);
      return [];
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 渲染
  // ════════════════════════════════════════════════════════════════════════

  function _render (cap, onSubmit) {
    const container = document.getElementById('diagFormContainer');
    if (!container) {
      console.error('[paramForm] diagFormContainer 容器不存在');
      return;
    }

    const fieldsHtml = _currentSchema.map(field => _renderField(field)).join('');

    container.innerHTML = `
      <div class="diag-form-modal">
        <div class="diag-form-header">
          <h3>${_esc(cap.name)} - 配置参数</h3>
          <button class="btn-close" onclick="paramFormClose()">×</button>
        </div>
        <div class="diag-form-body">
          <p class="form-desc">${_esc(cap.description || '')}</p>
          <form id="paramFormForm" onsubmit="paramFormSubmit(event)">
            ${fieldsHtml}
            <div class="form-actions">
              <button type="button" class="btn btn-secondary" onclick="paramFormClose()">取消</button>
              <button type="submit" class="btn btn-primary">执行诊断</button>
            </div>
          </form>
        </div>
      </div>
    `;

    // 保存回调
    container._onSubmit = onSubmit;
  }

  function _renderField (field) {
    const name = field.name;
    const label = field.label || name;
    const required = field.required ? 'required' : '';
    const placeholder = field.description || field.placeholder || '';
    const defaultValue = field.default != null ? field.default : '';
    const requiredMark = field.required ? '<span class="required">*</span>' : '';
    const hint = field.description ? '<div class="form-hint">' + _esc(field.description) + '</div>' : '';

    let inputHtml = '';

    switch (field.type) {
      case 'select':
        inputHtml = _renderSelect(field, required, defaultValue);
        break;

      case 'textarea':
        inputHtml = '<textarea name="' + _esc(name) + '" class="form-input" placeholder="' + _esc(placeholder) + '" '
          + required + ' rows="' + (field.rows || 3) + '" '
          + (field.min_length ? 'minlength="' + field.min_length + '" ' : '')
          + (field.max_length ? 'maxlength="' + field.max_length + '" ')
          + '>' + _esc(String(defaultValue)) + '</textarea>';
        break;

      case 'number':
        inputHtml = '<input type="number" name="' + _esc(name) + '" class="form-input" '
          + 'placeholder="' + _esc(placeholder) + '" value="' + _esc(String(defaultValue)) + '" '
          + required + ' '
          + (field.min !== undefined ? 'min="' + field.min + '" ' : '')
          + (field.max !== undefined ? 'max="' + field.max + '" ' : '')
          + 'step="' + (field.step || 'any') + '" />';
        break;

      case 'boolean':
        inputHtml = '<label style="display:flex;align-items:center;gap:8px;cursor:pointer">'
          + '<input type="checkbox" name="' + _esc(name) + '" ' + (defaultValue === true || defaultValue === 'true' ? 'checked ' : '') + ' '
          + 'style="width:16px;height:16px" />'
          + '<span style="font-size:13px;color:var(--text-secondary)">' + _esc(label) + '</span>'
          + '</label>';
        break;

      case 'password':
        inputHtml = '<input type="password" name="' + _esc(name) + '" class="form-input" '
          + 'placeholder="' + _esc(placeholder) + '" value="' + _esc(String(defaultValue)) + '" '
          + required + ' />';
        break;

      default: // text
        inputHtml = '<input type="text" name="' + _esc(name) + '" class="form-input" '
          + 'placeholder="' + _esc(placeholder) + '" value="' + _esc(String(defaultValue)) + '" '
          + required + ' '
          + (field.pattern ? 'pattern="' + _esc(field.pattern) + '" ' : '')
          + (field.min_length ? 'minlength="' + field.min_length + '" ' : '')
          + (field.max_length ? 'maxlength="' + field.max_length + '" ')
          + '/>';
    }

    // boolean 类型不需要包裹 form-group
    if (field.type === 'boolean') {
      return '<div class="form-group" style="margin-bottom:12px">' + inputHtml + '</div>';
    }

    return `
      <div class="form-group">
        <label class="form-label">${_esc(label)} ${requiredMark}</label>
        ${inputHtml}
        ${hint}
      </div>
    `;
  }

  function _renderSelect (field, required, defaultValue) {
    const options = field.options || [];
    const optionsHtml = options.map(function (opt) {
      const value = typeof opt === 'object' ? opt.value : opt;
      const label = typeof opt === 'object' ? opt.label : value;
      const selected = String(value) === String(defaultValue) ? 'selected' : '';
      return '<option value="' + _esc(value) + '" ' + selected + '>' + _esc(label) + '</option>';
    }).join('');

    return '<select name="' + _esc(field.name) + '" class="form-input" ' + required + '>'
      + optionsHtml
      + '</select>';
  }

  // ════════════════════════════════════════════════════════════════════════
  // 提交 & 校验
  // ════════════════════════════════════════════════════════════════════════

  window.paramFormSubmit = function (event) {
    event.preventDefault();

    const form = document.getElementById('paramFormForm');
    if (!form) return;

    // 收集数据
    const formData = new FormData(form);
    const params = {};
    formData.forEach(function (value, key) {
      params[key] = value;
    });

    // 处理 checkbox（boolean）
    _currentSchema.forEach(function (field) {
      if (field.type === 'boolean') {
        const cb = form.querySelector('input[name="' + field.name + '"]');
        params[field.name] = cb ? cb.checked : false;
      }
    });

    // 前端校验
    var error = _validate(params);
    if (error) {
      _showErr(error);
      return;
    }

    // 获取回调并关闭
    var container = document.getElementById('diagFormContainer');
    var onSubmit = container && container._onSubmit;

    paramFormClose();

    if (typeof onSubmit === 'function') {
      onSubmit(params);
    }
  };

  function _validate (params) {
    if (!_currentSchema) return null;

    for (var i = 0; i < _currentSchema.length; i++) {
      var field = _currentSchema[i];
      var value = params[field.name];

      // 必填
      if (field.required && (value === undefined || value === null || String(value).trim() === '')) {
        return '请填写必填项: ' + (field.label || field.name);
      }

      if (value === undefined || value === null || String(value).trim() === '') continue;

      // 正则
      if (field.pattern) {
        try {
          var regex = new RegExp(field.pattern);
          if (!regex.test(String(value))) {
            return (field.label || field.name) + ' 格式不正确';
          }
        } catch (_) { /* ignore invalid regex */ }
      }

      // 长度
      if (field.min_length && String(value).length < field.min_length) {
        return (field.label || field.name) + ' 长度不能少于 ' + field.min_length + ' 个字符';
      }
      if (field.max_length && String(value).length > field.max_length) {
        return (field.label || field.name) + ' 长度不能超过 ' + field.max_length + ' 个字符';
      }

      // 数值范围
      if (field.type === 'number') {
        var numVal = parseFloat(value);
        if (field.min !== undefined && numVal < field.min) {
          return (field.label || field.name) + ' 不能小于 ' + field.min;
        }
        if (field.max !== undefined && numVal > field.max) {
          return (field.label || field.name) + ' 不能大于 ' + field.max;
        }
      }
    }

    return null;
  }

  // ════════════════════════════════════════════════════════════════════════
  // 模态框控制
  // ════════════════════════════════════════════════════════════════════════

  function _showModal () {
    var modal = document.getElementById('diagFormModal');
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  function _hideModal () {
    var modal = document.getElementById('diagFormModal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  // 工具
  // ════════════════════════════════════════════════════════════════════════

  function _esc (text) {
    if (text === null || text === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

  function _showErr (msg) {
    if (typeof dcShowError === 'function') { dcShowError(msg); return; }
    if (typeof toast === 'function') { toast(msg, 'error'); return; }
    if (typeof showErrorNotification === 'function') { showErrorNotification(msg); return; }
    alert(msg);
  }

})();
