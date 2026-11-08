package com.iptv.scanner.editor.pro.player

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.URLDecoder

/**
 * FCC (Fast Channel Change) 快速换台辅助类。
 *
 * 播放地址**不做任何改写**：频道 URL 原样交给 mpv，FCC 只做两件事：
 * 1. 通过 UDP 文本协议通知 FCC 代理（如 rtp2httpd）预加入/退出组播组；
 * 2. 为判定为 FCC 的**直播**流应用一组低延迟 demuxer 参数。
 *
 * URL 形态（组播源可从 host 或 `/rtp/`、`/udp/` 路径两种位置取到）：
 *   rtp://239.1.1.1:5002?fcc=150.138.8.132:8027
 *   udp://@239.2.1.5:5000?fcc=10.0.0.1:9000
 *   http://proxy:8080/rtp/239.1.1.1:5002?fcc=150.138.8.132:8027
 *
 * FCC 通知协议（UDP 文本，`\n` 结尾）：
 *   LEAVE <multicast_ip> <multicast_port>
 *   JOIN <multicast_ip> <multicast_port>
 *
 * 解析约束（历史问题修复）：
 * - **不使用 java.net.URI**：带 `|User-Agent=...` 头、空格、非 ASCII 的 URL 会让 URI 抛
 *   URISyntaxException，旧实现因此在“调优判定”和“通知”之间静默分叉。这里改为手工切分。
 * - 参数名大小写不敏感、位置任意（首参或 `&fcc=` 都认）。
 * - “是否 FCC 流”与“是否可通知”是两个概念：前者只看参数存在，后者要求代理地址与组播源都解析成功。
 */
object FccHelper {
    private const val TAG = "FccHelper"

    /** fcc 参数未带端口时的默认代理端口 */
    private const val DEFAULT_FCC_PORT = 8027

    private val MULTICAST_PATH_REGEX =
        Regex("""/(?:rtp|udp)/(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})""", RegexOption.IGNORE_CASE)

    /**
     * FCC 判定结果。[isFcc] 为 true 表示 URL 带 fcc 参数（是 FCC 流）；
     * [endpoint] / [multicast] 任一为 null 时无法发送通知，原因写入 [error]。
     */
    data class FccPlan(
        val isFcc: Boolean,
        val endpoint: Pair<String, Int>?,
        val multicast: Pair<String, Int>?,
        val error: String? = null
    ) {
        /** 代理地址与组播源都解析成功，可以发送 LEAVE/JOIN */
        val canNotify: Boolean get() = endpoint != null && multicast != null
    }

    // 持久化 UDP socket —— 避免每次通知都创建/关闭 socket
    @Volatile
    private var persistentSock: DatagramSocket? = null
    private val sockLock = Any()

    internal fun getUdpSocket(): DatagramSocket {
        persistentSock?.let { return it }
        synchronized(sockLock) {
            persistentSock?.let { return it }
            val sock = DatagramSocket()
            persistentSock = sock
            Log.d(TAG, "FCC持久化UDP socket已创建")
            return sock
        }
    }

    fun closeUdpSocket() {
        synchronized(sockLock) {
            persistentSock?.let {
                try { it.close() } catch (_: Exception) {}
            }
            persistentSock = null
        }
    }

    // ---------------- 解析（单一判定源） ----------------

    /**
     * 唯一的 FCC 判定入口。播放参数调优与代理通知都必须使用本方法的返回值，
     * 不允许任何调用方再自行做字符串匹配。
     */
    fun resolve(url: String?): FccPlan {
        if (url.isNullOrBlank()) return FccPlan(false, null, null)
        val query = queryOf(url) ?: return FccPlan(false, null, null)
        val fccValue = findParam(query, "fcc") ?: return FccPlan(false, null, null)

        val multicast = parseMulticastFromUrl(url)
        if (fccValue.isBlank()) return FccPlan(true, null, multicast, "fcc 参数为空")
        val endpoint = parseEndpoint(fccValue)
            ?: return FccPlan(true, null, multicast, "fcc 代理地址非法: $fccValue")
        if (multicast == null) return FccPlan(true, endpoint, null, "无法解析组播源地址")
        return FccPlan(true, endpoint, multicast)
    }

