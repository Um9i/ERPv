document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".app-toast").forEach(function (el) {
        new bootstrap.Toast(el).show();
    });
});
