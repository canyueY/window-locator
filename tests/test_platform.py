# -*- coding: utf-8 -*-
"""平台相关部分：DPI 上下文、Win32 查询、显示器枚举。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

非 Windows 上这个文件仍然要能收集并跑一部分用例 —— 那正是"本包在 Linux CI
上可 import"这条承诺的验证。真机相关的用例用 ``skipif`` 跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import window_locator as wl  # noqa: E402
from window_locator import _win32  # noqa: E402

ON_WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not ON_WINDOWS, reason="需要 Windows")
posix_only = pytest.mark.skipif(ON_WINDOWS, reason="只在非 Windows 上有意义")


class TestImportSafety:
    def test_package_imports_on_any_platform(self):
        # 这是本包的核心承诺：非 Windows 上 import 不炸，调用时才抛
        assert wl.__version__
        assert isinstance(wl.is_windows(), bool)

    def test_geometry_math_works_everywhere(self):
        # 纯逻辑层不依赖平台
        assert wl.coverage_ratio(wl.Rect(0, 0, 10, 10), wl.Rect(0, 0, 10, 10)) == 1.0

    @posix_only
    def test_win32_calls_raise_unavailable(self):
        with pytest.raises(wl.Win32Unavailable):
            _win32.foreground_window()
        with pytest.raises(wl.Win32Unavailable):
            wl.all_monitors()

    @posix_only
    def test_dpi_context_is_noop(self):
        with wl.thread_dpi_awareness() as switched:
            assert switched is False  # 没真的切换过，不假装


class TestDpiAwareness:
    """DPI 上下文管理器的行为。

    ⚠️ 这里钉住的是一个**修掉的真实 bug**：原实现用
    ``try: return fn() finally: restore() except: return fn()`` 的结构，
    回调抛异常时会被 ``except`` 分支**第二次执行**。改成上下文管理器后
    回调只会跑一次。
    """

    def test_body_runs_exactly_once(self):
        calls = []
        with wl.thread_dpi_awareness():
            calls.append(1)
        assert calls == [1]

    def test_exception_propagates_and_body_runs_once(self):
        calls = []

        def body():
            calls.append(1)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            with wl.thread_dpi_awareness():
                body()
        # 关键断言：只跑了一次，不是两次
        assert calls == [1]

    def test_exception_is_not_swallowed(self):
        with pytest.raises(RuntimeError):
            with wl.thread_dpi_awareness():
                raise RuntimeError("must propagate")

    def test_nested_contexts(self):
        with wl.thread_dpi_awareness():
            with wl.thread_dpi_awareness():
                pass

    @windows_only
    def test_reports_switched_on_windows(self):
        with wl.thread_dpi_awareness() as switched:
            # 现代 Windows 上应该真的切换了
            assert switched is True

    @windows_only
    def test_restores_after_exception(self):
        # 抛异常后也要留下一个可用的 DPI 状态，不能把线程搞坏
        with pytest.raises(ValueError):
            with wl.thread_dpi_awareness():
                raise ValueError
        with wl.thread_dpi_awareness() as again:
            assert again is True


@windows_only
class TestMonitorsLive:
    def test_enumerates_at_least_one(self):
        monitors = wl.all_monitors()
        assert len(monitors) >= 1

    def test_exactly_one_primary(self):
        primaries = [m for m in wl.all_monitors() if m.is_primary]
        assert len(primaries) == 1

    def test_primary_monitor_helper_matches(self):
        p = wl.primary_monitor()
        assert p is not None and p.is_primary

    def test_primary_bounds_start_at_origin(self):
        # Windows 保证主显示器左上角在虚拟桌面原点
        p = wl.primary_monitor()
        assert p is not None
        assert (p.bounds.x, p.bounds.y) == (0, 0)
        assert p.bounds.width > 0 and p.bounds.height > 0

    def test_work_area_inside_bounds(self):
        for m in wl.all_monitors():
            assert m.bounds.contains_rect(m.work), m.device

    def test_device_names_unique(self):
        names = [m.device for m in wl.all_monitors()]
        assert len(names) == len(set(names))

    def test_scale_factor_sane(self):
        for m in wl.all_monitors():
            assert 1.0 <= m.scale_factor <= 4.0

    def test_monitor_at_primary_origin(self):
        m = wl.monitor_at_point(1, 1)
        assert m is not None and m.is_primary

    def test_monitor_at_far_away_point_is_none(self):
        # 极远的点不属于任何显示器（多屏之间的空隙同理）
        assert wl.monitor_at_point(200000, 200000) is None

    def test_monitor_for_rect_picks_overlap(self):
        monitors = wl.all_monitors()
        m = wl.monitor_for_rect(monitors[0].bounds)
        assert m is not None
        assert m.device == monitors[0].device

    def test_monitor_for_rect_none_inputs(self):
        assert wl.monitor_for_rect(None) is None
        assert wl.monitor_for_rect(wl.Rect(0, 0, 0, 0)) is None

    def test_virtual_desktop_covers_all(self):
        vd = wl.virtual_desktop_rect()
        assert vd is not None
        for m in wl.all_monitors():
            assert vd.contains_rect(m.bounds)

    def test_as_dict_json_safe(self):
        import json

        for m in wl.all_monitors():
            json.dumps(m.as_dict())


@windows_only
class TestForegroundLive:
    def test_foreground_window_returns_handle(self):
        # 测试进程通常有前台窗口，但也可能是 0（无头会话）—— 不断言非零
        hwnd = wl.foreground_window()
        assert isinstance(hwnd, int)

    def test_window_info_shape(self):
        info = wl.foreground_window_info()
        assert set(info) == {"hwnd", "title", "rect", "maximized", "pid", "is_self"}

    def test_self_process_id(self):
        import os

        assert wl.self_process_id() == os.getpid()

    def test_window_rect_none_for_nonexistent_handle(self):
        # 0 与 None 都表示"前台窗口"（见 _as_hwnd 的说明），
        # 所以这里用一个不存在但非零的句柄来测"取不到"
        assert wl.window_rect(0xDEADBEEF) is None

    def test_window_rect_zero_means_foreground(self):
        # 这是合法调用，不该抛 TypeError
        got = wl.window_rect(0)
        assert got is None or isinstance(got, wl.Rect)

    def test_window_title_empty_for_nonexistent_handle(self):
        assert wl.window_title(0xDEADBEEF) == ""

    def test_is_maximized_false_for_nonexistent_handle(self):
        assert wl.is_maximized(0xDEADBEEF) is False

    def test_window_process_id_zero_for_nonexistent_handle(self):
        assert wl.window_process_id(0xDEADBEEF) == 0

    def test_snapshot_never_raises(self):
        out = wl.foreground_snapshot()
        assert isinstance(out, dict)
        assert "coverage" in out and "fullscreen" in out

    def test_covers_monitor_in_range(self):
        ratio = wl.foreground_covers_monitor()
        assert 0.0 <= ratio <= 1.0

    def test_fullscreen_monitor_returns_monitor_or_none(self):
        got = wl.fullscreen_monitor()
        assert got is None or isinstance(got, wl.Monitor)


class TestBoundedMatch:
    """整词匹配：原实现用裸子串，``finals`` 会命中 ``semifinals``。"""

    @pytest.mark.parametrize(
        "title,keyword,expected",
        [
            ("THE FINALS", "finals", True),
            ("Semifinals Live", "finals", False),
            # 注意 "Discovery Channel" 里 discovery 后面是空格 —— 那是合法的
            # 词边界，所以**应该**命中。"Rediscovery" 才是真阴性。
            ("Discovery Channel", "discovery", True),
            ("Rediscovery", "discovery", False),
            ("Discovery", "discovery", True),
            ("终极角逐 - 游戏", "终极角逐", True),
            ("MyGame v2", "mygame", True),
            ("NotMyGame", "mygame", False),
        ],
    )
    def test_bounded_contains(self, title, keyword, expected, monkeypatch):
        from window_locator import foreground as fg

        monkeypatch.setattr(fg._win32, "foreground_window_title", lambda *a, **k: title)
        assert bool(fg.foreground_matches_any((keyword,))) is expected

    def test_returns_the_matched_keyword(self, monkeypatch):
        from window_locator import foreground as fg

        monkeypatch.setattr(
            fg._win32, "foreground_window_title", lambda *a, **k: "THE FINALS"
        )
        assert fg.foreground_matches_any(("nope", "finals")) == "finals"

    def test_empty_keywords(self, monkeypatch):
        from window_locator import foreground as fg

        monkeypatch.setattr(fg._win32, "foreground_window_title", lambda *a, **k: "x")
        assert fg.foreground_matches_any(()) == ""
        assert fg.foreground_matches_any(None) == ""

    def test_empty_title(self, monkeypatch):
        from window_locator import foreground as fg

        monkeypatch.setattr(fg._win32, "foreground_window_title", lambda *a, **k: "")
        assert fg.foreground_matches_any(("a",)) == ""

    def test_case_sensitivity_flag(self, monkeypatch):
        from window_locator import foreground as fg

        monkeypatch.setattr(
            fg._win32, "foreground_window_title", lambda *a, **k: "THE FINALS"
        )
        assert fg.foreground_matches_any(("finals",)) == "finals"
        assert fg.foreground_matches_any(("finals",), case_sensitive=True) == ""
