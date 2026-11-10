package com.iptv.scanner.editor.pro.mpv

import android.content.Context
import android.app.UiModeManager
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.util.AttributeSet
import android.util.Log
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View
import `is`.xyz.mpv.MPVLib
import com.iptv.scanner.editor.pro.NativeCrashLogger
import com.iptv.scanner.editor.pro.data.UserPrefs

/**
 * 基于 SurfaceView 的 MPV 视频渲染视图。
 *
 * 生命周期策略（keep-alive）：
 * - MPVLib.create() 只在进程首次使用 MPV 时调用一次
 * - MPVLib.destroy() **永远不调用**（进程退出时 OS 自动回收）
 * - 切换播放器时：destroy() 只做 stop + playlist-clear + detachSurface
 * - 切回 MPV 时：initialize() 复用实例，surfaceCreated() 重新 attachSurface + 设置 vo
 *
 * 根因：MPVLib.destroy() 在部分设备（如华为 Kirin arm64）上会 SIGSEGV，
 * 即使已先调用 stop() + detachSurface()。mpv 内部线程的清理时机不可控，
 * destroy() 可能在线程仍持有锁/资源时释放底层结构，导致 use-after-free。
 * keep-alive 策略从根本上避免 destroy() 调用，以内存换稳定性。
 *
 * 状态重置（防止多次复用后状态累积残留）：
 * - destroy() 中：stop + playlist-clear + vo=null + force-window=no + detachSurface
 * - surfaceCreated() 中：attachSurface + force-window=yes + vo=voInUse
 * - playlist-clear 清除 mpv 内部播放列表，防止旧 path 残留导致双重 loadfile
 * - vo=null → vo=voInUse 的切换强制 vo 模块重新初始化，防止渲染状态累积
 */
class MPVView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : SurfaceView(context, attrs), SurfaceHolder.Callback, MPVViewLike {

    init {
        // 首个实例构造时检测 arm32 TV（sanitizeHwdec 依赖该标记强制软解）
        if (arm32TvDetected == null) arm32TvDetected = computeArm32Tv(context.applicationContext)
    }

    /** mpv 实例状态（共享单例，所有 MPVView/MPVTextureView 引用同一份） */
    val instanceState = sharedState

    /** 公共逻辑委托 */
    private val delegate = BaseMPVViewDelegate(instanceState)

    // 保存初始化参数，用于 mpv 核心 shutdown 后重新创建实例
    private var savedConfigDir: String? = null
    private var savedCacheDir: String? = null
    private var savedHwdec: String = DEFAULT_HWDEC

    /**
     * Surface 是否当前已 attach 到 mpv。
     * 防止 double detachSurface 导致 native 崩溃：
     * surfaceDestroyed 和 destroy() 都会调用 detachSurface()，
     * 用此标志确保只 detach 一次。
     */
    @Volatile
    private var surfaceAttached = false

    /**
     * VO 延迟创建标志：surfaceCreated 时若拿不到有效尺寸，
     * 不建立 VO，等 surfaceChanged 提供真实尺寸后再创建，
     * 避免“先在 0x0 窗口上建 VO、再改尺寸”导致只有声音没画面。
     */
    @Volatile
    private var pendingVoUntilSize = false

    /**
     * mpv 核心重建回调。当 ensureInstanceAlive() 重新创建 mpv 实例后调用，
     * 让外部（MpvController）能重新注册 observeProperty 和同步状态。
     */
    override var onInstanceRecreated: (() -> Unit)? = null

/** 核心已不可用回调（shutdown 后无法重建，需上层降级到备用内核） */
override var onCoreUnavailable: (() -> Unit)? = null

/** Surface 重建回调（surfaceCreated 后触发） */
override var onSurfaceRebuilt: (() -> Unit)? = null

/** Surface 即将销毁回调（surfaceDestroyed 前触发） */
override var onSurfaceAboutToDestroy: (() -> Unit)? = null

    override fun asView(): View = this

