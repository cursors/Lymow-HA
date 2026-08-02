# Coverage Track GeoJSON Attribute — Design

Minimum-viable exposure of the mower's actual driven path as a new `geojson_coverage_track`
attribute, so a separate Lovelace map card (Geodroid) can draw real path lines instead of the
filled `geojson_mowed_area` polygon hull it reads today.

## Goal

`geojson_mowed_area` (`sensor.py`) is a filled polygon — it shows *where* was covered but not
the striped/lined path shape the diagnostic camera PNG already renders (`map_render.py`'s
Coverage styles). That look is driven by `breadcrumb_track` (`BreadcrumbAccumulator`,
`path_engine.py`), which is internal state today, consumed only by the PNG renderer — never
exposed as an entity attribute. This adds a small, decimated, line-geometry version of it as a
new `geojson_*` attribute, for live vector rendering elsewhere.

Scope for v1: try it locally, see if the track shape is useful to Geodroid before investing in
anything beyond plain geometry (no per-point telemetry/pass styling, no config toggle).

## Why the raw breadcrumb track can't be exposed directly

`BreadcrumbAccumulator` holds up to `max_points` (25,000, `path_engine.py:249`) points, each
`{x, y, +telemetry}` (~120-150 bytes/point as JSON) — a full session could be several MB.
`simplify_path()` (`path_engine.py:25`, Visvalingam-Whyatt curvature-aware thinning, already
used at ~2500-point budgets for PNG rendering) solves the size problem but is explicitly
documented "for RENDERING ONLY" and returns whatever element type it's given — it needs a
geometry-only (no telemetry) input to produce a safe-to-expose output.

## Data flow

```
BreadcrumbAccumulator.points (session-scoped, path_engine.py, resets on session_key change)
        │  (coordinator._state["breadcrumb_track"])
        ▼
path_engine.build_coverage_track(points, budget, gap_m)        ← NEW pure function
        │  1. strip telemetry → (x, y) tuples only
        │  2. split into runs wherever consecutive points exceed gap_m
        │     (same technique as the Gradient style's gap-split, map_render.py:852-859 —
        │      re-derived here, not shared code; see "What this does NOT touch" below)
        │  3. proportionally simplify_path() each run to fit the total point budget
        │     (same proportional-allocation formula as Gradient, map_render.py:861)
        │  4. drop any run left with < 2 points (can't form a LineString)
        ▼
returns list[list[(x, y)]] — one point list per run
        ▼
sensor.py LymowMapGeoJsonSensor — ENU→WGS84 convert each run's points (calls the existing
        │                          _enu_to_latlon directly; NOT _pts_to_ring, which auto-closes
        │                          rings for polygons — wrong for a line)
        ▼
extra_state_attributes["geojson_coverage_track"] = FeatureCollection, 1 Feature, MultiLineString
```

## New subsystem: `path_engine.build_coverage_track()`

Pure geometry function, alongside `simplify_path`/`segment_rows`/`BreadcrumbAccumulator` in
`path_engine.py` — no HA/GeoJSON concerns, matching this repo's existing separation
(`path_engine.py` = geometry, `sensor.py` = HA/GeoJSON glue, `map_render.py` = rendering only).

- **Budget:** `COVERAGE_TRACK_BUDGET = 800` (module constant, easy to retune while trying this
  out locally).
- **Gap threshold:** `COVERAGE_TRACK_GAP_M = 2.0` — its own constant, not shared with
  `map_render.py`'s `GAP_M2`. Same numeric behavior as the Gradient style's gap-split, but
  defined independently (see below).

