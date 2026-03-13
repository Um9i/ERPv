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

interface BomNode {
    name: string;
    quantity: number;
    stock: number;
    sufficient: boolean;
    children?: BomNode[];
}

(function () {
    "use strict";

    const dataEl = document.getElementById("bom-tree-data");
    const container = document.getElementById("bom-tree");
    if (!dataEl || !container) return;

    const treeData: BomNode = JSON.parse(dataEl.textContent!);
    const variant = container.dataset.variant || "badges";

    function renderNode(node: BomNode, depth: number): HTMLElement {
        const hasChildren = !!(node.children && node.children.length > 0);
        const sufficient = node.sufficient;

        const wrapper = document.createElement("div");
        wrapper.className = "bom-node";
        wrapper.style.paddingLeft = depth * 1.5 + "rem";

        const row = document.createElement("div");
        row.className =
            "bom-node-row d-flex align-items-center gap-2 py-1" +
            (!sufficient ? " text-danger" : "");

        if (hasChildren) {
            const toggle = document.createElement("button");
            toggle.className = "btn btn-link btn-sm p-0 text-muted bom-toggle";
            toggle.innerHTML = '<i class="bi bi-chevron-down"></i>';
            toggle.addEventListener("click", () => {
                const childContainer = wrapper.querySelector<HTMLElement>(".bom-children")!;
                const isOpen = childContainer.style.display !== "none";
                childContainer.style.display = isOpen ? "none" : "block";
                toggle.innerHTML = isOpen
                    ? '<i class="bi bi-chevron-right"></i>'
                    : '<i class="bi bi-chevron-down"></i>';
            });
            row.appendChild(toggle);
        } else {
            const spacer = document.createElement("span");
            spacer.style.width = "1.5rem";
            spacer.style.display = "inline-block";
            row.appendChild(spacer);
        }

        const icon = document.createElement("i");
        icon.className = sufficient
            ? "bi bi-check-circle-fill text-success"
            : "bi bi-x-circle-fill text-danger";
        row.appendChild(icon);

        const name = document.createElement("span");

        if (variant === "inline") {
            name.className = "flex-grow-1";
            name.textContent = node.name;
            row.appendChild(name);

            const qty = document.createElement("span");
            qty.className = "text-muted small ms-auto me-3";
            qty.textContent = "Need: " + node.quantity;
            row.appendChild(qty);

            const stock = document.createElement("span");
            stock.className =
                "small fw-semibold " + (sufficient ? "text-success" : "text-danger");
            stock.textContent = "Stock: " + node.stock;
            row.appendChild(stock);
        } else {
            name.className = "me-2";
            name.textContent = node.name;
            row.appendChild(name);

            const badges = document.createElement("span");
            badges.className = "ms-1 d-inline-flex gap-1";

            const needBadge = document.createElement("span");
            needBadge.className = "badge bg-secondary-subtle text-secondary fw-normal";
            needBadge.textContent = "Need\u00a0" + node.quantity;
            badges.appendChild(needBadge);

            const stockBadge = document.createElement("span");
            stockBadge.className =
                "badge fw-normal " +
                (sufficient ? "bg-success-subtle text-success" : "bg-danger-subtle text-danger");
            stockBadge.textContent = "Stock\u00a0" + node.stock;
            badges.appendChild(stockBadge);

            row.appendChild(badges);
        }

        wrapper.appendChild(row);

        if (hasChildren) {
            const childContainer = document.createElement("div");
            childContainer.className = "bom-children";
            node.children!.forEach((child) => {
                childContainer.appendChild(renderNode(child, depth + 1));
            });
            wrapper.appendChild(childContainer);
        }

        return wrapper;
    }

    container.appendChild(renderNode(treeData, 0));

    const expandBtn = document.getElementById("bom-expand-all");
    if (expandBtn) {
        expandBtn.addEventListener("click", () => {
            document.querySelectorAll<HTMLElement>(".bom-children").forEach((el) => {
                el.style.display = "block";
            });
            document.querySelectorAll<HTMLElement>(".bom-toggle i").forEach((el) => {
                el.className = "bi bi-chevron-down";
            });
        });
    }
})();