    override fun initialize(
        configDir: String,
        cacheDir: String,
        vo: String,
        hwdec: String
    ) {
        // 核心已 terminate：nativeHandleCreated 仍为 true，但句柄指向已终止的核心。
        // 此时调用 setOptionString/init 会在死句柄上执行并 native 崩溃（SIGABRT/SIGSEGV），
        // 因此禁止再初始化，改为向上层报告核心不可用，由上层降级到备用内核。
        if (instanceState.nativeCoreDead) {
            Log.e(TAG, "initialize: mpv core already terminated in this process, " +
                "refusing to init on dead handle (avoid native crash)")
            instanceState.nativeInstanceCreated = false
            instanceState.nativeInstanceAlive = false
            onCoreUnavailable?.invoke()
            return
        }
        voInUse = vo
        savedConfigDir = configDir
        savedCacheDir = cacheDir
        // houdini 转译层（x86 模拟器）强制软解：硬解码器 teardown 会 SIGSEGV
        val effectiveHwdec = sanitizeHwdec(hwdec)
        savedHwdec = effectiveHwdec
        myGeneration = ++instanceState.activeGeneration
        Log.i(TAG, "initialize: generation=$myGeneration, vo=$vo, hwdec=$hwdec")

        if (instanceState.nativeInstanceCreated) {
            // 复用现有 native mpv 实例（不 destroy + create）
            Log.i(TAG, "initialize: reusing existing native mpv instance (generation=$myGeneration)")
            try {
                // 运行时更新 hwdec（vo 由 surfaceCreated 设置，此时 surface 还没创建）
                MPVLib.setPropertyString("hwdec", effectiveHwdec)
                // 会话内从硬解切到软解时，补开跳过类优化（init 阶段未设置）
                if (effectiveHwdec == "no") {
                    MPVLib.setPropertyString("vd-lavc-skiploopfilter", "all")
                    MPVLib.setPropertyString("vd-lavc-skipframe", "nonref")
                }
                // 更新日志等级（运行时可切换）
                updateLogLevel()
            } catch (e: Throwable) {
                Log.w(TAG, "initialize: reuse setPropertyString failed: ${e.message}")
            }
            // 清除 filePath，防止 surfaceCreated 走 filePath 分支加载旧路径
            filePath = null
            // 恢复旋转前的播放路径：destroy() 时保存了 path，
            // 新 MPVView 创建后 surfaceCreated 时自动恢复播放
            val savedPath = instanceState.savedPlaybackPath
            if (savedPath != null) {
                filePath = savedPath
                instanceState.savedPlaybackPath = null
                Log.i(TAG, "initialize: restored saved playback path=$savedPath, will play on surfaceCreated")
            }
            // 标记实例为活跃（surfaceDestroyed/destroy 会设为 false）
            instanceState.nativeInstanceAlive = true
            holder.setFormat(PixelFormat.RGBA_8888)
            holder.addCallback(this)
            return
        }

        // 首次创建或 shutdown 后重建：MPVLib.create + 完整初始化
        // 关键：如果 native 句柄已存在（keep-alive 策略下 destroy 永不调用），
        // 跳过 create() 直接 init()，避免 "mpv is already initialized" 错误导致 native 崩溃。
        // 场景：mpv 核心 shutdown 后 markInstanceDead() 重置 nativeInstanceCreated=false，
        // 但 native 句柄仍然存在，ensureInstanceAlive() 走重建路径时需要跳过 create()。
        if (instanceState.nativeHandleCreated) {
            Log.i(TAG, "initialize: native handle already exists, skipping create() (init only)")
        } else {
            Log.i(TAG, "initialize: creating new native mpv instance")
            MPVLib.create(context)
            instanceState.nativeHandleCreated = true
        }

        setOptionChecked("config", "yes")
        setOptionChecked("config-dir", configDir)
        for (opt in arrayOf("gpu-shader-cache-dir", "icc-cache-dir"))
            setOptionChecked(opt, cacheDir)

        setOptionChecked("vo", vo)
        setOptionChecked("hwdec", effectiveHwdec)
        // 所有编解码器都允许走 MediaCodec：避免 mpv 因个别 codec 不在默认清单里
        // 直接回落软解（低端电视上软解 1080i/4K 必掉帧）。
        setOptionChecked("hwdec-codecs", "all")
        // gpu / gpu-next 路径启用 PBO 上传：减少每帧 glTexImage2D 的同步拷贝开销。
        if (vo == "gpu" || vo == "gpu-next") {
            setOptionChecked("opengl-pbo", "yes")
        }
        // 记录本次会话实际生效的 hwdec：进程若因硬解 teardown native 崩溃，
        // 下次启动据此把该设备加入硬解黑名单
        NativeCrashLogger.setActiveHwdec(context, effectiveHwdec)
        // keep-open=always：stop 期间也保留最后一帧，避免换台黑屏闪烁。
        // 与 PC 端不同，Android 端在 loadfile 前会发送 stop（对齐 PC 端 play_file 的逻辑），
        // 用 always 确保 stop → loadfile 之间画面不消失。
        // yes 只在 EOF 时保留，stop 会清空画面；always 在 stop 时也保留。
        setOptionChecked("keep-open", "always")
        setOptionChecked("keepaspect", "yes")
        setOptionChecked("keepaspect-window", "no")
        // FBO 格式：根据 HDR 模式选择。
        // rgba16hf（16-bit 半浮点）允许 HDR 内容以高色深渲染，但很多 GPU（尤其
        // 电视盒子如 Homatics、部分 Mali/Adreno）不支持 16-bit 浮点帧缓冲，
        // EGL 初始化成功但 FBO 创建失败 → 黑屏（无画面）。
        // 默认用 rgba8（8-bit，全设备兼容），仅在 HDR 模式非 disable 时使用 rgba16hf。
        val hdrMode = UserPrefs.getInstance().getHdrMode()
        val fboFormat = if (hdrMode == "disable") "rgba8" else "rgba16hf"
        setOptionChecked("fbo-format", fboFormat)
        // 4K 安全选项：降低 GPU 渲染负担
        // - dither-depth：限制抖动深度为 8-bit，避免 4K 时 GPU 过载
        // - gpu-texture-resolution：限制 GPU 纹理分辨率（0=自动, 1=最高, 2=高, 3=中）
        setOptionChecked("dither-depth", "8")
        // target-colorspace-hint：仅 HDR 模式启用。
        // 部分设备显示控制器无法处理 colorspace 切换信号，会导致黑屏。
        if (hdrMode != "disable") {
            setOptionChecked("target-colorspace-hint", "yes")
        }

        setOptionChecked("framedrop", "all")
        setOptionChecked("video-sync", "audio")
        setOptionChecked("cache-pause-initial", "no")

        // 缓存大小：Android TV 内存有限（通常 1-2GB），过大的 demuxer 缓存在播放坏流时
        // 会导致 native 内存耗尽 → malloc 返回 null → SIGABRT 崩溃。
        // 16MiB 前向 + 4MiB 后向 + 4s 预读：直播场景足够，且不会在低内存设备上 OOM。
        // 4K 不再单独抬到 128MiB（大缓存只会放大坏流的破坏面，且换台时释放更慢）。
        setOptionChecked("demuxer-max-bytes", MpvProtocolConstants.DEMUXER_MAX_BYTES_DEFAULT)
        setOptionChecked("demuxer-max-back-bytes", MpvProtocolConstants.DEMUXER_MAX_BACK_BYTES)
        setOptionChecked("demuxer-readahead-secs", MpvProtocolConstants.DEMUXER_READAHEAD_SECS.toString())
        setOptionChecked("demuxer-seekable-cache", "yes")
        setOptionChecked("force-seekable", "yes")
        // 不等待缓存填满就开始播放，实现秒开（与 PC 端 cache-pause-initial=no 配合）
        setOptionChecked("demuxer-cache-wait", "no")

        // 网络超时：缩短到 8 秒（原来 30 秒太长）。
        // 坏流场景：mpv demuxer 线程会卡在网络读取上，30s 超时期间所有
        // 后续 loadfile 命令都无法执行，导致切到坏频道后所有频道都无法播放。
        // 8s 足够覆盖合法流的连接时间，同时配合 startTimeoutSwitchSource
        // 中的 stop 命令（5s 超时换源时先 stop 强制中断 demuxer）双重保障。
        setOptionChecked("network-timeout", "8")
        setOptionChecked("source-timeout", "8")
        setOptionChecked("stream-open-timeout", "8")
        // demuxer 读取超时：lavf 读取数据超时后触发 end-file 事件，
        // 防止坏流时 demuxer 无限重试消耗内存。
        setOptionChecked("demuxer-read-timeout", "5")

        setOptionChecked("stream-lavf-o", "verify=1")
        setOptionChecked("tls-verify", "yes")

        // 不再覆盖 vd-lavc-threads：交回 mpv 按 CPU 核数自动决定，
        // 避免在 2 核盒子上线程过多、在 4 核电视上线程过少。
        //
        // 仅在“确实会走软解”的低算力分支上开启跳过类优化；硬解时这些选项无效，
        // 但开启会牺牲画质，因此不做无条件设置。
        if (effectiveHwdec == "no") {
            setOptionChecked("vd-lavc-skiploopfilter", "all")
            setOptionChecked("vd-lavc-skipframe", "nonref")
        }

        // force-window 和 idle 必须在 init() 之前设置！
        // libmpv 的 mpv_set_option_string() 只在 mpv_initialize() 之前有效，
        // init() 之后调用会静默失败（返回错误码但代码未检查），导致选项从未生效。
        // - force-window=no：无文件时不创建视频窗口（避免空窗口占用 GPU 资源）
        // - idle=yes：mpv 核心永不自动退出，即使文件加载失败也保持存活。
        //   原来用 idle=once，但文件加载失败后核心会自动 shutdown（触发
        //   MPV_EVENT_SHUTDOWN），而 keep-alive 策略下无法重新 create() 或
        //   init()（native 句柄已存在且无法被 destroy），导致应用崩溃。
        //   idle=yes 确保核心在任何情况下都不会自动关闭，从根本上避免
        //   需要重建核心的场景。
        setOptionChecked("force-window", "no")
        setOptionChecked("idle", "yes")

        MPVLib.init()

        updateLogLevel()

        instanceState.nativeInstanceAlive = true
        instanceState.nativeInstanceCreated = true

        holder.setFormat(PixelFormat.RGBA_8888)
        holder.addCallback(this)
        observeProperties()
    }

