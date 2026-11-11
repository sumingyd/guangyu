package com.iptv.scanner.editor.pro.player

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player as Media3Player
import androidx.media3.common.TrackSelectionParameters
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.VideoSize
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.mediacodec.MediaCodecSelector
import androidx.media3.exoplayer.mediacodec.MediaCodecUtil
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 基于 ExoPlayer 的播放器适配器，实现 [Player] 接口。
 *
 * 用于 [PlayerType.EXO] 模式，支持硬解和软解两种模式：
 * - 硬解：使用硬件 MediaCodec 编解码器（GPU 加速）
 * - 软解：使用软件 MediaCodec 编解码器（如 OMX.google.*，不依赖 GPU）
 *
 * 软解通过自定义 [MediaCodecSelector] 过滤掉硬件编解码器实现，
 * 不依赖 FFmpeg 扩展（Google 不发布预编译 AAR）。
 *
 * 与 [MpvController] 的区别：
 * - MPV 功能最完整（EQ/AB循环/逐帧/截图/HDR），但某些设备 GPU 兼容性差
 * - ExoPlayer 兼容性好（Google 官方维护），HLS/DASH/RTSP 协议支持完善
 * - 软解模式（软件编解码器）作为 fallback，不依赖 GPU
 *
 * MPV 专属的高级功能（EQ/截图/AB循环/逐帧/章节等）在此实现中返回 false 或 no-op，
 * UI 层通过 [capabilities] 自动隐藏不支持的功能面板。
 *
 * @param context 应用上下文
 */
