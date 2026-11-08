package com.iptv.scanner.editor.pro.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * IPTV 数据模型。对应 android_bridge.py 中各入口函数返回的 JSON 结构。
 *
 * 设计要点：
 * - 所有类用 @Serializable，支持 kotlinx-serialization JSON 反序列化
 * - 字段命名与 Python 端保持一致（snake_case 转 camelCase 用 @SerialName 映射）
 * - 可空字段用 String?（Python 端可能返回 None）
 * - 默认值确保反序列化不失败
 */

// -----------------------------------------------------------------
// 状态与频道
// -----------------------------------------------------------------

@Serializable
data class IptvStatus(
    @SerialName("inited") val inited: Boolean = false,
    @SerialName("channels_total") val channelsTotal: Int = 0,
    @SerialName("source_loading") val sourceLoading: Boolean = false,
    @SerialName("source_message") val sourceMessage: String = "",
    /** 非空表示订阅源刷新失败但已使用缓存频道（如网络异常），UI 应提示用户数据未丢失 */
    @SerialName("source_warning") val sourceWarning: String = "",
)

@Serializable
data class IptvChannel(
    @SerialName("id") val id: Int = 0,
    @SerialName("name") val name: String = "",
    @SerialName("url") val url: String = "",
    @SerialName("group") val group: String = "",
    @SerialName("logo") val logo: String = "",
    @SerialName("tvg_id") val tvgId: String = "",
    @SerialName("tvg_name") val tvgName: String = "",
    @SerialName("tvg_chno") val tvgChno: String = "",
    @SerialName("tvg_shift") val tvgShift: String = "",
    @SerialName("catchup") val catchup: String = "",
    @SerialName("catchup_days") val catchupDays: String = "",
    @SerialName("catchup_source") val catchupSource: String = "",
    @SerialName("catchup_correction") val catchupCorrection: String = "",
    /**
     * m3u 的 fcc 扩展字段，仅用于保留反序列化契约。
     * FCC 运行时判定只看播放 URL 中的 `fcc=` 参数（见 FccHelper.resolve），不读取本字段。
     */
    @SerialName("fcc") val fcc: String = "",
    @SerialName("resolution") val resolution: String = "",
    /** valid: True=有效, False=无效, null=未检测 */
    @SerialName("valid") val valid: Boolean? = null,
    @SerialName("status") val status: String = "待检测",
    /** 频道来源：空=手动添加/本地频道，非空=订阅源 URL */
    @SerialName("source") val source: String = "",
)

@Serializable
data class IptvChannelsPage(
    @SerialName("total") val total: Int = 0,
    @SerialName("page") val page: Int = 1,
    @SerialName("size") val size: Int = 100,
    @SerialName("channels") val channels: List<IptvChannel> = emptyList(),
)

@Serializable
data class IptvGroup(
    @SerialName("name") val name: String = "",
    @SerialName("count") val count: Int = 0,
)

// -----------------------------------------------------------------
// 订阅源
// -----------------------------------------------------------------

@Serializable
data class IptvSource(
    @SerialName("url") val url: String = "",
    @SerialName("name") val name: String = "",
    @SerialName("enabled") val enabled: Boolean = true,
    @SerialName("last_update") val lastUpdate: String? = null,
)

@Serializable
data class IptvEpgSource(
    @SerialName("url") val url: String = "",
    @SerialName("name") val name: String = "",
    @SerialName("last_update") val lastUpdate: String? = null,
)

@Serializable
data class IptvSourceStatus(
    @SerialName("loading") val loading: Boolean = false,
    @SerialName("message") val message: String = "",
    // Python 端 context.get_source_load_status() 返回字段名为 'channels'（不是 channels_total）
    @SerialName("channels") val channelsTotal: Int = 0,
)

// -----------------------------------------------------------------
// EPG
// -----------------------------------------------------------------

@Serializable
data class IptvEpgProgram(
    @SerialName("title") val title: String = "",
    @SerialName("desc") val desc: String = "",
    @SerialName("start") val start: String = "",
    /** XMLTV 标准用 stop，部分接口用 end，两者都接受 */
    @SerialName("stop") val stop: String = "",
    @SerialName("end") val end: String = "",
    @SerialName("start_ts") val startTs: Long = 0,
    @SerialName("stop_ts") val stopTs: Long = 0,
) {
    /** 统一的结束时间戳：优先 stop_ts，其次尝试解析 stop/end 字符串 */
    val endTimestamp: Long
        get() = if (stopTs > 0) stopTs else 0L
}

