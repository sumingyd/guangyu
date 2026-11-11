package com.iptv.scanner.editor.pro.mpv

import android.content.Context
import android.os.Looper
import android.util.Log
import android.view.ViewGroup
import android.widget.FrameLayout
import `is`.xyz.mpv.MPVLib
import com.iptv.scanner.editor.pro.NativeCrashLogger
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.mpv.controller.MpvAudioEqController
import com.iptv.scanner.editor.pro.mpv.controller.MpvControllerHost
import com.iptv.scanner.editor.pro.mpv.controller.MpvFilterController
import com.iptv.scanner.editor.pro.mpv.controller.MpvPlaybackController
import com.iptv.scanner.editor.pro.mpv.controller.MpvScreenshotController
import com.iptv.scanner.editor.pro.mpv.controller.MpvSubtitleController
import com.iptv.scanner.editor.pro.mpv.controller.MpvVideoEqController
import com.iptv.scanner.editor.pro.player.Player
import com.iptv.scanner.editor.pro.player.PlayerCapabilities
import com.iptv.scanner.editor.pro.player.PlayerType
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Compose 友好的 mpv 控制器门面：单例，持有 MPVView 引用，
 * 把 MPVLib 的属性/命令包装为 StateFlow + 命令方法。
 *
 * 门面委托 6 个子控制器：
 * - MpvPlaybackController：播放控制（playFile/stop/pause/seek/volume/speed/音轨/章节/AB循环/逐帧）
 * - MpvVideoEqController：视频均衡（亮度/对比度/饱和度/色相/Gamma/反交错/旋转/翻转/裁剪/3D）
 * - MpvAudioEqController：音频均衡（延迟/10段EQ/音调/声道信息/声道监控）
 * - MpvSubtitleController：字幕（可见性/延迟/缩放/位置/样式）
 * - MpvScreenshotController：截图
 * - MpvFilterController：滤镜（360°/运动补偿/超分辨率/着色器）
 *
 * 门面保留：生命周期管理、EventObserver、StateFlow 声明、通用属性/命令 API、媒体信息。
 */
class MpvController : MPVLib.EventObserver, Player, MpvControllerHost {

    override val playerType = PlayerType.MPV

    override val capabilities = PlayerCapabilities(
        supportsBrightness = true, supportsContrast = true, supportsSaturation = true,
        supportsHue = true, supportsGamma = true, supportsVideoRotate = true,
        supportsVideoFlip = true, supportsVideoCrop = true, supportsAudioDelay = true,
        supportsAudioEq = true, supportsSubDelay = true, supportsSubScale = true,
        supportsSubPos = true, supportsAbLoop = true, supportsLoopFile = true,
        supportsFrameStep = true, supportsChapters = true, supportsScreenshot = true,
        supportsOsd = true, supportsAddSubtitleFile = true,
        supportsSpeedControl = true, supportsTrackList = true,
        supportsHardwareDecodeSwitch = true
    )

    @Volatile
    private var mpvView: MPVViewLike? = null

    // -----------------------------------------------------------------
    // StateFlow（Compose 可观察状态）
    // -----------------------------------------------------------------
    private val _timePos = MutableStateFlow(0.0)
    override val timePos: StateFlow<Double> = _timePos.asStateFlow()

    private val _duration = MutableStateFlow(0.0)
    override val duration: StateFlow<Double> = _duration.asStateFlow()

    private val _paused = MutableStateFlow(true)
    override val paused: StateFlow<Boolean> = _paused.asStateFlow()

    private val _volume = MutableStateFlow(100)
    override val volume: StateFlow<Int> = _volume.asStateFlow()

    private val _muted = MutableStateFlow(false)
    override val muted: StateFlow<Boolean> = _muted.asStateFlow()

    private val _mediaTitle = MutableStateFlow("")
    override val mediaTitle: StateFlow<String> = _mediaTitle.asStateFlow()

    private val _trackListJson = MutableStateFlow("")
    override val trackListJson: StateFlow<String> = _trackListJson.asStateFlow()

    private val _eofReached = MutableStateFlow(false)
    override val eofReached: StateFlow<Boolean> = _eofReached.asStateFlow()

    private val _fileLoaded = MutableStateFlow(false)
    override val fileLoaded: StateFlow<Boolean> = _fileLoaded.asStateFlow()

    /** mpv 实际生效的 hwdec（hwdec-current），用于设置页展示，避免用户不知道自己在软解 */
    private val _actualHwdec = MutableStateFlow("")
    val actualHwdec: StateFlow<String> = _actualHwdec.asStateFlow()

    /** 硬解崩溃黑名单当前是否生效 */
    private val _hwdecBlacklisted = MutableStateFlow(false)
    val hwdecBlacklisted: StateFlow<Boolean> = _hwdecBlacklisted.asStateFlow()

    /** mpv 实际生效的 vo（可能与用户偏好不同：默认 mediacodec_embed 起播失败会自动回退 gpu） */
    private val _actualVo = MutableStateFlow("")
    val actualVo: StateFlow<String> = _actualVo.asStateFlow()

    /** 是否发生过 mediacodec_embed → gpu 的自动回退 */
    private val _voAutoFallback = MutableStateFlow(false)
    val voAutoFallback: StateFlow<Boolean> = _voAutoFallback.asStateFlow()

    /**
     * 自适应渲染路径原因：
     * - "subtitle"：当前内容带字幕轨，已切 GPU 路径（mpv 才能渲染字幕）
     * - "filter"：用户启用了去色带/反交错/超分等 GPU 侧滤镜，已切 GPU 路径
     * - "fallback"：默认直写路径起播失败，自动回退
     * - null：默认直写路径或用户手动选择
     */
    private val _renderPathReason = MutableStateFlow<String?>(null)
    val renderPathReason: StateFlow<String?> = _renderPathReason.asStateFlow()

    /** 本次是否因字幕/滤镜临时切到了 GPU 路径（换台时据此切回直写） */
    @Volatile
    private var adaptiveGpuPath = false

    /** 自动回退回调（UI 线程）：参数为回退后的 vo，用于同步界面与提示 */
    @Volatile
    var onVoAutoFallback: ((String) -> Unit)? = null

    /** 每个进程只做一次 mediacodec_embed 自动回退，避免黑屏判定抖动时反复切 vo */
    @Volatile
    private var voFallbackDone = false

    /** VO 健康检查（每个文件只做一次） */
    private var voHealthCheckRunnable: Runnable? = null

    /** VO 弱判定（无视频轨/无渲染帧）延时任务 */
    private var voWeakCheckRunnable: Runnable? = null

    /** 换台首帧耗时打点任务 */
    private var firstFramePerfRunnable: Runnable? = null

    /** 本会话内“会话级软解降级”的重试次数上限，防止在坏设备上反复崩溃 */
    private var hwdecRetryCount = 0

    private val _currentChapter = MutableStateFlow(-1)
    override val currentChapter: StateFlow<Int> = _currentChapter.asStateFlow()

    private val _chapterCount = MutableStateFlow(0)
    override val chapterCount: StateFlow<Int> = _chapterCount.asStateFlow()

    private val _videoWidth = MutableStateFlow(0)
    override val videoWidth: StateFlow<Int> = _videoWidth.asStateFlow()

    private val _videoHeight = MutableStateFlow(0)
    override val videoHeight: StateFlow<Int> = _videoHeight.asStateFlow()

    @Volatile
    var onFileError: (() -> Unit)? = null

    @Volatile
    private var suppressFileErrorFlag = false

    private val _speed = MutableStateFlow(1.0)
    override val speed: StateFlow<Double> = _speed.asStateFlow()

    @Volatile
    private var _hwdecCache: String = "auto-copy"

    @Volatile
    private var _voCache: String = "gpu"

    /**
     * 换台期间抑制 setVoAndHwdec 对**旧** URL 的二次 loadfile。
     * 由 playChannel 在应用频道 vo/hwdec 之前置位，playFile 之后释放。
     */
    @Volatile
    private var voReloadSuppressed = false

    // -----------------------------------------------------------------
    // 子控制器
    // -----------------------------------------------------------------
    private val playbackController = MpvPlaybackController(this)
    private val videoEqController = MpvVideoEqController(this)
    private val audioEqController = MpvAudioEqController(this)
    private val subtitleController = MpvSubtitleController(this)
    private val screenshotController = MpvScreenshotController(this)
    private val filterController = MpvFilterController(this)

    // -----------------------------------------------------------------
    // MpvControllerHost 实现
    // -----------------------------------------------------------------
    override fun postOnUiThread(block: () -> Unit) {
        val v = mpvView
        if (v != null) {
            v.asView().post { block() }
        } else {
            Log.w(TAG, "MPVView not attached, skip command")
        }
    }

    override fun getMpvView(): MPVViewLike? = mpvView

    override fun isFileLoaded(): Boolean = _fileLoaded.value

    override fun getCurrentVolume(): Int = _volume.value

