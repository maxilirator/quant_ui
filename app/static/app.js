const API_BASE = (() => {
  const params = new URLSearchParams(window.location.search);
  const override = params.get("api");
  if (override) {
    return override.replace(/\/$/, "");
  }
  if (window.location.protocol === "file:") {
    return "http://127.0.0.1:8000";
  }
  return window.location.origin;
})();

const state = {
  chart: null,
  candleSeries: null,
  volumeSeries: null,
  featureSeries: new Map(),
  featureColors: new Map(),
  featureMarkers: new Map(),
  featureData: new Map(),
  featureStats: new Map(),
  featureSettings: {},
  featureSettingsSaveTimer: null,
  featureAdjustments: {},
  indexSeries: new Map(),
  indexColors: new Map(),
  indexes: [],
  filteredIndexes: [],
  indexFilterQuery: "",
  selectedIndexes: new Set(),
  indexSearchTimer: null,
  instrumentMeta: null,
  features: [],
  filteredFeatures: [],
  featureFilterQuery: "",
  tickers: [],
  tickerBounds: new Map(),
  barStats: null,
  selectedTicker: "",
  tickerFilterQuery: "",
  selectedFeatures: new Set(),
  loading: false,
  pendingLoad: false,
  pendingAutoLoad: false,
  autoLoadTimer: null,
  featureSearchTimer: null,
  tickerSearchTimer: null,
};

const palette = [
  "#38bdf8",
  "#f59e0b",
  "#34d399",
  "#f97316",
  "#60a5fa",
  "#f43f5e",
  "#22d3ee",
  "#a3e635",
  "#fb7185",
  "#eab308",
];

const elements = {
  appRoot: document.querySelector(".app"),
  statusPill: document.getElementById("status-pill"),
  dataRoot: document.getElementById("data-root"),
  refreshHealth: document.getElementById("refresh-health"),
  tickerDropdown: document.getElementById("ticker-dropdown"),
  tickerTrigger: document.getElementById("ticker-trigger"),
  tickerFilter: document.getElementById("ticker-filter"),
  tickerList: document.getElementById("ticker-list"),
  tickerMeta: document.getElementById("ticker-meta"),
  dateFrom: document.getElementById("date-from"),
  dateTo: document.getElementById("date-to"),
  range2025: document.getElementById("range-2025"),
  rangeLastDay: document.getElementById("range-last-day"),
  rangeLastWeek: document.getElementById("range-last-week"),
  rangeLastMonth: document.getElementById("range-last-month"),
  instrumentRange: document.getElementById("instrument-range"),
  instrumentRangeText: document.getElementById("instrument-range-text"),
  applyInstrumentRange: document.getElementById("apply-instrument-range"),
  featureFilter: document.getElementById("feature-filter"),
  featureTrigger: document.getElementById("feature-trigger"),
  featureSelected: document.getElementById("feature-selected"),
  featureList: document.getElementById("feature-list"),
  indexDropdown: document.getElementById("index-dropdown"),
  indexTrigger: document.getElementById("index-trigger"),
  indexFilter: document.getElementById("index-filter"),
  indexSelected: document.getElementById("index-selected"),
  indexList: document.getElementById("index-list"),
  clearIndexes: document.getElementById("clear-indexes"),
  featureControls: document.getElementById("feature-controls"),
  selectAll: document.getElementById("select-all"),
  clearFeatures: document.getElementById("clear-features"),
  chartOverlay: document.getElementById("chart-overlay"),
  featureCount: document.getElementById("feature-count"),
  activeRange: document.getElementById("active-range"),
  fitChart: document.getElementById("fit-chart"),
  missingRatios: document.getElementById("missing-ratios"),
  featureSources: document.getElementById("feature-sources"),
  calendarWarning: document.getElementById("calendar-warning"),
  calendarWarningText: document.getElementById("calendar-warning-text"),
  missingBarsText: document.getElementById("missing-bars-text"),
  nanRatioText: document.getElementById("nan-ratio-text"),
};

function showOverlay(message) {
  elements.chartOverlay.textContent = message;
  elements.chartOverlay.style.display = "grid";
}

function hideOverlay() {
  elements.chartOverlay.style.display = "none";
}

function apiUrl(path) {
  return new URL(path, API_BASE).toString();
}

async function fetchJson(url) {
  const response = await fetch(apiUrl(url));
  if (!response.ok) {
    let payload = {};
    try {
      payload = await response.json();
    } catch (error) {
      payload = {};
    }
    const message = payload.error || response.statusText;
    const details = payload.details ? ` (${JSON.stringify(payload.details)})` : "";
    throw new Error(`${message}${details}`);
  }
  return response.json();
}

function normalizeFeatureSettingsMap(features) {
  if (!features || typeof features !== "object") {
    return {};
  }
  const normalized = {};
  Object.entries(features).forEach(([name, entry]) => {
    const color =
      typeof entry === "string"
        ? entry
        : typeof entry?.color === "string"
          ? entry.color
          : null;
    if (!color) {
      return;
    }
    normalized[name] = { color };
  });
  return normalized;
}

async function loadFeatureSettings() {
  try {
    const payload = await fetchJson("/feature-settings");
    state.featureSettings = normalizeFeatureSettingsMap(payload.features || payload);
  } catch (error) {
    console.warn("Failed to load feature settings", error);
    state.featureSettings = {};
  }
}

function scheduleFeatureSettingsSave() {
  clearTimeout(state.featureSettingsSaveTimer);
  state.featureSettingsSaveTimer = setTimeout(() => {
    saveFeatureSettings();
  }, 400);
}

async function saveFeatureSettings() {
  const payload = { features: normalizeFeatureSettingsMap(state.featureSettings) };
  try {
    const response = await fetch(apiUrl("/feature-settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`Save failed: ${response.status}`);
    }
  } catch (error) {
    console.warn("Failed to save feature settings", error);
  }
}

function setStatus(online) {
  elements.statusPill.textContent = online ? "online" : "offline";
  elements.statusPill.classList.toggle("online", online);
}

function setWarning(message) {
  if (!message) {
    elements.calendarWarningText.textContent = "None";
    elements.calendarWarning.classList.remove("warning");
    return;
  }
  elements.calendarWarningText.textContent = message;
  elements.calendarWarning.classList.add("warning");
}

function normalizeDate(value) {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

function formatRange(start, end) {
  const startText = normalizeDate(start) || "--";
  const endText = normalizeDate(end) || "--";
  return `${startText} -- ${endText}`;
}

function formatNumber(value, digits = 4) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "--";
  }
  return number.toFixed(digits);
}

function coerceNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function isOutsideRange(start, end, from, to) {
  const fromText = normalizeDate(from);
  const toText = normalizeDate(to);
  if (!fromText || !toText) {
    return false;
  }
  const startText = normalizeDate(start);
  const endText = normalizeDate(end);
  if (startText && fromText < startText) {
    return true;
  }
  if (endText && toText > endText) {
    return true;
  }
  return false;
}

const FEATURE_LINE_WIDTH = 2;
const GAP_MARKER_SIZE = 0.5;

function makeGapMarker(time, color, position = "inBar") {
  return {
    time,
    position,
    shape: "circle",
    color,
    size: GAP_MARKER_SIZE,
  };
}

function buildGapMarkersFromSeries(points, color, position = "inBar") {
  const markers = [];
  let lastValid = null;
  let inGap = false;

  points.forEach((point) => {
    const hasValue = point.value !== null && point.value !== undefined;
    if (hasValue) {
      if (inGap && lastValid) {
        markers.push(makeGapMarker(lastValid.date, color, position));
        markers.push(makeGapMarker(point.date, color, position));
      }
      inGap = false;
      lastValid = point;
    } else if (lastValid) {
      inGap = true;
    }
  });

  return markers;
}


async function loadHealth() {
  try {
    const payload = await fetchJson("/health");
    setStatus(true);
    elements.dataRoot.textContent = `data root: ${payload.data_root}`;
  } catch (error) {
    setStatus(false);
    elements.dataRoot.textContent = "data root: --";
    setWarning(String(error.message || error));
  }
}

function updateTickerTrigger() {
  if (!elements.tickerTrigger) {
    return;
  }
  elements.tickerTrigger.textContent = state.selectedTicker
    ? `Ticker: ${state.selectedTicker}`
    : "Select ticker";
}

function updateTickerMeta() {
  if (!elements.tickerMeta) {
    return;
  }
  const sector = state.instrumentMeta?.sector || "--";
  const industry = state.instrumentMeta?.industry || "--";
  elements.tickerMeta.textContent = `Sector: ${sector || "--"} · Industry: ${industry || "--"}`;
}

function getFilteredTickers() {
  if (!state.tickerFilterQuery) {
    return state.tickers;
  }
  const needle = state.tickerFilterQuery.toLowerCase();
  return state.tickers.filter((item) => item.ticker.toLowerCase().includes(needle));
}

function renderTickerOptions(list = getFilteredTickers()) {
  if (!elements.tickerList) {
    return;
  }
  const currentFrom = elements.dateFrom?.value;
  const currentTo = elements.dateTo?.value;
  elements.tickerList.innerHTML = "";
  if (!list.length) {
    const empty = document.createElement("div");
    empty.textContent = "No tickers found.";
    empty.style.color = "#6a7c92";
    empty.style.padding = "10px";
    elements.tickerList.appendChild(empty);
    return;
  }
  list.forEach((item) => {
    const row = document.createElement("div");
    row.className = "ticker-row";
    row.dataset.ticker = item.ticker;

    if (item.ticker === state.selectedTicker) {
      row.classList.add("selected");
    }

    if (isOutsideRange(item.start, item.end, currentFrom, currentTo)) {
      row.classList.add("out-of-range");
    }

    const name = document.createElement("span");
    name.className = "ticker-name";
    name.textContent = item.ticker;

    const range = document.createElement("span");
    range.className = "ticker-range";
    range.textContent = formatRange(item.start, item.end);

    const action = document.createElement("button");
    action.type = "button";
    action.className = "ticker-action";
    action.textContent = "max";
    action.dataset.ticker = item.ticker;

    row.appendChild(name);
    row.appendChild(range);
    row.appendChild(action);
    elements.tickerList.appendChild(row);
  });
}

function setSelectedTicker(ticker, options = {}) {
  const { closeDropdown = true } = options;
  if (!ticker) {
    return;
  }
  state.selectedTicker = ticker;
  updateTickerTrigger();
  renderTickerOptions();
  loadInstrumentMeta(ticker);
  if (closeDropdown && elements.tickerDropdown?.hide) {
    elements.tickerDropdown.hide();
  }
}

async function loadTickers() {
  try {
    const payload = await fetchJson("/tickers");
    state.tickers = payload.tickers || [];
    state.tickerBounds = new Map();
    state.tickers.forEach((item) => {
      state.tickerBounds.set(item.ticker, { start: item.start, end: item.end });
    });
    if (state.tickers.length) {
      const hasSelected = state.tickers.some(
        (item) => item.ticker === state.selectedTicker
      );
      if (!hasSelected) {
        state.selectedTicker = state.tickers[0].ticker;
      }
    }
    updateTickerTrigger();
    renderTickerOptions();
    if (state.tickers.length) {
      loadInstrumentMeta(state.selectedTicker);
      scheduleLoad();
    }
  } catch (error) {
    setWarning(error.message || "Failed to load tickers");
  }
}

async function loadIndexes() {
  try {
    const payload = await fetchJson("/indexes");
    state.indexes = payload.indexes || [];
    state.filteredIndexes = state.indexes;
    state.indexFilterQuery = "";
    renderIndexList();
    renderSelectedIndexes();
  } catch (error) {
    setWarning(error.message || "Failed to load indexes");
    state.indexes = [];
    state.filteredIndexes = [];
    state.indexFilterQuery = "";
    renderIndexList();
    renderSelectedIndexes();
  }
}

async function loadInstrumentMeta(ticker) {
  if (!ticker) {
    state.instrumentMeta = null;
    updateTickerMeta();
    renderIndexList();
    return;
  }
  try {
    const url = new URL("/instrument-meta", API_BASE);
    url.searchParams.set("ticker", ticker);
    const payload = await fetchJson(url.toString());
    state.instrumentMeta = payload;
  } catch (error) {
    state.instrumentMeta = null;
  }
  updateTickerMeta();
  renderIndexList();
}

