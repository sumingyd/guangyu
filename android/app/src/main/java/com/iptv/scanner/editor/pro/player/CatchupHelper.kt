package com.iptv.scanner.editor.pro.player

import android.util.Log
import com.iptv.scanner.editor.pro.data.IptvChannel
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Catchup URL 构建工具：与 PC 端 [controllers/catchup_controller.py] 的 catchup 逻辑完全对齐。
 *
 * 支持的 catchup 类型（与 PC 端 CATCHUP_TYPES 一致）：
 * - default / '' / vod / timemachine：直接返回 catchup_source 或 live_url
 * - append：live_url + sep + catchup_source（自动选 ? 或 &）
 * - flussonic / fs：catchup_source 或 `{live_url}/{ts_start}-{ts_end}.m3u8`
 * - xc / xtream：catchup_source 或 `{live_url}{sep}start={ts_start}&end={ts_end}&duration={dur}`
 * - shift：catchup_source 或 `{live_url}{sep}timeshift={offset}`
 * - pltv：catchup_source 或将 /PLTV/ 替换为 /TVOD/ 并追加 ?playseek={start}-{end}
 *
 * 模板变量（与 PC 端 replace_catchup_variables 对齐）：
 * - `${(b)fmt}` / `${(e)fmt}` / `${(start)fmt}` / `${(end)fmt}`：花括号带括号前缀变量（PC 端主要格式）
 * - `${start}` / `${end}` / `${timestamp}` / `${start_utc}` / `${end_utc}` / `${start_ms}` / `${end_ms}`
 * - `${offset}` / `${duration}` / `${duration_ms}`
 * - `{start}` / `{end}` / `{timestamp}` / `{offset}`：无 $ 简单变量
 * - `${start_year}` ... `${end_second}`：日期组件
 *
 * fmt 支持的时区后缀：`|utc` / `|local` / `|+HH:MM` / `|-HH:MM`
 * fmt 支持的格式：yyyyMMddHHmmss / yyyyMMddHHmm / yyyyMMdd / HHmmss / HHmm
 *   / yyyy-MM-dd / yyyy-MM-ddTHH:mm:ss / yyyy-MM-dd HH:mm:ss / yyyy / yy / MM / dd / HH / mm / ss
 *   / unix / unix_ms / 10 / 13
 */
object CatchupHelper {

    private const val TAG = "CatchupHelper"

