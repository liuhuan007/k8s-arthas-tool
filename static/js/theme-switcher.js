(function () {
  const KEY = 'ops_ui_theme';
  const DEFAULT_THEME = 'apm';
  const VALID_THEMES = new Set(['apm', 'devops']);

  function normalizeTheme(theme) {
    return VALID_THEMES.has(theme) ? theme : DEFAULT_THEME;
  }

  function readTheme() {
    try {
      return normalizeTheme(localStorage.getItem(KEY) || DEFAULT_THEME);
    } catch (_) {
      return DEFAULT_THEME;
    }
  }

  function writeTheme(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (_) {}
  }

  function applyThemeToDocument(doc, theme) {
    if (!doc || !doc.documentElement) return;
    if (normalizeTheme(theme) === 'devops') {
      doc.documentElement.setAttribute('data-ops-theme', 'devops');
    } else {
      doc.documentElement.removeAttribute('data-ops-theme');
    }
  }

  function syncChildFrames(theme) {
    document.querySelectorAll('iframe').forEach((frame) => {
      try {
        applyThemeToDocument(frame.contentDocument, theme);
      } catch (_) {}
      try {
        frame.contentWindow?.postMessage({ type: 'ops-ui-theme', theme }, window.location.origin);
      } catch (_) {}
    });
  }

  function applyTheme(theme, options) {
    const nextTheme = normalizeTheme(theme);
    applyThemeToDocument(document, nextTheme);

    document.querySelectorAll('[data-theme-switcher]').forEach((control) => {
      if (control.value !== nextTheme) control.value = nextTheme;
    });

    if (!options || options.persist !== false) writeTheme(nextTheme);
    if (!options || options.broadcast !== false) syncChildFrames(nextTheme);
  }

  function initThemeSwitchers() {
    applyTheme(readTheme(), { persist: false });
    document.querySelectorAll('[data-theme-switcher]').forEach((control) => {
      control.addEventListener('change', () => applyTheme(control.value));
    });
  }

  window.addEventListener('storage', (event) => {
    if (event.key === KEY) applyTheme(event.newValue, { persist: false, broadcast: false });
  });

  window.addEventListener('message', (event) => {
    if (event.origin !== window.location.origin) return;
    if (event.data && event.data.type === 'ops-ui-theme') {
      applyTheme(event.data.theme, { persist: false, broadcast: false });
    }
  });

  window.addEventListener('load', () => syncChildFrames(readTheme()));

  window.OpsTheme = {
    apply: applyTheme,
    current: readTheme,
    syncFrames: syncChildFrames,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeSwitchers);
  } else {
    initThemeSwitchers();
  }
})();
