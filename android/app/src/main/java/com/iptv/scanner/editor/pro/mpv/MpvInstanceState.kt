package com.iptv.scanner.editor.pro.mpv

/**
 * mpv native 实例状态。
 *
 * 由于 native mpv 是单例（一个 JNI 句柄），所有 MPVView/MPVTextureView 实例
 * 共享同一份 [MpvInstanceState]。多画面模式下通过 generation 机制确保只有
 * 最新创建的 View 能操作 native 实例。
 *
 * @see MPVView.instanceState
 */
class MpvInstanceState {
    @Volatile
    var nativeInstanceAlive: Boolean = false

    @Volatile
    var nativeInstanceCreated: Boolean = false

    @Volatile
    var nativeHandleCreated: Boolean = false

    /**
     * mpv 核心已因 MPV_EVENT_SHUTDOWN 终止（进程内不可恢复）。
     *
     * 与 [nativeHandleCreated] 的区别：句柄对象仍然存在（JNI 侧未释放），
     * 但核心已经 terminate，任何 setOptionString/init 调用都会在已终止的
     * 句柄上执行并触发 native 崩溃。此标记置位后禁止再次初始化，
     * 由上层降级到备用内核。
     */
    @Volatile
    var nativeCoreDead: Boolean = false

    @Volatile
    var activeGeneration: Int = 0

    @Volatile
    var forceRecreatePending: Boolean = false

    @Volatile
    var savedPlaybackPath: String? = null
}