async function loadFeaturesList() {
  try {
    const url = new URL("/features", API_BASE);
    const payload = await fetchJson(url.toString());
    state.features = payload.features || [];
    state.filteredFeatures = state.features;
    state.featureFilterQuery = "";
    renderFeatureList();
    renderFeatureSources();
    renderSelectedFeatures();
  } catch (error) {
    setWarning(error.message || "Failed to load features");
    state.features = [];
    state.filteredFeatures = [];
    state.featureFilterQuery = "";
    renderFeatureList();
    renderFeatureSources();
    renderSelectedFeatures();
  }
}

function updateIndexTrigger() {
  if (!elements.indexTrigger) {
    return;
  }
  const count = state.selectedIndexes.size;
  elements.indexTrigger.textContent = `Indexes (${count})`;
}

function getFilteredIndexes() {
  if (!state.indexFilterQuery) {
    return state.indexes;
  }
  const needle = state.indexFilterQuery.toLowerCase();
  return state.indexes.filter((item) => item.label.toLowerCase().includes(needle));
}

function getIndexLabel(id) {
  const match = state.indexes.find((item) => item.id === id);
  if (!match) {
    return id;
  }
  return match.kind === "sector" ? `Sector · ${match.label}` : match.label;
}

function renderIndexList() {
  if (!elements.indexList) {
    return;
  }
  elements.indexList.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const list = state.indexFilterQuery ? state.filteredIndexes : state.indexes;
  if (!list.length) {
    const empty = document.createElement("div");
    empty.textContent = state.indexFilterQuery
      ? "No matching indexes."
      : "No indexes loaded.";
    empty.style.color = "#6a7c92";
    fragment.appendChild(empty);
    elements.indexList.appendChild(fragment);
    updateIndexTrigger();
    return;
  }

  const recommended = state.instrumentMeta?.sector
    ? `sector:${state.instrumentMeta.sector}`
    : null;

  list.forEach((item) => {
    const row = document.createElement("div");
    row.className = "index-list-item";
    if (recommended && item.id === recommended) {
      row.classList.add("recommended");
    }

    const checkbox = document.createElement("sl-checkbox");
    checkbox.setAttribute("data-id", item.id);
    checkbox.checked = state.selectedIndexes.has(item.id);
    checkbox.textContent = item.kind === "sector" ? `Sector · ${item.label}` : item.label;

    const range = document.createElement("span");
    range.className = "index-range";
    range.textContent = formatRange(item.start, item.end);

    row.appendChild(checkbox);
    row.appendChild(range);
    fragment.appendChild(row);
  });

  elements.indexList.appendChild(fragment);
  updateIndexTrigger();
}

function renderSelectedIndexes() {
  if (!elements.indexSelected) {
    return;
  }
  elements.indexSelected.innerHTML = "";
  if (!state.selectedIndexes.size) {
    const empty = document.createElement("div");
    empty.textContent = "No indexes selected.";
    empty.style.color = "#6a7c92";
    empty.style.fontSize = "0.75rem";
    elements.indexSelected.appendChild(empty);
    updateIndexTrigger();
    return;
  }

  state.selectedIndexes.forEach((id) => {
    const chip = document.createElement("div");
    chip.className = "index-chip";
    const label = document.createElement("span");
    label.textContent = getIndexLabel(id);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "x";
    remove.dataset.id = id;
    chip.appendChild(label);
    chip.appendChild(remove);
    elements.indexSelected.appendChild(chip);
  });
  updateIndexTrigger();
}

function filterIndexes(query) {
  state.indexFilterQuery = query;
  if (!query) {
    state.filteredIndexes = state.indexes;
    renderIndexList();
    return;
  }
  const needle = query.toLowerCase();
  state.filteredIndexes = state.indexes.filter((item) =>
    item.label.toLowerCase().includes(needle)
  );
  renderIndexList();
}

function renderFeatureList() {
  elements.featureList.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const list = state.featureFilterQuery ? state.filteredFeatures : state.features;
  if (!list.length) {
    const empty = document.createElement("div");
    empty.textContent = state.featureFilterQuery
      ? "No matching features."
      : "No features loaded.";
    empty.style.color = "#6a7c92";
    fragment.appendChild(empty);
  }
  list.forEach((feature) => {
    const checkbox = document.createElement("sl-checkbox");
    checkbox.setAttribute("data-name", feature.name);
    checkbox.checked = state.selectedFeatures.has(feature.name);
    checkbox.textContent = feature.name;
    fragment.appendChild(checkbox);
  });
  elements.featureList.appendChild(fragment);
  updateFeatureCount();
  renderSelectedFeatures();
}

function renderSelectedFeatures() {
  if (!elements.featureSelected) {
    return;
  }
  elements.featureSelected.innerHTML = "";
  if (!state.selectedFeatures.size) {
    const empty = document.createElement("div");
    empty.textContent = "No features selected.";
    empty.style.color = "#6a7c92";
    empty.style.fontSize = "0.75rem";
    elements.featureSelected.appendChild(empty);
    renderFeatureControls();
    return;
  }
  state.selectedFeatures.forEach((name) => {
    const chip = document.createElement("div");
    chip.className = "feature-chip";
    const label = document.createElement("span");
    label.textContent = name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "x";
    remove.dataset.name = name;
    chip.appendChild(label);
    chip.appendChild(remove);
    elements.featureSelected.appendChild(chip);
  });
  renderFeatureControls();
}

function renderFeatureSources() {
  const sources = new Map();
  state.features.forEach((feature) => {
    if (!sources.has(feature.source)) {
      sources.set(feature.source, 0);
    }
    sources.set(feature.source, sources.get(feature.source) + 1);
  });
  elements.featureSources.innerHTML = "";
  if (!sources.size) {
    const row = document.createElement("div");
    row.textContent = "None";
    elements.featureSources.appendChild(row);
    return;
  }
  sources.forEach((count, name) => {
    const row = document.createElement("div");
    row.textContent = `${name}: ${count}`;
    elements.featureSources.appendChild(row);
  });
}

