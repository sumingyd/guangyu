package com.iptv.scanner.editor.pro.player

import kotlinx.coroutines.flow.StateFlow

/**
 * 播放器类型枚举。
 *
 * 两种播放器内核可切换，每种内核都支持硬解/软解：
 * - [MPV]：mpv (libmpv)，通过 JNI 调用，功能最完整（EQ/AB循环/逐帧/章节/截图/HDR等）
 *   硬解：hwdec=auto-copy/auto，软解：hwdec=no
 * - [EXO]：ExoPlayer，Google Media3 引擎，HLS/DASH/RTSP 兼容性好
 *   硬解：MediaCodec 硬件编解码器（GPU 加速），软解：MediaCodec 软件编解码器（如 OMX.google.*）
 */
enum class PlayerType(val displayName: String, val description: String) {
    MPV("mpv", "功能最完整（EQ/AB循环/逐帧/截图/HDR）"),
    EXO("ExoPlayer", "Google ExoPlayer（HLS/DASH/RTSP 兼容性好）");

    companion object {
        fun fromName(name: String?): PlayerType {
            // 兼容旧版：SYSTEM 映射为 EXO（软解通过 setHardwareDecode 控制）
            if (name == "SYSTEM") return EXO
            return entries.firstOrNull { it.name == name } ?: MPV
        }
    }
}

/**
 * 播放器能力声明。
 *
 * UI 层根据 [Player.capabilities] 决定是否显示高级功能面板。
 * MPV 全部为 true。
 */
data class PlayerCapabilities(
    val supportsBrightness: Boolean = false,
    val supportsContrast: Boolean = false,
    val supportsSaturation: Boolean = false,
    val supportsHue: Boolean = false,
    val supportsGamma: Boolean = false,
    val supportsVideoRotate: Boolean = false,
    val supportsVideoFlip: Boolean = false,
    val supportsVideoCrop: Boolean = false,
    val supportsAudioDelay: Boolean = false,
    val supportsAudioEq: Boolean = false,
    val supportsSubDelay: Boolean = false,
    val supportsSubScale: Boolean = false,
    val supportsSubPos: Boolean = false,
    val supportsAbLoop: Boolean = false,
    val supportsLoopFile: Boolean = false,
    val supportsFrameStep: Boolean = false,
    val supportsChapters: Boolean = false,
    val supportsScreenshot: Boolean = false,
    val supportsOsd: Boolean = false,
    val supportsAddSubtitleFile: Boolean = false,
    val supportsSpeedControl: Boolean = true,
    val supportsTrackList: Boolean = false,
    /** 是否支持运行时切换硬件解码/软件解码 */
    val supportsHardwareDecodeSwitch: Boolean = false
) {
    /** 是否支持任何画面调整（亮度/对比度/饱和度/色调/Gamma） */
    val supportsVideoEq: Boolean
        get() = supportsBrightness || supportsContrast || supportsSaturation ||
                supportsHue || supportsGamma
}

/**
 * 播放器抽象接口。
 *
 * 仅 MPV 一种实现，保留接口以维持 UI 层与播放器层的解耦。
 *
 * @see MpvController 完整实现
 */
interface BasicPlayer {
    val timePos: StateFlow<Double>
    val duration: StateFlow<Double>
    val paused: StateFlow<Boolean>
    val volume: StateFlow<Int>
    val muted: StateFlow<Boolean>
    val mediaTitle: StateFlow<String>
    val trackListJson: StateFlow<String>

    /** 播放器内核是否已不可用（mpv 核心终止等，需上层提示并降级到其他内核） */
    fun isCoreDead(): Boolean = false
    val eofReached: StateFlow<Boolean>
    val fileLoaded: StateFlow<Boolean>
    val videoWidth: StateFlow<Int>
    val videoHeight: StateFlow<Int>
    val speed: StateFlow<Double>
    val capabilities: PlayerCapabilities
    val playerType: PlayerType

