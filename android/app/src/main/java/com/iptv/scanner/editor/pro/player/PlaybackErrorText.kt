package com.iptv.scanner.editor.pro.player

import androidx.media3.common.PlaybackException

/**
 * 把底层播放错误翻译成用户能照做的下一步动作。
 *
 * 原始错误仍由调用方写日志；界面上只展示分类后的建议，
 * 避免把 URL、解码器名或异常堆栈直接丢给用户。
 */
fun playbackErrorHint(message: String?, errorCode: Int? = null): String {
    when (errorCode) {
        PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED,
        PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED,
        PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED,
        PlaybackException.ERROR_CODE_PARSING_MANIFEST_UNSUPPORTED ->
            return "媒体格式无法识别，请刷新线路或切换播放内核"

        PlaybackException.ERROR_CODE_DECODING_FAILED,
        PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED,
        PlaybackException.ERROR_CODE_DECODER_INIT_FAILED,
        PlaybackException.ERROR_CODE_DECODER_QUERY_FAILED ->
            return "设备解码不支持，请切换软解或降低清晰度"

        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
        PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
        PlaybackException.ERROR_CODE_IO_UNSPECIFIED ->
            return "网络连接失败，请检查网络后重试"
    }

    val text = message.orEmpty()
    val lower = text.lowercase()
    fun has(vararg keys: String) = keys.any { lower.contains(it) }
    return when {
        has("401", "403", "unauthorized", "forbidden", "鉴权", "无权限") ->
            "登录或权限失效，请刷新线路后重试"
        has("404", "410", "not found", "链接已失效", "地址失效") ->
            "链接已失效，请刷新线路后重试"
        has("drm", "encrypted", "加密", "license") ->
            "该频道需要授权，当前无法播放"
        has("timeout", "超时", "network", "connection", "unable to resolve host",
            "failed to connect", "网络") ->
            "网络连接失败，请检查网络后重试"
        has("audio", "音频", "mp2", "ac3", "eac3", "dts") ->
            "音频解码失败，请切换播放内核或换台"
        has("decode", "解码", "mediacodec", "decoder") ->
            "设备解码不支持，请切换软解或降低清晰度"
        has("m3u8", "manifest", "container", "parser", "格式", "malformed") ->
            "媒体格式无法识别，请刷新线路或切换播放内核"
        else -> "播放失败，请检查网络或切换频道后重试"
    }
}
