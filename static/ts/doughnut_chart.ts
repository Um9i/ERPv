/**
 * Generic doughnut chart initialiser.
 *
 * Reads configuration from a <script id="doughnut-chart-data" type="application/json">
 * block injected by the template.  Expected shape:
 *
 *   { "canvasId": "…", "labels": […], "data": […], "colors": […] }
 */
(function () {
    "use strict";

    interface DoughnutConfig {
        canvasId: string;
        labels: string[];
        data: number[];
        colors: string[];
    }

    const el = document.getElementById("doughnut-chart-data");
    if (!el) return;

    const cfg: DoughnutConfig = JSON.parse(el.textContent!);
    const ctx = document.getElementById(cfg.canvasId) as HTMLCanvasElement | null;
    if (!ctx) return;

    new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: cfg.labels,
            datasets: [
                {
                    data: cfg.data,
                    backgroundColor: cfg.colors,
                    borderWidth: 2,
                    borderColor: "#fff",
                    hoverOffset: 6,
                },
            ],
        },
        options: {
            cutout: "68%",
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context: {
                            dataset: { data: number[] };
                            parsed: number;
                            label: string;
                        }) => {
                            const total = context.dataset.data.reduce(
                                (a: number, b: number) => a + b,
                                0,
                            );
                            const pct =
                                total > 0
                                    ? Math.round((context.parsed / total) * 100)
                                    : 0;
                            return " " + context.label + ": " + context.parsed + " (" + pct + "%)";
                        },
                    },
                },
            },
        },
    });
})();
