/**
 * Product form — character counter & image drag-and-drop preview.
 *
 * Reads configuration from <div id="product-form-config"> data attributes:
 *   - data-textarea-id   : ID of the description <textarea>
 *   - data-file-input-id : ID of the image <input type="file">
 *   - data-preview-url   : (optional) existing image URL for preview
 */
(function () {
    "use strict";

    const config = document.getElementById("product-form-config") as HTMLElement | null;
    if (!config) return;

    // ── Character counter ──────────────────────────────────────
    const ta = document.getElementById(config.dataset.textareaId!) as HTMLTextAreaElement | null;
    const counter = document.getElementById("desc-counter");
    if (ta && counter) {
        function syncCounter(): void {
            counter!.textContent = ta!.value.length + " chars";
        }
        ta.addEventListener("input", syncCounter);
        syncCounter();
    }

    // ── Image drag-and-drop zone ───────────────────────────────
    const zone = document.getElementById("image-drop-zone");
    const fileInput = document.getElementById(config.dataset.fileInputId!) as HTMLInputElement | null;
    const placeholder = document.getElementById("image-placeholder");
    const previewWrap = document.getElementById("image-preview-wrap") as HTMLElement | null;
    const previewImg = document.getElementById("image-preview") as HTMLImageElement | null;
    const removeBtn = document.getElementById("remove-image");

    if (!zone || !fileInput) return;

    if (config.dataset.previewUrl) {
        previewImg!.src = config.dataset.previewUrl;
        placeholder!.classList.add("d-none");
        previewWrap!.classList.remove("d-none");
        previewWrap!.style.display = "flex";
    }

    function showPreview(file: File): void {
        const reader = new FileReader();
        reader.onload = (e: ProgressEvent<FileReader>) => {
            previewImg!.src = e.target!.result as string;
            placeholder!.classList.add("d-none");
            previewWrap!.classList.remove("d-none");
            previewWrap!.style.display = "flex";
        };
        reader.readAsDataURL(file);
    }

    fileInput.addEventListener("change", function () {
        if (this.files?.[0]) showPreview(this.files[0]);
    });

    zone.addEventListener("dragover", (e: DragEvent) => {
        e.preventDefault();
        zone!.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => {
        zone!.classList.remove("drag-over");
    });
    zone.addEventListener("drop", (e: DragEvent) => {
        e.preventDefault();
        zone!.classList.remove("drag-over");
        const file = e.dataTransfer?.files[0];
        if (file?.type.startsWith("image/")) {
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput!.files = dt.files;
            showPreview(file);
        }
    });

    removeBtn!.addEventListener("click", (e: Event) => {
        e.stopPropagation();
        fileInput!.value = "";
        previewImg!.src = "";
        previewWrap!.classList.add("d-none");
        previewWrap!.style.display = "";
        placeholder!.classList.remove("d-none");
    });
})();
