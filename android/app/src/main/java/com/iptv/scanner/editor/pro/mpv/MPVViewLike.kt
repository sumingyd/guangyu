package com.iptv.scanner.editor.pro.mpv

import android.view.View

interface MPVViewLike {
var onInstanceRecreated: (() -> Unit)?
/** 核心已不可用（shutdown 后无法重建）回调，MpvController 注册以向界面暴露错误 */
var onCoreUnavailable: (() -> Unit)?
/** Surface 重建回调（surfaceCreated 后触发），MpvController 注册以取消 pendingEndFileError */
var onSurfaceRebuilt: (() -> Unit)?
/** Surface 即将销毁回调（surfaceDestroyed 前触发），MpvController 注册以提前设置 suppressFileErrorFlag */
var onSurfaceAboutToDestroy: (() -> Unit)?
/** mpv 核心是否已终止（进程内不可恢复） */
val isCoreDead: Boolean
var pendingResumePos: Double
val isSurfaceValid: Boolean
    fun initialize(configDir: String, cacheDir: String, vo: String, hwdec: String)
    fun destroy()
    fun playFile(path: String)
    fun stop()
    fun forceRecreate()
    fun markInstanceDead()
    fun reattachSurfaceWithVo(vo: String)
    fun getDiagnosticInfo(): String
    fun setVoInUse(vo: String)
    fun asView(): View
}
