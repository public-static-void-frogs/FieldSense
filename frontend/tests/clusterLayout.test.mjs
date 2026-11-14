import assert from 'node:assert/strict';
import test from 'node:test';
import {
  clusterMarkerSize,
  clusterMinSpacing,
  layoutMapClusters,
} from '../src/features/maps/utils/clusterLayout.ts';

const project = (x, y) => ({ x, y });
const group = (x, y, count = 1) => ({
  type: 'Feature',
  id: `${x},${y}`,
  geometry: { type: 'Point', coordinates: [x, y] },
  properties: { kind: 'cluster', count, area: count * 2, bounds: [x - 1, y - 1, x + 1, y + 1] },
});
function assertSpaced(markers) {
  for (let first = 0; first < markers.length; first += 1) {
    for (let second = first + 1; second < markers.length; second += 1) {
      assert.ok(
        Math.hypot(markers[first].x - markers[second].x, markers[first].y - markers[second].y) >=
          clusterMinSpacing - 1e-8,
      );
    }
  }
}

test('a dense 600-group response leaves open map space without losing counts or extents', () => {
  const features = Array.from({ length: 600 }, (_, index) =>
    group(20 + (index % 30) * 39, 15 + Math.floor(index / 30) * 30, 200 + index),
  );
  const markers = layoutMapClusters(features, project, {
    left: 0,
    top: 0,
    width: 1180,
    height: 625,
  });
  assert.ok(markers.length < 50);
  assert.equal(
    markers.reduce((sum, item) => sum + item.count, 0),
    features.reduce((sum, item) => sum + item.properties.count, 0),
  );
  assert.equal(
    markers.reduce((sum, item) => sum + item.area, 0),
    2 * (600 * 200 + (599 * 600) / 2),
  );
  assert.deepEqual(
    [
      Math.min(...markers.map((item) => item.bounds[0])),
      Math.min(...markers.map((item) => item.bounds[1])),
      Math.max(...markers.map((item) => item.bounds[2])),
      Math.max(...markers.map((item) => item.bounds[3])),
    ],
    [19, 14, 1152, 586],
  );
  assertSpaced(markers);
  const coveredFraction = (markers.length * Math.PI * (clusterMarkerSize / 2) ** 2) / (1180 * 625);
  assert.ok(coveredFraction < 0.09);
});

test('neighboring bins and clamped edge groups cannot produce colliding badges', () => {
  const features = [group(159, 160, 4), group(161, 160, 6), group(250, 160, 2), group(319, 160, 3)];
  const markers = layoutMapClusters(features, project, {
    left: 0,
    top: 0,
    width: 320,
    height: 320,
  });
  assert.equal(
    markers.reduce((sum, item) => sum + item.count, 0),
    15,
  );
  assertSpaced(markers);
  for (const item of markers) {
    assert.ok(item.x >= 32 && item.x <= 288);
    assert.ok(item.y >= 32 && item.y <= 288);
  }
});

test('phone layout reduces group density while preserving all visible source counts', () => {
  const features = Array.from({ length: 300 }, (_, index) =>
    group(8 + (index % 10) * 32, 8 + Math.floor(index / 10) * 28, 20),
  );
  const markers = layoutMapClusters(features, project, {
    left: 0,
    top: 0,
    width: 314,
    height: 844,
  });
  assert.ok(markers.length <= 18);
  assert.equal(
    markers.reduce((sum, item) => sum + item.count, 0),
    6000,
  );
  assertSpaced(markers);
});

test('small pans retain world-anchored groups and offscreen previous-view groups are excluded', () => {
  const features = [group(400, 400, 2), group(430, 420, 3), group(900, 900, 7)];
  const first = layoutMapClusters(features, project, {
    left: 200,
    top: 200,
    width: 600,
    height: 600,
  });
  const panned = layoutMapClusters(features, project, {
    left: 220,
    top: 230,
    width: 600,
    height: 600,
  });
  assert.deepEqual(first, panned);
  assert.equal(first.length, 1);
  assert.equal(first[0].count, 5);
});