@Serializable
data class IptvEpgList(
    @SerialName("programmes") val programmes: List<IptvEpgProgram> = emptyList(),
    @SerialName("matched") val matched: Boolean = false,
)

@Serializable
data class IptvEpgStatus(
    @SerialName("has_epg_data") val hasEpgData: Boolean = false,
    @SerialName("channel_count") val channelCount: Int = 0,
    @SerialName("program_count") val programCount: Int = 0,
)

// -----------------------------------------------------------------
// 扫描
// -----------------------------------------------------------------

@Serializable
data class ScanStatus(
    @SerialName("running") val running: Boolean = false,
    @SerialName("total") val total: Int = 0,
    @SerialName("valid") val valid: Int = 0,
    @SerialName("invalid") val invalid: Int = 0,
    @SerialName("scanned") val scanned: Int = 0,
    @SerialName("message") val message: String = "",
    /** 'subscription' 或 'range' 或 null */
    @SerialName("mode") val mode: String? = null,
)

@Serializable
data class ScanResult(
    @SerialName("url") val url: String = "",
    @SerialName("name") val name: String = "",
    @SerialName("valid") val valid: Boolean = false,
    @SerialName("status") val status: String = "",
    @SerialName("latency") val latency: Int = 0,
    @SerialName("group") val group: String = "",
)

// -----------------------------------------------------------------
// 节目提醒（与 PC 端 services/epg_reminder_service.py 对齐）
// -----------------------------------------------------------------

@Serializable
data class ReminderItem(
    /** 唯一 ID：channelIdx_programTitle_startTs，用于去重和删除 */
    @SerialName("id") val id: String = "",
    /** 频道在 channels 列表中的下标（切台用） */
    @SerialName("channel_idx") val channelIdx: Int = -1,
    @SerialName("channel_name") val channelName: String = "",
    @SerialName("tvg_id") val tvgId: String = "",
    @SerialName("program_title") val programTitle: String = "",
    /** 节目开始时间戳（毫秒） */
    @SerialName("start_ts") val startTs: Long = 0,
    /** 节目结束时间戳（毫秒） */
    @SerialName("stop_ts") val stopTs: Long = 0,
    /** 提醒创建时间戳（毫秒） */
    @SerialName("created_at") val createdAt: Long = 0,
)

// -----------------------------------------------------------------
// 续播位置（与 PC 端 controllers/resume_playback_controller.py 对齐）
//
// 以 URL 为唯一 key（PC 端用 url 作 dict key，Web 端用 uuid 但同时存 url）。
// Android 端采用 url 作 id 简化去重逻辑。
// -----------------------------------------------------------------

@Serializable
data class ResumeItem(
    /** 唯一 ID：使用 url（同一 URL 重复播放只保留最新位置） */
    @SerialName("id") val id: String = "",
    @SerialName("url") val url: String = "",
    /** 显示名：本地视频取文件名，频道取频道名 */
    @SerialName("name") val name: String = "",
    /** 频道下标（-1 表示本地视频，不在频道列表中） */
    @SerialName("channel_idx") val channelIdx: Int = -1,
    /** 播放位置（秒） */
    @SerialName("position") val position: Long = 0,
    /** 总时长（秒），直播流为 0 或不保存 */
    @SerialName("duration") val duration: Long = 0,
    /** 更新时间戳（毫秒） */
    @SerialName("updated_at") val updatedAt: Long = 0,
)

// -----------------------------------------------------------------
// 书签（与 PC 端 controllers/bookmark_controller.py 对齐）
//
// 以 URL 为分组 key（与 PC 端 bookmarks.json 结构一致）。
// 同 URL 同位置（0.5s 容差）的书签会被覆盖。
// -----------------------------------------------------------------

