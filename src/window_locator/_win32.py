# -*- coding: utf-8 -*-
"""Win32 绑定：集中所有 user32 调用与其签名声明。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

**为什么单独一层。** 原项目里同一段 ``GetForegroundWindow`` + ``GetWindowRect``
在四个文件里各写了一遍，四份的 ``restype``/``argtypes`` 声明还不一样。没有
声明的话 ctypes 默认按 C ``int`` 处理返回值，64 位下 ``HWND`` 会被截断成
32 位 —— 在多显示器或句柄值较大时会拿到错误的窗口矩形，而且是**静默**的。

**为什么惰性加载。** 非 Windows 平台上 import 本包不该炸 —— 调用时才抛
:class:`Win32Unavailable`。这样打包、类型检查、CI 在 Linux 上都能跑。
"""
from __future__ import annotations

import contextlib
import ctypes
import sys
from ctypes import wintypes
from typing import Any, Iterator

from .rect import Rect

__all__ = [
    "DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2",
    "Win32Unavailable",
    "foreground_window",
    "foreground_window_rect",
    "foreground_window_title",
    "is_maximized",
    "is_windows",
    "thread_dpi_awareness",
    "window_process_id",
    "window_rect",
    "window_title",
]


class Win32Unavailable(RuntimeError):
    """当前平台不是 Windows，或 user32 不可用。"""


def is_windows() -> bool:
    """是否运行在 Windows 上。"""
    return sys.platform == "win32"


#: ``SetThreadDpiAwarenessContext`` 的 PMv2 值。传 -4 让本次调用按
#: per-monitor-v2 解释坐标，从而拿到**物理像素**而不是被系统虚拟化后的值。
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

_user32: Any = None


def _user32_lib() -> Any:
    """拿到声明过签名的 user32。非 Windows 上抛 :class:`Win32Unavailable`。"""
    global _user32
    if _user32 is not None:
        return _user32
    if not is_windows():
        raise Win32Unavailable(f"本模块只在 Windows 上可用（当前 {sys.platform}）")
    try:
        lib = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    except (OSError, AttributeError) as exc:  # pragma: no cover - 仅在异常环境
        raise Win32Unavailable(f"加载 user32 失败：{exc}") from exc

    # ---- 签名声明（漏掉这一步 = 静默截断句柄） ----
    lib.GetForegroundWindow.restype = wintypes.HWND
    lib.GetForegroundWindow.argtypes = []

    lib.GetWindowRect.restype = wintypes.BOOL
    lib.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

    lib.GetWindowTextLengthW.restype = ctypes.c_int
    lib.GetWindowTextLengthW.argtypes = [wintypes.HWND]

    lib.GetWindowTextW.restype = ctypes.c_int
    lib.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    lib.IsZoomed.restype = wintypes.BOOL
    lib.IsZoomed.argtypes = [wintypes.HWND]

    lib.IsWindow.restype = wintypes.BOOL
    lib.IsWindow.argtypes = [wintypes.HWND]

    # GetWindowThreadProcessId 在老系统上可能不存在 -> 可选
    if hasattr(lib, "GetWindowThreadProcessId"):
        lib.GetWindowThreadProcessId.restype = wintypes.DWORD
        lib.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]

    # ---- 显示器枚举（monitors.py 用） ----
    # 这两个也必须声明：HMONITOR 是 64 位句柄，不声明 argtypes 的话 ctypes
    # 按 C int 传参，句柄会被截断成 32 位。
    lib.EnumDisplayMonitors.restype = wintypes.BOOL
    lib.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.c_void_p,          # LPCRECT（可空；用 c_void_p 免得为它再定义结构）
        ctypes.c_void_p,          # MONITORENUMPROC；真实类型在 monitors.py 里定
        wintypes.LPARAM,
    ]
    lib.GetMonitorInfoW.restype = wintypes.BOOL
    lib.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]

    _user32 = lib
    return lib


def _as_hwnd(hwnd: Any) -> int:
    """把 ``None`` / ``0`` / int / 有 ``.handle`` 的对象统一成 int 句柄。

    ``None`` 与 ``0`` 都表示"前台窗口"—— 这两个写法在调用方那里都出现过，
    而且都是**合法**输入（``window_rect(0)`` 曾经因为把 0 当对象处理而抛
    ``TypeError``）。句柄 0 本来就不是有效窗口，不会产生歧义。
    """
    if hwnd is None:
        return int(_user32_lib().GetForegroundWindow() or 0)
    if isinstance(hwnd, int):
        if hwnd == 0:
            return int(_user32_lib().GetForegroundWindow() or 0)
        return hwnd
    for attr in ("handle", "hwnd", "winId"):
        val = getattr(hwnd, attr, None)
        if val is None:
            continue
        try:
            got = int(val() if callable(val) else val)
        except Exception:
            continue
        return got or int(_user32_lib().GetForegroundWindow() or 0)
    raise TypeError(f"无法从 {type(hwnd).__name__} 取出窗口句柄")


# ---------------------------------------------------------------------------
# 窗口查询
# ---------------------------------------------------------------------------


