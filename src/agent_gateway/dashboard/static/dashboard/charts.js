/**
 * Agent Gateway Dashboard — Chart.js helpers
 */

// Read CSS custom property values for chart theming
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function getChartColors() {
  return {
    accent: cssVar('--color-accent') || '#6366f1',
    success: cssVar('--color-success') || '#10b981',
    danger: cssVar('--color-danger') || '#ef4444',
    warning: cssVar('--color-warning') || '#f59e0b',
    info: cssVar('--color-info') || '#0ea5e9',
    grid: cssVar('--color-border') || '#e2e8f0',
    text: cssVar('--color-text-secondary') || '#64748b',
    surface: cssVar('--color-surface') || '#ffffff',
  };
}

// Apply theme-aware Chart.js defaults
function applyChartDefaults() {
  const c = getChartColors();
  Chart.defaults.color = c.text;
  Chart.defaults.borderColor = c.grid;
  Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
}

// Create cost over time line chart
function initCostChart(canvasId, labels, values) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();
  return new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Cost (USD)',
        data: values,
        borderColor: c.accent,
        backgroundColor: c.accent + '22',
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `$${Number(ctx.raw).toFixed(4)}`,
          },
        },
      },
      scales: {
        x: { grid: { color: c.grid + '60' } },
        y: {
          grid: { color: c.grid + '60' },
          ticks: {
            callback: (v) => `$${Number(v).toFixed(3)}`,
          },
        },
      },
    },
  });
}

// Create executions stacked bar chart
function initExecutionsChart(canvasId, labels, successData, failedData) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();
  return new Chart(el, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Completed',
          data: successData,
          backgroundColor: c.success + 'cc',
          borderRadius: 3,
          borderSkipped: false,
        },
        {
          label: 'Failed',
          data: failedData,
          backgroundColor: c.danger + 'cc',
          borderRadius: 3,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, grid: { color: c.grid + '60' }, ticks: { precision: 0 } },
      },
    },
  });
}

// Create cost by agent horizontal bar chart
function initAgentCostChart(canvasId, labels, values) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();
  return new Chart(el, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Cost (USD)',
        data: values,
        backgroundColor: c.accent + 'bb',
        borderRadius: 3,
        borderSkipped: false,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `$${Number(ctx.raw).toFixed(4)}` } },
      },
      scales: {
        x: {
          grid: { color: c.grid + '60' },
          ticks: { callback: (v) => `$${Number(v).toFixed(3)}` },
        },
        y: { grid: { display: false } },
      },
    },
  });
}

// Create token usage dual-line chart
function initTokenChart(canvasId, labels, inputData, outputData) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();
  return new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Input tokens',
          data: inputData,
          borderColor: c.info,
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
        },
        {
          label: 'Output tokens',
          data: outputData,
          borderColor: c.warning,
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } },
      scales: {
        x: { grid: { color: c.grid + '60' } },
        y: { grid: { color: c.grid + '60' }, ticks: { precision: 0 } },
      },
    },
  });
}

// Update an existing chart with new data (after HTMX swap via data attributes)
function updateChartFromDataAttributes() {
  const src = document.getElementById('chart-data-source');
  if (!src) return;

  const chartId = src.dataset.chartId;
  const chart = Chart.getChart(chartId);
  if (!chart) return;

  try {
    const labels = JSON.parse(src.dataset.labels || '[]');
    const datasets = JSON.parse(src.dataset.datasets || '[]');
    chart.data.labels = labels;
    chart.data.datasets.forEach((ds, i) => {
      if (datasets[i]) ds.data = datasets[i];
    });
    chart.update('none');
  } catch (e) {
    console.warn('Chart update failed', e);
  }
}

document.addEventListener('htmx:afterSettle', updateChartFromDataAttributes);

// Init all charts on page load
document.addEventListener('DOMContentLoaded', () => {
  if (typeof Chart === 'undefined') return;
  applyChartDefaults();

  // Re-apply defaults when theme toggles
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    setTimeout(applyChartDefaults, 50);
  });
});
