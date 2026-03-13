/**
 * Unified order-form line management for Purchase Orders, Sales Orders and BOMs.
 *
 * Reads configuration from data-* attributes on the <form> element:
 *   data-entity-select   – ID of the entity <select> (optional, omit for BOM)
 *   data-product-url     – URL template for fetching allowed product IDs (optional)
 *   data-formset-prefix  – Django formset prefix used for TOTAL_FORMS
 */

interface ProductResponse {
    product_ids: number[];
}

(function () {
    "use strict";

    const form = document.querySelector<HTMLFormElement>("[data-formset-prefix]");
    if (!form) return;

    const entitySelectId = form.dataset.entitySelect;
    const productUrl = form.dataset.productUrl;
    const prefix = form.dataset.formsetPrefix!;

    const entitySelect = entitySelectId
        ? (document.getElementById(entitySelectId) as HTMLSelectElement | null)
        : null;
    const linesSection = document.getElementById("lines-section") as HTMLElement | null;
    const submitSection = document.getElementById("submit-section") as HTMLElement | null;
    const container = document.getElementById("lines-container")!;
    const addBtn = document.getElementById("add-line")!;

    /* ── Show/hide lines section based on entity selection ── */
    function toggleSections(): void {
        const hasEntity = !!(entitySelect && entitySelect.value && entitySelect.value !== "");
        if (linesSection) linesSection.style.display = hasEntity ? "" : "none";
        if (submitSection) submitSection.style.display = hasEntity ? "" : "none";
        if (hasEntity) updateProductOptions(entitySelect!.value);
        updateLineCount();
    }

    if (entitySelect) {
        if ((entitySelect as HTMLElement).getAttribute("type") === "hidden") {
            if (linesSection) linesSection.style.display = "";
            if (submitSection) submitSection.style.display = "";
        }
        entitySelect.addEventListener("change", toggleSections);
        toggleSections();
    }

    /* ── Restrict product selects to allowed products ── */
    async function updateProductOptions(entityId: string): Promise<void> {
        if (!entityId || !productUrl) return;
        const url = productUrl.replace(/\/\d+\//, "/" + entityId + "/");
        try {
            const resp = await fetch(url);
            if (!resp.ok) return;
            const data: ProductResponse = await resp.json();
            const allowed = new Set(data.product_ids.map(String));
            document
                .querySelectorAll<HTMLSelectElement>("#lines-container select")
                .forEach((select) => {
                    if (!select.name.endsWith("-product")) return;
                    Array.from(select.options).forEach((opt) => {
                        if (opt.value === "") return;
                        opt.hidden = !allowed.has(opt.value);
                        if (opt.hidden && opt.selected) select.value = "";
                    });
                });
        } catch {
            /* network error – ignore */
        }
    }

    /* ── Add new line ── */
    addBtn.addEventListener("click", () => {
        const totalForms = document.getElementById(
            "id_" + prefix + "-TOTAL_FORMS",
        ) as HTMLInputElement | null;
        if (!totalForms) return;
        const formCount = parseInt(totalForms.value, 10);
        const prototype = container.querySelector<HTMLElement>(".line-form");
        if (!prototype) return;
        const emptyForm = prototype.cloneNode(true) as HTMLElement;
        emptyForm
            .querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
                "input, select, textarea",
            )
            .forEach((el) => {
                if (el.name) {
                    el.name = el.name.replace(/-(\d+)-/, "-" + formCount + "-");
                    el.id = "id_" + el.name;
                    if ((el as HTMLInputElement).type !== "hidden") el.value = "";
                    if ((el as HTMLInputElement).type === "checkbox")
                        (el as HTMLInputElement).checked = false;
                }
            });
        emptyForm
            .querySelectorAll<HTMLElement>(".text-danger, .invalid-feedback")
            .forEach((el) => el.remove());
        emptyForm
            .querySelectorAll<HTMLElement>(".is-invalid")
            .forEach((el) => el.classList.remove("is-invalid"));
        container.appendChild(emptyForm);
        totalForms.value = String(formCount + 1);
        if (entitySelect?.value) {
            updateProductOptions(entitySelect.value);
        }
        updateLineCount();
    });

    /* ── Remove line ── */
    container.addEventListener("click", (e: Event) => {
        const target = e.target as HTMLElement;
        const btn = target.closest<HTMLElement>(".remove-line");
        if (!btn) return;
        const lineForm = btn.closest<HTMLElement>(".line-form");
        if (!lineForm) return;
        const deleteCheckbox = lineForm.querySelector<HTMLInputElement>(
            'input[name$="-DELETE"]',
        );
        if (deleteCheckbox) {
            deleteCheckbox.checked = true;
            lineForm.style.display = "none";
        } else {
            lineForm.remove();
        }
        updateLineCount();
    });

    /* ── Line count ── */
    function updateLineCount(): void {
        const visible = container.querySelectorAll<HTMLElement>(
            '.line-form:not([style*="display: none"])',
        );
        const el = document.getElementById("line-count");
        if (el) el.textContent = String(visible.length);
    }
    updateLineCount();
})();
