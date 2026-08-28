/**
 * IONNA Rechargery Tracker — Interactive Web Dashboard Client
 *
 * Manages:
 * - Single-page dashboard state (data payload, active filters, sorting).
 * - Leaflet map initialization, custom marker rendering, and synchronized viewports.
 * - Dynamic SVG timeseries history chart rendering.
 * - Real-time client-side search, multi-factor filtering, and sortable tables.
 */

const state = {
  data: null,
  filteredLocations: [],
  sort: { key: "location", direction: "ascending" },
  map: null,
  mapMarkers: null,
  mapWheelCleanup: null,
};

const $ = (selector) => document.querySelector(selector);

// Operational status sorting priority
const STATUS_SORT_ORDER = {
  open: 0,
  coming_soon: 1,
  under_renovation: 2,
  unknown: 3,
};

// Distinct map marker colors for operational status
const MAP_STATUS_COLORS = {
  open: "#416d78",
  coming_soon: "#f0a340",
  under_renovation: "#ce592b",
  unknown: "#8d9999",
};

// Shape mapping for Rechargery station types
const MAP_TYPE_SHAPES = {
  "Rechargery": "circle",
  "Rechargery @": "square",
  "Rechargery Beacon": "diamond",
  "Rechargery Relay": "triangle",
};

/**
 * Escape HTML special characters to prevent XSS injection.
 * @param {string|number|null} value
 * @returns {string} Escaped string.
 */
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

/**
 * Return user-friendly label for an operational status code.
 * @param {string} status
 * @returns {string}
 */
const statusLabel = (status) => ({
  open: "Open", coming_soon: "Coming soon", under_renovation: "Renovation", unknown: "Unknown",
}[status] || status);

/**
 * Return human-readable label for a tracked location property.
 * @param {string} field
 * @returns {string}
 */
const fieldLabel = (field) => ({
  title: "title",
  street: "street",
  city: "city",
  state: "state",
  postcode: "zip",
  country: "country",
  note: "note",
  status: "status",
  type: "type",
  speed_kw: "speed",
  price_text: "price",
  price_per_kwh: "price/kWh",
  nacs_connectors: "NACS",
  ccs_connectors: "CCS",
  amenities: "amenities",
  latitude: "lat",
  longitude: "lon",
  link: "link",
  image_url: "image",
}[field] || field);

/**
 * Format a nullable field diff value for event descriptions.
 * @param {any} value
 * @returns {string}
 */
const renderChangeValue = (value) => (
  value === null || value === undefined ? "—" : String(value)
);

/**
 * Format date string into locale date and optional time.
 * @param {string} value
 * @param {{ time?: boolean }} options
 * @returns {string}
 */
const formatDate = (value, options = {}) => value
  ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: options.time ? "short" : undefined }).format(new Date(value))
  : "—";

/**
 * Extract comparable sort value for a station item based on active column.
 * @param {object} item
 * @param {string} key
 * @returns {string|number}
 */
function sortValue(item, key) {
  if (key === "status") return STATUS_SORT_ORDER[item.status] ?? 99;
  if (key === "type") return item.type || "";
  return item.title || "";
}

/**
 * Compare two station objects based on current sort settings with secondary fallbacks.
 * @param {object} a
 * @param {object} b
 * @param {{ key: string, direction: string }} sort
 * @returns {number}
 */
function compareLocations(a, b, sort) {
  const left = sortValue(a, sort.key);
  const right = sortValue(b, sort.key);
  const primary = typeof left === "number"
    ? left - right
    : left.localeCompare(right, undefined, { sensitivity: "base" });
  const direction = sort.direction === "descending" ? -1 : 1;
  if (primary) return primary * direction;
  return (a.state || "").localeCompare(b.state || "")
    || (a.city || "").localeCompare(b.city || "")
    || (a.title || "").localeCompare(b.title || "");
}

