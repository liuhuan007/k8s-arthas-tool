/**
 * 诊断能力参数表单组件 - 动态生成表单
 * 
 * 功能：
 * 1. 根据 parameters_schema 动态渲染表单字段
 * 2. 支持 text/number/select/textarea 等字段类型
 * 3. 表单校验（必填、正则、范围等）
 * 4. 提交执行诊断
 */
(function() {
  'use strict';

  let _currentCapability = null;

  /**
   * 显示能力参数表单
   */
  window.diagShowParameterForm = async function(capId) {
    // 获取能力详情
    try {
      const data = await safeGet(`/tasks/capabilities/${capId}`);
      _currentCapability = data.capability;

      if (!_currentCapability) {
        showError('能力不存在');
        return;
      }

      renderForm(_currentCapability);
      showFormModal();
    } catch (e) {
      showError('加载能力详情失败: ' + e.message);
    }
  };

  /**
   * 渲染表单
   */
  function renderForm(cap) {
    const schema = parseSchema(cap.parameters_schema);
    const formContainer = document.getElementById('diagFormContainer');
    if (!formContainer) {
      console.error('diagFormContainer 容器不存在');
      return;
    }

    formContainer.innerHTML = `
      <div class="diag-form-modal">
        <div class="diag-form-header">
          <h3>${escapeHtml(cap.name)} - 配置参数</h3>
          <button class="btn-close" onclick="window.diagCloseForm()">×</button>
        </div>
        
        <div class="diag-form-body">
          <p class="form-desc">${escapeHtml(cap.description || '')}</p>
          
          <form id="diagCapForm" onsubmit="window.diagSubmitForm(event, ${cap.id})">
            ${schema.map(field => renderFormField(field)).join('')}
            
            <div class="form-actions">
              <button type="button" class="btn btn-secondary" onclick="window.diagCloseForm()">取消</button>
              <button type="submit" class="btn btn-primary">执行诊断</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  /**
   * 解析参数 schema
   */
  function parseSchema(schemaStr) {
    if (!schemaStr || schemaStr === '{}' || schemaStr === '[]') return [];
    
    try {
      const schema = typeof schemaStr === 'string' ? JSON.parse(schemaStr) : schemaStr;
      return Array.isArray(schema) ? schema : [];
    } catch (e) {
      console.error('解析 parameters_schema 失败:', e);
      return [];
    }
  }

  /**
   * 渲染单个表单字段
   */
  function renderFormField(field) {
    const name = field.name;
    const label = field.label || name;
    const required = field.required ? 'required' : '';
    const placeholder = field.description || '';
    const defaultValue = field.default || '';

    let inputHtml = '';

    switch (field.type) {
      case 'select':
        inputHtml = renderSelectField(field, required, defaultValue);
        break;
      case 'textarea':
        inputHtml = `<textarea 
          name="${name}" 
          class="form-input"
          placeholder="${placeholder}"
          ${required}
          ${field.min_length ? `minlength="${field.min_length}"` : ''}
          ${field.max_length ? `maxlength="${field.max_length}"` : ''}
        >${defaultValue}</textarea>`;
        break;
      case 'number':
        inputHtml = `<input 
          type="number" 
          name="${name}" 
          class="form-input"
          placeholder="${placeholder}"
          value="${defaultValue}"
          ${required}
          ${field.min !== undefined ? `min="${field.min}"` : ''}
          ${field.max !== undefined ? `max="${field.max}"` : ''}
          step="${field.step || 'any'}"
        />`;
        break;
      default: // text
        inputHtml = `<input 
          type="text" 
          name="${name}" 
          class="form-input"
          placeholder="${placeholder}"
          value="${defaultValue}"
          ${required}
          ${field.pattern ? `pattern="${field.pattern}"` : ''}
          ${field.min_length ? `minlength="${field.min_length}"` : ''}
          ${field.max_length ? `maxlength="${field.max_length}"` : ''}
        />`;
    }

    return `
      <div class="form-group">
        <label class="form-label">
          ${escapeHtml(label)}
          ${required ? '<span class="required">*</span>' : ''}
        </label>
        ${inputHtml}
        ${field.description ? `<div class="form-hint">${escapeHtml(field.description)}</div>` : ''}
      </div>
    `;
  }

  /**
   * 渲染下拉选择字段
   */
  function renderSelectField(field, required, defaultValue) {
    const options = field.options || [];
    const optionsHtml = options.map(opt => {
      const value = typeof opt === 'object' ? opt.value : opt;
      const label = typeof opt === 'object' ? opt.label : value;
      const selected = value === defaultValue ? 'selected' : '';
      return `<option value="${value}" ${selected}>${label}</option>`;
    }).join('');

    return `
      <select name="${field.name}" class="form-input" ${required}>
        ${optionsHtml}
      </select>
    `;
  }

  /**
   * 显示表单模态框
   */
  function showFormModal() {
    const modal = document.getElementById('diagFormModal');
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  /**
   * 关闭表单
   */
  window.diagCloseForm = function() {
    const modal = document.getElementById('diagFormModal');
    if (modal) {
      modal.style.display = 'none';
    }
    _currentCapability = null;
  };

  /**
   * 提交表单
   */
  window.diagSubmitForm = async function(event, capId) {
    event.preventDefault();

    const form = document.getElementById('diagCapForm');
    if (!form) return;

    // 收集表单数据
    const formData = new FormData(form);
    const params = {};
    
    for (let [key, value] of formData.entries()) {
      params[key] = value;
    }

    // 前端校验
    const validationError = validateForm(params, _currentCapability);
    if (validationError) {
      showError(validationError);
      return;
    }

    // 关闭表单
    window.diagCloseForm();

    // 执行诊断
    if (window.diagExecuteCapWithParams) {
      await window.diagExecuteCapWithParams(capId, params);
    }
  };

  /**
   * 表单校验
   */
  function validateForm(params, cap) {
    const schema = parseSchema(cap.parameters_schema);
    
    for (const field of schema) {
      const value = params[field.name];

      // 必填项检查
      if (field.required && (!value || value.trim() === '')) {
        return `请填写必填项: ${field.label || field.name}`;
      }

      // 正则校验
      if (value && field.pattern) {
        const regex = new RegExp(field.pattern);
        if (!regex.test(value)) {
          return `${field.label || field.name} 格式不正确`;
        }
      }

      // 长度校验
      if (value) {
        if (field.min_length && value.length < field.min_length) {
          return `${field.label || field.name} 长度不能少于 ${field.min_length} 个字符`;
        }
        if (field.max_length && value.length > field.max_length) {
          return `${field.label || field.name} 长度不能超过 ${field.max_length} 个字符`;
        }
      }

      // 数值范围校验
      if (field.type === 'number' && value) {
        const numValue = parseFloat(value);
        if (field.min !== undefined && numValue < field.min) {
          return `${field.label || field.name} 不能小于 ${field.min}`;
        }
        if (field.max !== undefined && numValue > field.max) {
          return `${field.label || field.name} 不能大于 ${field.max}`;
        }
      }
    }

    return null;
  }

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * 显示错误
   */
  function showError(msg) {
    if (window.showErrorNotification) {
      window.showErrorNotification(msg);
    } else {
      alert(msg);
    }
  }

})();
