/**
 * Company configuration page — logo upload handler & hash-based tab routing.
 *
 * Reads initial-tab override from <div id="config-page-data"> data attributes:
 *   - data-initial-tab : (optional) tab name to activate on load (e.g. "integrations")
 */
(function () {
    "use strict";

    // ── Logo file input ────────────────────────────────────────
    const logoInput = document.getElementById("id_logo") as HTMLInputElement | null;
    if (logoInput) {
        logoInput.classList.add("d-none");
        logoInput.addEventListener("change", function () {
            const label = document.getElementById("logo-file-name");
            if (label) label.textContent = this.files?.[0] ? this.files[0].name : "No file selected";
        });
    }

    // ── Hash-based tab routing ─────────────────────────────────
    const TABS = ["company", "address", "branding", "integrations"] as const;
    const DEFAULT_TAB = "company";

    function activateTab(hash: string): void {
        let name = (hash || "").replace(/^#/, "");
        if (!(TABS as readonly string[]).includes(name)) name = DEFAULT_TAB;
        const btn = document.querySelector<HTMLElement>(`[data-tab-hash="${name}"]`);
        if (btn) {
            const tab = new bootstrap.Tab(btn);
            tab.show();
        }
    }

    // Set hash when tab changes
    document.querySelectorAll<HTMLElement>("[data-tab-hash]").forEach((btn) => {
        btn.addEventListener("shown.bs.tab", () => {
            history.replaceState(null, "", "#" + btn.dataset.tabHash);
        });
    });

    // Restore tab from hash on load
    activateTab(window.location.hash || "#" + DEFAULT_TAB);

    // Handle back/forward navigation
    window.addEventListener("hashchange", () => {
        activateTab(window.location.hash);
    });

    // If initial-tab override is present, jump to that tab
    const pageData = document.getElementById("config-page-data") as HTMLElement | null;
    if (pageData?.dataset.initialTab) {
        activateTab("#" + pageData.dataset.initialTab);
    }
})();
