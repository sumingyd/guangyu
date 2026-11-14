package com.iptv.scanner.editor.pro.player

import android.content.Context
import android.util.Log
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player as Media3Player
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 副画面播放器状态（UI 观察用）。
 */
data class SubPlayerState(
    val isPlaying: Boolean = false,
    val isBuffering: Boolean = false,
    val isError: Boolean = false,
    val errorMessage: String = "",
    val currentUrl: String = ""
)

/**
 * 基于 ExoPlayer 的副画面播放器。
 *
 * MPV 在安卓端为单例（MPVLib.create 只能调用一次），不支持多实例。
 * 多画面模式的副画面（index 1-8）使用 ExoPlayer 独立播放。
 *
 * 设计要点：
 * - 每个副视口创建一个独立的 ExoPlayer 实例（最多 8 个）
 * - 默认静音（只有主画面有声音），用户可手动取消静音
 * - 支持 HLS/HTTP/HTTPS/RTSP 协议
 * - User-Agent 与 MPV 主播放器保持一致（VLC/3.0.18Libmpv），确保流兼容性
 * - 生命周期由 [AppViewModel] 管理：进入多画面时创建，退出时释放
 *
 * 不实现 [Player] 接口（该接口有 100+ MPV 专属方法），仅提供副画面所需的最小 API。
 */
class SubPlayer(private val context: Context) {

    companion object {
        private const val TAG = "SubPlayer"
        /** 与 MPV 主播放器一致的 User-Agent */
        private const val USER_AGENT = "VLC/3.0.18Libmpv"
        /** 实例计数器（用于日志诊断多实例创建） */
        private var instanceCounter = 0
    }

    /** 实例ID（日志用） */
    private val instanceId = ++instanceCounter

    private var player: ExoPlayer? = null

    private val _state = MutableStateFlow(SubPlayerState())
    val state: StateFlow<SubPlayerState> = _state.asStateFlow()

    /** 是否已释放（释放后不能再使用） */
    private var released = false

    /** 当前是否静音 */
    var isMuted: Boolean = true
        private set