    /**
     * 更新 mpv 日志等级（运行时切换）。
     * 通过 setPropertyString("msg-level", ...) 实现，无需重启。
     */
    private fun updateLogLevel() = delegate.updateLogLevel()

    /**
     * 写入 mpv 选项并检查返回值（0 = 成功）。
     *
     * libmpv 在 init() 之后调用 mpv_set_option_string() 会返回错误码，
     * 原实现忽略返回值，导致选项静默失效后无从排查。
     */
    private fun setOptionChecked(name: String, value: String) {
        val rc = try {
            MPVLib.setOptionString(name, value)
        } catch (e: Throwable) {
            Log.e(TAG, "setOption $name=$value FAILED", e)
            return
        }
        if (rc != 0) {
            Log.e(TAG, "setOption $name=$value rejected by mpv (rc=$rc)")
        }
    }

    override fun destroy() {
        holder.removeCallback(this)
        if (myGeneration != instanceState.activeGeneration) {
            Log.i(TAG, "destroy: skipped (myGen=$myGeneration, activeGen=$instanceState.activeGeneration)")
            return
        }
        // 保存当前播放路径，供新 MPVView 恢复播放（旋转时 AndroidView 可能被销毁重建）
        val currentPath = try { MPVLib.getPropertyString("path") } catch (_: Exception) { null }
        if (!currentPath.isNullOrEmpty()) {
            instanceState.savedPlaybackPath = currentPath
            Log.i(TAG, "destroy: saved playback path=$currentPath")
        }
        // keep-alive：不调用 MPVLib.destroy()，只做状态重置
        pendingVoUntilSize = false
        if (instanceState.nativeInstanceAlive) {
            try {
                MPVLib.command(arrayOf("stop"))
                MPVLib.command(arrayOf("playlist-clear"))
                MPVLib.setPropertyString("force-window", "no")
                MPVLib.setPropertyString("vo", "null")
                // 只 detach 一次：surfaceDestroyed 可能已经 detach 过
                if (surfaceAttached) {
                    MPVLib.detachSurface()
                    surfaceAttached = false
                }
            } catch (e: Throwable) {
                Log.w(TAG, "destroy: reset failed: ${e.message}")
            }
            instanceState.nativeInstanceAlive = false
            Log.i(TAG, "destroy: instance kept alive, state reset (gen=$myGeneration)")
        }
    }