    // -----------------------------------------------------------------
    // 生命周期
    // -----------------------------------------------------------------
    fun attach(view: MPVViewLike) {
        this.mpvView = view
        MPVLib.addObserver(this)
        try {
            MPVLib.observeProperty("chapter", MPVLib.MpvFormat.MPV_FORMAT_INT64)
            MPVLib.observeProperty("chapter-count", MPVLib.MpvFormat.MPV_FORMAT_INT64)
            MPVLib.observeProperty("width", MPVLib.MpvFormat.MPV_FORMAT_INT64)
            MPVLib.observeProperty("height", MPVLib.MpvFormat.MPV_FORMAT_INT64)
            MPVLib.observeProperty("speed", MPVLib.MpvFormat.MPV_FORMAT_DOUBLE)
            MPVLib.observeProperty("path", MPVLib.MpvFormat.MPV_FORMAT_STRING)
            MPVLib.observeProperty("sub-visibility", MPVLib.MpvFormat.MPV_FORMAT_FLAG)
            MPVLib.observeProperty("hwdec-current", MPVLib.MpvFormat.MPV_FORMAT_STRING)
        } catch (e: Throwable) {
            Log.w(TAG, "observeProperty failed: ${e.message}")
        }

        try {
            _hwdecBlacklisted.value = UserPrefs.getInstance().isHwdecBlacklisted()
            _voAutoFallback.value = UserPrefs.getInstance().isVoAutoFallback()
        } catch (e: Throwable) {
            Log.w(TAG, "attach: read hwdec blacklist failed: ${e.message}")
        }

        try {
            val currentPause = MPVLib.getPropertyBoolean("pause") ?: true
            _paused.value = currentPause
            Log.i(TAG, "attach: synced pause state from mpv: $currentPause")
        } catch (e: Throwable) {
            Log.w(TAG, "attach: sync pause state failed: ${e.message}")
        }

        videoEqController.setDeinterlace(UserPrefs.getInstance().getDeinterlace())

        view.onInstanceRecreated = {
            Log.i(TAG, "onInstanceRecreated: re-observing properties after mpv core re-creation")
            try {
                MPVLib.observeProperty("chapter", MPVLib.MpvFormat.MPV_FORMAT_INT64)
                MPVLib.observeProperty("chapter-count", MPVLib.MpvFormat.MPV_FORMAT_INT64)
                MPVLib.observeProperty("width", MPVLib.MpvFormat.MPV_FORMAT_INT64)
                MPVLib.observeProperty("height", MPVLib.MpvFormat.MPV_FORMAT_INT64)
                MPVLib.observeProperty("speed", MPVLib.MpvFormat.MPV_FORMAT_DOUBLE)
                MPVLib.observeProperty("path", MPVLib.MpvFormat.MPV_FORMAT_STRING)
                MPVLib.observeProperty("sub-visibility", MPVLib.MpvFormat.MPV_FORMAT_FLAG)
                MPVLib.observeProperty("hwdec-current", MPVLib.MpvFormat.MPV_FORMAT_STRING)
            } catch (e: Throwable) {
                Log.w(TAG, "onInstanceRecreated: observeProperty failed: ${e.message}")
            }
            videoEqController.setDeinterlace(UserPrefs.getInstance().getDeinterlace())
        }

        view.onSurfaceRebuilt = {
            cancelPendingFileError()
            clearSuppressFileError(delayMs = 1000)
        }

        view.onSurfaceAboutToDestroy = {
            suppressFileError()
            Log.i(TAG, "onSurfaceAboutToDestroy: suppressFileError enabled")
        }

        // 核心不可用：不再静默失败，转成播放错误交给界面（触发换源/提示/降级）
        view.onCoreUnavailable = {
            Log.e(TAG, "onCoreUnavailable: mpv core is dead, surfacing playback error")
            postOnUiThread { onFileError?.invoke() }
        }

        Log.i(TAG, "MpvController attached to MPVView")
    }

    override fun attachView(view: Any) {
        if (view is MPVViewLike) {
            attach(view)
        } else {
            Log.w(TAG, "attachView: view is not MPVViewLike (${view.javaClass.name}), ignored")
        }
    }

    override fun detach() {
        val v = mpvView
        if (v != null) {
            v.asView().post {
                try {
                    v.stop()
                } catch (e: Throwable) {
                    Log.w(TAG, "detach: stop failed: ${e.message}")
                }
                v.onInstanceRecreated = null
            }
        }
        try {
            MPVLib.removeObserver(this)
        } catch (e: Exception) {
            Log.w(TAG, "detach: removeObserver failed: ${e.message}")
        }
        this.mpvView = null
        _fileLoaded.value = false
        _eofReached.value = false
        _timePos.value = 0.0
        _duration.value = 0.0
        _paused.value = true
        Log.i(TAG, "MpvController detached")
    }

    // -----------------------------------------------------------------
    // vo / hwdec（门面保留，涉及 _voCache/_hwdecCache 和 reattachSurfaceWithVo）
    // -----------------------------------------------------------------

    /**
     * 换台前调用：抑制紧接着的那次 setVoAndHwdec 对当前（旧）URL 的二次 loadfile。
     *
     * playChannel 的流程是「应用频道 vo/hwdec → playFile 新 URL」，如果不抑制，
     * setVoAndHwdec 会先把旧 URL 重新 loadfile，与 FCC JOIN 新组播的时序冲突。
     * 必须在 playFile 之后调用 [releaseVoReloadSuppression]，避免标记滞留影响后续手动切换。
     */
    fun suppressVoReloadOnSwitch() {
        voReloadSuppressed = true
    }

    /**
     * 释放 [suppressVoReloadOnSwitch] 的标记。投递到 UI 线程队列尾部，
     * 保证排在 setVoAndHwdec 的 UI 任务之后执行（两者共用同一个 View 的 Handler 队列）。
     */
    fun releaseVoReloadSuppression() {
        if (mpvView == null) {
            voReloadSuppressed = false
            return
        }
        postOnUiThread { voReloadSuppressed = false }
    }

    /** 用户显式重新选择 vo：清掉本进程的「已自动回退」记忆，允许再次尝试默认渲染路径 */
    fun resetVoFallbackForUser() {
        voFallbackDone = false
        _voAutoFallback.value = false
    }

    fun setVoAndHwdec(vo: String, hwdec: String): String? {
        // arm32 电视/盒子：运行中切 vo（任一方向）都会在 video-reconfig 阶段结束进程
        // （exit(1)，无 Java 异常；实测 embed→gpu 也会崩）。这里只落盘选择，重启播放器
        // 后以 init option 形式生效。
        if (_actualVo.value != vo) {
            try {
                val p = UserPrefs.getInstance()
                if (p.isTvEmbedRequired()) {
                    p.setVo(vo)
                    p.setHwdec(hwdec)
                    p.setVoFallbackConfirmed(true)
                    Log.i(TAG, "setVoAndHwdec: arm32 TV 运行中不切 vo（$vo），已落盘，重启播放器后生效")
                    return null
                }
            } catch (_: Throwable) {
            }
        }
        val hasFile = _fileLoaded.value
        // 显式设置 vo（用户切换 / 重置）视为重新选择：允许再次尝试 mediacodec_embed
        voFallbackDone = false
        // 用户显式选择路径后，清掉自适应（字幕/滤镜）临时切换标记
        adaptiveGpuPath = false
        _renderPathReason.value = null
        // houdini 转译层（x86 模拟器）强制软解：硬解码器 teardown 会 SIGSEGV
        val effectiveHwdec = MPVView.sanitizeHwdec(hwdec, vo)
        postOnUiThread {
            try {
                MPVLib.setPropertyString("hwdec", effectiveHwdec)
                _hwdecCache = effectiveHwdec
                // 立刻把新 hwdec 记进会话标记：硬解在一些车机上切换后几百毫秒内就会
                // SIGSEGV，等到 file-loaded 再写就来不及，下次启动会误判成「软解崩的」，
                // 于是又用崩溃值启动一次、多崩一轮才进黑名单。
                mpvView?.asView()?.context?.let {
                    NativeCrashLogger.setActiveDecode(it, vo, effectiveHwdec)
                }
                // 运行中切换 vo 必须重建 MPVView：reattachSurfaceWithVo 在 arm32 电视上
                // 切到 mediacodec_embed 会在 video-reconfig 阶段让进程静默退出。
                val rebuilt = rebuildWithVo(vo, effectiveHwdec)
                if (!rebuilt) mpvView?.reattachSurfaceWithVo(vo)
                _voCache = vo
                _actualVo.value = vo
                _voAutoFallback.value = try { UserPrefs.getInstance().isVoAutoFallback() } catch (_: Throwable) { false }

                if (rebuilt) {
                    // 重建时 MPVView.destroy() 已保存 path，新实例在 surfaceCreated 后自动恢复播放
                    Log.i(TAG, "setVoAndHwdec: rebuilt player with vo=$vo, hwdec=$effectiveHwdec")
                    Log.i(TAG, "diagnostic: ${mpvView?.getDiagnosticInfo()}")
                    return@postOnUiThread
                }

                val path = MPVLib.getPropertyString("path")
                // 保守处理换台时序：抑制标记，或已有新的 loadfile 在途时，
                // 都不对旧 URL 二次 loadfile，交给随后的 playFile 一次性加载新 URL。
                val suppressed = voReloadSuppressed
                val superseded = playbackController.switchingChannel &&
                        playbackController.pendingLoadUrl.isNotEmpty() &&
                        playbackController.pendingLoadUrl != path
                if (suppressed || superseded) {
                    Log.i(TAG, "setVoAndHwdec: 换台在途，跳过对旧 URL 的重载 (path=$path, pending=${playbackController.pendingLoadUrl})")
                } else if (path != null && path.isNotEmpty()) {
                    MPVLib.command(arrayOf("loadfile", path))
                    MPVLib.setPropertyBoolean("pause", false)
                }
                Log.i(TAG, "setVoAndHwdec: vo=$vo, hwdec=$hwdec, hasFile=$hasFile")
                Log.i(TAG, "diagnostic: ${mpvView?.getDiagnosticInfo()}")
            } catch (e: Throwable) {
                Log.e(TAG, "setVoAndHwdec failed", e)
            }
        }
        return if (hasFile) "reloaded" else null
    }

