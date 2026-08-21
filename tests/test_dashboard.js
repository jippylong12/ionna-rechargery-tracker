const test = require("node:test");
const assert = require("node:assert/strict");

const {
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
} = require("../static/dashboard.js");

const locations = [
  { title: "Zulu Site", status: "coming_soon", type: "Relay", state: "TX", city: "Austin" },
  { title: "Alpha Site", status: "under_renovation", type: "Beacon", state: "AZ", city: "Yuma" },
  { title: "Middle Site", status: "open", type: "Rechargery", state: "NC", city: "Raleigh" },
];

test("sorts location titles in either direction", () => {
  const ascending = [...locations].sort((a, b) => compareLocations(
    a, b, { key: "location", direction: "ascending" },
  ));
  const descending = [...locations].sort((a, b) => compareLocations(
    a, b, { key: "location", direction: "descending" },
  ));

  assert.deepEqual(ascending.map((item) => item.title), ["Alpha Site", "Middle Site", "Zulu Site"]);
  assert.deepEqual(descending.map((item) => item.title), ["Zulu Site", "Middle Site", "Alpha Site"]);
});

test("sorts statuses in a useful network order", () => {
  const sorted = [...locations].sort((a, b) => compareLocations(
    a, b, { key: "status", direction: "ascending" },
  ));

  assert.deepEqual(sorted.map((item) => item.status), ["open", "coming_soon", "under_renovation"]);
  assert.equal(sortValue({ status: "unexpected" }, "status"), 99);
});

test("switching columns resets to ascending and repeated clicks toggle", () => {
  assert.deepEqual(
    nextSort({ key: "location", direction: "ascending" }, "location"),
    { key: "location", direction: "descending" },
  );
  assert.deepEqual(
    nextSort({ key: "location", direction: "descending" }, "type"),
    { key: "type", direction: "ascending" },
  );
});

test("accepts valid coordinates and rejects unusable map points", () => {
  assert.deepEqual(locationCoordinates({ latitude: "30.2", longitude: -97.7 }), [30.2, -97.7]);
  assert.equal(locationCoordinates({ latitude: null, longitude: -97.7 }), null);
  assert.equal(locationCoordinates({ latitude: 95, longitude: -97.7 }), null);
  assert.equal(locationCoordinates({ latitude: 30.2, longitude: -181 }), null);
});

test("uses status colors and permits only web location links", () => {
  assert.equal(mapStatusColor("open"), "#416d78");
  assert.equal(mapStatusColor("unexpected"), "#8d9999");
  assert.equal(safeExternalUrl("https://www.ionna.com/rechargery/example/"), "https://www.ionna.com/rechargery/example/");
  assert.equal(safeExternalUrl("javascript:alert(1)"), "");
  assert.equal(safeExternalUrl("not a URL"), "");
});

test("uses a distinct map shape for each Rechargery type", () => {
  assert.equal(mapTypeShape("Rechargery"), "circle");
  assert.equal(mapTypeShape("Rechargery @"), "square");
  assert.equal(mapTypeShape("Rechargery Beacon"), "diamond");
  assert.equal(mapTypeShape("Rechargery Relay"), "triangle");
  assert.equal(mapTypeShape("Future type"), "pentagon");
  assert.equal(mapTypeShape(null), "pentagon");
});

test("limits map wheel zoom to Command or Control scrolling", () => {
  let wheelHandler;
  let listenerOptions;
  let removed = false;
  const host = {
    addEventListener: (type, handler, options) => {
      assert.equal(type, "wheel");
      wheelHandler = handler;
      listenerOptions = options;
    },
    removeEventListener: (type, handler, options) => {
      assert.equal(type, "wheel");
      assert.equal(handler, wheelHandler);
      assert.equal(options, listenerOptions);
      removed = true;
    },
  };
  const cleanup = setupModifierWheelZoom(host);
  let regularScrollStopped = false;
  wheelHandler({
    metaKey: false,
    ctrlKey: false,
    stopImmediatePropagation: () => { regularScrollStopped = true; },
  });
  assert.equal(regularScrollStopped, true);
  assert.deepEqual(listenerOptions, { capture: true, passive: true });

  for (const event of [{ metaKey: true, ctrlKey: false }, { metaKey: false, ctrlKey: true }]) {
    let modifierScrollStopped = false;
    wheelHandler({ ...event, stopImmediatePropagation: () => { modifierScrollStopped = true; } });
    assert.equal(mapWheelZoomAllowed(event), true);
    assert.equal(modifierScrollStopped, false);
  }

  cleanup();
  assert.equal(removed, true);
});

