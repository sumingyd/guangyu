package com.iptv.scanner.editor.pro.mpv.controller

import android.util.Log
import `is`.xyz.mpv.MPVLib
import org.json.JSONObject

enum class FilterApplyStatus { APPLIED, NOT_APPLIED, UNKNOWN, CLEARED }

/**
 * 滤镜挂载校验结果。
 *
 * mpv 的 `vf add` 即使失败也不会抛异常（Android 侧 MPVLib.command 无返回值），
 * 所以必须回读 `vf` 与 `hwdec-current` 才能判断滤镜是否真的生效：
 * - vo=mediacodec_embed 时不走 mpv 画面层，一定不可用
 * - hwdec-current=mediacodec 为零拷贝硬解，lavfi 拿不到软件帧
 * - hwdec-current 为空（尚未解码）时状态未知，不提示用户
 */
data class FilterApplyCheck(
    val label: String,
    val requested: Boolean,
    val status: FilterApplyStatus,
    val vo: String,
    val hwdecCurrent: String,
    val vf: String,
)

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

    /** 每个滤镜的请求代次：延迟复查时若已被关闭/重设，丢弃旧结果，避免误报 */
    private val verifyGenerations = mutableMapOf<String, Int>()

    fun clearAllVideoFilters() {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_flip"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_crop"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_360"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_mc"))
            MPVLib.command(arrayOf("vf", "remove", "@iptv_sr"))
            // 关闭/停止时同步清除界面的「未生效」状态
            notifyCleared(LABEL_MC)
            notifyCleared(LABEL_SR)
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
            if (preset == null) {
                notifyCleared(LABEL_MC)
                return@postOnUiThread
            }
            val fps = if (targetFps in listOf(50, 60, 90, 120, 144, 240)) targetFps else 60
            // 直写 Surface 不过 mpv 的画面/滤镜层，不发起注定失败的 vf add，
            // 直接回读并上报「未生效」，由界面给出切换入口（不自动切 vo）
            if (readString("vo") == "mediacodec_embed") {
                Log.i(TAG, "motion compensation skipped: vo=mediacodec_embed cannot host lavfi (fps=$fps)")
                reportCheck(LABEL_MC, requested = true)
                return@postOnUiThread
            }
            val w = try { MPVLib.getPropertyInt("width") ?: 0 } catch (_: Throwable) { 0 }
            val h = try { MPVLib.getPropertyInt("height") ?: 0 } catch (_: Throwable) { 0 }
            val is4k = w >= 3840 || h >= 2160
            val filterStr = if (is4k) {
                "@iptv_mc:lavfi=[scale=1920:1080:flags=fast_bilinear,minterpolate=fps=$fps:$preset]"
            } else {
                "@iptv_mc:lavfi=[minterpolate=fps=$fps:$preset]"
            }
            MPVLib.command(arrayOf("vf", "add", filterStr))
            reportCheck(LABEL_MC, requested = true)
        }
        return true
    }

    fun clearMotionCompensation() {
        host.postOnUiThread {
            MPVLib.command(arrayOf("vf", "remove", "@iptv_mc"))
            notifyCleared(LABEL_MC)
        }
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
            if (detail <= 0) {
                notifyCleared(LABEL_SR)
                return@postOnUiThread
            }
            if (readString("vo") == "mediacodec_embed") {
                Log.i(TAG, "detail enhance skipped: vo=mediacodec_embed cannot host lavfi (detail=$detail)")
                reportCheck(LABEL_SR, requested = true)
                return@postOnUiThread
            }
            val amount = String.format("%.3f", detail / 100.0 * 1.5)
            val filterStr = if (is4k) {
                "@iptv_sr:lavfi=[scale=1920:1080:flags=fast_bilinear,unsharp=5:5:$amount:5:5:0.0]"
            } else {
                "@iptv_sr:lavfi=[unsharp=5:5:$amount:5:5:0.0]"
            }
            MPVLib.command(arrayOf("vf", "add", filterStr))
            reportCheck(LABEL_SR, requested = true)
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
            notifyCleared(LABEL_SR)
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

    /**
     * 回读 vf / hwdec-current 后上报结果。
     *
     * 部分设备在文件刚加载时 hwdec-current 仍为空，此时状态记为 UNKNOWN 并在 1.5s 后复查一次；
     * 复查前若用户已关闭/重设该滤镜，代次变化会丢弃旧结果。
     */
    private fun reportCheck(label: String, requested: Boolean) {
        val generation = nextGeneration(label)
        val check = buildCheck(label, requested)
        logCheck("filter verify", check)
        host.notifyFilterApplyChecked(check)
        if (requested && check.status == FilterApplyStatus.UNKNOWN) {
            host.getMpvView()?.asView()?.postDelayed({
                if (verifyGenerations[label] != generation) return@postDelayed
                val retry = buildCheck(label, requested = true)
                logCheck("filter verify(retry)", retry)
                host.notifyFilterApplyChecked(retry)
            }, 1500)
        }
    }

    private fun buildCheck(label: String, requested: Boolean): FilterApplyCheck {
        val vo = readString("vo")
        val hwdec = readString("hwdec-current")
        val vf = readString("vf")
        val status = when {
            vo == "mediacodec_embed" -> FilterApplyStatus.NOT_APPLIED
            isZeroCopyHwdec(hwdec) -> FilterApplyStatus.NOT_APPLIED
            hwdec.isEmpty() -> FilterApplyStatus.UNKNOWN
            vfHasLabel(vf, label) -> FilterApplyStatus.APPLIED
            else -> FilterApplyStatus.NOT_APPLIED
        }
        return FilterApplyCheck(label, requested, status, vo, hwdec, vf)
    }

    private fun notifyCleared(label: String) {
        nextGeneration(label)
        val check = FilterApplyCheck(
            label = label,
            requested = false,
            status = FilterApplyStatus.CLEARED,
            vo = readString("vo"),
            hwdecCurrent = readString("hwdec-current"),
            vf = readString("vf")
        )
        logCheck("filter verify", check)
        host.notifyFilterApplyChecked(check)
    }

    private fun nextGeneration(label: String): Int {
        val next = (verifyGenerations[label] ?: 0) + 1
        verifyGenerations[label] = next
        return next
    }

    private fun readString(name: String): String {
        return try { MPVLib.getPropertyString(name) ?: "" } catch (_: Throwable) { "" }
    }

    /** vf 属性里的 label 可能带或不带 @ 前缀，两种都接受 */
    private fun vfHasLabel(vf: String, label: String): Boolean {
        if (vf.isBlank()) return false
        val short = label.removePrefix("@")
        return try {
            val arr = JSONObject(vf).optJSONArray("vf") ?: return false
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                if (item.optString("label").removePrefix("@") == short) return true
                val paramLabel = item.optJSONObject("params")?.optString("@label").orEmpty()
                if (paramLabel.removePrefix("@") == short) return true
            }
            false
        } catch (_: Throwable) {
            vf.contains(label) || vf.contains(short)
        }
    }

    /** mediacodec 零拷贝硬解拿不到软件帧；mediacodec-copy / no 才能接 lavfi */
    private fun isZeroCopyHwdec(hwdec: String): Boolean {
        val value = hwdec.trim().lowercase()
        return value == "mediacodec" || value == "mediacodec_embed"
    }

    private fun logCheck(prefix: String, check: FilterApplyCheck) {
        Log.i(
            TAG,
            "$prefix: label=${check.label} requested=${check.requested} status=${check.status} " +
                "vo='${check.vo}' hwdec-current='${check.hwdecCurrent}' vf=${check.vf.take(300)}"
        )
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
        private const val LABEL_MC = "@iptv_mc"
        private const val LABEL_SR = "@iptv_sr"
    }
}