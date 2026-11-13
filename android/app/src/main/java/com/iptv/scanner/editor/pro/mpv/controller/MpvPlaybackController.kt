package com.iptv.scanner.editor.pro.mpv.controller

import android.util.Log
import `is`.xyz.mpv.MPVLib
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.mpv.MpvProtocolConstants
import com.iptv.scanner.editor.pro.mpv.SwitchPerf
import com.iptv.scanner.editor.pro.player.FccHelper

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

    /**
     * 换台代次：每次 playFile 自增。
     * END_FILE 的延迟检查（300ms）与 VO 健康检查都绑定代次，
     * 代次变化说明已经开始新一次换台，旧检查必须作废。
     */
    @Volatile
    var switchGeneration: Long = 0
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
        switchGeneration++
        clearPendingEndFileError()
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
                MPVLib.setPropertyString("demuxer-max-bytes", MpvProtocolConstants.DEMUXER_MAX_BYTES_DEFAULT)
                Log.i(TAG, "playFile: loadfile replace (channel switch, demuxer-max-bytes=${MpvProtocolConstants.DEMUXER_MAX_BYTES_DEFAULT})")
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
        clearPendingLoadUrl()
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
        // 本次换台已落地：待加载 URL 的使命结束，避免残留值被后续 START_FILE 误用
        pendingLoadUrl = ""
        // FILE_LOADED 已到：取消 300ms 断流误报检查
        clearPendingEndFileError()
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
     * 清理换台/加载态标志（不清 pendingLoadUrl）。
     *
     * 换台失败时 END_FILE 不会走到 FILE_LOADED，如果不显式清理，
     * switchingChannel 会永久为 true，导致后续所有错误回调被当作
     * 「换台中」静默吞掉，只能等超时换源。
     *
     * 注意：pendingLoadUrl 必须保留到 START_FILE 之后，
     * 否则 onStartFile 拿不到真实 URL，loadingUrl 永远为空，
     * END_FILE 归属判断会退化回全局 path。
     */
    fun clearSwitchingState() {
        switchingChannel = false
        loadingUrl = ""
    }

    /** 显式丢弃待加载 URL（用户 stop / 换台失败确认后调用） */
    fun clearPendingLoadUrl() {
        pendingLoadUrl = ""
    }

    /** 取消 300ms 断流误报检查（新换台开始 / FILE_LOADED 到达时调用） */
    fun clearPendingEndFileError() {
        pendingEndFileError?.let { host.getMpvView()?.asView()?.removeCallbacks(it) }
        pendingEndFileError = null
    }

    /**
     * 已经用完整探测预算重试过的 URL（同一 URL 只回退一次）。
     * setupProtocolOptions 按 URL 比对，避免换台时把回退预算误用到别的频道。
     */
    @Volatile
    private var fullProbeBudgetUrl = ""

    /**
     * 直播探测预算回退：1MB / 0.5s 探测失败或识别不出编码时，
     * 用原来的 5MB / 5s 重新加载一次。同一 URL 只回退一次，避免死循环。
     *
     * @return true 表示已经发起重载，调用方不要再走错误/降级流程
     */
    fun retryWithFullProbeBudget(url: String): Boolean {
        if (url.isEmpty()) return false
        if (!isLiveProbeBudgetUrl(url)) return false
        if (fullProbeBudgetUrl == url) return false
        fullProbeBudgetUrl = url
        Log.w(TAG, "probe budget: retry with full 5M/5s url=$url")
        SwitchPerf.markAbort("probe-fallback-reload")
        playFile(url)
        return true
    }

    /**
     * 换台开始（T0）调用：清掉「这一路已经用完整预算重探过」的记忆。
     *
     * 原来 fullProbeBudgetUrl 只在同一 URL 上永久生效，4K↔1080 来回切回同一个
     * 4K 频道时，第二轮就不会再重探，只能停在“只有声音没有画面”。
     */
    fun resetProbeBudgetForSwitch() {
        fullProbeBudgetUrl = ""
    }

    /** 是否是使用 1MB/0.5s 探测预算的直播流（TS / RTSP / RTP / FCC），排除 VOD/HLS */
    private fun isLiveProbeBudgetUrl(url: String): Boolean {
        val u = url.lowercase()
        if (".m3u8" in u || "format=hls" in u) return false
        if (isVodLikeUrl(u)) return false
        val path = u.substringBefore('?')
        return u.startsWith("rtsp://") || u.startsWith("rtp://") || u.startsWith("udp://") ||
            path.endsWith(".ts") || "/rtp/" in u
    }

    private fun setupProtocolOptions(url: String) {
        if (url.isEmpty()) return
        val u = url.lowercase()
        val isNetwork = u.startsWith("http://") || u.startsWith("https://") ||
                u.startsWith("rtsp://") || u.startsWith("rtp://") || u.startsWith("udp://") ||
                u.startsWith("rtmp://") || ".m3u8" in u
        if (!isNetwork) {
            // 本地文件不参与网络协议调优，但必须复位上一频道（可能是 FCC/TS 流）留下的
            // demuxer 与零超时参数，否则会继承 mpegts 强制解封装或永不超时的行为
            resetProtocolOptions()
            return
        }

        // FCC 判定统一走 FccHelper.resolve：调优与代理通知共用同一结果。
        // 不允许这里再单独做字符串匹配，否则会出现“调优生效但通知静默”的分叉。
        val fccPlan = FccHelper.resolve(url)
        // 回看/时移是单播点播流，不得套用 FCC 的零超时与探针参数
        val isVod = isVodLikeUrl(u)
        val isFcc = fccPlan.isFcc && !isVod
        if (fccPlan.isFcc && isVod) {
            Log.i(TAG, "setupProtocolOptions: VOD/catchup 流，跳过 FCC 调优 url=$url")
        }
        try {
            // 直播探测预算：常规 1MB/0.5s；该 URL 探测失败后的回退轮使用 5MB/5s
            val fullProbe = url == fullProbeBudgetUrl
            if (!u.startsWith("rtsp://")) {
                MPVLib.setPropertyString("user-agent", MpvProtocolConstants.USER_AGENT)
            }
            if (isFcc) {
                MPVLib.setPropertyString("stream-lavf-o", "verify=1,rw_timeout=${MpvProtocolConstants.RW_TIMEOUT_US}")
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
                        MPVLib.setPropertyString("demuxer-lavf-probesize", if (fullProbe) "5000000" else "1000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", if (fullProbe) "5" else "0.5")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "5")
                        MPVLib.setPropertyString("force-seekable", "no")
                        Log.i(TAG, "RTSP-UDP options: probesize=${if (fullProbe) "5M" else "1M"}, " +
                            "analyzeduration=${if (fullProbe) "5s" else "0.5s"}, readahead=5s")
                    } else {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", if (fullProbe) "5000000" else "1000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", if (fullProbe) "5" else "0.5")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "4")
                        Log.i(TAG, "RTSP-TCP options: probesize=${if (fullProbe) "5M" else "1M"}, " +
                            "analyzeduration=${if (fullProbe) "5s" else "0.5s"}, readahead=4s")
                    }
                }
                u.endsWith(".ts") || u.startsWith("udp://") || "/rtp/" in u || u.startsWith("rtp://") -> {
                    MPVLib.setPropertyString("demuxer", "lavf")
                    MPVLib.setPropertyString("demuxer-lavf-format", "mpegts")
                    MPVLib.setPropertyString("demuxer-lavf-buffersize", "128000")
                    MPVLib.setPropertyString("demuxer-lavf-probesize", if (fullProbe) "5000000" else "1000000")
                    MPVLib.setPropertyString("demuxer-lavf-analyzeduration", if (fullProbe) "5" else "0.5")
                    // FCC 流缓冲更短，减少换台后首帧等待
                    MPVLib.setPropertyString("demuxer-readahead-secs", if (isFcc) "4" else "15")
                    MPVLib.setPropertyString("cache-secs", if (isFcc) "60" else "120")
                    MPVLib.setPropertyString("cache", "yes")
                    MPVLib.setPropertyString("force-seekable", "yes")
                    MPVLib.setPropertyString("demuxer-seekable-cache", "yes")
                    Log.i(TAG, "TS/UDP/RTP options: probesize=${if (fullProbe) "5M" else "1M"}, " +
                        "analyzeduration=${if (fullProbe) "5s" else "0.5s"}, readahead=${if (isFcc) 4 else 15}s, fcc=$isFcc")
                }
                else -> {
                    MPVLib.setPropertyString("demuxer-lavf-format", "")
                    if (isFcc) {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "1000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "0.5")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "4")
                        MPVLib.setPropertyString("cache-secs", "60")
                    } else {
                        MPVLib.setPropertyString("demuxer-lavf-probesize", "5000000")
                        MPVLib.setPropertyString("demuxer-lavf-analyzeduration", "5")
                        MPVLib.setPropertyString("demuxer-readahead-secs", "15")
                        MPVLib.setPropertyString("cache-secs", "120")
                    }
                    MPVLib.setPropertyString("cache", "yes")
                    MPVLib.setPropertyString("force-seekable", "yes")
                    Log.i(TAG, "Generic stream options: probesize=${if (isFcc) "1M" else "5M"}, analyzeduration=${if (isFcc) "0.5s" else "5s"}, readahead=${if (isFcc) "10s" else "15s"}, fcc=$isFcc")
                }
            }
        } catch (e: Throwable) {
            Log.w(TAG, "setupProtocolOptions failed: ${e.message}")
        }
    }

    /**
     * 回看 / 时移 / 点播类 URL 判定，与 PC 端 is_vod 关键字保持一致。
     * 这类流是单播点播，不能套用 FCC 的零超时参数。
     */
    private fun isVodLikeUrl(lowerUrl: String): Boolean =
        "playseek" in lowerUrl || "starttime=" in lowerUrl || "endtime=" in lowerUrl ||
                "timeshift" in lowerUrl || "catchup" in lowerUrl || "playback" in lowerUrl

    /**
     * 复位 [setupProtocolOptions] 会改写的协议/超时参数，避免本地文件或
     * 新协议流继承上一频道的 demuxer 与零超时设置。
     */
    private fun resetProtocolOptions() {
        try {
            MPVLib.setPropertyString("stream-lavf-o", "verify=1")
            MPVLib.setPropertyString("demuxer-read-timeout", "5")
            MPVLib.setPropertyString("source-timeout", "8")
            MPVLib.setPropertyString("network-timeout", "8")
            MPVLib.setPropertyString("demuxer", "auto")
            MPVLib.setPropertyString("demuxer-lavf-format", "")
        } catch (e: Throwable) {
            Log.w(TAG, "resetProtocolOptions failed: ${e.message}")
        }
    }

    companion object {
        private const val TAG = "MpvController"
    }
}