# -*- coding: utf-8 -*-
"""前台窗口判定：全屏 / 最大化 / 是否为自身进程。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

这里的判定数学全部收在 :mod:`window_locator.coverage`，本模块只负责
"把 Win32 的输出喂给它"。这样判定逻辑可以在 Linux CI 上单测，
而不用真的开一个 Windows 桌面。
"""
from __future__ import annotations

import os

from . import _win32
from .coverage import DEFAULT_MAXIMIZED_RATIO
from .coverage import coverage_ratio as _coverage_of
from .coverage import is_fullscreen_like
from .monitors import Monitor, all_monitors, monitor_for_rect

__all__ = [
    "DEFAULT_COVERAGE_RATIO",
    "DEFAULT_MAXIMIZED_RATIO",
    "foreground_covers_monitor",
    "foreground_is_self",
    "foreground_matches_any",
    "foreground_snapshot",
    "foreground_window_info",
    "fullscreen_monitor",
    "self_process_id",
]

#: 重新导出，方便调用方 `from window_locator.foreground import ...`
from .coverage import DEFAULT_COVERAGE_RATIO  # noqa: E402


def self_process_id() -> int:
    """本进程 id。"""
    return os.getpid()


def foreground_is_self() -> bool:
    """前台窗口是否属于本进程。

    一个截图/自动化工具最不该做的事就是截到自己弹出的窗口 —— 那会形成
    自反馈循环（工具截图 → 看到自己 → 触发动作 → 再截图）。
    原项目里完全没有这个判断，是个真实的功能缺口。
    """
    pid = _win32.window_process_id(None)
    return bool(pid) and pid == self_process_id()


def foreground_window_info(*, limit: int = 512) -> dict[str, object]:
    """一次拿回前台窗口的全部常用信息（诊断 / 日志用）。"""
    hwnd = _win32.foreground_window()
    return {
        "hwnd": hwnd,
        "title": _win32.window_title(hwnd, limit=limit),
        "rect": _win32.foreground_window_rect(),
        "maximized": _win32.is_maximized(hwnd),
        "pid": _win32.window_process_id(hwnd),
        "is_self": foreground_is_self(),
    }


def foreground_matches_any(
    keywords: tuple[str, ...] | list[str] | None,
    *,
    case_sensitive: bool = False,
) -> str:
    """前台窗口标题是否命中任一关键词；返回命中的那个（没命中返回空串）。

    **按整词边界匹配，不是裸子串。** 原实现用 ``hint in title``，于是
    ``"finals"`` 会命中 ``"semifinals"``、``"discovery"`` 会命中
    ``"Discovery Channel"`` —— 一个游戏识别开关被无关窗口误触发。
    这里改成"边界字符必须是非字母数字"，中英文都适用。

    :param keywords: 关键词表；空表返回空串
    :param case_sensitive: 是否区分大小写（默认不区分）
    """
    if not keywords:
        return ""
    title = _win32.foreground_window_title()
    if not title:
        return ""
    haystack = title if case_sensitive else title.lower()
    for raw in keywords:
        needle = str(raw or "").strip()
        if not needle:
            continue
        target = needle if case_sensitive else needle.lower()
        if _bounded_contains(haystack, target):
            return needle
    return ""


def _bounded_contains(haystack: str, needle: str) -> bool:
    """``needle`` 是否作为**整词**出现在 ``haystack`` 里。

    "整词"的边界定义：出现了且前后不是字母/数字。对中文按字符判断同样成立
    （中文字符不算字母数字边界，所以「终极角逐」这种整串匹配仍然有效）。
    """
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return False
        before_ok = idx == 0 or not haystack[idx - 1].isalnum()
        end = idx + len(needle)
        after_ok = end >= len(haystack) or not haystack[end].isalnum()
        if before_ok and after_ok:
            return True
        start = idx + 1


def foreground_covers_monitor(
    monitor: Monitor | None = None,
    *,
    maximized_ratio: float = DEFAULT_MAXIMIZED_RATIO,
    coverage_ratio: float | None = None,
) -> float:
    """前台窗口覆盖目标显示器的比例（0.0–1.0）。

    ``monitor=None`` 时先按窗口自己挑一块屏（取重叠面积最大的那块）。

    这是**覆盖率**，不带阈值判断；要不要算"全屏"请用
    :func:`is_fullscreen_like` 或 :func:`fullscreen_monitor`。
    两个 ratio 参数保留在这里只是为了让调用方能一路透传下来。
    """
    rect = _win32.foreground_window_rect()
    if rect is None or rect.is_empty:
        return 0.0
    target = monitor or monitor_for_rect(rect)
    if target is None:
        return 0.0
    return _coverage_of(rect, target.bounds)


def fullscreen_monitor(
    *,
    maximized_ratio: float = DEFAULT_MAXIMIZED_RATIO,
    coverage_ratio: float | None = None,
) -> Monitor | None:
    """被前台窗口"铺满"的那块显示器；没有则 ``None``。

    用途：全屏游戏/视频时，截图应该抓**整屏**而不是工作区 —— 后者会把
    底部任务栏那条排除掉，抓出来的图和用户在看的不是一回事。
    """
    rect = _win32.foreground_window_rect()
    if rect is None or rect.is_empty:
        return None
    maximized = _win32.is_maximized(None)
    for m in all_monitors():
        if is_fullscreen_like(
            rect,
            m.bounds,
            maximized=maximized,
            maximized_ratio=maximized_ratio,
            coverage_threshold=coverage_ratio,
        ):
            return m
    return None


def foreground_snapshot(
    *,
    maximized_ratio: float = DEFAULT_MAXIMIZED_RATIO,
    coverage_ratio: float | None = None,
) -> dict[str, object]:
    """给日志 / 后台面板用的完整快照。全程吞异常，永远返回字典。"""
    out: dict[str, object] = {
        "hwnd": 0,
        "title": "",
        "rect": None,
        "maximized": False,
        "pid": 0,
        "is_self": False,
        "monitor": None,
        "coverage": 0.0,
        "fullscreen": False,
        "error": "",
    }
    try:
        info = foreground_window_info()
        out.update(info)
        monitor = monitor_for_rect(info["rect"])  # type: ignore[arg-type]
        if monitor is not None:
            out["monitor"] = monitor.device
            ratio = _coverage_of(info["rect"], monitor.bounds)  # type: ignore[arg-type]
            out["coverage"] = round(ratio, 4)
            out["fullscreen"] = is_fullscreen_like(
                info["rect"],  # type: ignore[arg-type]
                monitor.bounds,
                maximized=bool(info["maximized"]),
                maximized_ratio=maximized_ratio,
                coverage_threshold=coverage_ratio,
            )
    except Exception as exc:
        out["error"] = str(exc)[:200]
    return out
