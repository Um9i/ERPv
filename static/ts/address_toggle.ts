/**
 * Secondary-address toggle for customer / supplier forms.
 *
 * Expects:
 *   - button#show-addr2
 *   - wrapper#show-addr2-btn  (hidden after click)
 *   - wrapper#addr2-wrap      (shown after click, focuses first input)
 */
(function () {
    "use strict";

    const btn = document.getElementById("show-addr2");
    if (!btn) return;

    btn.addEventListener("click", () => {
        document.getElementById("show-addr2-btn")!.classList.add("d-none");
        const wrap = document.getElementById("addr2-wrap")!;
        wrap.classList.remove("d-none");
        const inp = wrap.querySelector<HTMLInputElement>("input");
        if (inp) inp.focus();
    });
})();
