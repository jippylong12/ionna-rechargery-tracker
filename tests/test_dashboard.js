const test = require("node:test");
const assert = require("node:assert/strict");

const {
  compareLocations,
  locationCoordinates,
  mapStatusColor,
  nextSort,
  safeExternalUrl,
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
