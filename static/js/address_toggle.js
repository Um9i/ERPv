/**
 * Secondary-address toggle for customer / supplier forms.
 *
 * Expects:
 *   - button#show-addr2
 *   - wrapper#show-addr2-btn  (hidden after click)
 *   - wrapper#addr2-wrap      (shown after click, focuses first input)
 */
(function () {
    'use strict';

    var btn = document.getElementById('show-addr2');
    if (!btn) return;

    btn.addEventListener('click', function () {
        document.getElementById('show-addr2-btn').classList.add('d-none');
        document.getElementById('addr2-wrap').classList.remove('d-none');
        var inp = document.getElementById('addr2-wrap').querySelector('input');
        if (inp) inp.focus();
    });
}());