    private fun observeProperties() = delegate.observeProperties()

    private var filePath: String? = null
    private var voInUse: String = DEFAULT_VO

    @Volatile
    private var myGeneration: Int = 0

    @Volatile
    override var pendingResumePos: Double = -1.0

    override fun setVoInUse(vo: String) {
        voInUse = vo
    }

    override val isSurfaceValid: Boolean
        get() = holder.surface != null && holder.surface.isValid

    /** 核心是否已终止（进程内不可恢复） */
    override val isCoreDead: Boolean
        get() = instanceState.nativeCoreDead

    /**
     * 运行时强制重新初始化 VO 模块（detach → vo=null → reattach → vo=newVo）。
     *
     * 根因：仅 setPropertyString("vo", newVo) 在部分设备上不会真正释放旧 VO 模块
     * 并初始化新 VO。例如从 gpu（EGL）切换到 mediacodec_embed（Surface 直渲），
     * mpv 可能仍使用旧 gpu VO 导致黑屏。
     *
     * 本方法通过完整的 detach/reattach 循环强制 VO 模块重建：
     * 1. force-window=no + vo=null + detachSurface → 释放旧 VO 资源
     * 2. attachSurface + force-window=yes + vo=newVo → 初始化新 VO
     *
     * 调用后需重新 loadfile 触发新 VO 渲染。
     */
    override fun reattachSurfaceWithVo(vo: String) {
        voInUse = vo
        Log.i(TAG, "reattachSurfaceWithVo: switching to vo=$vo")
        try {
            // Step 1: 释放当前 VO 模块
            MPVLib.setPropertyString("force-window", "no")
            MPVLib.setPropertyString("vo", "null")
            if (surfaceAttached) {
                MPVLib.detachSurface()
                surfaceAttached = false
            }
            Log.i(TAG, "reattachSurfaceWithVo: detached old VO")

            // Step 2: 重新 attach surface 并设置新 VO
            val s = holder.surface
            if (s != null && s.isValid) {
                MPVLib.attachSurface(s)
                surfaceAttached = true
                // 与 surfaceCreated 保持一致：尺寸先于 VO 写入
                val size = surfaceSizeString(holder)
                if (size != null) {
                    MPVLib.setPropertyString("android-surface-size", size)
                }
                if (vo == "gpu" || vo == "gpu-next") {
                    MPVLib.setPropertyString("opengl-pbo", "yes")
                }
                MPVLib.setPropertyString("force-window", "yes")
                MPVLib.setPropertyString("vo", vo)
                Log.i(TAG, "reattachSurfaceWithVo: attached surface with vo=$vo, surface=${surfaceSizeString(holder) ?: "unknown"}")
            } else {
                // Surface 不可用：只设置 vo，等 surfaceCreated 回调时 attach
                MPVLib.setPropertyString("vo", vo)
                Log.w(TAG, "reattachSurfaceWithVo: surface not valid, vo set without reattach")
            }
        } catch (e: Throwable) {
            Log.e(TAG, "reattachSurfaceWithVo failed", e)
        }
    }

