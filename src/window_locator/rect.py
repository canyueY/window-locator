# -*- coding: utf-8 -*-
"""矩形与点：纯整数运算，无平台依赖。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

坐标约定
--------
全部使用 **Windows 虚拟桌面物理像素**坐标：左上角为 ``(0, 0)``，
主显示器固定在原点，其他显示器可以是负坐标（在主屏左侧或上方时）。
单位是物理像素，**不是** DPI 缩放后的逻辑像素 —— 后者是 Qt/WPF 那层的概念，
两个混用就是这类代码最常见的 bug 来源。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "Rect",
    "intersection",
    "intersection_area",
    "is_degenerate",
    "rect_from_any",
    "union",
]


@dataclass(frozen=True)
class Rect:
    """左闭右开的整数矩形：``x <= px < right``，``y <= py < bottom``。"""

    x: int = 0
    y: int = 0
    right: int = 0
    bottom: int = 0

    # -- 构造 -----------------------------------------------------------

    @classmethod
    def from_ltrb(cls, left: int, top: int, right: int, bottom: int) -> "Rect":
        return cls(int(left), int(top), int(right), int(bottom))

    @classmethod
    def from_xywh(cls, x: int, y: int, w: int, h: int) -> "Rect":
        return cls(int(x), int(y), int(x) + int(w), int(y) + int(h))

    @classmethod
    def around_point(cls, x: int, y: int, radius: int = 0) -> "Rect":
        r = max(0, int(radius))
        return cls(int(x) - r, int(y) - r, int(x) + r + 1, int(y) + r + 1)

    @classmethod
    def from_rect_like(cls, obj: Any) -> "Rect":
        """从 A 对象构造。接受 :class:`Rect`、``(l, t, r, b)``、``{"left": ...}``、
        以及任何有 ``x/y/width/height`` 或 ``left/top/right/bottom`` 方法的对象
        （Qt 的 ``QRect`` 就属于后者）。

        刻意用鸭子类型而不是 import Qt：这个包不该把 Qt 拉成依赖。
        """
        if isinstance(obj, Rect):
            return obj
        if isinstance(obj, (tuple, list)) and len(obj) == 4:
            return cls(*(int(v) for v in obj))
        if isinstance(obj, dict):
            if "left" in obj:
                return cls(
                    int(obj["left"]), int(obj["top"]),
                    int(obj["right"]), int(obj["bottom"]),
                )
            return cls.from_xywh(
                int(obj.get("x", 0)), int(obj.get("y", 0)),
                int(obj.get("width", 0)), int(obj.get("height", 0)),
            )
        # Qt QRect / 任何 x()/y()/width()/height() 对象
        for names in (("left", "top", "right", "bottom"), ("x", "y", "width", "height")):
            if all(callable(getattr(obj, n, None)) for n in names):
                vals = [int(getattr(obj, n)()) for n in names]
                if names[0] == "x":
                    return cls.from_xywh(*vals)
                return cls(*vals)
        raise TypeError(f"无法从 {type(obj).__name__} 构造 Rect")

    # -- 派生属性 -------------------------------------------------------

    @property
    def width(self) -> int:
        return max(0, self.right - self.x)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.y)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def ltrb(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.right, self.bottom)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def is_empty(self) -> bool:
        return self.width == 0 or self.height == 0

    # -- 变换 -----------------------------------------------------------

    def offset(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + int(dx), self.y + int(dy),
                    self.right + int(dx), self.bottom + int(dy))

    def scale(self, factor: float) -> "Rect":
        """按比例缩放（保持左上角）。用于把逻辑坐标换算成物理坐标。"""
        f = float(factor)
        return Rect(self.x, self.y,
                    self.x + int(round(self.width * f)),
                    self.y + int(round(self.height * f)))

    def clip(self, bounds: "Rect") -> "Rect":
        """裁到 ``bounds`` 内。完全在外时返回空矩形。"""
        return self.intersection(bounds) or Rect(self.x, self.y, self.x, self.y)

    # -- 判定 -----------------------------------------------------------

    def contains_point(self, x: int, y: int) -> bool:
        return self.x <= int(x) < self.right and self.y <= int(y) < self.bottom

    def contains_rect(self, other: "Rect") -> bool:
        return (
            other.x >= self.x and other.y >= self.y
            and other.right <= self.right and other.bottom <= self.bottom
        )

    def intersects(self, other: "Rect") -> bool:
        return intersection(self, other) is not None

    def intersection(self, other: "Rect") -> "Rect | None":
        return intersection(self, other)

    def intersection_area(self, other: "Rect") -> int:
        return intersection_area(self, other)

    def coverage_of(self, other: "Rect") -> float:
        """``other`` 被本矩形覆盖的比例（0.0–1.0）。``other`` 为空时返回 1.0。

        注意是"``other`` 有多少落在我里面"，不是 IoU。判断"前台窗口是否铺满
        某块屏幕"用的就是这个方向。
        """
        total = other.area
        if total <= 0:
            return 1.0
        return intersection_area(self, other) / total

    def as_dict(self) -> dict[str, int]:
        return {"left": self.x, "top": self.y, "right": self.right, "bottom": self.bottom}

    def __repr__(self) -> str:
        return (
            f"Rect({self.x}, {self.y}, {self.right}, {self.bottom}"
            f"  {self.width}x{self.height})"
        )


def intersection(a: Rect, b: Rect) -> Rect | None:
    """交集；不相交返回 ``None``。"""
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    if right <= left or bottom <= top:
        return None
    return Rect(left, top, right, bottom)


def intersection_area(a: Rect, b: Rect) -> int:
    """交集面积；不相交返回 0。"""
    inter = intersection(a, b)
    return inter.area if inter else 0


def union(rects: Iterable[Rect]) -> Rect | None:
    """包围盒。空输入返回 ``None``。"""
    items = [r for r in rects]
    if not items:
        return None
    return Rect(
        min(r.x for r in items),
        min(r.y for r in items),
        max(r.right for r in items),
        max(r.bottom for r in items),
    )


def is_degenerate(rect: Rect | None) -> bool:
    """矩形为空/退化（任一边长 ≤ 0）。``None`` 也算退化。

    这个判断单独抽出来是因为它总被写成 ``right <= left``，然后漏掉 ``height``。
    """
    if rect is None:
        return True
    return rect.width <= 0 or rect.height <= 0


# 便捷别名：调用方常常直接从包里拿这个
rect_from_any = Rect.from_rect_like
