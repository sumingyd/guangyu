package com.iptv.scanner.editor.pro.data.store

import android.content.SharedPreferences

/**
 * 网络设置域存储：HTTP Referer / Proxy / Headers。
 *
 * 仅对 MPV 播放器生效（通过 setPropertyString 下发到 mpv）。
 */
class NetworkSettingsStore(private val prefs: SharedPreferences) {

    fun getHttpReferer(): String = prefs.getString(KEY_HTTP_REFERER, "") ?: ""
    fun setHttpReferer(value: String) {
        prefs.edit().putString(KEY_HTTP_REFERER, value).apply()
    }

    fun getHttpProxy(): String = prefs.getString(KEY_HTTP_PROXY, "") ?: ""
    fun setHttpProxy(value: String) {
        prefs.edit().putString(KEY_HTTP_PROXY, value).apply()
    }

    fun getHttpHeaders(): String = prefs.getString(KEY_HTTP_HEADERS, "") ?: ""
    fun setHttpHeaders(value: String) {
        prefs.edit().putString(KEY_HTTP_HEADERS, value).apply()
    }

    companion object {
        private const val KEY_HTTP_REFERER = "http_referer"
        private const val KEY_HTTP_PROXY = "http_proxy"
        private const val KEY_HTTP_HEADERS = "http_headers"
    }
}

/**
 * http-header-fields 是 mpv 的字符串列表：条目之间用真实换行分隔，值内的逗号要转义。
 * 必须一次性整体写入；逐条 `set` 会相互覆盖，只剩最后一条。
 *
 * 下发时机有两处：设置面板点「应用」，以及每次 loadfile 前（
 * MpvPlaybackController.applyHttpSettings），后者保证冷启动后仍然生效。
 */
internal fun formatHttpHeaderFields(headers: String): String =
    headers.lines()
        .map { it.trim() }
        .filter { it.contains(":") }
        .joinToString("\n") { it.replace(",", "\\,") }

/** 代理只接受 http:// / https://；mpv 会忽略 socks5:// 等协议。 */
internal fun isValidHttpProxy(value: String): Boolean {
    val v = value.trim()
    if (v.isEmpty()) return true
    val lower = v.lowercase()
    if (!lower.startsWith("http://") && !lower.startsWith("https://")) return false
    return v.substringAfter("://").isNotBlank()
}