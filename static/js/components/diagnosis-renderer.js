/**
 * 诊断结果渲染器
 * 
 * 根据能力类型自动选择渲染模式：
 * - table: 结构化表格（trace/watch）
 * - file_link: 文件下载链接（profiler）
 * - markdown: Markdown 渲染（AI 诊断）
 * - multi_step: 多步骤结果展示（场景方案）
 * - text: 原始文本（其他命令）
 */
(function() {
  'use strict';

  /**
   * 渲染诊断结果
   */
  window.renderDiagnosisResult = function(result, capability) {
    const renderMode = result.render_mode || detectRenderMode(result, capability);
    
    switch (renderMode) {
      case 'table':
        return renderTraceTable(result.structured_data || result);
      case 'file_link':
        return renderFileLinks(result.structured_data || result);
      case 'markdown':
        return renderMarkdown(result.raw_output || result.message || '');
      case 'multi_step':
        return renderMultiStep(result.steps || []);
      default:
        return renderText(result.raw_output || result.message || '');
    }
  };

  /**
   * 检测渲染模式
   */
  function detectRenderMode(result, capability) {
    if (!capability) return 'text';
    
    // 根据能力类型判断
    if (capability.type === 'ai_diagnosis') return 'markdown';
    if (capability.type === 'diagnosis_scenario') return 'multi_step';
    
    // 根据命令类型判断
    const command = result.command || capability.name || '';
    if (command.includes('trace') || command.includes('watch')) return 'table';
    if (command.includes('profiler') || command.includes('jfr')) return 'file_link';
    
    return 'text';
  }

  /**
   * 渲染 Trace 表格
   */
  function renderTraceTable(data) {
    if (!data || !Array.isArray(data)) {
      return `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    }

    const headers = Object.keys(data[0] || {});
    
    return `
      <div class="result-table-wrapper">
        <table class="result-table">
          <thead>
            <tr>
              ${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${data.map(row => `
              <tr>
                ${headers.map(h => `<td>${escapeHtml(String(row[h] || ''))}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  /**
   * 渲染文件下载链接
   */
  function renderFileLinks(data) {
    if (typeof data === 'string') {
      return `<a href="${escapeHtml(data)}" class="file-link" target="_blank">📄 下载诊断报告</a>`;
    }
    
    if (data.file_path) {
      return `
        <div class="file-links">
          <a href="/api/files/${encodeURIComponent(data.file_path)}" class="file-link" target="_blank">
            📄 ${escapeHtml(data.file_name || '诊断报告')}
          </a>
          ${data.file_size ? `<span class="file-size">${formatFileSize(data.file_size)}</span>` : ''}
        </div>
      `;
    }
    
    return `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  }

  /**
   * 渲染 Markdown（简化版）
   */
  function renderMarkdown(text) {
    // 简化 Markdown 渲染（后续可引入 marked.js）
    const html = text
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
    
    return `<div class="markdown-body">${html}</div>`;
  }

  /**
   * 渲染多步骤结果
   */
  function renderMultiStep(steps) {
    if (!Array.isArray(steps) || steps.length === 0) {
      return '<div class="sb-empty">暂无步骤结果</div>';
    }

    return `
      <div class="multi-step-results">
        ${steps.map((step, index) => `
          <div class="step-result-item">
            <div class="step-result-header">
              <span class="step-number">Step ${index + 1}/${steps.length}</span>
              <span class="step-status ${step.status || 'success'}">
                ${step.status === 'success' ? '✅' : step.status === 'failed' ? '❌' : '⏸️'}
              </span>
              <span class="step-name">${escapeHtml(step.name || step.command || '')}</span>
            </div>
            <div class="step-result-body">
              ${step.output ? `<pre>${escapeHtml(step.output)}</pre>` : ''}
              ${step.duration_ms ? `<div class="step-duration">耗时: ${(step.duration_ms / 1000).toFixed(2)}s</div>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  /**
   * 渲染纯文本
   */
  function renderText(text) {
    return `<pre class="result-text">${escapeHtml(text)}</pre>`;
  }

  /**
   * 格式化文件大小
   */
  function formatFileSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  }

  /**
   * HTML 转义
   */
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

})();
