package com.iptv.scanner.editor.pro.ui

import android.content.Context
import android.util.Log
import android.content.res.Configuration
import android.os.Build
import android.view.WindowManager

/**
 * UI 模式：手机 / 平板 / TV。
 *
 * - PHONE：竖屏首页 + 底部 Tab，横屏走分屏/全屏触摸布局
 * - TABLET：触摸优先的大屏设备，沿用触摸布局，横屏默认分屏，交互与手机一致
 * - TV：遥控器焦点驱动，无独立首页，全屏即主页
 */
enum class UiMode {
    PHONE,
    TABLET,
    TV;

    val isTV: Boolean get() = this == TV
    val isPhone: Boolean get() = this == PHONE
    val isTablet: Boolean get() = this == TABLET
    /** 触摸优先（手机/平板）：保留触摸交互与自动画中画 */
    val isTouch: Boolean get() = this != TV
    /** 设置项里展示的中文名 */
    val displayName: String
        get() = when (this) {
            PHONE -> "手机"
            TABLET -> "平板"
            TV -> "TV"
        }
}

/**
 * 设置页「界面模式」：自动沿用设备判定，其余三项强制按所选形态渲染。
 * storageValue 写入 SharedPreferences，label 用于设置项与菜单副标题。
 */
enum class UiModePreference(val storageValue: String, val label: String) {
    AUTO("auto", "自动（按设备判断）"),
    PHONE("phone", "强制手机"),
    TABLET("tablet", "强制平板"),
    TV("tv", "强制 TV");

    companion object {
        fun fromStorage(value: String?): UiModePreference =
            values().firstOrNull { it.storageValue == value } ?: AUTO

        fun next(current: UiModePreference): UiModePreference {
            val all = values()
            return all[(current.ordinal + 1) % all.size]
        }
    }
}

object UiModeDetector {
    private const val PREFS_NAME = "iptv_user_prefs"
    private const val KEY_UI_MODE_OVERRIDE = "ui_mode_override"

    /**
     * 检测当前设备应该使用哪种 UI 模式。
     * 优先级：设置页手动指定 > 调试文件/开关 > 系统声明 > 硬件特征 > 大屏触摸（平板）。
     */
    fun detect(context: Context): UiMode {
        // 0. 设置页手动指定：强制按所选形态渲染，不再看设备实际形态
        when (readOverride(context)) {
            UiModePreference.PHONE -> {
                Log.i("UiModeDetector", "override -> PHONE")
                return UiMode.PHONE
            }
            UiModePreference.TABLET -> {
                Log.i("UiModeDetector", "override -> TABLET")
                return UiMode.TABLET
            }
            UiModePreference.TV -> {
                Log.i("UiModeDetector", "override -> TV")
                return UiMode.TV
            }
            UiModePreference.AUTO -> Unit
        }

        // 0.1 用户强制 TV 模式（调试/模拟器用，保留旧开关）
        try {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            if (prefs.getBoolean("force_tv_mode", false)) {
                return UiMode.TV
            }
        } catch (_: Exception) {}

        // 0.2 文件标志强制 TV 模式（adb shell touch /sdcard/force_tv_mode）
        try {
            val extDir = context.getExternalFilesDir(null)
            if (java.io.File(extDir, "force_tv_mode").exists() ||
                java.io.File("/sdcard/force_tv_mode").exists()
            ) {
                Log.i("UiModeDetector", "force_tv_mode -> TV")
                return UiMode.TV
            }
        } catch (_: Exception) {}

        // 0.3 文件标志强制手机模式（模拟器调试用）
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

        // 5. 大屏触摸设备 → 平板（触摸布局，交互与手机一致）
        if (sw >= 600) {
            Log.i("UiModeDetector", "big screen touch sw=${sw}dp -> TABLET")
            return UiMode.TABLET
        }

        return UiMode.PHONE
    }

    private fun readOverride(context: Context): UiModePreference {
        return try {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            UiModePreference.fromStorage(prefs.getString(KEY_UI_MODE_OVERRIDE, "auto"))
        } catch (_: Exception) {
            UiModePreference.AUTO
        }
    }

    /**
     * 是否手持设备（手机/平板）：只有手持设备允许自动进入画中画。
     *
     * 判定：
     * - 无触屏 → 非手持（TV/盒子）
     * - 最短边 < 600dp → 手机，手持
     * - 大屏且原生竖屏 → 平板，手持
     * - 大屏且原生横屏 → 车机/电视一体屏，非手持
     *
     * 不能只看 uiMode：车机通常声明 touchscreen/telephony/camera，uiMode 也不是 TELEVISION。
     */
    fun isHandheld(context: Context): Boolean {
        val pm = context.packageManager
        if (!pm.hasSystemFeature("android.hardware.touchscreen")) return false
        val config = context.resources.configuration
        val sw = minOf(config.screenWidthDp, config.screenHeightDp)
        if (sw < 600) return true
        return !isNaturalLandscape(context, config)
    }

    /** 屏幕物理原生方向是否横屏（车机/电视一体屏为 true，竖屏平板为 false） */
    private fun isNaturalLandscape(context: Context, config: Configuration): Boolean {
        val rotation = try {
            @Suppress("DEPRECATION")
            (context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.rotation
        } catch (_: Exception) {
            0
        }
        val landscapeNow = config.screenWidthDp > config.screenHeightDp
        // rotation 0/2 时宽高与物理方向一致；1/3 时宽高互换
        return if (rotation == 0 || rotation == 2) landscapeNow else !landscapeNow
    }
}