    /**
     * 从 URL 中提取组播地址与端口：优先取 host（本身是组播 IP 时），
     * 否则回退路径中的 `/rtp/`、`/udp/` 段。
     * @return (multicastIp, multicastPort) 或 null
     */
    fun parseMulticastFromUrl(url: String?): Pair<String, Int>? {
        if (url.isNullOrBlank()) return null

        val authority = authorityOf(url)
        if (authority != null) {
            val (host, port) = hostPortOf(authority)
            if (host != null && port != null && isMulticastIp(host)) return host to port
        }

        val match = MULTICAST_PATH_REGEX.find(pathOf(url)) ?: return null
        val ip = match.groupValues[1]
        val port = match.groupValues[2].toIntOrNull() ?: return null
        return if (isValidPort(port) && isMulticastIp(ip)) ip to port else null
    }

    /** 解析 `ip:port` / `[v6]:port` / 仅 ip（默认端口） */
    fun parseEndpoint(value: String): Pair<String, Int>? {
        val v = value.trim()
        if (v.isEmpty()) return null
        if (v.startsWith("[")) {
            val close = v.indexOf(']')
            if (close <= 1) return null
            val host = v.substring(1, close)
            val portText = v.substring(close + 1).removePrefix(":")
            val port = if (portText.isEmpty()) DEFAULT_FCC_PORT else portText.toIntOrNull() ?: return null
            return if (isValidPort(port)) host to port else null
        }
        val idx = v.lastIndexOf(':')
        if (idx < 0) return v to DEFAULT_FCC_PORT
        val host = v.substring(0, idx).trim()
        val port = v.substring(idx + 1).trim().toIntOrNull() ?: return null
        if (host.isEmpty() || !isValidPort(port)) return null
        return host to port
    }

    /** 判断是否为组播IP地址（224.0.0.0 ~ 239.255.255.255） */
    private fun isMulticastIp(ip: String): Boolean {
        val parts = ip.split(".")
        if (parts.size != 4) return false
        val octets = parts.map { it.toIntOrNull() ?: return false }
        if (octets.any { it !in 0..255 }) return false
        return octets[0] in 224..239
    }

    private fun isValidPort(port: Int): Boolean = port in 1..65535

    /** VLC 风格：URL 之后用 `|` 追加请求头，不属于 URL 本身 */
    private fun stripHeaderSuffix(url: String): String {
        val pipe = url.indexOf('|')
        return if (pipe >= 0) url.substring(0, pipe) else url
    }

    private fun queryOf(url: String): String? {
        val s = stripHeaderSuffix(url)
        val q = s.indexOf('?')
        if (q < 0) return null
        var query = s.substring(q + 1)
        val hash = query.indexOf('#')
        if (hash >= 0) query = query.substring(0, hash)
        return query
    }

    private fun authorityOf(url: String): String? {
        val s = stripHeaderSuffix(url)
        val schemeEnd = s.indexOf("://")
        if (schemeEnd < 0) return null
        val rest = s.substring(schemeEnd + 3)
        val end = rest.indexOfFirst { it == '/' || it == '?' || it == '#' }
        return if (end < 0) rest else rest.substring(0, end)
    }

    private fun pathOf(url: String): String {
        val s = stripHeaderSuffix(url)
        val schemeEnd = s.indexOf("://")
        val rest = if (schemeEnd < 0) s else s.substring(schemeEnd + 3)
        val slash = rest.indexOf('/')
        if (slash < 0) return ""
        var path = rest.substring(slash)
        val q = path.indexOf('?')
        if (q >= 0) path = path.substring(0, q)
        val hash = path.indexOf('#')
        if (hash >= 0) path = path.substring(0, hash)
        return path
    }

    private fun hostPortOf(authority: String): Pair<String?, Int?> {
        var a = authority
        val at = a.lastIndexOf('@')
        if (at >= 0) a = a.substring(at + 1)
        if (a.startsWith("[")) {
            val close = a.indexOf(']')
            if (close < 0) return null to null
            val host = a.substring(1, close)
            val portText = a.substring(close + 1).removePrefix(":")
            return host.ifBlank { null } to portText.toIntOrNull()
        }
        val colon = a.lastIndexOf(':')
        if (colon < 0) return a.ifBlank { null } to null
        return a.substring(0, colon).ifBlank { null } to a.substring(colon + 1).toIntOrNull()
    }

