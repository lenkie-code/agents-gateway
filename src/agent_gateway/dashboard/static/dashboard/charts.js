/**
 * Agent Gateway Dashboard — Chart.js helpers
 * Polished, gradient-rich charts with smooth animations.
 */

// Read CSS custom property values for chart theming
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function getChartColors() {
  return {
    accent: cssVar('--color-accent') || '#6366f1',
    accentDark: cssVar('--color-accent-dark') || '#818cf8',
    success: cssVar('--color-success') || '#10b981',
    danger: cssVar('--color-danger') || '#ef4444',
    warning: cssVar('--color-warning') || '#f59e0b',
    info: cssVar('--color-info') || '#0ea5e9',
    grid: cssVar('--color-border') || '#e2e8f0',
    text: cssVar('--color-text-secondary') || '#64748b',
    textTertiary: cssVar('--color-text-tertiary') || '#94a3b8',
    surface: cssVar('--color-surface') || '#ffffff',
    bg: cssVar('--color-bg') || '#f8fafc',
  };
}

function isDark() {
  return document.documentElement.classList.contains('dark') ||
    (!document.documentElement.classList.contains('light') &&
     window.matchMedia('(prefers-color-scheme: dark)').matches);
}

// Apply theme-aware Chart.js defaults
function applyChartDefaults() {
  const c = getChartColors();
  const dark = isDark();
  Chart.defaults.color = c.text;
  Chart.defaults.borderColor = 'transparent';
  Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.font.weight = 500;
  Chart.defaults.animation = {
    duration: 700,
    easing: 'easeOutQuart',
  };
  Chart.defaults.plugins.tooltip.backgroundColor = dark ? '#1e293b' : '#0f172a';
  Chart.defaults.plugins.tooltip.titleColor = '#f8fafc';
  Chart.defaults.plugins.tooltip.bodyColor = '#cbd5e1';
  Chart.defaults.plugins.tooltip.borderColor = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.padding = { top: 8, bottom: 8, left: 12, right: 12 };
  Chart.defaults.plugins.tooltip.displayColors = true;
  Chart.defaults.plugins.tooltip.boxPadding = 4;
  Chart.defaults.plugins.tooltip.titleFont = { size: 11, weight: 600 };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 12, weight: 500 };
  Chart.defaults.plugins.tooltip.caretSize = 5;
}

// Helper: create a gradient fill from color
function makeGradient(ctx, color, opacity1, opacity2) {
  const gradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
  gradient.addColorStop(0, hexToRgba(color, opacity1));
  gradient.addColorStop(1, hexToRgba(color, opacity2));
  return gradient;
}

function hexToRgba(hex, alpha) {
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Shared scale config
function makeScales(c, opts = {}) {
  const dark = isDark();
  return {
    x: {
      grid: {
        display: opts.xGrid !== false,
        color: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
        drawBorder: false,
      },
      border: { display: false },
      ticks: {
        color: c.textTertiary,
        font: { size: 10 },
        maxRotation: 0,
        ...(opts.xTicks || {}),
      },
      ...(opts.xExtra || {}),
    },
    y: {
      grid: {
        color: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
        drawBorder: false,
      },
      border: { display: false },
      ticks: {
        color: c.textTertiary,
        font: { size: 10 },
        padding: 8,
        ...(opts.yTicks || {}),
      },
      ...(opts.yExtra || {}),
    },
  };
}

// Create cost over time — area chart with gradient
function initCostChart(canvasId, labels, values) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();
  const ctx = el.getContext('2d');

  return new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Cost (USD)',
        data: values,
        borderColor: c.accent,
        backgroundColor: makeGradient(ctx, c.accent, 0.18, 0.01),
        borderWidth: 2.5,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2.5,
        pointHoverBorderColor: c.accent,
        pointHoverBackgroundColor: c.surface,
        fill: true,
        tension: 0.4,
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
            label: (ctx) => `  $${Number(ctx.raw).toFixed(4)}`,
          },
        },
      },
      scales: makeScales(c, {
        yTicks: { callback: (v) => `$${Number(v).toFixed(3)}` },
      }),
    },
  });
}

