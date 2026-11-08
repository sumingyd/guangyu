# 光屿 GuangYu

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.4+-green.svg)](https://www.qt.io/qt-for-python)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Android-lightgrey.svg)](https://github.com/sumingyd/guangyu)

**光屿 GuangYu** 是一款专业强大的 IPTV 播放器，跨平台支持 Windows / macOS / Linux 桌面端与 Android 手机 / 平板 / TV。以 **MPV 播放引擎为核心**，集成 FFprobe 流探测，覆盖「看、扫、管」完整链路：支持 EPG 电子节目单、频道台标自动匹配、HDR 显示、时移/回看、在线字幕下载、音频可视化、断点续播、片段导出等高级播放能力，同时提供频道扫描、批量验证、订阅管理等辅助工具。液态玻璃质感界面、中英双语，从扫描到观看一站式完成。

> 🏷️ 原名 **IPTV-Scanner-Editor-Pro**（ISEP），已更名为 **光屿 GuangYu**，GitHub 旧链接自动重定向，历史数据与配置完全兼容。

## 📸 程序截图


|  |  |  |
| ----------------- | ----------------- | ----------------- |
| ![](icons/1.png)  | ![](icons/2.png)  | ![](icons/3.png)  |
| ![](icons/4.png)  | ![](icons/5.png)  | ![](icons/6.png)  |
| ![](icons/7.png)  | ![](icons/8.png)  | ![](icons/9.png)  |
| ![](icons/10.png) | ![](icons/11.png) | ![](icons/12.png) |

## 📋 功能概览

| 功能类别      | 核心功能                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 播放器       | MPV 引擎驱动、FCC 快速换台（秒开优化）、完整播放控制、倍速、画面比例、全屏、硬件解码、HDR 显示（5种模式）、WCG 广色域、运动补偿（minterpolate插帧）、分辨率提升（高质量缩放+细节增强）、AI超分辨率着色器（GLSL Shader）、智能预设（硬件检测+一键优化）、画中画、多屏预览(4/9屏)、截图、连拍截图、音轨/字幕切换、3D/360°视频、视频旋转翻转、自动裁剪黑边、视频图像调整、流质量检测                                                                                                                                                                                                      |
| 字幕系统      | 字幕样式调整、在线字幕下载（OpenSubtitles/SubHD/SubtitleCat 三源聚合）、IMDB 中转中文搜索、字幕自动同步、字幕延迟/缩放/位置调整                                                                                                                                                                                                                                                                                                                                        |
| 音频        | 10段均衡器、声道布局、音调补偿、音频延迟、A/V 同步监控（实时波形图）、音频可视化（7种3D样式）、歌词显示                                                                                                                                                                                                                                                                                                                                                                   |
| 播放增强      | 断点续播、每文件播放设置持久化、跳过片头/片尾、播放队列（循环/AB循环/逐帧）、书签管理、切片导出/GIF制作、网络流增强（Referer/代理/Headers）                                                                                                                                                                                                                                                                                                                                         |
| 时移/回看     | 5种回看类型(default/append/shift/flussonic/xtream)、时间变量替换、时区偏移、catchup-correction、全局回看参数继承                                                                                                                                                                                                                                                                                                                                      |
| EPG       | XMLTV/JSON 解析、智能匹配(tvg-id→tvg-name→频道名)、日期导航、实时进度条、Gzip 兼容、M3U 内嵌 EPG、EPG 时间轴、EPG 搜索、全局搜索、统一搜索、节目提醒                                                                                                                                                                                                                                                                                                                        |
| 台标系统      | 400+ 内置规则、在线加载、异步下载、本地缓存、智能预加载、High-DPI 支持                                                                                                                                                                                                                                                                                                                                                                                 |
| 频道扫描      | IP 范围扫描、多协议(单播/组播/HTTP)、FFprobe 探测、自定义参数、追加扫描、智能重试                                                                                                                                                                                                                                                                                                                                                                         |
| 批量操作      | 自动分类、清理名称、匹配台标、分配字段、按组排序、批量验证                                                                                                                                                                                                                                                                                                                                                                                              |
| 频道管理      | M3U 导入导出、拖拽排序、分组筛选、右键操作、智能映射、频道分类、名称清理、拼音排序、多格式导出(M3U/TXT/Excel)、收藏、历史、去重、评分、批量编辑、快速跳转、撤销/重做                                                                                                                                                                                                                                                                                                                               |
| 界面        | 21种主题组合、中英双语、三栏布局、悬浮面板、系统托盘、文件关联、拖放打开、丰富快捷键                                                                                                                                                                                                                                                                                                                                                                                |
| 订阅        | 多源管理、独立缓存、智能更新(增量)、编辑功能、缓存回退、过期策略                                                                                                                                                                                                                                                                                                                                                                                          |
| Web 服务器   | 内置 aiohttp 服务器、频道列表和播放接口、频道管理后台（来源区分、订阅只读、本地持久化）                                                                                                                                                                                                                                                                                                                                                                           |
| Android 端 | Kotlin Compose 原生 UI、MPV+ExoPlayer 双内核（自动兜底切换）、DLNA 投屏（SSDP 搜索+推流）、液态玻璃 UI（iOS 拟态玻璃质感+画布背景+深浅色主题）、竖屏/横屏双布局（横屏左右分屏：宫格频道卡+EPG 时间线 / 播放页视频+常驻功能面板）、TV 遥控器适配（DPAD 焦点导航+焦点高亮+台标显示+自动隐藏）、18 种全屏底栏样式（信息详情/居中悬浮/广播电视/机顶盒 OSD/影院 EPG 卡/仪表盘/海报卡片/节目时间轴等，弹窗实时预览切换）、EPG 时间线拟态玻璃化+懒加载、画中画（PiP 增强）、HDR 模式切换（设备能力检测+target-colorspace-hint）、WCG 广色域、PQ/HLG 差异化处理、运动补偿（minterpolate插帧）、分辨率提升（高质量缩放+细节增强）、AI超分辨率着色器（GLSL Shader）、智能预设（硬件检测+一键优化）、3D/360°视频、随机播放、书签管理、EPG 时间轴/日期切换、全局搜索、流质量检测、字幕样式、连拍截图、LAN 管理后台（虚拟遥控器+自动关闭开关）、MPV 软硬解切换、FCC 秒开换台（probesize/analyzeduration 对齐 PC 端）、数据持久化（覆盖安装不丢失）、版本检查更新（GitHub API + 自动提示新版本） |

## ✨ 核心功能

### 🎬 集成播放器

- **MPV 引擎驱动**：基于 libmpv 的高性能流媒体播放

- **FCC 快速换台**：识别频道 URL 中的 `fcc=<IP>:<端口>` 参数（大小写不敏感、位置任意，兼容 `/rtp/`、`/udp/` 路径与直连组播），换台时向旧 FCC 端点发送 LEAVE、向新端点发送 JOIN，并对 FCC 流使用更小的 `probesize`/`analyzeduration` 以缩短首帧时间；实际加速效果取决于 FCC 服务器或代理是否支持该通知协议

- **完整播放控制**：播放（▶）、暂停（▮▮）、停止（■）、音量调节、静音切换

- **倍速播放**：循环切换多种播放速度

- **画面比例**：支持原始/16:9/4:3/填充等多种比例模式

- **全屏播放**：F11 或按钮一键全屏，Escape 退出

- **时移/回看**：支持直播时移和历史节目回看功能

  - 多种回看类型：`default`（完整URL）、`append`（附加到直播URL）、`shift`（时移偏移）、`flussonic`/`fs`（Flussonic格式）、`xc`/`xtream`（Xtream Codes格式）

  - 时间变量替换：`${(b)format}` / `${(e)format}` 支持自定义时间格式

  - 时区偏移：`${(b)yyyyMMddHHmmss|-08:00}` 语法支持时区转换

  - `catchup-correction`：频道级时区修正参数

  - 全局回看参数：M3U 文件头 `#EXTM3U` 可定义全局 `catchup`/`catchup-source`/`catchup-days` 等属性，频道级别未设置时自动继承

- **RTSP 传输协议**：支持 TCP/UDP/LAVF 三种 RTSP 传输方式，可按需选择以适配不同网络环境

- **悬浮控制面板**：底部浮动面板显示频道信息、节目进度、媒体参数

- **OSD 信息遮罩**：Tab 键切换显示详细媒体参数（分辨率、编码、帧率、硬解、HDR、像素格式、色彩参数、码率等），支持永久显示

- **窗口置顶**：标题栏置顶按钮，一键将窗口设为最顶层

- **硬件解码**：支持 D3D11VA / NVDEC / VAAPI 等硬件加速解码，提供 HW Copy-back（auto-copy，默认，保证 vf 滤镜可用）/ HW Native（auto，最快但滤镜受限）/ Software（no）三种模式

- **HDR 显示**：支持 HDR10 / HDR10+ / HLG / Dolby Vision 内容，OSD 中显示 HDR 标识，提供 5 种输出模式

  - `disable`：关闭 HDR 处理

  - `tonemap`：HDR→SDR 色调映射（`tone-mapping=auto` 自动选择算法：HDR10+→st2094-40，HDR10/HLG→bt.2390；`hdr-compute-peak=no` 信任动态元数据，避免画面偏暗；保留 `target-prim=bt.2020` 广色域 + `target-trc=bt.1886` SDR 伽马）

  - `passthrough`：HDR 直通（清空 target-prim/target-trc 让 mpv 直通视频原生色彩空间，启用 `target-colorspace-hint=yes` 让 Android 系统自动切换 HDR 显示模式，需 HDR 屏幕）

  - `scrgb`：scRGB 模式（auto 模式下系统 HDR 开启时走此分支）

  - `auto`：根据系统 HDR 状态自动选择 passthrough / scrgb（Android 端通过 `Display.getHdrCapabilities()` 检测设备 HDR 能力）

  - **PQ/HLG 差异化处理**：根据视频 gamma 自动区分 PQ（HDR10/HDR10+）与 HLG 视频

    - PQ 视频：`target-peak=10000` + `tone-mapping=clip` + `hdr10-opt=yes` 传递 HDR10+ 动态元数据

    - HLG 视频：自动 `target-peak`（不固定 10000）+ `hdr-compute-peak=yes` 自动计算峰值 + `tone-mapping=spline`（gpu-next），避免"阴阳脸"

  - **WCG 广色域处理**：检测到 BT.2020 色域但 SDR 亮度的视频时，自动设置 `target-prim=bt.2020` + `gamut-mapping-mode=relative`，正确显示广色域而不误判为 HDR

- **视频图像调整**：亮度、对比度、饱和度、色调、Gamma、锐度滑块实时调整，支持切换文件时自动重置

- **运动补偿**：基于 FFmpeg minterpolate 滤镜的运动补偿插帧，将低帧率视频提升至高帧率（24/30fps → 60/120fps），消除运动抖动和拖影

  - 3 档强度：轻度（帧混合 mi\_mode=blend）、中度（运动补偿 mi\_mode=mci+obmc）、强力（高级补偿 mi\_mode=mci+aobmc+vsbmc）

  - 目标帧率可选：50/60/90/120/144 fps

  - 使用 `@iptv_mc` 命名 lavfi 滤镜，需 copy-back 硬解或软解

- **分辨率提升**：高质量缩放算法 + 细节增强，提升低分辨率视频画质

  - 6 种缩放算法：双线性、双三次、Lanczos、样条、EWA Lanczos、EWA Lanczos Sharp

  - 细节增强滑块（0-100），使用 `@iptv_sr` 命名 unsharp 滤镜恢复边缘细节

  - 缩放算法通过 mpv scale/cscale/dscale 属性全局生效（不需要 copy-back）；细节增强需 copy-back 硬解或软解

- **AI 超分辨率着色器**：支持加载 GLSL 用户着色器，在 GPU 渲染管线实现 AI 级超分辨率

  - 内置预设：RAVU 锐利放大、FSRCNNX 超分辨率、Anime4K 动画增强、KrigBilateral 色度升频、SSim 降频

  - 着色器文件放在 `shaders/` 目录，自动检测并加载（.glsl/.hook 格式）

  - 通过 mpv `glsl-shaders` 属性动态切换，GPU 运行不影响 CPU

- **智能预设**：一键优化视频增强参数，适配不同场景

  - 智能推荐：根据硬件检测（CPU/GPU/RAM 综合评分）自动推荐最佳设置

  - 性能优先：关闭所有增强，确保流畅播放

  - 画质优先：开启运动补偿 + EWA Lanczos Sharp + 细节增强

  - 动画优化：轻度运动补偿 + Anime4K 着色器 + EWA Lanczos

  - 体育直播：强力运动补偿 + Lanczos + 细节增强，消除运动拖影

- **硬件检测**：自动检测 CPU/GPU/RAM 信息，提供性能评分和智能推荐

- **视频旋转翻转**：支持 0/90/180/270 度旋转，水平/垂直/双向镜像翻转（使用 `@iptv_flip` 命名 lavfi 滤镜，需 copy-back 硬解）

- **自动裁剪黑边**：基于帧分析自动检测并裁剪视频黑边（PIL 灰度 + numpy 边缘分析，`@iptv_autocrop` 命名滤镜），可一键移除

- **3D / 360° 视频**：支持 3D 立体模式（mono/sbs/sbs2/ab/ab2）和 360° 投影（equirect/cubemap/flat），可调整 yaw/pitch/roll 视角

- **网络流增强**：可配置 Referer、HTTP 代理、自定义 HTTP Headers，适配各种防盗链和受限流媒体源

- **软件图标占位**：未播放时视频区域显示程序图标

- **画中画**：PiP 模式，在独立小窗口中继续观看，视图菜单或快捷键切换

- **多屏预览**：支持 4 屏 / 9 屏同时预览多个频道，视图菜单中切换

- **截图**：一键截取当前视频画面保存到 `screenshots/` 目录

- **连拍截图**：定时连续截图，可设置间隔和数量，用于制作动态预览

- **音轨/字幕切换**：播放菜单和右键菜单支持切换音轨和字幕轨道

- **最近打开文件**：文件菜单记录最近访问的播放列表，快速重开

- **视频文件打开**：支持直接打开本地视频文件播放（Ctrl+Shift+O）

- **流质量检测**：独立对话框实时显示 mpv 流信息（每秒刷新），分组展示视频（codec/分辨率/显示分辨率/帧率/码率/像素格式/色彩空间/HDR/位深/宽高比）、音频（codec/声道/采样率/码率/位深）、网络与缓存（协议/缓存时长/缓存速度/缓冲状态/解复用码率）、丢帧统计（VO 丢帧/解码器丢帧/误时帧/VO 延迟帧）、硬件与渲染（硬解/视频输出/GPU API/GPU 上下文），与 Android 端 StreamQualityPanel 和 Web 端 stream\_quality 面板对齐

- **频道切换遮罩**：换台时显示频道信息过渡动画，提升视觉体验

### 📺 EPG 电子节目单

- **XMLTV 格式解析**：支持标准 XMLTV / JSON 格式 EPG 数据源，兼容非标准时间格式（如"在播"）

- **智能匹配**：优先 tvg-id → 其次 tvg-name → 最后频道名，全部模糊匹配

- **日期导航**：查看历史/当天/未来日期的节目安排

- **实时进度条**：显示当前节目的播放进度和时间轴

- **自动订阅**：配置 EPG 地址后自动下载更新，支持过期检测和 URL 变更感知

- **Gzip 兼容**：自动识别并解压 .gz 压缩的 EPG 数据

- **M3U 内嵌 EPG**：自动识别 M3U 文件头 `x-tvg-url` / `tvg-url` / `epg-url` 等属性，未配置 EPG 源时自动加载

- **EPG 时间轴**：可视化时间轴界面，按频道×时间展示全天节目，支持水平/垂直滚动浏览，双击节目直接跳转播放对应频道

- **EPG 搜索**：按节目名称快速搜索所有频道节目，双击结果跳转播放，结果上限200条防止卡顿

- **全局搜索**：跨频道列表和EPG数据的全局搜索功能（Ctrl+Shift+F）

- **统一搜索**：整合频道搜索与EPG搜索的统一搜索界面

- **节目提醒**：为即将开播的节目设置提醒，到时间弹出提醒弹窗，支持自动切换频道

  - 多提醒并发处理：多个提醒同时触发时弹窗堆叠显示，仅第一个自动切换，其余可手动切换

  - 系统托盘通知：最小化到托盘时通过系统托盘显示提醒

### 🖼️ 频道台标系统

- **智能台标匹配**：内置 400+ 频道台标规则，根据频道名称自动匹配对应台标图片

  - 覆盖央视全系列、卫视全系列、CGTN、CETV、CHC、咪咕、求索等主流频道

  - 支持动态规则：CCTV 数字频道、卫视 4K 版本、山东地方频道等自动生成

- **在线加载**：自动从播放列表 tvg-logo URL 下载台标图片

- **异步下载**：后台线程加载，不阻塞 UI

- **本地缓存**：缓存机制，减少重复下载

- **智能预加载**：滚动列表时自动预加载可见区域台标

- **高清渲染**：High-DPI 屏幕支持，原图缓存 + 显示时按需缩放

- **缩略图**：频道缩略图自动捕获服务，列表中可预览频道画面

### 🔍 智能频道扫描

- **范围扫描**：支持 IP 范围格式（如 `239.1.1.[1-255]:5002`）

- **多协议**：单播、组播、HTTP/HTTPS 流链接

- **FFprobe 探测**：使用 FFprobe 进行流有效性检测和媒体信息获取（分辨率、编码、码率）

- **自定义参数**：超时时间、线程数、用户代理等可调

- **追加扫描**：在现有列表基础上增量添加新频道

- **智能重试**：仅对超时失败的频道自动重试，避免对确定无效频道做无意义重试

- **批量操作**：扫描结果支持一键批量处理

  - **自动分类**：根据频道名称规则自动归类到对应分组

  - **清理名称**：去除多余括号、HD/4K 后缀、空格等，规范化频道名

  - **匹配台标**：批量匹配频道台标，支持覆盖/仅填充空位

  - **分配字段**：批量设置分组、台标等属性

  - **按组排序**：按频道分组自动排序

### ✅ 批量验证

- **有效性检测**：使用 FFprobe 批量检测所有频道是否可用

- **性能指标**：检测延迟、分辨率、编码、码率等流媒体参数

- **实时统计**：进度条、有效/无效数量实时更新

- **智能重试**：仅对超时失败的频道自动重试

### 🎯 频道管理

- **M3U 播放列表**：支持标准 M3U/M3U8 格式导入导出

- **拖拽排序**：自由调整频道顺序

- **分组筛选**：下拉框按分组快速过滤频道

- **右键操作**：删除、复制频道名及 URL、清理名称、匹配台标等快捷操作

- **智能映射**：自动匹配频道名称、LOGO、分组信息

- **频道分类**：基于正则规则自动将频道归类到对应分组

- **名称清理**：智能去除频道名中的冗余信息，规范化显示

- **拼音排序**：中文频道名按拼音首字母排序

- **多格式导出**：M3U、TXT、Excel（需 openpyxl）

- **收藏列表**：右键收藏频道，收藏列表支持右键删除单个收藏和清空收藏

- **播放历史**：自动记录播放过的频道，支持右键清空历史

- **频道去重**：自动检测并去除重复频道，支持按名称/URL/名称+URL多种去重策略

- **频道评分**：基于流质量参数对频道进行综合评分，优先播放高质量源

- **流质量评分**：综合分辨率、码率、编码等参数对流质量进行量化评分

- **批量编辑**：批量修改频道名称、分组、台标等属性

- **频道快速跳转**：支持按首字母/拼音快速跳转到目标频道

- **HDR 显示**：支持 HDR 内容在 HDR 屏幕上正确渲染显示，OSD 中显示 HDR 标识

### 🎵 音频增强

- **10 段均衡器**：支持 10 段 EQ 调节，内置预设（flat/bass/treble/vocal/classical/pop/rock/electronic）

- **声道布局**：支持 auto / mono / 1.0-7.1 多种声道布局切换

- **音调补偿**：调整音频音调

- **音频延迟**：调整音频延迟（-10s\~+10s，精度 0.01s），与视频同步

- **A/V 同步监控**：实时显示 A/V Diff、Audio PTS、Video PTS，带历史趋势波形图（200 采样点，颜色随偏差变化）

- **字幕自动同步**：根据 A/V Diff 自动调整字幕延迟（可配置阈值和增益，500ms 采样周期，避免 seek/暂停误判）

- **音频可视化**：纯音频文件自动启用 7 种 3D 可视化样式

  - `spectrum` 3D 频谱、`waves` 3D 波形、`circular` 3D 环形、`terrain` 3D 地形

  - `cosmos` 3D 宇宙、`fluid` 3D 流体、`ripple` 粒子震荡

  - `random` 随机切换（15 秒）、`none` 关闭

  - FFT 频谱分析（4096 点 FFT，64 频段，Hanning 窗，线性+对数频率分布）

- **歌词显示**：自动提取音频文件内嵌歌词（LRC/SYLT/USLT 标签），LRC 时间标签解析 + 自动滚动

### 🔤 字幕系统

- **字幕样式调整**：颜色、边框颜色、阴影颜色、字体、字体大小（8-200）、边框粗细、阴影偏移、加粗/斜体、边距、对齐，实时预览应用

- **字幕控制**：延迟（-300\~300s，0.001 步长）、缩放（0.1-10.0）、位置（0-100）、可见性切换

- **快速预设**：默认、黄色描边、粗描边、无阴影

- **在线字幕下载**：三源聚合搜索（OpenSubtitles + SubHD + SubtitleCat），并行查询合并去重

  - **OpenSubtitles**：XML-RPC 接口，支持文件哈希精准匹配 + IMDB ID + 关键词搜索，gzip 解压自动下载

  - **SubHD**：中文字幕站，自动搜索 + 浏览器跳转下载（需验证码）

  - **SubtitleCat**：免登录无验证码，直接下载 .srt

  - **IMDB 中转中文搜索**：检测 CJK 字符 → `SearchMoviesOnIMDB` 获取 IMDB ID → 用 IMDB ID 搜索字幕，解决中文片名命中率低问题

  - **语言过滤**：全部 / 中日韩 / 中文 / 英语

- **字幕自动同步**：见音频增强章节

### ⏯️ 播放增强

- **断点续播**：自动保存本地视频播放位置，重新打开时恢复（最小恢复位置 5 秒，距结尾 3 秒内不恢复），支持断点列表管理

- **每文件播放设置持久化**：按 URL 持久化音轨/字幕轨/音量/静音/画面比例/旋转/翻转/字幕延迟/音频延迟，LRU 淘汰（最多 300 个文件）

- **跳过片头/片尾**：可配置片头秒数和片尾秒数，自动跳过（安全限制：跳过秒数必须小于 duration 的 80%）

- **播放队列**：循环模式、AB 循环、逐帧播放，支持队列管理

- **书签管理**：为视频关键时间点添加书签，快速跳转

- **切片导出 / GIF 制作**：

  - 视频片段导出（mp4/mkv/webm），支持流复制（快）和重编码（H.264 + AAC，CRF 22）

  - GIF 制作（两步法：ffmpeg 抽帧 + Pillow 合成，避免色板失真），可配置宽度和 FPS

- **撤销/重做**：频道编辑操作支持撤销/重做（Ctrl+Z / Ctrl+Shift+Z），最大栈深度 200，支持批量命令原子操作

### 🎨 界面与体验

- **颜色模式 × 视觉风格组合主题**：3 种颜色模式与 7 种视觉风格任意组合，共 21 种搭配

  - **颜色模式**：自动（跟随系统）、暗黑、日间

  - **视觉风格**：拟态、扁平化、拟物、毛玻璃、Win11、Mac、iOS

- **双语界面**：中文 / English 一键切换

- **日志等级切换**：帮助菜单可切换 DEBUG / INFO / WARNING / ERROR 日志等级，方便调试和排查问题

- **三栏布局**：左侧 EPG 节目单 | 中间视频区域 | 右侧频道列表面板

- **悬浮面板**：EPG 列表、频道列表、播放控制面板均可独立开关

- **系统托盘**：关闭窗口时可选择最小化到系统托盘（继续执行定时提醒）或直接退出，双击托盘图标恢复主窗口

- **文件关联**：可自定义关联 .m3u/.m3u8/.txt 及常见视频格式，右键即可用本程序打开

- **拖放打开**：支持将文件直接拖放到主窗口打开

- **键盘快捷键**：

  - `Space` 播放/暂停

  - `Escape` 退出全屏 / 停止播放

  - `F11` / `F` 全屏

  - `Tab` 切换 OSD 遮罩

  - `E` / `L` / `M` 切换面板

  - `Y` 隐藏/恢复所有悬浮面板

  - `P` 画中画

  - `↑` / `↓` 切换频道

  - `←` / `→` 快退 / 快进 10 秒

  - `Backspace` 切换到上一个频道

  - `.` / `,` 增加 / 降低播放速度 0.1

  - `,` / `.` 逐帧后退 / 前进（播放队列模式）

  - `滚轮` 调整音量

  - `S` 截图

  - `Ctrl+Z` 撤销

  - `Ctrl+Shift+Z` / `Ctrl+Y` 重做

  - `Ctrl+O` 打开播放列表

  - `Ctrl+Shift+O` 打开视频文件

  - `Ctrl+S` 另存为

  - `Ctrl+U` 打开流地址

  - `Ctrl+Q` 退出程序

  - `Ctrl+M` 静音切换

  - `Ctrl+Shift+←` / `Ctrl+Shift+→` 切换频道

  - `F5` 刷新界面

  - `Ctrl+Shift+F` 全局搜索

### ⚙️ 订阅与自动化

- **多源管理**：支持配置多个播放列表源和多个 EPG 源，独立管理

- **独立缓存**：每个播放列表源拥有独立的 M3U 缓存文件和更新时间记录

- **智能更新**：

  - 启动时根据各源的更新时间间隔独立判断是否需要刷新

  - 保存设置时仅对实际变化的源触发重载（改名字不重载）

  - EPG 支持增量更新——只重新下载变化的那个源并合并

- **编辑功能**：双击列表项即可编辑已添加的源或 EPG 地址

- **缓存回退**：在线下载失败时自动回退到本地缓存；缓存为空时强制在线刷新

- **过期策略**：可配置的过期时间，到期自动刷新

- **配置持久化**：所有设置自动保存到 config.ini

### 🌐 内置 Web 服务器

- **本地服务**：内置 aiohttp 轻量级 Web 服务器，提供频道列表、播放接口、EPG、扫描、订阅等完整 RESTful API

- **远程控制**：通过浏览器访问频道列表和控制播放

- **流代理**：`/stream/{id}` 路由提供频道流代理，支持直连播放

- **管理后台**：`/admin/` 提供 8 个 Tab 的完整 Web 管理界面（PC/Linux/macOS/Android 通用）

  - 订阅源管理（启用/禁用切换、最后更新时间）、EPG 源管理、频道管理（列表/搜索/分页/分组筛选/**来源过滤（全部/订阅/本地）**/CRUD/导入 M3U）

  - **频道来源区分**：订阅频道标记为只读（不可编辑/删除），本地频道可完整 CRUD 操作；导入 M3U 文件自动写入本地频道列表并持久化

  - URL 范围扫描（实时状态轮询/结果列表）、频道映射管理（添加/删除/刷新远程）

  - 节目单 EPG 浏览（自动加载频道列表+节目详情，当前节目高亮）、缓存管理（清空缩略图/截图/字幕/全部）

  - **虚拟遥控器**：通过浏览器远程控制 TV 端（方向键/确定/频道切换/播放控制/音量/菜单/返回/OSD），100ms 轮询命令队列，2s 轮询显示当前播放状态（频道名/播放状态/硬解软解/分辨率/编码/帧率/HDR/音量）

- **PWA 支持**：移动端 UI 支持 PWA 安装，Service Worker 采用 network-first 缓存策略

### 📱 Android 播放器（手机 / 平板 / TV）

Android 端采用 **Kotlin Compose + Chaquopy Python 两层架构**，与 PC 端共用同一套 Python 业务后端，UI 全部用 Jetpack Compose 原生构建（已替换早期的 WebView 方案），整体为液态玻璃质感（iOS 拟态玻璃风格，深浅色主题自适应，统一画布背景 + 玻璃卡片磨砂透出）。

#### 架构

| 层        | 技术                                    | 职责                                                            |
| -------- | ------------------------------------- | ------------------------------------------------------------- |
| UI + 渲染层 | Kotlin（Jetpack Compose + MPVView\.kt） | Compose 声明式 UI、液态玻璃质感界面、竖屏/横屏分屏双布局、SurfaceView + JNI 调用 libmpv.so 渲染视频、TV/手机双模式适配 |
| 业务层      | Python（Chaquopy 3.11）                 | 复用 PC 端 core/services 模块处理订阅/扫描/EPG/映射；按需启动 LAN admin 服务器     |

#### 核心功能

- **界面布局**：竖屏 / 横屏双布局自动适配——竖屏采用底部弹出 Sheet 面板与 APTV 风格首页；横屏（平板/TV）采用左右分屏（首页：宫格频道卡 + EPG 时间线；播放页：视频区 + 常驻玻璃功能面板），TAB 底栏悬浮居中贴底，全屏播放页提供 **18 种底栏样式**（信息详情、单行紧凑、居中控制台、居中悬浮、广播电视、机顶盒 OSD、影院 EPG 卡、仪表盘、海报卡片、节目时间轴等，含台标/节目单/进度/时钟/网速/媒体徽章等信息组合），样式弹窗实时预览一键切换

- **双播放内核**：MPV Native 渲染 + ExoPlayer 双内核（与 PC 端架构统一），MP2 音频链路异常时自动兜底切换 MPV，兼顾兼容性与播放稳定性

- **DLNA 投屏**：SSDP 搜索局域网渲染设备（电视/盒子），AVTransport SOAP 推流投屏

- **视频播放**：支持播放/暂停/停止、音量、倍速、画面比例、音轨/字幕切换、hwdec 软硬解切换、**FCC 换台优化**（识别 URL 中的 `fcc=` 参数，按端点发送 LEAVE/JOIN 并调小 `probesize`/`analyzeduration`；实际效果依赖服务端支持）

- **HDR 模式切换**：禁用/自动/色调映射/直通 4 种模式，文件加载时自动检测 HDR（gamma=pq/hlg 或 sig-peak>1.0）并应用

  - `PASSTHROUGH`：清空 target-prim/target-trc + 启用 `target-colorspace-hint=yes`，让 Android 系统自动切换 HDR 显示模式；PQ 视频设置 `target-peak=10000` + `tone-mapping=clip`，HLG 视频使用自动 target-peak + `hdr-compute-peak=yes` 避免阴阳脸

  - `TONEMAP`：保留 `target-prim=bt.2020` 广色域 + `target-trc=bt.1886` SDR 伽马，`tone-mapping=auto`（HDR10+→st2094-40，HDR10/HLG→bt.2390）

  - `AUTO`：通过 `Display.getHdrCapabilities()` 检测设备 HDR 能力，支持则走直通，否则走色调映射

  - **PQ/HLG 差异化处理**：PQ 视频启用 `hdr10-opt=yes` 传递 HDR10+ 动态元数据；HLG 视频禁用 `hdr10-opt=no` 避免处理不存在的元数据导致偏色

  - **WCG 广色域**：检测 BT.2020 色域 + SDR 亮度的视频时，设置 `target-prim=bt.2020` + `gamut-mapping-mode=relative` 正确显示广色域

- **多画面预览**：DUAL（左右分屏）与 QUAD（2×2 网格）多画面同时预览，主画面复用现有 MPV 播放器，副画面使用独立 MPV 实例渲染

- **3D / 360° 视频**：5 种 3D 立体模式（mono/sbs/sbs2/ab/ab2）+ 360° 视角控制（panorama 滤镜，flat/equirect/cubemap 投影 + yaw/pitch/roll）

- **控制面板**：3 行布局对齐 PC 端——媒体信息徽章、节目信息行、控制行（上一/下一频道、播放/暂停/停止、进度条、音量、倍速、画面比例、音轨、字幕）

- **频道列表**：5 个 Tab（订阅 / 本地 / 收藏 / 历史 / 队列），搜索框、分组筛选

- **EPG 节目单**：节目列表、当前节目 LIVE 徽章 + 自动居中、过去节目点击触发回看、当前/未来节目设置提醒、**±7 天日期切换**

- **EPG 时间线视图**：多频道时间线对照（与 PC 端对齐）

- **时移 / 回看**：对齐 PC 端逻辑，进度条点击触发时移，EPG 过去节目点击触发 catchup

- **全局搜索**：跨频道名称/URL/分组/EPG 节目标题统一搜索

- **流质量检测**：实时探测视频分辨率/编解码/码率/帧率

- **书签管理**：频道书签的添加/列表/跳转/删除

- **字幕**：轨切换/显示/延迟/缩放/位置、**字幕样式高级**（颜色/字体/边框/阴影/加粗/斜体 + 4 种快速预设）、在线字幕搜索下载

- **音频**：音轨切换/延迟/10 段 EQ 预设、**音频音调**（audio-pitch-correction，0.5\~2.0，变调不变速）

- **截图**：单张/连拍（间隔+总数可调，进度条显示）、含字幕/含 OSD 模式

- **播放设置**：循环模式（单曲/列表/强制）、**随机播放 shuffle**（应用层随机选索引，避免短期重复，支持上一频道回退）、A-B 循环、逐帧、速度、章节

- **视频设置**：图像调整（亮度/对比度/饱和度/色调/Gamma）、旋转、翻转、3D/360

- **频道扫描**：独立 `StandaloneScanner`（requests + threading），支持 IP 范围扫描

- **订阅管理**：多源管理、独立缓存、启用/禁用切换、状态显示（优先 `/api/sources/status` 的 channels 字段）、添加订阅源自动触发加载

- **LAN 管理后台**：启动局域网 admin 服务器，二维码扫码访问（自动展开），5 分钟自动停止 + 倒计时（可关闭自动停止），端口冲突自动递增，虚拟遥控器命令轮询

- **画中画（PiP 增强）**：`onUserLeaveHint()` 自动进入 PiP，按视频实际宽高比设置窗口（消除黑边）、sourceRectHint 动画过渡、Android 12+ setAutoEnterEnabled + setSeamlessResizeEnabled、进入 PiP 自动关闭面板隐藏控制层

- **全屏切换**：沉浸式全屏

- **遥控器适配（TV 端）**：DPAD 方向键（面板开启时由 Compose 焦点系统导航，面板关闭时上下切换频道、左右切换面板）、CENTER/ENTER（播放暂停）、菜单键（主菜单）、返回键（关闭面板/退出）、SPACE/M（播放暂停）、音量键

  - **tvFocusBorder 焦点高亮**：4dp 金色边框 + 半透明白色背景，焦点切换清晰可见

  - **频道台标显示**：频道列表使用 Coil AsyncImage 加载显示每个频道的台标（logo）

  - **默认焦点当前频道**：打开播放列表时自动滚动到当前播放频道位置

  - **控制面板自动隐藏**：4 秒无操作后自动隐藏控制面板，切换频道时自动显示

  - **EPG 跟随焦点**：频道列表中切换焦点时，EPG 节目单跟随显示焦点频道的节目信息

- **本地文件打开**：SAF（Storage Access Framework）支持打开本地播放列表和视频

- **MPV 统一内核**：仅使用 MPV 内核（与 PC 端架构统一），通过 `hwdec` 属性运行时切换硬解码/软解码（auto-copy 硬解 / no 软解）

- **版本检查更新**：与 PC 端 `UpdateController` 对齐，通过 GitHub API 检查最新 release

  - 启动后自动延迟检查（初始化完成 5 秒后，避免影响启动性能）

  - 发现新版本时自动弹出对话框 + OSD 提示，提供「前往下载」按钮跳转浏览器

  - 「关于」面板提供手动「检查更新」按钮，显示检查状态（检查中/最新/发现新版本/失败）

  - 版本号从 `PackageManager` 动态读取（与 `build.gradle` versionName 一致）

#### 构建要求

- Android Studio + Gradle 8.7.0

- compileSdk 35 / minSdk 28 / targetSdk 35

- Chaquopy（Python 3.11）

- Kotlin 2.0.21 / JVM 21

- ABI：arm64-v8a、armeabi-v7a、x86\_64、x86（4 种通用架构）

- 依赖原生库：libmpv.so、libplayer.so、FFmpeg 系列（libavcodec/libavformat/libavfilter/libavutil/libswscale/libswresample）

- 签名：Release 构建使用 `release.keystore` 签名（同 CI 工作流）

#### 构建与安装

```bash
cd android
./gradlew.bat assembleRelease        # 构建 Release APK（需配置 release.keystore）
adb install -g app/build/outputs/apk/release/app-release.apk

# 按架构构建
./gradlew.bat assembleRelease -PtargetAbi=armeabi-v7a   # 32位 ARM（电视盒）
./gradlew.bat assembleRelease -PtargetAbi=arm64-v8a     # 64位 ARM（手机）
```

> **MPV 原生库来源**：仓库 `android/` 目录下附带的 `mpv-arm64.apk`、`mpv-x86_64.apk` 用于提取 libmpv.so 等原生库到 `app/src/main/jniLibs/`。armeabi-v7a 和 x86 架构的 libmpv.so 由 `build-tmp/cavs-android/jniLibs/` 目录提供。

> **各 ABI MPV 可用性**：
>
> - **arm64-v8a**（推荐）：MPV 可用
>
> - **armeabi-v7a**（电视盒）：MPV 可用（从 cavs-android 提取）
>
> - **x86\_64**：MPV 可用
>
> - **x86**（主要为模拟器）：MPV 可用（从 cavs-android 提取）

> **PC 端 Python 模块打包**：Chaquopy 构建时会将项目根目录的 `core/`、`services/`、`server/` 等 Python 包打包进 APK（通过 `extractPackages "server"` 指令解压 server 包，其余以 .zip 形式加载）。`android/app/src/main/python/android_bridge.py` 是 Android 端唯一的 Python 入口文件，运行时通过 `import server` / `import core` 等动态导入 PC 端模块。

> **数据持久化**：覆盖安装 APK 后，订阅源、EPG 源、设置等数据自动保留。所有数据（config.ini、缓存、收藏等）统一存放在外部存储根目录的 `/sdcard/ISEP/` 下（三级回退：`/sdcard/ISEP/` → `getExternalFilesDir()/ISEP/` → `getFilesDir()/ISEP/`），与 Chaquopy 资产解压目录完全隔离，不受 APK 版本更新影响。首次启动时会自动从旧目录（`ISEPP` 或 `IPTV_Scanner_Editor_Pro`）迁移历史数据。

## 🚀 快速开始

### 方式一：直接运行（推荐）

```bash
python main.py
```

> **注意**：运行需要 `mpv/` 目录（含 `libmpv-2.dll` on Windows / `libmpv.2.dylib` on macOS / `libmpv.so.2` on Linux）和 `ffmpeg/` 目录（含 `ffprobe.exe` on Windows / `ffprobe` on macOS/Linux），这些二进制文件未纳入版本控制。请自行下载 [MPV](https://mpv.io/) 和 [FFmpeg](https://ffmpeg.org/) 并放置到对应目录。

### 方式二：从源码安装依赖

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

### 系统要求

- **操作系统**：Windows 10/11, macOS 10.15+, Linux (x86\_64 / ARM64), Android 9.0+ (API 28)

- **Python**：3.8+（PC 端）/ Python 3.11（Android 端，由 Chaquopy 内嵌）

- **内存**：2GB RAM 以上

- **网络**：需要网络连接用于频道扫描、EPG 下载和流媒体播放

### Linux 支持

本项目已支持 Linux 平台（x86\_64 / ARM64），感谢 [@EricYin](https://github.com/EricYin) 的贡献。

- Linux ARM64 已添加 GitHub CI/CD workflow 来帮助编译

- ffprobe 和 ffmpeg 静态构建版本会编译进入程序本体，请参考 workflow 中 yml 文件的下载路径

- 在 Linux 系统上运行前，请确保安装系统依赖：

  ```bash
  sudo apt update
  sudo apt install libmpv-dev
  ```

### macOS 支持

- 运行前请安装依赖：`brew install mpv ffmpeg`

- 打包为 `.app` bundle，可直接分发

### Android 支持

- Android 端代码位于 `android/` 目录，采用 Kotlin Compose + Python 两层架构

- 需 Android Studio + Gradle 8.7.0 构建，详见上文「Android 播放器」章节

- 内嵌 Python 3.11（Chaquopy），与 PC 端共用业务后端代码

- 支持 arm64-v8a、armeabi-v7a、x86\_64、x86 四种 ABI（覆盖 32/64 位 ARM 与 x86）

- 详见 `android/app/build.gradle` 构建配置

## 📖 使用指南

### 基本流程

1. **打开播放列表**

   - 文件菜单 → 打开播放列表（Ctrl+O）

   - 支持 `.m3u` / `.m3u8` / `.txt` 格式

   - 也可直接将文件拖放到主窗口打开

2. **配置订阅（可选）**

   - 工具菜单 → 订阅设置

   - 添加多个播放列表源和 EPG 数据源地址

   - 单击列表项切换启用源，双击编辑源信息（URL / 名称）

   - 编辑模式下输入框清空可退出编辑模式

   - 配置过期时间和自动刷新策略

3. **播放频道**

   - 双击右侧频道列表中的任意频道开始播放

   - 底部控制面板：▶ 播放 / ▮▮ 暂停 / ■ 停止

   - 调节音量滑块、切换倍速、调整画面比例

   - 点击 ⛶ 全屏或按 F11

   - ↑↓ 键快速切换频道，←→ 键快退/快进，滚轮调整音量

4. **查看节目单**

   - 左侧 EPG 面板显示当前选中频道的节目安排

   - 点击 ◀ / ▶ 切换日期查看不同天的节目

   - 进度条显示当前播放位置

5. **扫描整理频道**

   - 工具菜单 → 扫描整理

   - 输入 IP 范围（如 `239.3.1.[1-100]:8000`）

   - 设置超时和线程数后开始扫描

   - 搜索过滤：输入框实时过滤频道名/URL/分组（Ctrl+F）

   - 右键菜单：全选/反选/选有效/选无效/批量删除

   - 扫描完成后可使用批量操作：自动分类、清理名称、匹配台标

   - 快捷键：Ctrl+S 保存、Ctrl+A 全选、Delete 删除选中

   - 导出时可选择仅导出选中频道

6. **保存结果**

   - 文件菜单 → 另存为（Ctrl+S）

   - 选择 M3U / TXT / Excel 格式导出

### 高级功能

#### 频道映射

- 工具菜单 → 频道映射管理器

- 可视化编辑频道名称、LOGO、分组的映射规则

- 支持提交自定义映射到仓库

#### 文件关联

- 工具菜单 → 文件关联

- 勾选需要关联的文件格式（M3U/M3U8/TXT/视频格式）

- 关联后可直接从资源管理器右键打开

#### 主题与语言

- 语言菜单：切换 中文 / English

- 主题菜单：3 种颜色模式 × 7 种视觉风格 = 21 种主题组合即时切换，全局生效

#### 面板控制

- 视图菜单或快捷键：

  - **E** — 显示/隐藏 EPG 节目单面板

  - **L** — 显示/隐藏频道列表面板

  - **M** — 显示/隐藏播放控制面板

  - **Y** — 隐藏/恢复所有悬浮面板

## 📁 项目结构

```
guangyu/
├── pyqt_player.py              # 主窗口 & 播放器核心（954行，15个Mixin + QMainWindow）
├── build.py                    # PyInstaller 打包脚本
├── requirements.txt            # Python 依赖
├── mixins/                     # Mixin 模块（从 IPTVPlayer 拆分的职责）
│   ├── __init__.py             # Mixin 导出
│   ├── server_mixin.py         # Server启停/设置
│   ├── tray_mixin.py           # 系统托盘
│   ├── update_mixin.py         # 更新检查
│   ├── thumbnail_mixin.py      # 缩略图/Logo回调
│   ├── file_ops_mixin.py       # 文件操作/本地视频
│   ├── panel_mixin.py          # 面板可见性/订阅/EPG回调
│   ├── progress_mixin.py       # 进度条/Seek
│   ├── playback_mixin.py       # 播放控制/OSD/窗口调整
│   ├── epg_mixin.py            # EPG/回看/本地文件判断
│   ├── channel_mixin.py        # 频道列表/选择/搜索/分组
│   ├── settings_mixin.py       # 设置/主题/语言
│   ├── window_mixin.py         # 窗口事件/定位/全屏/覆盖层
│   ├── control_panel_mixin.py  # 底部控制面板UI构建
│   ├── playlist_panel_mixin.py # 播放列表面板/EPG面板UI构建
│   └── event_mixin.py          # Qt事件覆写/拖放修复
├── tests/                      # 单元测试
│   ├── conftest.py             # MockMainWindow 基类
│   ├── test_mixins.py          # Mixin 测试（前9个）
│   ├── test_mixins_round4.py   # Mixin 测试（第4轮）
│   └── test_mixins_round5.py   # Mixin 测试（第5轮）
├── core/                       # 核心模块
│   ├── application_state.py    # 应用程序状态管理
│   ├── config_manager.py       # 配置管理（INI）
│   ├── language_manager.py     # 多语言管理（内置 zh/en 翻译）
│   ├── log_manager.py          # 日志管理
│   ├── panel_visibility.py     # 面板可见性状态
│   ├── play_state.py           # 播放状态枚举
│   ├── playback_settings_store.py # 每文件播放设置存储（LRU 持久化）
│   ├── subscription_manager.py # 订阅源管理（多源/独立缓存/增量更新）
│   └── version.py              # 版本信息
├── controllers/                # 控制器层
│   ├── bookmark_controller.py  # 书签控制器
│   ├── catchup_controller.py   # 时移/回看控制器
│   ├── channel_controller.py   # 频道管理控制器
│   ├── epg_controller.py      # EPG 电子节目单控制器
│   ├── epg_reminder_controller.py # EPG 节目提醒控制器
│   ├── event_handler.py       # 事件处理器
│   ├── favorites_controller.py # 收藏控制器
│   ├── file_queue_controller.py # 播放队列控制器（循环/AB循环/逐帧）
│   ├── main_window_protocol.py # 主窗口协议接口
│   ├── media_controller.py    # 媒体控制器
│   ├── multi_screen_controller.py # 多屏控制器
│   ├── pip_controller.py      # 画中画控制器
│   ├── playback_controller.py  # 播放控制
│   ├── playback_settings_controller.py # 每文件播放设置控制器
│   ├── progress_controller.py  # 进度控制器
│   ├── resume_playback_controller.py # 断点续播控制器
│   ├── settings_file_ops.py    # 设置文件操作
│   ├── skip_intro_outro_controller.py # 跳过片头/片尾控制器
│   ├── subscription_controller.py      # 订阅控制器
│   ├── subscription_ui_controller.py   # 订阅 UI 控制器
│   ├── ui_controller.py       # UI 控制器
│   ├── update_controller.py   # 自动更新控制器
│   └── window_controller.py    # 窗口控制器
├── models/                     # 数据模型
│   ├── channel_model.py       # 频道数据模型
│   └── channel_mappings.py    # 频道映射模型
├── services/                   # 服务层
│   ├── audio_visual_service.py # 音频可视化服务（7种3D样式 + FFT + 歌词）
│   ├── autocrop_service.py    # 自动裁剪黑边服务（PIL+numpy 边缘分析）
│   ├── channel_classifier.py  # 频道自动分类服务（正则规则引擎）
│   ├── channel_cleaner.py     # 频道名称清理服务
│   ├── channel_dedup_service.py # 频道去重服务
│   ├── channel_quick_jump_service.py # 频道快速跳转服务
│   ├── channel_rating_service.py # 频道评分服务
│   ├── clip_export_service.py # 切片导出/GIF制作服务（FFmpeg+Pillow）
│   ├── epg_matcher.py         # EPG 模糊匹配引擎
│   ├── epg_reminder_service.py # EPG 提醒服务
│   ├── epg_search_service.py  # EPG 搜索服务
│   ├── favorites_service.py   # 收藏与历史服务
│   ├── fcc_service.py         # FCC 快速换台服务（组播代理通知）
│   ├── ffprobe_validator_service.py # FFprobe 频道验证服务（当前使用）
│   ├── logo_cache_service.py   # 台标缓存服务（异步+DPI）
│   ├── logo_matcher.py        # 台标智能匹配服务（400+ 规则）
│   ├── m3u_parser.py          # M3U 播放列表解析器
│   ├── mpv_common.py          # MPV 公共模块
│   ├── mpv_gl_widget.py       # MPV OpenGL 渲染组件
│   ├── mpv_player_service.py # MPV 播放引擎（libmpv，HDR/翻转/旋转/A-V同步/运动补偿/分辨率提升/AI着色器）
│   ├── hardware_detect_service.py # 硬件检测服务（CPU/GPU/RAM 检测 + 智能推荐）
│   ├── mpv_validator_service.py # MPV 频道验证服务（旧版）
│   ├── scanner_service.py     # 频道扫描服务
│   ├── stream_quality_scorer.py # 流质量评分服务
│   ├── subtitle_download_service.py # 在线字幕下载服务（3源聚合+IMDB中转）
│   ├── thumbnail_service.py   # 缩略图服务
│   ├── undo_stack.py          # 撤销/重做栈（命令模式）
│   └── url_parser_service.py  # URL 解析服务
├── server/                     # 内置 Web 服务器
│   ├── app.py                 # Web 应用入口
│   ├── context.py             # 服务器上下文/单例
│   ├── routes.py              # 路由定义
│   ├── admin/                 # 管理后台 UI（PC/Android 通用）
│   │   └── index.html         # 管理后台单页应用（8 Tab：订阅源/EPG源/频道管理/扫描/映射/EPG浏览/缓存/遥控器）
│   └── mobile/                # 移动端 UI（PWA）
│       ├── index.html         # 移动端单页应用
│       ├── manifest.json      # PWA 清单
│       ├── sw.js              # Service Worker（network-first）
│       └── logo.png           # 移动端 Logo
├── ui/
│   ├── dialogs/
│   │   ├── about_dialog.py    # 关于对话框（含版本检查）
│   │   ├── audio_eq_dialog.py # 音频均衡器对话框（10段EQ+预设+声道）
│   │   ├── av_sync_dialog.py  # A/V 同步监控对话框（波形图+字幕自动同步）
│   │   ├── bookmark_dialog.py # 书签管理对话框
│   │   ├── burst_screenshot_dialog.py # 连拍截图对话框
│   │   ├── clip_export_dialog.py # 切片导出/GIF制作对话框
│   │   ├── epg_search_dialog.py # EPG 搜索对话框
│   │   ├── epg_timeline_dialog.py # EPG 时间轴对话框
│   │   ├── file_association_dialog.py # 文件关联对话框
│   │   ├── global_search_dialog.py # 全局搜索对话框
│   │   ├── mapping_manager_dialog.py # 映射管理器
│   │   ├── network_enhance_dialog.py # 网络流增强对话框（Referer/代理/Headers）
│   │   ├── playback_queue_dialog.py # 播放队列对话框（循环/AB循环/逐帧）
│   │   ├── reminder_manager_dialog.py # 提醒管理对话框
│   │   ├── reminder_popup.py  # 节目提醒弹窗
│   │   ├── resume_position_dialog.py # 断点续播列表对话框
│   │   ├── scan_channel_dialog.py # 扫描频道对话框
│   │   ├── stream_quality_dialog.py # 流质量检测对话框（实时显示 mpv 流信息，对齐 Android/Web 端）
│   │   ├── subtitle_style_dialog.py # 字幕样式+在线下载对话框
│   │   ├── unified_search_dialog.py # 统一搜索对话框
│   │   ├── video_3d_dialog.py # 3D/360°视频对话框
│   │   ├── video_eq_dialog.py # 视频图像调整对话框（亮度/对比度/旋转/翻转/裁剪/运动补偿/分辨率提升/AI着色器/智能预设/硬件检测）
│   │   └── video_open_dialog.py # 视频文件打开对话框
│   ├── cache_progress_slider.py # 缓存进度滑块组件
│   ├── channel_transition_overlay.py # 频道切换遮罩组件
│   ├── epg_timeline_widget.py # EPG 时间轴组件
│   ├── floating_dialog.py     # 悬浮对话框基类（Windows 隐藏任务栏图标）
│   ├── lyrics_widget.py       # 歌词显示组件（LRC 解析+滚动）
│   ├── menu_proxy_style.py    # 菜单代理样式
│   ├── multi_screen_widget.py # 多屏窗口组件
│   ├── quality_bar.py         # 质量评分条组件
│   ├── styles.py              # 21 套主题样式定义
│   ├── theme_manager.py       # 主题管理器
│   ├── virtual_channel_list.py # 虚拟频道列表组件
│   └── wallpaper_widget.py    # 壁纸背景组件（视频区域背景）
├── utils/                      # 工具模块
│   ├── config_notifier.py     # 配置变更通知器
│   ├── error_handler.py       # 错误处理器
│   ├── general_utils.py       # 通用工具函数
│   ├── hdr_detect.py          # HDR 检测工具
│   ├── logging_helper.py      # 日志辅助函数
│   ├── memory_manager.py      # 内存管理器
│   ├── platform_utils.py      # 平台工具（ffmpeg 路径定位等）
│   ├── progress_manager.py    # 进度管理器
│   ├── resource_cleaner.py    # 资源清理器
│   ├── scan_state_manager.py  # 扫描状态管理器
│   ├── singleton.py           # 单例模式基类
│   └── thread_safety.py       # Qt 线程安全工具
├── img/                        # 台标图片库（400+ 频道 Logo）
├── resources/logo.ico          # 程序图标
├── cache/                      # 运行时缓存（自动生成）
│   ├── logo_cache/            # 台标图片缓存（从 tvg-logo URL 下载）
│   │   ├── meta.json          # 缓存元数据
│   │   └── *.png              # 各频道台标文件
│   ├── epg_cache.json         # EPG 数据缓存（全量合并）
│   ├── playlist_cache_0.m3u   # 播放列表源 #0 的独立缓存
│   ├── playlist_cache_1.m3u   # 播放列表源 #1 的独立缓存
│   ├── playback_settings.json # 每文件播放设置持久化（LRU）
│   └── ...                    # 每个播放列表源一个独立缓存文件
├── logo/                       # 本地频道台标图片库
└── android/                    # Android 移动端工程
    ├── app/                    # 主应用模块
    │   ├── src/main/
    │   │   ├── java/com/iptv/scanner/editor/pro/
    │   │   │   ├── MainActivityCompose.kt  # 唯一 Activity（入口，Compose 宿主 + PiP + 遥控器）
    │   │   │   ├── data/                   # 数据层（Kotlin）
    │   │   │   │   ├── IptvModels.kt       # 数据模型（频道/EPG/书签/提醒/AdminServerInfo 等）
    │   │   │   │   ├── IptvRepository.kt   # 数据仓库（调用 Python bridge）
    │   │   │   │   └── UserPrefs.kt        # SharedPreferences 持久化
    │   │   │   ├── mpv/                    # MPV 渲染层（Kotlin）
    │   │   │   │   ├── MPVView.kt          # SurfaceView + mpv 渲染
    │   │   │   │   └── MpvController.kt    # Compose 友好的 mpv 控制器（StateFlow + 命令）
    │   │   │   ├── player/                 # MPV 播放内核层
    │   │   │   │   ├── Player.kt           # 统一播放器接口（含软硬解切换接口）
    │   │   │   │   ├── MpvPlayerController.kt # MPV 控制器（hwdec 软硬解切换，MPV 统一内核）
    │   │   │   │   ├── PlaybackState.kt    # 播放状态枚举
    │   │   │   │   ├── CatchupHelper.kt    # 回看/时移辅助
    │   │   │   │   ├── FccHelper.kt       # FCC 秒开换台辅助（UDP 通知 FCC 代理 + probesize/analyzeduration 优化，对齐 PC 端 fcc_service.py）
    │   │   │   │   └── ProgressHelper.kt   # 进度条逻辑（对齐 PC 端）
    │   │   │   └── ui/                     # Compose UI 层
    │   │   │       ├── AppViewModel.kt     # 核心 ViewModel（所有功能入口）
    │   │   │       ├── MainPlayerScreen.kt # 主播放界面
    │   │   │       ├── ControlPanel.kt     # 3 行控制面板
    │   │   │       ├── ChannelsPanel.kt    # 频道列表（5 Tab）
    │   │   │       ├── EpgPanel.kt         # EPG 节目单（±7 天日期切换）
    │   │   │       ├── EpgTimelinePanel.kt # EPG 时间线视图
    │   │   │       ├── FileBrowserPanel.kt # SAF 文件浏览器（本地播放列表/视频选择，TV 焦点适配）
    │   │   │       ├── SearchPanel.kt      # 全局搜索
    │   │   │       ├── StreamQualityPanel.kt # 流质量检测
    │   │   │       ├── SourceManagerPanel.kt # 订阅源管理 + LAN 管理（自动关闭开关）
    │   │   │       ├── MainMenuPanel.kt    # 主菜单
    │   │   │       ├── PlayerSettingsPanel.kt # 播放器设置（VO/HWDEC 软硬解切换/HDR 模式）
    │   │   │       ├── MorePanels.kt       # 视频/音频/字幕/播放/截图/关于面板集合
    │   │   │       ├── MultiViewOverlay.kt # 多画面网格容器（DUAL 左右分屏 / QUAD 2×2 网格）
    │   │   │       ├── MultiViewModels.kt  # 多画面视图模型（状态/布局切换）
    │   │   │       ├── QrCodeUtil.kt       # 二维码生成
    │   │   │       ├── SplashScreen.kt    # 启动画面（ViewModel 初始化）
    │   │   │       ├── UiMode.kt          # UI 模式枚举（TV/手机）
    │   │   │       ├── TvUnifiedPanel.kt  # TV 端统一面板（频道列表+EPG+台标+焦点跟踪）
    │   │   │       └── theme/              # 主题 + TvFocus（4dp 金色焦点边框）
    │   │   ├── python/                # 内嵌 Python 后端（Chaquopy 3.11）
    │   │   │   └── android_bridge.py  # Python 服务启动入口（IPTV_DATA_DIR 设置 + 虚拟遥控器命令队列；运行时 import server/core/services 动态加载 PC 端模块）
    │   │   ├── jniLibs/               # 原生库（arm64-v8a / armeabi-v7a / x86_64 / x86，构建时从 mpv-*.apk 提取）
    │   │   └── AndroidManifest.xml
    │   └── build.gradle               # 应用级构建脚本
    ├── mpv-arm64.apk                  # 预打包 mpv 库 APK（arm64-v8a，提取 libmpv.so）
    ├── mpv-x86_64.apk                 # 预打包 mpv 库 APK（x86_64，提取 libmpv.so）
    ├── build-tmp/cavs-android/jniLibs/ # 32位 MPV 原生库（armeabi-v7a / x86，cavs-android 提取）
    └── gradlew / gradlew.bat          # Gradle 包装器
```

## 🛠️ 技术栈

| 组件             | 技术                                                      |
| -------------- | ------------------------------------------------------- |
| GUI 框架（PC）     | PySide6                                                 |
| 移动端框架（Android） | Kotlin Jetpack Compose + Chaquopy Python（MPV + ExoPlayer 双内核） |
| 播放引擎           | libmpv (MPV)                                            |
| 流探测            | FFprobe (FFmpeg)                                        |
| 片段导出 / GIF     | FFmpeg + Pillow                                         |
| HTTP 客户端       | requests / aiohttp                                      |
| 图像处理           | Pillow                                                  |
| 音频元数据          | mutagen（封面/歌词提取）                                        |
| 频谱分析           | numpy（FFT）                                              |
| Excel 处理       | openpyxl                                                |
| 拼音排序           | pypinyin                                                |
| 系统监控           | psutil                                                  |
| 配置管理           | configparser                                            |
| 类型扩展           | typing-extensions                                       |
| 字幕下载           | OpenSubtitles XML-RPC / SubHD / SubtitleCat             |

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -m 'Add xxx'`)
4. 推送分支 (`git push origin feature/xxx`)
5. 开启 Pull Request

### 提交内容

- **频道映射**：直接修改仓库中的映射文件并提交 PR

- **台标图片**：上传 PNG 格式的频道 Logo 到 `logo/` 或 `img/` 目录

- **语言翻译**：修改代码中的内置翻译（`BUILTIN_TRANSLATIONS`）

## 📞 联系方式

- **QQ群**：[757694351](https://qm.qq.com/q/lVkybTyrdK)

- **GitHub Issues**：[提交问题](https://github.com/sumingyd/guangyu/issues)

## 💖 支持项目

如果你觉得这个项目对你有帮助，欢迎赞赏支持开发！

| 微信赞赏              | 支付宝赞赏              |
| ----------------- | ------------------ |
| ![](icons/wx.png) | ![](icons/zfb.jpg) |

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

***

*本工具仅供学习和研究使用，请遵守相关法律法规。*
