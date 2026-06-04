/**
 * Page-aware script loader
 * Loads only the scripts needed for the current page, sequentially,
 * skipping already-loaded ones.
 */
var PageLoader = {
    _loaded: new Set(),

    /**
     * Load scripts sequentially, skipping already-loaded ones.
     * Returns a Promise that resolves when all scripts are loaded.
     * @param {string[]} scripts - Array of script paths to load
     * @returns {Promise<void>}
     */
    loadScripts: function(scripts) {
        var self = this;
        var chain = Promise.resolve();
        scripts.forEach(function(src) {
            chain = chain.then(function() {
                if (self._loaded.has(src)) return;
                return self._loadScript(src).then(function() {
                    self._loaded.add(src);
                });
            });
        });
        return chain;
    },

    _loadScript: function(src) {
        return new Promise(function(resolve) {
            var script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = function() {
                console.warn('[PageLoader] Failed to load: ' + src);
                resolve(); // Don't block on failed scripts
            };
            document.body.appendChild(script);
        });
    }
};