    /**
     * 构建 catchup URL。返回 null 表示该频道不支持回看。
     *
     * @param channel 频道（含 catchup / catchup_source / url）
     * @param startMs 节目开始时间戳（毫秒）
     * @param endMs 节目结束时间戳（毫秒）
     * @return catchup URL，或 null 表示不支持
     */
    fun buildCatchupUrl(channel: IptvChannel, startMs: Long, endMs: Long): String? {
        val liveUrl = channel.url.ifEmpty { return null }
        // 安全：校验 liveUrl 协议，防止 file:/// 等非网络协议
        val lowerUrl = liveUrl.lowercase()
        if (!lowerUrl.startsWith("http://") && !lowerUrl.startsWith("https://") &&
            !lowerUrl.startsWith("rtsp://") && !lowerUrl.startsWith("rtp://") &&
            !lowerUrl.startsWith("udp://")) {
            Log.w(TAG, "Channel ${channel.name} has unsupported URL scheme")
            return null
        }
        val catchupType = channel.catchup.trim().lowercase(Locale.US)
        val catchupSource = channel.catchupSource.trim()

        // catchup_correction 时区修正（与 PC 端 catchup_controller.build_catchup_url 对齐）
        // 将 startMs/endMs 从本地时区转换到 correction 指定的时区
        val correction = channel.catchupCorrection.trim()
        var correctedStartMs = startMs
        var correctedEndMs = endMs
        if (correction.isNotEmpty()) {
            try {
                val offsetHours = correction.toDouble()
                val localOffsetMs = TimeZone.getDefault().getOffset(startMs).toLong()
                val correctionOffsetMs = (offsetHours * 3600_000).toLong()
                // 与 PC 端行为一致：replace(tzinfo=local).astimezone(target).replace(tzinfo=None)
                // 等价于：adjusted = original - localOffset + correctionOffset
                correctedStartMs = startMs - localOffsetMs + correctionOffsetMs
                correctedEndMs = endMs - localOffsetMs + correctionOffsetMs
                Log.d(TAG, "catchup_correction: offset=${offsetHours}h, localOffset=${localOffsetMs}ms, correction=${correctionOffsetMs}ms, adjusted start ${startMs}→$correctedStartMs")
            } catch (e: NumberFormatException) {
                Log.w(TAG, "Invalid catchup_correction: $correction")
            }
        }

        // Fallback：catchup 和 catchup_source 都为空时，尝试从 URL 检测 PLTV/SNM 模式
        val effectiveType: String
        val effectiveSource: String
        if (catchupSource.isEmpty() && catchupType.isEmpty()) {
            val detected = detectCatchupPattern(liveUrl)
            if (detected == null) {
                Log.d(TAG, "Channel ${channel.name} not catchup-enabled")
                return null
            }
            effectiveType = detected
            effectiveSource = ""  // 检测到的类型由 buildXxxUrl 内部生成
        } else {
            effectiveType = catchupType
            effectiveSource = catchupSource
        }

        val built = when (effectiveType) {
            "append" -> buildAppendUrl(liveUrl, effectiveSource, correctedStartMs, correctedEndMs)
            "flussonic", "fs" -> buildFlussonicUrl(liveUrl, effectiveSource, correctedStartMs, correctedEndMs)
            "xc", "xtream" -> buildXcUrl(liveUrl, effectiveSource, correctedStartMs, correctedEndMs)
            "shift" -> buildShiftUrl(liveUrl, effectiveSource, correctedStartMs, correctedEndMs)
            "pltv" -> buildPltvUrl(liveUrl, effectiveSource, correctedStartMs, correctedEndMs)
            "default", "vod", "timemachine", "" -> {
                // 直接返回 catchup_source（已替换变量），或回退到 live_url
                if (effectiveSource.isNotEmpty()) {
                    replaceCatchupVariables(effectiveSource, correctedStartMs, correctedEndMs)
                } else {
                    liveUrl
                }
            }
            else -> {
                // 未知类型，尝试直接用 catchup_source
                if (effectiveSource.isNotEmpty()) {
                    replaceCatchupVariables(effectiveSource, correctedStartMs, correctedEndMs)
                } else {
                    Log.w(TAG, "Unknown catchup type '$effectiveType' and no catchup_source")
                    null
                }
            }
        }
        // 回看/时移是单播点播流：剥离 fcc 参数，避免播放层把它当成 FCC 直播流套用
        // 零超时与 FCC 探针参数。回退到 liveUrl 的情况仍是直播，保持原样。
        return if (built != null && built != liveUrl) stripFccParam(built) else built
    }

    /**
     * 剥离 URL 查询串中的 fcc 参数（大小写不敏感、位置任意），保留其余参数、
     * fragment 与 VLC 风格的 `|` 头后缀。
     */
    fun stripFccParam(url: String): String {
        val pipeIdx = url.indexOf('|')
        val suffix = if (pipeIdx >= 0) url.substring(pipeIdx) else ""
        val core = if (pipeIdx >= 0) url.substring(0, pipeIdx) else url
        val q = core.indexOf('?')
        if (q < 0) return url

        val hashIdx = core.indexOf('#', q)
        val fragment = if (hashIdx >= 0) core.substring(hashIdx) else ""
        val path = core.substring(0, q)
        val query = core.substring(q + 1, if (hashIdx >= 0) hashIdx else core.length)

        var removed = false
        val kept = query.split('&').filter { pair ->
            if (pair.isEmpty()) return@filter false
            val key = pair.substringBefore('=').trim()
            if (key.equals("fcc", ignoreCase = true)) {
                removed = true
                false
            } else {
                true
            }
        }
        if (!removed) return url

        val newQuery = kept.joinToString("&")
        return buildString {
            append(path)
            if (newQuery.isNotEmpty()) append('?').append(newQuery)
            append(fragment)
            append(suffix)
        }
    }

