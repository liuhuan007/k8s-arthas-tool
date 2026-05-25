/**
 * diagnosis-report.js — 诊断报告展示组件
 *
 * 功能：
 * 1. 展示诊断执行结果（单步/多步骤/文件链接/AI 报告）
 * 2. 支持结果格式化（表格、Markdown、纯文本）
 * 3. 支持结果下载为文件
 * 4. 支持结果复制到剪贴板
 */
(function () {
  'use strict';

  // ════════════════════════════════════════════════════════════════════════
  // 公开 API
  // ════════════════════════════════════════════════════════════════════════

  /**
   * 展示诊断报告
   * @param {object} result - 执行结果对象
   * @param {object} [capability] - 能力元数据（可选）
   * @param {HTMLElement} [container] - 目标容器（默认 dcResultContainer）
   */
  window.diagReportShow = function (result, capability, container) {
    container = container || document.getElementById('dcResultContainer');
    if (!container) {
      console.warn('[diagReport] 目标容器不存在');
      return;
    }

    container.classList.add('visible');
    container.innerHTML = _renderReport(result, capability);

    // 滚动到结果区域
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  /**
   * 清除报告
   */
  window.diagReportClear = function (container) {
    container = container || document.getElementById('dcResultContainer');
    if (container) {
      container.classList.remove('visible');
      container.innerHTML = '';
    }
  };

  /**
   * 下载报告为文本文件
   */
  window.diagReportDownload = function (filename) {
    var container = document.getElementById('dcResultContainer');
    if (!container || !container.textContent.trim()) {
      if (typeof dcShowError === 'function') dcShowError('无可下载的内容');
      return;
    }

    var text = container.innerText;
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename || ('diagnosis-report-' + Date.now() + '.txt');
    a.click();
    URL.revokeObjectURL(url);
  };

  /**
   * 复制报告到剪贴板
   */
  window.diagReportCopy = function () {
    var container = document.getElementById('dcResultContainer');
    if (!container || !container.textContent.trim()) {
      if (typeof dcShowError === 'function') dcShowError('无内容可复制');
      return;
    }

    var text = container.innerText;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(function () {
        if (typeof dcShowSuccess === 'function') dcShowSuccess('已复制到剪贴板');
      });
    } else {
      // 降级
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      if (typeof dcShowSuccess === 'function') dcShowSuccess('已复制到剪贴板');
    }
  };

  // ════════════════════════════════════════════════════════════════════════
  // 渲染引擎
  // ════════════════════════════════════════════════════════════════════════

  function _renderReport (result, capability) {
    if (!result) {
      return '<div class="empty-state">无诊断结果</div>';
    }

    // 检测渲染模式
    var renderMode = result.render_mode || _detectMode(result, capability);

    var headerHtml = _renderHeader(result, capability);
    var bodyHtml = '';

    switch (renderMode) {
      case 'table':
        bodyHtml = _renderTable(result.structured_data || result);
        break;
      case 'file_link':
        bodyHtml = _renderFileLink(result.structured_data || result);
        break;
      case 'markdown':
        bodyHtml = _renderMarkdown(result.raw_output || result.message || '');
        break;
      case 'multi_step':
        bodyHtml = _renderMultiStep(result.steps || []);
        break;
      case 'scenario':
        bodyHtml = _renderScenarioResult(result, capability);
        break;
      default:
        bodyHtml = _renderText(result.raw_output || result.message || result);
    }

    var actionsHtml = '<div class="result-actions">'
      + '<button class="btn btn-secondary" onclick="diagReportDownload()">📄 下载报告</button>'
      + '<button class="btn btn-secondary" onclick="diagReportCopy()">📋 复制</button>'
      + '<button class="btn btn-primary" onclick="diagReportClear()">关闭</button>'
      + '</div>';

    return '<div class="diag-result">'
      + headerHtml
      + '<div class="report-body">' + bodyHtml + '</div>'
      + actionsHtml
      + '</div>';
  }

  function _renderHeader (result, capability) {
    var status = result.status || 'unknown';
    var statusText = _getStatusText(status);
    var statusClass = 'status-' + status;
    var duration = result.duration_ms ? (result.duration_ms / 1000).toFixed(2) + 's' : '-';

    var progressInfo = '';
    if (result.completed_steps !== undefined && result.total_steps !== undefined) {
      progressInfo = '<span class="meta-item">进度: ' + result.completed_steps + '/' + result.total_steps + '</span>';
    }

    return '<div class="result-header">'
      + '<h3>' + _esc(capability ? capability.name : '诊断报告') + '</h3>'
      + '<div class="result-meta">'
      + '<span class="meta-item ' + statusClass + '">' + statusText + '</span>'
      + progressInfo
      + '<span class="meta-item">耗时: ' + duration + '</span>'
      + '</div>'
      + '</div>';
  }

  function _renderTable (data) {
    if (!data) return '<div class="empty-state">无结构化数据</div>';

    // 如果是数组
    if (Array.isArray(data)) {
      if (data.length === 0) return '<div class="empty-state">数据为空</div>';

      var headers = Object.keys(data[0]);
      var rows = data.map(function (row) {
        return '<tr>' + headers.map(function (h) {
          return '<td>' + _esc(String(row[h] != null ? row[h] : '')) + '</td>';
        }).join('') + '</tr>';
      }).join('');

      return '<div class="result-table-wrapper">'
        + '<table class="result-table">'
        + '<thead><tr>' + headers.map(function (h) { return '<th>' + _esc(h) + '</th>'; }).join('') + '</tr></thead>'
        + '<tbody>' + rows + '</tbody>'
        + '</table></div>';
    }

    // 对象转键值对
    return '<div style="padding:12px">' + _renderKvPairs(data) + '</div>';
  }

  function _renderFileLink (data) {
    if (typeof data === 'string') {
      return '<div class="file-links"><a href="' + _esc(data) + '" class="file-link" target="_blank">📄 下载诊断报告</a></div>';
    }

    if (data && data.file_path) {
      return '<div class="file-links">'
        + '<a href="/api/files/' + encodeURIComponent(data.file_path) + '" class="file-link" target="_blank">'
        + '📄 ' + _esc(data.file_name || '诊断报告')
        + '</a>'
        + (data.file_size ? '<span class="file-size">' + _formatSize(data.file_size) + '</span>' : '')
        + '</div>';
    }

    return '<pre class="result-text">' + _esc(JSON.stringify(data, null, 2)) + '</pre>';
  }

  function _renderMarkdown (text) {
    if (!text) return '<div class="empty-state">无内容</div>';

    var html = _esc(text);
    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="result-output">$2</pre>');
    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code style="background:var(--bg2);padding:1px 4px;border-radius:3px;font-size:12px">$1</code>');
    // 标题
    html = html.replace(/^### (.+)$/gm, '<h4 style="font-size:14px;font-weight:600;color:var(--tx);margin:12px 0 6px">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 style="font-size:15px;font-weight:600;color:var(--tx);margin:14px 0 8px">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 style="font-size:16px;font-weight:600;color:var(--tx);margin:16px 0 8px">$1</h2>');
    // 粗体
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // 列表
    html = html.replace(/^- (.+)$/gm, '<div style="display:flex;gap:6px;margin:2px 0"><span style="color:var(--a)">•</span><span>$1</span></div>');
    html = html.replace(/^\d+\. (.+)$/gm, '<div style="display:flex;gap:6px;margin:2px 0"><span style="color:var(--a)">$&</span></div>');
    // 段落
    html = html.replace(/\n\n/g, '</p><p style="margin:8px 0">');
    html = '<div style="line-height:1.6"><p style="margin:8px 0">' + html + '</p></div>';

    return html;
  }

  function _renderMultiStep (steps) {
    if (!Array.isArray(steps) || steps.length === 0) {
      return '<div class="empty-state">暂无步骤结果</div>';
    }

    return '<div class="multi-step-results">'
      + steps.map(function (step, index) {
        var stepStatus = step.success !== false ? 'success' : 'failed';
        var icon = step.success !== false ? '✅' : '❌';
        return '<div class="step-result-item">'
          + '<div class="step-result-header">'
          + '<span class="step-number">Step ' + (index + 1) + '/' + steps.length + '</span>'
          + '<span class="step-status">' + icon + '</span>'
          + '<span class="step-name">' + _esc(step.name || step.command || '') + '</span>'
          + '</div>'
          + '<div class="step-result-body">'
          + (step.output ? '<pre>' + _esc(step.output) + '</pre>' : '')
          + (step.duration_ms ? '<div class="step-duration">耗时: ' + (step.duration_ms / 1000).toFixed(2) + 's</div>' : '')
          + '</div>'
          + '</div>';
      }).join('')
      + '</div>';
  }

  function _renderScenarioResult (result, capability) {
    var status = result.status || 'unknown';
    var statusText = _getStatusText(status);
    var duration = result.duration_ms ? (result.duration_ms / 1000).toFixed(2) + 's' : '-';
    var steps = result.steps || [];

    var headerHtml = '<div class="result-header">'
      + '<h3>' + _esc(capability ? capability.name : '场景方案结果') + '</h3>'
      + '<div class="result-meta">'
      + '<span class="meta-item status-' + status + '">' + statusText + '</span>'
      + '<span class="meta-item">进度: ' + (result.completed_steps || 0) + '/' + (result.total_steps || steps.length) + '</span>'
      + '<span class="meta-item">耗时: ' + duration + '</span>'
      + '</div></div>';

    var stepsHtml = steps.map(function (step) {
      var s = step.success !== false ? 'success' : 'failed';
      return '<div class="step-item step-' + s + '">'
        + '<div class="step-header">'
        + '<span class="step-icon ' + s + '">' + (s === 'success' ? '✓' : '✗') + '</span>'
        + '<span class="step-title">步骤 ' + (step.step_order || '?') + ': ' + _esc(step.desc || '') + '</span>'
        + '</div>'
        + (step.result ? '<div class="step-output">'
          + (step.result.message ? '<div class="result-message">' + _esc(step.result.message) + '</div>' : '')
          + (step.result.body ? '<pre class="result-output">' + _esc(typeof step.result.body === 'string' ? step.result.body : JSON.stringify(step.result.body, null, 2)) + '</pre>' : '')
          + '</div>' : '')
        + '</div>';
    }).join('');

    return '<div class="diag-result scenario-result">'
      + headerHtml
      + '<div class="steps-container">' + stepsHtml + '</div>'
      + '</div>';
  }

  function _renderText (data) {
    if (!data && data !== 0) return '<div class="empty-state">无输出</div>';

    var text = typeof data === 'object' ? JSON.stringify(data, null, 2) : String(data);
    return '<pre class="result-text">' + _esc(text) + '</pre>';
  }

  function _renderKvPairs (obj) {
    return Object.keys(obj).map(function (k) {
      var v = obj[k];
      var vs = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v != null ? v : '—');
      return '<div style="display:flex;gap:8px;margin:4px 0;font-size:12px">'
        + '<span style="color:var(--tx3);min-width:120px">' + _esc(k) + '</span>'
        + '<span style="color:var(--tx);word-break:break-all">' + _esc(vs) + '</span>'
        + '</div>';
    }).join('');
  }

  // ════════════════════════════════════════════════════════════════════════
  // 工具
  // ════════════════════════════════════════════════════════════════════════

  function _detectMode (result, capability) {
    if (!capability) return 'text';
    if (capability.type === 'ai_diagnosis') return 'markdown';
    if (capability.type === 'diagnosis_scenario') return 'scenario';
    if (result.steps && Array.isArray(result.steps)) return 'scenario';
    var cmd = (result.command || capability.name || '').toLowerCase();
    if (cmd.indexOf('trace') >= 0 || cmd.indexOf('watch') >= 0) return 'table';
    if (cmd.indexOf('profiler') >= 0 || cmd.indexOf('jfr') >= 0) return 'file_link';
    return 'text';
  }

  function _getStatusText (status) {
    var map = {
      success: '成功', completed: '成功', failed: '失败', partial: '部分成功',
      running: '执行中', cancelled: '已取消', pending: '等待中', unknown: '未知'
    };
    return map[status] || status || '未知';
  }

  function _formatSize (bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB';
    return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
  }

  function _esc (text) {
    if (text === null || text === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
  }

})();