    /**
     * 诊断信息：返回当前 VO、hwdec、surface 状态、视频尺寸等。
     * 用于日志输出和用户报告问题时的诊断。
     */
    override fun getDiagnosticInfo(): String {
        val vo = try { MPVLib.getPropertyString("vo") ?: "unknown" } catch (_: Throwable) { "error" }
        val hwdec = try { MPVLib.getPropertyString("hwdec") ?: "unknown" } catch (_: Throwable) { "error" }
        val hwdecCurrent = try { MPVLib.getPropertyString("hwdec-current") ?: "none" } catch (_: Throwable) { "error" }
        val videoFormat = try { MPVLib.getPropertyString("video-format") ?: "none" } catch (_: Throwable) { "error" }
        val width = try { MPVLib.getPropertyInt("width") ?: 0 } catch (_: Throwable) { -1 }
        val height = try { MPVLib.getPropertyInt("height") ?: 0 } catch (_: Throwable) { -1 }
        val surfaceValid = holder.surface?.isValid ?: false
        return "vo=$vo, hwdec=$hwdec, hwdec-current=$hwdecCurrent, " +
            "video-format=$videoFormat, ${width}x${height}, " +
            "surfaceValid=$surfaceValid, voInUse=$voInUse"
    }


    override fun playFile(path: String) {
        // 确保 mpv 核心存活：如果核心已 shutdown，先重新创建
        if (!ensureInstanceAlive()) {
            Log.e(TAG, "playFile: mpv instance not alive, cannot play")
            // 不再静默失败：让上层把「核心不可用」暴露给界面并触发降级
            onCoreUnavailable?.invoke()
            return
        }
        val s = holder.surface
        if (s != null && s.isValid) {
            MPVLib.command(arrayOf("loadfile", path))
            MPVLib.setPropertyBoolean("pause", false)
        } else {
            filePath = path
        }
    }

    /**
     * 标记 native mpv 实例已死亡（由 MPV_EVENT_SHUTDOWN 触发）。
     *
     * mpv 核心在某些坏流场景下会自动 shutdown（如加载无法解析的 m3u8），
     * shutdown 后所有 MPVLib 命令都发到已死的实例上，静默失败。
     * 此方法重置 instanceState.nativeInstanceCreated 标志，使下次 initialize/ensureInstanceAlive
     * 能重新创建 mpv 实例。
     */
    override fun markInstanceDead() = delegate.markInstanceDead()

