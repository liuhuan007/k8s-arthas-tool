/**
 * 连接信息提示条 (ConnStatusBar)
 *
 * 紧贴 Tab 栏下方，统一展示当前连接状态：
 * - 连接类型（Pod连接 / Arthas连接 / 未连接）
 * - 目标 Pod 信息（集群 / 命名空间 / Pod名）
 * - 运行时信息（Java版本、PID 等）
 * - 快捷操作按钮（连接 / 启动Arthas / 断开）
 *
 * 数据来源：window._connState / window._connections / window._currentConnId / window._runtimeInfo
 * 更新时机：连接状态变化时调用 csbRefresh()
 */

const ConnStatusBar = (function () {
  'use strict';

  // ── 层级配置 ──────────────────────────────────────────────────────────
  const LEVEL_CONFIG = {
    none:    { label: '未连接',     dot: 'dim',    bg: 'dim',    icon: '🔌' },
    pod:     { label: 'Pod连接',    dot: 'pod',    bg: 'pod',    icon: '🔵' },
    arthas:  { label: 'Arthas连接', dot: 'arthas', bg: 'arthas', icon: '⚡' },
  };

  // ── DOM 缓存 ──────────────────────────────────────────────────────────
  let _bar, _dot, _level, _target, _runtime, _action;

  function _cacheDom() {
    _bar     = document.getElementById('connStatusBar');
    _dot     = document.getElementById('csbDot');
    _level   = document.getElementById('csbLevel');
    _target  = document.getElementById('csbTarget');
    _runtime = document.getElementById('csbRuntime');
    _action  = document.getElementById('csbAction');
  }

  // ── 获取当前连接数据 ──────────────────────────────────────────────────
  function _getCurrentConn() {
    const connId = window._currentConnId;
    if (!connId) return null;
    return (window._connections || []).find(c => c.id === connId) || null;
  }

  function _getLevel() {
    if (window.ConnectionGuard) return ConnectionGuard.getCurrentLevel();
    const cs = window._connState;
    if (cs === 'arthas_ready') return 'arthas';
    if (cs === 'pod_connected') return 'pod';
    return 'none';
  }

  function _getRuntimeInfo() {
    // 优先从 window._runtimeInfo 取
    const ri = window._runtimeInfo;
    if (ri) {
      return {
        type: ri.type || ri.runtime_type || '',
        version: ri.version || ri.runtime_version || '',
        java_pid: ri.java_pid || '',
      };
    }
    // 从连接数据取
    const conn = _getCurrentConn();
    if (conn) {
      const rt = (typeof getConnRuntime === 'function') ? getConnRuntime(conn) : null;
      if (rt) return { type: rt.type, version: rt.version, java_pid: conn.java_pid || '' };
      if (conn.runtime_type) return { type: conn.runtime_type, version: conn.runtime_version || '', java_pid: conn.java_pid || '' };
    }
    return null;
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────
  function refresh() {
    if (!_bar) _cacheDom();
    if (!_bar) return;

    const level = _getLevel();
    const conn  = _getCurrentConn();
    const rt    = _getRuntimeInfo();
    const cfg   = LEVEL_CONFIG[level] || LEVEL_CONFIG.none;

    // ── 左侧：连接状态圆点 + 层级 + 目标 ──
    _dot.className = 'csb-dot ' + cfg.dot;

    _level.textContent = cfg.label;
    _level.className = 'csb-level ' + cfg.bg;

    if (conn) {
      const cluster = conn.cluster || conn.cluster_name || '';
      const ns      = conn.namespace || '';
      const pod     = conn.pod_name || conn.pod || '';
      _target.textContent = `${cluster} › ${ns}/${pod}`;
      _target.title = `集群: ${cluster}\n命名空间: ${ns}\nPod: ${pod}`;
    } else {
      _target.textContent = '— 选择集群和 Pod 后连接';
      _target.title = '';
    }

    // ── 右侧：运行时 + 操作按钮 ──
    if (rt && rt.type) {
      const icon = _runtimeIcon(rt.type);
      let rtText = `${icon} ${rt.type}`;
      if (rt.version) rtText += ` ${rt.version}`;
      if (rt.java_pid) rtText += ` · PID ${rt.java_pid}`;
      _runtime.textContent = rtText;
      _runtime.style.display = '';
    } else {
      _runtime.textContent = '';
      _runtime.style.display = 'none';
    }

    // 操作按钮
    if (level === 'none') {
      _action.textContent = '🔌 连接';
      _action.className = 'csb-action csb-action-connect';
      _action.style.display = '';
    } else if (level === 'pod') {
      const isJava = rt && rt.type === 'java';
      if (isJava) {
        _action.textContent = '⚡ 启动 Arthas';
        _action.className = 'csb-action csb-action-upgrade';
        _action.style.display = '';
      } else {
        _action.textContent = '🔵 已连接';
        _action.className = 'csb-action csb-action-connected';
        _action.style.display = '';
      }
    } else if (level === 'arthas') {
      _action.textContent = '⚡ 已连接';
      _action.className = 'csb-action csb-action-connected';
      _action.style.display = '';
    }

    // 条体可见性：始终显示（未连接时也展示引导状态）
    _bar.style.display = '';
  }

  function _runtimeIcon(type) {
    const icons = { java: '☕', node: '🟢', python: '🐍', go: '🔵', dotnet: '🟣', unknown: '❓' };
    return icons[type] || '❓';
  }

  // ── 操作按钮处理 ──────────────────────────────────────────────────────
  function handleAction() {
    const level = _getLevel();
    if (level === 'none') {
      if (typeof podConnect === 'function') podConnect();
    } else if (level === 'pod') {
      const rt = _getRuntimeInfo();
      if (rt && rt.type === 'java') {
        if (typeof upgradeToArthas === 'function') upgradeToArthas();
      }
    }
    // arthas 已连接时按钮无操作
  }

  // ── 初始化 ────────────────────────────────────────────────────────────
  function init() {
    _cacheDom();
    refresh();
    // 监听连接状态变化：用 MutationObserver 兜底 + 各连接函数主动调用
  }

  return { init, refresh, handleAction };
})();

// 全局暴露
window.csbRefresh     = function () { ConnStatusBar.refresh(); };
window.csbHandleAction = function () { ConnStatusBar.handleAction(); };

// DOM Ready 时初始化
document.addEventListener('DOMContentLoaded', function () {
  // 延迟一帧确保其他模块先初始化
  requestAnimationFrame(function () {
    ConnStatusBar.init();
  });
});