    /**
     * 检测 URL 是否包含 PLTV/SNM 模式（与 PC 端 m3u_parser.detect_catchup_pattern 对齐）。
     * 返回检测到的 catchup 类型，或 null 表示不支持。
     * PLTV 和 SNM 均返回 "pltv"（与 PC 端/JS 端一致，都使用 /TVOD/ + playseek 格式）。
     */
    fun detectCatchupPattern(url: String): String? {
        if (url.isEmpty()) return null
        // PLTV/.../TVOD 或 PLTV 模式（华为/电信/移动 IPTV 平台）
        if (url.contains("/PLTV/", ignoreCase = true) || url.contains("PLTV", ignoreCase = true)) return "pltv"
        // SNM 模式（华为 IPTV 平台另一种路径，与 PC 端一致返回 pltv）
        if (url.contains("/SNM/", ignoreCase = true)) return "pltv"
        // 默认：含 catchup-source 的频道已在外部处理
        return null
    }

    /** 无 catchup_source 也能自行生成 catchup URL 的类型 */
    private val CATCHUP_TYPES_WITHOUT_SOURCE = setOf(
        "flussonic", "fs", "xc", "xtream", "shift", "pltv"
    )

    /**
     * 判断频道是否真正支持回看（比仅检查 catchup 字段非空更严格）。
     *
     * 仅凭 catchup="default" 但无 catchup_source 的频道不算支持回看，
     * 因为 buildCatchupUrl 对 default 类型无 source 时返回 null。
     *
     * 判定规则：
     *   1. catchup_source 非空 → 有模板 URL，支持回看
     *   2. catchup_source 为空但 catchup 类型可自行生成 URL → 支持
     *   3. URL 匹配 PLTV/SNM 模式 → 支持
     *   4. 其他情况（default/vod/timemachine/append/空 无 source）→ 不支持
     */
    fun isCatchupEnabled(channel: IptvChannel): Boolean {
        val catchupSource = channel.catchupSource.trim()
        val catchupType = channel.catchup.trim().lowercase()
        // 1. 有 catchup_source 模板
        if (catchupSource.isNotEmpty()) return true
        // 2. 无 source 但类型可自行生成 URL
        if (catchupType in CATCHUP_TYPES_WITHOUT_SOURCE) return true
        // 3. URL 匹配 PLTV/SNM 模式
        if (detectCatchupPattern(channel.url) != null) return true
        // 4. 其他情况不支持
        return false
    }

    // -----------------------------------------------------------------
    // 各类型 URL 构建实现
    // -----------------------------------------------------------------

    private fun buildAppendUrl(liveUrl: String, source: String, startMs: Long, endMs: Long): String? {
        // 与 PC 端对齐：source 为空时返回 liveUrl
        if (source.isEmpty()) return liveUrl
        val replaced = replaceCatchupVariables(source, startMs, endMs)
        // source 以 ?/& 开头时按其分隔符语义拼接；liveUrl 已含查询串时必须用 &
        // 并去掉 source 的前导分隔符，否则会拼出 `...?fcc=x?starttime=y` 的双问号非法 URL
        if (replaced.startsWith("?") || replaced.startsWith("&")) {
            val body = replaced.substring(1)
            if (body.isEmpty()) return liveUrl
            return if (liveUrl.contains('?')) "$liveUrl&$body" else "$liveUrl?$body"
        }
        val sep = if (liveUrl.contains('?')) "&" else "?"
        return "$liveUrl$sep$replaced"
    }

    private fun buildFlussonicUrl(liveUrl: String, source: String, startMs: Long, endMs: Long): String? {
        if (source.isNotEmpty()) return replaceCatchupVariables(source, startMs, endMs)
        // 默认格式：{live_url}/{ts_start}-{ts_end}.m3u8（unix 秒）
        val startSec = startMs / 1000
        val endSec = endMs / 1000
        return "$liveUrl/$startSec-$endSec.m3u8"
    }

    private fun buildXcUrl(liveUrl: String, source: String, startMs: Long, endMs: Long): String? {
        if (source.isNotEmpty()) return replaceCatchupVariables(source, startMs, endMs)
        val startSec = startMs / 1000
        val endSec = endMs / 1000
        val duration = (endSec - startSec).coerceAtLeast(0L)
        val sep = if (liveUrl.contains('?')) "&" else "?"
        return "$liveUrl${sep}start=$startSec&end=$endSec&duration=$duration"
    }

