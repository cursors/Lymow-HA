# Coverage Track GeoJSON Attribute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a decimated, session-scoped version of the mower's breadcrumb track as a new `geojson_coverage_track` attribute on the `Map GeoJSON` sensor, so map cards can draw the mower's real driven path as a `MultiLineString` instead of the filled `geojson_mowed_area` polygon hull.

**Architecture:** A new pure-geometry function, `build_coverage_track()`, lives in `path_engine.py` next to `simplify_path`/`BreadcrumbAccumulator` — it gap-splits the breadcrumb track into runs and thins each run to a point budget, with zero HA/GeoJSON dependencies. `sensor.py`'s existing `LymowMapGeoJsonSensor.extra_state_attributes` calls it, converts the runs to WGS84 (or ENU fallback, matching sibling attributes), and adds the result to the attribute dict it already builds. No other file is touched.

**Tech Stack:** Python (stdlib only for the new function — `heapq`/`math`, same as the rest of `path_engine.py`), pytest for the new pure-function tests (no `homeassistant` package is installed locally, so the sensor-level wiring is verified manually against a live/deployed HA instance, not with an automated test — this matches the repo's existing convention of zero automated tests for HA entity classes).

## Global Constraints

- Point budget: `COVERAGE_TRACK_BUDGET = 800` (module constant in `path_engine.py`, easy to retune).
- Gap-split threshold: `COVERAGE_TRACK_GAP_M = 2.0` metres — its own constant, NOT shared with `map_render.py`'s `GAP_M2` (see "Do not touch" below).
- Attribute name: `geojson_coverage_track`, plus companion counts `coverage_track_run_count` and `coverage_track_point_count` on the same sensor, mirroring the existing `mowed_area_polygon_count`/`mowed_area_points_count` pair.
- `geojson_coverage_track` MUST be added to `LymowMapGeoJsonSensor._unrecorded_attributes`.
- No config toggle, no select/switch entity — always-on, wired the same way as the other `geojson_*` attributes.
- Throttled recompute: gate on `len(breadcrumb_track) // 15` added to the sensor's existing `cache_key` tuple — no new counter/gate mechanism.
- Session-scoped only — no new persistence; reuses `BreadcrumbAccumulator`'s existing reset-on-session-change behavior as-is.
- **Do not touch** `map_render.py` (Nate's file — the Gradient style's `GAP_M2` stays exactly as-is) or `sensor.py`'s `_pts_to_ring` (it auto-closes rings, which is wrong for a line — call `_enu_to_latlon` directly instead).
- Full design rationale: `docs/COVERAGE_TRACK_DESIGN.md`.

---

## Task 1: `build_coverage_track()` in `path_engine.py`

**Files:**
- Modify: `custom_components/lymow/path_engine.py` (add 2 constants + 1 function, after the `BreadcrumbAccumulator` class at the end of the file)
- Create: `tests/test_path_engine.py`

**Interfaces:**
- Produces: `build_coverage_track(points: list, budget: int = COVERAGE_TRACK_BUDGET, gap_m: float = COVERAGE_TRACK_GAP_M) -> list[list[tuple[float, float]]]` — Task 2 imports and calls this with breadcrumb points (list of `{"x": float, "y": float, ...telemetry}` dicts) and no extra args, relying on the defaults.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_path_engine.py`:

```python
"""Tests for path_engine.build_coverage_track — pure geometry, no HA dependency.

Imported by inserting custom_components/lymow onto sys.path and importing the
bare module name, NOT via `custom_components.lymow.path_engine` — that dotted
path would execute custom_components/lymow/__init__.py first (package import
semantics), which imports `homeassistant`, and that package isn't installed in
this local dev venv (confirmed: `pip show homeassistant` finds nothing here).
path_engine.py itself has zero HA dependency, so this sidesteps the problem
without needing homeassistant installed just to run these tests.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "lymow"))
from path_engine import build_coverage_track  # noqa: E402


def test_empty_input_returns_empty_list():
    assert build_coverage_track([]) == []


def test_single_point_is_dropped():
    # A lone point can't form a line — the run it's in has < 2 points.
    assert build_coverage_track([{"x": 1.0, "y": 2.0}]) == []


def test_two_close_points_form_one_run():
    pts = [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0}]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert runs == [[(0.0, 0.0), (0.5, 0.0)]]


def test_gap_splits_into_multiple_runs():
    # 5 m apart, gap_m=2.0 -> must split into two separate runs.
    pts = [
        {"x": 0.0, "y": 0.0}, {"x": 0.1, "y": 0.0}, {"x": 0.2, "y": 0.0},
        {"x": 5.2, "y": 0.0}, {"x": 5.3, "y": 0.0}, {"x": 5.4, "y": 0.0},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert len(runs) == 2
    assert runs[0] == [(0.0, 0.0), (0.1, 0.0), (0.2, 0.0)]
    assert runs[1] == [(5.2, 0.0), (5.3, 0.0), (5.4, 0.0)]


def test_budget_thinning_keeps_endpoints_and_reduces_count():
    # A long straight run of 100 points thinned to a budget of 10 should keep the
    # first and last points and end up with far fewer than 100.
    pts = [{"x": float(i), "y": 0.0} for i in range(100)]
    runs = build_coverage_track(pts, budget=10, gap_m=2.0)
    assert len(runs) == 1
    (run,) = runs
    assert len(run) <= 10
    assert run[0] == (0.0, 0.0)
    assert run[-1] == (99.0, 0.0)


def test_telemetry_is_stripped_from_output():
    pts = [
        {"x": 0.0, "y": 0.0, "wifi": -55, "rtk_snr": 42},
        {"x": 1.0, "y": 0.0, "wifi": -60, "act": "main"},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert runs == [[(0.0, 0.0), (1.0, 0.0)]]


def test_accepts_tuple_points_too():
    pts = [(0.0, 0.0), (1.0, 0.0)]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert runs == [[(0.0, 0.0), (1.0, 0.0)]]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_path_engine.py -v`
Expected: `ImportError: cannot import name 'build_coverage_track'` (the function doesn't exist yet).

- [ ] **Step 3: Implement `build_coverage_track()`**

Append to the end of `custom_components/lymow/path_engine.py` (after the `BreadcrumbAccumulator` class):

```python
# Render-quality decimation of a breadcrumb track for exporting as a GeoJSON
# MultiLineString (see docs/COVERAGE_TRACK_DESIGN.md). 2.0 m mirrors the Gradient
# coverage style's own gap-split threshold (map_render.py:853, GAP_M2 = 4.0 = 2.0²)
# but is its own constant — this module doesn't import from map_render.py.
COVERAGE_TRACK_GAP_M = 2.0
COVERAGE_TRACK_BUDGET = 800


def build_coverage_track(
    points: list, budget: int = COVERAGE_TRACK_BUDGET, gap_m: float = COVERAGE_TRACK_GAP_M
) -> list[list[tuple[float, float]]]:
    """Decimate a breadcrumb track into gap-split, budget-thinned (x, y) runs.

    Geometry only — telemetry fields on breadcrumb dicts are stripped. Splits into
    runs wherever consecutive points are farther apart than gap_m (so a dock<->zone
    transit hop doesn't draw a line across the yard, same technique as the Gradient
    style), then proportionally simplify_path()s each run so the combined point
    count fits budget while preserving turns. Runs left with fewer than 2 points
    (can't form a line) are dropped, so the result maps directly onto a
    MultiLineString's coordinate arrays.
    """
    pts = [
        (float(p["x"]), float(p["y"])) if isinstance(p, dict) else (float(p[0]), float(p[1]))
        for p in points
    ]
    if not pts:
        return []

    gap2 = gap_m * gap_m
    runs: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for p in pts:
        if cur and (p[0] - cur[-1][0]) ** 2 + (p[1] - cur[-1][1]) ** 2 > gap2:
            runs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        runs.append(cur)

    total = sum(len(r) for r in runs) or 1
    thinned = [
        simplify_path(r, max(2, int(budget * len(r) / total))) if len(r) > 2 else r
        for r in runs
    ]
    return [r for r in thinned if len(r) >= 2]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_path_engine.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/lymow/path_engine.py tests/test_path_engine.py
git commit -m "feat(lymow): add build_coverage_track for decimated breadcrumb path export"
```

---

## Task 2: Wire `geojson_coverage_track` into `LymowMapGeoJsonSensor`

**Files:**
- Modify: `custom_components/lymow/sensor.py:55` (import), `:1397-1400` (`_unrecorded_attributes`), `:1432` (fetch breadcrumb points), `:1446-1453` (`cache_key`), `:1625-1663` (new feature block + `result` dict)

**Interfaces:**
- Consumes: `build_coverage_track(points, budget=COVERAGE_TRACK_BUDGET, gap_m=COVERAGE_TRACK_GAP_M) -> list[list[tuple[float, float]]]` from Task 1.
- Consumes (existing, unmodified): `_enu_to_latlon(east_m, north_m, lat0_deg, lon0_deg) -> tuple[float, float]` (`sensor.py:1019`) — returns `(lat, lon)`.

- [ ] **Step 1: Add the import**

In `custom_components/lymow/sensor.py`, after line 55 (`from .entity_base import LymowEntity`):

```python
from .path_engine import build_coverage_track
```

- [ ] **Step 2: Add the attribute to `_unrecorded_attributes`**

Change (`sensor.py:1397-1400`):

```python
    _unrecorded_attributes = frozenset({
        "geojson", "geojson_zones", "geojson_nogo_zones", "geojson_mowed_area",
        "geojson_dock", "geojson_robot", "geojson_rtk_antenna",
    })
```

to:

```python
    _unrecorded_attributes = frozenset({
        "geojson", "geojson_zones", "geojson_nogo_zones", "geojson_mowed_area",
        "geojson_dock", "geojson_robot", "geojson_rtk_antenna", "geojson_coverage_track",
    })
```

- [ ] **Step 3: Fetch breadcrumb points and extend the cache key**

Change (`sensor.py:1432`, immediately after the `mowed_polygons` line):

```python
        mowed_polygons = data.get("mowed_area_polygons") or []
```

to:

```python
        mowed_polygons = data.get("mowed_area_polygons") or []
        breadcrumb_pts = data.get("breadcrumb_track") or []
```

Then change the `cache_key` tuple (`sensor.py:1446-1453`):

```python
        cache_key = (
            len(zones),
            len(nogo_zones),
            nogo_points_count,
            len(mowed_polygons),
            mowed_area_points_count,
            has_origin,
        )
```

to:

```python
        cache_key = (
            len(zones),
            len(nogo_zones),
            nogo_points_count,
            len(mowed_polygons),
            mowed_area_points_count,
            has_origin,
            len(breadcrumb_pts) // 15,
        )
```

- [ ] **Step 4: Build the coverage-track feature and add it to `result`**

Immediately before `result = {` (`sensor.py:1627`), add:

```python
        # Coverage track — decimated breadcrumb path as a MultiLineString, for map
        # cards that want the mower's real driven path instead of the mowed_area hull.
        # See docs/COVERAGE_TRACK_DESIGN.md.
        coverage_runs = build_coverage_track(breadcrumb_pts)
        coverage_track_point_count = sum(len(r) for r in coverage_runs)
        track_coords: list[list[list[float]]] = []
        for run in coverage_runs:
            if has_origin:
                line = []
                for x, y in run:
                    lat, lon = _enu_to_latlon(x, y, lat0, lon0)
                    line.append([round(lon, 8), round(lat, 8)])
            else:
                line = [[x, y] for x, y in run]
            track_coords.append(line)

        track_geometry: dict[str, Any] = {"type": "MultiLineString", "coordinates": track_coords}
        if not has_origin:
            track_geometry["_crs"] = "ENU_metres"

        coverage_track_features: list[dict[str, Any]] = []
        if coverage_runs:
            coverage_track_features.append({
                "type": "Feature",
                "properties": {
                    "type": "coverage_track",
                    "run_count": len(coverage_runs),
                    "point_count": coverage_track_point_count,
                },
                "geometry": track_geometry,
            })
```

Then add these keys to the existing `result` dict literal (`sensor.py:1627-1662`) — insert after the `"geojson_rtk_antenna"` entry and before `"zone_count"`:

```python
            "geojson_coverage_track": {
                "type": "FeatureCollection",
                "features": coverage_track_features,
            },
```

and insert after the existing `"mowed_area_points_count": mowed_area_points_count,` line:

```python
            "coverage_track_run_count": len(coverage_runs),
            "coverage_track_point_count": coverage_track_point_count,
```

- [ ] **Step 5: Syntax-check**

Run: `.venv/Scripts/python.exe -m py_compile custom_components/lymow/sensor.py`
Expected: no output, exit code 0.

- [ ] **Step 6: Run the Task 1 tests again (regression check)**

Run: `.venv/Scripts/python.exe -m pytest tests/test_path_engine.py -v`
Expected: all 7 tests still PASS (this task doesn't touch `path_engine.py`, so this just confirms nothing else broke).

- [ ] **Step 7: Deploy to the live HA instance and verify manually**

There is no `homeassistant` package installed locally and no existing automated test harness for entity classes in this repo, so this task is verified against the real Unraid HA instance instead of a unit test:

```bash
scp custom_components/lymow/sensor.py root@undercast.local:/mnt/user/appdata/Home-Assistant-Container/custom_components/lymow/sensor.py
scp custom_components/lymow/path_engine.py root@undercast.local:/mnt/user/appdata/Home-Assistant-Container/custom_components/lymow/path_engine.py
```

Then in Home Assistant:
1. Reload the Lymow integration (or restart HA) so the updated files load.
2. Start (or continue) a mow so breadcrumb points accumulate.
3. Open **Developer Tools → States**, find the `Map GeoJSON` sensor, and confirm:
   - `geojson_coverage_track` is present and is a `FeatureCollection` with one `Feature` whose `geometry.type` is `"MultiLineString"`.
   - `coverage_track_run_count` and `coverage_track_point_count` are present and non-zero once the mower has moved.
   - The attribute updates (point count increases) as the mower drives, but not on every single state refresh — confirming the throttle is active.
4. Confirm no new "attribute exceeds maximum size" recorder warning appears in the HA log for this entity.

- [ ] **Step 8: Commit**

```bash
git add custom_components/lymow/sensor.py
git commit -m "feat(lymow): expose geojson_coverage_track attribute on Map GeoJSON sensor"
```
