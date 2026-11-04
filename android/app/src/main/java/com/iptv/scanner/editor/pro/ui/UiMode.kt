package com.iptv.scanner.editor.pro.ui

import android.content.Context
import android.util.Log
import android.content.res.Configuration
import android.os.Build

/**
 * UI 模式：手机触摸 vs TV 遥控器。
 *
 * 设计差异（用户明确要求）：
 * - PHONE：底部控制面板（3 行：媒体信息 / 节目信息 / 控制条）+ 左右抽屉（频道列表 / EPG）
 *   触摸交互，点击/滑动为主
 * - TV：左侧频道导航栏（DPAD 上下切换）+ 顶部信息条 + 中央播放 + 右侧 EPG 抽屉
 *   DPAD 焦点导航，方向键 + 确认键为主
 *
 * 判断标准（与 Android Leanback 一致）：
 * 1. UI_MODE_TYPE_TELEVISION（系统声明 TV 模式）
 * 2. FEATURE_LEANBACK（系统支持 Leanback TV 启动器）
 * 3. Build.VERSION.SDK_INT >= 21 且无触屏（FEATURE_TOUCHSCREEN=false）
 *
 * 注意：部分 TV 盒子（如小米盒子）同时具备触屏和 TV 模式，以 UI_MODE_TYPE_TELEVISION 优先。
 */
enum class UiMode {
    PHONE,
    TV;

    val isTV: Boolean get() = this == TV
    val isPhone: Boolean get() = this == PHONE
}

object UiModeDetector {
    /**
     * 检测当前设备应该使用哪种 UI 模式。
     * 在 Activity 创建时调用一次，结果缓存在 ViewModel 中。
     */
    fun detect(context: Context): UiMode {
        // 0. 用户强制 TV 模式（调试/模拟器用）
        try {
            val prefs = context.getSharedPreferences("iptv_user_prefs", android.content.Context.MODE_PRIVATE)
            if (prefs.getBoolean("force_tv_mode", false)) {
                return UiMode.TV
            }
        } catch (_: Exception) {}

        // 0.1 文件标志强制 TV 模式（adb shell touch /sdcard/force_tv_mode）
        try {
            val extDir = context.getExternalFilesDir(null)
            if (java.io.File(extDir, "force_tv_mode").exists() ||
                java.io.File("/sdcard/force_tv_mode").exists()
            ) {
                Log.i("UiModeDetector", "force_tv_mode -> TV")
                return UiMode.TV
            }
        } catch (_: Exception) {}

        // 0.15 文件标志强制手机模式（模拟器调试用）
        // 位置：应用外部文件目录 force_phone_mode（adb: touch /sdcard/Android/data/<pkg>/files/force_phone_mode）
        // 也可放 /sdcard 根目录（需"所有文件访问"权限）。优先级低于 force_tv_mode，高于系统 TV 检测
        try {
            val extDir = context.getExternalFilesDir(null)
            if (java.io.File(extDir, "force_phone_mode").exists() ||
                java.io.File("/sdcard/force_phone_mode").exists()
            ) {
                Log.i("UiModeDetector", "force_phone_mode -> PHONE")
                return UiMode.PHONE
            }
        } catch (_: Exception) {}

        // 1. 系统声明 TV 模式（最可靠）
        val currentModeType = context.resources.configuration.uiMode and Configuration.UI_MODE_TYPE_MASK
        if (currentModeType == Configuration.UI_MODE_TYPE_TELEVISION) {
            Log.i("UiModeDetector", "system uiMode=TELEVISION -> TV")
            return UiMode.TV
        }

        // 2. 支持 Leanback（TV 启动器特性）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP
            && context.packageManager.hasSystemFeature("android.software.leanback")
        ) {
            Log.i("UiModeDetector", "leanback -> TV")
            return UiMode.TV
        }

        // 3. 无触屏设备（部分老旧 TV）
        if (!context.packageManager.hasSystemFeature("android.hardware.touchscreen")) {
            Log.i("UiModeDetector", "no touchscreen -> TV")
            return UiMode.TV
        }

        // 4. 大屏兜底（智慧屏/魔改盒子：声明触屏、无 leanback、uiMode 非 TELEVISION）。
        //    电视/盒子的硬件特征：无蜂窝电话（平板可能有）、无相机（平板标配前置相机）。
        //    屏幕最短边 ≥ 600dp 且两者皆无 → 视为电视；手机（有电话）、平板（有相机）不受影响
        val pm = context.packageManager
        val sw = minOf(
            context.resources.configuration.screenWidthDp,
            context.resources.configuration.screenHeightDp
        )
        if (sw >= 600
            && !pm.hasSystemFeature(android.content.pm.PackageManager.FEATURE_TELEPHONY)
            && !pm.hasSystemFeature(android.content.pm.PackageManager.FEATURE_CAMERA_ANY)
        ) {
            Log.i("UiModeDetector", "big screen no-telephony no-camera sw=${sw}dp -> TV")
            return UiMode.TV
        }

        return UiMode.PHONE
    }
}
