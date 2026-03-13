/**
 * Bootstrap toast auto-show on page load.
 */
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll<HTMLElement>(".app-toast").forEach((el) => {
        new bootstrap.Toast(el).show();
    });
});
