package com.iptv.scanner.editor.pro

import android.app.PictureInPictureParams
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.KeyEvent
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.lifecycleScope
import com.iptv.scanner.editor.pro.mpv.MpvController
import com.iptv.scanner.editor.pro.ui.AppViewModel
import com.iptv.scanner.editor.pro.ui.MainPlayerScreen
import com.iptv.scanner.editor.pro.ui.SplashScreen
import com.iptv.scanner.editor.pro.ui.UiMode
import com.iptv.scanner.editor.pro.ui.theme.IptvTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filterIsInstance
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import com.iptv.scanner.editor.pro.ui.InitState
import com.iptv.scanner.editor.pro.ui.*

/**
 * Compose 主入口 Activity。
 *
 * 替换原 [MainActivity]（Java + WebView 三层架构），改为：
 * - Jetpack Compose 原生 UI（无 WebView）
 * - Chaquopy 直调 Python（无 HTTP 服务）
 * - MPVView 作为 AndroidView 嵌入（保留 mpv 渲染）
 *
 * 生命周期：
 * - onCreate → 初始化 ViewModel → setContent（IptvTheme 包裹）
 *   - initState == Idle/Initializing/Failed → SplashScreen
 *   - initState == Ready → MainPlayerScreen
 * - onUserLeaveHint → 自动进入 PiP（如果正在播放）
 * - onDestroy → 当前播放器 stop+detach + MpvController 兜底 detach（移除 EventObserver）
 *
 * TV 模式 DPAD 按键处理（onKeyDown）：
 * - DPAD_UP/DOWN → 上一/下一频道
 * - DPAD_LEFT/RIGHT → 直播模式：切换面板（左=EPG，右=频道列表）
 *                     回看/时移/本地视频：seek ±10 秒
 * - DPAD_CENTER/ENTER → 短按打开统一面板，长按显示控制层
 * - MENU（KEYCODE_MENU=82）→ 关闭当前面板再开主菜单
 * - BACK → 关闭面板 → 退出回看/时移 → 退出
 * - STOP → 退出回看/时移（恢复直播）或停止播放
 *
 * 媒体键处理（TV 和 PHONE 模式通用，不受面板状态影响）：
 * - MEDIA_PLAY/PAUSE/PLAY_PAUSE → 播放控制
 * - MEDIA_NEXT/PREVIOUS → 切换频道
 * - MEDIA_STOP → 停止播放
 * - MEDIA_STEP_FORWARD/FAST_FORWARD → 快进 30 秒
 * - MEDIA_STEP_BACKWARD/REWIND → 快退 30 秒
 * - VOLUME_MUTE → 静音切换
 */
class MainActivityCompose : ComponentActivity() {

    companion object {
        private const val TAG = "MainActivityCompose"
        // 触控区域边界（占屏幕比例）
        private const val LEFT_REGION_BOUND = 0.3f
        private const val RIGHT_REGION_BOUND = 0.7f
        // 底部热区占屏幕高度 20%：0.85 时手机横屏仅约 62dp，比底栏本身还矮，
        // 点击底栏上半部落进中央区被误判为暂停
        private const val BOTTOM_REGION_BOUND = 0.80f
        // 中央暂停小块：宽/高占屏幕比例（暂停区过大易误触，仅屏幕中心小块触发暂停/播放）
        private const val PAUSE_ZONE_WIDTH = 0.28f
        private const val PAUSE_ZONE_HEIGHT = 0.42f
        private const val SIDEBAR_CLOSE_BOUND = 0.82f
        // 触控阈值
        private const val SLIDE_THRESHOLD = 80f
        private const val TOUCH_SLOP = 40f
        private const val LONG_PRESS_TIMEOUT_MS = 500L
        // 多画面退出按钮区域（px）
        private const val EXIT_BUTTON_WIDTH = 300f
        private const val EXIT_BUTTON_HEIGHT = 120f
        // 右侧主菜单面板总宽（dp）：130一级列 + 1分隔 + 150二级列 + 16右边距
        private const val MENU_PANEL_WIDTH_DP = 297f
    }

    /** OK 键长按标记：长按显示控制层，跳过短按逻辑（打开统一面板） */
    private var okKeyLongPressed = false

    /** 触控滑动检测：记录 ACTION_DOWN 坐标，ACTION_UP 时判断是否为滑动 */
    private var touchDownX = 0f
    private var touchDownY = 0f
    private var touchDownTime = 0L
    private val touchSlop = TOUCH_SLOP

    /** 横屏模式判断：横屏统一用侧边栏风格布局，支持触控+遥控器 */
    private fun isLandscapeMode(): Boolean {
        return resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
    }

    /** TV 模式判断：结合 UiMode 状态（含 leanback/forceTvMode/无触屏检测），避免手机横屏误判为 TV */
    private fun isTvMode(): Boolean = viewModel.uiMode.value == UiMode.TV

    /**
     * 全屏播放页判断：左右侧边栏与全屏底栏仅在全屏布局可呼出。
     * 分屏模式（分屏首页/分屏播放页）下返回 false；多画面布局属于全屏形态，返回 true。
     * 与 TvPlayerLayout 的 useSplit = splitModePref && !multiActive 对齐。
     */
    private fun isFullscreenPlayback(): Boolean {
        return !viewModel.landscapeSplitMode.value || viewModel.multiViewState.value.active
    }

