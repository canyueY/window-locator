# -*- coding: utf-8 -*-
"""覆盖率判定数学：纯函数，无平台依赖，可在任何系统上单测。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

**为什么单开一个模块。** 判定"这个窗口是不是铺满了那块屏"看起来只有一行，
但这里有两个容易搞错的地方：

1. **最大化的窗口不覆盖整屏。** 在 Windows 上最大化会留出边框（把窗口拖到
   屏幕边缘时会把它"吸"成略小于整屏的矩形）。所以纯按"覆盖率 == 1.0"判定
   会漏掉最大化的游戏/视频。这就是 ``maximized_ratio`` 存在的理由。
2. **方向搞反。** 要算的是"窗口有多少落在这块屏里"，不是"这块屏有多少被
   窗口覆盖"。显示器可能比窗口大得多，两个方向算出来的数完全不同。

把这两个数留在纯函数里，就能用假数据把边界情况全测一遍，不用真开一个
Windows 桌面 —— 这正是原实现最缺的东西（那段逻辑只能靠手动跑桌宠来验证）。
"""
from __future__ import annotations

from .rect import Rect, intersection_area

__all__ = [
    "DEFAULT_COVERAGE_RATIO",
    "DEFAULT_MAXIMIZED_RATIO",
    "coverage_ratio",
    "covers",
    "is_fullscreen_like",
]
#: 普通（非最大化）窗口要盖住多少才算"全屏"。窗口管理器给全屏应用留的
#: 缝一般很小，0.88 足够宽松又能排除掉"窗口拖到几乎占满"的情况。
DEFAULT_COVERAGE_RATIO = 0.88

#: 已最大化的窗口要盖住多少才算。比上面低，因为最大化本就带边框留缝。
DEFAULT_MAXIMIZED_RATIO = 0.75


def coverage_ratio(window: Rect | None, monitor: Rect | None) -> float:
    """窗口覆盖显示器的比例（0.0–1.0）。

    分母是**显示器**面积。显示器为空时返回 0.0；窗口为空时也返回 0.0
    （区别于 :meth:`Rect.coverage_of` 的 1.0 —— 那个方向是"空的东西被覆盖了
    多少"，这里问的是"你盖住了屏幕多少"，空窗口当然盖不住）。
    """
    if window is None or monitor is None:
        return 0.0
    total = monitor.area
    if total <= 0:
        return 0.0
    if window.is_empty:
        return 0.0
    return intersection_area(window, monitor) / total


def covers(window: Rect | None, monitor: Rect | None) -> float:
    """覆盖率（0.0–1.0）。

    .. deprecated::
        名字承诺布尔语义却返回浮点，调用方几乎必然误用。新代码请用
        :func:`is_fullscreen_like`（判定）或 :func:`coverage_ratio`（取比例）。
        保留它只为让旧调用点不改也能跑。
    """
    return coverage_ratio(window, monitor)


def is_fullscreen_like(
    window: Rect | None,
    monitor: Rect | None,
    *,
    maximized: bool = False,
    threshold: float | None = None,
    maximized_ratio: float = DEFAULT_MAXIMIZED_RATIO,
    coverage_threshold: float | None = None,
    **legacy: float,
) -> bool:
    """窗口是否铺满了显示器。

    * ``maximized=False`` → 需要盖住 :data:`DEFAULT_COVERAGE_RATIO`（0.88）
    * ``maximized=True``  → 只需要 :data:`DEFAULT_MAXIMIZED_RATIO`（0.75），
      因为 Windows 最大化会留边框，达不到 0.88

    :param threshold: 直接指定阈值，覆盖上面两个默认值
    :param coverage_threshold: 与 ``threshold`` 等价（更明确的写法）
    :param legacy: 接受 ``coverage_ratio=`` 这个旧参数名。
        **它曾经是个真 bug 的来源**：那个参数名与模块级函数
        :func:`coverage_ratio` 同名，函数内一调就把浮点当函数用 →
        ``TypeError: 'float' object is not callable``。所以现在参数改名，
        旧名字只从 ``**legacy`` 里捞，永远不会遮蔽任何东西。
    """
    ratio = coverage_ratio(window, monitor)  # 这里不会再被参数遮蔽了
    if threshold is None:
        threshold = coverage_threshold
    if threshold is None:
        threshold = legacy.get("coverage_ratio")
    if threshold is None:
        threshold = maximized_ratio if maximized else DEFAULT_COVERAGE_RATIO
    return ratio >= threshold
