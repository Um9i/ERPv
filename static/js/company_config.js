/**
 * Company configuration page — logo upload handler & hash-based tab routing.
 *
 * Reads initial-tab override from <div id="config-page-data"> data attributes:
 *   - data-initial-tab : (optional) tab name to activate on load (e.g. "integrations")
 */
(function () {
    'use strict';

    // ── Logo file input ────────────────────────────────────────
    var logoInput = document.getElementById('id_logo');
    if (logoInput) {
        logoInput.classList.add('d-none');
        logoInput.addEventListener('change', function () {
            var label = document.getElementById('logo-file-name');
            if (label) label.textContent = this.files[0] ? this.files[0].name : 'No file selected';
        });
    }

    // ── Hash-based tab routing ─────────────────────────────────
    var TABS = ['company', 'address', 'branding', 'integrations'];
    var DEFAULT_TAB = 'company';

    function activateTab(hash) {
        var name = (hash || '').replace(/^#/, '');
        if (TABS.indexOf(name) === -1) name = DEFAULT_TAB;
        var btn = document.querySelector('[data-tab-hash="' + name + '"]');
        if (btn) {
            var tab = new bootstrap.Tab(btn);
            tab.show();
        }
    }

    // Set hash when tab changes
    document.querySelectorAll('[data-tab-hash]').forEach(function (btn) {
        btn.addEventListener('shown.bs.tab', function () {
            history.replaceState(null, '', '#' + btn.dataset.tabHash);
        });
    });

    // Restore tab from hash on load
    activateTab(window.location.hash || '#' + DEFAULT_TAB);

    // Handle back/forward navigation
    window.addEventListener('hashchange', function () {
        activateTab(window.location.hash);
    });

    // If initial-tab override is present, jump to that tab
    var pageData = document.getElementById('config-page-data');
    if (pageData && pageData.dataset.initialTab) {
        activateTab('#' + pageData.dataset.initialTab);
    }
}());