// Create executions stacked bar chart — rounded bars with subtle gradients
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
          backgroundColor: hexToRgba(c.success, 0.75),
          hoverBackgroundColor: c.success,
          borderRadius: { topLeft: 4, topRight: 4, bottomLeft: 4, bottomRight: 4 },
          borderSkipped: false,
          barPercentage: 0.65,
          categoryPercentage: 0.7,
        },
        {
          label: 'Failed',
          data: failedData,
          backgroundColor: hexToRgba(c.danger, 0.7),
          hoverBackgroundColor: c.danger,
          borderRadius: { topLeft: 4, topRight: 4, bottomLeft: 4, bottomRight: 4 },
          borderSkipped: false,
          barPercentage: 0.65,
          categoryPercentage: 0.7,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 8,
            boxHeight: 8,
            borderRadius: 2,
            useBorderRadius: true,
            padding: 16,
            font: { size: 11, weight: 500 },
          },
        },
      },
      scales: makeScales(c, {
        xGrid: false,
        xExtra: { stacked: true },
        yExtra: { stacked: true },
        yTicks: { precision: 0 },
      }),
    },
  });
}

// Create cost by agent — horizontal bar chart with colored bars
function initAgentCostChart(canvasId, labels, values) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();

  // Generate distinct colours for each agent
  const palette = [c.accent, c.info, c.success, c.warning, c.danger, '#8b5cf6', '#ec4899', '#14b8a6'];
  const bgColors = values.map((_, i) => hexToRgba(palette[i % palette.length], 0.7));
  const hoverColors = values.map((_, i) => palette[i % palette.length]);

  return new Chart(el, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Cost (USD)',
        data: values,
        backgroundColor: bgColors,
        hoverBackgroundColor: hoverColors,
        borderRadius: 6,
        borderSkipped: false,
        barPercentage: 0.6,
        categoryPercentage: 0.8,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `  $${Number(ctx.raw).toFixed(4)}`,
          },
        },
      },
      scales: makeScales(c, {
        xGrid: false,
        xTicks: { callback: (v) => `$${Number(v).toFixed(3)}` },
        yTicks: { font: { size: 11, weight: 500 } },
      }),
    },
  });
}

// Create token usage — dual-area chart with gradients
function initTokenChart(canvasId, labels, inputData, outputData) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  const c = getChartColors();
  const ctx = el.getContext('2d');

  return new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Input tokens',
          data: inputData,
          borderColor: c.info,
          backgroundColor: makeGradient(ctx, c.info, 0.15, 0.01),
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: c.info,
          pointHoverBackgroundColor: c.surface,
          fill: true,
          tension: 0.4,
          order: 2,
        },
        {
          label: 'Output tokens',
          data: outputData,
          borderColor: c.warning,
          backgroundColor: makeGradient(ctx, c.warning, 0.12, 0.01),
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: c.warning,
          pointHoverBackgroundColor: c.surface,
          fill: true,
          tension: 0.4,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 8,
            boxHeight: 8,
            borderRadius: 2,
            useBorderRadius: true,
            padding: 16,
            font: { size: 11, weight: 500 },
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `  ${ctx.dataset.label}: ${Number(ctx.raw).toLocaleString()}`,
          },
        },
      },
      scales: makeScales(c, {
        yTicks: {
          precision: 0,
          callback: (v) => {
            if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
            if (v >= 1000) return (v / 1000).toFixed(0) + 'k';
            return v;
          },
        },
      }),
    },
  });
}

// Init all charts on page load
document.addEventListener('DOMContentLoaded', () => {
  if (typeof Chart === 'undefined') return;
  applyChartDefaults();

  // Re-apply defaults when theme toggles
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    setTimeout(applyChartDefaults, 50);
  });
});
