/**
 * Core 模块入口
 * 统一导出所有核心工具
 */

// 加载顺序：api.js -> auth.js -> utils.js
// 由于浏览器直接加载，这些已作为全局变量注入

// 如果在模块系统下，导出所有
if (typeof module !== 'undefined' && module.exports) {
  // 已在各模块中导出
}