test("renders filtered locations with status colors and type shapes", () => {
  const hosts = {
    "#location-map": {
      addEventListener: () => {},
      removeEventListener: () => {},
      innerHTML: "",
    },
    "#map-location-count": { textContent: "" },
  };
  const markerIcons = [];
  const map = {
    fitBounds: () => {},
    remove: () => {},
    setView: () => {},
  };
  const markerLayer = {
    addTo: () => markerLayer,
    clearLayers: () => {},
  };
  const originalDocument = global.document;
  const originalLeaflet = global.L;
  global.document = { querySelector: (selector) => hosts[selector] || null };
  global.L = {
    divIcon: (options) => options,
    layerGroup: () => markerLayer,
    map: () => map,
    marker: (_coordinates, options) => {
      markerIcons.push(options.icon.html);
      const marker = {
        addTo: () => marker,
        bindPopup: () => marker,
      };
      return marker;
    },
    tileLayer: () => ({ addTo: () => {} }),
  };

  try {
    setupMap();
    renderMap([
      { title: "Open Relay", type: "Rechargery Relay", status: "open", latitude: 30, longitude: -97, street: "1 Main", city: "Austin", state: "TX", postcode: "78701" },
      { title: "Future @", type: "Rechargery @", status: "coming_soon", latitude: 31, longitude: -98, street: "2 Main", city: "Waco", state: "TX", postcode: "76701" },
    ]);
    assert.match(markerIcons[0], /map-shape--triangle/);
    assert.match(markerIcons[0], /#416d78/);
    assert.match(markerIcons[1], /map-shape--square/);
    assert.match(markerIcons[1], /#f0a340/);
    assert.equal(hosts["#map-location-count"].textContent, "2 locations mapped from IONNA coordinates");
  } finally {
    if (originalDocument === undefined) delete global.document;
    else global.document = originalDocument;
    if (originalLeaflet === undefined) delete global.L;
    else global.L = originalLeaflet;
  }
});

test("map initialization failures preserve the table fallback", () => {
  const hosts = {
    "#location-map": { innerHTML: "" },
    "#map-location-count": { textContent: "" },
  };
  const originalDocument = global.document;
  const originalLeaflet = global.L;
  const originalWarn = console.warn;
  global.document = { querySelector: (selector) => hosts[selector] || null };
  global.L = { map: () => { throw new Error("canvas unavailable"); } };
  console.warn = () => {};

  try {
    assert.doesNotThrow(() => setupMap());
    assert.match(hosts["#location-map"].innerHTML, /location table remains fully usable/i);
    assert.match(hosts["#map-location-count"].textContent, /table still active/i);
  } finally {
    if (originalDocument === undefined) delete global.document;
    else global.document = originalDocument;
    if (originalLeaflet === undefined) delete global.L;
    else global.L = originalLeaflet;
    console.warn = originalWarn;
  }
});

test("marker rendering failures preserve the table fallback", () => {
  const hosts = {
    "#location-map": { innerHTML: "" },
    "#map-location-count": { textContent: "" },
  };
  const map = { remove: () => {} };
  const markerLayer = {
    addTo: () => markerLayer,
    clearLayers: () => { throw new Error("renderer unavailable"); },
  };
  const originalDocument = global.document;
  const originalLeaflet = global.L;
  const originalWarn = console.warn;
  global.document = { querySelector: (selector) => hosts[selector] || null };
  global.L = {
    map: () => map,
    tileLayer: () => ({ addTo: () => {} }),
    layerGroup: () => markerLayer,
  };
  console.warn = () => {};

  try {
    setupMap();
    assert.doesNotThrow(() => renderMap([]));
    assert.match(hosts["#location-map"].innerHTML, /location table remains fully usable/i);
    assert.match(hosts["#map-location-count"].textContent, /table still active/i);
  } finally {
    if (originalDocument === undefined) delete global.document;
    else global.document = originalDocument;
    if (originalLeaflet === undefined) delete global.L;
    else global.L = originalLeaflet;
    console.warn = originalWarn;
  }
});
