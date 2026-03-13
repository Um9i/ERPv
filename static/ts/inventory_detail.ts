/**
 * Inventory detail page – Chart.js visualisations.
 *
 * Reads chart data from a <script id="chart-data" type="application/json">
 * tag injected by Django's |json_script filter.
 */

interface InventoryChartData {
    sales_pending: number;
    purchase_pending: number;
    production_pending: number;
    required_qty: number;
    history_dates: string[];
    history_qty: number[];
    monthly_dates: string[];
    monthly_sales: number[];
    monthly_purchases: number[];
    monthly_production: number[];
}

(function () {
    "use strict";

    const dataEl = document.getElementById("chart-data");
    if (!dataEl) return;
    const data: InventoryChartData = JSON.parse(dataEl.textContent!);

    /* ── Design-system colours ── */
    const COLORS = {
        primary: "#6366f1",
        primaryLight: "rgba(99,102,241,0.15)",
        success: "#059669",
        successBg: "rgba(5,150,105,0.12)",
        info: "#2563eb",
        infoBg: "rgba(37,99,235,0.12)",
        warning: "#d97706",
        warningBg: "rgba(217,119,6,0.12)",
        danger: "#dc2626",
        dangerBg: "rgba(220,38,38,0.12)",
        border: "#e2e8f0",
        text: "#64748b",
    } as const;

    const sharedFont = { family: "'Inter', sans-serif", size: 12 };
    const sharedOptions = {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
            legend: {
                labels: { font: sharedFont, usePointStyle: true, padding: 16 },
            },
            tooltip: {
                titleFont: sharedFont,
                bodyFont: sharedFont,
                cornerRadius: 8,
                padding: 10,
            },
        },
    } as const;

    /* ── Demand doughnut (only rendered when canvas exists) ── */
    const pendingEl = document.getElementById("pending-chart") as HTMLCanvasElement | null;
    if (pendingEl) {
        const pendingCtx = pendingEl.getContext("2d")!;
        const pendingLabels: string[] = ["Sales Pending", "Purchases Incoming"];
        const pendingData: number[] = [data.sales_pending, data.purchase_pending];
        const pendingColors: string[] = [COLORS.success, COLORS.info];

        if (data.production_pending > 0) {
            pendingLabels.push("In Production");
            pendingData.push(data.production_pending);
            pendingColors.push(COLORS.warning);
        }

        pendingLabels.push("Shortage");
        pendingData.push(data.required_qty);
        pendingColors.push(COLORS.danger);

        new Chart(pendingCtx, {
            type: "doughnut",
            data: {
                labels: pendingLabels,
                datasets: [
                    {
                        data: pendingData,
                        backgroundColor: pendingColors,
                        borderWidth: 2,
                        borderColor: "#fff",
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                ...sharedOptions,
                cutout: "62%",
                plugins: {
                    ...sharedOptions.plugins,
                    legend: {
                        position: "bottom" as const,
                        labels: {
                            font: sharedFont,
                            usePointStyle: true,
                            padding: 12,
                        },
                    },
                },
            },
        });
    }

    /* ── Inventory level history ── */
    const histCtx = (
        document.getElementById("history-chart") as HTMLCanvasElement
    ).getContext("2d")!;
    const histGradient = histCtx.createLinearGradient(0, 0, 0, 280);
    histGradient.addColorStop(0, "rgba(99,102,241,0.25)");
    histGradient.addColorStop(1, "rgba(99,102,241,0.01)");

    const histChart = new Chart(histCtx, {
        type: "line",
        data: {
            labels: data.history_dates,
            datasets: [
                {
                    label: "Stock Level",
                    data: data.history_qty,
                    borderColor: COLORS.primary,
                    backgroundColor: histGradient,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 3,
                    pointBackgroundColor: "#fff",
                    pointBorderColor: COLORS.primary,
                    pointBorderWidth: 2,
                    pointHoverRadius: 6,
                    borderWidth: 2.5,
                },
            ],
        },
        options: {
            ...sharedOptions,
            aspectRatio: 3.5,
            scales: {
                x: {
                    ticks: {
                        font: sharedFont,
                        color: COLORS.text,
                        maxTicksLimit: 8,
                        maxRotation: 0,
                    },
                    grid: { display: false },
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: sharedFont, color: COLORS.text },
                    grid: { color: COLORS.border },
                },
            },
        },
    });

    /* ── Monthly activity ── */
    const monthCtx = (
        document.getElementById("monthly-chart") as HTMLCanvasElement
    ).getContext("2d")!;

    const monthChart = new Chart(monthCtx, {
        type: "bar",
        data: {
            labels: data.monthly_dates,
            datasets: [
                {
                    label: "Sales",
                    backgroundColor: COLORS.success,
                    borderRadius: 4,
                    data: data.monthly_sales,
                },
                {
                    label: "Purchases",
                    backgroundColor: COLORS.info,
                    borderRadius: 4,
                    data: data.monthly_purchases,
                },
                {
                    label: "Production",
                    backgroundColor: COLORS.warning,
                    borderRadius: 4,
                    data: data.monthly_production,
                },
            ],
        },
        options: {
            ...sharedOptions,
            aspectRatio: 3,
            scales: {
                x: {
                    ticks: { font: sharedFont, color: COLORS.text },
                    grid: { display: false },
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: sharedFont, color: COLORS.text },
                    grid: { color: COLORS.border },
                },
            },
        },
    });

    /* ── Resize activity charts when their tab becomes visible ── */
    const actTabBtn = document.getElementById("tab-activity-btn");
    if (actTabBtn) {
        actTabBtn.addEventListener("shown.bs.tab", () => {
            histChart.resize();
            monthChart.resize();
        });
    }
})();

/* ── Bootstrap tooltips ── */
(function () {
    "use strict";
    document.querySelectorAll<HTMLElement>('[data-bs-toggle="tooltip"]').forEach((el) => {
        new bootstrap.Tooltip(el);
    });
})();