function updateFeatureCount() {
  const count = state.selectedFeatures.size;
  elements.featureCount.textContent = `${count} overlay${count === 1 ? "" : "s"}`;
  if (elements.featureTrigger) {
    elements.featureTrigger.textContent = `Features (${count})`;
  }
}

function filterFeatures(query) {
  state.featureFilterQuery = query;
  if (!query) {
    state.filteredFeatures = state.features;
    renderFeatureList();
    return;
  }
  const needle = query.toLowerCase();
  state.filteredFeatures = state.features.filter((feature) =>
    feature.name.toLowerCase().includes(needle)
  );
  renderFeatureList();
}

function initChart() {
  const container = document.getElementById("chart");
  if (!window.LightweightCharts) {
    throw new Error("Lightweight Charts failed to load");
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
    leftPriceScale: {
      borderColor: "#223247",
      visible: true,
    },
    crosshair: {
      vertLine: { color: "#334155" },
      horzLine: { color: "#334155" },
    },
  });

  const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: "#22c55e",
    downColor: "#ef4444",
    borderVisible: false,
    wickUpColor: "#22c55e",
    wickDownColor: "#ef4444",
  });

  const volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
    priceScaleId: "vol",
    priceFormat: { type: "volume" },
    color: "rgba(56, 189, 248, 0.5)",
  });

  chart.priceScale("vol").applyOptions({
    scaleMargins: { top: 0.75, bottom: 0 },
    borderColor: "#223247",
    visible: false,
  });

  state.chart = chart;
  state.candleSeries = candleSeries;
  state.volumeSeries = volumeSeries;

  window.addEventListener("resize", () => {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  });
}

function clearFeatureSeries() {
  state.featureSeries.forEach((series) => {
    state.chart.removeSeries(series);
  });
  state.featureSeries.clear();
  state.featureMarkers.forEach((markers) => {
    if (markers?.detach) {
      markers.detach();
    }
  });
  state.featureMarkers.clear();
  state.featureData.clear();
  state.featureStats.clear();
}

function clearIndexSeries() {
  state.indexSeries.forEach((series) => {
    state.chart.removeSeries(series);
  });
  state.indexSeries.clear();
}

function getFeatureColor(name) {
  const savedColor = state.featureSettings?.[name]?.color;
  if (savedColor) {
    return savedColor;
  }
  if (state.featureColors.has(name)) {
    return state.featureColors.get(name);
  }
  const color = palette[state.featureColors.size % palette.length];
  state.featureColors.set(name, color);
  return color;
}

function getIndexColor(name) {
  if (state.indexColors.has(name)) {
    return state.indexColors.get(name);
  }
  const color = palette[state.indexColors.size % palette.length];
  state.indexColors.set(name, color);
  return color;
}

function getFeatureDefaults() {
  const barStats = state.barStats;
  if (barStats && Number.isFinite(barStats.min) && Number.isFinite(barStats.max)) {
    const span = Math.max(1, barStats.max - barStats.min);
    return {
      scale: span / 2,
      offset: (barStats.min + barStats.max) / 2,
    };
  }
  return { scale: 1, offset: 0 };
}

function getAdjustmentBucket() {
  const key = state.selectedTicker || "__default__";
  if (!state.featureAdjustments[key]) {
    state.featureAdjustments[key] = {};
  }
  return state.featureAdjustments[key];
}

function getFeatureAdjustments(name) {
  const bucket = getAdjustmentBucket();
  return bucket[name] || null;
}

function getFeatureSettings(name) {
  const defaults = getFeatureDefaults();
  const adjustments = getFeatureAdjustments(name) || {};
  return {
    color: getFeatureColor(name),
    scale: coerceNumber(adjustments.scale, defaults.scale),
    offset: coerceNumber(adjustments.offset, defaults.offset),
  };
}

function setFeatureSettings(name, updates) {
  const current = getFeatureSettings(name);
  let color = current.color;
  if (typeof updates.color === "string") {
    color = updates.color;
    state.featureSettings[name] = { color };
    scheduleFeatureSettingsSave();
  }
  const nextScale =
    updates.scale === undefined ? current.scale : coerceNumber(updates.scale, current.scale);
  const nextOffset =
    updates.offset === undefined ? current.offset : coerceNumber(updates.offset, current.offset);
  if (updates.scale !== undefined || updates.offset !== undefined) {
    const bucket = getAdjustmentBucket();
    bucket[name] = { scale: nextScale, offset: nextOffset };
  }
  return { color, scale: nextScale, offset: nextOffset };
}

function buildFeatureSeries(points) {
  const cleaned = points.map((point) => {
    const rawValue = point.value;
    const value =
      rawValue === null || rawValue === undefined ? null : Number(rawValue);
    return {
      date: point.date,
      value: value === null || !Number.isFinite(value) ? null : value,
    };
  });

  let first = null;
  let min = Infinity;
  let max = -Infinity;
  cleaned.forEach((point) => {
    if (point.value === null) {
      return;
    }
    if (first === null) {
      first = point.value;
    }
    min = Math.min(min, point.value);
    max = Math.max(max, point.value);
  });

  let maxAbs = 0;
  if (first !== null) {
    cleaned.forEach((point) => {
      if (point.value === null) {
        return;
      }
      maxAbs = Math.max(maxAbs, Math.abs(point.value - first));
    });
  }

  const denom = maxAbs || 1;
  const normalized = cleaned.map((point) => {
    if (point.value === null) {
      return { time: point.date };
    }
    return { time: point.date, value: (point.value - first) / denom };
  });

  const stats = {
    min: Number.isFinite(min) ? min : null,
    max: Number.isFinite(max) ? max : null,
    first,
    maxAbs: first === null ? null : maxAbs,
    span: Number.isFinite(min) && Number.isFinite(max) ? max - min : null,
  };

  return { cleaned, normalized, stats };
}

