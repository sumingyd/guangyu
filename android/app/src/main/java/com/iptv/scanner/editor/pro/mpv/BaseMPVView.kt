package com.iptv.scanner.editor.pro.mpv

import android.util.Log
import `is`.xyz.mpv.MPVLib
import com.iptv.scanner.editor.pro.data.UserPrefs

/**
 * MPVView/MPVTextureView 公共逻辑委托。
 *
 * 由于 Kotlin 单继承限制，MPVView 继承 SurfaceView、MPVTextureView 继承 TextureView，
 * 无法提取共同基类。本类通过委托模式消除重复代码。
 */
class BaseMPVViewDelegate(
    private val instanceState: MpvInstanceState
) {
    companion object {
        private const val TAG = "mpv"
    }

    var voInUse: String = MPVView.DEFAULT_VO
    var filePath: String? = null


    fun updateLogLevel() {
        try {
            val logLevel = UserPrefs.getInstance().getLogLevel()
            val mpvMsgLevel = MpvLogLevelMapper.toMpvValue(logLevel)
            MPVLib.setPropertyString("msg-level", mpvMsgLevel)
        } catch (e: Throwable) {
            Log.w(TAG, "updateLogLevel failed: ${e.message}")
        }
    }

    fun observeProperties() {
        MPVLib.observeProperty("time-pos", MPVLib.MpvFormat.MPV_FORMAT_DOUBLE)
        MPVLib.observeProperty("duration", MPVLib.MpvFormat.MPV_FORMAT_DOUBLE)
        MPVLib.observeProperty("pause", MPVLib.MpvFormat.MPV_FORMAT_FLAG)
        MPVLib.observeProperty("eof-reached", MPVLib.MpvFormat.MPV_FORMAT_FLAG)
        MPVLib.observeProperty("volume", MPVLib.MpvFormat.MPV_FORMAT_INT64)
        MPVLib.observeProperty("mute", MPVLib.MpvFormat.MPV_FORMAT_FLAG)
        MPVLib.observeProperty("media-title", MPVLib.MpvFormat.MPV_FORMAT_STRING)
        MPVLib.observeProperty("track-list", MPVLib.MpvFormat.MPV_FORMAT_NODE)
    }

    fun stop() {
        if (!instanceState.nativeInstanceCreated || !instanceState.nativeInstanceAlive) return
        try {
            MPVLib.command(arrayOf("stop"))
        } catch (e: Throwable) {
            Log.w(TAG, "stop failed: ${e.message}")
        }
    }

    fun forceRecreate() {
        Log.w(TAG, "forceRecreate: resetting mpv state (stop + playlist-clear, no quit)")
        instanceState.forceRecreatePending = true
        try {
            MPVLib.command(arrayOf("stop"))
            MPVLib.command(arrayOf("playlist-clear"))
        } catch (e: Throwable) {
            Log.w(TAG, "forceRecreate: reset commands failed: ${e.message}")
        }
    }

    fun markInstanceDead() {
        Log.e(TAG, "markInstanceDead: mpv core shutdown detected, marking core as dead (in-process unrecoverable)")
        instanceState.nativeInstanceCreated = false
        instanceState.nativeInstanceAlive = false
        // 关键：native 句柄仍然存在（keep-alive 策略下从未 destroy），但核心已 terminate。
        // 必须置 nativeCoreDead，禁止后续 initialize() 在死句柄上调用 init()（会 native 崩溃）。
        instanceState.nativeCoreDead = true
    }
}