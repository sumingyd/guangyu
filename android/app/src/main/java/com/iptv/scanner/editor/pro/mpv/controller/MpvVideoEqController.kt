package com.iptv.scanner.editor.pro.mpv.controller

import android.util.Log
import `is`.xyz.mpv.MPVLib

/**
 * 视频均衡子控制器：亮度/对比度/饱和度/色相/Gamma/反交错/旋转/翻转/裁剪/3D立体模式。
 */
class MpvVideoEqController(private val host: MpvControllerHost) {

    fun setDeinterlace(value: String) {
        // auto 必须原样交给 mpv：deinterlace=auto 才由 FFmpeg 检测隔行帧后再插滤镜；
        // 旧实现把 auto 映射成 yes，会导致逐行片源也被强制反交错。
        val mpvValue = when (value) {
            "auto" -> "auto"
            "yes" -> "yes"
            else -> "no"
        }
        host.postOnUiThread {
            try {
                MPVLib.setPropertyString("deinterlace", mpvValue)
                Log.i(TAG, "setDeinterlace: value=$value → mpv=$mpvValue")
            } catch (e: Throwable) {
                Log.e(TAG, "setDeinterlace failed", e)
            }
        }
    }

    fun setBrightness(v: Int): Boolean {
        host.postOnUiThread { MPVLib.setPropertyInt("brightness", v.coerceIn(-100, 100)) }
        return true
    }

    fun setContrast(v: Int): Boolean {
        host.postOnUiThread { MPVLib.setPropertyInt("contrast", v.coerceIn(-100, 100)) }
        return true
    }

    fun setSaturation(v: Int): Boolean {
        host.postOnUiThread { MPVLib.setPropertyInt("saturation", v.coerceIn(-100, 100)) }
        return true
    }

    fun setHue(v: Int): Boolean {
        host.postOnUiThread { MPVLib.setPropertyInt("hue", v.coerceIn(-100, 100)) }
        return true
    }

    fun setGamma(v: Int): Boolean {
        host.postOnUiThread { MPVLib.setPropertyInt("gamma", v.coerceIn(-100, 100)) }
        return true
    }

    fun setVideoRotate(degree: Int): Boolean {
        host.postOnUiThread { MPVLib.setPropertyInt("video-rotate", degree) }
        return true
    }

    fun setVideoFlip(mode: String): Boolean {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_flip"))
            val filters = when (mode) {
                "horizontal" -> listOf("hflip")
                "vertical" -> listOf("vflip")
                "both" -> listOf("hflip", "vflip")
                else -> emptyList()
            }
            if (filters.isNotEmpty()) {
                val expr = "lavfi=[" + filters.joinToString(",") + "]"
                MPVLib.command(arrayOf("vf", "add", "@iptv_flip:$expr"))
            }
        }
        return true
    }

    fun setVideoCrop(x: Int, y: Int, w: Int, h: Int): Boolean {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_crop"))
            if (w > 0 && h > 0) {
                MPVLib.command(arrayOf("vf", "add", "@iptv_crop:crop=$w:$h:$x:$y"))
            }
        }
        return true
    }

    fun clearVideoCrop() {
        host.postOnUiThread { MPVLib.command(arrayOf("vf", "remove", "@iptv_crop")) }
    }

    fun setVideoStereoMode(mode: String): Boolean {
        host.postOnUiThread { MPVLib.setPropertyString("video-stereo-mode", mode) }
        return true
    }

    fun getVideoStereoMode(): String? {
        return MPVLib.getPropertyString("video-stereo-mode")
    }

    companion object {
        private const val TAG = "MpvController"
    }
}