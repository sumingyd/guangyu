package com.iptv.scanner.editor.pro.mpv.controller

import android.util.Log
import `is`.xyz.mpv.MPVLib

/**
 * 滤镜子控制器：视频滤镜清理/360°视角/运动补偿/超分辨率/用户着色器。
 */
class MpvFilterController(private val host: MpvControllerHost) {

    private val shaderPresetFiles = mapOf(
        "ravu" to listOf("ravu_r3.hook"),
        "fsrcnnx" to listOf("FSRCNNX_x2_8-0-4-1.glsl"),
        "anime4k" to listOf(
            "Anime4K_Clamp_Highlights.glsl",
            "Anime4K_Restore_CNN_S.glsl",
            "Anime4K_Upscale_CNN_x2_S.glsl"
        ),
        "krig" to listOf("KrigBilateral.hook"),
        "ssim" to listOf("SSimDownscaler.glsl"),
        "esrgan" to listOf(
            "ravu_r4.hook",
            "FSRCNNX_x2_8-0-4-1.glsl",
            "adaptive_sharpen.glsl"
        ),
        "adaptive_sharpen" to listOf("adaptive_sharpen.glsl")
    )

    fun clearAllVideoFilters() {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_flip"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_crop"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_360"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_mc"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_sr"))
        }
    }

    fun set360View(yaw: Double, pitch: Double, roll: Double, projection: String): Boolean {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_360"))
            val expr = "lavfi=[panorama=e=$projection:yaw=$yaw:pitch=$pitch:roll=$roll]"
            MPVLib.command(arrayOf("vf", "add", "@iptv_360:$expr"))
        }
        return true
    }

    fun clear360Filter() {
        host.postOnUiThread { MPVLib.command(arrayOf("vf", "remove", "@iptv_360")) }
    }

    fun setMotionCompensation(strength: String, targetFps: Int): Boolean {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_mc"))
            val preset = when (strength) {
                "low" -> "mi_mode=blend"
                "medium" -> "mi_mode=mci:mc_mode=obmc:me=dsr"
                "high" -> "mi_mode=mci:mc_mode=aobmc:me=hexbs"
                else -> null
            }
            if (preset != null) {
                val fps = if (targetFps in listOf(50, 60, 90, 120, 144, 240)) targetFps else 60
                val w = try { MPVLib.getPropertyInt("width") ?: 0 } catch (_: Throwable) { 0 }
                val h = try { MPVLib.getPropertyInt("height") ?: 0 } catch (_: Throwable) { 0 }
                val is4k = w >= 3840 || h >= 2160
                val filterStr = if (is4k) {
                    "@iptv_mc:lavfi=[scale=1920:1080:flags=fast_bilinear,minterpolate=fps=$fps:$preset]"
                } else {
                    "@iptv_mc:lavfi=[minterpolate=fps=$fps:$preset]"
                }
                MPVLib.command(arrayOf("vf", "add", filterStr))
            }
        }
        return true
    }

    fun clearMotionCompensation() {
        host.postOnUiThread { MPVLib.command(arrayOf("vf", "remove", "@iptv_mc")) }
    }

    fun setSuperResolution(scaleAlgo: String, detailEnhance: Int): Boolean {
        host.postOnUiThread {
            val validAlgos = listOf("bilinear", "bicubic", "lanczos", "spline", "ewa_lanczos", "ewa_lanczossharp")
            val w = try { MPVLib.getPropertyInt("width") ?: 0 } catch (_: Throwable) { 0 }
            val h = try { MPVLib.getPropertyInt("height") ?: 0 } catch (_: Throwable) { 0 }
            val is4k = w >= 3840 || h >= 2160
            var algo = scaleAlgo
            if (is4k && algo in listOf("ewa_lanczos", "ewa_lanczossharp")) {
                algo = "lanczos"
            }
            if (algo in validAlgos) {
                MPVLib.setPropertyString("scale", algo)
                MPVLib.setPropertyString("cscale", algo)
                val dscale = if (algo == "ewa_lanczossharp") "ewa_lanczos" else algo
                MPVLib.setPropertyString("dscale", dscale)
            } else {
                // 恢复 mpv 默认缩放（scale=lanczos，cscale/dscale=bilinear），不能写 bilinear 降画质
                MPVLib.setPropertyString("scale", "lanczos")
                MPVLib.setPropertyString("cscale", "bilinear")
                MPVLib.setPropertyString("dscale", "bilinear")
            }
            MPVLib.command(arrayOf("vf", "remove", "@iptv_sr"))
            val detail = detailEnhance.coerceIn(0, 100)
            if (detail > 0) {
                val amount = String.format("%.3f", detail / 100.0 * 1.5)
                val filterStr = if (is4k) {
                    "@iptv_sr:lavfi=[scale=1920:1080:flags=fast_bilinear,unsharp=5:5:$amount:5:5:0.0]"
                } else {
                    "@iptv_sr:lavfi=[unsharp=5:5:$amount:5:5:0.0]"
                }
                MPVLib.command(arrayOf("vf", "add", filterStr))
            }
        }
        return true
    }

    fun clearSuperResolution() {
        host.postOnUiThread {
            // 恢复 mpv 默认缩放（scale=lanczos，cscale/dscale=bilinear），与“关闭”路径保持一致
            MPVLib.setPropertyString("scale", "lanczos")
            MPVLib.setPropertyString("cscale", "bilinear")
            MPVLib.setPropertyString("dscale", "bilinear")
            MPVLib.command(arrayOf("vf", "remove", "@iptv_sr"))
        }
    }

    fun setUserShader(preset: String): Boolean {
        if (preset == "off" || preset.isEmpty()) {
            clearUserShader()
            return true
        }
        host.postOnUiThread {
            val shaderPaths: List<String>
            if (java.io.File(preset).isFile) {
                shaderPaths = listOf(preset)
            } else {
                shaderPaths = findShaderFiles(preset)
            }
            if (shaderPaths.isNotEmpty()) {
                val shaderStr = shaderPaths.joinToString(",")
                MPVLib.setPropertyString("glsl-shaders", shaderStr)
                Log.i(TAG, "用户着色器已加载: $preset -> $shaderStr")
            } else {
                Log.w(TAG, "着色器文件未找到: preset=$preset，请在 shaders/ 目录放置对应文件")
            }
        }
        return true
    }

    fun clearUserShader() {
        host.postOnUiThread {
            MPVLib.setPropertyString("glsl-shaders", "")
        }
    }

    private fun findShaderFiles(preset: String): List<String> {
        val ctx = host.getMpvView()?.asView()?.context ?: return emptyList()
        val shadersDir = java.io.File(ctx.filesDir, "shaders")
        if (!shadersDir.isDirectory) return emptyList()

        val fileNames = shaderPresetFiles[preset]
        if (fileNames != null) {
            val paths = fileNames.mapNotNull { fname ->
                val f = java.io.File(shadersDir, fname)
                if (f.isFile) f.absolutePath else null
            }
            if (paths.isNotEmpty()) return paths
        }

        val extensions = arrayOf(".glsl", ".hook", ".glsl.hook")
        for (ext in extensions) {
            val exact = java.io.File(shadersDir, "$preset$ext")
            if (exact.isFile) return listOf(exact.absolutePath)
            val matches = shadersDir.listFiles { f ->
                f.name.lowercase().startsWith(preset.lowercase()) &&
                f.name.lowercase().endsWith(ext)
            }
            if (matches != null && matches.isNotEmpty()) {
                return listOf(matches[0].absolutePath)
            }
        }
        return emptyList()
    }

    companion object {
        private const val TAG = "MpvController"
    }
}