/**
 * Cycle sort direction or toggle column.
 * @param {{ key: string, direction: string }} current
 * @param {string} key
 * @returns {{ key: string, direction: string }}
 */
function nextSort(current, key) {
  return {
    key,
    direction: current.key === key && current.direction === "ascending"
      ? "descending"
      : "ascending",
  };
}

/**
 * Validate and extract latitude/longitude coordinates.
 * @param {object} item
 * @returns {[number, number]|null}
 */
function locationCoordinates(item) {
  if (item.latitude === null || item.latitude === "" || item.longitude === null || item.longitude === "") return null;
  const latitude = Number(item.latitude);
  const longitude = Number(item.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
  return [latitude, longitude];
}

function mapStatusColor(status) {
  return MAP_STATUS_COLORS[status] || MAP_STATUS_COLORS.unknown;
}

function mapTypeShape(type) {
  return MAP_TYPE_SHAPES[type] || "pentagon";
}

/**
 * Generate a custom Leaflet HTML divIcon matching status color and type shape.
 * @param {object} item
 * @returns {L.DivIcon}
 */
function mapMarkerIcon(item) {
  const shape = mapTypeShape(item.type);
  return L.divIcon({
    className: "map-marker-icon",
    html: `<span class="map-shape map-shape--${shape}" style="--map-marker-color:${mapStatusColor(item.status)}" aria-hidden="true"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -8],
  });
}

/**
 * Ensure URL is a safe HTTP/HTTPS link.
 * @param {string} value
 * @returns {string}
 */
function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch (_error) {
    return "";
  }
}

/**
 * Render popup HTML content for a map marker.
 * @param {object} item
 * @returns {string}
 */
function mapPopup(item) {
  const href = safeExternalUrl(item.link);
  const title = href
    ? `<a class="map-popup__title" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>`
    : `<strong class="map-popup__title">${escapeHtml(item.title)}</strong>`;
  return `${title}
    <span class="map-popup__type">${escapeHtml(item.type || "Unknown type")}</span>
    <span class="map-popup__address">${escapeHtml(item.street)}, ${escapeHtml(item.city)}, ${escapeHtml(item.state)} ${escapeHtml(item.postcode)}</span>
    <span class="status status--${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>`;
}

function mapWheelZoomAllowed(event) {
  return Boolean(event.metaKey || event.ctrlKey);
}

/**
 * Require Command/Ctrl key for wheel zooming so page scrolling is not trapped.
 * @param {HTMLElement} host
 * @returns {Function} Cleanup function.
 */
function setupModifierWheelZoom(host) {
  if (!host?.addEventListener) return () => {};
  const options = { capture: true, passive: true };
  const handleWheel = (event) => {
    if (!mapWheelZoomAllowed(event)) event.stopImmediatePropagation();
  };
  host.addEventListener("wheel", handleWheel, options);
  return () => host.removeEventListener("wheel", handleWheel, options);
}

/**
 * Fallback handler if Leaflet or map tiles cannot be loaded.
 * @param {Error|null} error
 */
function showMapFallback(error = null) {
  const host = $("#location-map");
  if (!host) return;
  if (state.mapWheelCleanup) state.mapWheelCleanup();
  state.mapWheelCleanup = null;
  if (state.map) {
    try {
      state.map.remove();
    } catch (_removeError) {
      // Leaflet may be only partially initialized; replacing the host is enough.
    }
  }
  state.map = null;
  state.mapMarkers = null;
  host.innerHTML = '<div class="map-fallback">Map tiles are unavailable. The location table remains fully usable.</div>';
  const count = $("#map-location-count");
  if (count) count.textContent = "Map unavailable; location table still active";
  if (error) console.warn("Location map unavailable", error);
}

/**
 * Initialize the Leaflet map with OpenStreetMap tiles.
 */
function setupMap() {
  const host = $("#location-map");
  if (!host) return;
  if (typeof L === "undefined") {
    showMapFallback();
    return;
  }

  try {
    state.map = L.map(host, {
      minZoom: 3,
      scrollWheelZoom: true,
      preferCanvas: true,
    });
    state.mapWheelCleanup = setupModifierWheelZoom(host);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(state.map);
    state.mapMarkers = L.layerGroup().addTo(state.map);
  } catch (error) {
    showMapFallback(error);
  }
}

/**
 * Render station markers on the Leaflet map and fit bounds to filtered locations.
 * @param {Array<object>} locations
 */
function renderMap(locations) {
  if (!state.map || !state.mapMarkers) return;
  try {
    state.mapMarkers.clearLayers();
    const bounds = [];

    locations.forEach((item) => {
      const coordinates = locationCoordinates(item);
      if (!coordinates) return;
      bounds.push(coordinates);
      L.marker(coordinates, {
        icon: mapMarkerIcon(item),
        keyboard: true,
        riseOnHover: true,
        title: `${item.title} — ${statusLabel(item.status)} — ${item.type || "Unknown type"}`,
      }).bindPopup(mapPopup(item), { maxWidth: 320 }).addTo(state.mapMarkers);
    });

    if (bounds.length === 1) state.map.setView(bounds[0], 10, { animate: false });
    else if (bounds.length > 1) state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 10, animate: false });
    else state.map.setView([39.5, -98.35], 4, { animate: false });

    $("#map-location-count").textContent = bounds.length === locations.length
      ? `${bounds.length} locations mapped from IONNA coordinates`
      : `${bounds.length} of ${locations.length} locations have mappable coordinates`;
  } catch (error) {
    showMapFallback(error);
  }
}

function updateSortHeaders() {
  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    const header = button.closest("th");
    const active = button.dataset.sortKey === state.sort.key;
    header.setAttribute("aria-sort", active ? state.sort.direction : "none");
    button.querySelector(".sort-button__icon").textContent = active
      ? (state.sort.direction === "ascending" ? "↑" : "↓")
      : "↕";
  });
}

