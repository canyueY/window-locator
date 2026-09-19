# window-locator

Windows **显示器几何**与**前台窗口查询**，全部用**物理像素**。零依赖（`ctypes` 是标准库）。

```python
from window_locator import all_monitors, foreground_window_info

for m in all_monitors():
    print(m.device, m.bounds, m.work, "primary" if m.is_primary else "")

info = foreground_window_info()
print(info["title"], info["rect"], info["is_self"])
```

## 它解决两个常被写错的问题

### ① 不要用 Qt 的 `QScreen.geometry()` 算屏幕矩形

那是 DPI 缩放后的**逻辑**坐标，而 Windows 的窗口 API 全部按**物理**像素工作。
想把两者对上就得自己乘 dpr，于是就有了这类代码里最经典的 bug：

```python
# ❌ 混合 DPI 的多屏环境下会偏
physical = QRect(screen.geometry().x() * screen.devicePixelRatio(), ...)
```

屏幕上各屏的 dpr 不同，而 `QScreen.geometry()` 的 `x/y` 是**虚拟桌面范围内的
全局逻辑原点**（按主屏缩放系数算出来的）。把它乘**本屏**的 dpr，换算系数不一致，
位置就偏了 —— 尺寸倒是可以乘本屏 dpr，所以这个 bug 表现为"大小对、位置错"，
更难查。

直接问 Windows 要物理矩形（`GetMonitorInfoW`）就没有这个换算：

```python
m = primary_monitor()
m.bounds    # Rect(0, 0, 2560, 1440)  ← 物理像素，缩放 150% 时就是这么大
m.work      # 去掉任务栏
m.scale_factor   # 1.5
```

### ② 取窗口矩形前必须设 DPI 感知

`GetWindowRect` 的返回值**取决于调用线程的 DPI 感知级别**。在 Qt/WPF 线程里
默认拿到的是虚拟化后的值，拿去和物理像素的屏幕矩形比面积，结果随机。

本包默认替你处理：

```python
rect = window_rect(None)          # physical=True 是默认值
rect = window_rect(None, physical=False)   # 确实想要虚拟化坐标时才关掉
```

## 安装

```bash
pip install git+https://github.com/canyueY/window-locator.git
# 或从源码
git clone https://github.com/canyueY/window-locator.git
cd window-locator && pip install -e ".[dev]"
```

> 暂未发布到 PyPI。
> **平台**：Windows。非 Windows 上可以 `import`（纯逻辑层照常可用），
> 调用 Win32 部分会抛 `Win32Unavailable` —— 这样 CI 和类型检查在任何平台都能跑。

## API

### 显示器

```python
from window_locator import (
    all_monitors, primary_monitor, monitor_at_point, monitor_for_rect,
    virtual_desktop_rect, Monitor,
)

all_monitors()                  # -> list[Monitor]
primary_monitor()               # -> Monitor | None（主屏左上角保证在 (0,0)）
monitor_at_point(x, y)          # -> Monitor | None（多屏空隙返回 None）
monitor_for_rect(rect)          # -> Monitor | None（按**重叠面积**取最大，不是中心点）
virtual_desktop_rect()          # -> Rect | None（所有屏的并集；副屏在主屏左侧时是负坐标）
```

`monitor_for_rect` 用重叠面积而不是中心点：窗口被拖到两屏之间时，中心点判定会
来回跳，而"主要在哪块屏上"才是调用方想知道的。

### 前台窗口

```python
from window_locator import (
    foreground_window, foreground_window_rect, foreground_window_title,
    foreground_window_info, foreground_snapshot, foreground_is_self,
    foreground_matches_any, fullscreen_monitor,
)

foreground_is_self()               # 前台窗口是不是本进程 —— 别截自己
foreground_matches_any(("the finals", "终极角逐"))   # 整词匹配，见下
fullscreen_monitor()               # 被前台窗口铺满的那块屏；没有则 None
foreground_snapshot()              # 一次拿全，全程吞异常，永远返回字典
```

