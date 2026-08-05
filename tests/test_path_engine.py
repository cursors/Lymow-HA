"""Tests for path_engine — pure geometry/state logic, no HA dependency.

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
from path_engine import accumulate_mowed_area_polygons  # noqa: E402


def test_empty_existing_and_empty_segments_returns_empty_list():
    assert accumulate_mowed_area_polygons([], []) == []


def test_first_pull_seeds_the_polygon_set():
    segments = [[[0, 0], [1, 0], [1, 1]]]
    assert accumulate_mowed_area_polygons([], segments) == segments


def test_second_pull_appends_instead_of_replacing():
    # This is the regression case: a later poll that reports fewer/different
    # segments than a prior poll must not erase what was already accumulated.
    first_poll = [[0, 0], [1, 0], [1, 1]]
    second_poll = [[5, 5], [6, 5], [6, 6]]

    after_first = accumulate_mowed_area_polygons([], [first_poll])
    after_second = accumulate_mowed_area_polygons(after_first, [second_poll])

    assert after_second == [first_poll, second_poll]


def test_segments_under_three_points_are_dropped():
    segments = [[[0, 0], [1, 0]], [[0, 0], [1, 0], [1, 1]]]
    assert accumulate_mowed_area_polygons([], segments) == [[[0, 0], [1, 0], [1, 1]]]


def test_non_list_segments_are_ignored():
    segments = ["not-a-segment", [[0, 0], [1, 0], [1, 1]]]
    assert accumulate_mowed_area_polygons([], segments) == [[[0, 0], [1, 0], [1, 1]]]


def test_none_segments_leaves_existing_untouched():
    existing = [[[0, 0], [1, 0], [1, 1]]]
    assert accumulate_mowed_area_polygons(existing, None) == existing


def test_none_existing_is_treated_as_empty():
    segments = [[[0, 0], [1, 0], [1, 1]]]
    assert accumulate_mowed_area_polygons(None, segments) == segments


def test_does_not_mutate_the_existing_list_in_place():
    existing = [[[0, 0], [1, 0], [1, 1]]]
    segments = [[[5, 5], [6, 5], [6, 6]]]
    result = accumulate_mowed_area_polygons(existing, segments)
    assert result is not existing
    assert existing == [[[0, 0], [1, 0], [1, 1]]]
