/**
 * Product form — character counter & image drag-and-drop preview.
 *
 * Reads configuration from <div id="product-form-config"> data attributes:
 *   - data-textarea-id   : ID of the description <textarea>
 *   - data-file-input-id : ID of the image <input type="file">
 *   - data-preview-url   : (optional) existing image URL for preview
 */
(function () {
    'use strict';

    var config = document.getElementById('product-form-config');
    if (!config) return;

    // ── Character counter ──────────────────────────────────────
    var ta = document.getElementById(config.dataset.textareaId);
    var counter = document.getElementById('desc-counter');
    if (ta && counter) {
        function syncCounter() {
            counter.textContent = ta.value.length + ' chars';
        }
        ta.addEventListener('input', syncCounter);
        syncCounter();
    }

    // ── Image drag-and-drop zone ───────────────────────────────
    var zone        = document.getElementById('image-drop-zone');
    var fileInput   = document.getElementById(config.dataset.fileInputId);
    var placeholder = document.getElementById('image-placeholder');
    var previewWrap = document.getElementById('image-preview-wrap');
    var previewImg  = document.getElementById('image-preview');
    var removeBtn   = document.getElementById('remove-image');

    if (!zone || !fileInput) return;

    if (config.dataset.previewUrl) {
        previewImg.src = config.dataset.previewUrl;
        placeholder.classList.add('d-none');
        previewWrap.classList.remove('d-none');
        previewWrap.style.display = 'flex';
    }

    function showPreview(file) {
        var reader = new FileReader();
        reader.onload = function (e) {
            previewImg.src = e.target.result;
            placeholder.classList.add('d-none');
            previewWrap.classList.remove('d-none');
            previewWrap.style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }

    fileInput.addEventListener('change', function () {
        if (this.files && this.files[0]) showPreview(this.files[0]);
    });

    zone.addEventListener('dragover', function (e) {
        e.preventDefault();
        zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', function () {
        zone.classList.remove('drag-over');
    });
    zone.addEventListener('drop', function (e) {
        e.preventDefault();
        zone.classList.remove('drag-over');
        var file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            var dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
            showPreview(file);
        }
    });

    removeBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        fileInput.value = '';
        previewImg.src = '';
        previewWrap.classList.add('d-none');
        previewWrap.style.display = '';
        placeholder.classList.remove('d-none');
    });
}());