    private fun findParam(query: String, name: String): String? {
        for (pair in query.split('&')) {
            if (pair.isEmpty()) continue
            val idx = pair.indexOf('=')
            val rawKey = if (idx >= 0) pair.substring(0, idx) else pair
            val rawValue = if (idx >= 0) pair.substring(idx + 1) else ""
            if (!decode(rawKey).trim().equals(name, ignoreCase = true)) continue
            return decode(rawValue).trim()
        }
        return null
    }

    /** 容错解码：非法百分号转义时退回原文，绝不抛异常 */
    private fun decode(raw: String): String = try {
        URLDecoder.decode(raw, "UTF-8")
    } catch (_: Exception) {
        raw
    }

    // ---------------- 发送 ----------------

    /**
     * 向 FCC 代理发送换台通知（UDP），LEAVE+JOIN 可合并为单个包。
     * @return 是否发送成功（失败仅记录日志，不影响播放）
     */
    suspend fun sendFccNotification(
        fccIp: String,
        fccPort: Int,
        leaveAddr: Pair<String, Int>? = null,
        joinAddr: Pair<String, Int>? = null
    ): Boolean {
        val messages = mutableListOf<String>()
        if (leaveAddr != null) messages.add("LEAVE ${leaveAddr.first} ${leaveAddr.second}")
        if (joinAddr != null) messages.add("JOIN ${joinAddr.first} ${joinAddr.second}")
        if (messages.isEmpty()) return true

        val payload = (messages.joinToString("\n") + "\n").toByteArray(Charsets.UTF_8)
        return sendUdp(fccIp, fccPort, payload)
    }