@Serializable
data class BookmarkItem(
    /** 唯一 ID：url_position（用于 Compose LazyColumn key） */
    @SerialName("id") val id: String = "",
    @SerialName("url") val url: String = "",
    /** 书签名（用户输入或自动生成） */
    @SerialName("name") val name: String = "",
    /** 书签位置（秒） */
    @SerialName("position") val position: Long = 0,
    /** 创建时间戳（毫秒） */
    @SerialName("created_at") val createdAt: Long = 0,
)

// -----------------------------------------------------------------
// 频道级播放器设置（per-channel override）
//
// 开启"频道记忆"后，每个频道可独立记忆播放器内核 / vo / hwdec / HDR 模式。
// 切换频道时自动应用该频道的设置（如有），实现不同频道用不同最佳配置。
// null 字段表示使用全局默认值。
// -----------------------------------------------------------------

@Serializable
data class ChannelPlayerSettings(
/** 播放器内核名称（仅 MPV），null=全局默认 */
val playerType: String? = null,
    /** 视频输出（gpu / mediacodec_embed），null=全局默认 */
    val vo: String? = null,
    /** 硬件解码模式（auto-copy / auto / no / mediacodec），null=全局默认 */
    val hwdec: String? = null,
    /** HDR 输出模式（disable / auto / tonemap / passthrough），null=全局默认 */
    val hdrMode: String? = null
)

// -----------------------------------------------------------------
// 频道映射
// -----------------------------------------------------------------

@Serializable
data class MappingEntry(
    @SerialName("unique_key") val uniqueKey: String = "",
    @SerialName("standard_name") val standardName: String = "",
    @SerialName("raw_name") val rawName: String = "",
    @SerialName("raw_names") val rawNames: List<String> = emptyList(),
    @SerialName("logo_url") val logoUrl: String? = null,
    @SerialName("group_name") val groupName: String? = null,
    @SerialName("tvg_id") val tvgId: String? = null,
    @SerialName("tvg_chno") val tvgChno: String? = null,
    @SerialName("tvg_shift") val tvgShift: String? = null,
    @SerialName("catchup") val catchup: String? = null,
    @SerialName("catchup_days") val catchupDays: String? = null,
    @SerialName("catchup_source") val catchupSource: String? = null,
    @SerialName("resolution") val resolution: String? = null,
)

// -----------------------------------------------------------------
// 字幕
// -----------------------------------------------------------------

@Serializable
data class SubtitleItem(
    @SerialName("source") val source: String = "",
    @SerialName("id") val id: String = "",
    @SerialName("file_name") val fileName: String = "",
    @SerialName("language") val language: String = "",
    @SerialName("language_id") val languageId: String = "",
    @SerialName("download_link") val downloadLink: String = "",
    @SerialName("zip_link") val zipLink: String = "",
    @SerialName("movie_name") val movieName: String = "",
    @SerialName("score") val score: Double = 0.0,
    @SerialName("rating") val rating: Double = 0.0,
    @SerialName("format") val format: String = "srt",
    @SerialName("encoding") val encoding: String = "UTF-8",
    @SerialName("title") val title: String = "",
    @SerialName("detail_url") val detailUrl: String = "",
    @SerialName("auto_download") val autoDownload: Boolean = false,
    @SerialName("bad") val bad: Boolean = false,
)

@Serializable
data class SubtitleSearchResponse(
    @SerialName("subtitles") val subtitles: List<SubtitleItem> = emptyList(),
    @SerialName("last_error") val lastError: String = "",
)

// -----------------------------------------------------------------
// 倍速双步进控制配置（与侧边栏 Speed_value 对齐）
// -----------------------------------------------------------------

/**
 * 倍速参数配置。
 *
 * @param min 最小倍速（如 0.5）
 * @param max 最大倍速（如 3.0）
 * @param slowStep 慢放步进（如 0.25，速度 < 1.0 时使用）
 * @param fastStep 快放步进（如 0.5，速度 >= 1.0 且 < threshold 时使用）
 * @param fastStep2 二级快放步进（如 1.0，速度 >= threshold 时使用）
 * @param fastStep2Threshold 二级快放触发阈值（如 2.0）
 */