    fun attachView(view: Any)
    fun detach()
    fun getAudioSessionId(): Int = 0
    fun playFile(url: String)
    fun stop()
    fun refreshSurface()
    fun togglePause()
    fun setPause(p: Boolean)
    fun seekTo(seconds: Double)
    fun seekRelative(seconds: Double)
    fun seekAbsolute(seconds: Double)
    fun setVolume(v: Int)
    fun adjustVolume(delta: Int)
    fun toggleMute()
    fun setMute(m: Boolean)
    fun setSpeed(s: Double)
    fun cycleAudio()
    fun cycleSub()
    fun setAudioTrack(id: Int)
    fun setSubTrack(id: Int)
    /**
     * 加载外挂字幕文件。
     * @return true 表示命令已成功提交给播放器；false 表示播放器不可用/未在播放，调用方不得提示「已加载」
     */
    fun addSubtitleFile(path: String): Boolean
    fun setSubVisibility(v: Boolean)
    fun toggleSubVisibility()
    fun setSubDelay(delaySec: Double)
    fun adjustSubDelay(delta: Double)
    fun setSubScale(scale: Double)
    fun setSubPos(pos: Int)
    fun getMediaInfo(): Map<String, String?> = emptyMap()
    fun setHardwareDecode(enabled: Boolean): Boolean = false
    fun isHardwareDecodeEnabled(): Boolean = true
    fun savePlaybackState(): Pair<String, Double>? = null
    fun restorePlaybackState(url: String, timePosSec: Double) {}
}

interface VideoEqPlayer {
    fun setBrightness(v: Int): Boolean = false
    fun setContrast(v: Int): Boolean = false
    fun setSaturation(v: Int): Boolean = false
    fun setHue(v: Int): Boolean = false
    fun setGamma(v: Int): Boolean = false
    fun setVideoRotate(degree: Int): Boolean = false
    fun setVideoFlip(mode: String): Boolean = false
    fun setVideoCrop(x: Int, y: Int, w: Int, h: Int): Boolean = false
    fun clearVideoCrop() {}
    fun clearAllVideoFilters() {}
    fun setVideoStereoMode(mode: String): Boolean = false
    fun getVideoStereoMode(): String? = null
    fun set360View(yaw: Double, pitch: Double, roll: Double, projection: String): Boolean = false
    fun clear360Filter() {}
    fun setMotionCompensation(strength: String, targetFps: Int): Boolean = false
    fun clearMotionCompensation() {}
    fun setSuperResolution(scaleAlgo: String, detailEnhance: Int): Boolean = false
    fun clearSuperResolution() {}
    fun setUserShader(preset: String): Boolean = false
    fun clearUserShader() {}
}

interface AudioEqPlayer {
    fun setAudioDelay(delaySec: Double): Boolean = false
    fun adjustAudioDelay(delta: Double): Boolean = false
    fun setAudioEq(gains: List<Float>): Boolean = false
    fun resetAudioEq(): Boolean = false
    fun setAudioPitch(pitch: Double): Boolean = false
    fun setChannelVolumes(volumes: Map<String, Float>): Boolean = false
    fun getAudioChannelInfo(): Map<String, Any> = emptyMap()
    fun startChannelMonitor(): Boolean = false
    fun stopChannelMonitor() {}
    fun getChannelLevels(): Map<Int, Float> = emptyMap()
}

interface AdvancedPlayer {
    val currentChapter: StateFlow<Int>
    val chapterCount: StateFlow<Int>
    fun screenshotToFile(path: String, mode: String = "video"): Boolean = false
    fun setAbLoopA(): Boolean = false
    fun setAbLoopB(): Boolean = false
    fun clearAbLoop() {}
    fun setLoopFile(mode: String): Boolean = false
    fun setLoopPlaylist(mode: String): Boolean = false
    fun frameStep(): Boolean = false
    fun frameBackStep(): Boolean = false
    fun setChapter(idx: Int): Boolean = false
    fun chapterNext(): Boolean = false
    fun chapterPrev(): Boolean = false
    fun showOsd(text: String, durationMs: Int = 3000) {}
}

interface MpvSpecificPlayer {
    fun getPropertyString(name: String): String? = null
    fun getPropertyInt(name: String): Int? = null
    fun getPropertyDouble(name: String): Double? = null
    fun getPropertyBoolean(name: String): Boolean? = null
    fun setPropertyString(name: String, value: String) {}
    fun setPropertyInt(name: String, value: Int) {}
    fun setPropertyDouble(name: String, value: Double) {}
    fun setPropertyBoolean(name: String, value: Boolean) {}
    fun command(args: Array<String>) {}
}

interface Player : BasicPlayer, VideoEqPlayer, AudioEqPlayer, AdvancedPlayer, MpvSpecificPlayer