    /**
     * 同步发送（供退出清理使用，此时协程作用域可能已取消）。
     * 目标为 IP 字面量，不做 DNS 解析，单次 UDP send 为微秒级系统调用。
     */
    internal fun sendFccBlocking(fccIp: String, fccPort: Int, messages: List<String>): Boolean {
        if (messages.isEmpty()) return true
        val payload = (messages.joinToString("\n") + "\n").toByteArray(Charsets.UTF_8)
        return try {
            val sock = getUdpSocket()
            val addr = InetAddress.getByName(fccIp)
            sock.send(DatagramPacket(payload, payload.size, addr, fccPort))
            Log.i(TAG, "FCC通知已发送(同步): $fccIp:$fccPort, 数据: ${String(payload)}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "FCC通知发送失败(同步): ip=$fccIp port=$fccPort error=${e.javaClass.simpleName}: ${e.message}")
            false
        }
    }

    private suspend fun sendUdp(ip: String, port: Int, data: ByteArray): Boolean = withContext(Dispatchers.IO) {
        try {
            val sock = getUdpSocket()
            val addr = InetAddress.getByName(ip)
            val packet = DatagramPacket(data, data.size, addr, port)
            sock.send(packet)
            Log.i(TAG, "FCC通知已发送: $ip:$port, 数据: ${String(data)}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "FCC通知发送失败: ip=$ip port=$port error=${e.javaClass.simpleName}: ${e.message}")
            false
        }
    }
}

/**
 * FCC 快速换台服务管理器。
 *
 * 状态机语义：
 * - 换台时先向**旧代理端点**发 LEAVE（旧组播），再向**新代理端点**发 JOIN（新组播）；
 *   两端点不同时绝不混发，避免把 LEAVE 发到新代理。
 * - 切到非 FCC 频道、停止播放，都要向旧端点补 LEAVE。
 * - 断流重连、切换播放内核后可 [resendJoin] 强制重发 JOIN（绕过“同址早退”）。
 * - 换台/重发 JOIN 的状态变更与发包在同一个 [Mutex] 内串行，避免“状态已改、包未发”；
 *   [onStop]/[shutdown] 则在调用线程同步摘取旧会话后异步/同步补发 LEAVE，避免与新会话竞态。
 *
 * 注意：FCC 通知是尽力而为的加速手段，发送失败只记录日志，不影响正常播放。
 */
class FccService {
    private companion object {
        const val TAG = "FccService"
    }

    private val mutex = Mutex()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /** 当前已通知代理加入的组播源 */
    @Volatile
    private var currentMulticast: Pair<String, Int>? = null

    /** 当前会话使用的代理端点（LEAVE 必须发往该端点） */
    @Volatile
    private var currentFcc: Pair<String, Int>? = null

    /**
     * 频道切换时调用（需在 mpv loadfile 之前 await 完成，保证代理先预加入）。
     */
    suspend fun onChannelChange(newUrl: String) {
        mutex.withLock { switchLocked(newUrl) }
    }

    /**
     * 强制重发 JOIN：断流重连、切换 MPV/EXO 内核恢复播放前调用。
     * 与 [onChannelChange] 不同，同址情况下也会重发。
     */
    fun resendJoin(url: String) {
        scope.launch { mutex.withLock { resendJoinLocked(url) } }
    }

    /**
     * 停止播放 / 切到非 FCC 流时调用——向旧端点补发 LEAVE。
     *
     * 状态在调用线程同步捕获并清空，LEAVE 异步发送：这样即使紧接着又换台（新 JOIN 已写入状态），
     * 本次 LEAVE 也只会发给**旧**端点/旧组播，不会误伤新会话。
     */
    fun onStop() {
        val fcc = currentFcc
        val multicast = currentMulticast
        currentFcc = null
        currentMulticast = null
        if (fcc == null || multicast == null) return
        scope.launch {
            FccHelper.sendFccNotification(fcc.first, fcc.second, leaveAddr = multicast)
        }
    }

    /**
     * 退出清理：先同步补发 LEAVE（此时协程可能已取消），再关闭持久化 socket。
     */
    fun shutdown() {
        val fcc = currentFcc
        val multicast = currentMulticast
        currentFcc = null
        currentMulticast = null
        if (fcc != null && multicast != null) {
            FccHelper.sendFccBlocking(
                fcc.first, fcc.second,
                listOf("LEAVE ${multicast.first} ${multicast.second}")
            )
        }
        FccHelper.closeUdpSocket()
    }

    /** 重置状态（不发送 leave 通知）。 */
    fun reset() {
        currentFcc = null
        currentMulticast = null
    }

    private suspend fun switchLocked(url: String) {
        val plan = FccHelper.resolve(url)
        Log.i(
            TAG,
            "onChannelChange: isFcc=${plan.isFcc} endpoint=${plan.endpoint} " +
                "multicast=${plan.multicast} error=${plan.error} url=$url"
        )
        if (plan.isFcc && !plan.canNotify) {
            Log.w(TAG, "FCC 流但无法通知代理(${plan.error})，本次仅清理旧会话: $url")
        }

        val oldFcc = currentFcc
        val oldMulticast = currentMulticast
        val newFcc = plan.endpoint
        val newMulticast = plan.multicast

        val needLeave = oldFcc != null && oldMulticast != null &&
            (oldFcc != newFcc || oldMulticast != newMulticast)
        val needJoin = newFcc != null && newMulticast != null &&
            (newFcc != oldFcc || newMulticast != oldMulticast)

        // 先更新状态再发包：让并发的 onStop/resendJoin 看到最新会话；
        // 发送失败无法回滚（UDP 尽力而为），只能靠日志排查。
        currentFcc = newFcc
        currentMulticast = newMulticast

        if (!needLeave && !needJoin) return

        if (needLeave && needJoin && oldFcc == newFcc) {
            // 同一代理端点：LEAVE+JOIN 合并为一个包，减少一次 UDP 发送
            FccHelper.sendFccNotification(
                newFcc!!.first, newFcc.second,
                leaveAddr = oldMulticast, joinAddr = newMulticast
            )
        } else {
            if (needLeave) {
                FccHelper.sendFccNotification(
                    oldFcc!!.first, oldFcc.second,
                    leaveAddr = oldMulticast
                )
            }
            if (needJoin) {
                FccHelper.sendFccNotification(
                    newFcc!!.first, newFcc.second,
                    joinAddr = newMulticast
                )
            }
        }
    }

    private suspend fun resendJoinLocked(url: String) {
        val plan = FccHelper.resolve(url)
        val endpoint = plan.endpoint
        val multicast = plan.multicast
        if (endpoint == null || multicast == null) {
            Log.w(TAG, "resendJoin: 无法解析 FCC 端点/组播源(${plan.error}), url=$url")
            return
        }
        currentFcc = endpoint
        currentMulticast = multicast
        FccHelper.sendFccNotification(endpoint.first, endpoint.second, joinAddr = multicast)
    }
}