## GeoJSON shape

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "properties": {"type": "coverage_track", "run_count": 7, "point_count": 743},
    "geometry": {
      "type": "MultiLineString",
      "coordinates": [[[lon, lat], ...], [[lon, lat], ...], ...]
    }
  }]
}
```

Same `has_origin` fallback as sibling attributes: WGS84 coordinates when an ENU origin is
known, else raw `(x, y)` with `"_crs": "ENU_metres"` on the geometry.

## Integration point (`sensor.py`, `LymowMapGeoJsonSensor`)

Three additive touches, no restructuring of the existing property:

1. Add `"geojson_coverage_track"` to the existing `_unrecorded_attributes` frozenset.
2. Add one element to the existing `cache_key` tuple: `len(breadcrumb_track) // 15`. This gives
   the point-count throttle for free by reusing the cache-skip branch that's already there — no
   new counter/gate logic needed. Side effect: crossing that threshold invalidates the whole
   cached dict (zone/mowed-area features rebuild too), but that's the same recompute cost class
   that already happens routinely today, since `mowed_area_points_count` changes on nearly every
   tick during active mowing — not a new cost category, just one more trigger of it.
3. A new code block (net-new lines) that calls `build_coverage_track()`, converts each run, and
   adds `geojson_coverage_track`, `coverage_track_run_count`, `coverage_track_point_count` to the
   `result` dict — mirroring the existing `mowed_area_polygon_count`/`mowed_area_points_count`
   pair.

## Update cadence

Throttled: recomputes only every 15 new breadcrumb points (via the cache-key bucket above), the
same cadence as the existing `_breadcrumb_save_counter % 15` disk-persistence gate
(`coordinator.py:1462`) — reusing an already-tuned number, not inventing a new one. At the
~0.6 s/point breadcrumb append rate, that's ~9 s of lag between the mower's real position and
the published track during active mowing — acceptable for a coverage-shape overlay (not a
live position indicator; `geojson_robot` already covers that need every tick).

## Session scoping

Free. `breadcrumb_track` already resets on session-key change inside
`BreadcrumbAccumulator.reset()` (`path_engine.py:255-257`); the new attribute just reads
whatever is currently in that list, so it's naturally short/empty at the start of a new mow.

## Payload size

At `COVERAGE_TRACK_BUDGET = 800` with 8-decimal lat/lon (matching the existing
`_pts_to_ring`/coordinate convention, `sensor.py:1057`), each coordinate pair is ~27-28 bytes,
so 800 points is **~22 KB** — over the recorder's 16 KB attribute cap, not under it.

That's fine, not a problem to solve: `geojson_mowed_area`/`geojson_zones` already exceed 16 KB
on big maps today, which is the literal reason `_unrecorded_attributes` exists
(`sensor.py:1393-1400`) — to stop the recorder from warning about / storing history for
live-only map attributes, not to keep them under the cap. `geojson_coverage_track` goes in that
same set for the same reason.

The number that actually matters is websocket push size × push frequency (dashboard bandwidth).
~22 KB pushed at most every 15 new breadcrumb points (~9 s during active mowing) is the same
order of magnitude as what `geojson_mowed_area` already pushes on essentially every coordinator
tick with **no** throttle — so this is no worse than existing behavior, and the explicit
throttle makes it better.

## What this does NOT touch

Deliberately avoids editing `map_render.py` or `sensor.py`'s existing helpers beyond the three
additive touches above:

- `map_render.py`'s `GAP_M2` (Gradient style, `map_render.py:853`) is Nate's code, last touched
  in his coverage PR (#33) and not something this feature needs to change. `COVERAGE_TRACK_GAP_M`
  is a separate constant with the same value, not a shared one — a comment cross-references
  `map_render.py:853` for anyone wondering why the numbers match, instead of hoisting a shared
  constant into his file.
- `_pts_to_ring` (`sensor.py:1051`) is left untouched (it auto-closes rings, which a line must
  not do); the new code calls `_enu_to_latlon` directly instead.
- `BreadcrumbAccumulator`'s persistence format (`to_dict`/`load_dict`) is unchanged — this reads
  `breadcrumb_track` as-is.

## Non-goals for v1

- Per-point telemetry or pass-classification styling (`_classify_passes`, `map_render.py:307`).
  Revisit only if the plain track shape proves useful.
- Any config toggle/select — this is being tried out locally first, not shipped as a
  user-facing option.
- All-time/cross-session history — session-scoped only, matching `BreadcrumbAccumulator`.

## Out of scope

Geodroid-side rendering (a separate repo/PR). This design only covers what Lymow-HA exposes.
