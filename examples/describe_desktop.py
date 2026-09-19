# -*- coding: utf-8 -*-
"""最小可运行示例：打印显示器几何与前台窗口信息。

Copyright (C) 2026 canyueY <https://github.com/canyueY>
SPDX-License-Identifier: AGPL-3.0-or-later

直接跑（Windows）：

    python examples/describe_desktop.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from window_locator import (  # noqa: E402
    Rect,
    Win32Unavailable,
    all_monitors,
    coverage_ratio,
    foreground_snapshot,
    fullscreen_monitor,
    is_fullscreen_like,
    monitor_for_rect,
    virtual_desktop_rect,
)


def main() -> int:
    try:
        monitors = all_monitors()
    except Win32Unavailable as exc:
        print(f"这台机器不是 Windows（{exc}）—— 纯逻辑层的演示见 tests/。")
        return 0

    print("=" * 74)
    print(f"显示器 {len(monitors)} 块")
    print("=" * 74)
    for m in monitors:
        tag = "主屏" if m.is_primary else "副屏"
        print(f"\n[{tag}] {m.device}")
        print(f"  整屏  {m.bounds}   缩放 {m.scale_factor:g}x")
        print(f"  工作区 {m.work}")
        if m.scale_factor != 1.0:
            logical_w = m.bounds.width / m.scale_factor
            logical_h = m.bounds.height / m.scale_factor
            print(f"  换算成逻辑像素：{logical_w:.0f} x {logical_h:.0f}")

    vd = virtual_desktop_rect()
    print(f"\n虚拟桌面包围盒：{vd}")
    if vd is not None and (vd.x < 0 or vd.y < 0):
        print("  （有负坐标 = 副屏在主屏左侧/上方，这是正常的，也是"
              "'逻辑坐标×本屏dpr'会算错的那类布局）")

    print("\n" + "=" * 74)
    print("前台窗口")
    print("=" * 74)
    snap = foreground_snapshot()
    if snap["error"]:
        print(f"  探测失败：{snap['error']}")
    print(f"  标题     {snap['title'] or '(无标题)'}")
    print(f"  矩形     {snap['rect']}")
    print(f"  最大化   {snap['maximized']}")
    print(f"  本进程？ {snap['is_self']}  (pid={snap['pid']})")
    print(f"  所在屏   {snap['monitor'] or '(未知)'}")
    print(f"  覆盖率   {snap['coverage']}  -> 全屏判定 {snap['fullscreen']}")

    rect = snap["rect"]
    if isinstance(rect, Rect):
        # 注意要拿**窗口所在的**那块屏来比。拿 monitors[0] 比是常见错误：
        # 窗口在副屏上时，与主屏的覆盖率是 0。
        home = monitor_for_rect(rect)
        print(f"  与主屏覆盖率 {coverage_ratio(rect, monitors[0].bounds):.4f}")
        if home is not None:
            print(f"  与所在屏({home.device})覆盖率 "
                  f"{coverage_ratio(rect, home.bounds):.4f}"
                  f"  -> 全屏判定 {is_fullscreen_like(rect, home.bounds, maximized=bool(snap['maximized']))}")

    fm = fullscreen_monitor()
    print(f"  fullscreen_monitor() -> {fm.device if fm else None}")

    print("\n要点：")
    print("  · 所有坐标都是物理像素；缩放 150% 的屏上报的是实际像素尺寸")
    print("  · 副屏可以是负坐标；用 GetMonitorInfoW 拿到的就是正确值，无需换算")
    print("  · 取窗口矩形前默认已设 per-monitor-v2 DPI 感知，结果可信")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
