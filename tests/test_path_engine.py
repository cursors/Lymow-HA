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


def test_isolated_spike_does_not_split_the_run():
    # A single point ~3.4-3.5m from both neighbors, whose neighbors are only
    # ~0.07m from each other — the exact signature found in production data
    # (a lone bad/misordered breadcrumb "flying away" and snapping back).
    # It should be dropped entirely, not treated as two real gap-splits.
    pts = [
        {"x": 0.0, "y": 0.0},
        {"x": 0.1, "y": 0.0},
        {"x": 3.5, "y": 0.0},
        {"x": 0.15, "y": 0.05},
        {"x": 0.2, "y": 0.05},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert len(runs) == 1
    (run,) = runs
    assert (3.5, 0.0) not in run
    assert run == [(0.0, 0.0), (0.1, 0.0), (0.15, 0.05), (0.2, 0.05)]


def test_consecutive_spikes_are_both_removed():
    # Two isolated points in a row, both far from the real path on either side,
    # but the real path's two flanking points are close to each other.
    pts = [
        {"x": 0.0, "y": 0.0},
        {"x": 3.5, "y": 0.0},
        {"x": 3.6, "y": 3.5},
        {"x": 0.05, "y": 0.0},
        {"x": 0.1, "y": 0.0},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert len(runs) == 1
    (run,) = runs
    assert (3.5, 0.0) not in run
    assert (3.6, 3.5) not in run
    assert run == [(0.0, 0.0), (0.05, 0.0), (0.1, 0.0)]


def test_genuine_transit_gap_still_splits():
    # A real transit hop — the far side does NOT snap back close to the near
    # side — must still produce two separate runs, not get merged away.
    pts = [
        {"x": 0.0, "y": 0.0}, {"x": 0.1, "y": 0.0}, {"x": 0.2, "y": 0.0},
        {"x": 5.2, "y": 0.0}, {"x": 5.3, "y": 0.0}, {"x": 5.4, "y": 0.0},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert len(runs) == 2


def test_genuine_sparse_midrow_stretch_is_stitched_not_dropped():
    # A brief comms hiccup mid-row: real, monotonic forward progress along the
    # row, but each point during the hiccup lands >2m from its neighbor (so
    # each becomes its own 1-point run). The bracket distance across the whole
    # stretch is large (real progress, not a "there and back"), so it must NOT
    # be merged as an artifact — but it also shouldn't just vanish (today: each
    # 1-point run gets dropped, leaving an unrepresented gap in a straight
    # row). It should survive as its own sparse-but-real run.
    pts = [
        {"x": 0.0, "y": 0.0}, {"x": 0.1, "y": 0.0}, {"x": 0.2, "y": 0.0},
        {"x": 3.0, "y": 0.0}, {"x": 6.0, "y": 0.0},
        {"x": 9.0, "y": 0.0}, {"x": 9.1, "y": 0.0}, {"x": 9.2, "y": 0.0},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert len(runs) == 3
    assert runs[1] == [(3.0, 0.0), (6.0, 0.0)]


def test_truly_isolated_single_point_with_no_sibling_still_dropped():
    # A stretch of exactly one point (no neighboring 1-point runs to stitch
    # with) still can't form a line on its own — must still be dropped, same
    # as before this stitching behavior existed.
    pts = [
        {"x": 0.0, "y": 0.0}, {"x": 0.1, "y": 0.0}, {"x": 0.2, "y": 0.0},
        {"x": 5.0, "y": 0.0},
        {"x": 10.0, "y": 0.0}, {"x": 10.1, "y": 0.0}, {"x": 10.2, "y": 0.0},
    ]
    runs = build_coverage_track(pts, gap_m=2.0)
    assert len(runs) == 2
    assert (5.0, 0.0) not in [p for r in runs for p in r]
