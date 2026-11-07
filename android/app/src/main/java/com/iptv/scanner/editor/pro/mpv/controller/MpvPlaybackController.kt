package com.iptv.scanner.editor.pro.mpv.controller

import android.util.Log
import `is`.xyz.mpv.MPVLib
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.mpv.MpvProtocolConstants

/**
 * 播放控制子控制器：playFile/stop/pause/seek/volume/mute/speed/音轨字幕切换/章节/AB循环/逐帧。
 *
 * 持有频道切换状态（needPreStop/switchingChannel/pendingLoadUrl/loadingUrl/lastLoadedUrl/pendingEndFileError），
 * 这些字段为 public var 供 MpvController 门面的 event() 事件观察者访问。
 */
class MpvPlaybackController(private val host: MpvControllerHost) {

    @Volatile
    var needPreStop = false
        private set

    @Volatile
    var switchingChannel = false
        private set

    @Volatile
    var pendingLoadUrl: String = ""
        private set

    @Volatile
    var loadingUrl: String = ""
        private set

    var lastLoadedUrl: String = ""
        private set

    @Volatile
    var pendingEndFileError: Runnable? = null

    fun playFile(url: String) {
        // 核心已终止（shutdown 后无法重建）：不再静默 return，
        // 交给上层向界面暴露错误并降级到备用内核
        if (host.isCoreDead()) {
            Log.e(TAG, "playFile: mpv core is dead, cannot load $url")
            host.notifyPlaybackUnavailable()
            return
        }
        pendingEndFileError?.let { host.getMpvView()?.asView()?.removeCallbacks(it) }
        pendingEndFileError = null
        loadingUrl = url
        pendingLoadUrl = url
        switchingChannel = true
        host.postOnUiThread {
            if (pendingLoadUrl != url) {
                Log.i(TAG, "playFile: skipped, superseded (pending=$pendingLoadUrl, this=$url)")
                return@postOnUiThread
            }
            val doLoadFile: () -> Unit = {
                setupProtocolOptions(url)
                try {
                    Log.i(TAG, "playFile: loadfile $url (surface=${host.getMpvView()?.isSurfaceValid})")
                    MPVLib.command(arrayOf("loadfile", url))
                    MPVLib.setPropertyBoolean("pause", false)
                } catch (e: Throwable) {
                    Log.w(TAG, "playFile: loadfile failed: ${e.message}")
                }
            }
            if (needPreStop) {
                try {
                    MPVLib.command(arrayOf("stop"))
                    MPVLib.command(arrayOf("playlist-clear"))
                    Log.i(TAG, "playFile: pre-stop + playlist-clear (recovering from error)")
                } catch (e: Throwable) {
                    Log.w(TAG, "playFile: pre-stop failed: ${e.message}")
                }
                needPreStop = false
                doLoadFile()
                // 必须显式返回：否则落到函数末尾再次执行 doLoadFile()，
                // 向 mpv 核心连发两条 loadfile，可能触发 native 崩溃
                return@postOnUiThread
            } else if (host.isFileLoaded()) {
                MPVLib.setPropertyString("demuxer-max-bytes", "16MiB")
                Log.i(TAG, "playFile: loadfile replace (channel switch)")
                doLoadFile()
                return@postOnUiThread
            }
            doLoadFile()
        }
    }

    fun markNeedPreStop() {
        needPreStop = true
        Log.i(TAG, "markNeedPreStop: next playFile will pre-stop before loadfile")
    }

    fun getPath(): String {
        return try {
            MPVLib.getPropertyString("path") ?: ""
        } catch (e: Throwable) {
            Log.w(TAG, "getPath failed: ${e.message}")
            ""
        }
    }

    fun stop() {
        // 停止播放时清理切换标志，否则下次换台失败时错误会被永久抑制
        clearSwitchingState()
        host.postOnUiThread {
            host.getMpvView()?.stop()
        }
    }

    fun togglePause() = host.postOnUiThread { MPVLib.command(arrayOf("cycle", "pause")) }
    fun setPause(p: Boolean) = host.postOnUiThread { MPVLib.setPropertyBoolean("pause", p) }

    fun seekTo(seconds: Double) =
        host.postOnUiThread { MPVLib.setPropertyDouble("time-pos", seconds) }

    fun seekRelative(seconds: Double) =
        host.postOnUiThread { MPVLib.command(arrayOf("seek", seconds.toString(), "relative")) }

    fun seekAbsolute(seconds: Double) =
        host.postOnUiThread { MPVLib.command(arrayOf("seek", seconds.toString(), "absolute")) }

    fun setVolume(v: Int) =
        host.postOnUiThread { MPVLib.setPropertyInt("volume", v.coerceIn(0, 130)) }

