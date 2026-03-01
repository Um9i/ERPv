/**
 * Unified order-form line management for Purchase Orders, Sales Orders and BOMs.
 *
 * Reads configuration from data-* attributes on the <form> element:
 *   data-entity-select   – ID of the entity <select> (optional, omit for BOM)
 *   data-product-url     – URL template for fetching allowed product IDs (optional)
 *   data-formset-prefix  – Django formset prefix used for TOTAL_FORMS
 */
(function () {
    'use strict';

    var form = document.querySelector('[data-formset-prefix]');
    if (!form) return;

    var entitySelectId = form.dataset.entitySelect;
    var productUrl     = form.dataset.productUrl;
    var prefix         = form.dataset.formsetPrefix;

    var entitySelect  = entitySelectId ? document.getElementById(entitySelectId) : null;
    var linesSection  = document.getElementById('lines-section');
    var submitSection = document.getElementById('submit-section');
    var container     = document.getElementById('lines-container');
    var addBtn        = document.getElementById('add-line');

    /* ── Show/hide lines section based on entity selection ── */
    function toggleSections() {
        var hasEntity = entitySelect && entitySelect.value && entitySelect.value !== '';
        if (linesSection)  linesSection.style.display  = hasEntity ? '' : 'none';
        if (submitSection) submitSection.style.display = hasEntity ? '' : 'none';
        if (hasEntity) updateProductOptions(entitySelect.value);
        updateLineCount();
    }

    if (entitySelect) {
        if (entitySelect.type === 'hidden') {
            if (linesSection)  linesSection.style.display  = '';
            if (submitSection) submitSection.style.display = '';
        }
        entitySelect.addEventListener('change', toggleSections);
        toggleSections();
    }

    /* ── Restrict product selects to allowed products ── */
    async function updateProductOptions(entityId) {
        if (!entityId || !productUrl) return;
        var url = productUrl.replace(/\/\d+\//, '/' + entityId + '/');
        try {
            var resp = await fetch(url);
            if (!resp.ok) return;
            var data = await resp.json();
            var allowed = new Set(data.product_ids.map(String));
            document.querySelectorAll('#lines-container select').forEach(function (select) {
                if (!select.name.endsWith('-product')) return;
                Array.from(select.options).forEach(function (opt) {
                    if (opt.value === '') return;
                    opt.hidden = !allowed.has(opt.value);
                    if (opt.hidden && opt.selected) select.value = '';
                });
            });
        } catch (e) { /* network error – ignore */ }
    }

    /* ── Add new line ── */
    addBtn.addEventListener('click', function () {
        var totalForms = document.getElementById('id_' + prefix + '-TOTAL_FORMS');
        if (!totalForms) return;
        var formCount = parseInt(totalForms.value, 10);
        var prototype = container.querySelector('.line-form');
        if (!prototype) return;
        var emptyForm = prototype.cloneNode(true);
        emptyForm.querySelectorAll('input, select, textarea').forEach(function (el) {
            if (el.name) {
                el.name = el.name.replace(/-(\d+)-/, '-' + formCount + '-');
                el.id = 'id_' + el.name;
                if (el.type !== 'hidden') el.value = '';
                if (el.type === 'checkbox') el.checked = false;
            }
        });
        emptyForm.querySelectorAll('.text-danger, .invalid-feedback').forEach(function (el) { el.remove(); });
        emptyForm.querySelectorAll('.is-invalid').forEach(function (el) { el.classList.remove('is-invalid'); });
        container.appendChild(emptyForm);
        totalForms.value = formCount + 1;
        if (entitySelect && entitySelect.value) {
            updateProductOptions(entitySelect.value);
        }
        updateLineCount();
    });

    /* ── Remove line ── */
    container.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-line');
        if (!btn) return;
        var lineForm = btn.closest('.line-form');
        if (!lineForm) return;
        var deleteCheckbox = lineForm.querySelector('input[name$="-DELETE"]');
        if (deleteCheckbox) {
            deleteCheckbox.checked = true;
            lineForm.style.display = 'none';
        } else {
            lineForm.remove();
        }
        updateLineCount();
    });

    /* ── Line count ── */
    function updateLineCount() {
        var visible = container.querySelectorAll('.line-form:not([style*="display: none"])');
        var el = document.getElementById('line-count');
        if (el) el.textContent = visible.length;
    }
    updateLineCount();
})();
