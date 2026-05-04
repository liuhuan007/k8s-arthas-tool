/**
 * External Links Menu - 外部链接菜单管理
 * 
 * 功能:
 * - 从 external_links.json 加载配置
 * - 动态渲染到侧边栏"扩展能力"菜单组
 * - 支持分类、权限控制、启用/禁用
 */

(function() {
  'use strict';
  
  const API = window.API || '/api';
  let externalLinks = [];
  let categories = {};
  
  /**
   * 加载外部链接配置
   */
  async function loadExternalLinks() {
    try {
      const res = await fetch('/external_links.json', {
        cache: 'no-cache'
      });
      
      if (!res.ok) {
        console.warn('[ExternalLinks] Failed to load config:', res.status);
        return;
      }
      
      const data = await res.json();
      externalLinks = data.links || [];
      categories = data.categories || {};
      
      console.log('[ExternalLinks] Loaded', externalLinks.length, 'links');
      
      // 渲染到侧边栏
      renderExternalLinks();
      
    } catch (e) {
      console.error('[ExternalLinks] Load error:', e);
    }
  }
  
  /**
   * 渲染外部链接到侧边栏
   */
  function renderExternalLinks() {
    // ✅ 修改: 渲染到新的外部系统菜单组
    const externalGroup = document.querySelector('[data-side-group="external"]');
    if (!externalGroup) {
      console.warn('[ExternalLinks] External group not found');
      return;
    }
    
    const itemsContainer = externalGroup.querySelector('.side-nav-items');
    if (!itemsContainer) return;
    
    // 按分类分组
    const grouped = {};
    externalLinks
      .filter(link => link.enabled)
      .forEach(link => {
        const cat = link.category || 'other';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(link);
      });
    
    // 按分类顺序排序
    const sortedCats = Object.keys(grouped).sort((a, b) => {
      const orderA = categories[a]?.order || 999;
      const orderB = categories[b]?.order || 999;
      return orderA - orderB;
    });
    
    // 构建 HTML
    let html = '';
    
    // 外部链接
    sortedCats.forEach(catKey => {
      const cat = categories[catKey] || { name: catKey, icon: '🔗' };
      const links = grouped[catKey];
      
      html += `
        <div class="side-nav-subtitle">
          <span>${cat.icon} ${cat.name}</span>
        </div>
      `;
      
      links.forEach(link => {
        html += `
          <button class="side-nav-item external-link" 
                  data-link-id="${link.id}"
                  onclick="openExternalLink('${link.url}', '${link.id}', '${link.name}')"
                  title="${link.description || ''}">
            <span>${link.icon}</span><span>${link.name}</span>
          </button>
        `;
      });
    });
    
    if (html === '') {
      html = '<div class="sb-empty">暂无外部系统</div>';
    }
    
    itemsContainer.innerHTML = html;
  }
  
  /**
   * 打开外部链接
   */
  window.openExternalLink = function(url, linkId, name) {
    console.log('[ExternalLinks] Opening:', linkId, url);
    
    // 记录访问日志 (可选)
    logLinkAccess(linkId);
    
    // ✅ 在 iframe 中嵌入打开
    openExternalSystem(url, name || linkId);
  };
  
  /**
   * 打开外部系统 (iframe 嵌入)
   */
  function openExternalSystem(url, title) {
    const panel = document.getElementById('panel-external-system');
    const iframe = document.getElementById('externalSystemIframe');
    const loading = document.getElementById('externalSystemLoading');
    const error = document.getElementById('externalSystemError');
    const titleEl = document.getElementById('externalSystemTitle');
    
    if (!panel || !iframe) {
      console.error('[ExternalLinks] Panel not found');
      return;
    }
    
    // ✅ 跨域检测: 如果是跨域地址,先尝试在新标签页打开
    const isCrossOrigin = isCrossOriginUrl(url);
    
    if (isCrossOrigin) {
      console.warn('[ExternalLinks] 跨域地址,直接在新标签页打开:', url);
      window.open(url, '_blank');
      return;
    }
    
    // 切换到外部系统面板
    switchTab('external-system');
    
    // 更新标题
    titleEl.textContent = title;
    
    // 显示加载状态
    loading.style.display = 'flex';
    error.style.display = 'none';
    iframe.style.display = 'none';
    
    // 设置 iframe src
    iframe.src = url;
    
    // 监听加载完成
    iframe.onload = function() {
      loading.style.display = 'none';
      iframe.style.display = 'block';
      console.log('[ExternalLinks] Loaded:', url);
    };
    
    // 监听 iframe 错误 (跨域限制)
    iframe.onerror = function() {
      loading.style.display = 'none';
      error.style.display = 'flex';
      console.error('[ExternalLinks] iframe 加载失败:', url);
    };
    
    // ✅ 增强: 监听加载错误 (3秒后如果还在加载,可能是被阻止)
    setTimeout(() => {
      if (loading.style.display !== 'none') {
        // 可能是不允许 iframe 嵌入
        loading.style.display = 'none';
        error.style.display = 'flex';
        console.warn('[ExternalLinks] 可能不允许 iframe 嵌入:', url);
      }
    }, 3000);
  }
  
  /**
   * 检测是否为跨域 URL
   */
  function isCrossOriginUrl(url) {
    try {
      const urlObj = new URL(url);
      const currentOrigin = window.location.origin;
      return urlObj.origin !== currentOrigin;
    } catch (e) {
      // 如果 URL 解析失败,默认认为跨域
      return true;
    }
  }
  
  /**
   * 关闭外部系统面板
   */
  window.closeExternalSystem = function() {
    const iframe = document.getElementById('externalSystemIframe');
    if (iframe) {
      iframe.src = '';
    }
    
    // 切换回连接中心
    switchTab('connections');
  };
  
  /**
   * 刷新外部系统
   */
  window.reloadExternalSystem = function() {
    const iframe = document.getElementById('externalSystemIframe');
    if (iframe && iframe.src) {
      iframe.src = iframe.src;
    }
  };
  
  /**
   * 在新标签页打开外部系统
   */
  window.openExternalInNewTab = function() {
    const iframe = document.getElementById('externalSystemIframe');
    if (iframe && iframe.src) {
      window.open(iframe.src, '_blank');
    }
  };
  
  /**
   * 记录链接访问 (可选,发送到后端)
   */
  async function logLinkAccess(linkId) {
    try {
      await fetch(`${API}/audit/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          action: 'external_link_access',
          target: linkId,
          details: `访问外部链接: ${linkId}`
        })
      });
    } catch (e) {
      // 忽略审计日志失败
    }
  }
  
  /**
   * 刷新外部链接配置 (管理员功能)
   */
  window.refreshExternalLinks = async function() {
    await loadExternalLinks();
    console.log('[ExternalLinks] Refreshed');
  };
  
  // DOM Ready 时加载
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadExternalLinks);
  } else {
    loadExternalLinks();
  }
  
})();