    @Suppress("DEPRECATION")
    private val viewModel: AppViewModel by viewModels {
        AppViewModel.factory(application)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 启用 edge-to-edge（沉浸式布局）：让内容绘制到状态栏/导航栏后面。
        // Android 15 (targetSdk 35) 已强制此行为，旧版本需主动调用以保持一致。
        // 视频播放器全屏沉浸（延伸到状态栏后），控制层/面板通过 systemBarsPadding 避让系统栏。
        enableEdgeToEdge()
        Log.i(TAG, "onCreate")

        // 处理外部文件打开（intent-filter 文件关联）
        handleIntent(intent)

        // 注入 PiP 回调（ViewModel 不能直接调用 Activity 方法）
        viewModel.onEnterPip = { enterPipManual() }
        // 注入全屏切换回调（竖屏→强制横屏，横屏→跟随传感器）
        viewModel.onToggleFullscreen = { toggleFullscreen() }

        // Android 13+ 通知运行时授权：EPG 节目提醒的后台系统通知依赖它；
        // 拒绝后仅影响后台提醒，应用内弹窗不受影响
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            registerForActivityResult(
                androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
            ) { granted ->
                Log.i(TAG, "POST_NOTIFICATIONS granted=$granted")
            }.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }

        setContent {
            val themeMode by viewModel.themeMode.collectAsState()
            IptvTheme(themeMode = themeMode) {
                val initState by viewModel.initState.collectAsState()
                when (initState) {
                    is InitState.Ready -> MainPlayerScreen(viewModel)
                    else -> SplashScreen(viewModel)
                }
            }
        }

        // 监听初始化完成，自动恢复上次播放的频道（如果有）
        lifecycleScope.launch {
            viewModel.initState
                .filterIsInstance<InitState.Ready>()
                .distinctUntilChanged()
                .collect { state ->
                    Log.i(TAG, "Init Ready, channels=${state.status.channelsTotal}")
                    // 恢复上次播放的频道：等待 channels 加载完成（startInitialization 已触发 loadChannels）
                    if (state.status.channelsTotal > 0 && viewModel.currentIdx.value < 0) {
                        val startTime = System.currentTimeMillis()
                        // 最多等待 5 秒 channels 加载完成
                        while (isActive && viewModel.channels.value.isEmpty() &&
                            System.currentTimeMillis() - startTime < 5_000L
                        ) {
                            delay(200L)
                        }
                        if (viewModel.channels.value.isNotEmpty() && viewModel.currentIdx.value < 0) {
                            // 优先按 URL 恢复上次播放的频道；未开启续播时仅横屏（TV 风格）
                            // 回退播放第一个频道，竖屏停留首页由用户自行选台
                            val isLandscape = resources.configuration.orientation ==
                                android.content.res.Configuration.ORIENTATION_LANDSCAPE
                            viewModel.restoreLastChannel(autoPlayFirstFallback = isLandscape)
                            Log.i(TAG, "Auto-restored last channel")
                        }
                    }
                }
        }

