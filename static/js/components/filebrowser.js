/**
 * 文件浏览器组件
 * 处理 Pod 内文件浏览、目录导航、文件操作
 */

// ── State ─────────────────────────────────────────────────────────────────
// _fbSelected, _fbCurPath, _fbFiles 在 app-ui.js 中声明，使用 window 访问

// 获取当前路径
function fbGetCurPath() {
  return window._fbCurPath || '/tmp';
}

// 设置当前路径
function fbSetCurPath(path) {
  window._fbCurPath = path;
}

// 获取文件列表
function fbGetFiles() {
  return window._fbFiles || [];
}

// 选中文件/目录
function fbSelectEl(el) {
  if (window._fbSelected) {
    window._fbSelected.classList.remove('selected');
  }
  window._fbSelected = el;
  el.classList.add('selected');
}

// 选中并执行操作
function fbDblClickEl(el) {
  const isDir = el.dataset.isDir === 'true';
  const path = el.dataset.path;
  
  if (isDir) {
    fbNavTo(path);
  } else {
    downloadPodFile(path);
  }
}

// 导航到指定路径
async function fbNavTo(path) {
  const conn = getCurrentConnection();
  if (!conn) {
    toast('请先选择连接', 'error');
    return;
  }
  
  try {
    const resp = await safePost('/api/pod/files', {
      cluster_name: conn.cluster,
      namespace: conn.namespace,
      pod_name: conn.pod,
      container: conn.container || '',
      path: path
    });
    
    window._fbCurPath = path;
    window._fbFiles = resp.files || [];
    renderFileBrowser(resp.files || [], path);
  } catch (e) {
    toast('加载目录失败: ' + e.message, 'error');
  }
}

// 相对路径导航
function fbNav(relative) {
  if (relative === '..') {
    const parts = (window._fbCurPath || '/tmp').split('/');
    parts.pop();
    fbNavTo(parts.join('/') || '/');
  } else {
    fbNavTo((window._fbCurPath || '/tmp') + '/' + relative);
  }
}

// 上一级目录
function fbUp() {
  fbNav('..');
}

// 渲染文件浏览器
function renderFileBrowser(files, curPath) {
  const el = document.getElementById('fbFileList');
  if (!el) return;
  
  if (!files || files.length === 0) {
    el.innerHTML = '<div class="empty-state">目录为空</div>';
    return;
  }
  
  el.innerHTML = files.map(f => `
    <div class="fb-item ${f.is_dir ? 'dir' : 'file'}" 
         data-path="${esc(f.path)}" 
         data-is-dir="${f.is_dir}"
         ondblclick="fbDblClickEl(this)">
      <span class="fb-icon">${f.is_dir ? '📁' : getFileIcon(f.name)}</span>
      <span class="fb-name">${esc(f.name)}</span>
      <span class="fb-size">${f.is_dir ? '' : fmtSz(f.size)}</span>
      <span class="fb-time">${fmtTs(f.modified)}</span>
    </div>`).join('');
  
  // 更新当前路径显示
  const pathEl = document.getElementById('fbCurPath');
  if (pathEl) pathEl.textContent = curPath;
}

// 下载文件
async function downloadPodFile(filePath) {
  const conn = getCurrentConnection();
  if (!conn) return;
  
  const filename = filePath.split('/').pop();
  
  try {
    // 使用 POST 接口下载
    const resp = await safePost('/api/pod/files/download', {
      cluster_name: conn.cluster,
      namespace: conn.namespace,
      pod_name: conn.pod,
      container: conn.container || '',
      path: filePath
    });
    
    // 如果返回的是文件内容，创建下载
    if (resp instanceof Blob) {
      const url = URL.createObjectURL(resp);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }
    toast('文件下载成功', 'success');
  } catch (e) {
    toast('下载失败: ' + e.message, 'error');
  }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    fbGetCurPath,
    fbSetCurPath,
    fbGetFiles,
    fbSelectEl,
    fbDblClickEl,
    fbNavTo,
    fbNav,
    fbUp,
    renderFileBrowser,
    downloadPodFile
  };
}