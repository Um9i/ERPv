/**
 * BOM (Bill of Materials) tree renderer.
 *
 * Reads tree data from <script id="bom-tree-data" type="application/json">
 * and renders a collapsible hierarchy into <div id="bom-tree">.
 *
 * Supports two display variants via data-variant on the #bom-tree element:
 *   - "badges" (default): Need/Stock shown as coloured badge pills
 *   - "inline": Need/Stock shown as plain text spans
 */
(function () {
    'use strict';

    var dataEl = document.getElementById('bom-tree-data');
    var container = document.getElementById('bom-tree');
    if (!dataEl || !container) return;

    var treeData = JSON.parse(dataEl.textContent);
    var variant = (container.dataset.variant || 'badges');

    function renderNode(node, depth) {
        var hasChildren = node.children && node.children.length > 0;
        var sufficient = node.sufficient;

        var wrapper = document.createElement('div');
        wrapper.className = 'bom-node';
        wrapper.style.paddingLeft = depth * 1.5 + 'rem';

        var row = document.createElement('div');
        row.className = 'bom-node-row d-flex align-items-center gap-2 py-1' +
                         (!sufficient ? ' text-danger' : '');

        if (hasChildren) {
            var toggle = document.createElement('button');
            toggle.className = 'btn btn-link btn-sm p-0 text-muted bom-toggle';
            toggle.innerHTML = '<i class="bi bi-chevron-down"></i>';
            toggle.addEventListener('click', function () {
                var childContainer = wrapper.querySelector('.bom-children');
                var isOpen = childContainer.style.display !== 'none';
                childContainer.style.display = isOpen ? 'none' : 'block';
                toggle.innerHTML = isOpen
                    ? '<i class="bi bi-chevron-right"></i>'
                    : '<i class="bi bi-chevron-down"></i>';
            });
            row.appendChild(toggle);
        } else {
            var spacer = document.createElement('span');
            spacer.style.width = '1.5rem';
            spacer.style.display = 'inline-block';
            row.appendChild(spacer);
        }

        var icon = document.createElement('i');
        icon.className = sufficient
            ? 'bi bi-check-circle-fill text-success'
            : 'bi bi-x-circle-fill text-danger';
        row.appendChild(icon);

        var name = document.createElement('span');

        if (variant === 'inline') {
            name.className = 'flex-grow-1';
            name.textContent = node.name;
            row.appendChild(name);

            var qty = document.createElement('span');
            qty.className = 'text-muted small ms-auto me-3';
            qty.textContent = 'Need: ' + node.quantity;
            row.appendChild(qty);

            var stock = document.createElement('span');
            stock.className = 'small fw-semibold ' + (sufficient ? 'text-success' : 'text-danger');
            stock.textContent = 'Stock: ' + node.stock;
            row.appendChild(stock);
        } else {
            name.className = 'me-2';
            name.textContent = node.name;
            row.appendChild(name);

            var badges = document.createElement('span');
            badges.className = 'ms-1 d-inline-flex gap-1';

            var needBadge = document.createElement('span');
            needBadge.className = 'badge bg-secondary-subtle text-secondary fw-normal';
            needBadge.textContent = 'Need\u00a0' + node.quantity;
            badges.appendChild(needBadge);

            var stockBadge = document.createElement('span');
            stockBadge.className = 'badge fw-normal ' + (sufficient ? 'bg-success-subtle text-success' : 'bg-danger-subtle text-danger');
            stockBadge.textContent = 'Stock\u00a0' + node.stock;
            badges.appendChild(stockBadge);

            row.appendChild(badges);
        }

        wrapper.appendChild(row);

        if (hasChildren) {
            var childContainer = document.createElement('div');
            childContainer.className = 'bom-children';
            node.children.forEach(function (child) {
                childContainer.appendChild(renderNode(child, depth + 1));
            });
            wrapper.appendChild(childContainer);
        }

        return wrapper;
    }

    container.appendChild(renderNode(treeData, 0));

    var expandBtn = document.getElementById('bom-expand-all');
    if (expandBtn) {
        expandBtn.addEventListener('click', function () {
            document.querySelectorAll('.bom-children').forEach(function (el) {
                el.style.display = 'block';
            });
            document.querySelectorAll('.bom-toggle i').forEach(function (el) {
                el.className = 'bi bi-chevron-down';
            });
        });
    }
}());