def foreground_window() -> int:
    """当前前台窗口句柄；没有则 0。"""
    return int(_user32_lib().GetForegroundWindow() or 0)


def window_rect(hwnd: Any = None, *, physical: bool = True) -> Rect | None:
    """窗口矩形（含标题栏与边框的整窗）。取不到返回 ``None``。

    :param hwnd: 句柄；``None`` 表示前台窗口
    :param physical: 是否包一层 per-monitor-v2 DPI 上下文。**建议保持 True**：
        ``GetWindowRect`` 的返回值取决于调用线程的 DPI 感知级别，
        在 Qt/WPF 线程里默认是虚拟化过的逻辑值，和物理像素的屏幕矩形比面积
        会得到随机结果。这就是原项目里"覆盖率偶尔失真"的根因。
    """
    lib = _user32_lib()
    handle = _as_hwnd(hwnd)
    if not handle or not lib.IsWindow(handle):
        return None
    buf = wintypes.RECT()
    ctx = thread_dpi_awareness() if physical else contextlib.nullcontext()
    with ctx:
        ok = lib.GetWindowRect(handle, ctypes.byref(buf))
    if not ok:
        return None
    return Rect(int(buf.left), int(buf.top), int(buf.right), int(buf.bottom))


def window_title(hwnd: Any = None, *, limit: int = 512) -> str:
    """窗口标题。取不到返回空串。

    ``limit`` 是上限：``GetWindowTextLengthW`` 返回的长度可以很长（浏览器标签页
    标题），而不设上限的 ``create_unicode_buffer`` 会按那个长度分配内存。
    """
    lib = _user32_lib()
    handle = _as_hwnd(hwnd)
    if not handle or not lib.IsWindow(handle):
        return ""
    length = int(lib.GetWindowTextLengthW(handle))
    if length <= 0:
        return ""
    size = min(length + 1, max(1, int(limit)))
    buf = ctypes.create_unicode_buffer(size)
    lib.GetWindowTextW(handle, buf, size)
    return str(buf.value or "")


def is_maximized(hwnd: Any = None) -> bool:
    """窗口是否最大化。"""
    lib = _user32_lib()
    handle = _as_hwnd(hwnd)
    if not handle or not lib.IsWindow(handle):
        return False
    return bool(lib.IsZoomed(handle))


def window_process_id(hwnd: Any = None) -> int:
    """窗口所属进程 id；取不到返回 0。

    用来实现"排除自己"：一个截图工具最不该截的就是自己弹出的窗口。
    """
    lib = _user32_lib()
    handle = _as_hwnd(hwnd)
    if not handle:
        return 0
    if not hasattr(lib, "GetWindowThreadProcessId"):
        return 0
    pid = wintypes.DWORD(0)
    lib.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    return int(pid.value or 0)


# ---------------------------------------------------------------------------
# 便捷组合
# ---------------------------------------------------------------------------


def foreground_window_rect(*, physical: bool = True) -> Rect | None:
    """前台窗口矩形。"""
    return window_rect(None, physical=physical)


def foreground_window_title(*, limit: int = 512) -> str:
    """前台窗口标题。"""
    return window_title(None, limit=limit)


# ---------------------------------------------------------------------------
# DPI 感知
# ---------------------------------------------------------------------------


def _set_thread_dpi_awareness(value: int) -> int:
    """设置本线程 DPI 感知级别，返回旧值。API 不存在时返回 0。"""
    lib = _user32_lib()
    if not hasattr(lib, "SetThreadDpiAwarenessContext"):
        return 0
    lib.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    lib.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    try:
        old = lib.SetThreadDpiAwarenessContext(ctypes.c_void_p(int(value)))
    except OSError:
        return 0
    return int(old or 0)


@contextlib.contextmanager
def thread_dpi_awareness(value: int = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) -> Iterator[bool]:
    """在本线程临时切到指定 DPI 感知级别，退出时还原。

    在 Windows 10 1703 之前（或 API 缺失时）是空操作，``yield`` 出 ``False``。

    ⚠️ **这里修掉了原实现的一个真实 bug。** 原来的写法是::

        try:
            old = set(...)          # 设 DPI
            return fn()             # 执行回调
        finally:
            restore(old)
        except Exception:
            return fn()             # ← 回调被第二次执行

    回调抛异常时，异常穿过 ``try/finally``（finally 不吞异常）后被 ``except``
    捕获，于是 ``fn()`` **又跑了一遍**。对截图而言这是失败时抓两次屏；对任何
    有副作用的回调都是双写。改成上下文管理器后，回调只在一个地方被执行。

    :return: 上下文里 ``yield`` 的布尔值表示是否真的切换了 DPI 感知
    """
    if not is_windows():
        yield False
        return
    try:
        old = _set_thread_dpi_awareness(value)
    except Win32Unavailable:
        yield False
        return
    if not old:
        # API 不可用：不假装切换过
        yield False
        return
    try:
        yield True
    finally:
        try:
            _set_thread_dpi_awareness(old)
        except Exception:
            # 还原失败不能盖掉业务异常；这是尽力而为的清理
            pass
