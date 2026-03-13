/**
 * Product P&L — horizontal bar chart of gross profit by product.
 *
 * Reads chart data from <script id="chart-data" type="application/json">
 * injected by Django's |json_script filter.
 */
(function () {
    "use strict";

    interface PLChartData {
        labels: string[];
        values: number[];
        colors: string[];
    }

    const raw: PLChartData = JSON.parse(document.getElementById("chart-data")!.textContent!);
    const ctx = (document.getElementById("pl-chart") as HTMLCanvasElement).getContext("2d")!;

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: raw.labels,
            datasets: [
                {
                    label: "Gross Profit",
                    data: raw.values,
                    backgroundColor: raw.colors,
                },
            ],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context: { parsed: { x: number } }) =>
                            "\u00a3" + context.parsed.x.toFixed(2),
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        callback: (val: string | number) =>
                            "\u00a3" + Number(val).toFixed(0),
                    },
                },
            },
        },
    });
})();