    /**
     * 如果当前处于“会话级软解降级”，解除降级并重新尝试硬解。
     *
     * 旧实现里 sessionHwdecOverride 一旦置位在进程内永不恢复，
     * 用户手动改回硬解 / 换台都救不回来（表现为“MPV 一直卡，ExoPlayer 不卡”）。
     * 这里加一个进程内重试预算，避免在真正会崩的设备上反复触发。
     */
    fun retryHardwareDecodeIfDegraded(trigger: String) {
        if (!MPVView.hasSessionHwdecOverride()) return
        if (hwdecRetryCount >= MAX_HWDEC_RETRIES_PER_SESSION) {
            Log.w(TAG, "retryHardwareDecode skipped ($trigger): retry budget exhausted ($hwdecRetryCount)")
            return
        }
        hwdecRetryCount++
        MPVView.clearSessionHwdecOverride(trigger)
        val desired = try { UserPrefs.getInstance().getHwdec() } catch (_: Throwable) { MPVView.DEFAULT_HWDEC }
        val effective = MPVView.sanitizeHwdec(desired, _voCache)
        _hwdecCache = effective
        Log.w(TAG, "retryHardwareDecode: trigger=$trigger, retry=$hwdecRetryCount, desired=$desired, effective=$effective")
        if (effective == "no") return
        postOnUiThread {
            try {
                MPVLib.setPropertyString("hwdec", effective)
            } catch (e: Throwable) {
                Log.w(TAG, "retryHardwareDecode: set hwdec failed: ${e.message}")
            }
        }
    }

    /** 用户手动切换 hwdec：重置重试预算，给一次干净的重试机会 */
    fun resetHwdecRetryBudget() {
        hwdecRetryCount = 0
    }

    override fun setHardwareDecode(enabled: Boolean): Boolean {
        val prefs = try { UserPrefs.getInstance() } catch (_: Throwable) { return false }
        // 电视/盒子：硬解固定 mediacodec_embed + mediacodec（不碰 AImageReader/copy-back）；
        // 手机：gpu-next + mediacodec 直通。软解时 mediacodec_embed 无解码器直渲，退回 gpu。
        val vo = prefs.voForHardwareDecode(enabled, _voCache)
        val hwdec = prefs.hwdecForHardwareDecode(enabled, _hwdecCache)
        setVoAndHwdec(vo, hwdec)
        Log.i(TAG, "setHardwareDecode: enabled=$enabled, vo=$vo, hwdec=$hwdec")
        return true
    }

    override fun isHardwareDecodeEnabled(): Boolean {
        return try {
            val hwdec = _hwdecCache
            hwdec != "no"
        } catch (e: Throwable) { true }
    }

    // -----------------------------------------------------------------
    // 日志等级 / 视频信息（门面保留，依赖 StateFlow）
    // -----------------------------------------------------------------
    fun setMpvLogLevel(level: String) {
        val mpvMsgLevel = MpvLogLevelMapper.toMpvValue(level)
        postOnUiThread {
            try {
                MPVLib.setPropertyString("msg-level", mpvMsgLevel)
                Log.i(TAG, "setMpvLogLevel: level=$level → msg-level=$mpvMsgLevel")
            } catch (e: Throwable) {
                Log.e(TAG, "setMpvLogLevel failed", e)
            }
        }
    }

    fun getVideoAspectRatio(): android.util.Rational? {
        val w = _videoWidth.value
        val h = _videoHeight.value
        if (w <= 0 || h <= 0) return null
        val g = gcd(w, h)
        return try {
            android.util.Rational(w / g, h / g)
        } catch (e: Throwable) {
            null
        }
    }

    fun getVideoBoundsOnScreen(): android.graphics.Rect? {
        val view = mpvView ?: return null
        val rect = android.graphics.Rect()
        val visible = view.asView().getGlobalVisibleRect(rect)
        return if (visible) rect else null
    }

    private fun gcd(a: Int, b: Int): Int = if (b == 0) a else gcd(b, a % b)

    // -----------------------------------------------------------------
    // Surface / 文件错误抑制（门面保留，涉及 suppressFileErrorFlag 和 mpvView）
    // -----------------------------------------------------------------
    override fun refreshSurface() {
        postOnUiThread {
            try {
                val vo = _voCache
                cancelPendingFileError()
                mpvView?.reattachSurfaceWithVo(vo)
                Log.i(TAG, "refreshSurface: reattached surface with vo=$vo")
            } catch (e: Exception) {
                Log.w(TAG, "refreshSurface failed: ${e.message}")
            }
        }
    }

    fun cancelPendingFileError() {
        playbackController.pendingEndFileError?.let { mpvView?.asView()?.removeCallbacks(it) }
        playbackController.pendingEndFileError = null
    }

    fun suppressFileError() {
        suppressFileErrorFlag = true
        cancelPendingFileError()
        Log.i(TAG, "suppressFileError: enabled")
    }

    fun clearSuppressFileError(delayMs: Long = 800) {
        mpvView?.asView()?.postDelayed({
            suppressFileErrorFlag = false
            Log.i(TAG, "clearSuppressFileError: disabled after ${delayMs}ms")
        }, delayMs)
    }

    /**
     * 首帧出画耗时打点：FILE_LOADED 之后轮询 estimated-frame-number，
     * 第一次 > 0 即认为新频道首帧已经显示，输出 T5 相对 T0 的耗时。
     * 只做日志，不影响播放行为。
     */
    private fun scheduleFirstFramePerf() {
        firstFramePerfRunnable?.let { mpvView?.asView()?.removeCallbacks(it) }
        val view = mpvView?.asView() ?: return
        val deadline = android.os.SystemClock.elapsedRealtime() + 3_000L
        val runnable = object : Runnable {
            override fun run() {
                val frames = try {
                    MPVLib.getPropertyInt("estimated-frame-number") ?: 0
                } catch (_: Throwable) {
                    0
                }
                if (frames > 0) {
                    firstFramePerfRunnable = null
                    SwitchPerf.markFirstFrame()
                    // 直写 Surface 已出帧：清掉 pending 标记，下次启动不再判该组合不可用
                    try { UserPrefs.getInstance().endEmbedSession() } catch (_: Throwable) {}
                    return
                }
                if (android.os.SystemClock.elapsedRealtime() >= deadline) {
                    firstFramePerfRunnable = null
                    Log.w(TAG, "first-frame perf: timeout after 3s")
                    return
                }
                view.postDelayed(this, 16L)
            }
        }
        firstFramePerfRunnable = runnable
        view.postDelayed(runnable, 16L)
    }

    /**
     * VO 健康检查（每个文件最多一次）：
     * FILE_LOADED 后 1.5s，如果有视频轨但 `vo-configured` 仍不是 yes，
     * 说明 VO 没真正接管 Surface（表现为“只有声音没画面”），
     * 自动重建一次 VO 并重新 loadfile —— 等价于用户手动“切一次 VO”。
     */
    private fun scheduleVoHealthCheck() {
        cancelVoHealthCheck()
        val runnable = Runnable {
            voHealthCheckRunnable = null
            try {
                val videoFormat = MPVLib.getPropertyString("video-format") ?: ""
                val configured = try {
                    MPVLib.getPropertyBoolean("vo-configured")
                } catch (_: Throwable) {
                    null
                }
                val currentVo = try { MPVLib.getPropertyString("vo") } catch (_: Throwable) { null }
                if (!currentVo.isNullOrEmpty()) _actualVo.value = currentVo
                if (configured == true) {
                    Log.i(TAG, "vo health check: ok (vo=$currentVo, video-format=$videoFormat)")
                    return@Runnable
                }
                // VO 没接管时，先排除“探测预算太小导致编码没识别出来”：
                // 用 5MB/5s 重载一次，比直接切 vo 更轻，也不会误伤正常流。
                val activeUrl = playbackController.lastLoadedUrl.ifEmpty { playbackController.loadingUrl }
                if (playbackController.retryWithFullProbeBudget(activeUrl)) {
                    Log.w(TAG, "vo health check: no vo-configured, retry '$activeUrl' with full probe budget")
                    return@Runnable
                }
                // 设备默认渲染路径（TV 直写 Surface / 手机 gpu-next 直通）起播失败：自动回退一次
                if (configured == false && maybeFallbackFromDefaultPath("vo-configured=false, video-format=$videoFormat")) {
                    return@Runnable
                }
                if (videoFormat.isEmpty()) {
                    // 无 video track 无法判断是「纯音频流」还是「VO 没起来」，
                    // 延时再取一次帧计数（弱判定），只有确实一帧都没出且 vo 未配置才回退。
                    Log.i(TAG, "vo health check: no video track yet, scheduling weak check")
                    scheduleVoWeakFailureCheck()
                    return@Runnable
                }
                Log.w(TAG, "vo health check: video-format=$videoFormat but vo-configured=$configured, rebuilding VO once")
                suppressFileError()
                mpvView?.reattachSurfaceWithVo(_voCache)
                val path = try { MPVLib.getPropertyString("path") } catch (_: Throwable) { null }
                if (!path.isNullOrEmpty()) {
                    mpvView?.playFile(path)
                }
                clearSuppressFileError(1200)
            } catch (e: Throwable) {
                Log.w(TAG, "vo health check failed: ${e.message}")
            }
        }
        voHealthCheckRunnable = runnable
        mpvView?.asView()?.postDelayed(runnable, VO_HEALTH_CHECK_DELAY_MS)
    }

