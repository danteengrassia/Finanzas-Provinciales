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
  };
  const charts = {};
  const palette = {
    teal: "#167c77",
    tealDark: "#0d5d59",
    blue: "#3f708e",
    gold: "#bd8b2e",
    red: "#b64c3f",
    charcoal: "#2e3a38",
    gray: "#87928e",
    pale: "#d9e2de",
  };

  const integerFormatter = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
  const decimalFormatter = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
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
        state.period = province.periods.includes(state.period) ? state.period : province.latest_period;
        render();
      });
    });
  }

  function renderPeriodSelect() {
    const province = DATA.provinces[state.provinceId];
    const select = document.getElementById("periodSelect");
    select.innerHTML = [...province.periods]
      .reverse()
      .map((period) => `<option value="${period}"${period === state.period ? " selected" : ""}>${formatPeriod(period)}</option>`)
      .join("");
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
    document.getElementById("kpiGrid").innerHTML = kpis.map((metricId) => {
      const definition = definitionMap[metricId];
      const value = metricValue(province, metricId, state.period);
      const isBalance = metricId.startsWith("balance_");
      let className = isBalance ? (value !== null && value < 0 ? "balance-negative" : "balance-positive") : "debt-kpi";
      return `
        <article class="kpi-card ${className}" title="${escapeHtml(definition.description)}">
          <span class="kpi-label">${escapeHtml(definition.label)}</span>
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
          grid: { color: "#e5eae7" },
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
          y: { stacked: true, grid: { color: "#e5eae7" }, ticks: { callback: (value) => `${value}%` } },
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
          grid: { color: "#e5eae7" },
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

    const categories = snapshot.categories.filter((item) => item.value > 0);
    charts.categoryChart = new Chart(document.getElementById("categoryChart"), {
      type: "bar",
      data: {
        labels: categories.map((item) => item.category),
        datasets: [{
          data: categories.map((item) => item.value),
          backgroundColor: [palette.teal, palette.gold, palette.blue, palette.charcoal, palette.red, palette.gray],
          borderWidth: 0,
          borderRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (context) => `$ ${integerFormatter.format(context.raw)} M` } },
        },
        scales: {
          x: { grid: { color: "#e5eae7" }, ticks: { callback: (value) => compactFormatter.format(value) } },
          y: { grid: { display: false } },
        },
      },
    });

    const currencies = snapshot.currencies.filter((item) => item.value > 0);
    charts.currencyChart = new Chart(document.getElementById("currencyChart"), {
      type: "doughnut",
      data: {
        labels: currencies.map((item) => item.currency),
        datasets: [{
          data: currencies.map((item) => item.value),
          backgroundColor: [palette.teal, palette.gold, palette.blue, palette.red, palette.charcoal, palette.gray, palette.pale],
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
          tooltip: { callbacks: { label: (context) => `${context.label}: $ ${integerFormatter.format(context.raw)} M` } },
        },
      },
    });
  }

  function renderDebtTables(province) {
    const snapshot = snapshotForPeriod(province);
    const categoryBody = document.getElementById("debtCategoryRows");
    const currencyBody = document.getElementById("currencyRows");
    if (!snapshot) {
      categoryBody.innerHTML = '<tr><td colspan="3" class="data-missing">Sin datos para este cierre.</td></tr>';
      currencyBody.innerHTML = '<tr><td colspan="3" class="data-missing">Sin datos para este cierre.</td></tr>';
    } else {
      const total = snapshot.total_stock;
      categoryBody.innerHTML = snapshot.categories
        .filter((item) => item.value > 0)
        .map((item) => `<tr><td>${escapeHtml(item.category)}</td><td class="numeric">${formatValue(item.value, "ars_millions", false)}</td><td class="numeric">${total ? decimalFormatter.format((item.value / total) * 100) : "s/d"}%</td></tr>`)
        .join("");
      currencyBody.innerHTML = snapshot.currencies
        .filter((item) => item.value > 0)
        .map((item) => `<tr><td>${escapeHtml(item.currency)}</td><td class="numeric">${formatValue(item.value, "ars_millions", false)}</td><td class="numeric">${total ? decimalFormatter.format((item.value / total) * 100) : "s/d"}%</td></tr>`)
        .join("");
    }

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

    const commercialContainer = document.getElementById("commercialDebtContent");
    if (!snapshot || !snapshot.commercial_details.length) {
      commercialContainer.innerHTML = '<div class="empty-state">No hay una serie separada de deuda flotante y comercial para este cierre.</div>';
      return;
    }
    const total = snapshot.floating_total;
    commercialContainer.innerHTML = `
      <table>
        <thead><tr><th>Concepto</th><th>Stock</th><th>% total</th></tr></thead>
        <tbody>
          ${snapshot.commercial_details.map((item) => `<tr><td>${escapeHtml(item.item)}</td><td class="numeric">${formatValue(item.value, "ars_millions", false)}</td><td class="numeric">${total ? decimalFormatter.format((item.value / total) * 100) : "s/d"}%</td></tr>`).join("")}
          <tr><td><strong>Total deuda flotante</strong></td><td class="numeric"><strong>${formatValue(total, "ars_millions", false)}</strong></td><td class="numeric"><strong>100,0%</strong></td></tr>
        </tbody>
      </table>`;
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

  function render() {
    const province = DATA.provinces[state.provinceId];
    renderTabs();
    renderPeriodSelect();
    renderHeader(province);
    renderKpis(province);
    renderTrendCharts(province);
    renderCompositionCharts(province);
    renderDebtTables(province);
    renderMetricTable(province);
  }

  document.getElementById("periodSelect").addEventListener("change", (event) => {
    state.period = event.target.value;
    render();
  });

  if (typeof Chart !== "undefined") {
    Chart.defaults.font.family = "Arial, sans-serif";
    Chart.defaults.color = "#66716e";
    Chart.defaults.borderColor = "#d5dcd8";
  } else {
    document.getElementById("chartError").hidden = false;
  }

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