    private fun buildShiftUrl(liveUrl: String, source: String, startMs: Long, endMs: Long): String? {
        if (source.isNotEmpty()) return replaceCatchupVariables(source, startMs, endMs)
        // 时移偏移量（秒，从节目开始到现在）
        val now = System.currentTimeMillis()
        val offset = ((now - startMs) / 1000).coerceAtLeast(0L)
        val sep = if (liveUrl.contains('?')) "&" else "?"
        return "$liveUrl${sep}timeshift=$offset"
    }

    private fun buildPltvUrl(liveUrl: String, source: String, startMs: Long, endMs: Long): String? {
        if (source.isNotEmpty()) return replaceCatchupVariables(source, startMs, endMs)
        // 将 /PLTV/ 或 /SNM/ 替换为 /TVOD/，追加 ?playseek={start}-{end}（yyyyMMddHHmmss 格式）
        // 与 PC 端 build_catchup_url 的 pltv 分支对齐：使用本地时区（非 UTC）
        val tvodUrl = liveUrl
            .replace("/PLTV/", "/TVOD/", ignoreCase = true)
            .replace("/SNM/", "/TVOD/", ignoreCase = true)
        val fmt = SimpleDateFormat("yyyyMMddHHmmss", Locale.US)
        val startStr = fmt.format(Date(startMs))
        val endStr = fmt.format(Date(endMs))
        val sep = if (tvodUrl.contains('?')) "&" else "?"
        return "$tvodUrl${sep}playseek=$startStr-$endStr"
    }

    // -----------------------------------------------------------------
    // 模板变量替换（与 PC 端 replace_catchup_variables 对齐）
    // -----------------------------------------------------------------

    /**
     * 替换 catchup URL 中的模板变量。
     *
     * 安全：所有替换值均为数字时间戳或格式化日期字符串，不包含用户可控的任意文本，
     * 因此不存在 URL 注入风险。catchup_source 模板来自频道配置（非用户实时输入），
     * 且替换后的 URL 仅用于 mpv loadfile，不会执行任意命令。
     *
     * 支持的变量格式：
     * - `${(b|e|start|end)fmt}`：花括号带前缀，fmt 可带时区后缀 `|utc|local|+HH:MM|-HH:MM`
     * - `${name}`：简单变量（start/end/timestamp/start_utc/end_utc/start_ms/end_ms/offset/duration/duration_ms）
     * - `${start_year}` / `${end_month}` 等：日期组件
     * - `{start}` / `{end}` / `{timestamp}` / `{offset}`：无 $ 简单变量
     */
    fun replaceCatchupVariables(url: String, startMs: Long, endMs: Long): String {
        if (url.isEmpty()) return url
        val startSec = startMs / 1000
        val endSec = endMs / 1000
        val durationSec = ((endMs - startMs) / 1000).coerceAtLeast(0L)

        var result = url

        // 1. 花括号带括号前缀变量：${(b)fmt} / ${(e)fmt} / ${(start)fmt} / ${(end)fmt}
        // 与 PC 端 catchup_controller.replace_braced_vars 的 regex 完全对齐：
        //   re.finditer(r'\$\{\(' + re.escape(prefix) + r'\)([^}]+)\}', url)
        val prefixedPattern = Regex("""\$\{\((b|e|start|end)\)([^}]*)\}""")
        result = prefixedPattern.replace(result) { m ->
            val prefix = m.groupValues[1]
            val fmt = m.groupValues[2].ifEmpty { "" }
            val ts = when (prefix) {
                "b", "start" -> startMs
                "e", "end" -> endMs
                else -> startMs
            }
            formatCatchupTime(ts, fmt)
        }

        // 2. 简单变量：${name}
        // 与 PC 端 replace_catchup_variables 的 replacements 对齐
        val simplePattern = Regex("""\$\{(\w+)\}""")
        result = simplePattern.replace(result) { m ->
            val name = m.groupValues[1]
            when (name) {
                "start" -> startSec.toString()
                "end" -> endSec.toString()
                "timestamp" -> startSec.toString()  // PC 端: '${timestamp}': start_ts
                "start_utc" -> startSec.toString()
                "end_utc" -> endSec.toString()
                "start_ms" -> startMs.toString()
                "end_ms" -> endMs.toString()
                "offset" -> startSec.toString()  // PC 端: '${offset}': start_ts
                "duration" -> durationSec.toString()
                "duration_ms" -> (durationSec * 1000).toString()
                // 日期组件
                "start_year" -> formatDateComponent(startMs, "yyyy")
                "start_month" -> formatDateComponent(startMs, "MM")
                "start_day" -> formatDateComponent(startMs, "dd")
                "start_hour" -> formatDateComponent(startMs, "HH")
                "start_minute" -> formatDateComponent(startMs, "mm")
                "start_second" -> formatDateComponent(startMs, "ss")
                "end_year" -> formatDateComponent(endMs, "yyyy")
                "end_month" -> formatDateComponent(endMs, "MM")
                "end_day" -> formatDateComponent(endMs, "dd")
                "end_hour" -> formatDateComponent(endMs, "HH")
                "end_minute" -> formatDateComponent(endMs, "mm")
                "end_second" -> formatDateComponent(endMs, "ss")
                else -> m.value  // 未知变量，保留原样
            }
        }

        // 3. 无 $ 简单变量：{start} / {end} / {timestamp} / {offset}
        // 与 PC 端 replacements 中的无 $ 变量对齐
        val noDollarPattern = Regex("""\{(start|end|timestamp|offset)\}""")
        result = noDollarPattern.replace(result) { m ->
            when (m.groupValues[1]) {
                "start" -> startSec.toString()
                "end" -> endSec.toString()
                "timestamp" -> startSec.toString()  // PC 端: '{timestamp}': start_ts
                "offset" -> startSec.toString()  // PC 端: '{offset}': start_ts
                else -> m.value
            }
        }

        return result
    }

