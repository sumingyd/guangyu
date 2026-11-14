package com.iptv.scanner.editor.pro.mpv.controller

import `is`.xyz.mpv.MPVLib

/**
 * 音频均衡子控制器：音频延迟/10段EQ/音调/声道信息/声道活动监控。
 */
class MpvAudioEqController(private val host: MpvControllerHost) {

    fun setAudioDelay(delaySec: Double): Boolean {
        host.postOnUiThread { MPVLib.setPropertyDouble("audio-delay", delaySec.coerceIn(-10.0, 10.0)) }
        return true
    }

    fun adjustAudioDelay(delta: Double): Boolean {
        host.postOnUiThread {
            val cur = try { MPVLib.getPropertyDouble("audio-delay") ?: 0.0 } catch (_: Throwable) { 0.0 }
            MPVLib.setPropertyDouble("audio-delay", (cur + delta).coerceIn(-10.0, 10.0))
        }
        return true
    }

    fun setAudioEq(gains: List<Float>): Boolean {
        host.postOnUiThread {
            MPVLib.command(arrayOf("af", "remove", "@iptv_eq"))
            if (gains.size != 10 || gains.all { it == 0f }) return@postOnUiThread
            val eqStr = gains.joinToString(":") { "%.1f".format(it) }
            MPVLib.command(arrayOf("af", "add", "@iptv_eq:equalizer=$eqStr"))
        }
        return true
    }

    fun resetAudioEq(): Boolean {
        host.postOnUiThread { MPVLib.command(arrayOf("af", "remove", "@iptv_eq")) }
        return true
    }

    fun setAudioPitch(pitch: Double): Boolean {
        // audio-pitch-correction 只是 yes/no 开关，浮点音调要用 rubberband 滤镜。
        // 滤镜走 PCM，音频直通/硬解直出时听不到变调效果。
        val v = pitch.coerceIn(0.5, 2.0)
        host.postOnUiThread {
            MPVLib.command(arrayOf("af", "remove", "@iptv_pitch"))
            if (kotlin.math.abs(v - 1.0) < 0.005) return@postOnUiThread
            MPVLib.command(
                arrayOf("af", "add", "@iptv_pitch:lavfi=[rubberband=pitch=%.3f]".format(v))
            )
        }
        return true
    }

    fun getAudioChannelInfo(): Map<String, Any> {
        val layout = MPVLib.getPropertyString("audio-params/channel-layout") ?: ""
        val count = MPVLib.getPropertyInt("audio-params/channel-count") ?: 0
        val layoutLower = layout.lowercase().trim()
        var channels = CHANNEL_LAYOUT_MAP[layoutLower] ?: emptyList()
        var resolvedLayout = layoutLower
        if (channels.isEmpty() && count > 0) {
            channels = when {
                count == 1 -> { resolvedLayout = "mono"; listOf("FC") }
                count == 2 -> { resolvedLayout = "stereo"; listOf("FL", "FR") }
                count >= 6 -> { resolvedLayout = "5.1"; listOf("FL", "FR", "FC", "LFE", "BL", "BR") }
                count >= 3 -> { resolvedLayout = "3.0"; listOf("FL", "FR", "FC") }
                else -> emptyList()
            }
        }
        return mapOf(
            "layout" to resolvedLayout,
            "channels" to channels,
            "count" to channels.size,
        )
    }

    fun startChannelMonitor(): Boolean {
        host.postOnUiThread {
            MPVLib.command(arrayOf("af", "remove", "@iptv_stats"))
            MPVLib.command(arrayOf("af", "add", "@iptv_stats:lavfi=[astats=metadata=1:reset=1]"))
        }
        return true
    }

    fun stopChannelMonitor() {
        host.postOnUiThread { MPVLib.command(arrayOf("af", "remove", "@iptv_stats")) }
    }

    fun getChannelLevels(): Map<Int, Float> {
        val raw = MPVLib.getPropertyString("af-metadata/@iptv_stats") ?: return emptyMap()
        val result = mutableMapOf<Int, Float>()
        try {
            val data = org.json.JSONObject(raw)
            val keys = data.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                if (key.startsWith("lavfi.astats.") && key.endsWith(".RMS_level")) {
                    val parts = key.split(".")
                    if (parts.size == 4) {
                        val chIdx = parts[2].toIntOrNull()
                        if (chIdx != null) {
                            val level = data.getString(key)
                            if (level != "-inf" && level != "nan") {
                                result[chIdx] = level.toFloat()
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            // 忽略解析错误
        }
        return result
    }

    companion object {
        val CHANNEL_LAYOUT_MAP = mapOf(
            "mono" to listOf("FC"),
            "1.0" to listOf("FC"),
            "stereo" to listOf("FL", "FR"),
            "2.0" to listOf("FL", "FR"),
            "2.1" to listOf("FL", "FR", "LFE"),
            "3.0" to listOf("FL", "FR", "FC"),
            "4.0" to listOf("FL", "FR", "FC", "BC"),
            "quad" to listOf("FL", "FR", "BL", "BR"),
            "5.0" to listOf("FL", "FR", "FC", "BL", "BR"),
            "5.1" to listOf("FL", "FR", "FC", "LFE", "BL", "BR"),
            "6.0" to listOf("FL", "FR", "FC", "BC", "SL", "SR"),
            "6.1" to listOf("FL", "FR", "FC", "LFE", "BC", "SL", "SR"),
            "7.0" to listOf("FL", "FR", "FC", "BL", "BR", "SL", "SR"),
            "7.1" to listOf("FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR"),
        )

        val CHANNEL_DISPLAY = mapOf(
            "FL" to "左前", "FR" to "右前", "FC" to "中置",
            "LFE" to "低音炮", "BL" to "左环绕", "BR" to "右环绕",
            "BC" to "后中置", "SL" to "左侧", "SR" to "右侧",
        )
    }
}