    /**
     * VO 弱判定（起播 4s 后）：无 video track 或一帧都没渲染，且 vo-configured 不为真时，
     * 对默认 mediacodec_embed 路径执行一次自动回退。手选 vo / 已回退过的不受影响。
     */
    private fun scheduleVoWeakFailureCheck() {
        voWeakCheckRunnable?.let { mpvView?.asView()?.removeCallbacks(it) }
        val runnable = Runnable {
            voWeakCheckRunnable = null
            try {
                val configured = try { MPVLib.getPropertyBoolean("vo-configured") } catch (_: Throwable) { null }
                if (configured == true) return@Runnable
                val videoFormat = MPVLib.getPropertyString("video-format") ?: ""
                val frames = try { MPVLib.getPropertyInt("estimated-frame-number") ?: 0 } catch (_: Throwable) { 0 }
                if (videoFormat.isEmpty() || frames <= 0) {
                    // 也可能只是 1MB/0.5s 没探到编码：先按完整预算重载一次，再判定 VO 故障
                    val activeUrl = playbackController.lastLoadedUrl.ifEmpty { playbackController.loadingUrl }
                    if (playbackController.retryWithFullProbeBudget(activeUrl)) {
                        Log.w(TAG, "vo weak check: no frames, retry '$activeUrl' with full probe budget")
                        return@Runnable
                    }
                    Log.w(TAG, "vo weak check failed: video-format='$videoFormat', frames=$frames, vo-configured=$configured")
                    maybeFallbackFromDefaultPath(
                        "no frames after ${(VO_HEALTH_CHECK_DELAY_MS + VO_WEAK_CHECK_DELAY_MS) / 1000}s " +
                            "(video-format='$videoFormat', frames=$frames, vo-configured=$configured)"
                    )
                }
            } catch (e: Throwable) {
                Log.w(TAG, "vo weak check failed: ${e.message}")
            }
        }
        voWeakCheckRunnable = runnable
        mpvView?.asView()?.postDelayed(runnable, VO_WEAK_CHECK_DELAY_MS)
    }

    /**
     * ABI 默认渲染路径起播失败时自动回退，并写盘记住。
     *
     * 覆盖两类默认路径：
     * - 电视/盒子默认 mediacodec_embed + mediacodec（直写 Surface）
     * - 手机默认 gpu-next + mediacodec（MediaCodec 直通）
     * 回退目标：手机/平板回 gpu + auto-copy；arm32 TV 回 gpu + 软解
     * （该机型不允许 AImageReader/copy-back）。
     *
     * 只对「用户没有显式选过 vo」的 ABI 默认值生效：手选的 vo 永不被自动回退覆盖。
     * 每个进程只回退一次，避免在坏流上反复切 vo 抖动。
     *
     * @return true 表示本次已执行回退
     */
    private fun maybeFallbackFromDefaultPath(reason: String): Boolean {
        if (voFallbackDone) return false
        val prefs = try { UserPrefs.getInstance() } catch (_: Throwable) { return false }
        if (prefs.hasExplicitVo()) {
            Log.i(TAG, "vo auto-fallback skipped: user explicitly selected vo=${prefs.getVo()}")
            return false
        }
        // 只在当前实际跑的正是设备默认路径时回退（已回退过/手选过都不再动）
        if (_voCache == "gpu" || _voCache != prefs.getVo()) return false
        voFallbackDone = true
        prefs.setVoAutoFallback(true)
        _voAutoFallback.value = true
        _renderPathReason.value = "fallback"
        // 直写/直通专用的 hwdec=mediacodec 在 gpu 上不再适用，按设备安全值回退
        val fallbackHwdec = if (prefs.isTvEmbedRequired()) "no" else "auto-copy"
        try { prefs.setHwdec(fallbackHwdec) } catch (_: Throwable) {}
        _voCache = "gpu"
        _hwdecCache = fallbackHwdec
        _actualVo.value = "gpu"
        Log.w(TAG, "vo auto-fallback: ${reason}, vo=gpu, hwdec=$fallbackHwdec")
        suppressFileError()
        postOnUiThread {
            try {
                MPVLib.setPropertyString("hwdec", fallbackHwdec)
                // arm32 电视运行中切 vo 必崩：只落盘，下次启动以 gpu + 软解 起播
                if (isTvEmbedDevice()) {
                    try {
                        val p = UserPrefs.getInstance()
                        p.setVo("gpu"); p.setHwdec(fallbackHwdec); p.setVoAutoFallback(true)
                    } catch (_: Throwable) {
                    }
                    Log.i(TAG, "vo auto-fallback: arm32 TV 只落盘，重启播放器后生效")
                    onVoAutoFallback?.invoke("gpu")
                    return@postOnUiThread
                }
                val rebuilt = rebuildWithVo("gpu", fallbackHwdec)
                if (!rebuilt) {
                    mpvView?.reattachSurfaceWithVo("gpu")
                    val path = try { MPVLib.getPropertyString("path") } catch (_: Throwable) { null }
                    if (!path.isNullOrEmpty()) mpvView?.playFile(path)
                }
                Log.i(TAG, "vo auto-fallback applied: vo=gpu, hwdec=$fallbackHwdec, rebuilt=$rebuilt")
            } catch (e: Throwable) {
                Log.e(TAG, "vo auto-fallback apply failed", e)
            }
            onVoAutoFallback?.invoke("gpu")
        }
        clearSuppressFileError(1500)
        return true
    }

    private fun cancelVoHealthCheck() {
        voHealthCheckRunnable?.let { mpvView?.asView()?.removeCallbacks(it) }
        voHealthCheckRunnable = null
        voWeakCheckRunnable?.let { mpvView?.asView()?.removeCallbacks(it) }
        voWeakCheckRunnable = null
    }

    // -----------------------------------------------------------------
    // 自适应渲染路径：直写 Surface 无法渲染字幕/滤镜，需要时自动切 GPU
    // -----------------------------------------------------------------

    /**
     * 当前内容/设置需要 mpv 画面层（GPU）时，自动从 mediacodec_embed 切到 GPU 路径。
     * 由字幕/滤镜入口调用（用户显式操作，允许立即切换）。
     */
    fun ensureGpuPathForFeatures(reason: String) {
        val prefs = try { UserPrefs.getInstance() } catch (_: Throwable) { return }
        if (_voCache != "mediacodec_embed") {
            _renderPathReason.value = reason
            return
        }
        adaptiveGpuPath = true
        _renderPathReason.value = reason
        val hwdec = gpuPathHwdec(prefs)
        Log.i(TAG, "adaptive render path -> gpu, reason=$reason, hwdec=$hwdec")
        postOnUiThread { applyVoSwitch("gpu", hwdec) }
    }

    /** GPU 路径下安全可用的 hwdec（arm32 TV 不允许 copy-back，手机走 AImageReader 直通） */
    private fun gpuPathHwdec(prefs: UserPrefs): String = when {
        prefs.isTvEmbedRequired() -> "no"
        prefs.isHandheldDevice() -> "mediacodec"
        else -> "auto-copy"
    }

    /** arm32 电视/盒子：运行中切 vo 必崩，只能靠重启生效 */
    private fun isTvEmbedDevice(): Boolean =
        try { UserPrefs.getInstance().isTvEmbedRequired() } catch (_: Throwable) { false }

    /** 立即切换 vo/hwdec（调用方保证在 UI 线程） */
    private fun applyVoSwitch(vo: String, hwdec: String) {
        try {
            if (hwdec != _hwdecCache) {
                MPVLib.setPropertyString("hwdec", hwdec)
                _hwdecCache = hwdec
            }
            if (_voCache != vo || mpvView == null) {
                // arm32 电视运行中切 vo 必崩，这里直接放弃本次切换（自适应字幕/滤镜同理），
                // 由换台前的 adaptivePreSwitchPlan 或下次冷启动生效。
                if (vo != _voCache && isTvEmbedDevice()) {
                    Log.i(TAG, "applyVoSwitch: arm32 TV 运行中不切 vo（$vo），跳过")
                    return
                }
                mpvView?.asView()?.context?.let { NativeCrashLogger.setActiveDecode(it, vo, hwdec) }
                val rebuilt = rebuildWithVo(vo, hwdec)
                if (!rebuilt) mpvView?.reattachSurfaceWithVo(vo)
                _voCache = vo
                _actualVo.value = vo
                if (rebuilt) {
                    Log.i(TAG, "applyVoSwitch: rebuilt player with vo=$vo, hwdec=$hwdec")
                    return
                }
            }
            Log.i(TAG, "applyVoSwitch: vo=$vo, hwdec=$hwdec")
        } catch (e: Throwable) {
            Log.w(TAG, "applyVoSwitch failed: ${e.message}")
        }
    }