**`foreground_matches_any` 按整词边界匹配，不是裸子串。**
常见的写法 `hint in title` 会让 `"finals"` 命中 `"Semifinals"`、
`"discovery"` 命中 `"Rediscovery"` —— 一个游戏识别开关被无关窗口误触发。
本包的边界定义是"前后不是字母或数字"，中英文都适用。

### 矩形

```python
from window_locator import Rect, intersection, intersection_area, union, is_degenerate

r = Rect.from_xywh(100, 100, 800, 600)
r = Rect.from_rect_like(qt_rect)     # 接受 QRect / tuple / dict，鸭子类型，不依赖 Qt
r.area, r.center, r.ltrb
r.contains_point(x, y)
r.intersection(other)                # -> Rect | None
r.coverage_of(other)                 # other 有多少落在我里面
```

坐标约定：左闭右开（`x <= px < right`），虚拟桌面物理像素，主屏在原点，
副屏可以是负坐标。

### 覆盖率

```python
from window_locator import coverage_ratio, is_fullscreen_like

coverage_ratio(window, monitor)                     # -> 0.0–1.0
is_fullscreen_like(window, monitor, maximized=True) # -> bool
```

**为什么"最大化"要用更低的下限**：Windows 最大化会留边框，达不到
"非最大化全屏"要求的 0.88。所以 `maximized=True` 时下限降到 0.75，
否则全屏游戏会被漏判。

**方向很重要**：算的是"窗口有多少落在屏幕里"，不是"屏幕有多少被窗口盖住"，
也不是 IoU。三者数值完全不同。

## 修掉的一个真实 bug：回调被执行两次

原实现里那段"临时切 DPI 感知再还原"的代码长这样：

```python
try:
    old = set_dpi(...)
    return fn()              # 执行回调
finally:
    restore(old)
except Exception:
    return fn()              # ← 回调被第二次执行
```

回调抛异常时，异常穿过 `try/finally`（`finally` 不吞异常）后被 `except` 捕获，
于是 `fn()` **又跑了一遍**。对截图而言这是失败时抓两次屏；对任何有副作用的
回调都是双写。

本包改成上下文管理器，回调只在一个地方被执行：

```python
with thread_dpi_awareness():
    ...      # 这里跑你的代码，出异常就正常抛出，不会重跑
```

## 授权

**AGPL-3.0-or-later**，见 [LICENSE](LICENSE)。

本包从作者自己的桌宠项目 [MurasamePet](https://github.com/canyueY/MurasamePet)
（AGPL-3.0）中抽出。代码是那个项目自己新增的部分，但既然来自 AGPL 项目，
这里就继续沿用 AGPL，不做改许可。

## 来源与开发位置

> **本仓库是镜像；权威源码在 MurasamePet 仓库里。**
>
> 开发位置：`MurasamePet/packages/window-locator/`。
> 桌宠通过 **path 依赖**直接使用它 —— 不再保留任何副本，改这里立即可见。
> 这个独立仓库用于对外发布与展示，内容由 Monorepo 同步而来。
>
> **为什么不反过来（本仓库为源、桌宠用 `git` 依赖）？**
> 开发机上网关受限：`github.com` 必须走本地代理，而 `uv` 拉 git 依赖时
> 用不上该代理（实测 `git fetch` 失败）。path 依赖离线可用、不受代理开关影响。

## 测试

```bash
uv run --python 3.10 --extra dev python -m pytest tests -q
```

99 个用例，分两半：

- **纯逻辑层**（`Rect` / 覆盖率 / 整词匹配）在任何平台都跑，所以 Linux CI 也能验证。
- **Win32 层**用 `skipif` 跳过，在真机上验证显示器枚举、前台窗口矩形、
  DPI 上下文还原、以及"异常时回调只执行一次"。