    /**
     * 格式化 catchup 时间。与 PC 端 format_catchup_time 对齐。
     *
     * @param tsMs 时间戳（毫秒）
     * @param fmt 格式字符串，可能含时区后缀 `|utc|local|+HH:MM|-HH:MM`
     *   - 支持的格式：yyyyMMddHHmmss / yyyyMMddHHmm / yyyyMMdd / HHmmss / HHmm
     *     / yyyy-MM-dd / yyyy-MM-ddTHH:mm:ss / yyyy-MM-dd HH:mm:ss / yyyy / yy / MM / dd / HH / mm / ss
     *   - unix / unix_ms / 10 / 13：返回 unix 时间戳（秒/毫秒）
     *   - 空字符串：默认 yyyyMMddHHmmss
     */
    fun formatCatchupTime(tsMs: Long, fmt: String): String {
        if (fmt.isEmpty()) {
            // 默认格式：本地时区 yyyyMMddHHmmss（与 PC 端 strftime 行为一致）
            return SimpleDateFormat("yyyyMMddHHmmss", Locale.US)
                .format(Date(tsMs))
        }

        // 解析时区后缀（与 PC 端 format_time 对齐，支持 | 和 : 两种分隔符）
        var formatPart = fmt
        var tzPart = ""
        val pipeIdx = fmt.indexOf('|')
        if (pipeIdx >= 0) {
            formatPart = fmt.substring(0, pipeIdx)
            tzPart = fmt.substring(pipeIdx + 1).trim()
        } else {
            val lowerFmt = fmt.lowercase()
            val utcIdx = lowerFmt.indexOf(":utc")
            val localIdx = lowerFmt.indexOf(":local")
            if (utcIdx >= 0) {
                formatPart = fmt.substring(0, utcIdx)
                tzPart = "utc"
            } else if (localIdx >= 0) {
                formatPart = fmt.substring(0, localIdx)
                tzPart = "local"
            }
        }

        // unix 时间戳特殊处理
        when (formatPart) {
            "unix", "10" -> return (tsMs / 1000).toString()
            "unix_ms", "13" -> return tsMs.toString()
        }

        // 时区选择
        val tz = when {
            tzPart.isEmpty() || tzPart.equals("local", ignoreCase = true) -> TimeZone.getDefault()
            tzPart.equals("utc", ignoreCase = true) -> TimeZone.getTimeZone("UTC")
            tzPart.startsWith("+") || tzPart.startsWith("-") -> TimeZone.getTimeZone("GMT$tzPart")
            else -> TimeZone.getTimeZone(tzPart)
        }

        val pattern = when (formatPart) {
            "yyyyMMddHHmmss", "" -> "yyyyMMddHHmmss"
            "yyyyMMddHHmm" -> "yyyyMMddHHmm"
            "yyyyMMdd" -> "yyyyMMdd"
            "HHmmss" -> "HHmmss"
            "HHmm" -> "HHmm"
            "yyyy-MM-dd" -> "yyyy-MM-dd"
            "yyyy-MM-ddTHH:mm:ss" -> "yyyy-MM-dd'T'HH:mm:ss"
            "yyyy-MM-dd HH:mm:ss" -> "yyyy-MM-dd HH:mm:ss"
            "yyyy" -> "yyyy"
            "yy" -> "yy"
            "MM" -> "MM"
            "dd" -> "dd"
            "HH" -> "HH"
            "mm" -> "mm"
            "ss" -> "ss"
            else -> formatPart  // 自定义格式直接用
        }

        return SimpleDateFormat(pattern, Locale.US).apply { timeZone = tz }.format(Date(tsMs))
    }

