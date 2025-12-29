const API_BASE = window.location.origin;

const elements = {
  statusPill: document.getElementById("status-pill"),
  dataRoot: document.getElementById("data-root"),
  refreshHealth: document.getElementById("refresh-health"),
  universe: document.getElementById("universe"),
  target: document.getElementById("target"),
  horizon: document.getElementById("horizon"),
  method: document.getElementById("method"),
  dateFrom: document.getElementById("date-from"),
  dateTo: document.getElementById("date-to"),
  neutralize: document.getElementById("neutralize"),
  regimes: document.getElementById("regimes"),
  rollingWindow: document.getElementById("rolling-window"),
  runButton: document.getElementById("run-analysis"),
  clearButton: document.getElementById("clear-results"),
  runHint: document.getElementById("run-hint"),
  powerMeta: document.getElementById("power-meta"),
  resultsCount: document.getElementById("results-count"),
  resultsMeta: document.getElementById("results-meta"),
  resultsFilter: document.getElementById("results-filter"),
  resultsHead: document.getElementById("results-head"),
  resultsBody: document.getElementById("results-body"),
  resultsEmpty: document.getElementById("results-empty"),
  detailTitle: document.getElementById("detail-title"),
  detailMeta: document.getElementById("detail-meta"),
  detailStats: document.getElementById("detail-stats"),
  icChart: document.getElementById("ic-chart"),
  icEmpty: document.getElementById("ic-empty"),
  decileChart: document.getElementById("decile-chart"),
  decileEmpty: document.getElementById("decile-empty"),
};

const state = {
  results: [],
  filteredResults: [],
  resultMap: new Map(),
  activeFeature: null,
  sortKey: "ic_ir",
  sortDir: "desc",
  icChart: null,
  icSeries: null,
  icRollingSeries: null,
  decileChart: null,
  decileSeries: null,
  decileRollingSeries: null,
  detailRequestId: 0,
};

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return Number(value).toFixed(digits);
}

function formatCount(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return Math.round(Number(value)).toString();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (err) {
      payload = null;
    }
  }
  if (!response.ok) {
    const message = payload?.error || response.statusText || "Request failed";
    throw new Error(message);
  }
  return payload;
}

function setStatus(message, isError = false) {
  elements.powerMeta.textContent = message;
  if (isError) {
    elements.powerMeta.style.color = "#f97316";
  } else {
    elements.powerMeta.style.color = "";
  }
}

function setResultsEmpty(isEmpty, message) {
  if (isEmpty) {
    elements.resultsEmpty.textContent = message || "Run analysis to see results.";
    elements.resultsEmpty.style.display = "";
  } else {
    elements.resultsEmpty.style.display = "none";
  }
}

