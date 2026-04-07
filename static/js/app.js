/**
 * K8s Arthas Tool - 主入口
 * 
 * 模块化架构：
 * - core/          核心工具（API、认证、工具函数）
 * - components/    功能组件（连接、终端、监控、分析、文件、集群）
 * - app-ui.js      主 UI 逻辑（逐步迁移到 components/）
 * 
 * 使用方式：
 * 1. 先加载核心模块
 * 2. 再加载组件模块
 * 3. 最后加载 app-ui.js
 * 
 * 注意：初始化逻辑已在 app-ui.js 的 DOMContentLoaded 中处理
 * 此文件仅提供全局 App 命名空间接口
 */

// 服务器健康检查（供外部调用）
async function checkServerHealth() {
  try {
    const resp = await safeGet('/health');
    if (resp.status === 'ok') {
      console.log('服务器连接正常');
    }
  } catch (e) {
    console.warn('服务器连接异常:', e.message);
  }
}

// 全局 App 命名空间（供外部访问）
window.App = {
  // 核心
  API,
  safePost,
  safeGet,
  downloadFile,
  getCurrentUser,
  isAuthenticated,
  isAdmin,
  doLogout,
  initUserDisplay,
  
  // 工具
  esc,
  fmtSz,
  fmtTs,
  fmtNowTs,
  mkv,
  gRow,
  toast,
  getFileIcon,
  debounce,
  throttle,
  
  // 组件 - 连接
  getConnections,
  setConnections,
  getCurrentConnId,
  getCurrentConnection,
  renderConnList,
  switchConnection,
  deleteConnection,
  
  // 组件 - 集群
  getClusters,
  getCurrentCluster,
  getNamespaces,
  getPods,
  selCluster,
  loadPods,
  openAddCluster,
  closeModal,
  
  // 组件 - 性能分析
  pfSetMode,
  pfSetDur,
  
  // 组件 - 文件浏览器
  fbGetCurPath,
  fbNavTo,
  fbUp,
  
  // 组件 - 终端（函数已在 app-terminal.js 中定义）
  // termInit, termExec 等
};