function applyFeatureSettings(name) {
  const series = state.featureSeries.get(name);
  const data = state.featureData.get(name);
  if (!series || !data) {
    return;
  }
  const settings = getFeatureSettings(name);
  const adjusted = data.normalized.map((point) => {
    if (point.value === undefined) {
      return { time: point.time };
    }
    return { time: point.time, value: point.value * settings.scale + settings.offset };
  });
  series.setData(adjusted);
  series.applyOptions({ color: settings.color, lineWidth: FEATURE_LINE_WIDTH });

  const markers = state.featureMarkers.get(name);
  if (markers?.setMarkers) {
    const gapMarkers = buildGapMarkersFromSeries(data.cleaned, settings.color, "inBar");
    markers.setMarkers(gapMarkers);
  }
}

function resizeChart() {
  if (!state.chart) {
    return;
  }
  const container = document.getElementById("chart");
  if (!container) {
    return;
  }
  state.chart.applyOptions({
    width: container.clientWidth,
    height: container.clientHeight,
  });
}

function getFeatureControlRanges(settings) {
  const barStats = state.barStats;
  if (barStats && Number.isFinite(barStats.min) && Number.isFinite(barStats.max)) {
    const span = Math.max(1, barStats.max - barStats.min);
    const step = Math.max(0.01, span / 200);
    return {
      scaleMin: Math.min(-span, settings.scale),
      scaleMax: Math.max(span, settings.scale),
      offsetMin: Math.min(barStats.min - span, settings.offset),
      offsetMax: Math.max(barStats.max + span, settings.offset),
      step,
    };
  }
  return {
    scaleMin: Math.min(-5, settings.scale),
    scaleMax: Math.max(5, settings.scale),
    offsetMin: Math.min(-5, settings.offset),
    offsetMax: Math.max(5, settings.offset),
    step: 0.1,
  };
}

function renderFeatureControls() {
  if (!elements.featureControls) {
    return;
  }
  elements.featureControls.innerHTML = "";
  if (!state.selectedFeatures.size) {
    const empty = document.createElement("div");
    empty.className = "feature-controls-empty";
    empty.textContent = "No features selected.";
    elements.featureControls.appendChild(empty);
    return;
  }

  const fragment = document.createDocumentFragment();
  state.selectedFeatures.forEach((name) => {
    const settings = getFeatureSettings(name);
    const stats = state.featureStats.get(name) || {};
    const ranges = getFeatureControlRanges(settings);

    const card = document.createElement("div");
    card.className = "feature-control-card";
    card.dataset.name = name;

    const header = document.createElement("div");
    header.className = "feature-control-header";

    const dot = document.createElement("span");
    dot.className = "feature-color-dot";
    dot.style.color = settings.color;
    dot.style.backgroundColor = settings.color;

    const title = document.createElement("div");
    title.className = "feature-control-name";
    title.textContent = name;

    const colorInput = document.createElement("input");
    colorInput.type = "color";
    colorInput.value = settings.color;
    colorInput.className = "feature-color-input";
    colorInput.dataset.name = name;
    colorInput.dataset.control = "color";

    header.appendChild(dot);
    header.appendChild(title);
    header.appendChild(colorInput);

    const scaleRow = document.createElement("div");
    scaleRow.className = "feature-control-row";
    scaleRow.innerHTML = `<label>Scale</label>`;
    const scaleRange = document.createElement("input");
    scaleRange.type = "range";
    scaleRange.min = ranges.scaleMin;
    scaleRange.max = ranges.scaleMax;
    scaleRange.step = ranges.step;
    scaleRange.value = settings.scale;
    scaleRange.dataset.name = name;
    scaleRange.dataset.control = "scale";
    const scaleNumber = document.createElement("input");
    scaleNumber.type = "number";
    scaleNumber.step = ranges.step;
    scaleNumber.value = settings.scale;
    scaleNumber.dataset.name = name;
    scaleNumber.dataset.control = "scale";
    scaleRow.appendChild(scaleRange);
    scaleRow.appendChild(scaleNumber);

    const offsetRow = document.createElement("div");
    offsetRow.className = "feature-control-row";
    offsetRow.innerHTML = `<label>Offset</label>`;
    const offsetRange = document.createElement("input");
    offsetRange.type = "range";
    offsetRange.min = ranges.offsetMin;
    offsetRange.max = ranges.offsetMax;
    offsetRange.step = ranges.step;
    offsetRange.value = settings.offset;
    offsetRange.dataset.name = name;
    offsetRange.dataset.control = "offset";
    const offsetNumber = document.createElement("input");
    offsetNumber.type = "number";
    offsetNumber.step = ranges.step;
    offsetNumber.value = settings.offset;
    offsetNumber.dataset.name = name;
    offsetNumber.dataset.control = "offset";
    offsetRow.appendChild(offsetRange);
    offsetRow.appendChild(offsetNumber);

    const statsGrid = document.createElement("div");
    statsGrid.className = "feature-stats";
    statsGrid.innerHTML = `
      <div class="feature-stat"><span>min</span><span>${formatNumber(stats.min)}</span></div>
      <div class="feature-stat"><span>max</span><span>${formatNumber(stats.max)}</span></div>
      <div class="feature-stat"><span>start</span><span>${formatNumber(stats.first)}</span></div>
      <div class="feature-stat"><span>norm</span><span>${formatNumber(stats.maxAbs)}</span></div>
    `;

    const actions = document.createElement("div");
    actions.className = "feature-control-actions";

    const rescaleButton = document.createElement("sl-button");
    rescaleButton.setAttribute("size", "small");
    rescaleButton.textContent = "Rescale";
    rescaleButton.dataset.name = name;
    rescaleButton.dataset.action = "rescale";

    const renormalizeButton = document.createElement("sl-button");
    renormalizeButton.setAttribute("size", "small");
    renormalizeButton.textContent = "Renormalize";
    renormalizeButton.dataset.name = name;
    renormalizeButton.dataset.action = "renormalize";

    const resetButton = document.createElement("sl-button");
    resetButton.setAttribute("size", "small");
    resetButton.textContent = "Reset";
    resetButton.dataset.name = name;
    resetButton.dataset.action = "reset";

    actions.appendChild(rescaleButton);
    actions.appendChild(renormalizeButton);
    actions.appendChild(resetButton);

    card.appendChild(header);
    card.appendChild(scaleRow);
    card.appendChild(offsetRow);
    card.appendChild(actions);
    card.appendChild(statsGrid);
    fragment.appendChild(card);
  });

  elements.featureControls.appendChild(fragment);
}