function parseListInput(value) {
  if (!value) {
    return null;
  }
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

function buildBasePayload() {
  const payload = {
    universe: elements.universe.value?.trim() || "all",
    target: elements.target.value?.trim() || "ret_cc",
    horizon_days: Number(elements.horizon.value || 1),
    date_from: elements.dateFrom.value,
    date_to: elements.dateTo.value,
    method: elements.method.value || "spearman",
  };
  const neutralize = parseListInput(elements.neutralize.value || "");
  if (neutralize) {
    payload.neutralize = neutralize;
  }
  const regimes = parseListInput(elements.regimes.value || "");
  if (regimes) {
    payload.regimes = regimes;
  }
  return payload;
}

async function loadSummary() {
  const dateFrom = elements.dateFrom.value;
  const dateTo = elements.dateTo.value;
  if (!dateFrom || !dateTo) {
    setStatus("Date range is required.", true);
    return;
  }

  const payload = buildBasePayload();
  elements.runButton.disabled = true;
  setStatus("Loading feature power summary...");
  try {
    const response = await fetchJson(`${API_BASE}/feature_power_summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.results = response?.results || [];
    state.resultMap = new Map(
      state.results.map((result) => [result.feature, result])
    );
    state.filteredResults = [];
    state.activeFeature = null;
    setStatus(
      `Loaded ${state.results.length} feature${
        state.results.length === 1 ? "" : "s"
      }.`
    );
    applyResultsFilter();
  } catch (err) {
    setStatus(err.message || "Failed to load feature power summary.", true);
    state.results = [];
    state.filteredResults = [];
    state.resultMap = new Map();
    state.activeFeature = null;
    renderResultsTable();
    renderFeatureDetail(null, null);
  } finally {
    elements.runButton.disabled = false;
  }
}

function clearResults() {
  state.results = [];
  state.filteredResults = [];
  state.resultMap = new Map();
  state.activeFeature = null;
  setStatus("Results cleared.");
  renderResultsTable();
  renderFeatureDetail(null, null);
}

function sortResults(results) {
  const key = state.sortKey;
  const direction = state.sortDir === "desc" ? -1 : 1;
  const sorted = [...results];
  sorted.sort((a, b) => {
    if (key === "feature") {
      const nameA = (a.feature || "").toLowerCase();
      const nameB = (b.feature || "").toLowerCase();
      if (nameA < nameB) {
        return -1 * direction;
      }
      if (nameA > nameB) {
        return 1 * direction;
      }
      return 0;
    }
    const valueA = a[key];
    const valueB = b[key];
    if (valueA === null || valueA === undefined) {
      return 1;
    }
    if (valueB === null || valueB === undefined) {
      return -1;
    }
    if (valueA === valueB) {
      return 0;
    }
    return valueA > valueB ? direction : -direction;
  });
  return sorted;
}

function updateSortIndicators() {
  const buttons = elements.resultsHead.querySelectorAll(".sort-button");
  buttons.forEach((button) => {
    const indicator = button.querySelector(".sort-indicator");
    if (button.dataset.key === state.sortKey) {
      button.classList.add("active");
      if (indicator) {
        indicator.textContent = state.sortDir === "asc" ? "^" : "v";
      }
    } else {
      button.classList.remove("active");
      if (indicator) {
        indicator.textContent = "";
      }
    }
  });
}

function applyResultsFilter() {
  const query = elements.resultsFilter.value?.trim().toLowerCase();
  if (!query) {
    state.filteredResults = sortResults(state.results);
  } else {
    const filtered = state.results.filter((result) =>
      result.feature.toLowerCase().includes(query)
    );
    state.filteredResults = sortResults(filtered);
  }
  renderResultsTable();
}

function renderResultsTable() {
  elements.resultsBody.innerHTML = "";
  updateSortIndicators();
  if (!state.filteredResults.length) {
    setResultsEmpty(true, state.results.length ? "No matches found." : null);
    elements.resultsCount.textContent = "0 features";
    elements.resultsMeta.textContent = "No results.";
    return;
  }

  setResultsEmpty(false);
  elements.resultsCount.textContent = `${state.filteredResults.length} feature${
    state.filteredResults.length === 1 ? "" : "s"
  }`;
  elements.resultsMeta.textContent = `Showing ${state.filteredResults.length} of ${
    state.results.length
  }`;

  let shouldLoadDetail = false;
  if (!state.activeFeature || !state.resultMap.has(state.activeFeature)) {
    state.activeFeature = state.filteredResults[0]?.feature || null;
    shouldLoadDetail = Boolean(state.activeFeature);
  }

  const fragment = document.createDocumentFragment();
  state.filteredResults.forEach((result) => {
    const row = document.createElement("tr");
    row.dataset.feature = result.feature;
    if (result.feature === state.activeFeature) {
      row.classList.add("active");
    }

    const cells = [
      { value: result.feature, className: "" },
      { value: formatCount(result.n_obs), className: "num" },
      { value: formatNumber(result.ic_mean), className: "num" },
      { value: formatNumber(result.ic_std), className: "num" },
      { value: formatNumber(result.ic_ir), className: "num" },
      { value: formatNumber(result.t_stat), className: "num" },
      { value: formatNumber(result.decile_spread), className: "num" },
    ];
    cells.forEach((cell) => {
      const td = document.createElement("td");
      if (cell.className) {
        td.className = cell.className;
      }
      td.textContent = cell.value;
      row.appendChild(td);
    });
    fragment.appendChild(row);
  });
  elements.resultsBody.appendChild(fragment);

  if (shouldLoadDetail) {
    const summary = state.resultMap.get(state.activeFeature);
    renderFeatureDetail(summary, null);
    loadDetail(state.activeFeature, summary);
  } else if (state.activeFeature) {
    const summary = state.resultMap.get(state.activeFeature);
    renderFeatureDetail(summary, null);
  }
}

function createLineChart(container, accent) {
  if (!window.LightweightCharts) {
    return { chart: null, series: null, rollingSeries: null };
  }
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { color: "#0b0f14" },
      textColor: "#cbd5e1",
      fontFamily: '"Space Grotesk", sans-serif',
    },
    grid: {
      vertLines: { color: "#1b2a3a" },
      horzLines: { color: "#1b2a3a" },
    },
    timeScale: {
      borderColor: "#223247",
      timeVisible: true,
    },
    rightPriceScale: {
      borderColor: "#223247",
    },
    crosshair: {
      vertLine: { color: "#334155" },
      horzLine: { color: "#334155" },
    },
  });

  const series = chart.addSeries(LightweightCharts.LineSeries, {
    color: accent,
    lineWidth: 2,
  });
  const rollingSeries = chart.addSeries(LightweightCharts.LineSeries, {
    color: "#f59e0b",
    lineWidth: 2,
  });
  return { chart, series, rollingSeries };
}

function initCharts() {
  const ic = createLineChart(elements.icChart, "#38bdf8");
  state.icChart = ic.chart;
  state.icSeries = ic.series;
  state.icRollingSeries = ic.rollingSeries;

  const decile = createLineChart(elements.decileChart, "#38bdf8");
  state.decileChart = decile.chart;
  state.decileSeries = decile.series;
  state.decileRollingSeries = decile.rollingSeries;

  window.addEventListener("resize", () => {
    if (state.icChart) {
      state.icChart.applyOptions({
        width: elements.icChart.clientWidth,
        height: elements.icChart.clientHeight,
      });
    }
    if (state.decileChart) {
      state.decileChart.applyOptions({
        width: elements.decileChart.clientWidth,
        height: elements.decileChart.clientHeight,
      });
    }
  });
}

function normalizeSeries(series) {
  if (!Array.isArray(series)) {
    return [];
  }
  return series.map((point) => ({
    time: point.date,
    value: point.value === undefined ? null : point.value,
  }));
}

function computeRollingMean(series, window) {
  const values = series.map((point) => point.value);
  const result = [];
  const windowValues = [];
  const size = Math.max(Number(window) || 1, 1);
  series.forEach((point, idx) => {
    windowValues.push(values[idx]);
    if (windowValues.length > size) {
      windowValues.shift();
    }
    const valid = windowValues.filter((value) => value !== null && value !== undefined);
    let mean = null;
    if (valid.length) {
      mean = valid.reduce((sum, item) => sum + item, 0) / valid.length;
    }
    result.push({ time: point.time, value: mean });
  });
  return result;
}

function lastSeriesValue(series) {
  if (!Array.isArray(series)) {
    return null;
  }
  for (let i = series.length - 1; i >= 0; i -= 1) {
    const value = series[i]?.value;
    if (value !== null && value !== undefined && !Number.isNaN(value)) {
      return value;
    }
  }
  return null;
}

function renderFeatureDetail(summary, detail) {
  if (!summary && !detail) {
    elements.detailTitle.textContent = "Select a feature";
    elements.detailMeta.textContent = "--";
    elements.detailStats.innerHTML = "";
    renderSeries(state.icSeries, state.icRollingSeries, [], elements.icEmpty, state.icChart);
    renderSeries(
      state.decileSeries,
      state.decileRollingSeries,
      [],
      elements.decileEmpty,
      state.decileChart
    );
    return;
  }

  if (summary) {
    elements.detailTitle.textContent = summary.feature;
    elements.detailMeta.textContent = `Observations: ${formatCount(summary.n_obs)}`;
  } else if (detail) {
    elements.detailTitle.textContent = detail.feature;
    elements.detailMeta.textContent = "--";
  }

  const stats = [];
  if (summary) {
    stats.push(["IC mean", formatNumber(summary.ic_mean)]);
    stats.push(["IC std", formatNumber(summary.ic_std)]);
    stats.push(["IC IR", formatNumber(summary.ic_ir)]);
    stats.push(["t-stat", formatNumber(summary.t_stat)]);
    stats.push(["Decile spread", formatNumber(summary.decile_spread)]);
    stats.push(["N obs", formatCount(summary.n_obs)]);
  }

  if (detail?.rolling) {
    const latestMean = lastSeriesValue(detail.rolling.ic_mean);
    const latestStd = lastSeriesValue(detail.rolling.ic_std);
    const latestIr = lastSeriesValue(detail.rolling.ic_ir);
    const latestT = lastSeriesValue(detail.rolling.t_stat);
    stats.push(["Rolling IC mean", formatNumber(latestMean)]);
    stats.push(["Rolling IC std", formatNumber(latestStd)]);
    stats.push(["Rolling IC IR", formatNumber(latestIr)]);
    stats.push(["Rolling t-stat", formatNumber(latestT)]);
  }

  elements.detailStats.innerHTML = "";
  stats.forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "stat-item";
    const labelSpan = document.createElement("span");
    labelSpan.className = "stat-label";
    labelSpan.textContent = label;
    const valueSpan = document.createElement("span");
    valueSpan.className = "stat-value";
    valueSpan.textContent = value;
    row.appendChild(labelSpan);
    row.appendChild(valueSpan);
    elements.detailStats.appendChild(row);
  });

  if (!detail) {
    renderSeries(state.icSeries, state.icRollingSeries, [], elements.icEmpty, state.icChart);
    renderSeries(
      state.decileSeries,
      state.decileRollingSeries,
      [],
      elements.decileEmpty,
      state.decileChart
    );
    return;
  }

  const icSeries = normalizeSeries(detail.daily.ic || []);
  const icRolling = normalizeSeries(detail.rolling.ic_mean || []);
  renderSeries(
    state.icSeries,
    state.icRollingSeries,
    [icSeries, icRolling],
    elements.icEmpty,
    state.icChart
  );

  const decileDaily = normalizeSeries(detail.daily.decile_spread || []);
  const decileRolling = computeRollingMean(decileDaily, detail.params.rolling_window);
  renderSeries(
    state.decileSeries,
    state.decileRollingSeries,
    [decileDaily, decileRolling],
    elements.decileEmpty,
    state.decileChart
  );
}

function renderSeries(series, rollingSeries, data, emptyEl, chart) {
  if (!series || !rollingSeries) {
    return;
  }
  if (!data || !data.length || !data[0].length) {
    emptyEl.style.display = "";
    series.setData([]);
    rollingSeries.setData([]);
    return;
  }
  emptyEl.style.display = "none";
  series.setData(data[0]);
  rollingSeries.setData(data[1] || []);
  if (chart) {
    chart.timeScale().fitContent();
  }
}

async function loadDetail(feature, summary) {
  if (!feature) {
    return;
  }
  const payload = buildBasePayload();
  payload.feature = feature;
  payload.rolling_window = Number(elements.rollingWindow.value || 20);

  const requestId = ++state.detailRequestId;
  setStatus(`Loading ${feature} detail...`);
  try {
    const response = await fetchJson(`${API_BASE}/feature_power_detail`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (requestId !== state.detailRequestId) {
      return;
    }
    setStatus(`Loaded ${feature} detail.`);
    renderFeatureDetail(summary, response);
  } catch (err) {
    if (requestId !== state.detailRequestId) {
      return;
    }
    setStatus(err.message || "Failed to load feature detail.", true);
    renderFeatureDetail(summary, null);
  }
}

async function loadHealth() {
  try {
    const payload = await fetchJson(`${API_BASE}/health`);
    if (elements.statusPill) {
      elements.statusPill.textContent = "online";
      elements.statusPill.classList.add("online");
    }
    if (elements.dataRoot) {
      elements.dataRoot.textContent = `data root: ${payload.data_root}`;
    }
  } catch (err) {
    if (elements.statusPill) {
      elements.statusPill.textContent = "offline";
      elements.statusPill.classList.remove("online");
    }
    if (elements.dataRoot) {
      elements.dataRoot.textContent = "data root: --";
    }
  }
}

function handleResultsHeadClick(event) {
  const button = event.target.closest(".sort-button");
  if (!button || !button.dataset.key) {
    return;
  }
  const key = button.dataset.key;
  if (state.sortKey === key) {
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
  } else {
    state.sortKey = key;
    state.sortDir = "desc";
  }
  applyResultsFilter();
}

function handleResultsBodyClick(event) {
  const row = event.target.closest("tr");
  if (!row || !row.dataset.feature) {
    return;
  }
  const feature = row.dataset.feature;
  if (feature === state.activeFeature) {
    return;
  }
  state.activeFeature = feature;
  renderResultsTable();
  const summary = state.resultMap.get(feature);
  loadDetail(feature, summary);
}

function init() {
  elements.universe.value = elements.universe.value || "all";
  elements.target.value = elements.target.value || "open_open";
  elements.horizon.value = elements.horizon.value || "1";
  elements.method.value = elements.method.value || "spearman";
  elements.dateFrom.value = elements.dateFrom.value || "2025-01-01";
  elements.dateTo.value = elements.dateTo.value || "2025-12-31";
  elements.rollingWindow.value = elements.rollingWindow.value || "20";

  initCharts();
  loadHealth();
  loadSummary();

  elements.refreshHealth.addEventListener("click", loadHealth);
  elements.runButton.addEventListener("click", loadSummary);
  elements.clearButton.addEventListener("click", clearResults);
  elements.resultsFilter.addEventListener("input", applyResultsFilter);
  elements.resultsHead.addEventListener("click", handleResultsHeadClick);
  elements.resultsBody.addEventListener("click", handleResultsBodyClick);
  elements.rollingWindow.addEventListener("change", () => {
    if (state.activeFeature && state.resultMap.has(state.activeFeature)) {
      const summary = state.resultMap.get(state.activeFeature);
      loadDetail(state.activeFeature, summary);
    }
  });
}

init();
