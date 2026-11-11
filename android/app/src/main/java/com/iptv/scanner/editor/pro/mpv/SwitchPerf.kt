package com.iptv.scanner.editor.pro.mpv

import android.os.SystemClock
import android.util.Log

/**
 * 换台耗时打点（仅日志，不影响行为）。
 *
 * 一次切台的链路：
 * T0 按键进入 playChannel
 * T1 FCC JOIN 完成（组播预加入）
 * T2 调用 loadfile（带上当时的 vo/hwdec）
 * T3 START_FILE（mpv 开始打开新流）
 * T4 FILE_LOADED（解复用/探测完成）
 * T5 首帧出画（estimated-frame-number > 0）
 *
 * 用 `adb logcat -s ChannelSwitchPerf` 即可拿到单次切台的各段耗时。
 */
object SwitchPerf {
    private const val TAG = "ChannelSwitchPerf"

    @Volatile
    private var requestAt = 0L

    @Volatile
    private var channelName = ""

    fun markRequest(name: String, url: String) {
        requestAt = SystemClock.elapsedRealtime()
        channelName = name
        Log.i(TAG, "T0 keypress: $name url=$url")
    }

    fun markFccJoined() = stage("T1 fcc-join")

    fun markBeforeLoad(vo: String, hwdec: String) = stage("T2 loadfile vo=$vo hwdec=$hwdec")

    fun markStartFile() = stage("T3 START_FILE")

    fun markFileLoaded() = stage("T4 FILE_LOADED")

    fun markFirstFrame() {
        stage("T5 first-frame")
        requestAt = 0L
    }

    fun markAbort(reason: String) {
        stage("abort $reason")
        requestAt = 0L
    }

    private fun stage(text: String) {
        val t0 = requestAt
        if (t0 == 0L) {
            Log.i(TAG, "$text (no active switch request)")
            return
        }
        Log.i(TAG, "$text +${SystemClock.elapsedRealtime() - t0}ms channel=$channelName")
    }
}