    private fun formatDateComponent(tsMs: Long, pattern: String): String =
        SimpleDateFormat(pattern, Locale.US).format(Date(tsMs))

    // -----------------------------------------------------------------
    // EPG 节目时间戳提取（与 PC 端对齐）
    // -----------------------------------------------------------------

    /**
     * 从 IptvEpgProgram 提取开始/结束时间戳（毫秒）。
     * 优先使用 start_ts/stop_ts，否则解析 start/stop ISO 字符串。
     * 返回 Pair<startMs, endMs>，任一为 0 表示无效。
     */
    fun extractProgramTimestamps(program: com.iptv.scanner.editor.pro.data.IptvEpgProgram): Pair<Long, Long> {
        val startMs = if (program.startTs > 0) {
            program.startTs * 1000L
        } else {
            parseIsoToMs(program.start)
        }
        val endMs = if (program.stopTs > 0) {
            program.stopTs * 1000L
        } else if (program.end.isNotEmpty()) {
            parseIsoToMs(program.end)
        } else {
            parseIsoToMs(program.stop)
        }
        return startMs to endMs
    }

    /** 解析 ISO 时间字符串为毫秒时间戳，失败返回 0 */
    private fun parseIsoToMs(iso: String): Long {
        if (iso.isEmpty()) return 0
        // 尝试常见 ISO 格式
        val patterns = listOf(
            "yyyy-MM-dd'T'HH:mm:ssXXX",
            "yyyy-MM-dd'T'HH:mm:ssXXX'Z'",
            "yyyy-MM-dd'T'HH:mm:ss'Z'",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd HH:mm",
        )
        for (pattern in patterns) {
            try {
                val sdf = SimpleDateFormat(pattern, Locale.US)
                val date = sdf.parse(iso) ?: continue
                return date.time
            } catch (_: Exception) {
                // 尝试下一个格式
            }
        }
        // 尝试纯数字时间戳
        return iso.toLongOrNull()?.let { if (it > 1_000_000_000_000L) it else it * 1000 } ?: 0
    }

    /**
     * 计算时移 targetWallclock（用于 startLiveTimeshift）。
     * @param programStartMs 节目开始时间戳（毫秒）
     * @param hourStartMs 当前小时整点时间戳（毫秒，无 EPG 时使用）
     * @param sliderSec 进度条点击位置（秒）
     * @param hasEpg 是否有 EPG（决定用 programStart 还是 hourStart）
     * @return targetWallclockMs，已限制不超过 now-5s
     */
    fun computeTimeshiftTarget(programStartMs: Long, hourStartMs: Long, sliderSec: Double, hasEpg: Boolean): Long {
        val base = if (hasEpg && programStartMs > 0) programStartMs else hourStartMs
        val target = base + (sliderSec * 1000).toLong()
        val now = System.currentTimeMillis()
        // 不超过当前时间，留 5 秒余量
        return target.coerceAtMost(now - 5_000L)
    }

    /**
     * 计算当前小时整点时间戳（毫秒）。
     */
    fun currentHourStartMs(): Long {
        val cal = Calendar.getInstance()
        cal.set(Calendar.MINUTE, 0)
        cal.set(Calendar.SECOND, 0)
        cal.set(Calendar.MILLISECOND, 0)
        return cal.timeInMillis
    }
}