class ExoPlayerWrapper(
    private val context: Context
) : Player {

    companion object {
        private const val TAG = "ExoPlayerWrapper"
        private const val USER_AGENT = "VLC/3.0.18Libmpv"

        /** exo_tuning 偏好：上次播放的视频高度（决定 1080/4K 缓冲档） */
        private const val KEY_LAST_VIDEO_HEIGHT = "last_video_height"

        /** 4K 视为 >=1440p（含 2160p / 1440p 源），1080/720 走 1080 档 */
        private const val FOUR_K_HEIGHT_THRESHOLD = 1440

        /** 4K 首帧看门狗超时 */
        private const val FIRST_FRAME_TIMEOUT_MS = 6_000L

        /**
         * 软解专用 MediaCodecSelector：优先软件编解码器，若无软解则回退硬解（避免黑屏）。
         */
        private val SOFTWARE_ONLY_SELECTOR = MediaCodecSelector { mimeType, requiresSecureDecoder, requiresTunnelingDecoder ->
            val all = MediaCodecUtil.getDecoderInfos(mimeType, requiresSecureDecoder, requiresTunnelingDecoder)
            val software = all.filter { !it.hardwareAccelerated }
            if (software.isNotEmpty()) software else all
        }

        /**
         * 缓冲档位：1080 档优先秒开；4K 档给更大的前向缓冲吸收码率抖动。
         *
         * - 1080：min 15s / max 45s，起播 1.2s，重缓冲 2.5s，回退缓冲 15s，目标 64MiB
         * - 4K：  min 30s / max 90s，起播 2.5s，重缓冲 5.0s，回退缓冲 30s，目标 160MiB
         *
         * 之前全用 media3 默认值（50s/50s/2.5s/5s），直播起播慢且 4K 缓冲不足。
         */
        fun buildLoadControl(use4kTier: Boolean): DefaultLoadControl {
            val builder = DefaultLoadControl.Builder().setPrioritizeTimeOverSizeThresholds(true)
            return if (use4kTier) {
                builder
                    .setBufferDurationsMs(30_000, 90_000, 2_500, 5_000)
                    .setBackBuffer(30_000, false)
                    .setTargetBufferBytes(160 * 1024 * 1024)
                    .build()
            } else {
                builder
                    .setBufferDurationsMs(15_000, 45_000, 1_200, 2_500)
                    .setBackBuffer(15_000, false)
                    .setTargetBufferBytes(64 * 1024 * 1024)
                    .build()
            }
        }
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null
    private var currentUrl: String = ""
    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private fun isMainThread() = android.os.Looper.myLooper() == android.os.Looper.getMainLooper()

    /** MP2 音频链路兜底：音频时钟 50s 未启动（Mp2Decoder 无 PCM 产出）时回调，由上层切换 MPV 内核 */
    var onStalledAudio: (() -> Unit)? = null
    private var audioClockStartedForCurrentPlay = false
    private val stalledAudioCheckRunnable = Runnable {
        if (!audioClockStartedForCurrentPlay) {
            Log.e(TAG, "AUDIO clock never started (Mp2 audio stalled), requesting kernel fallback")
            diagLog("MP2 audio stalled: audio clock never started, fallback")
            onStalledAudio?.invoke()
        }
    }

    /** 音频焦点：与 MpvController 同一套抢占暂停/回播语义 */
    private val audioFocus = AudioFocusHelper(context).also { h ->
        h.onPause = { setPause(true) }
        h.onResume = { setPause(false) }
        h.isPaused = { paused.value }
    }

    // -----------------------------------------------------------------
    // 可观察状态（与 MpvController StateFlow 对齐）
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

    /** 音频解码失败信号（如 MP2 格式 Android 不支持），UI 监听后自动切换到 MPV */
    private val _audioDecodeError = MutableStateFlow(false)
    val audioDecodeError: StateFlow<Boolean> = _audioDecodeError.asStateFlow()

    private val _mediaTitle = MutableStateFlow("")
    override val mediaTitle: StateFlow<String> = _mediaTitle.asStateFlow()

    private val _trackListJson = MutableStateFlow("[]")
    override val trackListJson: StateFlow<String> = _trackListJson.asStateFlow()

    private val _eofReached = MutableStateFlow(false)
    override val eofReached: StateFlow<Boolean> = _eofReached.asStateFlow()

    private val _fileLoaded = MutableStateFlow(false)
    override val fileLoaded: StateFlow<Boolean> = _fileLoaded.asStateFlow()

    private val _videoWidth = MutableStateFlow(0)
    override val videoWidth: StateFlow<Int> = _videoWidth.asStateFlow()

    private val _videoHeight = MutableStateFlow(0)
    override val videoHeight: StateFlow<Int> = _videoHeight.asStateFlow()

    private val _speed = MutableStateFlow(1.0)
    override val speed: StateFlow<Double> = _speed.asStateFlow()

    private val _currentChapter = MutableStateFlow(-1)
    override val currentChapter: StateFlow<Int> = _currentChapter.asStateFlow()

    private val _chapterCount = MutableStateFlow(0)
    override val chapterCount: StateFlow<Int> = _chapterCount.asStateFlow()

    // -----------------------------------------------------------------
    // 能力声明
    // -----------------------------------------------------------------

    override val capabilities: PlayerCapabilities = PlayerCapabilities(
        supportsSpeedControl = true,
        supportsTrackList = true,
        supportsAddSubtitleFile = true,
        supportsSubDelay = false,
        supportsSubScale = false,
        supportsSubPos = false,
        supportsHardwareDecodeSwitch = true
    )

    override val playerType: PlayerType = PlayerType.EXO

    // -----------------------------------------------------------------
    // 生命周期
    // -----------------------------------------------------------------

    /**
     * 绑定 View（PlayerView）。
     * 同时初始化 ExoPlayer 实例（如果尚未初始化）。
     */
    override fun attachView(view: Any) {
        if (view !is PlayerView) {
            Log.w(TAG, "attachView: expected PlayerView, got ${view::class.simpleName}")
            return
        }
        playerView = view
        ensurePlayer()
        view.player = player
        // 不再在 attachView 中调 setHardwareDecode：
        // 渲染器模式在 ensurePlayer() 中根据 hardwareDecodeEnabled 直接设置，避免无效的 rebuild。
        Log.i(TAG, "attachView: PlayerView attached, hwdec=$hardwareDecodeEnabled")
    }

    /** 解绑 View，释放 ExoPlayer 资源 */
    override fun detach() {
        _fileLoaded.value = false
        _paused.value = true
        _timePos.value = 0.0
        _duration.value = 0.0
        _videoWidth.value = 0
        _videoHeight.value = 0
        if (!isMainThread()) {
            mainHandler.post {
                playerView?.player = null
                playerView = null
                try { player?.release() } catch (_: Exception) {}
                player = null
            }
            return
        }
        playerView?.player = null
        playerView = null
        try {
            player?.release()
        } catch (e: Exception) {
            Log.w(TAG, "detach: release failed: ${e.message}")
        }
        player = null
        Log.i(TAG, "detach: released")
    }

    override fun getAudioSessionId(): Int {
        return try { player?.audioSessionId ?: 0 } catch (_: Exception) { 0 }
    }


    // -----------------------------------------------------------------
    // 诊断文件日志（EMUI logd 限流吞应用日志，写文件保证可回溯）
    // -----------------------------------------------------------------
    private val diagLock = Any()
    private fun diagLog(msg: String) {
        try {
            synchronized(diagLock) {
                val dir = context.getExternalFilesDir(null) ?: return
                val f = java.io.File(dir, "exoplayer_diag.log")
                if (f.length() > 512 * 1024) f.delete()
                val ts = java.text.SimpleDateFormat("MM-dd HH:mm:ss.SSS", java.util.Locale.US)
                    .format(java.util.Date())
                f.appendText("$ts $msg\n")
            }
        } catch (_: Exception) {}
    }

    // -----------------------------------------------------------------
    // 内核调优状态（缓冲档位 / 4K 降级 / 首帧看门狗）
    // -----------------------------------------------------------------

    /** 上次已知视频高度：跨进程持久化，用于下次建播放器时选 1080/4K 缓冲档 */
    private var lastVideoHeight: Int = 0

    /** 当前播放器实际使用的缓冲档位（true=4K 档） */
    private var loadControl4k = false

    /** 已检测到需要切换档位，等下一次 playFile 时重建播放器（避免播放中打断） */
    private var pendingTierRebuild: Boolean? = null

    /** 最近一次视频编码（用于判断 4K HEVC 降级） */
    private var lastVideoMime: String? = null

    /** 4K/HEVC 硬解初始化失败后本会话固定软解（只降一次，避免反复重建） */
    private var fourKSoftFallbackDone = false

    /** 4K 首帧看门狗：SurfaceView 输出在部分设备上不吐首帧时请求切 TextureView */
    private var firstFrameSeen = false
    private var textureFallbackRequested = false
    var onRequestTextureViewFallback: (() -> Unit)? = null

    private val firstFrameWatchdogRunnable = Runnable {
        if (!firstFrameSeen && _videoHeight.value >= 1440 && !textureFallbackRequested) {
            textureFallbackRequested = true
            Log.w(TAG, "4K first frame not rendered in 6s, requesting TextureView fallback")
            diagLog("4K first frame timeout -> request TextureView")
            onRequestTextureViewFallback?.invoke()
        }
    }

    private val tuningPrefs by lazy {
        context.getSharedPreferences("exo_tuning", Context.MODE_PRIVATE)
    }

    private fun ensurePlayer() {
        if (player != null) return
        try {
            // ExoPlayer 使用 Android HTTP 栈，受 network_security_config.xml 限制。
            // MPV 用自己的网络栈不受影响，但 ExoPlayer 需要显式允许 cleartext HTTP。
            // setAllowCrossProtocolRedirects=true 允许 HTTPS→HTTP 重定向（IPTV 常见）。
            val httpDataSourceFactory = DefaultHttpDataSource.Factory()
                .setUserAgent(USER_AGENT)
                .setConnectTimeoutMs(10_000)
                .setReadTimeoutMs(30_000)
                .setAllowCrossProtocolRedirects(true)
            val dataSourceFactory = DefaultDataSource.Factory(context, httpDataSourceFactory)
            val mediaSourceFactory = DefaultMediaSourceFactory(dataSourceFactory)

            // 渲染器配置：根据 hardwareDecodeEnabled 选择解码器
            // - 硬解：使用默认 MediaCodecSelector，优先硬件编解码器（GPU 加速）
            // - 软解：使用自定义 MediaCodecSelector，只返回软件编解码器（如 OMX.google.*）
            //
            // 不依赖 FFmpeg 扩展（Google 不发布预编译的 media3-decoder-ffmpeg AAR），
            // 而是通过 MediaCodecSelector 过滤 Android 系统自带的软件编解码器实现软解。
            //
            // DefaultRenderersFactory 扩展渲染器模式说明：
            // - OFF：不加载扩展渲染器（无 FFmpeg 扩展时等于默认行为）
            // - setEnableDecoderFallback(true)：允许解码器 fallback，提升兼容性
            // 4K 档判定：用上一次播放到的高度（跨进程持久化）。首次启动未知时先按 1080 档，
            // 检测到 4K 后在下一次换台（playFile）时重建播放器切到 4K 缓冲档，不打断当前播放。
            if (lastVideoHeight == 0) {
                lastVideoHeight = tuningPrefs.getInt(KEY_LAST_VIDEO_HEIGHT, 0)
            }
            loadControl4k = lastVideoHeight >= 1440

            val renderersFactory = CustomRenderersFactory(context)
                .setEnableDecoderFallback(true)
                .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_PREFER)
                .setMediaCodecSelector(
                    if (hardwareDecodeEnabled) MediaCodecSelector.DEFAULT
                    else SOFTWARE_ONLY_SELECTOR
                )
            player = ExoPlayer.Builder(context, renderersFactory)
                .setMediaSourceFactory(mediaSourceFactory)
                .setUseLazyPreparation(true)
                // 1080 / 4K 分档缓冲（直播优先起播速度，4K 给更大余量）
                .setLoadControl(buildLoadControl(loadControl4k))
                // 跳过静音段：直播插播静音时保持音频时钟连续，减少音画漂移
                .setSkipSilenceEnabled(true)
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(C.USAGE_MEDIA)
                        .setContentType(C.AUDIO_CONTENT_TYPE_MOVIE)
                        .build(),
                    false  // handleAudioFocus = false，避免模拟器音频焦点竞争导致无声
                )
                .setHandleAudioBecomingNoisy(true)
                .build().also { p ->
                    p.addListener(object : Media3Player.Listener {
                        override fun onPlaybackStateChanged(playbackState: Int) {
                            when (playbackState) {
                                Media3Player.STATE_BUFFERING -> {
                                    // buffering
                                }
                                Media3Player.STATE_READY -> {
                                    _paused.value = !p.isPlaying
                                    _fileLoaded.value = true
                                    _duration.value = (p.duration.coerceAtLeast(0)) / 1000.0
                                    // 4K 首帧看门狗：SurfaceView 在部分电视盒子上不吐首帧（黑屏但有声），
                                    // 6s 未出画则请求上层切 TextureView（同一次进程只请求一次）
                                    mainHandler.removeCallbacks(firstFrameWatchdogRunnable)
                                    if (_videoHeight.value >= FOUR_K_HEIGHT_THRESHOLD && !textureFallbackRequested) {
                                        mainHandler.postDelayed(firstFrameWatchdogRunnable, FIRST_FRAME_TIMEOUT_MS)
                                    }
                                }
                                Media3Player.STATE_ENDED -> {
                                    _eofReached.value = true
                                    _paused.value = true
                                }
                                Media3Player.STATE_IDLE -> {
                                    _fileLoaded.value = false
                                }
                            }
                        }

                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            _paused.value = !isPlaying
                        }

                        override fun onTracksChanged(tracks: androidx.media3.common.Tracks) {
                            // 检查音轨选择状态
                            val audioGroups = tracks.groups.filter { it.type == C.TRACK_TYPE_AUDIO }
                            val hasSelectedAudio = audioGroups.any { it.isSelected }
                            if (!hasSelectedAudio && audioGroups.isNotEmpty()) {
                                Log.w(TAG, "No audio track selected, attempting to force-enable")
                                try {
                                    // 强制启用音轨类型（不被disabled）
                                    p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                                        .setTrackTypeDisabled(C.TRACK_TYPE_AUDIO, false)
                                        .build()
                                    // 尝试直接override第一个音轨
                                    val firstAudioGroup = audioGroups[0]
                                    val supportedIndices = (0 until firstAudioGroup.length)
                                        .filter { firstAudioGroup.isTrackSupported(it) }
                                    if (supportedIndices.isNotEmpty()) {
                                        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                                            .setOverrideForType(
                                                androidx.media3.common.TrackSelectionOverride(
                                                    firstAudioGroup.mediaTrackGroup, supportedIndices
                                                )
                                            )
                                            .build()
                                        Log.i(TAG, "Forced audio track selection: group=${firstAudioGroup.mediaTrackGroup}, indices=$supportedIndices")
                                    } else {
                                        // 即使 supported=false 也尝试强制选择
                                        val allIndices = (0 until firstAudioGroup.length).toList()
                                        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                                            .setOverrideForType(
                                                androidx.media3.common.TrackSelectionOverride(
                                                    firstAudioGroup.mediaTrackGroup, allIndices
                                                )
                                            )
                                            .build()
                                        Log.i(TAG, "Force-selected unsupported audio track: group=${firstAudioGroup.mediaTrackGroup}, indices=$allIndices")
                                    }
                                } catch (e: Exception) {
                                    Log.e(TAG, "Failed to force audio track", e)
                                }
                            }
                        }

                        override fun onPlayerError(error: PlaybackException) {
                            Log.e(TAG, "Player error: ${error.message}", error)
                            _fileLoaded.value = false
                            mainHandler.removeCallbacks(firstFrameWatchdogRunnable)
                            // 4K / HEVC 硬解初始化失败：降级到软解重建一次，不依赖 media3 默认 fallback
                            val is4kOrHevc = lastVideoHeight >= FOUR_K_HEIGHT_THRESHOLD ||
                                lastVideoMime?.contains("hevc", ignoreCase = true) == true
                            if (hardwareDecodeEnabled && is4kOrHevc && !fourKSoftFallbackDone &&
                                currentUrl.isNotEmpty()
                            ) {
                                fourKSoftFallbackDone = true
                                hardwareDecodeEnabled = false
                                Log.w(TAG, "4K/HEVC hardware decode failed (${error.errorCodeName}), " +
                                    "falling back to software decoder once")
                                diagLog("4K/HEVC hw decode failed -> software fallback")
                                player?.release()
                                player = null
                                ensurePlayer()
                                val url = currentUrl
                                currentUrl = ""
                                playFile(url)
                                return
                            }
                            // 降级重试：若当前为软解且出错，自动切回硬解重试
                            if (!hardwareDecodeEnabled && currentUrl.isNotEmpty()) {
                                Log.w(TAG, "Soft decode failed, falling back to hardware decode")
                                hardwareDecodeEnabled = true
                                player?.release()
                                player = null
                                ensurePlayer()
                                val url = currentUrl
                                currentUrl = ""
                                playFile(url)
                            }
                        }

                        override fun onVideoSizeChanged(videoSize: VideoSize) {
                            _videoWidth.value = videoSize.width
                            _videoHeight.value = videoSize.height
                            Log.i(TAG, "onVideoSizeChanged: ${videoSize.width}x${videoSize.height}")
                            // 记录高度：下一次 playFile 时按 1080/4K 档重建缓冲配置
                            lastVideoHeight = videoSize.height
                            tuningPrefs.edit().putInt(KEY_LAST_VIDEO_HEIGHT, videoSize.height).apply()
                            val want4k = videoSize.height >= FOUR_K_HEIGHT_THRESHOLD
                            if (want4k != loadControl4k) {
                                pendingTierRebuild = want4k
                                Log.i(TAG, "buffer tier change pending: 4k=$want4k (applied on next playFile)")
                            }
                        }

                        override fun onRenderedFirstFrame() {
                            firstFrameSeen = true
                            mainHandler.removeCallbacks(firstFrameWatchdogRunnable)
                            Log.i(TAG, "VIDEO first frame rendered")
                        }
                    })
                // 视频管线诊断（AnalyticsListener 携带解码器/帧计数细节）
                p.addAnalyticsListener(object : androidx.media3.exoplayer.analytics.AnalyticsListener {
                    override fun onVideoEnabled(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        decoderCounters: androidx.media3.exoplayer.DecoderCounters
                    ) {
                        Log.i(TAG, "VIDEO enabled"); diagLog("VIDEO enabled")
                    }

                    override fun onRenderedFirstFrame(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        output: Any,
                        renderTimeMs: Long
                    ) {
                        Log.i(TAG, "VIDEO first frame rendered to $output"); diagLog("VIDEO first frame")
                    }

                    override fun onVideoInputFormatChanged(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        format: androidx.media3.common.Format,
                        decoderReuseEvaluation: androidx.media3.exoplayer.DecoderReuseEvaluation?
                    ) {
                        lastVideoMime = format.sampleMimeType
                        Log.i(TAG, "VIDEO input format: ${format.sampleMimeType} ${format.width}x${format.height}"); diagLog("format: ${format.sampleMimeType} ${format.width}x${format.height}")
                    }

                    override fun onDroppedVideoFrames(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        droppedFrames: Int,
                        elapsedMs: Long
                    ) {
                        Log.w(TAG, "VIDEO dropped frames: $droppedFrames in ${elapsedMs}ms")
                    }

                    override fun onIsLoadingChanged(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        isLoading: Boolean
                    ) {
                        Log.i(TAG, "LOADER isLoading=$isLoading"); diagLog("isLoading=$isLoading")
                    }

                    override fun onLoadError(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        loadEventInfo: androidx.media3.exoplayer.source.LoadEventInfo,
                        mediaLoadData: androidx.media3.exoplayer.source.MediaLoadData,
                        error: java.io.IOException,
                        wasCanceled: Boolean
                    ) {
                        Log.e(TAG, "LOADER error: ${error.javaClass.simpleName}: ${error.message}"); diagLog("LOAD ERROR: ${error.javaClass.simpleName}: ${error.message}")
                    }

                    override fun onLoadCompleted(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        loadEventInfo: androidx.media3.exoplayer.source.LoadEventInfo,
                        mediaLoadData: androidx.media3.exoplayer.source.MediaLoadData
                    ) {
                        Log.i(TAG, "LOADER completed: bytes=${loadEventInfo.bytesLoaded}"); diagLog("loadCompleted bytes=${loadEventInfo.bytesLoaded}")
                    }

                    override fun onUpstreamDiscarded(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        mediaLoadData: androidx.media3.exoplayer.source.MediaLoadData
                    ) {
                        Log.w(TAG, "LOADER upstream discarded")
                    }

                    override fun onAudioEnabled(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        audioCounters: androidx.media3.exoplayer.DecoderCounters
                    ) {
                        Log.i(TAG, "AUDIO enabled"); diagLog("AUDIO enabled")
                    }

                    override fun onAudioDisabled(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        audioCounters: androidx.media3.exoplayer.DecoderCounters
                    ) {
                        Log.w(TAG, "AUDIO disabled: rendered=${audioCounters.renderedOutputBufferCount}")
                        diagLog("AUDIO disabled rendered=${audioCounters.renderedOutputBufferCount}")
                    }

                    override fun onAudioDecoderInitialized(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        decoderName: String,
                        initializedTimestampMs: Long,
                        initializationDurationMs: Long
                    ) {
                        Log.i(TAG, "AUDIO decoder initialized: $decoderName")
                        diagLog("AUDIO decoder: $decoderName (${initializationDurationMs}ms)")
                    }

                    override fun onAudioPositionAdvancing(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        playoutStartSystemTimeMs: Long
                    ) {
                        audioClockStartedForCurrentPlay = true
                        mainHandler.removeCallbacks(stalledAudioCheckRunnable)
                        Log.i(TAG, "AUDIO position advancing"); diagLog("AUDIO position advancing")
                    }

                    override fun onAudioInputFormatChanged(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        format: androidx.media3.common.Format,
                        decoderReuseEvaluation: androidx.media3.exoplayer.DecoderReuseEvaluation?
                    ) {
                        Log.i(TAG, "AUDIO format: ${format.sampleMimeType} rate=${format.sampleRate} ch=${format.channelCount}")
                        diagLog("AUDIO format: ${format.sampleMimeType} rate=${format.sampleRate} ch=${format.channelCount}")
                    }

                    override fun onAudioUnderrun(
                        eventTime: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime,
                        bufferSize: Int,
                        bufferSizeBytes: Long,
                        elapsedBufferTimeMs: Long
                    ) {
                        Log.w(TAG, "AUDIO underrun"); diagLog("AUDIO underrun")
                    }
                })
                }
            Log.i(TAG, "ExoPlayer initialized, hwdec=$hardwareDecodeEnabled")
            // 确保初始音量正确设置
            val initVol = if (_muted.value) 0f else (_volume.value / 100f).coerceIn(0f, 1f)
            player?.volume = initVol
            Log.i(TAG, "ExoPlayer initial volume=$initVol (muted=${_muted.value}, vol=${_volume.value})")
        } catch (e: Exception) {
            Log.e(TAG, "ensurePlayer failed", e)
        }
    }

    // -----------------------------------------------------------------
    // 基础播放控制
    // -----------------------------------------------------------------

    override fun playFile(url: String) {
        currentUrl = url
        _eofReached.value = false
        _fileLoaded.value = false
        audioFocus.request()
        // MP2 音频兜底检查：正常播放时音频时钟数秒内启动
        audioClockStartedForCurrentPlay = false
        mainHandler.removeCallbacks(stalledAudioCheckRunnable)
        mainHandler.postDelayed(stalledAudioCheckRunnable, 50_000L)
        if (!isMainThread()) {
            mainHandler.post { playFileOnMainThread(url) }
            return
        }
        playFileOnMainThread(url)
    }

    private fun playFileOnMainThread(url: String) {
        // 检测到 1080/4K 档位变化：在换台这一刻重建播放器（不打断正在播放的流）
        pendingTierRebuild?.let { want4k ->
            pendingTierRebuild = null
            if (want4k != loadControl4k) {
                Log.i(TAG, "rebuilding player for buffer tier: 4k=$want4k")
                try { player?.release() } catch (_: Throwable) {}
                player = null
                loadControl4k = want4k
            }
        }
        firstFrameSeen = false
        mainHandler.removeCallbacks(firstFrameWatchdogRunnable)
        ensurePlayer()
        val p = player ?: run {
            Log.e(TAG, "playFile: player is null")
            return
        }
        try {
            Log.i(TAG, "playFile: $url"); diagLog("playFile: $url")
            val mediaItem = MediaItem.Builder().setUri(Uri.parse(url)).build()
            p.setMediaItem(mediaItem)
            p.prepare()
            p.playWhenReady = true
            _paused.value = false
            _mediaTitle.value = url.substringAfterLast('/').substringBefore('?')
            // 诊断：周期采样播放状态（pos/渲染帧数随时间变化，定位时钟或释放问题）
            for (i in 1..6) mainHandler.postDelayed({
                try {
                    val audioGroups = p.currentTracks.groups.filter { it.type == C.TRACK_TYPE_AUDIO }
                    val vCounters = p.videoDecoderCounters
                    Log.i(TAG, "EXO audio diag: volume=${p.volume}, audioSessionId=${p.audioSessionId}, " +
                        "audioGroups=${audioGroups.size}, " +
                        "selected=${audioGroups.count { it.isSelected }}, " +
                        "isPlaying=${p.isPlaying}, playWhenReady=${p.playWhenReady}, " +
                        "playbackState=${p.playbackState}, pos=${p.currentPosition}ms, " +
                        "renderedOut=${vCounters?.renderedOutputBufferCount}, droppedBuf=${vCounters?.droppedBufferCount}")
                    diagLog("diag: state=${p.playbackState} pos=${p.currentPosition} rendered=${vCounters?.renderedOutputBufferCount} isPlaying=${p.isPlaying}")
                    audioGroups.forEachIndexed { i, g ->
                        Log.i(TAG, "  audioGroup[$i]: selected=${g.isSelected}, length=${g.length}, " +
                            "supported=${(0 until g.length).map { g.isTrackSupported(it) }}")
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "EXO audio diag failed", e)
                }
            }, 2000L * i)
        } catch (e: Exception) {
            Log.e(TAG, "playFile failed: $url", e)
        }
    }

    override fun stop() {
        currentUrl = ""
        _fileLoaded.value = false
        _paused.value = true
        _timePos.value = 0.0
        audioFocus.abandon()
        mainHandler.removeCallbacks(stalledAudioCheckRunnable)
        if (!isMainThread()) {
            mainHandler.post { player?.stop() }
            return
        }
        try {
            player?.stop()
            Log.i(TAG, "stop")
        } catch (e: Exception) {
            Log.w(TAG, "stop failed: ${e.message}")
        }
    }

    override fun refreshSurface() {
        // ExoPlayer 不需要手动刷新 Surface
    }

    override fun togglePause() {
        if (!isMainThread()) {
            mainHandler.post { togglePause() }
            return
        }
        val p = player ?: return
        p.playWhenReady = !p.playWhenReady
        _paused.value = !p.playWhenReady
    }

    override fun setPause(p: Boolean) {
        _paused.value = p
        if (!isMainThread()) {
            mainHandler.post { player?.playWhenReady = !p }
            return
        }
        player?.playWhenReady = !p
    }

    override fun seekTo(seconds: Double) {
        val targetMs = (seconds * 1000).toLong()
        if (!isMainThread()) {
            mainHandler.post { player?.seekTo(targetMs) }
            return
        }
        player?.seekTo(targetMs)
    }

    override fun seekRelative(seconds: Double) {
        if (!isMainThread()) {
            mainHandler.post { seekRelative(seconds) }
            return
        }
        val p = player ?: return
        val target = (p.currentPosition + seconds * 1000.0).coerceAtLeast(0.0)
            .coerceAtMost(p.duration.coerceAtLeast(0L).toDouble())
        p.seekTo(target.toLong())
    }

    override fun seekAbsolute(seconds: Double) {
        seekTo(seconds)
    }

    // -----------------------------------------------------------------
    // 音量 / 静音 / 速度
    // -----------------------------------------------------------------

    override fun setVolume(v: Int) {
        val clamped = v.coerceIn(0, 130)
        _volume.value = clamped
        val vol = (clamped / 100f).coerceIn(0f, 1f)
        if (!isMainThread()) {
            mainHandler.post { player?.volume = vol }
            return
        }
        player?.volume = vol
    }

    override fun adjustVolume(delta: Int) {
        setVolume(_volume.value + delta)
    }

    override fun toggleMute() {
        setMute(!_muted.value)
    }

    override fun setMute(m: Boolean) {
        _muted.value = m
        val vol = if (m) 0f else (_volume.value / 100f).coerceIn(0f, 1f)
        if (!isMainThread()) {
            mainHandler.post { player?.volume = vol }
            return
        }
        player?.volume = vol
    }

    override fun setSpeed(s: Double) {
        val clamped = s.coerceIn(0.01, 100.0)
        _speed.value = clamped
        if (!isMainThread()) {
            mainHandler.post { setSpeed(s) }
            return
        }
        try {
            val params = player?.playbackParameters?.withSpeed(clamped.toFloat())
            player?.playbackParameters = params ?: androidx.media3.common.PlaybackParameters(clamped.toFloat())
        } catch (e: Exception) {
            Log.w(TAG, "setSpeed failed: ${e.message}")
        }
    }

    // -----------------------------------------------------------------
    // 音轨 / 字幕轨
    // -----------------------------------------------------------------

    override fun cycleAudio() {
        val p = player ?: return
        val audioGroups = p.currentTracks.groups.filter { it.type == androidx.media3.common.C.TRACK_TYPE_AUDIO }
        if (audioGroups.isEmpty()) return
        try {
            val currentSelectedIdx = audioGroups.indexOfFirst { it.isSelected }
            val nextIdx = if (currentSelectedIdx >= 0 && currentSelectedIdx < audioGroups.size - 1) currentSelectedIdx + 1 else 0
            val nextGroup = audioGroups[nextIdx]
            val trackIndices = mutableListOf<Int>()
            for (i in 0 until nextGroup.length) {
                if (nextGroup.isTrackSupported(i)) trackIndices.add(i)
            }
            if (trackIndices.isEmpty()) return
            p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                .setOverrideForType(TrackSelectionOverride(nextGroup.mediaTrackGroup, trackIndices))
                .setTrackTypeDisabled(C.TRACK_TYPE_AUDIO, false)
                .build()
            Log.i(TAG, "cycleAudio: switched to audio track $nextIdx")
        } catch (e: Exception) {
            Log.w(TAG, "cycleAudio failed: ${e.message}")
        }
    }

    override fun cycleSub() {
        val p = player ?: return
        val subGroups = p.currentTracks.groups.filter { it.type == androidx.media3.common.C.TRACK_TYPE_TEXT }
        if (subGroups.isEmpty()) {
            val subEnabled = p.trackSelectionParameters.disabledTrackTypes
                .contains(androidx.media3.common.C.TRACK_TYPE_TEXT).not()
            p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                .setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, subEnabled)
                .build()
            return
        }
        try {
            val currentSelectedIdx = subGroups.indexOfFirst { it.isSelected }
            val nextIdx = if (currentSelectedIdx >= 0 && currentSelectedIdx < subGroups.size - 1) currentSelectedIdx + 1 else 0
            p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                .setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, false)
                .build()
            Log.i(TAG, "cycleSub: switched to subtitle track $nextIdx")
        } catch (e: Exception) {
            Log.w(TAG, "cycleSub failed: ${e.message}")
        }
    }

    override fun setAudioTrack(id: Int) {
        val p = player ?: return
        val audioGroups = p.currentTracks.groups.filter { it.type == androidx.media3.common.C.TRACK_TYPE_AUDIO }
        if (audioGroups.isEmpty() || id < 0 || id >= audioGroups.size) return
        try {
            val targetGroup = audioGroups[id]
            val trackIndices = mutableListOf<Int>()
            for (i in 0 until targetGroup.length) {
                if (targetGroup.isTrackSupported(i)) trackIndices.add(i)
            }
            if (trackIndices.isEmpty()) return
            p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                .setOverrideForType(androidx.media3.common.TrackSelectionOverride(targetGroup.mediaTrackGroup, trackIndices))
                .setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_AUDIO, false)
                .build()
            Log.i(TAG, "setAudioTrack: set to track $id")
        } catch (e: Exception) {
            Log.w(TAG, "setAudioTrack failed: ${e.message}")
        }
    }

    override fun setSubTrack(id: Int) {
        val p = player ?: return
        val subGroups = p.currentTracks.groups.filter { it.type == androidx.media3.common.C.TRACK_TYPE_TEXT }
        if (subGroups.isEmpty() || id < 0 || id >= subGroups.size) return
        try {
            val targetGroup = subGroups[id]
            val trackIndices = mutableListOf<Int>()
            for (i in 0 until targetGroup.length) {
                if (targetGroup.isTrackSupported(i)) trackIndices.add(i)
            }
            if (trackIndices.isEmpty()) return
            p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
                .setOverrideForType(androidx.media3.common.TrackSelectionOverride(targetGroup.mediaTrackGroup, trackIndices))
                .setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, false)
                .build()
            Log.i(TAG, "setSubTrack: set to track $id")
        } catch (e: Exception) {
            Log.w(TAG, "setSubTrack failed: ${e.message}")
        }
    }

    override fun addSubtitleFile(path: String): Boolean {
        // ExoPlayer 支持外挂字幕通过 MediaItem.subtitleConfigurations
        Log.i(TAG, "addSubtitleFile: $path (not fully implemented)")
        return false
    }

    // -----------------------------------------------------------------
    // 字幕显示与样式
    // -----------------------------------------------------------------

    override fun setSubVisibility(v: Boolean) {
        val p = player ?: return
        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
            .setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, !v)
            .build()
    }

    override fun setSubDelay(delaySec: Double) {
        // ExoPlayer 不支持字幕延迟设置
    }

    override fun adjustSubDelay(delta: Double) {
        // ExoPlayer 不支持字幕延迟调整
    }

    override fun setSubScale(scale: Double) {
        // ExoPlayer 不支持字幕缩放
    }

    override fun setSubPos(pos: Int) {
        // ExoPlayer 不支持字幕位置设置
    }

    override fun toggleSubVisibility() {
        val p = player ?: return
        val currentlyVisible = !p.trackSelectionParameters.disabledTrackTypes
            .contains(androidx.media3.common.C.TRACK_TYPE_TEXT)
        setSubVisibility(!currentlyVisible)
    }

    // -----------------------------------------------------------------
    // 硬件解码切换
    // -----------------------------------------------------------------

    @Volatile
    private var hardwareDecodeEnabled = true

    override fun setHardwareDecode(enabled: Boolean): Boolean {
        if (hardwareDecodeEnabled == enabled) return true
        hardwareDecodeEnabled = enabled
        Log.i(TAG, "setHardwareDecode: $enabled")
        if (!isMainThread()) {
            mainHandler.post { setHardwareDecode(enabled) }
            return true
        }
        try {
            val p = player ?: return true
            // 重建播放器以应用新的 RenderersFactory 配置
            val currentUrl = this.currentUrl
            if (currentUrl.isNotEmpty()) {
                val currentPosition = p.currentPosition
                p.release()
                player = null
                ensurePlayer()
                player?.let { newPlayer ->
                    val mediaItem = MediaItem.Builder().setUri(Uri.parse(currentUrl)).build()
                    newPlayer.setMediaItem(mediaItem)
                    newPlayer.prepare()
                    if (currentPosition > 0) {
                        newPlayer.seekTo(currentPosition)
                    }
                    newPlayer.playWhenReady = true
                    _paused.value = false
                    // 重新绑定到 PlayerView
                    playerView?.player = newPlayer
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "setHardwareDecode failed", e)
        }
        return true
    }

    override fun isHardwareDecodeEnabled(): Boolean = hardwareDecodeEnabled

    // -----------------------------------------------------------------
    // 播放状态保存/恢复
    // -----------------------------------------------------------------

    override fun savePlaybackState(): Pair<String, Double>? {
        if (currentUrl.isEmpty()) return null
        return Pair(currentUrl, _timePos.value)
    }

    override fun restorePlaybackState(url: String, timePosSec: Double) {
        playFile(url)
        if (timePosSec > 0) {
            val targetMs = (timePosSec * 1000).toLong()
            val p = player ?: return
            val listener = object : Media3Player.Listener {
                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (playbackState == Media3Player.STATE_READY) {
                        p.seekTo(targetMs)
                        p.removeListener(this)
                    }
                }
            }
            p.addListener(listener)
        }
    }

    /**
     * 获取媒体信息（与 MpvController.getMediaInfo 对齐）。
     * 通过 ExoPlayer 的 TrackInfo 提取视频/音频编码、分辨率、HDR 等信息。
     */
    override fun getMediaInfo(): Map<String, String?> {
        val p = player ?: return emptyMap()
        return try {
            val tracks = p.currentTracks
            var videoCodec: String? = null
            var audioCodec: String? = null
            var videoBitrate: String? = null
            var audioBitrate: String? = null
            var fps: String? = null
            var primaries: String? = null
            var gamma: String? = null
            var colorRange: String? = null

            for (trackGroup in tracks.groups) {
                val trackType = trackGroup.type
                if (trackGroup.length == 0) continue
                val format = trackGroup.getTrackFormat(0)
                when (trackType) {
                    androidx.media3.common.C.TRACK_TYPE_VIDEO -> {
                        videoCodec = format.sampleMimeType
                        videoBitrate = if (format.bitrate > 0) format.bitrate.toString() else null
                        if (format.frameRate > 0f) fps = format.frameRate.toString()
                        val colorInfo = format.colorInfo
                        if (colorInfo != null) {
                            primaries = when (colorInfo.colorSpace) {
                                androidx.media3.common.C.COLOR_SPACE_BT709 -> "bt.709"
                                androidx.media3.common.C.COLOR_SPACE_BT601 -> "bt.601"
                                androidx.media3.common.C.COLOR_SPACE_BT2020 -> "bt.2020"
                                else -> null
                            }
                            gamma = when (colorInfo.colorTransfer) {
                                androidx.media3.common.C.COLOR_TRANSFER_SDR -> "sdr"
                                androidx.media3.common.C.COLOR_TRANSFER_HLG -> "hlg"
                                androidx.media3.common.C.COLOR_TRANSFER_ST2084 -> "pq"
                                else -> null
                            }
                            colorRange = when (colorInfo.colorRange) {
                                androidx.media3.common.C.COLOR_RANGE_FULL -> "full"
                                androidx.media3.common.C.COLOR_RANGE_LIMITED -> "limited"
                                else -> null
                            }
                        }
                    }
                    androidx.media3.common.C.TRACK_TYPE_AUDIO -> {
                        audioCodec = format.sampleMimeType
                        audioBitrate = if (format.bitrate > 0) format.bitrate.toString() else null
                    }
                }
            }

            mapOf(
                "videoCodec" to videoCodec,
                "audioCodec" to audioCodec,
                "videoRes" to "${_videoWidth.value}x${_videoHeight.value}",
                "fps" to fps,
                "bitrate" to videoBitrate,
                "audioBitrate" to audioBitrate,
                "containerFormat" to p.currentMediaItem?.localConfiguration?.mimeType,
                "hwdec" to if (hardwareDecodeEnabled) "mediacodec" else "software",
                "vo" to "exo",
                "videoPrimaries" to primaries,
                "videoGamma" to gamma,
                "videoColorRange" to colorRange
            )
        } catch (e: Throwable) {
            Log.w(TAG, "getMediaInfo failed: ${e.message}")
            emptyMap()
        }
    }

    /**
     * 更新进度（由 UI 定时轮询调用，与 MpvController 的 progress report 对齐）。
     */
    fun updateProgress() {
        val p = player ?: return
        if (!isMainThread()) {
            mainHandler.post { updateProgress() }
            return
        }
        try {
            _timePos.value = p.currentPosition / 1000.0
            if (p.duration > 0) {
                _duration.value = p.duration / 1000.0
            }
        } catch (e: Exception) {
            // ignore
        }
    }
}
