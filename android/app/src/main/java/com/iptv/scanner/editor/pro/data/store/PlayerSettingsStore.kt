package com.iptv.scanner.editor.pro.data.store

import android.app.UiModeManager
import android.content.Context
import android.content.res.Configuration
import android.content.SharedPreferences
import com.iptv.scanner.editor.pro.data.ChannelPlayerSettings
import com.iptv.scanner.editor.pro.data.SpeedConfig
import org.json.JSONObject

/**
 * 播放器设置域存储：vo/hwdec/HDR/RTSP/反交错/播放器类型/超时换源/断线重连/画面锁定/倍速/频道级设置。
 *
 * 与 MPVView.DEFAULT_VO / DEFAULT_HWDEC 默认值对齐（字符串常量避免反向依赖 mpv 层）。
 */
class PlayerSettingsStore(
    private val prefs: SharedPreferences,
    private val appContext: Context? = null
) {

    // -----------------------------------------------------------------
    // vo / hwdec
    // -----------------------------------------------------------------

    /** 获取持久化的 video output，未持久化时按设备类型给默认值 */
    fun getVo(): String {
        val vo = requestedVo()
        // 软解（含崩溃黑名单）时 mediacodec_embed 没有解码器直渲，必须退回 gpu
        if (vo == VO_MEDIACODEC_EMBED && getHwdec() == HWDEC_SOFTWARE) return DEFAULT_VO_VALUE
        return vo
    }

    /** 未经软解兜底的 vo：只反映用户选择 / 设备默认 / 自动回退 */
    private fun requestedVo(): String {
        val saved = prefs.getString(KEY_VO, null)?.takeIf { it.isNotEmpty() }
        if (saved != null) {
            // 电视/盒子硬解只允许 MediaCodec 直写 Surface：gpu + mediacodec（AImageReader）
            // 在 arm32 OMX 设备上会起播失败，这里统一换成 mediacodec_embed。
            if (isArm32Tv() && saved == DEFAULT_VO_VALUE && resolveRequestedHwdec() == HWDEC_MEDIACODEC) {
                return VO_MEDIACODEC_EMBED
            }
            return saved
        }
        // 自动回退过：本次（以及后续启动）固定 gpu，直到用户在设置页重新选择
        if (isVoAutoFallback()) return DEFAULT_VO_VALUE
        return defaultVo()
    }

    fun setVo(vo: String) {
        // 用户显式选择即重置自动回退标记（回退只是默认值的兜底，不能覆盖用户手选）
        prefs.edit().putString(KEY_VO, vo).putBoolean(KEY_VO_AUTO_FALLBACK, false).apply()
    }

    /** 用户是否在设置页/频道级设置里显式选择过 vo（未选择时走 ABI 默认值） */
    fun hasExplicitVo(): Boolean = prefs.contains(KEY_VO)

    /**
     * mediacodec_embed 默认路径是否已因起播失败自动回退到 gpu。
     * 回退后写盘，避免每次启动都重试同一条在部分设备上黑屏的渲染路径。
     */
    fun isVoAutoFallback(): Boolean = prefs.getBoolean(KEY_VO_AUTO_FALLBACK, false)

    fun setVoAutoFallback(fallback: Boolean) {
        prefs.edit().putBoolean(KEY_VO_AUTO_FALLBACK, fallback).apply()
    }

    /**
     * 获取持久化的 hwdec 模式，未持久化时按设备类型给默认值。
     *
     * 崩溃黑名单按 vo+hwdec 组合判定：只有上次真正崩溃的那一组组合才会被强制软解，
     * 旧的 gpu+auto-copy 崩溃不会继续挡住 mediacodec_embed+mediacodec 直写路径。
     */
    fun getHwdec(): String {
        val requested = resolveRequestedHwdec()
        if (isHwdecComboBlacklisted(requestedVo(), requested)) return HWDEC_SOFTWARE
        return requested
    }

    /** 用户请求的 hwdec（不含黑名单/软解兜底） */
    private fun resolveRequestedHwdec(): String {
        val saved = prefs.getString(KEY_HWDEC, null)?.takeIf { it.isNotEmpty() }
        if (saved == null) return defaultHwdec()
        return normalizeHwdecForDevice(saved)
    }

    /**
     * 按设备纠正 hwdec：arm32 电视/盒子不再提供 copy-back（auto-copy / auto 会落到
     * AImageReader/copy-back，实测起播即 SIGSEGV），统一改成直写 Surface 的 mediacodec。
     * 频道级设置绕过持久化偏好，也需要走这里纠正。
     */
    fun normalizeHwdecForDevice(hwdec: String): String =
        if (isArm32Tv() && (hwdec == "auto-copy" || hwdec == "auto")) HWDEC_MEDIACODEC else hwdec

    fun setHwdec(hwdec: String) {
        // 用户显式选择硬解即视为认可该设置，解除崩溃黑名单
        if (hwdec != HWDEC_SOFTWARE) setHwdecBlacklisted(false)
        prefs.edit().putString(KEY_HWDEC, hwdec).apply()
    }

    /** 是否处于「硬解导致崩溃」的设备黑名单（强制软解） */
    fun isHwdecBlacklisted(): Boolean = prefs.getBoolean(KEY_HWDEC_CRASH_BLACKLIST, false)

    fun setHwdecBlacklisted(blacklisted: Boolean) {
        prefs.edit().apply {
            putBoolean(KEY_HWDEC_CRASH_BLACKLIST, blacklisted)
            if (!blacklisted) remove(KEY_HWDEC_CRASH_COMBO)
        }.apply()
    }

    /**
     * 该 vo+hwdec 组合是否被崩溃黑名单挡住。
     *
     * 黑名单只记录上次真正崩溃的那一组组合；旧版本遗留（没有组合记录）只挡
     * gpu + auto-copy/auto，避免历史 auto-copy 崩溃一直挡住新的直写 Surface 方案。
     */
    fun isHwdecComboBlacklisted(vo: String, hwdec: String): Boolean {
        if (!isHwdecBlacklisted()) return false
        val combo = prefs.getString(KEY_HWDEC_CRASH_COMBO, null)
        if (combo != null) return combo == "$vo|$hwdec"
        return vo == DEFAULT_VO_VALUE && (hwdec == "auto-copy" || hwdec == "auto")
    }

    /** 记录导致崩溃的 vo+hwdec 组合（由 NativeCrashLogger 在下次启动时写入） */
    fun setHwdecCrashCombo(combo: String?) {
        prefs.edit().apply {
            if (combo == null) remove(KEY_HWDEC_CRASH_COMBO) else putString(KEY_HWDEC_CRASH_COMBO, combo)
        }.apply()
    }

    fun getHwdecCrashCombo(): String? = prefs.getString(KEY_HWDEC_CRASH_COMBO, null)

    /** 是否已确认该设备需要 vo fallback（黑屏检测曾触发过） */
    fun isVoFallbackConfirmed(): Boolean = prefs.getBoolean(KEY_VO_FALLBACK, false)

    fun setVoFallbackConfirmed(confirmed: Boolean) {
        prefs.edit().putBoolean(KEY_VO_FALLBACK, confirmed).apply()
    }

    // -----------------------------------------------------------------
    // HDR 输出模式
    // -----------------------------------------------------------------

    fun getHdrMode(): String = prefs.getString(KEY_HDR_MODE, DEFAULT_HDR_MODE) ?: DEFAULT_HDR_MODE

    fun setHdrMode(mode: String) {
        prefs.edit().putString(KEY_HDR_MODE, mode).apply()
    }

    // -----------------------------------------------------------------
    // 颜色管线兼容模式
    // -----------------------------------------------------------------

    /**
     * 色彩兼容模式：强制保守的 SDR 输出参数（clip 色调映射、pt.709 目标色域、
     * 关闭 HDR 动态峰值/hint），用于个别设备过曝/发灰时排障。
     * 默认关闭 —— 不改变现有正常用户的画面。
     */
    fun isColorCompatMode(): Boolean = prefs.getBoolean(KEY_COLOR_COMPAT_MODE, false)

    fun setColorCompatMode(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_COLOR_COMPAT_MODE, enabled).apply()
    }

    // -----------------------------------------------------------------
    // RTSP 传输协议
    // -----------------------------------------------------------------

    fun getRtspTransport(): String = prefs.getString(KEY_RTSP_TRANSPORT, DEFAULT_RTSP_TRANSPORT) ?: DEFAULT_RTSP_TRANSPORT

    fun setRtspTransport(transport: String) {
        prefs.edit().putString(KEY_RTSP_TRANSPORT, transport).apply()
    }

    // ExoPlayer 视频渲染视图（true=SurfaceView, false=TextureView）
    fun getExoSurfaceView(): Boolean = prefs.getBoolean(KEY_EXO_SURFACE_VIEW, true)

    fun setExoSurfaceView(useSurfaceView: Boolean) {
        prefs.edit().putBoolean(KEY_EXO_SURFACE_VIEW, useSurfaceView).apply()
    }

    // -----------------------------------------------------------------
    // 反交错
    // -----------------------------------------------------------------

    fun getDeinterlace(): String = prefs.getString(KEY_DEINTERLACE, DEFAULT_DEINTERLACE) ?: DEFAULT_DEINTERLACE

    fun setDeinterlace(value: String) {
        prefs.edit().putString(KEY_DEINTERLACE, value).apply()
    }

    // -----------------------------------------------------------------
    // 播放器类型（MPV / ExoPlayer）
    // -----------------------------------------------------------------

    fun getPlayerType(): String = prefs.getString(KEY_PLAYER_TYPE, DEFAULT_PLAYER_TYPE) ?: DEFAULT_PLAYER_TYPE

    fun setPlayerType(type: String) {
        prefs.edit().putString(KEY_PLAYER_TYPE, type).apply()
    }

    // -----------------------------------------------------------------
    // 超时换源（0=5s, 1=10s, 2=15s, 3=20s, 4=25s, 5=30s）
    // -----------------------------------------------------------------

    fun getTimeoutSwitchSource(): Int = prefs.getInt(KEY_TIMEOUT_SWITCH_SOURCE, DEFAULT_TIMEOUT_SWITCH_SOURCE)

    fun setTimeoutSwitchSource(value: Int) {
        prefs.edit().putInt(KEY_TIMEOUT_SWITCH_SOURCE, value).apply()
    }

    fun getTimeoutMs(): Long = when (getTimeoutSwitchSource()) {
        0 -> 5_000L
        1 -> 10_000L
        2 -> 15_000L
        3 -> 20_000L
        4 -> 25_000L
        5 -> 30_000L
        else -> 10_000L
    }

    // -----------------------------------------------------------------
    // 断线重连（0=关闭, 1=1s, 2=3s, 3=5s, 4=10s, 5=20s）
    // -----------------------------------------------------------------

    fun getReconnectIndex(): Int = prefs.getInt(KEY_RECONNECT_INDEX, DEFAULT_RECONNECT_INDEX)

    fun setReconnectIndex(value: Int) {
        prefs.edit().putInt(KEY_RECONNECT_INDEX, value).apply()
    }

    fun getReconnectDelayMs(): Long = when (getReconnectIndex()) {
        0 -> 0L
        1 -> 1_000L
        2 -> 3_000L
        3 -> 5_000L
        4 -> 10_000L
        5 -> 20_000L
        else -> 0L
    }

    // -----------------------------------------------------------------
    // 画面锁定（换源不黑屏）
    // -----------------------------------------------------------------

    fun getScreenLock(): Boolean = prefs.getBoolean(KEY_SCREEN_LOCK, true)

    fun setScreenLock(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_SCREEN_LOCK, enabled).apply()
    }

    fun getLiquidGlass(): Boolean = prefs.getBoolean(KEY_LIQUID_GLASS, true)

    fun setLiquidGlass(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_LIQUID_GLASS, enabled).apply()
    }

    // -----------------------------------------------------------------
    // 倍速双步进参数
    // -----------------------------------------------------------------

    fun getSpeedParams(): String = prefs.getString(KEY_SPEED_PARAMS, DEFAULT_SPEED_PARAMS) ?: DEFAULT_SPEED_PARAMS

    fun setSpeedParams(params: String) {
        prefs.edit().putString(KEY_SPEED_PARAMS, params).apply()
    }

    fun getSpeedConfig(): SpeedConfig {
        val parts = getSpeedParams().split(",")
        return try {
            SpeedConfig(
                min = parts.getOrNull(0)?.toDoubleOrNull() ?: 0.5,
                max = parts.getOrNull(1)?.toDoubleOrNull() ?: 3.0,
                slowStep = parts.getOrNull(2)?.toDoubleOrNull() ?: 0.25,
                fastStep = parts.getOrNull(3)?.toDoubleOrNull() ?: 0.5,
                fastStep2 = parts.getOrNull(4)?.toDoubleOrNull() ?: 1.0,
                fastStep2Threshold = parts.getOrNull(5)?.toDoubleOrNull() ?: 2.0
            )
        } catch (e: Exception) {
            SpeedConfig()
        }
    }

    // -----------------------------------------------------------------
    // 频道级播放器设置（per-channel override）
    // -----------------------------------------------------------------

    fun isPerChannelPlayerSettings(): Boolean =
        prefs.getBoolean(KEY_PER_CHANNEL_SETTINGS, false)

    fun setPerChannelPlayerSettings(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_PER_CHANNEL_SETTINGS, enabled).apply()
    }

    fun getChannelSettings(idx: Int): ChannelPlayerSettings? {
        val json = prefs.getString("$KEY_CHANNEL_SETTINGS_PREFIX$idx", null) ?: return null
        return try {
            val obj = JSONObject(json)
            ChannelPlayerSettings(
                playerType = obj.optString("player_type").takeIf { it.isNotEmpty() },
                vo = obj.optString("vo").takeIf { it.isNotEmpty() },
                hwdec = obj.optString("hwdec").takeIf { it.isNotEmpty() },
                hdrMode = obj.optString("hdr_mode").takeIf { it.isNotEmpty() }
            )
        } catch (e: Exception) { null }
    }

    fun setChannelSettings(idx: Int, settings: ChannelPlayerSettings) {
        val obj = JSONObject().apply {
            settings.playerType?.let { put("player_type", it) }
            settings.vo?.let { put("vo", it) }
            settings.hwdec?.let { put("hwdec", it) }
            settings.hdrMode?.let { put("hdr_mode", it) }
        }
        prefs.edit().putString("$KEY_CHANNEL_SETTINGS_PREFIX$idx", obj.toString()).apply()
    }

    fun removeChannelSettings(idx: Int) {
        prefs.edit().remove("$KEY_CHANNEL_SETTINGS_PREFIX$idx").apply()
    }

    // -----------------------------------------------------------------
    // 重置
    // -----------------------------------------------------------------

    fun resetPlayerSettings() {
        prefs.edit()
            .remove(KEY_VO)
            .remove(KEY_HWDEC)
            .remove(KEY_VO_FALLBACK)
            .remove(KEY_VO_AUTO_FALLBACK)
            .remove(KEY_HWDEC_CRASH_COMBO)
            .remove(KEY_PLAYER_TYPE)
            .remove(KEY_HDR_MODE)
            .remove(KEY_RTSP_TRANSPORT)
            .remove(KEY_DEINTERLACE)
            .remove(KEY_TIMEOUT_SWITCH_SOURCE)
            .remove(KEY_RECONNECT_INDEX)
            .remove(KEY_SCREEN_LOCK)
            .remove(KEY_SPEED_PARAMS)
            .apply()
    }

    companion object {
        internal const val KEY_VO = "player_vo"
        private const val KEY_VO_FALLBACK = "player_vo_fallback_confirmed"

        /** 默认 vo（arm64 TV 的 mediacodec_embed）因起播失败已自动回退到 gpu */
        private const val KEY_VO_AUTO_FALLBACK = "player_vo_auto_fallback"

        /** 色彩兼容模式（默认关闭） */
        private const val KEY_COLOR_COMPAT_MODE = "player_color_compat_mode"

        /**
         * hwdec 偏好键。internal 供启动早期的 NativeCrashLogger 直接读 SharedPreferences
         * （此时 UserPrefs 尚未 init，不能走门面）。
         */
        internal const val KEY_HWDEC = "player_hwdec"

        /** 硬解崩溃设备黑名单：置位后强制软解，用户手动切回硬解时解除 */
        internal const val KEY_HWDEC_CRASH_BLACKLIST = "player_hwdec_crash_blacklist"

        internal const val HWDEC_SOFTWARE = "no"
        private const val KEY_PLAYER_TYPE = "player_type"
        private const val DEFAULT_PLAYER_TYPE = "MPV"
        private const val KEY_HDR_MODE = "hdr_output_mode"
        private const val DEFAULT_HDR_MODE = "disable"
        private const val KEY_TIMEOUT_SWITCH_SOURCE = "timeout_switch_source"
        private const val DEFAULT_TIMEOUT_SWITCH_SOURCE = 2
        private const val KEY_RECONNECT_INDEX = "reconnect_index"
        private const val DEFAULT_RECONNECT_INDEX = 0
        private const val KEY_SCREEN_LOCK = "screen_lock"
        private const val KEY_LIQUID_GLASS = "liquid_glass"
        private const val KEY_SPEED_PARAMS = "speed_params"
        private const val DEFAULT_SPEED_PARAMS = "0.5,3,0.25,0.5,1,2"
        private const val KEY_RTSP_TRANSPORT = "rtsp_transport"
        private const val DEFAULT_RTSP_TRANSPORT = "tcp"
        private const val KEY_EXO_SURFACE_VIEW = "exo_surface_view"
        private const val KEY_DEINTERLACE = "deinterlace"
        private const val DEFAULT_DEINTERLACE = "no"
        private const val KEY_PER_CHANNEL_SETTINGS = "per_channel_player_settings"
        private const val KEY_CHANNEL_SETTINGS_PREFIX = "channel_settings_"

        // 与 MPVView.DEFAULT_VO / DEFAULT_HWDEC 保持一致（字符串常量避免反向依赖 mpv 层）
        private const val DEFAULT_VO_VALUE = "gpu"
        private const val DEFAULT_HWDEC_VALUE = "auto-copy"

        /** 电视/盒子默认零拷贝直渲路径（MediaCodec 直接写 Surface，不碰 AImageReader/copy-back） */
        private const val VO_MEDIACODEC_EMBED = "mediacodec_embed"
        private const val HWDEC_MEDIACODEC = "mediacodec"

        /** 手机（arm64 手持设备）默认渲染：gpu-next 配 mediacodec 直通，少一次 CPU 回读 */
        private const val VO_GPU_NEXT = "gpu-next"

        /** 崩溃黑名单记录的具体 vo+hwdec 组合（"vo|hwdec"），空=旧版本遗留 */
        internal const val KEY_HWDEC_CRASH_COMBO = "player_hwdec_crash_combo"
    }

    /** 是否为 arm32 TV 设备（仅 armeabi-v7a 主 ABI 的电视/盒子） */
    private fun isArm32Tv(): Boolean {
        val ctx = appContext ?: return false
        val uiMode = (ctx.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager)
            ?.currentModeType
        if (uiMode != Configuration.UI_MODE_TYPE_TELEVISION) return false
        return android.os.Build.SUPPORTED_ABIS.any { it.startsWith("armeabi") } &&
            android.os.Build.SUPPORTED_ABIS.none { it == "arm64-v8a" }
    }

    /** 是否为 arm32 TV 设备（UI 用它隐藏 copy-back 选项） */
    fun isArm32TvDevice(): Boolean = isArm32Tv()

    /** 电视/盒子硬解必须走 mediacodec_embed（AImageReader/copy-back 在 OMX 设备上必崩） */
    fun isTvEmbedRequired(): Boolean = isArm32Tv()

    /** 用户切换硬/软解时的目标 vo */
    fun voForHardwareDecode(enabled: Boolean, currentVo: String): String = when {
        !enabled -> if (currentVo == VO_MEDIACODEC_EMBED) DEFAULT_VO_VALUE else currentVo
        isTvEmbedRequired() -> VO_MEDIACODEC_EMBED
        else -> currentVo
    }

    /** 用户切换硬/软解时的目标 hwdec */
    fun hwdecForHardwareDecode(enabled: Boolean, currentHwdec: String): String = when {
        !enabled -> HWDEC_SOFTWARE
        isTvEmbedRequired() -> HWDEC_MEDIACODEC
        isArm64Handheld() -> HWDEC_MEDIACODEC
        currentHwdec == "auto" -> "auto"
        else -> DEFAULT_HWDEC_VALUE
    }

    /**
     * 是否为 arm64 电视/盒子。
     *
     * 这类设备默认走 vo=mediacodec_embed + hwdec=mediacodec（解码器直接写 Surface，
     * 零拷贝、少一次 GPU 上传）。出错时由 MpvController 自动回退 gpu + auto-copy 一次。
     * 手机/平板/车机（非 TV 模式）不放开，避免非电视设备走未验证路径。
     */
    private fun isArm64Tv(): Boolean {
        val ctx = appContext ?: return false
        val uiMode = (ctx.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager)
            ?.currentModeType
        if (uiMode != Configuration.UI_MODE_TYPE_TELEVISION) return false
        return android.os.Build.SUPPORTED_ABIS.any { it == "arm64-v8a" }
    }

    /** 是否为 arm64 手机（有触屏、最短边 < 600dp） */
    fun isHandheldDevice(): Boolean = isArm64Handheld()

    /**
     * 是否为 arm64 手机（有触屏、最短边 < 600dp）。
     * 车机/平板屏幕最短边 ≥ 600dp 或没有触屏，不在此列，保持 gpu + auto-copy。
     */
    private fun isArm64Handheld(): Boolean {
        val ctx = appContext ?: return false
        if (android.os.Build.SUPPORTED_ABIS.none { it == "arm64-v8a" }) return false
        if (!ctx.packageManager.hasSystemFeature(android.content.pm.PackageManager.FEATURE_TOUCHSCREEN)) return false
        val config = ctx.resources.configuration
        return minOf(config.screenWidthDp, config.screenHeightDp) < 600
    }

    private fun defaultVo(): String = when {
        isArm32Tv() || isArm64Tv() -> VO_MEDIACODEC_EMBED
        isArm64Handheld() -> VO_GPU_NEXT
        else -> DEFAULT_VO_VALUE
    }

    private fun defaultHwdec(): String = when {
        // arm32 TV：硬解统一走 mediacodec 直写 Surface（不提供 copy-back）
        isArm32Tv() -> HWDEC_MEDIACODEC
        // 默认 vo 是 mediacodec_embed 时，hwdec 必须配对 mediacodec（零拷贝直渲）
        hasExplicitVo().not() && defaultVo() == VO_MEDIACODEC_EMBED -> HWDEC_MEDIACODEC
        // 手机：MediaCodec 直通 GPU，避免 copy-back 回读 CPU
        isArm64Handheld() -> HWDEC_MEDIACODEC
        else -> DEFAULT_HWDEC_VALUE
    }
}