        // 保持屏幕常亮：视频加载后避免系统进入屏保/休眠（TV 端长时间播放必备）。
        // 根因：Android TV 系统默认在一段时间无操作后触发屏保（Daydream/Standby），
        // 视频播放类 APP 必须主动设置 FLAG_KEEP_SCREEN_ON 阻止系统熄屏。
        // fileLoaded=true（视频已加载，含播放/暂停状态）→ 屏幕常亮
        // fileLoaded=false（未加载/已停止）→ 清除 FLAG，允许系统正常休眠
        // 注：StateFlow 本身已去重（distinctUntilChanged 对 StateFlow 是 no-op）
        lifecycleScope.launch {
            viewModel.mpv.fileLoaded
                .collect { loaded ->
                    if (loaded) {
                        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        Log.i(TAG, "Keep screen on: video loaded")
                    } else {
                        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        Log.i(TAG, "Allow screen sleep: no video loaded")
                    }
                }
        }
    }

    /**
     * TV 模式 DPAD 按键处理。
     *
     * 与 PC 端键盘快捷键对齐：
     * - 方向键：DPAD_UP/DOWN 切换频道，DPAD_LEFT/RIGHT 切换面板
     * - 确认键：短按打开统一面板，长按显示控制层
     * - MENU 键：主菜单
     * - BACK：关闭面板 / 退出
     *
     * PHONE 模式下也处理部分按键（BACK、MENU），方便外接键盘测试。
     */
    /** 横屏触控处理 */
    override fun dispatchTouchEvent(ev: android.view.MotionEvent): Boolean {
        if (isLandscapeMode()) {
            val multiActive = viewModel.multiViewState.value.active
            // 横屏首页（左右双屏）：全 Compose 触控，不做分区呼出/暂停拦截
            if (viewModel.showHome.value && !multiActive) return super.dispatchTouchEvent(ev)
            if (ev.action == android.view.MotionEvent.ACTION_DOWN) {
                Log.v(TAG, "dispatchTouchEvent: ACTION_DOWN x=${ev.x}, y=${ev.y}, multiActive=$multiActive")
            }
            when (ev.action) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    touchDownX = ev.x
                    touchDownY = ev.y
                    touchDownTime = System.currentTimeMillis()
                }
                android.view.MotionEvent.ACTION_UP -> {
                    val dx = ev.x - touchDownX
                    val dy = ev.y - touchDownY
                    val moved = (dx * dx + dy * dy) > touchSlop * touchSlop
                    val duration = System.currentTimeMillis() - touchDownTime
                    val isLongPress = duration > LONG_PRESS_TIMEOUT_MS
                    val w = resources.displayMetrics.widthPixels
                    val h = resources.displayMetrics.heightPixels
                    val x = ev.x
                    val y = ev.y
                    val density = resources.displayMetrics.density

                    val sidebarOpen = viewModel.landscapeSidebarVisible.value
                    val menuOpen = viewModel.menuPanelOpen.value
                    val anyPanelOpen = sidebarOpen || menuOpen

                    if (multiActive) {
                        // ---- 多画面模式 ----
                        // 面板打开时触控交给 Compose（列表滚动等）
                        if (anyPanelOpen) return super.dispatchTouchEvent(ev)
                        // 右上角退出按钮区域：Compose 按钮未覆盖处的兜底退出区
                        if (!moved && x > w - EXIT_BUTTON_WIDTH && y < EXIT_BUTTON_HEIGHT) {
                            Log.v(TAG, "MultiView: exit button tapped")
                            viewModel.exitMultiView()
                            return true
                        }
                        val state = viewModel.multiViewState.value
                        val idx = computeMultiViewportIndex(x, y, w, h, state.layout)
                        val viewport = state.viewports.getOrNull(idx)
                        if (moved) {
                            // 上下滑动切换频道
                            if (kotlin.math.abs(dy) > kotlin.math.abs(dx) && kotlin.math.abs(dy) > SLIDE_THRESHOLD) {
                                if (dy < 0) viewModel.prevChannel() else viewModel.nextChannel()
                            }
                            return true
                        }
                        if (isLongPress && viewport != null) {
                            // 长按逻辑 Compose 无对应实现，仍由 Activity 处理：
                            // 长按主画面开主菜单；长按有频道的副画面移除频道
                            Log.v(TAG, "MultiView long press: idx=$idx, isPrimary=${viewport.isPrimary}, isEmpty=${viewport.isEmpty}")
                            if (viewport.isPrimary) {
                                viewModel.toggleMenuPanel()
                            } else if (!viewport.isEmpty) {
                                viewModel.removeFromMultiView(idx)
                            }
                            return true
                        }
                        if (!isLongPress && viewport != null && viewport.isEmpty && !viewport.isPrimary) {
                            // 单击空副画面：打开统一面板添加频道（Compose onClick 只做聚焦）
                            Log.v(TAG, "MultiView: opening TvUnifiedPanel for empty viewport $idx")
                            viewModel.toggleTvUnifiedPanel()
                            return true
                        }
                        // 其余单击（聚焦视口/静音/关闭/退出按钮）交由 Compose onClick 处理：
                        // DOWN 已通过文末 super 送达 Compose，UP 放行即完成点击
                        return super.dispatchTouchEvent(ev)
                    }

                    // ---- 非多画面模式 ----
                    val controlsVisible = viewModel.controlsVisible.value
                    if (moved) {
                        // 面板打开时滚动手势交给面板内列表，不做切台判定
                        // （修复：面板列表滚动被误判为滑动切台且 UP 被吞）
                        if (anyPanelOpen) return super.dispatchTouchEvent(ev)
                        // 分屏模式：右侧面板滚动/视频区滑动手势全部交给 Compose
                        if (viewModel.landscapeSplitMode.value) return super.dispatchTouchEvent(ev)
                        // 控制条可见时，底栏区域的拖动（进度滑杆等）交给 Compose
                        if (controlsVisible && y > h * BOTTOM_REGION_BOUND) return super.dispatchTouchEvent(ev)
                        // 上下滑动切换频道
                        if (kotlin.math.abs(dy) > kotlin.math.abs(dx) && kotlin.math.abs(dy) > SLIDE_THRESHOLD) {
                            if (dy < 0) viewModel.prevChannel() else viewModel.nextChannel()
                            return true
                        }
                        return super.dispatchTouchEvent(ev)
                    }
                    // ---- 单击（tap）----
                    // 交互总则：任何悬浮窗（左侧统一面板/右侧主菜单/底栏控制条）打开时，
                    // 点击悬浮窗以外的区域 = 关闭该悬浮窗，绝不误触暂停/切台。
                    if (sidebarOpen) {
                        // 统一面板实际内容宽度（dp）：16起始边距+48快捷列+6列间距+(多源72)+180分组+260频道+260节目单
                        val multiSource = viewModel.sources.value.count { it.enabled } > 1
                        val sidebarWidthDp = 16 + 48 + 6 + (if (multiSource) 72 else 0) + 180 + 260 + 260
                        // 面板使用 dpiScale 缩放密度（与 TvPlayerLayout/TvUnifiedPanel 一致）
                        val dpiScale = (resources.configuration.screenHeightDp / 720f).coerceIn(0.70f, 1f)
                        val pxPerDp = density * dpiScale
                        val closeBound = minOf(w * SIDEBAR_CLOSE_BOUND, sidebarWidthDp * pxPerDp + 8f * pxPerDp)
                        // 面板垂直范围：top 10dp、bottom 10dp（与 TvLayout 贴底布局一致）；
                        // 上下留白与面板右侧区域点击均关闭面板
                        val inPanelV = y > 10f * pxPerDp && y < h - 10f * pxPerDp
                        if (x < closeBound && inPanelV) return super.dispatchTouchEvent(ev)
                        viewModel.setLandscapeSidebarVisible(false)
                        return true
                    }
                    if (menuOpen) {
                        // 右侧主菜单宽度（dp）：130一级列+1分隔+150二级列+16右边距
                        val dpiScale = (resources.configuration.screenHeightDp / 720f).coerceIn(0.70f, 1f)
                        val pxPerDp = density * dpiScale
                        // 面板垂直范围：top 10dp、bottom 10dp（与 MainMenuPanel 贴底布局一致）
                        val inMenuV = y > 10f * pxPerDp && y < h - 10f * pxPerDp
                        if (x > w - (MENU_PANEL_WIDTH_DP * pxPerDp + 8f * pxPerDp) && inMenuV) return super.dispatchTouchEvent(ev)
                        viewModel.toggleMenuPanel()
                        return true
                    }
                    if (viewModel.landscapeSplitMode.value) {
                        // 分屏模式：右面板常驻、控制条常驻，视频区手势（暂停/双击全屏/上下滑切台）
                        // 由 Compose 视频触控层处理；触控全部放行，不做底栏呼出/分区拦截
                        return super.dispatchTouchEvent(ev)
                    }
                    if (controlsVisible) {
                        // 底栏控制条打开：点击底栏区域交给 Compose 按钮/滑杆；点击其他区域收起底栏
                        if (y > h * BOTTOM_REGION_BOUND) return super.dispatchTouchEvent(ev)
                        viewModel.toggleControls()
                        return true
                    }
                    // 无任何悬浮窗：分区呼出（左右边缘呼出面板，底部呼出控制条）；
                    // 仅屏幕中央小块触发暂停/恢复，小块之外的过渡区域呼出底栏控制条，
                    // 确保点击画面任意位置都不会误暂停
                    if (y > h * BOTTOM_REGION_BOUND) {
                        viewModel.toggleControls()
                        return true
                    }
                    val isLeftZone = x < w * LEFT_REGION_BOUND
                    val isRightZone = x > w * RIGHT_REGION_BOUND
                    if (isLeftZone) {
                        viewModel.setLandscapeSidebarVisible(true)
                        return true
                    } else if (isRightZone) {
                        viewModel.toggleMenuPanel()
                        return true
                    }
                    // 中央暂停小块：以屏幕中心为基准（宽 28% × 高 42%）
                    val inCenterZone = kotlin.math.abs(x - w / 2f) <= w * PAUSE_ZONE_WIDTH / 2f &&
                        kotlin.math.abs(y - h / 2f) <= h * PAUSE_ZONE_HEIGHT / 2f
                    if (inCenterZone) {
                        // 暂停/恢复以观察到的 paused 状态为准显式设置：
                        // 原 cycle pause 是盲切换，一旦 UI 状态与 mpv 真实状态错位
                        // （如音频焦点抢占后状态不同步），点击中央会"越点越暂停"
                        if (viewModel.mpv.paused.value) viewModel.mpv.setPause(false)
                        else viewModel.mpv.setPause(true)
                    } else {
                        viewModel.toggleControls()
                    }
                    return true
                }
            }
        }
        return super.dispatchTouchEvent(ev)
    }

    /** 根据点击位置计算多画面视口索引 */
    private fun computeMultiViewportIndex(
        x: Float, y: Float, w: Int, h: Int, layout: com.iptv.scanner.editor.pro.ui.MultiViewLayout
    ): Int {
        if (w <= 0 || h <= 0) return -1
        return when (layout) {
            com.iptv.scanner.editor.pro.ui.MultiViewLayout.DUAL -> if (x < w / 2f) 0 else 1
            com.iptv.scanner.editor.pro.ui.MultiViewLayout.QUAD -> {
                val col = if (x < w / 2f) 0 else 1
                val row = if (y < h / 2f) 0 else 1
                row * 2 + col
            }
            com.iptv.scanner.editor.pro.ui.MultiViewLayout.NINE -> {
                val col = (x / (w / 3f)).toInt().coerceIn(0, 2)
                val row = (y / (h / 3f)).toInt().coerceIn(0, 2)
                row * 3 + col
            }
            com.iptv.scanner.editor.pro.ui.MultiViewLayout.SINGLE -> 0
        }
    }

     override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (isTvMode()) {
            val kc = event.keyCode
            val isOk = kc == KeyEvent.KEYCODE_DPAD_CENTER || kc == KeyEvent.KEYCODE_ENTER
            val isDpad = kc == KeyEvent.KEYCODE_DPAD_UP || kc == KeyEvent.KEYCODE_DPAD_DOWN ||
                    kc == KeyEvent.KEYCODE_DPAD_LEFT || kc == KeyEvent.KEYCODE_DPAD_RIGHT
            if (event.action == KeyEvent.ACTION_DOWN) {
                // 底栏控制条显示时：DPAD/OK 交给 Compose 焦点系统在底栏内移动焦点/触发按钮，
                // 不再全局拦截为切台/seek（此前底栏内焦点移动只能暂用 TAB 键）。
                // 侧边栏打开时底栏被互斥隐藏（TvLayout: showOverlays && !sidebarVisible），不适用。
                if ((isOk || isDpad) && !viewModel.anyPanelOpen &&
                    !viewModel.landscapeSidebarVisible.value &&
                    (viewModel.controlsVisible.value || viewModel.controlsPinned.value)) {
                    return super.dispatchKeyEvent(event)
                }
                if (isOk) {
                    // 侧边栏（TvUnifiedPanel）打开时，DPAD_CENTER 必须传给 Compose 焦点系统，
                    // 让菜单项的 onClick / 频道列表的 onChannelClick 触发。
                    // 之前这里直接关闭侧边栏并消费事件，导致菜单项点击无效。
                    // 关闭侧边栏由 openOverlay（菜单项 onClick）或 BACK 键处理。
                    if (viewModel.landscapeSidebarVisible.value) {
                        return super.dispatchKeyEvent(event)
                    }
                    // 统一侧边栏仅全屏播放页可呼出；分屏模式 OK 键交给 Compose 焦点系统
                    if (!viewModel.anyPanelOpen && isFullscreenPlayback()) {
                        // 零频道：OK 直达订阅源管理面板（初始焦点在 URL 输入框），
                        // 免去先进统一面板再逐项导航；有频道时行为保持不变
                        if (viewModel.isZeroChannelState()) {
                            viewModel.openSourceManagerForAdd()
                            Log.i(TAG, "dispatchKeyEvent: zero-channel DPAD_CENTER open source manager")
                            return true
                        }
                        viewModel.setLandscapeSidebarVisible(true)
                        Log.i(TAG, "dispatchKeyEvent: DPAD_CENTER open sidebar")
                        return true
                    }
                }
                if (isDpad && !viewModel.anyPanelOpen) {
                    // 首页模式：直接放行走 View 树分发 → Compose 焦点系统（宫格/底栏/EPG 网格导航）。
                    // 注意不能走 onKeyDown —— 从 dispatchKeyEvent 中间调 super.onKeyDown 只是
                    // Activity 兜底逻辑，事件不会再进入焦点系统，遥控器在首页将无法移动焦点。
                    if (viewModel.showHome.value) {
                        return super.dispatchKeyEvent(event)
                    }
                    // 分屏播放页：同样放行 → Compose 焦点系统。
                    // 右侧面板（分类/频道/节目/信息）与左侧控制栏按钮（含全屏）都是焦点可导航元素；
                    // 若走 onKeyDown 会被全局拦截为切台(UP/DOWN)/快进快退(LEFT/RIGHT)，
                    // 导致面板内焦点无法移动、遥控器无法聚焦全屏按钮进全屏。
                    if (isLandscapeMode() && viewModel.landscapeSplitMode.value) {
                        return super.dispatchKeyEvent(event)
                    }
                    return onKeyDown(kc, event)
                }
            }
        }
        return super.dispatchKeyEvent(event)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        // 初始化未完成时，按键交给系统处理
        val initState = viewModel.initState.value
        if (initState !is InitState.Ready) {
            return super.onKeyDown(keyCode, event)
        }

        // 数字选台（与侧边栏 CHANNEL_NUMBER 对齐）：
        // 用户按数字键 0-9 时，累积输入并显示在 OSD 上。
        // 2秒内无新输入或按确认键(DPAD_CENTER/ENTER)时，切到对应频道。
        val digit = when (keyCode) {
            KeyEvent.KEYCODE_0 -> 0
            KeyEvent.KEYCODE_1 -> 1
            KeyEvent.KEYCODE_2 -> 2
            KeyEvent.KEYCODE_3 -> 3
            KeyEvent.KEYCODE_4 -> 4
            KeyEvent.KEYCODE_5 -> 5
            KeyEvent.KEYCODE_6 -> 6
            KeyEvent.KEYCODE_7 -> 7
            KeyEvent.KEYCODE_8 -> 8
            KeyEvent.KEYCODE_9 -> 9
            else -> -1
        }
        if (digit >= 0) {
            viewModel.inputChannelNumber(digit)
            return true
        }
        // 确认键：立即执行数字选台
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (viewModel.commitChannelNumber()) {
                return true
            }
        }

        // BACK 键：先关闭面板 → 再收起底栏控制条 → 再退出多画面 → 再退出回看/时移 → 播放器模式返回首页 → 最后显示退出确认对话框
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            // 主菜单内的「全屏底栏样式」选择弹窗打开时：BACK 仅关闭弹窗，保留主菜单
            // （按键分发下 Compose BackHandler 不生效，BACK 统一走此处）
            if (viewModel.stylePickerOpen.value) {
                viewModel.setStylePickerOpen(false)
                // 未确定即关闭：清预览，底栏恢复已确定样式并回到常规自动隐藏
                viewModel.setStylePreview(null)
                viewModel.showControlsAutoHide()
                return true
            }
            if (viewModel.closeAnyPanel()) {
                return true
            }
            // 仅底栏控制条打开时，BACK 收起底栏（遥控器/触屏一致：悬浮窗打开时 BACK=关闭）
            if (viewModel.controlsVisible.value) {
                viewModel.toggleControls()
                return true
            }
            // 多画面激活时，BACK 退出多画面（释放副画面 Player）
            if (viewModel.multiViewState.value.active) {
                viewModel.exitMultiView()
                return true
            }
            // 在回看/时移模式下，BACK 退出回看/时移，恢复直播
            if (viewModel.playbackState.value.mode.isCatchupOrTimeshift) {
                viewModel.exitCatchup()
                return true
            }
            // 播放器模式返回首页（横屏：全屏→回分屏，分屏→回首页；竖屏直接回首页）
            // TV 无独立首页：全屏即主页，BACK 打开自带的频道列表侧边栏
            if (!viewModel.showHome.value) {
                if (isTvMode()) {
                    viewModel.setLandscapeSidebarVisible(true)
                } else if (isLandscapeMode() && !viewModel.landscapeSplitMode.value) {
                    viewModel.setLandscapeSplitMode(true)
                } else {
                    viewModel.showHomeScreen()
                }
                return true
            }
            // 首页模式下，显示退出确认对话框（立即退出 / 进入 PiP）
            viewModel.showExitConfirm()
            return true
        }

        // MENU 键：侧边栏风格 — TV/PHONE 都打开右侧设置菜单
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            // 主菜单仅全屏布局可呼出：分屏模式（分屏首页/分屏播放页）下 MENU 键不响应
            if (isLandscapeMode() && !isFullscreenPlayback()) return true
            when {
                viewModel.menuPanelOpen.value -> {
                    viewModel.closeAllPanels()
                }
                viewModel.landscapeSidebarVisible.value -> {
                    // 频道列表打开时，MENU键关闭频道列表再开设置菜单
                    viewModel.setLandscapeSidebarVisible(false)
                    viewModel.toggleMenuPanel()
                }
                viewModel.anyPanelOpen -> {
                    viewModel.closeAllPanels()
                    viewModel.toggleMenuPanel()
                }
                else -> {
                    viewModel.toggleMenuPanel()
                }
            }
            return true
        }

        // 左方向键：侧边栏风格 — TV模式下打开左侧频道列表（仅全屏播放页可呼出）
        if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT && isTvMode() && isFullscreenPlayback()) {
            // 仅在全屏播放（无任何面板打开）时，左方向键打开频道列表
            if (!viewModel.landscapeSidebarVisible.value && !viewModel.menuPanelOpen.value && !viewModel.anyPanelOpen) {
                viewModel.setLandscapeSidebarVisible(true)
                return true
            }
        }

        // 媒体键处理（TV 和 PHONE 模式都工作，不受面板状态影响）
        // 与 PC 端 onRemoteKey 对齐
        when (keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY -> {
                viewModel.mpv.setPause(false)
                return true
            }
            KeyEvent.KEYCODE_MEDIA_PAUSE -> {
                viewModel.mpv.setPause(true)
                return true
            }
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                viewModel.mpv.togglePause()
                return true
            }
            KeyEvent.KEYCODE_MEDIA_NEXT -> {
                viewModel.nextChannel()
                return true
            }
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> {
                viewModel.prevChannel()
                return true
            }
            KeyEvent.KEYCODE_MEDIA_STOP -> {
                // 回看/时移模式下退出回看恢复直播，其他模式停止播放
                if (viewModel.playbackState.value.mode.isCatchupOrTimeshift) {
                    viewModel.exitCatchup()
                } else {
                    viewModel.stopPlay()
                }
                return true
            }
            KeyEvent.KEYCODE_MEDIA_STEP_FORWARD, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> {
                viewModel.mpv.seekRelative(30.0)
                return true
            }
            KeyEvent.KEYCODE_MEDIA_STEP_BACKWARD, KeyEvent.KEYCODE_MEDIA_REWIND -> {
                viewModel.mpv.seekRelative(-30.0)
                return true
            }
            KeyEvent.KEYCODE_VOLUME_MUTE -> {
                viewModel.mpv.toggleMute()
                return true
            }
        }

        // 仅在 TV 模式下处理 DPAD 方向键
        val isTv = isTvMode()
        if (!isTv) {
            // PHONE 模式下也处理一些快捷键（方便外接键盘测试）
            when (keyCode) {
                KeyEvent.KEYCODE_SPACE -> {
                    viewModel.mpv.togglePause()
                    return true
                }
                KeyEvent.KEYCODE_M -> {
                    viewModel.mpv.toggleMute()
                    return true
                }
                // 音量键交给系统处理（PHONE 模式不拦截，显示系统音量条）
            }
            return super.onKeyDown(keyCode, event)
        }

        // TV 模式 DPAD 处理
        // 面板打开时，方向键和确认键交给 Compose 焦点系统在面板内导航，
        // 不再全局拦截为切频道/切面板（与 PC 端面板内键盘导航一致）。
        // 字母键（SPACE/M）和音量键仍由这里处理播放控制。
        val isDpadNavigation = keyCode == KeyEvent.KEYCODE_DPAD_UP ||
                keyCode == KeyEvent.KEYCODE_DPAD_DOWN ||
                keyCode == KeyEvent.KEYCODE_DPAD_LEFT ||
                keyCode == KeyEvent.KEYCODE_DPAD_RIGHT ||
                keyCode == KeyEvent.KEYCODE_DPAD_CENTER ||
                keyCode == KeyEvent.KEYCODE_ENTER
        // 侧边栏打开时 OK 键由 dispatchKeyEvent 传给 Compose 焦点系统处理（菜单项点击），
        // 关闭侧边栏由 BACK 键或菜单项 onClick 处理，此处不重复处理避免逻辑冲突。
        if (viewModel.anyPanelOpen && isDpadNavigation) {
            // 交给 Compose 焦点系统处理（在面板内导航/确认）
            return super.onKeyDown(keyCode, event)
        }
        // 首页模式：方向键/OK 交给 Compose 焦点系统（宫格频道卡/底部 tab/EPG 时间线网格导航）。
        // 否则首页按方向键会被下方全局逻辑拦截为切频道，TV 遥控器在首页永远无法移动焦点。
        if (viewModel.showHome.value && isDpadNavigation) {
            return super.onKeyDown(keyCode, event)
        }

        // 多画面模式：方向键全部用于切换焦点视口（无面板打开时）。
        // 多画面激活时方向键不再切频道/seek，避免误切主画面频道；
        // 用户切主画面频道需通过统一面板的频道列表（点击频道调用 playChannel）。
        // moveMultiViewFocus 返回 false（如 DUAL 模式上下键）时也拦截，避免触发切频道。
        if (viewModel.multiViewState.value.active) {
            val direction = when (keyCode) {
                KeyEvent.KEYCODE_DPAD_LEFT -> 0
                KeyEvent.KEYCODE_DPAD_UP -> 1
                KeyEvent.KEYCODE_DPAD_RIGHT -> 2
                KeyEvent.KEYCODE_DPAD_DOWN -> 3
                else -> -1
            }
            if (direction >= 0) {
                viewModel.moveMultiViewFocus(direction)
                return true
            }
        }

        // 分屏播放页兜底：事件能落到这里说明 Compose 焦点系统没有消费该按键，两种情况：
        // a) 焦点树无活跃焦点节点（初焦请求被异步加载重组清掉、或电视端时序异常）
        //    → 焦点归零，重新请求到视频区；
        // b) 焦点仍在树内，但方向键几何搜索到边缘无候选（右面板最右按钮/列表末行/
        //    控制栏最左最右/顶栏）。情况 b 此前也被无差别归零到视频区，
        //    导致用户每次按到边缘焦点都跳回视频区——"切着切着焦点消失"的根源。
        //    现改为原地保持焦点，仅消费事件防止落到下方全局切台/seek 兜底。
        if (isLandscapeMode() && viewModel.landscapeSplitMode.value && !viewModel.showHome.value) {
            val isDirectional = keyCode == KeyEvent.KEYCODE_DPAD_UP ||
                    keyCode == KeyEvent.KEYCODE_DPAD_DOWN ||
                    keyCode == KeyEvent.KEYCODE_DPAD_LEFT ||
                    keyCode == KeyEvent.KEYCODE_DPAD_RIGHT
            val isOk = keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER
            if (isDirectional || isOk) {
                if (viewModel.splitTreeHasFocus) {
                    // 情况 b：焦点未丢，原地保持
                    return true
                }
                // 情况 a：真正无焦点，把焦点重新请求到视频区（OK 键同样触发恢复）
                viewModel._splitFocusResetTick.value++
                return true
            }
        }

        when (keyCode) {
            KeyEvent.KEYCODE_DPAD_UP -> {
                viewModel.prevChannel()
                return true
            }
            KeyEvent.KEYCODE_DPAD_DOWN -> {
                viewModel.nextChannel()
                return true
            }

            KeyEvent.KEYCODE_DPAD_LEFT -> {
                // 左键：快退
                // - 回看/本地视频：直接 seek
                // - 直播/时移：在缓冲区内快退，自动进入时移模式
                val mode = viewModel.playbackState.value.mode
                if (mode.isCatchup || viewModel.currentChannel.value == null) {
                    viewModel.mpv.seekRelative(-10.0)
                } else {
                    viewModel.seekLiveRelative(-10.0)
                }
                return true
            }
            KeyEvent.KEYCODE_DPAD_RIGHT -> {
                // 右键：快进
                // - 回看/本地视频：直接 seek
                // - 直播/时移：时移下快进，追赶到前沿自动切回直播；直播前沿提示
                val mode = viewModel.playbackState.value.mode
                if (mode.isCatchup || viewModel.currentChannel.value == null) {
                    viewModel.mpv.seekRelative(10.0)
                } else {
                    viewModel.seekLiveRelative(10.0)
                }
                return true
            }
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                // 多画面模式：OK 键打开统一面板，让用户在频道列表中选择频道添加到焦点视口。
                // （多画面模式下添加副画面的唯一入口；控制层可通过 MENU 键或其他方式显示）
                if (viewModel.multiViewState.value.active) {
                    viewModel.toggleTvUnifiedPanel()
                    return true
                }
                // OK 键：短按打开统一面板，长按显示控制层。
                // startTracking() 启动长按检测，onKeyLongPress 在长按超时（~500ms）后触发，
                // onKeyUp 在松开时触发：长按已处理则跳过，否则短按打开统一面板。
                //
                // 重要：长按期间系统会重复发送 ACTION_DOWN（key repeat，repeatCount > 0），
                // 不能在重复事件中重置 okKeyLongPressed，否则会覆盖 onKeyLongPress 设置的 true，
                // 导致松手时 onKeyUp 误判为短按，触发统一面板。
                if (event != null && event.repeatCount == 0) {
                    okKeyLongPressed = false
                    event.startTracking()
                }
                return true
            }
            KeyEvent.KEYCODE_SPACE -> {
                viewModel.mpv.togglePause()
                return true
            }
            KeyEvent.KEYCODE_M -> {
                viewModel.mpv.toggleMute()
                return true
            }
            KeyEvent.KEYCODE_VOLUME_UP -> {
                viewModel.mpv.adjustVolume(5)
                return true
            }
            KeyEvent.KEYCODE_VOLUME_DOWN -> {
                viewModel.mpv.adjustVolume(-5)
                return true
            }
        }

        return super.onKeyDown(keyCode, event)
    }

    /**
     * 长按 OK 键（DPAD_CENTER/ENTER）显示控制层。
     *
     * 与 onKeyDown + onKeyUp 配合实现：
     * - onKeyDown: startTracking() 启动长按检测
     * - onKeyLongPress: 长按超时触发，显示控制层并标记
     * - onKeyUp: 松开时，长按已处理则跳过，否则短按打开统一面板
     *
     * 设计原因：短按打开统一面板后焦点会落到频道列表，
     * 若用长按打开统一面板，松开时的 KEYUP 会被 Compose 焦点系统消费，
     * 直接选中频道导致面板关闭。改为短按打开面板（无后续按键事件，
     * 不会误选），长按显示控制层（控制层不抢焦点）。
     */
    override fun onKeyLongPress(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            okKeyLongPressed = true
            // TV 模式：长按显示控制层（auto-hide），仅全屏播放页（全屏底栏为全屏专属）
            if (isTvMode() && !viewModel.anyPanelOpen && isFullscreenPlayback()) {
                viewModel.showControlsAutoHide()
                Log.i(TAG, "Long press OK: show controls")
                return true
            }
        }
        return super.onKeyLongPress(keyCode, event)
    }

    /**
     * OK 键松开：长按已处理（显示控制层）则跳过，否则短按打开统一面板。
     */
    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (okKeyLongPressed) {
                okKeyLongPressed = false
                return true
            }
            if (isTvMode()) {
                return true
            }
            if (viewModel.anyPanelOpen) {
                return super.onKeyUp(keyCode, event)
            }
            // 侧边栏仅全屏布局可呼出：分屏模式（手机横屏分屏）短按 OK 不再呼出
            if (isLandscapeMode() && !isFullscreenPlayback()) {
                return super.onKeyUp(keyCode, event)
            }
            // 短按 OK 键：打开侧边栏（替代统一面板，适配无菜单键遥控器）
            viewModel.setLandscapeSidebarVisible(!viewModel.landscapeSidebarVisible.value)
            Log.i(TAG, "Short press OK: toggle sidebar")
            return true
        }
        return super.onKeyUp(keyCode, event)
    }

    /**
     * 用户按 HOME 键离开应用时自动进入 PiP（如果正在播放且支持 PiP）。
     *
     * PiP 增强（与 Android 最佳实践对齐）：
     * - setAspectRatio：按视频实际宽高比设置 PiP 窗口，消除黑边
     * - setSourceBoundsHint：从视频区域平滑动画过渡到 PiP 窗口
     * - Android 12+：setAutoEnterEnabled + setSeamlessResizeEnabled
     */
    /** 全屏切换：竖屏→强制横屏，横屏→跟随传感器（可回竖屏）。
     * 大屏设备（sw>=600dp）系统会忽略 requestedOrientation，此时由
     * forceLandscapeLayout 驱动应用内伪横屏布局，保证全屏按钮始终有效。 */
    fun toggleFullscreen() {
        try {
            val portrait = resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_PORTRAIT
            Log.i(TAG, "toggleFullscreen: portrait=$portrait -> forceLandscape=$portrait")
            viewModel.setForceLandscapeLayout(portrait)
            if (portrait) {
                requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            } else {
                requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            }
        } catch (e: Exception) {
            Log.w(TAG, "toggleFullscreen failed: ${e.message}")
        }
    }

    /**
     * 手动进入 PiP 模式（主菜单/控制层按钮触发）。
     * 与 onUserLeaveHint 自动进入不同，这是用户主动请求 PiP。
     */
    fun enterPipManual() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            && packageManager.hasSystemFeature("android.software.picture_in_picture")
        ) {
            try {
                enterPictureInPictureMode(buildPipParams())
                Log.i(TAG, "Manual PiP entered")
            } catch (e: Exception) {
                Log.w(TAG, "Manual PiP failed: ${e.message}")
                viewModel.showOsd("画中画", "不支持或失败")
            }
        } else {
            viewModel.showOsd("画中画", "设备不支持")
        }
    }

    /**
     * 处理外部文件打开 Intent（文件关联）。
     * 支持 VIEW intent 打开 M3U/M3U8 播放列表和视频文件。
     */
    private fun handleIntent(intent: android.content.Intent?) {
        if (intent == null || intent.action != android.content.Intent.ACTION_VIEW) return
        val uri = intent.data ?: return
        val mimeType = intent.type ?: ""
        Log.i(TAG, "handleIntent: uri=$uri, mime=$mimeType")
        // 判断是播放列表还是视频文件
        val isPlaylist = mimeType.contains("mpegurl") ||
                uri.toString().lowercase().endsWith(".m3u") ||
                uri.toString().lowercase().endsWith(".m3u8")
        if (isPlaylist) {
            viewModel.openPlaylistFromUri(uri.toString(), uri.lastPathSegment ?: "播放列表")
        } else {
            viewModel.playLocalVideo(uri.toString())
        }
        // 清除 action 避免旋转屏幕时重复触发
        intent.action = null
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun buildPipParams(): PictureInPictureParams {
        val builder = PictureInPictureParams.Builder()
        val mpv = MpvController.getInstance()
        mpv.getVideoAspectRatio()?.let { ratio -> builder.setAspectRatio(ratio) }
        mpv.getVideoBoundsOnScreen()?.let { rect -> builder.setSourceRectHint(rect) }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            builder.setAutoEnterEnabled(true)
            builder.setSeamlessResizeEnabled(true)
        }
        return builder.build()
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        val mpv = MpvController.getInstance()
        // 仅在播放中（fileLoaded 且 !paused）才自动进入 PiP
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            && packageManager.hasSystemFeature("android.software.picture_in_picture")
            && mpv.fileLoaded.value && !mpv.paused.value
        ) {
            try {
                enterPictureInPictureMode(buildPipParams())
                Log.i(TAG, "Auto-entered PiP on user leave")
            } catch (e: Exception) {
                Log.w(TAG, "Auto PiP failed: ${e.message}")
            }
        }
    }

    /**
     * PiP 模式变化回调：进入 PiP 时关闭所有面板并隐藏控制层（小窗口只显示视频），
     * 退出 PiP 时恢复控制层显示。
     */
    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode)
        if (isInPictureInPictureMode) {
            viewModel.closeAllPanels()
            viewModel.hideControls()
            // 进入 PiP 时保持播放器不动，不要重载
            Log.i(TAG, "Entered PiP: panels closed, controls hidden")
        } else {
            // 退出 PiP 时不要重载视频，只是恢复控制层
            viewModel.showControls()
            Log.i(TAG, "Exited PiP: controls shown")
        }
    }


    override fun onDestroy() {
        super.onDestroy()
        // 停止并释放当前活跃播放器（MPV）
        // 注意：MPVView.destroy()（销毁 mpv 原生实例）由 AndroidView 的 onRelease 处理
        // 这里 stop + detach 当前播放器，避免 native 资源（解码器/缓冲队列/observer）泄漏
        try {
            val player = viewModel.mpv
            player.stop()
            player.detach()
        } catch (e: Throwable) {
            Log.w(TAG, "Player cleanup failed: ${e.message}")
        }
        // 兜底：确保 MpvController 的 EventObserver 被移除（即使当前播放器不是 MPV）
        try {
            val mpv = MpvController.getInstance()
            mpv.detach()
        } catch (e: Throwable) {
            Log.w(TAG, "MpvController cleanup failed: ${e.message}")
        }
        // 标记正常退出（NativeCrashLogger 据此判断下次启动是否需要保存崩溃日志）
        try {
            NativeCrashLogger.markCleanExit(application)
        } catch (e: Throwable) {
            Log.w(TAG, "NativeCrashLogger markCleanExit failed: ${e.message}")
        }
        Log.i(TAG, "onDestroy")
    }
}
