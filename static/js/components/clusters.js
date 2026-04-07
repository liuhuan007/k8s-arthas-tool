/**
 * 集群管理组件
 * 处理集群列表、命名空间/Pod 选择、集群配置
 * 注意：UI 交互函数（openAddCluster/saveCluster 等）在 app-ui.js 中定义
 * 此文件只保留纯数据操作的 getter/setter 函数
 */

// ── State ─────────────────────────────────────────────────────────────────
// 注意：状态变量 _clusters/_ac/_namespaces/_pods 在 app-ui.js 中定义
// 此处只提供数据访问接口

// 获取集群列表（代理到 app-ui.js 的全局变量）
function getClusters() {
  return window._clusters || [];
}

// 设置集群列表（代理到 app-ui.js 的全局变量）
function setClusters(clusters) {
  window._clusters = clusters || [];
}

// 获取当前集群名称
function getCurrentCluster() {
  try { return localStorage.getItem('arthas_ac') || null; } catch { return null; }
}

// 设置当前集群名称
function setCurrentCluster(cluster) {
  try { localStorage.setItem('arthas_ac', cluster); } catch {}
}

// 获取命名空间列表（从缓存）
function getNamespaces() {
  const ac = getCurrentCluster();
  if (!ac) return [];
  try {
    const cached = window._clusterNs && window._clusterNs[ac];
    return cached || [];
  } catch { return []; }
}

// 获取 Pod 列表（需要调用 API）
function getPods() {
  // Pod 列表需要通过 loadPods 加载，暂时返回空
  return window._podsList || [];
}

// ── 导出 ─────────────────────────────────────────────────────────────────
// 暴露到 window 全局（供 app.js 和 HTML onclick 使用）
window.getClusters = getClusters;
window.setClusters = setClusters;
window.getCurrentCluster = getCurrentCluster;
window.setCurrentCluster = setCurrentCluster;
window.getNamespaces = getNamespaces;
window.getPods = getPods;

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    getClusters,
    setClusters,
    getCurrentCluster,
    setCurrentCluster,
    getNamespaces,
    getPods
  };
}