function renormalizeFeature(name) {
  const data = state.featureData.get(name);
  if (!data) {
    return;
  }
  const { cleaned } = data;
  const next = buildFeatureSeries(cleaned);
  state.featureData.set(name, { cleaned, normalized: next.normalized });
  state.featureStats.set(name, next.stats);
}

function rescaleFeature(name) {
  const defaults = getFeatureDefaults();
  setFeatureSettings(name, { scale: defaults.scale });
}

function resetFeatureDefaults(name) {
  const defaults = getFeatureDefaults();
  setFeatureSettings(name, { scale: defaults.scale, offset: defaults.offset });
  renormalizeFeature(name);
}

function handleFeatureControlAction(event) {
  const path = event.composedPath();
  const button = path.find((node) => node?.dataset?.action);
  const action = button?.dataset?.action;
  const name = button?.dataset?.name;
  if (!action || !name) {
    return;
  }
  if (action === "rescale") {
    rescaleFeature(name);
  } else if (action === "renormalize") {
    renormalizeFeature(name);
  } else if (action === "reset") {
    resetFeatureDefaults(name);
  }
  applyFeatureSettings(name);
  renderFeatureControls();
}

function handleFeatureControlInput(event) {
  const target = event.target;
  const name = target?.dataset?.name;
  const control = target?.dataset?.control;
  if (!name || !control) {
    return;
  }
  const card = target.closest(".feature-control-card");
  if (!card) {
    return;
  }

  if (control === "color") {
    const color = target.value;
    setFeatureSettings(name, { color });
    const dot = card.querySelector(".feature-color-dot");
    if (dot) {
      dot.style.color = color;
      dot.style.backgroundColor = color;
    }
    applyFeatureSettings(name);
    return;
  }

  const value = Number(target.value);
  if (!Number.isFinite(value)) {
    return;
  }
  const updates = {};
  updates[control] = value;
  const settings = setFeatureSettings(name, updates);

  const rangeInput = card.querySelector(
    `input[type="range"][data-control="${control}"]`
  );
  const numberInput = card.querySelector(
    `input[type="number"][data-control="${control}"]`
  );
  if (rangeInput) {
    const min = Number(rangeInput.min);
    const max = Number(rangeInput.max);
    if (Number.isFinite(min) && settings[control] < min) {
      rangeInput.min = settings[control];
    }
    if (Number.isFinite(max) && settings[control] > max) {
      rangeInput.max = settings[control];
    }
    rangeInput.value = settings[control];
  }
  if (numberInput) {
    numberInput.value = settings[control];
  }

  applyFeatureSettings(name);
}

function renderBars(payload) {
  const bars = payload.bars || [];
  const candles = bars
    .filter(
      (bar) =>
        bar.open !== null &&
        bar.high !== null &&
        bar.low !== null &&
        bar.close !== null
    )
    .map((bar) => ({
      time: bar.date,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }));
  const volumes = bars.map((bar) => ({
    time: bar.date,
    value: bar.volume ?? 0,
    color: bar.close >= bar.open ? "rgba(34, 197, 94, 0.6)" : "rgba(239, 68, 68, 0.6)",
  }));
  let min = null;
  let max = null;
  bars.forEach((bar) => {
    const low = Number(bar.low);
    const high = Number(bar.high);
    if (Number.isFinite(low)) {
      min = min === null ? low : Math.min(min, low);
    }
    if (Number.isFinite(high)) {
      max = max === null ? high : Math.max(max, high);
    }
  });
  state.barStats = min !== null && max !== null ? { min, max } : null;
  state.candleSeries.setData(candles);
  state.volumeSeries.setData(volumes);
  state.chart.timeScale().fitContent();
  renderFeatureControls();
}

function renderFeatures(payload) {
  clearFeatureSeries();
  const features = payload.features || {};
  Object.entries(features).forEach(([name, points]) => {
    const { cleaned, normalized, stats } = buildFeatureSeries(points);
    state.featureData.set(name, { cleaned, normalized });
    state.featureStats.set(name, stats);
    const settings = getFeatureSettings(name);
    const series = state.chart.addSeries(LightweightCharts.LineSeries, {
      priceScaleId: "right",
      color: settings.color,
      lineWidth: FEATURE_LINE_WIDTH,
      autoscaleInfoProvider: () => null,
    });
    state.featureSeries.set(name, series);

    if (LightweightCharts.createSeriesMarkers) {
      const markers = LightweightCharts.createSeriesMarkers(series);
      state.featureMarkers.set(name, markers);
    }

    applyFeatureSettings(name);
  });
  renderFeatureControls();
  updateFeatureCount();
}

function renderIndexes(payload) {
  clearIndexSeries();
  const indexes = payload?.indexes || {};
  Object.entries(indexes).forEach(([name, points]) => {
    const color = getIndexColor(name);
    const series = state.chart.addSeries(LightweightCharts.LineSeries, {
      priceScaleId: "right",
      color,
      lineWidth: 2,
    });
    let hasValue = false;
    const data = points.map((point) => {
      const value = Number(point.value);
      if (point.value === null || point.value === undefined || !Number.isFinite(value)) {
        return { time: point.date };
      }
      hasValue = true;
      return { time: point.date, value };
    });
    series.setData(data);
    if (hasValue) {
      state.indexSeries.set(name, series);
    } else {
      state.chart.removeSeries(series);
    }
  });
}

function updateDiagnostics(barsPayload, featuresPayload) {
  const missingBars = barsPayload?.meta?.missing_dates?.length ?? 0;
  elements.missingBarsText.textContent = missingBars ? `${missingBars} days` : "0";

  const featureRatios = featuresPayload?.meta?.missing_ratio || {};
  const featureValues = Object.values(featureRatios);
  const maxFeatureRatio = featureValues.length ? Math.max(...featureValues) : 0;

  elements.nanRatioText.textContent = `${(maxFeatureRatio * 100).toFixed(2)}%`;

  const missingSet = new Set([
    ...(barsPayload?.meta?.missing_dates || []),
    ...(featuresPayload?.meta?.missing_dates || []),
  ]);
  const calendarGaps = missingSet.size;

  elements.missingRatios.innerHTML = "";
  const featureRatioEntries = Object.entries(featureRatios);
  if (!featureRatioEntries.length) {
    const row = document.createElement("div");
    row.textContent = "None";
    elements.missingRatios.appendChild(row);
  } else {
    featureRatioEntries.forEach(([name, ratio]) => {
      const row = document.createElement("div");
      row.innerHTML = `<span>${name}</span><span>${(ratio * 100).toFixed(2)}%</span>`;
      elements.missingRatios.appendChild(row);
    });
  }

  if (calendarGaps) {
    setWarning(`Calendar gaps: ${calendarGaps} dates`);
  } else {
    setWarning("");
  }
}