    /**
     * 初始化 ExoPlayer 实例。
     * 使用硬解 + 低延迟配置，适合多画面同时播放。
     */
    fun init() {
        Log.i(TAG, "init[#$instanceId]: called, released=$released, player=${player != null}")
        if (released) {
            Log.w(TAG, "init[#$instanceId]: already released, ignoring")
            return
        }
        if (player != null) {
            Log.w(TAG, "init[#$instanceId]: already initialized")
            return
        }
        try {
            Log.i(TAG, "init[#$instanceId]: creating ExoPlayer (instance #$instanceId, total instances=$instanceCounter)")
            // 设置与 MPV 一致的 User-Agent，确保 IPTV 流兼容性
            val httpDataSourceFactory = DefaultHttpDataSource.Factory()
                .setUserAgent(USER_AGENT)
                .setConnectTimeoutMs(8000)
                .setReadTimeoutMs(8000)
                .setAllowCrossProtocolRedirects(true)
            val dataSourceFactory = DefaultDataSource.Factory(context, httpDataSourceFactory)
            val mediaSourceFactory = DefaultMediaSourceFactory(dataSourceFactory)

            val renderersFactory = com.iptv.scanner.editor.pro.player.CustomRenderersFactory(context)
                .setEnableDecoderFallback(true)
                .setExtensionRendererMode(androidx.media3.exoplayer.DefaultRenderersFactory.EXTENSION_RENDERER_MODE_PREFER)
            player = ExoPlayer.Builder(context, renderersFactory)
                .setMediaSourceFactory(mediaSourceFactory)
                .setUseLazyPreparation(true)
                .setAudioAttributes(
                    androidx.media3.common.AudioAttributes.Builder()
                        .setUsage(androidx.media3.common.C.USAGE_MEDIA)
                        .setContentType(androidx.media3.common.C.AUDIO_CONTENT_TYPE_MOVIE)
                        .build(),
                    false
                )
                .setHandleAudioBecomingNoisy(true)
                .build().also { p ->
                    p.addListener(object : Media3Player.Listener {
                        override fun onPlaybackStateChanged(playbackState: Int) {
                            Log.i(TAG, "onPlaybackStateChanged[#$instanceId]: state=$playbackState (${when(playbackState){1->"BUFFERING";2->"READY";3->"ENDED";else->"IDLE"}})")
                            when (playbackState) {
                                Media3Player.STATE_BUFFERING -> {
                                    _state.value = _state.value.copy(
                                        isBuffering = true,
                                        isError = false
                                    )
                                }
                                Media3Player.STATE_READY -> {
                                    _state.value = _state.value.copy(
                                        isBuffering = false,
                                        isPlaying = player?.isPlaying == true,
                                        isError = false
                                    )
                                }
                                Media3Player.STATE_ENDED -> {
                                    _state.value = _state.value.copy(
                                        isPlaying = false,
                                        isBuffering = false
                                    )
                                }
                                Media3Player.STATE_IDLE -> {
                                    _state.value = _state.value.copy(
                                        isPlaying = false,
                                        isBuffering = false
                                    )
                                }
                            }
                        }

                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            Log.i(TAG, "onIsPlayingChanged[#$instanceId]: isPlaying=$isPlaying")
                            _state.value = _state.value.copy(isPlaying = isPlaying)
                        }

                        override fun onPlayerError(error: PlaybackException) {
                            Log.e(TAG, "onPlayerError[#$instanceId]: ${error.message}", error)
                            _state.value = _state.value.copy(
                                isError = true,
                                errorMessage = playbackErrorHint(error.message, error.errorCode),
                                isPlaying = false,
                                isBuffering = false
                            )
                        }
                    })
                    // 副画面默认静音
                    p.volume = 0f
                }
            Log.i(TAG, "init[#$instanceId]: ExoPlayer initialized successfully, player=${player?.hashCode()}")
        } catch (e: Exception) {
            Log.e(TAG, "init[#$instanceId] failed", e)
            _state.value = _state.value.copy(
                isError = true,
                errorMessage = "播放器初始化失败: ${e.message}"
            )
        }
    }

    /**
     * 播放指定 URL。
     * 支持 HLS (m3u8)、HTTP/HTTPS、RTSP 协议。
     *
     * @param url 流地址
     */
    fun play(url: String) {
        Log.i(TAG, "play[#$instanceId]: url=$url, released=$released, player=${player != null}")
        if (released || player == null) {
            Log.w(TAG, "play[#$instanceId]: player not ready, initializing first")
            init()
        }
        val p = player ?: run {
            Log.e(TAG, "play[#$instanceId]: player is null after init")
            return
        }
        try {
            Log.i(TAG, "play[#$instanceId]: setMediaItem + prepare + playWhenReady")
            val mediaItem = MediaItem.Builder()
                .setUri(url)
                .build()
            p.setMediaItem(mediaItem)
            p.prepare()
            p.playWhenReady = true
            _state.value = _state.value.copy(
                currentUrl = url,
                isError = false,
                errorMessage = "",
                isBuffering = true
            )
            Log.i(TAG, "play[#$instanceId]: media item set, preparing...")
        } catch (e: Exception) {
            Log.e(TAG, "play[#$instanceId] failed: $url", e)
            _state.value = _state.value.copy(
                isError = true,
                errorMessage = "播放失败: ${e.message}"
            )
        }
    }

    /** 停止播放 */
    fun stop() {
        try {
            player?.stop()
            _state.value = _state.value.copy(
                isPlaying = false,
                isBuffering = false,
                currentUrl = ""
            )
        } catch (e: Exception) {
            Log.w(TAG, "stop[#$instanceId] failed: ${e.message}")
        }
    }

    /**
     * 设置静音状态。
     * @param muted true=静音（volume=0），false=取消静音（volume=1）
     */
    fun setMuted(muted: Boolean) {
        isMuted = muted
        try {
            player?.volume = if (muted) 0f else 1f
            Log.i(TAG, "setMuted[#$instanceId]: $muted")
        } catch (e: Exception) {
            Log.w(TAG, "setMuted[#$instanceId] failed: ${e.message}")
        }
    }

    /** 切换静音 */
    fun toggleMute() {
        setMuted(!isMuted)
    }

    /**
     * 获取 ExoPlayer 实例（供 UI 层创建 PlayerView 时使用）。
     * @return ExoPlayer 实例，如果已释放则为 null
     */
    fun getExoPlayer(): ExoPlayer? = player

    /**
     * 释放所有资源。
     * 释放后不能再使用此实例。
     */
    fun release() {
        Log.i(TAG, "release[#$instanceId]: called, released=$released, player=${player != null}")
        if (released) return
        released = true
        try {
            player?.release()
            Log.i(TAG, "release[#$instanceId]: Released")
        } catch (e: Exception) {
            Log.w(TAG, "release[#$instanceId] failed: ${e.message}")
        }
        player = null
        _state.value = SubPlayerState()
    }
}
