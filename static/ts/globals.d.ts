/* Global types for libraries loaded via CDN <script> tags in base.html */

import type { Chart as ChartJS, ChartConfiguration } from "chart.js";
import type { Tab, Toast, Tooltip } from "bootstrap";

declare global {
    const Chart: typeof ChartJS;

    /* Bootstrap exposes these constructors on the global `bootstrap` object */
    const bootstrap: {
        Tab: typeof Tab;
        Toast: typeof Toast;
        Tooltip: typeof Tooltip;
    };
}

export {};