    fun adjustVolume(delta: Int) {
        val cur = host.getCurrentVolume()
        setVolume(cur + delta)
    }

    fun toggleMute() = host.postOnUiThread { MPVLib.command(arrayOf("cycle", "mute")) }
    fun setMute(m: Boolean) = host.postOnUiThread { MPVLib.setPropertyBoolean("mute", m) }

    fun setSpeed(s: Double) =
        host.postOnUiThread { MPVLib.setPropertyDouble("speed", s.coerceIn(0.01, 100.0)) }

    fun cycleAudio() = host.postOnUiThread { MPVLib.command(arrayOf("cycle", "audio")) }
    fun cycleSub() = host.postOnUiThread { MPVLib.command(arrayOf("cycle", "sub")) }

    fun setAudioTrack(id: Int) = host.postOnUiThread {
        try {
            MPVLib.setPropertyInt("aid", id)
        } catch (e: Exception) {
            MPVLib.command(arrayOf("set", "aid", id.toString()))
        }
    }

    fun setSubTrack(id: Int) = host.postOnUiThread {
        try {
            MPVLib.setPropertyInt("sid", id)
        } catch (e: Exception) {
            MPVLib.command(arrayOf("set", "sid", id.toString()))
        }
    }

    /**
     * 加载外挂字幕。
     * @return false 表示核心不可用或当前没有加载文件，此时 sub-add 不会生效，调用方不得谎报成功
     */
    fun addSubtitleFile(path: String): Boolean {
        if (host.isCoreDead()) {
            Log.w(TAG, "addSubtitleFile: mpv core is dead, skip sub-add $path")
            return false
        }
        if (!host.isFileLoaded()) {
            Log.w(TAG, "addSubtitleFile: no file loaded, skip sub-add $path")
            return false
        }
        host.postOnUiThread { MPVLib.command(arrayOf("sub-add", path, "select")) }
        return true
    }

    fun setChapter(idx: Int): Boolean {
        host.postOnUiThread {
            try {
                MPVLib.setPropertyInt("chapter", idx)
            } catch (e: Exception) {
                MPVLib.command(arrayOf("set", "chapter", idx.toString()))
            }
        }
        return true
    }

    fun chapterNext(): Boolean {
        host.postOnUiThread { MPVLib.command(arrayOf("add", "chapter", "1")) }
        return true
    }

    fun chapterPrev(): Boolean {
        host.postOnUiThread { MPVLib.command(arrayOf("add", "chapter", "-1")) }
        return true
    }

    fun setAbLoopA(): Boolean {
        host.postOnUiThread {
            val t = MPVLib.getPropertyDouble("time-pos") ?: 0.0
            MPVLib.setPropertyDouble("ab-loop-a", t)
        }
        return true
    }

    fun setAbLoopB(): Boolean {
        host.postOnUiThread {
            val t = MPVLib.getPropertyDouble("time-pos") ?: 0.0
            MPVLib.setPropertyDouble("ab-loop-b", t)
        }
        return true
    }

    fun clearAbLoop() {
        host.postOnUiThread {
            MPVLib.setPropertyString("ab-loop-a", "no")
            MPVLib.setPropertyString("ab-loop-b", "no")
        }
    }

    fun setLoopFile(mode: String): Boolean {
        host.postOnUiThread { MPVLib.setPropertyString("loop-file", mode) }
        return true
    }

    fun setLoopPlaylist(mode: String): Boolean {
        host.postOnUiThread { MPVLib.setPropertyString("loop-playlist", mode) }
        return true
    }

    fun frameStep(): Boolean {
        host.postOnUiThread { MPVLib.command(arrayOf("frame-step")) }
        return true
    }

    fun frameBackStep(): Boolean {
        host.postOnUiThread { MPVLib.command(arrayOf("frame-back-step")) }
        return true
    }

    fun showOsd(text: String, durationMs: Int) {
        host.postOnUiThread { MPVLib.command(arrayOf("show-text", text, durationMs.toString())) }
    }

    /** 由 event() 在 FILE_LOADED 事件中调用，更新 lastLoadedUrl */
    fun onFileLoaded(url: String) {
        lastLoadedUrl = url
        loadingUrl = ""
        switchingChannel = false
    }

    /** 由 event() 在 START_FILE 事件中调用 */
    fun onStartFile() {
        loadingUrl = pendingLoadUrl
    }

    /** 由 event() 在 END_FILE 事件中调用 */
    fun onEndFile() {
        loadingUrl = ""
    }

    /**
     * 清理换台/加载态标志。
     *
     * 换台失败时 END_FILE 不会走到 FILE_LOADED，如果不显式清理，
     * switchingChannel 会永久为 true，导致后续所有错误回调被当作
     * 「换台中」静默吞掉，只能等超时换源。
     */
    fun clearSwitchingState() {
        switchingChannel = false
        loadingUrl = ""
        pendingLoadUrl = ""
    }

