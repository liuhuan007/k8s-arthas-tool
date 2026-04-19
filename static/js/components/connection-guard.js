/**
 * 连接引导守卫 (ConnectionGuard)
 *
 * 统一管理功能→所需连接层级的映射，提供：
 * 1. 连接层级检查
 * 2. 统一引导面板（替代分散的 toast / diagShowError）
 * 3. 层级定义：none < pod < arthas
 */

const ConnectionGuard = (function () {
  'use strict';

  // ── 功能所需最低连接层级 ──────────────────────────────────────────
  const REQUIREMENTS = {
    'profiler':    'arthas',   // 🔥 采样工具
    'console':     'arthas',   // ⚡ Arthas 命令
    'diag.jvm':    'arthas',   // 🔬 JVM 深度诊断 (dashboard/threads/trace)
    'monitor':     'pod',      // 📊 Pod 监控
    'filebrowser': 'pod',      // 📂 文件下载
    'terminal':    'pod',      // 🖥️ 终端
    'diag.pod':    'pod',      // 🔬 系统诊断 (sys_cpu/mem/disk/net/proc/system_overview)
    'diag':        'pod',      // 🔬 性能诊断 Tab 整体
    'ai':          'none',     // 🤖 AI 助手
    'history':     'none',     // 📋 历史记录
  };

  // 层级排序
  const LEVEL_RANK = { none: 0, pod: 1, arthas: 2 };

  // ── 获取当前连接层级 ──────────────────────────────────────────────

  function getCurrentLevel() {
    const cs = window._connState;
    if (cs === 'arthas_ready') return 'arthas';
    if (cs === 'pod_connected') return 'pod';

    // 兼容旧流程或状态未完全同步的场景：优先从当前连接对象推断真实层级
    if (window._currentConnId) {
      const conn = (window._connections || []).find(c => c.id === window._currentConnId);
      if (conn) {
        if (conn.level === 'arthas' || conn.local_port || conn.arthas_version || conn.java_pid) return 'arthas';
        if (conn.level === 'pod' || conn.runtime_type || conn.runtime) return 'pod';
      }
    }
    return 'none';
  }

  // ── 检查是否满足要求 ──────────────────────────────────────────────

  function check(feature) {
    const required = REQUIREMENTS[feature] || 'none';
    const current = getCurrentLevel();
    const ok = LEVEL_RANK[current] >= LEVEL_RANK[required];
    return { ok, current, required, missing: !ok };
  }

  // ── 统一引导入口 ──────────────────────────────────────────────────

  function guard(feature) {
    const result = check(feature);
    if (result.ok) return true;
    showGuide(feature, result.current, result.required);
    return false;
  }

  // ── 引导面板 ──────────────────────────────────────────────────────

  let _guideEl = null;

  /** 连接类型值映射：pod→Pod连接, arthas→Arthas连接 */
  function _levelLabel(lv) {
    return { pod: 'Pod连接', arthas: 'Arthas连接', none: '未连接' }[lv] || lv;
  }

  function showGuide(feature, current, required) {
    // 获取或创建引导容器
    const container = _getGuideContainer();
    if (!container) return;

    const runtimeInfo = window._runtimeInfo;
    const runtimeType = runtimeInfo && (runtimeInfo.runtime_type || runtimeInfo.type);
    const runtimeVersion = runtimeInfo && (runtimeInfo.version || runtimeInfo.runtime_version || '');
    const isJava = runtimeType === 'java';

    let html = '';

    if (required === 'pod' && current === 'none') {
      // 场景 A: 需要 Pod 连接
      html = `
        <div class="cg-card">
          <div class="cg-icon">🔌</div>
          <div class="cg-body">
            <div class="cg-title">需要先建立 Pod 连接</div>
            <div class="cg-desc">选择左侧的集群和 Pod，然后点击连接按钮</div>
            <button class="cg-btn cg-btn-primary" onclick="window.podConnect && podConnect()">🔌 立即连接</button>
          </div>
        </div>`;
    } else if (required === 'arthas' && current === 'pod') {
      if (isJava) {
        // 场景 B: 需要 Arthas，Pod 已连接且是 Java
        const rtIcon = _getRuntimeIcon(runtimeType);
        const rtVer = runtimeVersion ? ` ${runtimeVersion}` : '';
        html = `
          <div class="cg-card">
            <div class="cg-icon">⚡</div>
            <div class="cg-body">
              <div class="cg-title">此功能需要 Arthas 诊断环境</div>
              <div class="cg-desc">当前 Pod 已连接 (${rtIcon} ${runtimeType}${rtVer})，可一键启动 Arthas</div>
              <button class="cg-btn cg-btn-primary" onclick="window.upgradeToArthas && upgradeToArthas()">⚡ 启动 Arthas</button>
            </div>
          </div>`;
      } else {
        // 场景 C: 需要 Arthas，但非 Java 运行时
        html = `
          <div class="cg-card">
            <div class="cg-icon">⚡</div>
            <div class="cg-body">
              <div class="cg-title">此功能需要 Arthas 诊断环境</div>
              <div class="cg-desc">当前运行时为 ${runtimeType || '未知'}，Arthas 仅支持 Java 应用。<br>请选择一个 Java 应用的 Pod。</div>
            </div>
          </div>`;
      }
    } else if (required === 'arthas' && current === 'none') {
      // 场景 D: 需要 Arthas，但连 Pod 都没连
      html = `
        <div class="cg-card">
          <div class="cg-icon">⚡</div>
          <div class="cg-body">
            <div class="cg-title">此功能需要 Arthas 诊断环境</div>
            <div class="cg-desc">请先建立 Pod 连接，再启动 Arthas</div>
            <button class="cg-btn cg-btn-primary" onclick="window.podConnect && podConnect()">🔌 立即连接</button>
          </div>
        </div>`;
    } else {
      // 兜底
      html = `
        <div class="cg-card">
          <div class="cg-icon">🔒</div>
          <div class="cg-body">
            <div class="cg-title">需要更高连接类型</div>
            <div class="cg-desc">当前: ${_levelLabel(current)}，需要: ${_levelLabel(required)}</div>
          </div>
        </div>`;
    }

    container.innerHTML = html;
    container.style.display = 'block';
  }

  function hideGuide() {
    const container = _getGuideContainer();
    if (container) {
      container.style.display = 'none';
      container.innerHTML = '';
    }
  }

  /**
   * 获取引导面板容器。
   * 策略：优先在当前激活的 panel 内找，否则创建全局浮动层。
   */
  function _getGuideContainer() {
    // 优先找当前激活面板内的引导容器
    const activePanel = document.querySelector('.panel.on');
    if (activePanel) {
      let el = activePanel.querySelector('.cg-container');
      if (!el) {
        el = document.createElement('div');
        el.className = 'cg-container';
        // 插入到面板最前面
        activePanel.insertBefore(el, activePanel.firstChild);
      }
      return el;
    }

    // 全局浮动层
    if (!_guideEl) {
      _guideEl = document.createElement('div');
      _guideEl.className = 'cg-container cg-floating';
      document.body.appendChild(_guideEl);
    }
    return _guideEl;
  }

  function _getRuntimeIcon(type) {
    const icons = { java: '☕', node: '🟢', python: '🐍', go: '🔵', unknown: '❓' };
    return icons[type] || '❓';
  }

  // ── 功能→层级映射查询 ──────────────────────────────────────────────

  function getRequiredLevel(feature) {
    return REQUIREMENTS[feature] || 'none';
  }

  function getFeatureLevelLabel(level) {
    const labels = { none: '无需连接', pod: 'Pod 连接', arthas: 'Arthas 连接' };
    return labels[level] || level;
  }

  // ── 导出 ──────────────────────────────────────────────────────────

  return {
    getCurrentLevel,
    check,
    guard,
    showGuide,
    hideGuide,
    getRequiredLevel,
    getFeatureLevelLabel,
    REQUIREMENTS,
    LEVEL_RANK
  };
})();

// 全局暴露
window.ConnectionGuard = ConnectionGuard;
