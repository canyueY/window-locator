# Changelog

本文件记录 window-locator 的对外变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-09-19

首次发布。从 [MurasamePet](https://github.com/canyueY/MurasamePet) 的
`Murasame/screen_capture.py` 中抽出与 Windows 相关的部分，并重写了显示器几何。

### Added

- `Rect`：纯整数矩形（左闭右开），含 `from_rect_like` 鸭子类型构造，
  接受 `QRect` / tuple / dict 而不依赖 Qt。
- `all_monitors` / `primary_monitor` / `monitor_at_point` / `monitor_for_rect` /
  `virtual_desktop_rect`：`EnumDisplayMonitors` + `GetMonitorInfoW` 的物理像素几何。
- `Monitor`：`bounds` / `work` / `is_primary` / `scale_factor`。
- `foreground_window` / `foreground_window_rect` / `foreground_window_title` /
  `window_rect` / `window_title` / `is_maximized` / `window_process_id`。
- `foreground_is_self()`：**全新功能**。原项目全文没有自身进程判断，
  一个能读屏幕的常驻进程最不该截的就是自己弹出的窗口。
- `foreground_matches_any()`：按**整词边界**匹配窗口标题。
- `coverage_ratio` / `is_fullscreen_like` / `fullscreen_monitor`：全屏判定。
- `thread_dpi_awareness()`：DPI 感知上下文管理器。
- `foreground_snapshot()`：一次拿全的诊断快照，全程吞异常。
- `Win32Unavailable`：非 Windows 上调用 Win32 部分时抛出；`import` 本身不炸。

### Changed

相对于抽取前的实现：

- **显示器几何改用 `GetMonitorInfoW` 的原生物理矩形**，不再用
  `QScreen.geometry()` 乘本屏 dpr。后者在混合 DPI 的多屏环境下是错的：
  逻辑原点是全局的（按主屏缩放算），乘本屏 dpr 会让**位置**偏移
  （尺寸恰好是对的，所以更难查）。
- **`GetWindowRect` 默认包一层 per-monitor-v2 DPI 上下文**。原实现只在
  PIL 截图路径包了，而 `_screen_covers_foreground` 里的调用点没包 ——
  从 QThread 调用时矩形被虚拟化，覆盖率随机失真。
- **`foreground_matches_any` 改成整词边界匹配**。原实现是裸子串，
  `"finals"` 会命中 `"Semifinals"`、`"discovery"` 会命中 `"Discovery Channel"`。
- `monitor_for_rect` 按重叠面积取显示器；原实现遍历屏列表取第一个"覆盖达标"的。
- `window_rect(0)` 不再抛 `TypeError`：`0` 与 `None` 统一表示"前台窗口"。
- `is_fullscreen_like` 的阈值参数从 `coverage_ratio` 改名为 `threshold` /
  `coverage_threshold`。**旧参数名是个真 bug**：它与模块级函数同名，
  函数内一调就把浮点当函数用 → `TypeError: 'float' object is not callable`。
  旧名字仍可通过 `**legacy` 传入。

### Fixed

- **`thread_dpi_awareness` 不再重复执行回调。** 原实现是
  `try: return fn() finally: restore() except: return fn()`：回调抛异常时
  异常穿过 `try/finally` 被 `except` 捕获，于是 `fn()` **被第二次执行**。
  对 ImageGrab 是失败时抓两次屏，对有副作用的回调是双写。
- 所有 user32 调用显式声明 `restype`/`argtypes`。原实现只有三处有声明，
  其余按 C `int` 处理返回值 —— 64 位下 `HWND`/`HMONITOR` 会被截断成 32 位，
  静默拿到错误的窗口矩形。
- 窗口标题读取加了长度上限，避免按 `GetWindowTextLengthW` 报的超长值
  分配缓冲区。

### Removed

以下内容**没有**进包，它们属于应用层或另立包：

- 游戏标题硬编码表（THE FINALS 相关的 5 个词）→ 由调用方传关键词。
- `_DEFAULT_CAPTURE` 那 21 个配置键 → 原项目 schema，留在应用层。
- 截屏后端（mss / dxcam / Qt / ImageGrab）→ 语义上是另一个包。
- 图像比对工具（降采样、变化率、跳过未变帧）→ 同上。
- `_DXCAM_CREATE_ERROR`（只写不读的死状态）→ 直接删掉。

[0.1.0]: https://github.com/canyueY/window-locator/releases/tag/v0.1.0