    private fun setupProtocolOptions(url: String) {
        if (url.isEmpty()) return
        val u = url.lowercase()
        val isNetwork = u.startsWith("http://") || u.startsWith("https://") ||
                u.startsWith("rtsp://") || u.startsWith("rtp://") || u.startsWith("udp://") ||
                ".m3u8" in u
        if (!isNetwork) return

        val isFcc = "?fcc=" in u
        try {
            if (!u.startsWith("rtsp://")) {
                MPVLib.setPropertyString("user-agent", MpvProtocolConstants.USER_AGENT)
            }
            if (isFcc) {
                MPVLib.setPropertyString("stream-lavf-o", "verify=1,rw_timeout=${MpvProtocolConstants.RW_TIMEOUT_MS}")
                MPVLib.setPropertyString("demuxer-read-timeout", "0")
                MPVLib.setPropertyString("source-timeout", "0")
                MPVLib.setPropertyString("network-timeout", "0")
                Log.i(TAG, "FCC stream: stream-lavf-o rw_timeout=30s, demuxer-read-timeout=0, source-timeout=0")
            } else {
                MPVLib.setPropertyString("stream-lavf-o", "verify=1")
                MPVLib.setPropertyString("demuxer-read-timeout", "5")
                MPVLib.setPropertyString("source-timeout", "8")
                MPVLib.setPropertyString("network-timeout", "8")
            }
            when {
                ".m3u8" in u || "format=hls" in u -> {
                    MPVLib.setPropertyString("demuxer-lavf-format", "")
                    MPVLib.setPropertyString("cache", "yes")
                    MPVLib.setPropertyString("force-seekable", "yes")
                    MPVLib.setPropertyString("demuxer-readahead-secs", "120")
                    MPVLib.setPropertyString("cache-secs", "3600")
                    MPVLib.setPropertyString("prefetch-playlist", "yes")
                    Log.i(TAG, "HLS options: readahead=120s, cache-secs=3600, prefetch=yes")
                }
                u.startsWith("rtsp://") -> {
                    val transport = UserPrefs.getInstance().getRtspTransport()
                    MPVLib.setPropertyString("rtsp-transport", transport)
                    MPVLib.setPropertyString("user-agent", MpvProtocolConstants.FCC_USER_AGENT)
                    MPVLib.setPropertyString("cache", "yes")
                    MPVLib.setPropertyString("demuxer-lavf-format", "")
                    MPVLib.setPropertyString("cache-secs", "60")
                    if (transport == "udp") {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "500000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "1")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "5")
                        MPVLib.setPropertyString("force-seekable", "no")
                        Log.i(TAG, "RTSP-UDP options: probesize=500K, readahead=5s")
                    } else {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "5000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "5")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "10")
                        Log.i(TAG, "RTSP-TCP options: probesize=5M, readahead=10s")
                    }
                }
                u.endsWith(".ts") || u.startsWith("udp://") || "/rtp/" in u || u.startsWith("rtp://") -> {
                    MPVLib.setPropertyString("demuxer", "lavf")
                    MPVLib.setPropertyString("demuxer-lavf-format", "mpegts")
                    MPVLib.setPropertyString("demuxer-lavf-buffersize", "128000")
                    if (isFcc) {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "2000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "1")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "10")
                        MPVLib.setPropertyString("cache-secs", "60")
                    } else {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "2000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "1")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "15")
                        MPVLib.setPropertyString("cache-secs", "120")
                    }
                    MPVLib.setPropertyString("cache", "yes")
                    MPVLib.setPropertyString("force-seekable", "yes")
                    MPVLib.setPropertyString("demuxer-seekable-cache", "yes")
                    Log.i(TAG, "TS/UDP/RTP options: probesize=${if (isFcc) "2M" else "2M"}, readahead=${if (isFcc) "10s" else "15s"}, fcc=$isFcc")
                }
                else -> {
                    MPVLib.setPropertyString("demuxer-lavf-format", "")
                    if (isFcc) {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "2000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "1")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "10")
                        MPVLib.setPropertyString("cache-secs", "60")
                    } else {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "5000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "5")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "15")
                        MPVLib.setPropertyString("cache-secs", "120")
                    }
                    MPVLib.setPropertyString("cache", "yes")
                    MPVLib.setPropertyString("force-seekable", "yes")
                    Log.i(TAG, "Generic stream options: probesize=${if (isFcc) "2M" else "5M"}, readahead=${if (isFcc) "10s" else "15s"}, fcc=$isFcc")
                }
            }
        } catch (e: Throwable) {
            Log.w(TAG, "setupProtocolOptions failed: ${e.message}")
        }
    }

    companion object {
        private const val TAG = "MpvController"
    }
}