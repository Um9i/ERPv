/**
 * Finance dashboard — Sales vs Purchases bar chart.
 *
 * Reads chart data from <script id="finance-chart-data" type="application/json">
 * injected by Django's |json_script filter.
 */
(function () {
    "use strict";

    interface FinanceChartData {
        months: string[];
        sales: number[];
        purchases: number[];
    }

    const dataEl = document.getElementById("finance-chart-data");
    if (!dataEl) return;
    const data: FinanceChartData = JSON.parse(dataEl.textContent!);

    function buildChart(): void {
        const canvasEl = document.getElementById("finance-chart") as HTMLCanvasElement | null;
        if (!canvasEl || canvasEl.dataset.initialised) return;
        canvasEl.dataset.initialised = "1";
        const ctx = canvasEl.getContext("2d")!;
        new Chart(ctx, {
            type: "bar",
            data: {
                labels: data.months,
                datasets: [
                    {
                        label: "Sales",
                        backgroundColor: "#22c55e",
                        borderRadius: 4,
                        data: data.sales,
                    },
                    {
                        label: "Purchases",
                        backgroundColor: "#3b82f6",
                        borderRadius: 4,
                        data: data.purchases,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        labels: { usePointStyle: true, padding: 16 },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context: {
                                dataset: { label?: string };
                                parsed: { y: number };
                            }) =>
                                context.dataset.label + ": \u00a3" + context.parsed.y.toFixed(2),
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value: string | number) =>
                                "\u00a3" + Number(value).toFixed(2),
                        },
                    },
                },
            },
        });
    }

    // Build on first activation of the chart tab; handles both initial load
    // (chart tab not visible) and any subsequent re-clicks.
    const tabEl = document.getElementById("tab-chart");
    if (tabEl) {
        tabEl.addEventListener("shown.bs.tab", buildChart);
    }
})();
