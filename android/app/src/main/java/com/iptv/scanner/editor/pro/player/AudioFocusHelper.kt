package com.iptv.scanner.editor.pro.player

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.util.Log

/**
 * 音频焦点管理：播放开始时请求焦点；来电/其它应用抢占时自动暂停，
 * 短暂抢占结束后回播（仅回播由焦点抢占导致的暂停，不覆盖用户手动暂停）。
 *
 * MPV 与 ExoPlayer 双内核共用（ExoPlayer 的 handleAudioFocus 保持 false，
 * 沿用既有注释的原因：模拟器上双焦点管理会互相竞争导致无声）。
 */
class AudioFocusHelper(context: Context) {

    companion object {
        private const val TAG = "AudioFocusHelper"
    }

    private val audioManager =
        context.applicationContext.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
    private var requested = false
    private var autoPausedByFocus = false
    /** 用户手动暂停意图：抢占结束后不得覆盖 */
    private var userPaused = false
    private var focusRequest: AudioFocusRequest? = null

    /** 焦点被抢占时暂停（宿主播放器注入） */
    var onPause: (() -> Unit)? = null
    /** 焦点恢复时回播（宿主播放器注入） */
    var onResume: (() -> Unit)? = null
    /** 当前是否处于暂停态（宿主播放器注入，用于判定是否为抢占暂停） */
    var isPaused: () -> Boolean = { true }

    private val focusListener = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_LOSS -> {
                Log.i(TAG, "audio focus loss: pause + abandon")
                autoPausedByFocus = false
                onPause?.invoke()
                abandon()
            }
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> {
                if (!isPaused()) {
                    Log.i(TAG, "audio focus transient loss: pause")
                    autoPausedByFocus = true
                    onPause?.invoke()
                }
            }
            AudioManager.AUDIOFOCUS_GAIN -> {
                // 用户手动暂停优先：抢占期间用户按了暂停，不得自动恢复播放
                if (autoPausedByFocus && !userPaused) {
                    Log.i(TAG, "audio focus gain: resume")
                    autoPausedByFocus = false
                    onResume?.invoke()
                } else {
                    Log.i(TAG, "audio focus gain: keep paused (userPaused=$userPaused)")
                    autoPausedByFocus = false
                }
            }
        }
    }

    /**
     * 用户手动暂停：记录暂停意图，并清除「抢占暂停」标记，
     * 避免后续焦点恢复时覆盖用户意图。
     */
    @Synchronized
    fun onUserPause() {
        userPaused = true
        autoPausedByFocus = false
    }

    /**
     * 用户手动恢复播放：清除暂停意图并重新申请音频焦点。
     * 永久失焦（AUDIOFOCUS_LOSS）后必须重新申请，否则会与其他应用混音
     * 且后续不再响应抢占事件。
     */
    @Synchronized
    fun onUserResume() {
        userPaused = false
        request()
    }

    @Synchronized
    fun request() {
        val am = audioManager ?: return
        if (requested) return
        val req = focusRequest ?: AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE)
                    .build()
            )
            .setOnAudioFocusChangeListener(focusListener)
            .build()
            .also { focusRequest = it }
        requested = am.requestAudioFocus(req) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
    }

    @Synchronized
    fun abandon() {
        val am = audioManager ?: return
        focusRequest?.let { am.abandonAudioFocusRequest(it) }
        requested = false
        autoPausedByFocus = false
    }
}