    /**
     * 确保 mpv 核心存活。如果核心已 shutdown，使用保存的参数重新创建。
     *
     * @return true 如果核心存活（原本就活着或成功重建），false 如果无法重建
     */
    private fun ensureInstanceAlive(): Boolean {
        // 核心已 terminate 且句柄未释放：进程内无法安全重建（destroy 会 SIGSEGV，
        // 在死句柄上 init 会 native 崩溃），直接返回 false 让上层降级。
        if (instanceState.nativeCoreDead) {
            Log.e(TAG, "ensureInstanceAlive: mpv core terminated in-process, cannot recreate")
            return false
        }
        // 检查强制重建标志：forceRecreate() 已通过 stop+playlist-clear 重置状态
        if (instanceState.forceRecreatePending) {
            instanceState.forceRecreatePending = false
            Log.i(TAG, "ensureInstanceAlive: instanceState.forceRecreatePending=true, state already reset by forceRecreate()")
            // idle=yes 确保核心仍然存活，forceRecreate 只做了状态重置（stop + playlist-clear），
            // 不需要重建核心。如果核心确实已 shutdown（极端情况），下面的检查会处理。
        }
        // 核心存活检查：如果核心已创建且活跃，直接返回
        if (instanceState.nativeInstanceCreated && instanceState.nativeInstanceAlive) {
            return true
        } else if (instanceState.nativeInstanceCreated && !instanceState.nativeHandleCreated) {
            // nativeInstanceCreated=true 但 nativeInstanceAlive=false 且无 native 句柄：
            // 实例存在但未活跃（destroy() 后状态），surfaceCreated 会恢复
            return true
        } else if (instanceState.nativeInstanceCreated) {
            // nativeInstanceCreated=true + nativeHandleCreated=true 但 nativeInstanceAlive=false：
            // mpv 核心已 shutdown（markInstanceDead），native 句柄仍存在（keep-alive）。
            // idle=yes 下核心不应 shutdown，但若发生，返回 false 防止在已死句柄上操作。
            Log.w(TAG, "ensureInstanceAlive: instance created but not alive (core shutdown?), returning false")
            return false
        }
        // 核心 shutdown 后需要重建（idle=yes 下不应发生，此处为安全兜底）
        // 安全检查：如果 native 句柄已存在（keep-alive），不要尝试在已终止的句柄上
        // 调用 setOptionString/init —— libmpv 的 mpv_initialize() 只能调用一次，
        // 在已终止的句柄上调用会导致 native 崩溃（SIGABRT）。
        // 此时返回 false，让 playFile 跳过本次播放，避免崩溃。
        if (instanceState.nativeHandleCreated) {
            Log.e(TAG, "ensureInstanceAlive: core has shutdown but native handle still exists (keep-alive). " +
                "Cannot safely re-initialize. Returning false to avoid native crash.")
            return false
        }
        val configDir = savedConfigDir ?: return false
        val cacheDir = savedCacheDir ?: return false
        Log.i(TAG, "ensureInstanceAlive: re-creating mpv instance after shutdown")
        try {
            // instanceState.nativeInstanceCreated 为 false（首次创建或 native 句柄不存在），
            // 走完整初始化路径：create() + setOptionString + init() + observeProperties()。
            initialize(configDir, cacheDir, vo = voInUse, hwdec = savedHwdec)
            // 重新 attach surface（initialize 中已 addCallback，但 surface 可能已存在）
            val s = holder.surface
            if (s != null && s.isValid) {
                MPVLib.attachSurface(s)
                MPVLib.setPropertyString("force-window", "yes")
                MPVLib.setPropertyString("vo", voInUse)
                Log.i(TAG, "ensureInstanceAlive: surface re-attached")
            }
            // 通知外部（MpvController）核心已重建，重新注册 observeProperty
            onInstanceRecreated?.invoke()
            return true
        } catch (e: Throwable) {
            Log.e(TAG, "ensureInstanceAlive: re-create failed", e)
            // 恢复状态：重建失败时标记为死亡，下次 playFile 会再次尝试
            instanceState.nativeInstanceCreated = false
            instanceState.nativeInstanceAlive = false
            return false
        }
    }

    override fun stop() = delegate.stop()

    // ---- SurfaceHolder.Callback ----

    override fun surfaceCreated(holder: SurfaceHolder) {
        if (!instanceState.nativeInstanceCreated || !instanceState.nativeInstanceAlive) {
            Log.w(TAG, "surfaceCreated: skipped, instanceState.nativeInstanceCreated=$instanceState.nativeInstanceCreated, instanceState.nativeInstanceAlive=$instanceState.nativeInstanceAlive")
            return
        }
        Log.i(TAG, "surfaceCreated: attaching surface (vo=$voInUse)")
        try {
            MPVLib.attachSurface(holder.surface)
            surfaceAttached = true
        } catch (e: Throwable) {
            Log.e(TAG, "surfaceCreated: attachSurface FAILED", e)
        }

        // 关键顺序：android-surface-size 必须先于 VO 建立写入。
        //
        // 旧实现是 vo=null → force-window=yes → vo=voInUse，而尺寸要等后面的
        // surfaceChanged 才写入。VO 因此在“尺寸未知（0x0）”的窗口上完成初始化，
        // 部分 GPU/驱动此后不会重连 BufferQueue，表现为只有声音没有画面；
        // 只有再完整重建一次 VO（用户切一次 VO / 旋转）才恢复。
        //
        // 现在：有尺寸就“先写尺寸再建 VO”；拿不到尺寸就完全推迟到 surfaceChanged。
        val size = surfaceSizeString(holder)
        if (size != null) {
            MPVLib.setPropertyString("android-surface-size", size)
            createVoNow(size)
            loadPendingPathAfterSurface()
        } else {
            pendingVoUntilSize = true
            Log.i(TAG, "surfaceCreated: 尺寸未知，VO 延迟到 surfaceChanged 建立")
        }

        // 通知 MpvController 取消 pendingEndFileError，防止旋转后误报断流
        onSurfaceRebuilt?.invoke()
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        if (width <= 0 || height <= 0) {
            Log.w(TAG, "surfaceChanged: invalid size ${width}x$height, VO state unchanged")
            return
        }
        val size = "${width}x$height"
        MPVLib.setPropertyString("android-surface-size", size)
        if (pendingVoUntilSize) {
            pendingVoUntilSize = false
            Log.i(TAG, "surfaceChanged: 尺寸就绪($size)，现在建立 VO")
            createVoNow(size)
            loadPendingPathAfterSurface()
        }
    }