function setupSorting() {
  document.querySelectorAll("[data-sort-key]").forEach((button) => {
    button.addEventListener("click", () => {
      state.sort = nextSort(state.sort, button.dataset.sortKey);
      updateSortHeaders();
      renderLocations({ updateMap: false });
    });
  });
  updateSortHeaders();
}

/**
 * Populate top summary KPI metrics.
 * @param {object} data
 */
function populateSummary(data) {
  const s = data.summary;
  $("#metric-total").textContent = s.total.toLocaleString();
  $("#metric-states").textContent = `${s.states} states`;
  $("#metric-open").textContent = s.open.toLocaleString();
  $("#metric-open-share").textContent = s.total ? `${Math.round((s.open / s.total) * 100)}% of network` : "—";
  $("#metric-coming").textContent = s.coming_soon.toLocaleString();
  $("#metric-new").textContent = s.new_recent.toLocaleString();
  $("#metric-new-window").textContent = `Last ${data.recent_days} days, after baseline`;
  $("#metric-openings").textContent = s.observed_openings.toLocaleString();
  $("#last-updated").textContent = `Last collected ${formatDate(data.last_run?.fetched_at, { time: true })}`;
}

/**
 * Render SVG network history timeseries line chart.
 * @param {Array<object>} history
 */
function renderHistory(history) {
  const host = $("#history-chart");
  if (!history.length) { host.innerHTML = '<div class="no-events">No observations yet.</div>'; return; }
  const width = 1050, height = 250, pad = { l: 42, r: 18, t: 15, b: 32 };
  const maxY = Math.max(1, ...history.map((d) => d.total));
  const x = (i) => pad.l + (history.length === 1 ? (width - pad.l - pad.r) / 2 : i * (width - pad.l - pad.r) / (history.length - 1));
  const y = (v) => height - pad.b - (v / maxY) * (height - pad.t - pad.b);
  const points = (key) => history.map((d, i) => `${x(i)},${y(d[key] || 0)}`).join(" ");
  const grid = [0, .25, .5, .75, 1].map((ratio) => {
    const gy = y(maxY * ratio);
    return `<line class="chart-grid" x1="${pad.l}" x2="${width - pad.r}" y1="${gy}" y2="${gy}"/><text class="chart-label" x="0" y="${gy + 4}">${Math.round(maxY * ratio)}</text>`;
  }).join("");
  const first = history[0], last = history.at(-1);
  host.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
    ${grid}
    <polyline class="chart-line chart-line--total" points="${points("total")}" />
    <polyline class="chart-line chart-line--open" points="${points("open")}" />
    <polyline class="chart-line chart-line--soon" points="${points("coming_soon")}" />
    <text class="chart-label" x="${pad.l}" y="${height - 7}">${formatDate(first.at)}</text>
    <text class="chart-label" x="${width - pad.r}" y="${height - 7}" text-anchor="end">${formatDate(last.at)}</text>
  </svg>`;
  $("#history-note").textContent = history.length === 1
    ? "One baseline captured. Run the collector again later to begin the trend line."
    : `${history.length} observations shown. Dates reflect collection time.`;
}

/**
 * Render horizontal distribution bars by state.
 * @param {Array<object>} rows
 */
function renderStates(rows) {
  const max = Math.max(1, ...rows.map((row) => row.total));
  $("#state-bars").innerHTML = rows.map((row) => `<div class="bar-row" title="${row.open} open, ${row.coming_soon} coming soon">
    <strong>${escapeHtml(row.state)}</strong>
    <div class="bar-track">
      <span class="bar-open" style="width:${row.open / max * 100}%"></span>
      <span class="bar-soon" style="width:${row.coming_soon / max * 100}%"></span>
      <span class="bar-other" style="width:${(row.total - row.open - row.coming_soon) / max * 100}%"></span>
    </div><span class="bar-total">${row.total}</span></div>`).join("");
}

/**
 * Render Rechargery type breakdown cards.
 * @param {Array<object>} rows
 */
function renderTypes(rows) {
  $("#type-breakdown").innerHTML = rows.map((row) => `<article class="type-card">
    <div class="type-card__top"><strong>${escapeHtml(row.type)}</strong><b>${row.total}</b></div>
    <div class="type-card__meta">${row.open} open · ${row.coming_soon} coming soon${row.under_renovation ? ` · ${row.under_renovation} renovation` : ""}</div>
  </article>`).join("");
}

/**
 * Setup dropdown filter options dynamically from data.
 * @param {object} data
 */
function setupFilters(data) {
  const states = [...new Set(data.locations.map((item) => item.state))].sort();
  const types = [...new Set(data.locations.map((item) => item.type))].sort();
  $("#state-filter").insertAdjacentHTML("beforeend", states.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join(""));
  $("#type-filter").insertAdjacentHTML("beforeend", types.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join(""));
  ["#search-filter", "#state-filter", "#status-filter", "#type-filter"].forEach((selector) => {
    $(selector).addEventListener("input", () => renderLocations());
  });
}

/**
 * Filter and render the station directory table and update map markers.
 * @param {{ updateMap?: boolean }} options
 */
function renderLocations({ updateMap = true } = {}) {
  const query = $("#search-filter").value.trim().toLowerCase();
  const selectedState = $("#state-filter").value;
  const status = $("#status-filter").value;
  const type = $("#type-filter").value;
  const filtered = state.data.locations.filter((item) => {
    const haystack = `${item.title} ${item.street} ${item.city} ${item.state} ${item.postcode}`.toLowerCase();
    return (!query || haystack.includes(query)) && (!selectedState || item.state === selectedState)
      && (!status || item.status === status) && (!type || item.type === type);
  }).sort((a, b) => compareLocations(a, b, state.sort));
  state.filteredLocations = filtered;
  if (updateMap) renderMap(filtered);
  $("#locations-table").innerHTML = filtered.map((item) => {
    const connectors = [[item.nacs_connectors, "NACS"], [item.ccs_connectors, "CCS"]]
      .filter(([count]) => count !== null).map(([count, name]) => `${count} ${name}`).join(" · ") || "—";
    const href = safeExternalUrl(item.link);
    const locationName = href
      ? `<a class="location-name" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>`
      : `<strong class="location-name">${escapeHtml(item.title)}</strong>`;
    return `<tr><td>${locationName}
      <span class="location-address">${escapeHtml(item.street)}, ${escapeHtml(item.city)}, ${escapeHtml(item.state)} ${escapeHtml(item.postcode)}</span></td>
      <td><span class="status status--${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span></td>
      <td>${escapeHtml(item.type)}</td><td>${escapeHtml(connectors)}</td><td>${escapeHtml(item.price_text || "—")}</td>
      <td>${formatDate(item.first_seen_at)}</td></tr>`;
  }).join("");
  const visibleViews = state.map && state.mapMarkers ? "the map and table" : "the table";
  $("#location-count").textContent = `Showing ${filtered.length} of ${state.data.locations.length} active locations in ${visibleViews}.`;
}

/**
 * Render recent lifecycle events and changes list.
 * @param {object} data
 */
function renderEvents(data) {
  $("#recent-window").textContent = `Last ${data.recent_days} days`;
  const host = $("#recent-events");
  if (!data.recent_changes.length) {
    host.innerHTML = '<div class="no-events">No post-baseline changes observed in this window.</div>';
    return;
  }
  host.innerHTML = data.recent_changes.map((event) => {
    const kind = event.event_type === "discovered"
      ? "New location"
      : event.event_type === "observed_open"
        ? "Observed opening"
        : event.event_type === "updated"
          ? "Updated details"
          : "Status changed";
    const detail = event.event_type === "discovered"
      ? `${statusLabel(event.to_status)} in ${event.state}`
      : event.event_type === "updated"
        ? `${(event.changed_fields || [])
            .slice(0, 3)
            .map((item) => `${fieldLabel(item.field)}: ${renderChangeValue(item.from)} → ${renderChangeValue(item.to)}`)
            .join(" · ")}${(event.changed_count || 0) > 3 ? ` · +${(event.changed_count || 0) - 3} more` : ""}`.trim() || "Location details changed"
        : `${statusLabel(event.from_status)} → ${statusLabel(event.to_status)}`;
    return `<article class="event"><span class="event__kind">${kind}</span><div><strong>${escapeHtml(event.title)}</strong><br><span class="panel__hint">${escapeHtml(detail)}</span></div><time class="event__time">${formatDate(event.occurred_at, { time: true })}</time></article>`;
  }).join("");
}

/**
 * Fetch dashboard data from backend API and initialize all UI components.
 */
async function loadDashboard() {
  try {
    const response = await fetch("/api/dashboard?days=7");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    if (!data.has_data) {
      $("#empty-state").classList.remove("hidden");
      $("#dashboard-content").classList.add("hidden");
      return;
    }
    state.data = data;
    populateSummary(data); renderHistory(data.history); renderStates(data.states); renderTypes(data.types);
    setupFilters(data); setupSorting(); setupMap(); renderLocations(); renderEvents(data);
  } catch (error) {
    $("#dashboard-content").innerHTML = `<div class="error-banner"><strong>Dashboard unavailable.</strong> ${escapeHtml(error.message)}</div>`;
    $("#last-updated").textContent = "Local data unavailable";
  }
}

if (typeof document !== "undefined") loadDashboard();

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    compareLocations,
    locationCoordinates,
    mapStatusColor,
    mapTypeShape,
    mapWheelZoomAllowed,
    nextSort,
    renderMap,
    safeExternalUrl,
    setupMap,
    setupModifierWheelZoom,
    sortValue,
  };
}
