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
    fun getVo(): String = prefs.getString(KEY_VO, null)?.takeIf { it.isNotEmpty() } ?: defaultVo()

    fun setVo(vo: String) {
        prefs.edit().putString(KEY_VO, vo).apply()
    }

    /** 获取持久化的 hwdec 模式，未持久化时按设备类型给默认值 */
    fun getHwdec(): String {
        // 设备黑名单：上次会话开启硬解时进程异常退出（native 崩溃），
        // 本次会话强制软解，避免再次走到同一条 MediaCodec teardown 崩溃路径。
        if (isHwdecBlacklisted()) return HWDEC_SOFTWARE
        return prefs.getString(KEY_HWDEC, null)?.takeIf { it.isNotEmpty() } ?: defaultHwdec()
    }

    fun setHwdec(hwdec: String) {
        // 用户显式选择硬解即视为认可该设置，解除崩溃黑名单
        if (hwdec != HWDEC_SOFTWARE) setHwdecBlacklisted(false)
        prefs.edit().putString(KEY_HWDEC, hwdec).apply()
    }

    /** 是否处于「硬解导致崩溃」的设备黑名单（强制软解） */
    fun isHwdecBlacklisted(): Boolean = prefs.getBoolean(KEY_HWDEC_CRASH_BLACKLIST, false)

    fun setHwdecBlacklisted(blacklisted: Boolean) {
        prefs.edit().putBoolean(KEY_HWDEC_CRASH_BLACKLIST, blacklisted).apply()
    }

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
        private const val KEY_VO = "player_vo"
        private const val KEY_VO_FALLBACK = "player_vo_fallback_confirmed"

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

        /**
         * arm32（armeabi-v7a）TV 设备：MediaCodec 硬解码器运行中的 teardown
         * 存在 native 空指针崩溃（Sony BRAVIA VH21 实测，无论 mediacodec copy
         * 还是 mediacodec_embed 直渲，vo 切换/换台触发解码器销毁即 SIGSEGV，
         * fault addr 0x18/0x24，OMX.MTK 解码器区域）。唯一稳定路径是软解，
         * 与 houdini 转译层同构规避：默认 hwdec=no（sanitizeHwdec 双保险强制）。
         */
        private const val TV_ARM32_HWDEC_VALUE = "no"
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

    private fun defaultVo(): String = DEFAULT_VO_VALUE

    private fun defaultHwdec(): String = if (isArm32Tv()) TV_ARM32_HWDEC_VALUE else DEFAULT_HWDEC_VALUE
}