    /** 当前 Surface 的有效尺寸；拿不到返回 null（0x0 视为无效） */
    private fun surfaceSizeString(holder: SurfaceHolder): String? = try {
        val frame = holder.surfaceFrame
        if (frame != null && frame.width() > 0 && frame.height() > 0) {
            "${frame.width()}x${frame.height()}"
        } else {
            null
        }
    } catch (_: Throwable) {
        null
    }

    /**
     * 在当前 Surface 上建立 VO（尺寸已先写入）。
     * 不再使用 vo=null 的写法，避免在尺寸未知时创建 VO。
     */
    private fun createVoNow(size: String) {
        try {
            if (voInUse == "gpu" || voInUse == "gpu-next") {
                MPVLib.setPropertyString("opengl-pbo", "yes")
            }
            MPVLib.setPropertyString("force-window", "yes")
            MPVLib.setPropertyString("vo", voInUse)
            Log.i(TAG, "createVoNow: vo=$voInUse, surface=$size")
        } catch (e: Throwable) {
            Log.e(TAG, "createVoNow FAILED vo=$voInUse", e)
        }
    }

    /**
     * VO 就绪后加载待播放路径。
     *
     * 文件已在播放时也需要重新 loadfile：重建解码器→VO 管线，
     * 确保视频帧正确输出到新 Surface（与 MPVTextureView 行为对齐）。
     */
    private fun loadPendingPathAfterSurface() {
        if (filePath != null) {
            Log.i(TAG, "surfaceCreated: 播放缓存的 filePath=$filePath")
            MPVLib.command(arrayOf("loadfile", filePath as String))
            MPVLib.setPropertyBoolean("pause", false)
            filePath = null
            return
        }
        try {
            val currentPath = MPVLib.getPropertyString("path")
            if (!currentPath.isNullOrEmpty()) {
                Log.i(TAG, "surfaceCreated: re-loading current path=$currentPath to restore render")
                // pause 是核心属性、跨 loadfile 保持：先读后还原，
                // 用户暂停时旋转不应被强制续播（新文件分支的 pause=false 才是播放意图）
                val wasPaused = try { MPVLib.getPropertyBoolean("pause") } catch (_: Exception) { false }
                MPVLib.command(arrayOf("loadfile", currentPath))
                MPVLib.setPropertyBoolean("pause", wasPaused == true)
            } else {
                Log.i(TAG, "surfaceCreated: no pending filePath, waiting for external playFile")
            }
        } catch (e: Throwable) {
            Log.w(TAG, "loadPendingPathAfterSurface failed: ${e.message}")
        }
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        if (!instanceState.nativeInstanceAlive) {
            Log.i(TAG, "surfaceDestroyed: native instance not active, skipping")
            return
        }
        // 通知 MpvController 提前设置 suppressFileErrorFlag，
        // 防止 surfaceCreated 重新 loadfile 触发的 END_FILE 事件误报断流
        onSurfaceAboutToDestroy?.invoke()
        pendingVoUntilSize = false
        Log.i(TAG, "surfaceDestroyed: detaching surface")
        try {
            if (surfaceAttached) {
                MPVLib.detachSurface()
                surfaceAttached = false
            }
        } catch (e: Throwable) {
            Log.w(TAG, "surfaceDestroyed: detachSurface failed: ${e.message}")
        }
    }