@Serializable
data class SpeedConfig(
    val min: Double = 0.5,
    val max: Double = 3.0,
    val slowStep: Double = 0.25,
    val fastStep: Double = 0.5,
    val fastStep2: Double = 1.0,
    val fastStep2Threshold: Double = 2.0
) {
    /**
     * 根据当前速度计算加速后的新速度。
     * - 速度 < 1.0：用 slowStep（从慢放区域逐步加速到 1.0）
     * - 1.0 <= 速度 < threshold：用 fastStep
     * - 速度 >= threshold：用 fastStep2（大步进快速到达 max）
     */
    fun speedUp(current: Double): Double {
        val step = when {
            current < 1.0 -> slowStep
            current < fastStep2Threshold -> fastStep
            else -> fastStep2
        }
        return (current + step).coerceIn(min, max)
    }

    /**
     * 根据当前速度计算减速后的新速度。
     * - 速度 > threshold：用 fastStep2（从高速区域大步减速）
     * - 1.0 < 速度 <= threshold：用 fastStep
     * - 速度 <= 1.0：用 slowStep（逐步减速到 min）
     */
    fun speedDown(current: Double): Double {
        val step = when {
            current > fastStep2Threshold -> fastStep2
            current > 1.0 -> fastStep
            else -> slowStep
        }
        return (current - step).coerceIn(min, max)
    }

    /** 格式化为侧边栏配置字符串 */
    fun toConfigString(): String = "$min,$max,$slowStep,$fastStep,$fastStep2,$fastStep2Threshold"
}

// -----------------------------------------------------------------
// 通用响应
// -----------------------------------------------------------------

@Serializable
data class OkResponse(
    @SerialName("ok") val ok: Boolean = false,
)

@Serializable
data class CountResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("count") val count: Int = 0,
)

@Serializable
data class ImportedResponse(
    @SerialName("imported") val imported: Int = 0,
    @SerialName("epg_url") val epgUrl: String = "",
)

@Serializable
data class ClearedResponse(
    @SerialName("cleared") val cleared: Int = 0,
)

@Serializable
data class IdxResponse(
    @SerialName("idx") val idx: Int = 0,
)

@Serializable
data class StartedResponse(
    @SerialName("started") val started: Boolean = false,
)

@Serializable
data class BatchEditResponse(
    @SerialName("changed") val changed: Int = 0,
    @SerialName("total") val total: Int = 0,
)

@Serializable
data class PlaybackSettingsResponse(
    @SerialName("settings") val settings: Map<String, String> = emptyMap(),
)

@Serializable
data class PathResponse(
    @SerialName("path") val path: String = "",
)

@Serializable
data class ClearCacheResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("deleted_count") val deletedCount: Int = 0,
)

@Serializable
data class ThumbnailPathsResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("paths") val paths: Map<String, String> = emptyMap(),
)

@Serializable
data class GenerateThumbnailBgResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("path") val path: String = "",
    @SerialName("cached") val cached: Boolean = false,
)

@Serializable
data class M3uTextResponse(
    @SerialName("text") val text: String = "",
    @SerialName("count") val count: Int = 0,
)

// -----------------------------------------------------------------
// 局域网管理服务器
// -----------------------------------------------------------------

@Serializable
data class AdminServerInfo(
    @SerialName("url") val url: String = "",
    @SerialName("port") val port: Int = 0,
    @SerialName("running") val running: Boolean = false,
    @SerialName("already_running") val alreadyRunning: Boolean = false,
    @SerialName("error") val error: String = "",
    @SerialName("token") val token: String = "",
)

/** 设置访问令牌响应 */
@Serializable
data class TokenResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("token") val token: String = "",
)

/** 虚拟遥控器命令轮询响应 */
@Serializable
data class RemoteCommandResponse(
    @SerialName("cmd") val cmd: String? = null,
)

// -----------------------------------------------------------------
// 最近打开（与 PC 端 recent_menu 对齐）
// -----------------------------------------------------------------

/**
 * 最近打开的文件/URL 条目。
 * @param uri 文件 URI 或 URL
 * @param name 显示名称
 * @param type 类型："playlist" / "url" / "video"
 * @param timestamp 打开时间戳（毫秒）
 */
data class RecentEntry(
    val uri: String,
    val name: String,
    val type: String,
    val timestamp: Long,
)