function getSelectedFeatures() {
  return Array.from(state.selectedFeatures);
}

function getSelectedIndexes() {
  return Array.from(state.selectedIndexes);
}

function hasFullRange() {
  return Boolean(state.selectedTicker && elements.dateFrom.value && elements.dateTo.value);
}

function scheduleLoad() {
  if (!hasFullRange()) {
    showOverlay("Select a ticker and date range.");
    return;
  }
  if (!state.chart) {
    state.pendingAutoLoad = true;
    return;
  }
  clearTimeout(state.autoLoadTimer);
  state.autoLoadTimer = setTimeout(() => {
    if (state.loading) {
      state.pendingLoad = true;
      return;
    }
    loadData();
  }, 150);
}

function showInstrumentRangeNotice(ticker) {
  if (!elements.instrumentRange || !elements.instrumentRangeText) {
    return;
  }
  const bounds = state.tickerBounds.get(ticker) || {};
  const range = formatRange(bounds.start, bounds.end);
  elements.instrumentRangeText.textContent = `Instrument range: ${range}`;
  elements.instrumentRange.classList.add("visible");
}

function hideInstrumentRangeNotice() {
  if (!elements.instrumentRange) {
    return;
  }
  elements.instrumentRange.classList.remove("visible");
}

function applyInstrumentRange(ticker) {
  const bounds = state.tickerBounds.get(ticker);
  if (!bounds) {
    return;
  }
  if (ticker) {
    setSelectedTicker(ticker, { closeDropdown: false });
  }
  if (bounds.start) {
    elements.dateFrom.value = normalizeDate(bounds.start);
  }
  if (bounds.end) {
    elements.dateTo.value = normalizeDate(bounds.end);
  }
  renderTickerOptions();
  scheduleLoad();
}

function updateTickerOptionStyles() {
  renderTickerOptions();
}

async function loadData() {
  const ticker = state.selectedTicker;
  const from = elements.dateFrom.value;
  const to = elements.dateTo.value;

  if (!ticker || !from || !to) {
    setWarning("Ticker and date range are required");
    showOverlay("Select a ticker and date range.");
    return;
  }

  if (!state.chart) {
    setWarning("Chart failed to initialize. Check console for errors.");
    showOverlay("Chart failed to initialize.");
    return;
  }

  state.loading = true;
  showOverlay("Loading...");
  setWarning("");
  hideInstrumentRangeNotice();

  const featureNames = getSelectedFeatures();
  const indexNames = getSelectedIndexes();
  const barsUrl = new URL("/bars", API_BASE);
  barsUrl.searchParams.set("ticker", ticker);
  barsUrl.searchParams.set("from", from);
  barsUrl.searchParams.set("to", to);

  const featuresUrl =
    featureNames.length > 0
      ? (() => {
          const url = new URL("/features", API_BASE);
          url.searchParams.set("ticker", ticker);
          url.searchParams.set("from", from);
          url.searchParams.set("to", to);
          url.searchParams.set("names", featureNames.join(","));
          return url;
        })()
      : null;

  const indexesUrl =
    indexNames.length > 0
      ? (() => {
          const url = new URL("/index-series", API_BASE);
          url.searchParams.set("instrument", ticker);
          url.searchParams.set("from", from);
          url.searchParams.set("to", to);
          url.searchParams.set("names", indexNames.join(","));
          return url;
        })()
      : null;

  try {
    const responses = await Promise.all([
      fetchJson(barsUrl.toString()),
      featuresUrl ? fetchJson(featuresUrl.toString()) : Promise.resolve(null),
      indexesUrl ? fetchJson(indexesUrl.toString()) : Promise.resolve(null),
    ]);
    const barsPayload = responses[0];
    const featuresPayload = responses[1];
    const indexesPayload = responses[2];

    renderBars(barsPayload);
    if (featuresPayload) {
      renderFeatures(featuresPayload);
    } else {
      clearFeatureSeries();
      renderFeatureControls();
      updateFeatureCount();
    }
    if (indexesPayload) {
      renderIndexes(indexesPayload);
    } else {
      clearIndexSeries();
    }

    elements.activeRange.textContent = `${ticker} · ${formatRange(from, to)}`;
    updateDiagnostics(barsPayload, featuresPayload);
    if (!barsPayload.bars || !barsPayload.bars.length) {
      setWarning("No bars returned for the selected range");
      showInstrumentRangeNotice(ticker);
      showOverlay("No bars returned. Use instrument range.");
    } else {
      hideOverlay();
    }
  } catch (error) {
    setWarning(error.message || "Failed to load data");
    showOverlay("Failed to load data.");
  } finally {
    state.loading = false;
    if (state.pendingLoad) {
      state.pendingLoad = false;
      scheduleLoad();
    }
  }
}

