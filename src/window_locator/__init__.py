# -*- coding: utf-8 -*-
"""window-locator —— Windows 显示器几何与前台窗口查询（物理像素）。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

本包解决两件常被写错的事：

1. **显示器几何用物理像素，不经过 Qt 的逻辑坐标换算。** 混合 DPI 的多屏环境下，
   "逻辑坐标 × 本屏 dpr"是错的（各屏 dpr 不同，而逻辑原点是全局的）。
   直接问 Windows 要 ``GetMonitorInfoW`` 的物理矩形就没有这个换算。
2. **前台窗口矩形要先设 DPI 感知再取。** ``GetWindowRect`` 的返回值取决于
   调用线程的 DPI 感知级别；在 Qt/WPF 线程里默认拿到的是虚拟化后的值，
   拿去和物理像素的屏幕矩形比面积会得到随机结果。

零运行时依赖（ctypes 是标准库）。非 Windows 上可 import，调用时抛
:class:`Win32Unavailable` —— 这样 CI 和类型检查在任何平台都能跑。

快速上手::

    from window_locator import all_monitors, foreground_window_info, is_self

    for m in all_monitors():
        print(m.device, m.bounds, m.work, "primary" if m.is_primary else "")

    info = foreground_window_info()
    if info["is_self"]:
        ...          # 别截自己
"""
from __future__ import annotations

from ._win32 import (
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
    Win32Unavailable,
    foreground_window,
    foreground_window_rect,
    foreground_window_title,
    is_maximized,
    is_windows,
    thread_dpi_awareness,
    window_process_id,
    window_rect,
    window_title,
)
from .coverage import (
    DEFAULT_COVERAGE_RATIO,
    DEFAULT_MAXIMIZED_RATIO,
    coverage_ratio,
    covers,
    is_fullscreen_like,
)
from .foreground import (
    foreground_covers_monitor,
    foreground_is_self,
    foreground_matches_any,
    foreground_snapshot,
    foreground_window_info,
    fullscreen_monitor,
    self_process_id,
)
from .monitors import (
    MONITORINFOF_PRIMARY,
    Monitor,
    all_monitors,
    monitor_at_point,
    monitor_for_rect,
    primary_monitor,
    virtual_desktop,
    virtual_desktop_rect,
)
from .rect import (
    Rect,
    intersection,
    intersection_area,
    is_degenerate,
    rect_from_any,
    union,
)

__version__ = "0.1.0"

#: ``foreground_is_self`` 的短别名，读起来更顺
is_self = foreground_is_self

__all__ = [
    "DEFAULT_COVERAGE_RATIO",
    "DEFAULT_MAXIMIZED_RATIO",
    "DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2",
    "MONITORINFOF_PRIMARY",
    "Monitor",
    "Rect",
    "Win32Unavailable",
    "__version__",
    "all_monitors",
    "coverage_ratio",
    "covers",
    "foreground_covers_monitor",
    "foreground_is_self",
    "foreground_matches_any",
    "foreground_snapshot",
    "foreground_window",
    "foreground_window_info",
    "foreground_window_rect",
    "foreground_window_title",
    "fullscreen_monitor",
    "intersection",
    "intersection_area",
    "is_degenerate",
    "is_fullscreen_like",
    "is_maximized",
    "is_self",
    "is_windows",
    "monitor_at_point",
    "monitor_for_rect",
    "primary_monitor",
    "rect_from_any",
    "self_process_id",
    "thread_dpi_awareness",
    "union",
    "virtual_desktop",
    "virtual_desktop_rect",
    "window_process_id",
    "window_rect",
    "window_title",
]
