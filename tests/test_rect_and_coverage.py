# -*- coding: utf-8 -*-
"""Rect 与覆盖率判定：纯逻辑，任何平台都能跑。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from window_locator import (  # noqa: E402
    DEFAULT_COVERAGE_RATIO,
    DEFAULT_MAXIMIZED_RATIO,
    Rect,
    coverage_ratio,
    intersection,
    intersection_area,
    is_degenerate,
    is_fullscreen_like,
    rect_from_any,
    union,
)

FULL_HD = Rect(0, 0, 1920, 1080)


class TestConstruct:
    def test_xywh(self):
        r = Rect.from_xywh(10, 20, 30, 40)
        assert r.ltrb == (10, 20, 40, 60)
        assert r.width == 30 and r.height == 40

    def test_ltrb(self):
        assert Rect.from_ltrb(1, 2, 3, 4).ltrb == (1, 2, 3, 4)

    def test_around_point_radius_zero(self):
        r = Rect.around_point(5, 7)
        assert r.ltrb == (5, 7, 6, 8)

    def test_around_point_with_radius(self):
        r = Rect.around_point(5, 7, 2)
        assert r.contains_point(5, 7)
        assert r.width == 5 and r.height == 5

    def test_frozen(self):
        with pytest.raises(Exception):
            FULL_HD.x = 1  # type: ignore[misc]


class TestFromRectLike:
    def test_rect_passthrough(self):
        assert rect_from_any(FULL_HD) is FULL_HD

    def test_tuple(self):
        assert rect_from_any((1, 2, 3, 4)).ltrb == (1, 2, 3, 4)

    def test_list(self):
        assert rect_from_any([1, 2, 3, 4]).ltrb == (1, 2, 3, 4)

    def test_dict_ltrb(self):
        r = rect_from_any({"left": 1, "top": 2, "right": 3, "bottom": 4})
        assert r.ltrb == (1, 2, 3, 4)

    def test_dict_xywh(self):
        r = rect_from_any({"x": 1, "y": 2, "width": 3, "height": 4})
        assert r.ltrb == (1, 2, 4, 6)

    def test_qt_like_ltrb(self):
        class QtLike:
            def left(self): return 1
            def top(self): return 2
            def right(self): return 3
            def bottom(self): return 4

        assert rect_from_any(QtLike()).ltrb == (1, 2, 3, 4)

    def test_qt_like_xywh(self):
        class QtLike:
            def x(self): return 10
            def y(self): return 20
            def width(self): return 30
            def height(self): return 40

        assert rect_from_any(QtLike()).ltrb == (10, 20, 40, 60)

    def test_unconvertible_raises(self):
        with pytest.raises(TypeError):
            rect_from_any(object())


class TestDerived:
    def test_area(self):
        assert FULL_HD.area == 1920 * 1080

    def test_empty_when_degenerate(self):
        assert Rect(5, 5, 5, 10).is_empty
        assert Rect(5, 5, 10, 5).is_empty
        assert not FULL_HD.is_empty

    def test_negative_extent_clamped_to_zero(self):
        r = Rect(100, 100, 50, 50)
        assert r.width == 0 and r.height == 0

    def test_center(self):
        assert FULL_HD.center == (960, 540)


class TestTransforms:
    def test_offset(self):
        assert FULL_HD.offset(10, -20).ltrb == (10, -20, 1930, 1060)

    def test_scale(self):
        r = Rect(0, 0, 100, 50).scale(2.0)
        assert r.ltrb == (0, 0, 200, 100)

    def test_scale_fractional_rounds(self):
        # round(151.5) = 152（Python 银行家舍入），round(76.5) = 76
        r = Rect(0, 0, 101, 51).scale(1.5)
        assert (r.width, r.height) == (152, 76)

    def test_clip(self):
        assert Rect(-10, -10, 50, 50).clip(FULL_HD).ltrb == (0, 0, 50, 50)

    def test_clip_outside_returns_empty(self):
        r = Rect(3000, 3000, 3100, 3100).clip(FULL_HD)
        assert r.is_empty


class TestPredicates:
    def test_contains_point(self):
        assert FULL_HD.contains_point(0, 0)
        assert FULL_HD.contains_point(1919, 1079)
        assert not FULL_HD.contains_point(1920, 1079)  # 右开
        assert not FULL_HD.contains_point(-1, 0)

    def test_contains_rect(self):
        assert FULL_HD.contains_rect(Rect(10, 10, 20, 20))
        assert not FULL_HD.contains_rect(Rect(-1, 0, 20, 20))

    def test_intersects(self):
        assert FULL_HD.intersects(Rect(1000, 500, 3000, 2000))
        assert not FULL_HD.intersects(Rect(2000, 2000, 2100, 2100))

    def test_coverage_of_returns_one_for_empty_other(self):
        # "空的东西被覆盖了多少" -> 1.0（trivially covered）
        assert FULL_HD.coverage_of(Rect(0, 0, 0, 0)) == 1.0

    def test_intersection_area(self):
        assert FULL_HD.intersection_area(Rect(1000, 500, 3000, 2000)) == 920 * 580


class TestModuleFunctions:
    def test_intersection_none_when_disjoint(self):
        assert intersection(FULL_HD, Rect(5000, 5000, 5100, 5100)) is None

    def test_intersection_touching_edges_is_none(self):
        # 相邻但不重叠 -> None（右开区间）
        assert intersection(Rect(0, 0, 10, 10), Rect(10, 0, 20, 10)) is None

    def test_intersection_area_disjoint_zero(self):
        assert intersection_area(FULL_HD, Rect(5000, 5000, 5100, 5100)) == 0

    def test_union(self):
        u = union([Rect(0, 0, 10, 10), Rect(20, 20, 30, 30)])
        assert u is not None and u.ltrb == (0, 0, 30, 30)

    def test_union_empty(self):
        assert union([]) is None

    def test_union_negative_coords(self):
        # 副屏在主屏左侧 -> 负坐标，这是真实场景
        u = union([Rect(-1920, 0, 0, 1080), FULL_HD])
        assert u is not None and u.ltrb == (-1920, 0, 1920, 1080)

    @pytest.mark.parametrize("bad", [None, Rect(0, 0, 0, 10), Rect(5, 5, 5, 5)])
    def test_is_degenerate(self, bad):
        assert is_degenerate(bad) is True

    def test_is_degenerate_false(self):
        assert is_degenerate(FULL_HD) is False


class TestCoverage:
    def test_exact_match(self):
        assert coverage_ratio(FULL_HD, FULL_HD) == 1.0

    def test_half(self):
        assert coverage_ratio(Rect(0, 0, 960, 1080), FULL_HD) == pytest.approx(0.5)

    def test_none_inputs(self):
        assert coverage_ratio(None, FULL_HD) == 0.0
        assert coverage_ratio(FULL_HD, None) == 0.0

    def test_empty_window_is_zero(self):
        # 方向很重要：空窗口盖不住屏幕 -> 0.0
        assert coverage_ratio(Rect(0, 0, 0, 0), FULL_HD) == 0.0

    def test_empty_monitor_is_zero(self):
        assert coverage_ratio(FULL_HD, Rect(0, 0, 0, 0)) == 0.0

    def test_window_larger_than_monitor_caps_at_one(self):
        assert coverage_ratio(Rect(-500, -500, 3000, 3000), FULL_HD) == 1.0

    def test_window_outside_is_zero(self):
        assert coverage_ratio(Rect(5000, 5000, 6000, 6000), FULL_HD) == 0.0

    def test_partial_overlap_is_fraction_not_iou(self):
        # 窗口只盖住右半屏 -> 0.5（不是 IoU，那还要算上窗口在屏外的部分）
        assert coverage_ratio(Rect(960, 0, 5000, 1080), FULL_HD) == pytest.approx(0.5)


class TestIsFullscreenLike:
    def test_full_cover(self):
        assert is_fullscreen_like(FULL_HD, FULL_HD) is True

    def test_just_above_threshold(self):
        w = Rect(0, 0, int(1920 * (DEFAULT_COVERAGE_RATIO + 0.02)), 1080)
        assert is_fullscreen_like(w, FULL_HD) is True

    def test_just_below_threshold(self):
        # 注意 int() 是**向下**取整：0.88 阈值下 1689/1920 = 0.8797 < 0.88，
        # 所以这里刻意用 0.88 减一点，保证确实落在阈值下方
        w = Rect(0, 0, int(1920 * (DEFAULT_COVERAGE_RATIO - 0.02)), 1080)
        assert is_fullscreen_like(w, FULL_HD) is False

    def test_threshold_is_inclusive(self):
        # 用干净的阈值验证 ">= threshold" 是闭区间，避开 0.88×1080 的取整噪声
        half = Rect(0, 0, 960, 1080)
        assert coverage_ratio(half, FULL_HD) == 0.5
        assert is_fullscreen_like(half, FULL_HD, threshold=0.5) is True
        assert is_fullscreen_like(half, FULL_HD, threshold=0.5000001) is False

    def test_lower_threshold_accepts_a_smaller_window(self):
        # Windows 最大化会留边框，所以 maximized 用更低的下限（0.75）。
        # 注意面积比是**二维**的：两个方向都乘 0.8 只剩 0.64，不是 0.8。
        # 这里只压宽度，得到干净的 0.8。
        w = Rect(0, 0, int(1920 * 0.8), 1080)
        ratio = coverage_ratio(w, FULL_HD)
        assert ratio == pytest.approx(0.8)
        assert is_fullscreen_like(w, FULL_HD, maximized=False) is False
        assert is_fullscreen_like(w, FULL_HD, maximized=True) is True

    def test_near_full_window_is_fullscreen_either_way(self):
        # 只差几个像素边框的窗口，两种判定都该算全屏
        w = Rect(8, 8, 1912, 1072)
        assert is_fullscreen_like(w, FULL_HD, maximized=False) is True
        assert is_fullscreen_like(w, FULL_HD, maximized=True) is True

    def test_custom_thresholds(self):
        w = Rect(0, 0, 960, 1080)
        assert is_fullscreen_like(w, FULL_HD, coverage_ratio=0.5) is True
        assert is_fullscreen_like(w, FULL_HD, coverage_ratio=0.6) is False

    def test_none_inputs(self):
        assert is_fullscreen_like(None, FULL_HD) is False
        assert is_fullscreen_like(FULL_HD, None) is False
