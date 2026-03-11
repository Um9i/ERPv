/**
 * Product P&L — horizontal bar chart of gross profit by product.
 *
 * Reads chart data from <script id="chart-data" type="application/json">
 * injected by Django's |json_script filter.
 */
(function () {
    'use strict';

    var raw = JSON.parse(document.getElementById('chart-data').textContent);
    var ctx = document.getElementById('pl-chart').getContext('2d');

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: raw.labels,
            datasets: [{
                label: 'Gross Profit',
                data: raw.values,
                backgroundColor: raw.colors,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            return '\u00a3' + ctx.parsed.x.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        callback: function (val) { return '\u00a3' + val.toFixed(0); }
                    }
                }
            }
        }
    });
}());
