package com.iptv.scanner.editor.pro.mpv

/**
 * MPV 协议相关常量。
 *
 * 统一管理 user-agent、超时、缓冲区大小等硬编码值。
 */
object MpvProtocolConstants {
    const val USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    const val FCC_USER_AGENT = "VLC/3.0.18Libmpv"

    /**
     * ffmpeg `rw_timeout` 选项的单位是**微秒**。
     * 该值经 `stream-lavf-o` 传给 libavformat，不是 mpv 的秒级超时。
     *
     * 注意：这版 libmpv 的 `--source-timeout` / `--stream-open-timeout` /
     * `--demuxer-read-timeout` 三个选项都不存在（启动日志 rc=-5），
     * 所以“慢源按时放弃”只能靠 `network-timeout` + 这里的 `rw_timeout`，
     * “卡死的 demuxer 被释放”靠 startTimeoutSwitchSource 的 stop。
     */
    const val NETWORK_RW_TIMEOUT_US = 8_000_000
    const val FCC_RW_TIMEOUT_US = 30_000_000

    /** 网络无响应超时（秒），这版 mpv 真实支持的超时属性 */
    const val NETWORK_TIMEOUT_SEC = 8

    /**
     * demuxer 预算：直播场景 16MiB 前向足够，且低内存设备（1-2GB）不会 OOM；
     * 4K 不再单独抬升（大缓存只会放大坏流破坏面、拖慢换台释放）。
     */
    const val DEMUXER_MAX_BYTES_DEFAULT = "16MiB"
    const val DEMUXER_MAX_BACK_BYTES = "4MiB"
    const val DEMUXER_READAHEAD_SECS = 4
}