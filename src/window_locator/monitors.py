# -*- coding: utf-8 -*-
"""显示器几何：``EnumDisplayMonitors`` + ``GetMonitorInfoW``。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

**为什么不用 Qt 的 ``QScreen.geometry()``。** 那是 DPI 缩放后的**逻辑**坐标，
而 Windows 的窗口 API 全部按**物理**像素工作。想把两者对上就得自己乘 dpr ——
于是就有了这类代码里最经典的 bug：

    物理左上角 = 逻辑左上角 × 本屏 dpr

在混合 DPI 的多屏环境下这是错的。屏幕上各屏的 dpr 不同，而 ``QScreen.geometry()``
的 ``x/y`` 是**虚拟桌面范围内的全局逻辑原点**（主屏缩放系数下算出来的），
把它乘**本屏**的 dpr 换算系数不一致，位置就偏了。尺寸倒是可以乘本屏 dpr。

直接问 Windows 要物理矩形（``GetMonitorInfoW``）就没有这个换算，
也不需要在每个调用点记得设 DPI 感知 —— 这是本模块存在的唯一理由。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from ._win32 import Win32Unavailable, is_windows, thread_dpi_awareness
from ._win32 import _user32_lib  # noqa: PLC2701 - 同包内部
from .rect import Rect

__all__ = [
    "MONITORINFOF_PRIMARY",
    "Monitor",
    "all_monitors",
    "monitor_at_point",
    "monitor_for_rect",
    "primary_monitor",
    "virtual_desktop",
    "virtual_desktop_rect",
]

#: ``MONITORINFO.dwFlags`` 里的主显示器标志
MONITORINFOF_PRIMARY = 0x00000001

_CCHDEVICENAME = 32


class _MONITORINFOEXW(ctypes.Structure):
    """``MONITORINFO`` + 显示器设备名。

    ``cbSize`` 必须等于结构体实际大小，否则 ``GetMonitorInfoW`` 会失败并
    让 ``GetLastError`` 报参数错误 —— 这是最常见的调用错误。
    """

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * _CCHDEVICENAME),
    ]


def _monitor_enum_proc():
    """枚举回调类型。

    ``WINFUNCTYPE`` 只在 Windows 上存在，所以要在函数里取而不是模块级 ——
    否则整个包在 Linux 上连 import 都过不去，CI 和类型检查就都跑不了。
    """
    return ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )


def _gdi32_lib():
    """gdi32 只为 ``GetDeviceCaps``（拿 dpr）而加载，可选。"""
    try:
        return ctypes.WinDLL("gdi32", use_last_error=True)  # type: ignore[attr-defined]
    except (OSError, AttributeError):  # pragma: no cover
        return None


@dataclass(frozen=True)
class Monitor:
    """一块显示器。坐标全部是虚拟桌面里的物理像素。"""

    #: 设备名，如 ``\\\\.\\DISPLAY1``
    device: str
    #: 整屏矩形（含任务栏区域）
    bounds: Rect
    #: 工作区矩形（不含任务栏与停靠栏）
    work: Rect
    #: 是否主显示器
    is_primary: bool = False
    #: 系统句柄（诊断用）
    handle: int = 0

    @property
    def width(self) -> int:
        return self.bounds.width

    @property
    def height(self) -> int:
        return self.bounds.height

    @property
    def center(self) -> tuple[int, int]:
        return self.bounds.center

    @property
    def scale_factor(self) -> float:
        """相对 96 DPI 的缩放系数（1.0 / 1.25 / 1.5 / 2.0 …）。

        取不到时返回 1.0。用它可以把物理像素换算回逻辑像素：
        ``logical = physical / scale_factor``。
        """
        gdi = _gdi32_lib()
        if gdi is None or not self.handle:
            return 1.0
        try:
            # MONITORINFOF_PRIMARY 之外没有直接拿 DPI 的老 API 可用；
            # GetDpiForMonitor 在 shcore 里，这里做可选调用。
            shcore = ctypes.WinDLL("shcore", use_last_error=True)  # type: ignore[attr-defined]
            dpi_x = ctypes.c_uint(96)
            dpi_y = ctypes.c_uint(96)
            # MDT_EFFECTIVE_DPI = 0
            if shcore.GetDpiForMonitor(
                wintypes.HMONITOR(self.handle),
                0,
                ctypes.byref(dpi_x),
                ctypes.byref(dpi_y),
            ) == 0:
                return max(1.0, float(dpi_x.value) / 96.0)
        except Exception:
            pass
        return 1.0

    def as_dict(self) -> dict[str, object]:
        return {
            "device": self.device,
            "bounds": self.bounds.as_dict(),
            "work": self.work.as_dict(),
            "primary": self.is_primary,
            "scale_factor": self.scale_factor,
        }


def all_monitors() -> list[Monitor]:
    """枚举所有显示器。

    非 Windows 上抛 :class:`Win32Unavailable`。空列表意味着枚举失败 ——
    Windows 至少会报一块显示器出来，所以空列表一定是异常情况。
    """
    if not is_windows():
        raise Win32Unavailable("显示器枚举需要 Windows")
    lib = _user32_lib()
    found: list[Monitor] = []

    def _cb(hmon, _hdc, _lprc, _data):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if lib.GetMonitorInfoW(hmon, ctypes.byref(info)):
            found.append(
                Monitor(
                    device=str(info.szDevice or ""),
                    bounds=Rect(
                        int(info.rcMonitor.left), int(info.rcMonitor.top),
                        int(info.rcMonitor.right), int(info.rcMonitor.bottom),
                    ),
                    work=Rect(
                        int(info.rcWork.left), int(info.rcWork.top),
                        int(info.rcWork.right), int(info.rcWork.bottom),
                    ),
                    is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    handle=int(hmon or 0),
                )
            )
        return True

    # 枚举本身也包一层 DPI 上下文：虽然 GetMonitorInfoW 返回的就是物理像素，
    # 但保持一致能避免调用方在别的线程里的语义差异。
    with thread_dpi_awareness():
        cb = _monitor_enum_proc()(_cb)
        if not lib.EnumDisplayMonitors(None, None, cb, 0):
            return []
    return found


def primary_monitor() -> Monitor | None:
    """主显示器；枚举失败返回 ``None``。"""
    monitors = all_monitors()
    for m in monitors:
        if m.is_primary:
            return m
    return monitors[0] if monitors else None


def monitor_at_point(x: int, y: int) -> Monitor | None:
    """点所在的显示器。点不落在任何屏上（多屏之间的空隙）时返回 ``None``。"""
    for m in all_monitors():
        if m.bounds.contains_point(x, y):
            return m
    return None


def monitor_for_rect(rect: Rect | None) -> Monitor | None:
    """与给定矩形**重叠面积最大**的显示器。

    用重叠面积而不是中心点：窗口被拖到两屏之间时，中心点判定会跳来跳去，
    而"主要在哪块屏上"才是调用方想知道的。
    """
    if rect is None or rect.is_empty:
        return None
    best: Monitor | None = None
    best_area = 0
    for m in all_monitors():
        area = rect.intersection_area(m.bounds)
        if area > best_area:
            best, best_area = m, area
    return best


def virtual_desktop_rect() -> Rect | None:
    """整个虚拟桌面的包围盒（所有显示器的并集）。"""
    from .rect import union

    return union(m.bounds for m in all_monitors())


#: 别名，读起来更顺
virtual_desktop = virtual_desktop_rect
