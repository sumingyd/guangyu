package com.iptv.scanner.editor.pro.mpv.controller

import com.iptv.scanner.editor.pro.mpv.MPVViewLike

/**
 * 子控制器访问门面资源的接口，避免循环依赖。
 *
 * MpvController 门面实现此接口，子控制器通过它访问：
 * - postOnUiThread：把命令 post 到 MPVView 线程（mpv 要求同线程访问）
 * - getMpvView：获取当前绑定的 MPVView 实例
 * - isFileLoaded：查询文件是否已加载（StateFlow 同步可读）
 * - getCurrentVolume：查询当前音量（StateFlow 同步可读）
 */
interface MpvControllerHost {
    fun postOnUiThread(block: () -> Unit)
    fun getMpvView(): MPVViewLike?
    fun isFileLoaded(): Boolean
    fun getCurrentVolume(): Int
    /** mpv 核心是否已终止（进程内不可恢复），用于拒绝无效播放请求 */
    fun isCoreDead(): Boolean
    /** 向界面暴露「播放器核心不可用」错误（不再静默失败） */
    fun notifyPlaybackUnavailable()
}