    /**
     * 运行中切换渲染路径：销毁当前 MPVView，按新 vo/hwdec 重建并恢复播放。
     *
     * 不能再用 reattachSurfaceWithVo：在 Sony/MTK 的 arm32 电视上，运行中把 vo 切到
     * mediacodec_embed，mpv 会在 video-reconfig 阶段静默退出（进程 exit(1)，无 Java
     * 异常、无 tombstone）。重建走的是启动时同一套初始化流程（vo 在 surfaceCreated
     * 里首次建立），绕开运行中重建 VO 模块这条失败路径。
     *
     * @return true=已完成重建（调用方不要再自己 reattach / 重载 URL）
     */
    private fun rebuildWithVo(newVo: String, newHwdec: String): Boolean {
        val old = mpvView ?: return false
        val oldView = old.asView()
        val parent = oldView.parent as? ViewGroup ?: return false
        val ctx: Context = oldView.context
        val index = parent.indexOfChild(oldView)
        return try {
            Log.i(TAG, "rebuildWithVo: vo=$newVo, hwdec=$newHwdec")
            // 先移除旧 View（触发 surfaceDestroyed → detach），再销毁实例
            parent.removeView(oldView)
            old.destroy()
            val newView = MPVView(ctx)
            newView.initialize(
                ctx.getDir("mpv_config", Context.MODE_PRIVATE).absolutePath,
                ctx.cacheDir.absolutePath,
                newVo,
                newHwdec
            )
            attach(newView)
            parent.addView(
                newView.asView(),
                index,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT
                )
            )
            _voCache = newVo
            _hwdecCache = MPVView.sanitizeHwdec(newHwdec, newVo)
            _actualVo.value = newVo
            Log.i(TAG, "rebuildWithVo: done, vo=$newVo, hwdec=$newHwdec")
            true
        } catch (e: Throwable) {
            Log.e(TAG, "rebuildWithVo failed, fallback to reattach", e)
            false
        }
    }

    /** 起播前判定：有滤镜 → GPU；上一台因字幕/滤镜切过 GPU，本台无需求则切回直写 */
    private fun adaptivePreSwitchPlan(): Pair<String, String>? {
        val prefs = try { UserPrefs.getInstance() } catch (_: Throwable) { return null }
        if (prefs.hasExplicitVo()) return null
        val filterReason = gpuOnlyFilterReason()
        if (filterReason != null) {
            _renderPathReason.value = filterReason
            if (_voCache == "gpu" || _voCache == "gpu-next") return null
            adaptiveGpuPath = true
            return "gpu" to gpuPathHwdec(prefs)
        }
        if (adaptiveGpuPath) {
            adaptiveGpuPath = false
            _renderPathReason.value = null
            if (prefs.getVo() == "mediacodec_embed" && _voCache != "mediacodec_embed") {
                return "mediacodec_embed" to "mediacodec"
            }
        }
        return null
    }

    /** 当前是否启用了只能在 GPU 画面层生效的滤镜（去色带/反交错/超分等） */
    private fun gpuOnlyFilterReason(): String? = try {
        when {
            UserPrefs.getInstance().getDeinterlace() != "no" -> "filter"
            MPVLib.getPropertyString("deband") == "yes" -> "filter"
            !MPVLib.getPropertyString("glsl-shaders").isNullOrBlank() -> "filter"
            !MPVLib.getPropertyString("vf").isNullOrBlank() -> "filter"
            else -> null
        }
    } catch (_: Throwable) {
        null
    }

    /** 当前文件是否带可用字幕轨（直写 Surface 无法显示） */
    private fun hasSubtitleTrack(): Boolean = try {
        val count = MPVLib.getPropertyInt("track-list/count") ?: 0
        (0 until count).any { i ->
            MPVLib.getPropertyString("track-list/$i/type") == "sub" &&
                MPVLib.getPropertyString("track-list/$i/albumart") != "yes"
        }
    } catch (_: Throwable) {
        false
    }

    /**
     * 用户在设置页显式选择了硬解：解除崩溃黑名单并给一次干净的重试机会。
     * 若该机型真的会崩，NativeCrashLogger 会在下次启动重新写入黑名单。
     */
    fun confirmHardwareDecodeSelection(hwdec: String) {
        if (hwdec == "no") return
        hwdecRetryCount = 0
        MPVView.confirmHardwareDecodeByUser()
        MPVView.clearSessionHwdecOverride("user selected hwdec=$hwdec")
        try {
            if (UserPrefs.getInstance().isHwdecBlacklisted()) {
                UserPrefs.getInstance().setHwdecBlacklisted(false)
                Log.w(TAG, "user selected hwdec=$hwdec, crash blacklist cleared")
            }
            _hwdecBlacklisted.value = false
        } catch (e: Throwable) {
            Log.w(TAG, "confirmHardwareDecodeSelection failed: ${e.message}")
        }
    }

    fun forceRecreate() = postOnUiThread {
        mpvView?.forceRecreate()
    }

    // -----------------------------------------------------------------
    // 播放控制（委托 MpvPlaybackController）
    // -----------------------------------------------------------------
    /** 音频焦点助手：绑定到 attach 的 View 上下文后生效（见 ensureAudioFocus） */
    private var audioFocusHelper: com.iptv.scanner.editor.pro.player.AudioFocusHelper? = null

    /** 用户主动 stop 标记：抑制 stop 触发的 END_FILE 被误判为播放错误 */
    @Volatile
    private var userStopped = false

    /** 连续加载失败次数（用于硬解会话级降级） */
    @Volatile
    private var consecutiveLoadFailures = 0

    private fun ensureAudioFocus(): com.iptv.scanner.editor.pro.player.AudioFocusHelper? {
        if (audioFocusHelper == null) {
            val ctx = mpvView?.asView()?.context?.applicationContext ?: return null
            audioFocusHelper =
                com.iptv.scanner.editor.pro.player.AudioFocusHelper(ctx).also { h ->
                    h.onPause = { playbackController.setPause(true) }
                    h.onResume = { playbackController.setPause(false) }
                    h.isPaused = { paused.value }
                }
        }
        return audioFocusHelper
    }

    override fun playFile(url: String) {
        if (isCoreDead()) {
            Log.e(TAG, "playFile: mpv core is dead, refusing loadfile $url")
            postOnUiThread { onFileError?.invoke() }
            return
        }
        userStopped = false
        // 从发起加载起就标记「播放中」：硬解崩溃可能发生在 FILE_LOADED 之前的解码器初始化阶段，
        // 等到 FILE_LOADED 再写会漏判成后台回收，导致黑名单兜底失效。
        mpvView?.asView()?.context?.applicationContext?.let {
            NativeCrashLogger.setPlaybackActive(it, true)
        }
        ensureAudioFocus()?.onUserResume()
        // 起播前判定自适应渲染路径（有滤镜/上一台因字幕切过 GPU）：在 loadfile 之前切换，避免起播闪断
        val plan = adaptivePreSwitchPlan()
        if (plan != null && mpvView != null) {
            val (targetVo, targetHwdec) = plan
            if (Looper.myLooper() == Looper.getMainLooper()) {
                applyVoSwitch(targetVo, targetHwdec)
                playbackController.playFile(url)
            } else {
                postOnUiThread {
                    applyVoSwitch(targetVo, targetHwdec)
                    playbackController.playFile(url)
                }
            }
        } else {
            playbackController.playFile(url)
        }
    }

    /** mpv 核心是否已终止（进程内不可恢复） */
    override fun isCoreDead(): Boolean = mpvView?.isCoreDead == true

    /** 向界面暴露「播放器核心不可用」（转成播放错误，由上层提示/降级） */
    override fun notifyPlaybackUnavailable() {
        postOnUiThread { onFileError?.invoke() }
    }

    /**
     * 硬解失败后的会话级降级。
     *
     * 只靠 houdini/arm32 设备判定不足以覆盖历史出问题的车机（判定不成立时仍走
     * MediaCodec teardown 崩溃路径）。这里在连续加载/播放失败后把 hwdec 降级为软解，
     * 并同步到 MPVView 的会话覆盖值，后续换台不再使用硬解。
     */
    private fun degradeHwdecOnLoadFailure() {
        try {
            // 用 hwdec-current（实际生效值）判断：hwdec 是“期望值”，
            // 在已被降级/被黑名单接管时仍是 auto-copy，会导致降级逻辑重复执行。
            val current = try { MPVLib.getPropertyString("hwdec-current") } catch (_: Throwable) { null }
                ?: MPVLib.getPropertyString("hwdec") ?: ""
            if (current.isEmpty() || current == "no") return
            consecutiveLoadFailures++
            Log.w(TAG, "playback failure #$consecutiveLoadFailures (hwdec-current=$current)")
            if (consecutiveLoadFailures < 2) return
            consecutiveLoadFailures = 0
            MPVView.forceSoftwareDecodeForSession("repeated playback failures with hwdec-current=$current")
            postOnUiThread {
                try {
                    MPVLib.setPropertyString("hwdec", "no")
                    _hwdecCache = "no"
                } catch (e: Throwable) {
                    Log.w(TAG, "degrade hwdec runtime apply failed: ${e.message}")
                }
            }
        } catch (e: Throwable) {
            Log.w(TAG, "degradeHwdecOnLoadFailure failed: ${e.message}")
        }
    }

    fun markNeedPreStop() = playbackController.markNeedPreStop()
    fun getPath(): String = playbackController.getPath()
    override fun stop() {
        // 用户主动停止：随后的 END_FILE 不应被当作播放错误
        userStopped = true
        firstFramePerfRunnable?.let { mpvView?.asView()?.removeCallbacks(it) }
        firstFramePerfRunnable = null
        SwitchPerf.markAbort("user-stop")
        audioFocusHelper?.abandon()
        // 停止后标记空闲：按 Home/退出播放页再被系统回收，不再误判成硬解崩溃
        mpvView?.asView()?.context?.applicationContext?.let {
            NativeCrashLogger.setPlaybackActive(it, false)
        }
        playbackController.stop()
    }
    override fun togglePause() {
        // 记录用户意图：暂停后焦点恢复不得覆盖；恢复播放时重新申请音频焦点
        if (paused.value) ensureAudioFocus()?.onUserResume() else ensureAudioFocus()?.onUserPause()
        playbackController.togglePause()
    }

    override fun setPause(p: Boolean) {
        if (p) ensureAudioFocus()?.onUserPause() else ensureAudioFocus()?.onUserResume()
        playbackController.setPause(p)
    }
    override fun seekTo(seconds: Double) = playbackController.seekTo(seconds)
    override fun seekRelative(seconds: Double) = playbackController.seekRelative(seconds)
    override fun seekAbsolute(seconds: Double) = playbackController.seekAbsolute(seconds)
    override fun setVolume(v: Int) = playbackController.setVolume(v)
    override fun adjustVolume(delta: Int) = playbackController.adjustVolume(delta)
    override fun toggleMute() = playbackController.toggleMute()
    override fun setMute(m: Boolean) = playbackController.setMute(m)
    override fun setSpeed(s: Double) = playbackController.setSpeed(s)
    override fun cycleAudio() = playbackController.cycleAudio()
    override fun cycleSub() = playbackController.cycleSub()
    override fun setAudioTrack(id: Int) = playbackController.setAudioTrack(id)
    override fun setSubTrack(id: Int) = playbackController.setSubTrack(id)
    override fun addSubtitleFile(path: String): Boolean {
        // 字幕只能由 mpv 画面层渲染：直写 Surface 时先切回 GPU 路径
        ensureGpuPathForFeatures("subtitle")
        return playbackController.addSubtitleFile(path)
    }
    override fun setChapter(idx: Int): Boolean = playbackController.setChapter(idx)
    override fun chapterNext(): Boolean = playbackController.chapterNext()
    override fun chapterPrev(): Boolean = playbackController.chapterPrev()
    override fun setAbLoopA(): Boolean = playbackController.setAbLoopA()
    override fun setAbLoopB(): Boolean = playbackController.setAbLoopB()
    override fun clearAbLoop() = playbackController.clearAbLoop()
    override fun setLoopFile(mode: String): Boolean = playbackController.setLoopFile(mode)
    override fun setLoopPlaylist(mode: String): Boolean = playbackController.setLoopPlaylist(mode)
    override fun frameStep(): Boolean = playbackController.frameStep()
    override fun frameBackStep(): Boolean = playbackController.frameBackStep()
    override fun showOsd(text: String, durationMs: Int) = playbackController.showOsd(text, durationMs)

    // -----------------------------------------------------------------
    // 视频均衡（委托 MpvVideoEqController）
    // -----------------------------------------------------------------
    fun setDeinterlace(value: String) {
        if (value != "no") ensureGpuPathForFeatures("filter")
        videoEqController.setDeinterlace(value)
    }
    override fun setBrightness(v: Int): Boolean = videoEqController.setBrightness(v)
    override fun setContrast(v: Int): Boolean = videoEqController.setContrast(v)
    override fun setSaturation(v: Int): Boolean = videoEqController.setSaturation(v)
    override fun setHue(v: Int): Boolean = videoEqController.setHue(v)
    override fun setGamma(v: Int): Boolean = videoEqController.setGamma(v)
    override fun setVideoRotate(degree: Int): Boolean = videoEqController.setVideoRotate(degree)
    override fun setVideoFlip(mode: String): Boolean = videoEqController.setVideoFlip(mode)
    override fun setVideoCrop(x: Int, y: Int, w: Int, h: Int): Boolean = videoEqController.setVideoCrop(x, y, w, h)
    override fun clearVideoCrop() = videoEqController.clearVideoCrop()
    override fun setVideoStereoMode(mode: String): Boolean = videoEqController.setVideoStereoMode(mode)
    override fun getVideoStereoMode(): String? = videoEqController.getVideoStereoMode()

    // -----------------------------------------------------------------
    // 音频均衡（委托 MpvAudioEqController）
    // -----------------------------------------------------------------
    override fun setAudioDelay(delaySec: Double): Boolean = audioEqController.setAudioDelay(delaySec)
    override fun adjustAudioDelay(delta: Double): Boolean = audioEqController.adjustAudioDelay(delta)
    override fun setAudioEq(gains: List<Float>): Boolean = audioEqController.setAudioEq(gains)
    override fun resetAudioEq(): Boolean = audioEqController.resetAudioEq()
    override fun setAudioPitch(pitch: Double): Boolean = audioEqController.setAudioPitch(pitch)
    override fun getAudioChannelInfo(): Map<String, Any> = audioEqController.getAudioChannelInfo()
    override fun startChannelMonitor(): Boolean = audioEqController.startChannelMonitor()
    override fun stopChannelMonitor() = audioEqController.stopChannelMonitor()
    override fun getChannelLevels(): Map<Int, Float> = audioEqController.getChannelLevels()

    // -----------------------------------------------------------------
    // 字幕（委托 MpvSubtitleController）
    // -----------------------------------------------------------------
    override fun setSubVisibility(v: Boolean) = subtitleController.setSubVisibility(v)
    override fun toggleSubVisibility() = subtitleController.toggleSubVisibility()
    override fun setSubDelay(delaySec: Double) = subtitleController.setSubDelay(delaySec)
    override fun adjustSubDelay(delta: Double) = subtitleController.adjustSubDelay(delta)
    override fun setSubScale(scale: Double) = subtitleController.setSubScale(scale)
    override fun setSubPos(pos: Int) = subtitleController.setSubPos(pos)
    fun applySubStyle(style: Map<String, String>) = subtitleController.applySubStyle(style)

    // -----------------------------------------------------------------
    // 截图（委托 MpvScreenshotController）
    // -----------------------------------------------------------------
    override fun screenshotToFile(path: String, mode: String): Boolean = screenshotController.screenshotToFile(path, mode)

    // -----------------------------------------------------------------
    // 滤镜（委托 MpvFilterController）
    // -----------------------------------------------------------------
    override fun clearAllVideoFilters() = filterController.clearAllVideoFilters()
    override fun set360View(yaw: Double, pitch: Double, roll: Double, projection: String): Boolean {
        ensureGpuPathForFeatures("filter")
        return filterController.set360View(yaw, pitch, roll, projection)
    }
    override fun clear360Filter() = filterController.clear360Filter()
    override fun setMotionCompensation(strength: String, targetFps: Int): Boolean {
        ensureGpuPathForFeatures("filter")
        return filterController.setMotionCompensation(strength, targetFps)
    }
    override fun clearMotionCompensation() = filterController.clearMotionCompensation()
    override fun setSuperResolution(scaleAlgo: String, detailEnhance: Int): Boolean {
        ensureGpuPathForFeatures("filter")
        return filterController.setSuperResolution(scaleAlgo, detailEnhance)
    }
    override fun clearSuperResolution() = filterController.clearSuperResolution()
    override fun setUserShader(preset: String): Boolean {
        ensureGpuPathForFeatures("filter")
        return filterController.setUserShader(preset)
    }
    override fun clearUserShader() = filterController.clearUserShader()

    // -----------------------------------------------------------------
    // 通用 API
    // -----------------------------------------------------------------
    override fun setPropertyString(name: String, value: String) =
        postOnUiThread { MPVLib.setPropertyString(name, value) }

    override fun setPropertyInt(name: String, value: Int) =
        postOnUiThread { MPVLib.setPropertyInt(name, value) }

    override fun setPropertyDouble(name: String, value: Double) =
        postOnUiThread { MPVLib.setPropertyDouble(name, value) }

    override fun setPropertyBoolean(name: String, value: Boolean) =
        postOnUiThread { MPVLib.setPropertyBoolean(name, value) }

    override fun getPropertyString(name: String): String? =
        if (mpvView != null) { try { MPVLib.getPropertyString(name) } catch (e: Throwable) { null } } else null

    override fun getPropertyInt(name: String): Int? =
        if (mpvView != null) { try { MPVLib.getPropertyInt(name) } catch (e: Throwable) { null } } else null

    override fun getPropertyDouble(name: String): Double? =
        if (mpvView != null) { try { MPVLib.getPropertyDouble(name) } catch (e: Throwable) { null } } else null

    override fun getPropertyBoolean(name: String): Boolean? =
        if (mpvView != null) { try { MPVLib.getPropertyBoolean(name) } catch (e: Throwable) { null } } else null

    override fun command(args: Array<String>) = postOnUiThread { MPVLib.command(args) }

    // -----------------------------------------------------------------
    // 媒体信息
    // -----------------------------------------------------------------
    override fun getMediaInfo(): Map<String, String?> {
        if (mpvView == null) return emptyMap()
        val startedNs = System.nanoTime()
        val timings = ArrayList<Pair<String, Long>>(32)
        fun timedGet(key: String, prop: String): String? {
            val s = System.nanoTime()
            val v = safeGet(prop)
            timings.add(key to (System.nanoTime() - s) / 1000)
            return v
        }
        fun timedGetDouble(key: String, prop: String): String? {
            val s = System.nanoTime()
            val v = safeGetDouble(prop)
            timings.add(key to (System.nanoTime() - s) / 1000)
            return v
        }
        val result = try {
            mapOf(
                "videoCodec" to timedGet("videoCodec", "video-format"),
                "audioCodec" to timedGet("audioCodec", "audio-codec-name"),
                "videoRes" to "${_videoWidth.value}x${_videoHeight.value}",
                "fps" to timedGet("fps", "container-fps"),
                "displayFps" to timedGetDouble("displayFps", "display-fps"),
                "bitrate" to timedGet("bitrate", "video-bitrate"),
                "audioBitrate" to timedGet("audioBitrate", "audio-bitrate"),
                "cacheDuration" to timedGet("cacheDuration", "demuxer-cache-duration"),
                "avdiff" to timedGet("avdiff", "total-avsync-change"),
                "containerFormat" to timedGet("containerFormat", "file-format"),
                "hwdec" to timedGet("hwdec", "hwdec-current"),
                "vo" to timedGet("vo", "vo"),
                "videoPrimaries" to timedGet("videoPrimaries", "video-params/primaries"),
                "videoGamma" to timedGet("videoGamma", "video-params/gamma"),
                "videoColorRange" to timedGet("videoColorRange", "video-params/color-range"),
                // 颜色管线诊断：当前色调映射算法 / 输出范围 / 是否发生色调映射，
                // 用户反馈「过曝/发灰」时对号用（信息面板可只读该字段，无需改播放侧）
                "videoToneMapping" to timedGet("videoToneMapping", "tone-mapping"),
                "videoOutputLevels" to timedGet("videoOutputLevels", "video-output-levels"),
                "videoHdrComputePeak" to timedGet("videoHdrComputePeak", "hdr-compute-peak"),
                // 扩展信息：音频细节、像素格式、实际渲染性能、流元数据
                "audioSampleRate" to timedGet("audioSampleRate", "audio-params/samplerate"),
                "audioChannels" to timedGet("audioChannels", "audio-params/channel-layout"),
                "pixelFormat" to timedGet("pixelFormat", "video-params/pixelformat"),
                "colorspace" to timedGet("colorspace", "video-params/colorspace"),
                "renderFps" to timedGetDouble("renderFps", "estimated-vf-fps"),
                "droppedFrames" to timedGet("droppedFrames", "decoder-frame-drop-count"),
                "cacheSpeed" to timedGetDouble("cacheSpeed", "cache-speed"),
                "mediaTitle" to timedGet("mediaTitle", "media-title"),
                "serviceName" to timedGet("serviceName", "metadata/by-key/service_name"),
                "serviceProvider" to timedGet("serviceProvider", "metadata/by-key/service_provider"),
                "trackCount" to timedGet("trackCount", "track-list/count")
            )
        } catch (e: Throwable) {
            Log.w(TAG, "getMediaInfo failed: ${e.message}")
            emptyMap()
        }
        // 逐属性耗时仅在调试时输出：adb shell setprop log.tag.MpvController VERBOSE
        // 用于确认「切台徽章读取是否占用 UI 线程并推迟首帧」。
        if (Log.isLoggable(TAG, Log.VERBOSE)) {
            val totalUs = (System.nanoTime() - startedNs) / 1000
            val detail = timings.joinToString(", ") { "${it.first}=${it.second}us" }
            Log.v(TAG, "getMediaInfo ${result.size} props total=${totalUs}us thread=${Thread.currentThread().name} [$detail]")
        }
        return result
    }

    // 注意：不要在这里“记住失败过的属性”。切台刚 FILE_LOADED 时 video-format /
    // audio-codec-name / hwdec-current 可能还不可用，一次读取失败不代表该属性永远取不到；
    // 一旦缓存成黑名单，本次播放期间徽章与信息面板会一直显示为空。
    private fun safeGet(name: String): String? =
        try { MPVLib.getPropertyString(name) } catch (_: Throwable) { null }

    private fun safeGetDouble(name: String): String? =
        try {
            val v = MPVLib.getPropertyDouble(name)
            if (v != null && v > 0) String.format("%.1f", v) else null
        } catch (_: Throwable) { null }

    // -----------------------------------------------------------------
    // HDR 重建协调
    // -----------------------------------------------------------------
    override fun savePlaybackState(): Pair<String, Double>? {
        return try {
            val url = MPVLib.getPropertyString("path") ?: return null
            if (url.isEmpty()) return null
            val time = MPVLib.getPropertyDouble("time-pos") ?: 0.0
            url to time
        } catch (e: Throwable) {
            Log.w(TAG, "savePlaybackState failed (MPVLib not initialized?): ${e.message}")
            null
        }
    }

    override fun restorePlaybackState(url: String, timePosSec: Double) {
        postOnUiThread {
            val v = mpvView
            if (v != null) {
                if (timePosSec > 0) {
                    v.pendingResumePos = timePosSec
                }
                v.playFile(url)
            } else {
                MPVLib.command(arrayOf("loadfile", url))
                if (timePosSec > 0) {
                    MPVLib.command(arrayOf("seek", timePosSec.toString(), "absolute", "exact"))
                }
                MPVLib.setPropertyBoolean("pause", false)
            }
        }
    }

    // -----------------------------------------------------------------
    // EventObserver 实现
    // -----------------------------------------------------------------
    override fun eventProperty(property: String) {}

    override fun eventProperty(property: String, value: Long) {
        when (property) {
            "volume" -> _volume.value = value.toInt()
            "chapter" -> _currentChapter.value = value.toInt()
            "chapter-count" -> _chapterCount.value = value.toInt()
            "width" -> _videoWidth.value = value.toInt()
            "height" -> _videoHeight.value = value.toInt()
        }
    }

    override fun eventProperty(property: String, value: Boolean) {
        when (property) {
            "pause" -> _paused.value = value
            "mute" -> _muted.value = value
            "eof-reached" -> _eofReached.value = value
            "sub-visibility" -> { }
        }
    }

    override fun eventProperty(property: String, value: Double) {
        when (property) {
            "time-pos" -> _timePos.value = value
            "duration" -> _duration.value = value
            "speed" -> _speed.value = value
        }
    }

    override fun eventProperty(property: String, value: String) {
        when (property) {
            "media-title" -> _mediaTitle.value = value
            "track-list" -> _trackListJson.value = value
            "path" -> { _eofReached.value = false }
            "hwdec-current" -> _actualHwdec.value = value
        }
    }

    override fun event(eventId: Int) {
        when (eventId) {
            MPVLib.MpvEvent.MPV_EVENT_FILE_LOADED -> {
                _fileLoaded.value = true
                consecutiveLoadFailures = 0
                userStopped = false
                val loadedUrl = try { MPVLib.getPropertyString("path") ?: "" } catch (_: Throwable) { "" }
                playbackController.onFileLoaded(loadedUrl)
                SwitchPerf.markFileLoaded()
                scheduleFirstFramePerf()
                _eofReached.value = false

                try {
                    val w = MPVLib.getPropertyInt("width") ?: 0
                    val h = MPVLib.getPropertyInt("height") ?: 0
                    // 预算固定 16MiB/4MiB：直播场景足够，低内存设备不易 OOM；
                    // 不再按 4K 抬到 128MiB（大缓存对直播无收益，只会放大坏流破坏面）
                    MPVLib.setPropertyString("demuxer-max-bytes", MpvProtocolConstants.DEMUXER_MAX_BYTES_DEFAULT)
                    MPVLib.setPropertyString("demuxer-max-back-bytes", MpvProtocolConstants.DEMUXER_MAX_BACK_BYTES)
                    Log.i(TAG, "buffer: ${MpvProtocolConstants.DEMUXER_MAX_BYTES_DEFAULT}/${MpvProtocolConstants.DEMUXER_MAX_BACK_BYTES} (video=${w}x$h)")
                } catch (e: Throwable) {
                    Log.w(TAG, "buffer adjust failed: ${e.message}")
                }

                // 记录实际生效的 hwdec（设置页展示，避免用户不知道自己在软解）
                try {
                    _actualHwdec.value = MPVLib.getPropertyString("hwdec-current") ?: ""
                    Log.i(TAG, "hwdec-current=${_actualHwdec.value}")
                } catch (_: Throwable) {
                }

                // 实际生效的 vo（默认 mediacodec_embed 起播失败会自动回退 gpu，设置页以此为准）
                try {
                    val voNow = MPVLib.getPropertyString("vo") ?: ""
                    if (voNow.isNotEmpty()) _actualVo.value = voNow
                    Log.i(TAG, "vo-current=$voNow")
                } catch (_: Throwable) {
                }

                // 自适应：当前内容带字幕轨时，直写 Surface 无法显示字幕 → 起播阶段切回 GPU 路径
                try {
                    val prefs = UserPrefs.getInstance()
                    if (_voCache == "mediacodec_embed" && !prefs.hasExplicitVo() && hasSubtitleTrack()) {
                        adaptiveGpuPath = true
                        _renderPathReason.value = "subtitle"
                        val hwdec = gpuPathHwdec(prefs)
                        Log.i(TAG, "adaptive render path -> gpu (subtitle track), hwdec=$hwdec")
                        postOnUiThread { applyVoSwitch("gpu", hwdec) }
                    }
                } catch (e: Throwable) {
                    Log.w(TAG, "adaptive render path check failed: ${e.message}")
                }

                scheduleVoHealthCheck()

                mpvView?.let { v ->
                    val pos = v.pendingResumePos
                    if (pos > 0) {
                        v.pendingResumePos = -1.0
                        postOnUiThread {
                            try {
                                MPVLib.command(arrayOf("seek", pos.toString(), "absolute"))
                            } catch (e: Throwable) {
                                Log.w(TAG, "resume seek after surface rebuild failed: ${e.message}")
                            }
                        }
                    }
                }
            }
            MPVLib.MpvEvent.MPV_EVENT_START_FILE -> {
                _fileLoaded.value = false
                _eofReached.value = false
                userStopped = false
                // 新文件开始加载即视为播放中（解码器初始化阶段的硬解崩溃要能被黑名单捕获）
                mpvView?.asView()?.context?.applicationContext?.let {
                    NativeCrashLogger.setPlaybackActive(it, true)
                }
                playbackController.onStartFile()
                SwitchPerf.markStartFile()
                cancelPendingFileError()
                Log.i(TAG, "MPV_EVENT_START_FILE: loadingUrl=${playbackController.loadingUrl}")
            }
            MPVLib.MpvEvent.MPV_EVENT_END_FILE -> {
                val wasLoaded = _fileLoaded.value
                _fileLoaded.value = false
                _videoWidth.value = 0
                _videoHeight.value = 0
                // END_FILE 归属判定：不再依赖全局 path。
                // loadfile replace 时 path 很可能已经指向新 URL，用它判断归属会失真。
                // 现在用「上一次真正 FILE_LOADED 的 URL」+「换台代次」记账。
                val switching = playbackController.switchingChannel
                val hadPendingLoad = playbackController.pendingLoadUrl.isNotEmpty()
                val endedUrl = playbackController.lastLoadedUrl.ifEmpty { playbackController.loadingUrl }
                val wasPlaying = wasLoaded || playbackController.lastLoadedUrl.isNotEmpty()
                val gen = playbackController.switchGeneration

                cancelPendingFileError()
                cancelVoHealthCheck()

                if (suppressFileErrorFlag) {
                    Log.i(TAG, "MPV_EVENT_END_FILE: suppressed (surface rebuilding), wasLoaded=$wasLoaded")
                    playbackController.clearSwitchingState()
                } else if (userStopped) {
                    Log.i(TAG, "MPV_EVENT_END_FILE: suppressed (user stopped playback)")
                    userStopped = false
                    playbackController.clearSwitchingState()
                    playbackController.clearPendingLoadUrl()
                } else if (switching) {
                    // 换台在途：END_FILE 可能属于被替换的旧流，也可能属于目标流。
                    // 需求：换台进行中一律不弹「频道断流 尝试重连」；
                    // 目标流失败由 MpvController 的超时换源逻辑负责，不在这里误报。
                    Log.i(TAG, "MPV_EVENT_END_FILE: suppressed (channel switching in progress, " +
                        "gen=$gen, lastLoaded=${playbackController.lastLoadedUrl}, pending=${playbackController.pendingLoadUrl})")
                    playbackController.clearSwitchingState()
                } else if (!wasPlaying) {
                    Log.w(TAG, "MPV_EVENT_END_FILE: file '$endedUrl' failed to load, notifying error")
                    // 换台失败：必须清理切换标志，否则后续错误回调全部被当成「换台中」跳过
                    playbackController.clearSwitchingState()
                    playbackController.clearPendingLoadUrl()
                    // 探测预算回退：1MB/0.5s 探测失败时用 5MB/5s 重载一次，成功则不再报错
                    if (playbackController.retryWithFullProbeBudget(endedUrl)) {
                        Log.w(TAG, "probe budget fallback: reload '$endedUrl' with full 5M/5s")
                    } else {
                        degradeHwdecOnLoadFailure()
                        postOnUiThread { onFileError?.invoke() }
                    }
                } else if (wasPlaying && !_eofReached.value) {
                    Log.i(TAG, "MPV_EVENT_END_FILE: stream '$endedUrl' ended mid-stream (wasLoaded=$wasLoaded), delayed error check 300ms (gen=$gen)")
                    val runnable = Runnable {
                        // 300ms 检查绑定换台代次：期间已经开始新一次换台就作废，避免误报
                        if (playbackController.switchGeneration != gen) {
                            Log.i(TAG, "MPV_EVENT_END_FILE: 300ms check skipped, generation changed " +
                                "($gen -> ${playbackController.switchGeneration})")
                            return@Runnable
                        }
                        if (!_fileLoaded.value) {
                            Log.w(TAG, "MPV_EVENT_END_FILE: stream ended mid-stream, no FILE_LOADED followed, notifying error (gen=$gen)")
                            playbackController.clearSwitchingState()
                            playbackController.clearPendingLoadUrl()
                            degradeHwdecOnLoadFailure()
                            postOnUiThread { onFileError?.invoke() }
                        }
                    }
                    playbackController.pendingEndFileError = runnable
                    mpvView?.asView()?.postDelayed(runnable, 300)
                } else {
                    Log.i(TAG, "MPV_EVENT_END_FILE: stream '$endedUrl' ended normally (wasLoaded=$wasLoaded, eof=${_eofReached.value})")
                    playbackController.clearSwitchingState()
                    playbackController.clearPendingLoadUrl()
                }
                playbackController.onEndFile()
                // 文件已结束且没有在途换台：若随后按 Home 被系统回收，不应算作硬解崩溃。
                // 换台时保留「播放中」，由新文件的 START_FILE/FILE_LOADED 继续维持。
                if (!switching && !hadPendingLoad) {
                    mpvView?.asView()?.context?.applicationContext?.let {
                        NativeCrashLogger.setPlaybackActive(it, false)
                    }
                    SwitchPerf.markAbort("end-file")
                }
            }
            MPVLib.MpvEvent.MPV_EVENT_SHUTDOWN -> {
                Log.w(TAG, "MPV_EVENT_SHUTDOWN: mpv core has shut down, marking instance as dead")
                // 核心终止后所有播放请求都无法执行：若当时正在播放/加载，必须把错误暴露给界面，
                // 否则后续 playFile 会永久静默 return，用户只看到黑屏无任何提示
                val wasActive = _fileLoaded.value || playbackController.loadingUrl.isNotEmpty()
                _fileLoaded.value = false
                _eofReached.value = true
                cancelVoHealthCheck()
                playbackController.clearSwitchingState()
                playbackController.clearPendingLoadUrl()
                mpvView?.markInstanceDead()
                if (wasActive) {
                    playbackController.clearSwitchingState()
                    postOnUiThread { onFileError?.invoke() }
                }
            }
        }
    }

    companion object {
        private const val TAG = "MpvController"

        /** FILE_LOADED 后多久做一次 VO 健康检查 */
        private const val VO_HEALTH_CHECK_DELAY_MS = 1500L

        /** VO 弱判定（无视频轨/无帧）在健康检查之后再等多久 */
        private const val VO_WEAK_CHECK_DELAY_MS = 2500L

        /** 进程内允许的“会话级软解降级”恢复重试次数 */
        private const val MAX_HWDEC_RETRIES_PER_SESSION = 3

        @Volatile
        private var INSTANCE: MpvController? = null

        fun getInstance(): MpvController =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: MpvController().also { INSTANCE = it }
            }

        val CHANNEL_LAYOUT_MAP get() = MpvAudioEqController.CHANNEL_LAYOUT_MAP
        val CHANNEL_DISPLAY get() = MpvAudioEqController.CHANNEL_DISPLAY
    }
}