    companion object {
        private const val TAG = "MPVView"

        const val DEFAULT_VO = "gpu"
        const val DEFAULT_HWDEC = "auto-copy"

        internal val sharedState = MpvInstanceState()

        /** houdini 检测结果缓存 */
        @Volatile
        private var houdiniDetected: Boolean? = null

        /** arm32 TV 检测结果缓存（首个 MPVView 实例初始化时计算） */
        @Volatile
        private var arm32TvDetected: Boolean? = null

        /**
         * 是否为 arm32 TV 设备（TV 模式 + armeabi-v7a 主 ABI 且无 arm64）。
         * 由首个 MPVView 实例构造时计算（UiModeManager 需要 Context）。
         */
        private fun computeArm32Tv(context: Context): Boolean = try {
            val uiMode = (context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager)
                ?.currentModeType
            val isTv = uiMode == Configuration.UI_MODE_TYPE_TELEVISION
            val abis = android.os.Build.SUPPORTED_ABIS
            isTv && abis.any { it.startsWith("armeabi") } && abis.none { it == "arm64-v8a" }
        } catch (_: Throwable) {
            false
        }

        /**
         * 是否运行在 houdini ARM 转译层上（x86 模拟器执行 arm64 libmpv）。
         * 转译层下 MediaCodec 硬解码器的销毁（切台 stop / loadfile replace /
         * mpv_terminate_destroy 均触发）会 SIGSEGV 空指针（fault addr 0x48，
         * backtrace 全在 libhoudini.so 内部），唯一规避是禁用硬解走软解。
         * 真机（原生 arm64）不存在 houdini，不受影响。
         */
        fun isHoudiniTranslation(): Boolean {
            val cached = houdiniDetected
            if (cached != null) return cached
            val detected = try {
                java.io.File("/system/vendor/lib64/libhoudini.so").exists() ||
                    java.io.File("/system/lib64/libhoudini.so").exists() ||
                    java.io.File("/system/lib/libhoudini.so").exists() ||
                    android.os.Build.HARDWARE.contains("ranchu")
            } catch (_: Throwable) {
                false
            }
            houdiniDetected = detected
            return detected
        }

        /** 本会话内的硬解降级（软解）：一旦置位，所有 sanitizeHwdec 都返回 "no" */
        @Volatile
        private var sessionHwdecOverride: String? = null

        /**
         * 用户在设置页显式选择硬解：本次进程内允许越过崩溃黑名单，
         * 给一次“解除黑名单”的机会（若仍崩溃，NativeCrashLogger 会重新写入）。
         * 注意：arm32 TV / houdini 的设备级强制软解不受此标志影响。
         */
        @Volatile
        private var userForcedHardwareDecode = false

        fun confirmHardwareDecodeByUser() {
            userForcedHardwareDecode = true
            Log.w(TAG, "hwdec: user explicitly selected hardware decode, blacklist override enabled for this session")
        }

        /**
         * 硬解失败后的会话级降级：本次进程内强制软解，避免继续走同一条
         * MediaCodec teardown 路径（历史出问题的车机在设备判定不成立时仍会崩溃）。
         */
        fun forceSoftwareDecodeForSession(reason: String) {
            if (sessionHwdecOverride == "no") return
            sessionHwdecOverride = "no"
            Log.w(TAG, "hwdec: session-level downgrade to software decode ($reason)")
        }

        /** 是否处于会话级软解降级 */
        fun hasSessionHwdecOverride(): Boolean = sessionHwdecOverride != null

        /**
         * 解除会话级软解降级，允许重新尝试硬解。
         *
         * 由“换台 / 重新打开播放页 / 用户手动修改 hwdec”触发，
         * 避免一次坏流导致的降级在进程内永久生效（用户看到的症状是
         * “选回硬解也还是卡”）。
         */
        fun clearSessionHwdecOverride(reason: String) {
            if (sessionHwdecOverride == null) return
            sessionHwdecOverride = null
            Log.w(TAG, "hwdec: session-level software downgrade cleared ($reason)")
        }

        /** 返回应生效的 hwdec 值：会话降级 / houdini 转译 / arm32 TV / 崩溃黑名单 强制软解 */
        fun sanitizeHwdec(hwdec: String): String {
            if (hwdec == "no") return hwdec
            if (sessionHwdecOverride != null) return sessionHwdecOverride!!
            // 设备黑名单：上次会话硬解异常退出（native 崩溃）后本进程强制软解。
            // 覆盖按频道保存的 hwdec（频道设置不走 PlayerSettingsStore），
            // 避免历史出问题的车机因设备判定不成立而再次走到硬解 teardown 崩溃路径。
            // 用户显式选择硬解时允许越过黑名单（见 confirmHardwareDecodeByUser）。
            val blacklisted = try {
                UserPrefs.getInstance().isHwdecBlacklisted()
            } catch (e: Exception) {
                false
            }
            return when {
                blacklisted && !userForcedHardwareDecode -> {
                    Log.w(TAG, "hwdec: device in crash blacklist -> force software decode")
                    "no"
                }
                isHoudiniTranslation() || arm32TvDetected == true -> {
                    Log.w(TAG, "hwdec: houdini=${isHoudiniTranslation()} arm32Tv=$arm32TvDetected -> force software decode (avoid MediaCodec teardown SIGSEGV)")
                    "no"
                }
                else -> hwdec
            }
        }
    }

    /**
     * 强制重置 mpv 核心状态（不终止核心）。
     *
     * 用于连续超时换源场景：当 stop 命令无法清除卡死的 demuxer 时，
     * 通过 stop + playlist-clear + vo 重置来强制清除内部状态。
     *
     * 关键变更：不再发送 quit 命令！
     * 原实现发送 quit 终止 mpv 核心，然后尝试通过 ensureInstanceAlive() 重建。
     * 但 keep-alive 策略下 native 句柄无法被 destroy()（会 SIGSEGV），
     * 而 MPVLib.create() 检测到句柄已存在会拒绝创建（"mpv is already initialized"），
     * 导致 init() 在已终止的句柄上执行 → native 崩溃。
     *
     * 配合 idle=yes，mpv 核心永不自动关闭，forceRecreate 只需重置状态而非重建核心。
     * demuxer-read-timeout=5 确保卡死的 demuxer 最终会超时释放。
     */
    override fun forceRecreate() = delegate.forceRecreate()
}