function wireEvents() {
  elements.refreshHealth.addEventListener("click", loadHealth);
  elements.fitChart.addEventListener("click", () => {
    if (!state.chart) {
      return;
    }
    state.chart.timeScale().fitContent();
  });
  if (elements.dateFrom) {
    elements.dateFrom.addEventListener("sl-change", () => {
      updateTickerOptionStyles();
      scheduleLoad();
    });
  }

  if (elements.dateTo) {
    elements.dateTo.addEventListener("sl-change", () => {
      updateTickerOptionStyles();
      scheduleLoad();
    });
  }

  if (elements.tickerFilter) {
    elements.tickerFilter.addEventListener("sl-input", (event) => {
      const query = event.target.value.trim().toLowerCase();
      clearTimeout(state.tickerSearchTimer);
      state.tickerSearchTimer = setTimeout(() => {
        state.tickerFilterQuery = query;
        renderTickerOptions();
      }, 200);
    });
  }

  if (elements.tickerList) {
    elements.tickerList.addEventListener("click", (event) => {
      const target = event.target;
      const action = target.closest?.(".ticker-action");
      if (action) {
        event.preventDefault();
        event.stopPropagation();
        const ticker = action.dataset.ticker;
        if (ticker) {
          applyInstrumentRange(ticker);
        }
        return;
      }
      const row = target.closest?.(".ticker-row");
      if (!row) {
        return;
      }
      const ticker = row.dataset.ticker;
      if (!ticker) {
        return;
      }
      setSelectedTicker(ticker);
      scheduleLoad();
    });
  }

  if (elements.indexFilter) {
    elements.indexFilter.addEventListener("sl-input", (event) => {
      const query = event.target.value.trim();
      clearTimeout(state.indexSearchTimer);
      state.indexSearchTimer = setTimeout(() => {
        filterIndexes(query);
      }, 200);
    });
  }

  if (elements.indexSelected) {
    elements.indexSelected.addEventListener("click", (event) => {
      const target = event.target;
      const id = target.dataset?.id;
      if (!id) {
        return;
      }
      state.selectedIndexes.delete(id);
      renderIndexList();
      renderSelectedIndexes();
      scheduleLoad();
    });
  }

  if (elements.indexList) {
    elements.indexList.addEventListener("sl-change", (event) => {
      const target = event.target;
      const checkbox = target.closest?.("sl-checkbox") || target;
      const id = checkbox.getAttribute?.("data-id");
      if (!id) {
        return;
      }
      if (checkbox.checked) {
        state.selectedIndexes.add(id);
      } else {
        state.selectedIndexes.delete(id);
      }
      renderIndexList();
      renderSelectedIndexes();
      scheduleLoad();
    });
  }

  if (elements.clearIndexes) {
    elements.clearIndexes.addEventListener("click", () => {
      state.selectedIndexes.clear();
      renderIndexList();
      renderSelectedIndexes();
      clearIndexSeries();
      scheduleLoad();
    });
  }

  if (elements.featureFilter) {
    elements.featureFilter.addEventListener("sl-input", (event) => {
      const query = event.target.value.trim();
      clearTimeout(state.featureSearchTimer);
      state.featureSearchTimer = setTimeout(() => {
        filterFeatures(query);
      }, 200);
    });
  }

  if (elements.featureSelected) {
    elements.featureSelected.addEventListener("click", (event) => {
      const target = event.target;
      const name = target.dataset?.name;
      if (!name) {
        return;
      }
      state.selectedFeatures.delete(name);
      renderFeatureList();
      renderSelectedFeatures();
      scheduleLoad();
    });
  }

  if (elements.featureControls) {
    elements.featureControls.addEventListener("input", handleFeatureControlInput);
    elements.featureControls.addEventListener("change", handleFeatureControlInput);
    elements.featureControls.addEventListener("click", handleFeatureControlAction);
  }

  if (elements.range2025) {
    elements.range2025.addEventListener("click", () => {
      elements.dateFrom.value = "2025-01-01";
      elements.dateTo.value = "2025-12-31";
      updateTickerOptionStyles();
      scheduleLoad();
    });
  }

  if (elements.rangeLastDay) {
    elements.rangeLastDay.addEventListener("click", () => {
      const today = new Date();
      const iso = today.toISOString().slice(0, 10);
      elements.dateFrom.value = iso;
      elements.dateTo.value = iso;
      updateTickerOptionStyles();
      scheduleLoad();
    });
  }

  if (elements.rangeLastWeek) {
    elements.rangeLastWeek.addEventListener("click", () => {
      const today = new Date();
      const past = new Date(today);
      past.setDate(today.getDate() - 7);
      elements.dateFrom.value = past.toISOString().slice(0, 10);
      elements.dateTo.value = today.toISOString().slice(0, 10);
      updateTickerOptionStyles();
      scheduleLoad();
    });
  }

  if (elements.rangeLastMonth) {
    elements.rangeLastMonth.addEventListener("click", () => {
      const today = new Date();
      const past = new Date(today);
      past.setMonth(today.getMonth() - 1);
      elements.dateFrom.value = past.toISOString().slice(0, 10);
      elements.dateTo.value = today.toISOString().slice(0, 10);
      updateTickerOptionStyles();
      scheduleLoad();
    });
  }

  if (elements.applyInstrumentRange) {
    elements.applyInstrumentRange.addEventListener("click", () => {
      applyInstrumentRange(state.selectedTicker);
    });
  }

  elements.featureList.addEventListener("sl-change", (event) => {
    const target = event.target;
    const name = target.getAttribute("data-name");
    if (!name) {
      return;
    }
    if (target.checked) {
      state.selectedFeatures.add(name);
    } else {
      state.selectedFeatures.delete(name);
    }
    updateFeatureCount();
    renderSelectedFeatures();
    scheduleLoad();
  });

  elements.selectAll.addEventListener("click", () => {
    state.features.forEach((feature) => state.selectedFeatures.add(feature.name));
    renderFeatureList();
    renderSelectedFeatures();
    scheduleLoad();
  });

  elements.clearFeatures.addEventListener("click", () => {
    state.selectedFeatures.clear();
    renderFeatureList();
    clearFeatureSeries();
    renderFeatureControls();
    renderSelectedFeatures();
    scheduleLoad();
  });
}

async function init() {
  wireEvents();
  showOverlay("Loading tickers...");
  elements.dateFrom.value = "2025-01-01";
  elements.dateTo.value = "2025-12-31";
  await loadFeatureSettings();
  await loadHealth();
  await loadTickers();
  await loadIndexes();
  await loadFeaturesList();
  try {
    initChart();
  } catch (error) {
    setWarning(error.message || "Chart failed to initialize");
    showOverlay("Chart failed to initialize.");
  }
  if (state.pendingAutoLoad) {
    state.pendingAutoLoad = false;
    scheduleLoad();
    return;
  }
  scheduleLoad();
}

init();
