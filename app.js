(function () {
  "use strict";

  const GATE_USER = "danteengrassia";
  const GATE_TOKEN = "06dc05f6bd2ae96a590a2a338fd9ec86982f676897f7adb51dcef41fa266fb9e";
  const GATE_KEY = "fp_acceso_autorizado";
  const gateElement = document.getElementById("loginGate");

  async function sha256Hex(value) {
    const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  function storedToken() {
    try {
      return window.localStorage.getItem(GATE_KEY);
    } catch (storageError) {
      return null;
    }
  }

  function unlock() {
    document.body.classList.remove("auth-locked");
    if (gateElement && gateElement.parentNode) gateElement.parentNode.removeChild(gateElement);
    bootApp();
  }

  async function authorize(event) {
    event.preventDefault();
    const userField = document.getElementById("gateUser");
    const passField = document.getElementById("gatePass");
    const errorMessage = document.getElementById("gateError");
    let token = null;
    try {
      token = await sha256Hex(passField.value);
    } catch (digestError) {
      errorMessage.textContent = "El navegador no permite validar el acceso.";
      errorMessage.hidden = false;
      return;
    }
    if (userField.value.trim().toLowerCase() === GATE_USER && token === GATE_TOKEN) {
      try {
        window.localStorage.setItem(GATE_KEY, GATE_TOKEN);
      } catch (storageError) {
        window.sessionStorage.setItem(GATE_KEY, GATE_TOKEN);
      }
      unlock();
    } else {
      errorMessage.hidden = false;
      passField.value = "";
      passField.focus();
    }
  }

  function bootApp() {
  const DATA = window.PROVINCIAS_DATA;
  if (!DATA || !DATA.provinces) {
    document.body.innerHTML = '<div class="empty-state">No se encontraron datos consolidados.</div>';
    return;
  }

  const definitions = DATA.definitions;
  const definitionMap = Object.fromEntries(definitions.map((item) => [item.id, item]));
  const provinceIds = Object.keys(DATA.provinces);
  const state = {
    provinceId: provinceIds[0],
    period: DATA.provinces[provinceIds[0]].latest_period,
    view: "summary",
  };
  const charts = {};
  const palette = {
    teal: "#3b8681",
    tealDark: "#2c615d",
    blue: "#35618f",
    gold: "#cf9d43",
    red: "#c0392b",
    charcoal: "#232d4f",
    gray: "#9aa0ad",
    pale: "#d9dbe9",
    lavender: "#9284be",
  };

  const integerFormatter = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
  const decimalFormatter = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const percentFormatter = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const compactFormatter = new Intl.NumberFormat("es-AR", { notation: "compact", maximumFractionDigits: 1 });

  function periodIndex(period) {
    const match = /^(\d{4})Q([1-4])$/.exec(period || "");
    return match ? Number(match[1]) * 4 + Number(match[2]) - 1 : -1;
  }

  function periodFromIndex(index) {
    const year = Math.floor(index / 4);
    return `${year}Q${(index % 4) + 1}`;
  }

  function formatPeriod(period) {
    if (period === "ltm") return "LTM";
    const match = /^(\d{4})Q([1-4])$/.exec(period || "");
    if (match) return `${match[2]}T ${match[1]}`;
    const monthMatch = /^(\d{4})-(\d{2})$/.exec(period || "");
    if (monthMatch) {
      const monthNames = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
      return `${monthNames[Number(monthMatch[2]) - 1]} ${monthMatch[1]}`;
    }
    return period || "s/d";
  }

  function metricRecord(province, metricId, period) {
    const series = province.metrics[metricId] || [];
    return series.find((item) => item.period === period) || null;
  }

  function metricValue(province, metricId, period) {
    const record = metricRecord(province, metricId, period);
    return record && record.status === "ok" ? record.value : null;
  }

  function trendMetricValue(province, metricId, period) {
    const series = province.trends?.metrics?.[metricId] || [];
    const record = series.find((item) => item.period === period);
    return record && record.status === "ok" ? record.value : null;
  }

  function formatValue(value, unit, compact) {
    if (value === null || value === undefined || Number.isNaN(value)) return "s/d";
    if (unit === "percent") return `${decimalFormatter.format(value * 100)}%`;
    if (unit === "usd_millions") return `USD ${compact ? compactFormatter.format(value) : decimalFormatter.format(value)} M`;
    if (unit === "ars_millions") return `$ ${compact ? compactFormatter.format(value) : integerFormatter.format(value)} M`;
    return decimalFormatter.format(value);
  }

  function priorYearPeriod(period) {
    return periodFromIndex(periodIndex(period) - 4);
  }

  function changeText(province, metricId, period) {
    const current = metricValue(province, metricId, period);
    const previousPeriod = priorYearPeriod(period);
    const previous = metricValue(province, metricId, previousPeriod);
    if (current === null || previous === null) return "Sin comparación interanual";
    const definition = definitionMap[metricId];
    if (definition.unit === "percent") {
      const difference = (current - previous) * 100;
      const sign = difference > 0 ? "+" : "";
      return `${sign}${decimalFormatter.format(difference)} pp vs. ${formatPeriod(previousPeriod)}`;
    }
    if (Math.abs(previous) < 1e-9) return `vs. ${formatPeriod(previousPeriod)}: s/d`;
    const change = ((current / previous) - 1) * 100;
    const sign = change > 0 ? "+" : "";
    return `${sign}${decimalFormatter.format(change)}% vs. ${formatPeriod(previousPeriod)}`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderTabs() {
    const container = document.getElementById("provinceTabs");
    container.innerHTML = provinceIds.map((provinceId) => {
      const province = DATA.provinces[provinceId];
      const selected = provinceId === state.provinceId;
      return `<button class="province-tab" type="button" data-province="${provinceId}" role="tab" aria-selected="${selected}">${escapeHtml(province.name)}</button>`;
    }).join("");
    container.querySelectorAll("[data-province]").forEach((button) => {
      button.addEventListener("click", () => {
        state.provinceId = button.dataset.province;
        const province = DATA.provinces[state.provinceId];
        state.period = province.latest_period;
        if (state.view !== "summary") {
          switchView("summary");
        } else {
          render();
        }
      });
    });
  }

  function renderHeader(province) {
    document.getElementById("provinceTitle").textContent = province.name;
    document.getElementById("provinceEyebrow").textContent = `Provincia de ${province.name}`;
    document.getElementById("periodLabel").textContent = formatPeriod(state.period);
    document.getElementById("frequencyNote").textContent = province.trends?.latest_period
      ? `Series fiscales mensuales LTM hasta ${formatPeriod(province.trends.latest_period)} · servicio trimestral`
      : "Base devengado trimestral · flujos últimos 12 meses";
    const generated = new Date(DATA.metadata.generated_at);
    document.getElementById("updatedAt").textContent = `Datos regenerados ${generated.toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" })}`;
  }

  function renderKpis(province) {
    const kpis = [
      "balance_operativo_pct",
      "balance_primario_pct",
      "balance_financiero_pct",
      "deuda_pct_ingresos",
      "deuda_neta_pct_ingresos",
      "servicio_deuda_pct_ingresos_operativos",
    ];
    const labelOverrides = {
      balance_operativo_pct: "Balance operativo (% ing. totales)",
      balance_primario_pct: "Balance primario (% ing. totales)",
      balance_financiero_pct: "Balance financiero (% ing. totales)",
      deuda_pct_ingresos: "Deuda (% ing. totales)",
      deuda_neta_pct_ingresos: "Deuda neta (% ing. totales)",
    };
    document.getElementById("kpiGrid").innerHTML = kpis.map((metricId) => {
      const definition = definitionMap[metricId];
      const value = metricValue(province, metricId, state.period);
      const isBalance = metricId.startsWith("balance_");
      let className = isBalance ? (value !== null && value < 0 ? "balance-negative" : "balance-positive") : "debt-kpi";
      return `
        <article class="kpi-card ${className}" title="${escapeHtml(definition.description)}">
          <span class="kpi-label">${escapeHtml(labelOverrides[metricId] || definition.label)}</span>
          <strong class="kpi-value">${formatValue(value, definition.unit, false)}</strong>
          <span class="kpi-change">${escapeHtml(changeText(province, metricId, state.period))}</span>
        </article>`;
    }).join("");
  }

  function visiblePeriods(province, monthlyMaximum, quarterlyMaximum, useMonthlyTrend) {
    const trendPeriods = province.trends?.periods || [];
    if (useMonthlyTrend && trendPeriods.length) {
      const selectedMatch = /^(\d{4})Q([1-4])$/.exec(state.period);
      const quarterCutoff = selectedMatch ? `${selectedMatch[1]}-${String(Number(selectedMatch[2]) * 3).padStart(2, "0")}` : null;
      const cutoff = state.period === province.latest_period ? province.trends.latest_period : quarterCutoff;
      return trendPeriods.filter((period) => !cutoff || period <= cutoff).slice(-monthlyMaximum);
    }
    return province.periods
      .filter((period) => periodIndex(period) <= periodIndex(state.period))
      .slice(-(quarterlyMaximum || monthlyMaximum));
  }

  function destroyChart(id) {
    if (charts[id]) {
      charts[id].destroy();
      delete charts[id];
    }
  }

  function chartValue(value, unit) {
    if (unit === "percent") return `${decimalFormatter.format(value)}%`;
    if (unit === "usd") return `USD ${decimalFormatter.format(value)} M`;
    if (unit === "ars") return `$ ${integerFormatter.format(value)} M`;
    return decimalFormatter.format(value);
  }

  function baseLineOptions(unit, extraScales) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      animation: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 12,
            boxHeight: 2,
            usePointStyle: false,
            padding: 18,
            filter(item, data) {
              return !data.datasets[item.datasetIndex]?.hideFromLegend;
            },
          },
        },
        tooltip: {
          filter(context) {
            return !context.dataset.hideFromTooltip;
          },
          callbacks: {
            label(context) {
              const value = context.raw;
              if (value === null) return `${context.dataset.label}: s/d`;
              return `${context.dataset.label}: ${chartValue(value, context.dataset.chartUnit || unit)}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
        },
        y: {
          grid: { color: "#e0e0e0" },
          ticks: { callback: (value) => unit === "percent" ? `${value}%` : compactFormatter.format(value) },
        },
        ...(extraScales || {}),
      },
    };
  }

  function renderLineChart(canvasId, province, datasetSpecs, unit, maximumPeriods, optionsOverride) {
    destroyChart(canvasId);
    if (typeof Chart === "undefined") return;
    const useMonthlyTrend = Boolean(optionsOverride?.useMonthlyTrend && province.trends?.periods?.length);
    const periods = visiblePeriods(province, maximumPeriods, optionsOverride?.quarterlyMaximum || 32, useMonthlyTrend);
    const datasets = datasetSpecs.map((spec) => ({
      label: spec.label,
      data: periods.map((period) => {
        const value = spec.constant === undefined
          ? (useMonthlyTrend ? trendMetricValue(province, spec.id, period) : metricValue(province, spec.id, period))
          : spec.constant;
        return value === null ? null : (spec.unit === "percent" ? value * 100 : value);
      }),
      borderColor: spec.color,
      backgroundColor: spec.color,
      borderWidth: spec.width || 2,
      borderDash: spec.dash || [],
      pointRadius: 0,
      pointHoverRadius: 4,
      spanGaps: true,
      tension: spec.constant === undefined ? 0.18 : 0,
      yAxisID: spec.axis || "y",
      chartUnit: spec.unit || unit,
    }));
    const negativeAxes = new Set(
      datasets
        .filter((dataset) => dataset.data.some((value) => value !== null && value < 0))
        .map((dataset) => dataset.yAxisID),
    );
    negativeAxes.forEach((axis) => {
      datasets.push({
        label: "Cero",
        data: periods.map(() => 0),
        borderColor: palette.gray,
        backgroundColor: palette.gray,
        borderWidth: 1.5,
        borderDash: [4, 4],
        pointRadius: 0,
        pointHoverRadius: 0,
        spanGaps: true,
        tension: 0,
        yAxisID: axis,
        chartUnit: unit,
        hideFromLegend: true,
        hideFromTooltip: true,
      });
    });
    const options = baseLineOptions(unit, optionsOverride?.scales);
    charts[canvasId] = new Chart(document.getElementById(canvasId), {
      type: "line",
      data: { labels: periods.map(formatPeriod), datasets },
      options,
    });
  }

  function renderServiceChart(province) {
    const canvasId = "serviceChart";
    destroyChart(canvasId);
    if (typeof Chart === "undefined") return;
    const periods = visiblePeriods(province, 32, 32, false);
    const percentSeries = (metricId) => periods.map((period) => {
      const value = metricValue(province, metricId, period);
      return value === null ? null : value * 100;
    });
    charts[canvasId] = new Chart(document.getElementById(canvasId), {
      type: "bar",
      data: {
        labels: periods.map(formatPeriod),
        datasets: [
          {
            label: "Amortizaciones",
            data: percentSeries("amortizaciones_pct_ingresos_operativos"),
            backgroundColor: palette.gold,
            borderWidth: 0,
            borderRadius: 1,
            stack: "service",
          },
          {
            label: "Intereses",
            data: percentSeries("intereses_pct_ingresos_operativos"),
            backgroundColor: palette.blue,
            borderWidth: 0,
            borderRadius: 1,
            stack: "service",
          },
          {
            type: "line",
            label: "Límite 15% Ley de Disciplina Financiera",
            data: periods.map(() => 15),
            borderColor: palette.red,
            backgroundColor: palette.red,
            borderWidth: 2,
            borderDash: [6, 5],
            pointRadius: 0,
            pointHoverRadius: 0,
            tension: 0,
            stack: "limit",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } },
          tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${decimalFormatter.format(context.raw)}%` } },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
          y: { stacked: true, grid: { color: "#e0e0e0" }, ticks: { callback: (value) => `${value}%` } },
        },
      },
    });
  }

  function renderTrendCharts(province) {
    renderLineChart("balanceChart", province, [
      { id: "balance_operativo_pct", label: "Operativo", color: palette.teal, unit: "percent" },
      { id: "balance_primario_pct", label: "Primario", color: palette.blue, unit: "percent" },
      { id: "balance_financiero_pct", label: "Financiero", color: palette.charcoal, unit: "percent" },
    ], "percent", 96, { useMonthlyTrend: true, quarterlyMaximum: 32 });

    renderServiceChart(province);

    renderLineChart("debtEvolutionChart", province, [
      { id: "deuda_pct_ingresos", label: "Deuda bruta", color: palette.gold, unit: "percent", width: 3 },
      { id: "deuda_neta_pct_ingresos", label: "Deuda neta", color: palette.teal, unit: "percent", width: 3 },
    ], "percent", 96, { useMonthlyTrend: true, quarterlyMaximum: 32 });

    renderLineChart("capexChart", province, [
      { id: "capex_pct_gasto_primario", label: "CAPEX / gasto primario", color: palette.teal, unit: "percent", axis: "y" },
      { id: "capex_ltm_usd_m", label: "CAPEX LTM USD", color: palette.gold, unit: "usd", axis: "y1" },
    ], "percent", 96, {
      useMonthlyTrend: true,
      quarterlyMaximum: 32,
      scales: {
        y1: {
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { callback: (value) => `USD ${compactFormatter.format(value)}` },
        },
      },
    });

    renderLineChart("realCapexChart", province, [
      { id: "capex_ltm_real_ars_m", label: "CAPEX real LTM", color: palette.blue, unit: "ars", axis: "y", width: 3 },
      { id: "capex_pct_gasto_primario", label: "CAPEX / gasto primario", color: palette.teal, unit: "percent", axis: "y1" },
    ], "ars", 96, {
      useMonthlyTrend: true,
      quarterlyMaximum: 32,
      scales: {
        y: {
          grid: { color: "#e0e0e0" },
          ticks: { callback: (value) => `$ ${compactFormatter.format(value)} M` },
        },
        y1: {
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { callback: (value) => `${value}%` },
        },
      },
    });
  }

  function snapshotForPeriod(province) {
    return province.debt.snapshots[state.period] || null;
  }

  function renderCompositionCharts(province) {
    const snapshot = snapshotForPeriod(province);
    ["categoryChart", "currencyChart"].forEach(destroyChart);
    if (typeof Chart === "undefined" || !snapshot) return;

    const split = snapshot.categories_by_currency?.length
      ? snapshot.categories_by_currency
      : snapshot.categories.map((item) => ({ category: item.category, usd: null, ars: null, otras: item.value }));
    const buckets = [
      { key: "usd", label: "Pagadero en USD", color: palette.blue },
      { key: "ars", label: "Pagadero en ARS", color: palette.lavender },
      { key: "otras", label: "Otras monedas", color: palette.gray },
    ];
    charts.categoryChart = new Chart(document.getElementById("categoryChart"), {
      type: "bar",
      data: {
        labels: split.map((item) => item.category),
        datasets: buckets.map((bucket) => ({
          label: bucket.label,
          data: split.map((item) => item[bucket.key] || null),
          backgroundColor: bucket.color,
          borderWidth: 0,
          borderRadius: 2,
          stack: "stock",
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        animation: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, boxHeight: 2, padding: 14 } },
          tooltip: {
            filter: (context) => context.raw !== null && Math.abs(context.raw) > 1e-9,
            callbacks: { label: (context) => `${context.dataset.label}: $ ${integerFormatter.format(context.raw)} M` },
          },
        },
        scales: {
          x: { stacked: true, grid: { color: "#e0e0e0" }, ticks: { callback: (value) => compactFormatter.format(value) } },
          y: { stacked: true, grid: { display: false } },
        },
      },
    });

    const currencies = snapshot.currencies.filter((item) => item.value > 0);
    const extraCurrencyColors = [palette.gold, palette.charcoal, palette.gray, palette.pale];
    let extraColorIndex = 0;
    const currencyColor = (label) => {
      const normalized = label.toUpperCase();
      if (normalized.includes("USD")) return palette.blue;
      if (normalized.includes("ARS") || normalized.includes("PESO")) return palette.lavender;
      return extraCurrencyColors[extraColorIndex++ % extraCurrencyColors.length];
    };
    charts.currencyChart = new Chart(document.getElementById("currencyChart"), {
      type: "doughnut",
      data: {
        labels: currencies.map((item) => item.currency),
        datasets: [{
          data: currencies.map((item) => item.value),
          backgroundColor: currencies.map((item) => currencyColor(item.currency)),
          borderColor: "#ffffff",
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "58%",
        animation: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, padding: 14 } },
          tooltip: {
            callbacks: {
              label: (context) => `${context.label}: $ ${integerFormatter.format(context.raw)} M (${decimalFormatter.format((context.raw / snapshot.total_stock) * 100)}%)`,
            },
          },
        },
      },
    });
  }

  function latestSnapshot(province) {
    const periods = Object.keys(province.debt.snapshots);
    if (!periods.length) return null;
    const last = periods.reduce((a, b) => (periodIndex(b) > periodIndex(a) ? b : a));
    return province.debt.snapshots[last];
  }

  function debtStockFx(snapshot) {
    return snapshot && snapshot.stock_fx ? snapshot.stock_fx : null;
  }

  function debtSummaryRowHtml(label, value, fx) {
    const usd = value !== null && value !== undefined && fx ? value / fx : null;
    const signClass = value === null || value === undefined ? "" : value >= 0 ? "value-positive" : "value-negative";
    return `<tr><td>${escapeHtml(label)}</td><td class="numeric ${signClass}">${formatValue(value, "ars_millions", false)}</td><td class="numeric ${signClass}">${formatValue(usd, "usd_millions", false)}</td></tr>`;
  }

  function renderEvolutionSummary(province) {
    const periodLabel = document.getElementById("evoSummaryPeriod");
    const container = document.getElementById("evoSummaryRows");
    if (!periodLabel || !container) return;
    const snapshot = snapshotForPeriod(province) || latestSnapshot(province);
    if (!snapshot) {
      periodLabel.textContent = "";
      container.innerHTML = '<tr><td colspan="3" class="data-missing">Sin datos disponibles.</td></tr>';
      return;
    }
    periodLabel.textContent = formatPeriod(snapshot.period);
    const fx = debtStockFx(snapshot);
    container.innerHTML = [
      debtSummaryRowHtml("Deuda bruta total", snapshot.total_stock, fx),
      debtSummaryRowHtml("Depósitos totales", snapshot.deposits_total, fx),
      debtSummaryRowHtml("Deuda neta de depósitos BCRA", snapshot.net_debt, fx),
    ].join("");
  }

  function renderDebtTables(province) {
    const financialValue = (metricId) => metricValue(province, metricId, state.period);
    const financialRow = (metricId, className, labelOverride) => {
      const definition = definitionMap[metricId];
      const value = financialValue(metricId);
      const signClass = value === null ? "" : (value >= 0 ? "value-positive" : "value-negative");
      return `<tr class="${className || ""}"><td>${escapeHtml(labelOverride || definition.label)}</td><td class="numeric ${signClass}">${formatValue(value, definition.unit, false)}</td></tr>`;
    };
    document.getElementById("financialFlowRows").innerHTML = [
      financialRow("fuentes_resultado_financiero_usd_m", "financial-balance"),
      '<tr class="financial-group applications-group"><td colspan="2">Aplicaciones financieras</td></tr>',
      financialRow("fuentes_amort_total_usd_m", "financial-total"),
      financialRow("fuentes_amort_comercial_usd_m", "financial-detail"),
      financialRow("fuentes_amort_ooii_usd_m", "financial-detail"),
      financialRow("fuentes_amort_otras_usd_m", "financial-detail"),
      '<tr class="financial-group sources-group"><td colspan="2">Fuentes financieras</td></tr>',
      financialRow("fuentes_endeudamiento_total_usd_m", "financial-total"),
      financialRow("fuentes_endeudamiento_comercial_usd_m", "financial-detail"),
      financialRow("fuentes_endeudamiento_ooii_usd_m", "financial-detail"),
      financialRow("fuentes_endeudamiento_otros_usd_m", "financial-detail"),
      financialRow("fuentes_variacion_inversion_financiera_usd_m", "financial-cash"),
    ].join("");
  }

  function renderMetricTable(province) {
    const rows = [];
    const groupedDefinitions = new Map();
    definitions.forEach((definition) => {
      if (!groupedDefinitions.has(definition.section)) groupedDefinitions.set(definition.section, []);
      groupedDefinitions.get(definition.section).push(definition);
    });
    groupedDefinitions.forEach((sectionDefinitions, section) => {
      if (section === "Financiamiento") {
        const financingOrder = [
          "endeudamiento_total_usd_m",
          "emision_bonos_internacionales_usd_m",
          "borrowings_ooii_usd_m",
          "amortizacion_ooii_usd_m",
          "intereses_ooii_usd_m",
          "saldo_neto_endeudamiento_ooii_usd_m",
        ];
        sectionDefinitions.sort((first, second) => financingOrder.indexOf(first.id) - financingOrder.indexOf(second.id));
      }
      rows.push(`<tr class="section-row"><td colspan="3">${escapeHtml(section)}</td></tr>`);
      sectionDefinitions.forEach((definition) => {
        const value = metricValue(province, definition.id, state.period);
        rows.push(`
          <tr>
            <td><span class="metric-label">${escapeHtml(definition.label)}</span><span class="metric-description">${escapeHtml(definition.description)}</span></td>
            <td class="numeric ${value === null ? "data-missing" : ""}">${formatValue(value, definition.unit, false)}</td>
            <td class="numeric">${escapeHtml(changeText(province, definition.id, state.period))}</td>
          </tr>`);
      });
    });
    document.getElementById("metricRows").innerHTML = rows.join("");
  }

  // === COMPARATOR ===

  const comparatorState = {
    selectedProvinces: [...provinceIds],
    indicatorId: "",
    unit: "percent",
    startPeriod: "",
    endPeriod: "",
    frequency: "trimestral",
  };

  function getIndicatorOptions() {
    const unitFilters = {
      percent: (u) => u === "percent",
      ars_millions: (u) => u === "ars_millions" || u === "ars",
      usd_millions: (u) => u === "usd_millions" || u === "usd",
    };
    const matcher = unitFilters[comparatorState.unit] || (() => false);
    return definitions.filter((d) => matcher(d.unit));
  }

  function isMensualAvailable() {
    return comparatorState.selectedProvinces.every((id) => {
      const p = DATA.provinces[id];
      return p.trends && Array.isArray(p.trends.periods) && p.trends.periods.length > 0;
    });
  }

  function getComparatorPeriods() {
    const provinces = comparatorState.selectedProvinces;
    const freq = comparatorState.frequency;

    if (freq === "mensual") {
      const all = new Set();
      provinces.forEach((id) => {
        (DATA.provinces[id].trends?.periods || []).forEach((p) => all.add(p));
      });
      return [...all].sort();
    }

    const all = new Set();
    provinces.forEach((id) => {
      (DATA.provinces[id].periods || []).forEach((p) => all.add(p));
    });

    if (freq === "anual") {
      const q4 = [...all].filter((p) => p.endsWith("Q4")).sort();
      if (provinces.some((id) => DATA.provinces[id].trends?.latest_period)) {
        q4.push("ltm");
      }
      return q4;
    }

    return [...all].sort();
  }

  function populateComparatorControls() {
    const indicatorSelect = document.getElementById("comparatorIndicator");
    const options = getIndicatorOptions();
    const grouped = new Map();
    options.forEach((d) => {
      if (!grouped.has(d.section)) grouped.set(d.section, []);
      grouped.get(d.section).push(d);
    });
    let optHtml = "";
    grouped.forEach((defs, section) => {
      optHtml += `<optgroup label="${escapeHtml(section)}">`;
      defs.forEach((d) => {
        const sel = d.id === comparatorState.indicatorId ? " selected" : "";
        optHtml += `<option value="${d.id}"${sel}>${escapeHtml(d.label)}</option>`;
      });
      optHtml += "</optgroup>";
    });
    indicatorSelect.innerHTML = optHtml;
    if (!comparatorState.indicatorId && options.length) {
      comparatorState.indicatorId = options[0].id;
      indicatorSelect.value = comparatorState.indicatorId;
    }

    const provSelect = document.getElementById("comparatorProvinces");
    provSelect.innerHTML = provinceIds.map((id) => {
      const sel = comparatorState.selectedProvinces.includes(id) ? " selected" : "";
      return `<option value="${id}"${sel}>${escapeHtml(DATA.provinces[id].name)}</option>`;
    }).join("");

    const freqSelect = document.getElementById("comparatorFreq");
    const mensualOpt = freqSelect.querySelector('option[value="mensual"]');
    const mensualOk = isMensualAvailable();
    mensualOpt.disabled = !mensualOk;
    if (comparatorState.frequency === "mensual" && !mensualOk) {
      comparatorState.frequency = "trimestral";
      freqSelect.value = "trimestral";
    }

    const periods = getComparatorPeriods();
    const optsHtml = periods.map((p) => `<option value="${p}">${formatPeriod(p)}</option>`).join("");
    document.getElementById("comparatorStart").innerHTML = optsHtml;
    document.getElementById("comparatorEnd").innerHTML = optsHtml;
    if (periods.length) {
      const defaultStart = (comparatorState.frequency !== "mensual" && periods.includes("2017Q4")) ? "2017Q4" : periods[0];
      if (!periods.includes(comparatorState.startPeriod)) comparatorState.startPeriod = defaultStart;
      if (!periods.includes(comparatorState.endPeriod)) comparatorState.endPeriod = periods[periods.length - 1];
      document.getElementById("comparatorStart").value = comparatorState.startPeriod;
      document.getElementById("comparatorEnd").value = comparatorState.endPeriod;
    }
  }

  function getComparisonData() {
    const indicator = comparatorState.indicatorId;
    const periods = getComparatorPeriods();
    const startIdx = periods.indexOf(comparatorState.startPeriod);
    const endIdx = periods.indexOf(comparatorState.endPeriod);
    const range = (startIdx >= 0 && endIdx >= 0) ? periods.slice(startIdx, Math.max(endIdx, startIdx) + 1) : periods;

    const series = {};
    comparatorState.selectedProvinces.forEach((id) => {
      const province = DATA.provinces[id];
      series[id] = range.map((period) => {
        if (period === "ltm") {
          const latestMonthly = province.trends?.latest_period;
          if (!latestMonthly) return null;
          const record = (province.trends?.metrics?.[indicator] || []).find((r) => r.period === latestMonthly);
          return record && record.status === "ok" ? record.value : null;
        }
        if (comparatorState.frequency === "mensual") {
          const record = (province.trends?.metrics?.[indicator] || []).find((r) => r.period === period);
          return record && record.status === "ok" ? record.value : null;
        }
        return metricValue(province, indicator, period);
      });
    });

    return { periods: range, series };
  }

  function renderComparisonChart() {
    destroyChart("comparisonChart");
    if (typeof Chart === "undefined") return;

    const { periods, series } = getComparisonData();
    const definition = definitionMap[comparatorState.indicatorId];
    if (!definition || !periods.length) return;

    const isPercent = definition.unit === "percent";
    const colors = [palette.blue, palette.lavender, palette.gold, palette.red, palette.charcoal];
    const datasets = comparatorState.selectedProvinces
      .filter((id) => series[id])
      .map((id, idx) => ({
        label: DATA.provinces[id].name,
        data: series[id].map((v) => (isPercent && v !== null) ? v * 100 : v),
        borderColor: colors[idx % colors.length],
        backgroundColor: colors[idx % colors.length] + "20",
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        tension: 0.15,
        spanGaps: true,
      }));

    const labels = periods.map(formatPeriod);

    charts.comparisonChart = new Chart(document.getElementById("comparisonChart"), {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, padding: 14 } },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${isPercent ? percentFormatter.format(ctx.raw) + "%" : chartValue(ctx.raw, definition.unit)}`,
            },
          },
        },
        scales: {
          x: { grid: { color: "#e0e0e0" }, ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 } },
          y: {
            grid: { color: "#e0e0e0" },
            ticks: {
              callback: (value) => {
                if (isPercent) return `${percentFormatter.format(value)}%`;
                if (definition.unit?.includes("usd")) return `USD ${compactFormatter.format(value)} M`;
                return `$ ${compactFormatter.format(value)} M`;
              },
            },
          },
        },
      },
    });
  }

  function renderComparisonTable() {
    const { periods, series } = getComparisonData();
    const definition = definitionMap[comparatorState.indicatorId];
    const selected = comparatorState.selectedProvinces.filter((id) => series[id]);
    const isPercent = definition && definition.unit === "percent";

    const thead = document.getElementById("comparisonHead");
    thead.innerHTML = `<tr><th>Periodo</th>${selected.map((id) => `<th>${escapeHtml(DATA.provinces[id].name)}</th>`).join("")}</tr>`;

    const tbody = document.getElementById("comparisonRows");
    if (!periods.length || !definition) {
      tbody.innerHTML = '<tr><td colspan="99" class="data-missing">Seleccioná indicador y provincias para comparar.</td></tr>';
      return;
    }
    tbody.innerHTML = periods.map((period) => {
      const idx = periods.indexOf(period);
      const cells = selected.map((id) => {
        const raw = series[id][idx];
        const value = (isPercent && raw !== null) ? raw * 100 : raw;
        const display = value === null || value === undefined ? "s/d" : (isPercent ? `${percentFormatter.format(value)}%` : formatValue(raw, definition.unit, false));
        return `<td class="numeric">${escapeHtml(display)}</td>`;
      }).join("");
      return `<tr><td>${formatPeriod(period)}</td>${cells}</tr>`;
    }).join("");
  }

  function renderComparator() {
    populateComparatorControls();
    renderComparisonChart();
    renderComparisonTable();
  }

  function switchView(view) {
    state.view = view;
    document.getElementById("summaryView").hidden = view !== "summary";
    document.getElementById("comparatorView").hidden = view !== "comparator";
    const toggle = document.getElementById("comparatorToggle");
    toggle.setAttribute("aria-current", view === "comparator" ? "page" : "false");
    if (view === "comparator") {
      renderComparator();
    } else {
      render();
    }
  }

  // === END COMPARATOR ===

  function render() {
    const province = DATA.provinces[state.provinceId];
    renderTabs();
    renderHeader(province);
    renderKpis(province);
    renderTrendCharts(province);
    renderCompositionCharts(province);
    renderDebtTables(province);
    renderEvolutionSummary(province);
    renderMetricTable(province);
    requestAnimationFrame(() => Object.values(charts).forEach((chart) => chart?.resize?.()));
  }

  if (typeof Chart !== "undefined") {
    Chart.defaults.font.family = "'Encode Sans', Arial, sans-serif";
    Chart.defaults.color = "#666666";
    Chart.defaults.borderColor = "#e0e0e0";
  } else {
    document.getElementById("chartError").hidden = false;
  }

  document.querySelectorAll(".view-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchView(tab.dataset.view));
  });

  document.getElementById("comparatorToggle").addEventListener("click", () => {
    switchView(state.view === "comparator" ? "summary" : "comparator");
  });

  document.getElementById("comparatorUnit").addEventListener("change", (e) => {
    comparatorState.unit = e.target.value;
    comparatorState.indicatorId = "";
    populateComparatorControls();
    renderComparisonChart();
    renderComparisonTable();
  });

  document.getElementById("comparatorIndicator").addEventListener("change", (e) => {
    comparatorState.indicatorId = e.target.value;
    renderComparisonChart();
    renderComparisonTable();
  });

  document.getElementById("comparatorFreq").addEventListener("change", (e) => {
    comparatorState.frequency = e.target.value;
    const periods = getComparatorPeriods();
    const defaultStart = (comparatorState.frequency !== "mensual" && periods.includes("2017Q4")) ? "2017Q4" : (periods[0] || "");
    comparatorState.startPeriod = defaultStart;
    comparatorState.endPeriod = periods[periods.length - 1] || "";
    populateComparatorControls();
    renderComparisonChart();
    renderComparisonTable();
  });

  document.getElementById("comparatorStart").addEventListener("change", (e) => {
    comparatorState.startPeriod = e.target.value;
    renderComparisonChart();
    renderComparisonTable();
  });

  document.getElementById("comparatorEnd").addEventListener("change", (e) => {
    comparatorState.endPeriod = e.target.value;
    renderComparisonChart();
    renderComparisonTable();
  });

  document.getElementById("comparatorProvinces").addEventListener("change", () => {
    const selected = [...document.getElementById("comparatorProvinces").selectedOptions].map((opt) => opt.value);
    if (selected.length > 0) comparatorState.selectedProvinces = selected;
    const freqSelect = document.getElementById("comparatorFreq");
    const mensualOpt = freqSelect.querySelector('option[value="mensual"]');
    mensualOpt.disabled = !isMensualAvailable();
    if (comparatorState.frequency === "mensual" && mensualOpt.disabled) {
      comparatorState.frequency = "trimestral";
      freqSelect.value = "trimestral";
    }
    const periods = getComparatorPeriods();
    const defaultStart = (comparatorState.frequency !== "mensual" && periods.includes("2017Q4")) ? "2017Q4" : (periods[0] || "");
    comparatorState.startPeriod = defaultStart;
    comparatorState.endPeriod = periods[periods.length - 1] || "";
    populateComparatorControls();
    renderComparisonChart();
    renderComparisonTable();
  });

  render();
  }

  if (storedToken() === GATE_TOKEN) {
    unlock();
  } else if (gateElement) {
    document.getElementById("loginForm").addEventListener("submit", (event) => {
      authorize(event);
    });
    document.getElementById("gateUser").focus();
  }
})();
