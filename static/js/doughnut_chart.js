/**
 * Generic doughnut chart initialiser.
 *
 * Reads configuration from a <script id="doughnut-chart-data" type="application/json">
 * block injected by the template.  Expected shape:
 *
 *   { "canvasId": "…", "labels": […], "data": […], "colors": […] }
 */
(function () {
    'use strict';

    var el = document.getElementById('doughnut-chart-data');
    if (!el) return;

    var cfg = JSON.parse(el.textContent);
    var ctx = document.getElementById(cfg.canvasId);
    if (!ctx) return;

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: cfg.labels,
            datasets: [{
                data: cfg.data,
                backgroundColor: cfg.colors,
                borderWidth: 2,
                borderColor: '#fff',
                hoverOffset: 6
            }]
        },
        options: {
            cutout: '68%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            var total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                            var pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
                            return ' ' + ctx.label + ': ' + ctx.parsed + ' (' + pct + '%)';
                        }
                    }
                }
            }
        }
    });
}());
