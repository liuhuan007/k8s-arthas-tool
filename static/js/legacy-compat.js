(function() {
  'use strict';

  const LEGACY_TAB_ALIAS = {
    workspace: '',
    connections: '',
    profiler: 'sampling',
    sampling: 'sampling',
    console: 'console',
    'arthas-console': 'console',
    terminal: 'terminal',
    monitor: 'monitor',
    filebrowser: 'files',
    files: 'files',
    hotfix: 'hotfix',
    history: 'history',
    diagnose: 'diag',
    diag: 'diag',
    'model-config': 'model-config',
    'task-center': 'task-center',
    'toolchain-center': 'toolchain-center',
    'diagnosis-cap': 'diagnosis-cap',
    alerts: 'alerts',
  };

  const LEGACY_ROUTE_DEFAULT_TAB = {
    connections: '',
    workspace: '',
    profiler: 'sampling',
    'arthas-console': 'console',
    terminal: 'terminal',
    monitor: 'monitor',
    filebrowser: 'files',
    history: 'history',
    diagnose: 'diag',
  };

  function normalizeLegacyCompatTab(rawTab) {
    const key = String(rawTab || '').trim().replace(/^#/, '').toLowerCase();
    return LEGACY_TAB_ALIAS[key] || key;
  }

  function resolveLegacyCompatTarget(routeName, href) {
    const url = new URL(href || window.location.href);
    const params = new URLSearchParams();
    const connId = url.searchParams.get('conn')
      || url.searchParams.get('connection_id')
      || url.searchParams.get('connectionId')
      || '';
    if (connId) params.set('conn', connId);

    const hintedTab = normalizeLegacyCompatTab(
      url.searchParams.get('tab')
      || url.hash.replace(/^#/, '')
      || LEGACY_ROUTE_DEFAULT_TAB[routeName]
      || ''
    );

    const query = params.toString();
    return `/${query ? `?${query}` : ''}${hintedTab ? `#${hintedTab}` : ''}`;
  }

  function initLegacyCompatPage() {
    const routeName = document.body?.dataset?.legacyRoute || '';
    if (!routeName) return;
    const target = resolveLegacyCompatTarget(routeName, window.location.href);
    const link = document.getElementById('legacyCompatLink');
    const targetEl = document.getElementById('legacyCompatTarget');
    if (link) link.href = target;
    if (targetEl) targetEl.textContent = target;
    window.setTimeout(() => window.location.replace(target), 80);
  }

  window.LegacyCompat = {
    normalizeLegacyCompatTab,
    resolveLegacyCompatTarget,
  };

  document.addEventListener('DOMContentLoaded', initLegacyCompatPage);
})();
