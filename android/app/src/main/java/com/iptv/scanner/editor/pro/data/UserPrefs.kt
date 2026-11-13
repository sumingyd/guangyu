package com.iptv.scanner.editor.pro.data

import android.content.Context
import android.content.SharedPreferences
import com.iptv.scanner.editor.pro.data.store.BookmarkStore
import com.iptv.scanner.editor.pro.data.store.EpgSettingsStore
import com.iptv.scanner.editor.pro.data.store.FavoriteStore
import com.iptv.scanner.editor.pro.data.store.HistoryStore
import com.iptv.scanner.editor.pro.data.store.NetworkSettingsStore
import com.iptv.scanner.editor.pro.data.store.PlayerSettingsStore
import com.iptv.scanner.editor.pro.data.store.QueueStore
import com.iptv.scanner.editor.pro.data.store.ResumeStore
import org.json.JSONArray
import org.json.JSONObject

/**
 * 用户偏好持久化门面：委托 8 个域存储，保持对外 API 兼容。
 *
 * 域存储：
 * - FavoriteStore：收藏（idx + URL，O(1) 缓存查询）
 * - HistoryStore：历史（idx + URL）
 * - QueueStore：队列（idx + URL）
 * - PlayerSettingsStore：播放器设置（vo/hwdec/HDR/RTSP/反交错/类型/超时/重连/锁定/倍速/频道级）
 * - EpgSettingsStore：EPG 设置（时区偏移/缓存定时）
 * - NetworkSettingsStore：网络设置（Referer/Proxy/Headers）
 * - BookmarkStore：书签
 * - ResumeStore：续播位置
 *
 * 剩余设置（开机自启/分屏/分组/日志/主题/最近文件/管理服务器/提醒/TV/屏保/竖屏/OSD/强制TV）
 * 体量较小，保留在门面中。
 *
 * SharedPreferences 键名不变，仅重组方法分布，保证向后兼容。
 */
class UserPrefs private constructor() {

    private lateinit var prefs: SharedPreferences

    private lateinit var favoriteStore: FavoriteStore
    private lateinit var historyStore: HistoryStore
    private lateinit var queueStore: QueueStore
    private lateinit var playerSettingsStore: PlayerSettingsStore
    private lateinit var epgSettingsStore: EpgSettingsStore
    private lateinit var networkSettingsStore: NetworkSettingsStore
    private lateinit var bookmarkStore: BookmarkStore
    private lateinit var resumeStore: ResumeStore

    fun init(context: Context) {
        prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        favoriteStore = FavoriteStore(prefs)
        historyStore = HistoryStore(prefs)
        queueStore = QueueStore(prefs)
        playerSettingsStore = PlayerSettingsStore(prefs, context.applicationContext)
        epgSettingsStore = EpgSettingsStore(prefs)
        networkSettingsStore = NetworkSettingsStore(prefs)
        bookmarkStore = BookmarkStore(prefs)
        resumeStore = ResumeStore(prefs)
        favoriteStore.initCache()
    }

    // -----------------------------------------------------------------
    // 收藏（委托 FavoriteStore）
    // -----------------------------------------------------------------

    fun getFavorites(): Set<Int> = favoriteStore.getFavorites()
    fun isFavorite(idx: Int): Boolean = favoriteStore.isFavorite(idx)
    fun toggleFavorite(idx: Int): Boolean = favoriteStore.toggleFavorite(idx)
    fun setFavorites(favorites: Set<Int>) = favoriteStore.setFavorites(favorites)

    fun getFavoriteUrls(): Set<String> = favoriteStore.getFavoriteUrls()
    fun isFavoriteUrl(url: String): Boolean = favoriteStore.isFavoriteUrl(url)
    fun toggleFavoriteUrl(url: String): Boolean = favoriteStore.toggleFavoriteUrl(url)
    fun setFavoriteUrls(urls: Set<String>) = favoriteStore.setFavoriteUrls(urls)

    // -----------------------------------------------------------------
    // 历史（委托 HistoryStore）
    // -----------------------------------------------------------------

    fun getHistory(): List<Int> = historyStore.getHistory()
    fun addToHistory(idx: Int) = historyStore.addToHistory(idx)
    fun clearHistory() = historyStore.clearHistory()
    fun setHistory(history: List<Int>) = historyStore.setHistory(history)

    fun getHistoryUrls(): List<String> = historyStore.getHistoryUrls()
    fun addToHistoryUrl(url: String) = historyStore.addToHistoryUrl(url)
    fun setHistoryUrls(urls: List<String>) = historyStore.setHistoryUrls(urls)

    // -----------------------------------------------------------------
    // 队列（委托 QueueStore）
    // -----------------------------------------------------------------

    fun getQueue(): List<Int> = queueStore.getQueue()
    fun addToQueue(idx: Int) = queueStore.addToQueue(idx)
    fun removeFromQueue(idx: Int) = queueStore.removeFromQueue(idx)
    fun clearQueue() = queueStore.clearQueue()
    fun setQueue(queue: List<Int>) = queueStore.setQueue(queue)

    fun getQueueUrls(): List<String> = queueStore.getQueueUrls()
    fun addToQueueUrl(url: String) = queueStore.addToQueueUrl(url)
    fun removeFromQueueUrl(url: String) = queueStore.removeFromQueueUrl(url)
    fun setQueueUrls(urls: List<String>) = queueStore.setQueueUrls(urls)

    // -----------------------------------------------------------------
    // 上次播放频道（启动时恢复）
    // -----------------------------------------------------------------

    fun getLastChannelUrl(): String = prefs.getString(KEY_LAST_CHANNEL_URL, "") ?: ""
    fun setLastChannelUrl(url: String) {
        prefs.edit().putString(KEY_LAST_CHANNEL_URL, url).apply()
    }

    fun isAutoResumeOnStart(): Boolean = prefs.getBoolean(KEY_AUTO_RESUME, DEFAULT_AUTO_RESUME)
    fun setAutoResumeOnStart(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_AUTO_RESUME, enabled).apply()
    }

    // -----------------------------------------------------------------
    // 播放器设置（委托 PlayerSettingsStore）
    // -----------------------------------------------------------------

    fun getVo(): String = playerSettingsStore.getVo()
    fun setVo(vo: String) = playerSettingsStore.setVo(vo)
    /** 用户是否显式选择过 vo（未选择时为 ABI 默认值） */
    fun hasExplicitVo(): Boolean = playerSettingsStore.hasExplicitVo()
    /** 默认 mediacodec_embed 是否已自动回退到 gpu */
    fun isVoAutoFallback(): Boolean = playerSettingsStore.isVoAutoFallback()
    fun setVoAutoFallback(fallback: Boolean) = playerSettingsStore.setVoAutoFallback(fallback)
    fun getHwdec(): String = playerSettingsStore.getHwdec()
    fun setHwdec(hwdec: String) = playerSettingsStore.setHwdec(hwdec)
    /** 用户手动改过渲染方式：默认值迁移不得覆盖 */
    fun markRenderPathUserChosen() = playerSettingsStore.markRenderPathUserChosen()

    /** 是否为 arm32 TV 设备（硬解只走 mediacodec_embed） */
    fun isArm32TvDevice(): Boolean = playerSettingsStore.isArm32TvDevice()

    /** 电视/盒子硬解是否必须走 mediacodec_embed（禁用 AImageReader/copy-back） */
    fun isTvEmbedRequired(): Boolean = playerSettingsStore.isTvEmbedRequired()

    /** 切换硬/软解时的目标 vo / hwdec */
    fun voForHardwareDecode(enabled: Boolean, currentVo: String): String =
        playerSettingsStore.voForHardwareDecode(enabled, currentVo)

    fun hwdecForHardwareDecode(enabled: Boolean, currentHwdec: String): String =
        playerSettingsStore.hwdecForHardwareDecode(enabled, currentHwdec)

    /** 是否处于「硬解导致崩溃」的设备黑名单（强制软解） */
    fun isHwdecBlacklisted(): Boolean = playerSettingsStore.isHwdecBlacklisted()

    /** 指定 vo+hwdec 组合是否命中崩溃黑名单 */
    fun isHwdecComboBlacklisted(vo: String, hwdec: String): Boolean =
        playerSettingsStore.isHwdecComboBlacklisted(vo, hwdec)

    /** 按设备纠正 hwdec（arm32 TV 的 copy-back 统一改为 mediacodec 直写） */
    fun normalizeHwdecForDevice(hwdec: String): String =
        playerSettingsStore.normalizeHwdecForDevice(hwdec)

    /** 是否为手机（arm64 手持设备，GPU 路径走 AImageReader 直通） */
    fun isHandheldDevice(): Boolean = playerSettingsStore.isHandheldDevice()

    fun setHwdecBlacklisted(blacklisted: Boolean) = playerSettingsStore.setHwdecBlacklisted(blacklisted)
    fun isVoFallbackConfirmed(): Boolean = playerSettingsStore.isVoFallbackConfirmed()
    fun setVoFallbackConfirmed(confirmed: Boolean) = playerSettingsStore.setVoFallbackConfirmed(confirmed)

    /** 直写 Surface 起播兜底：初始化前打标记、首帧后清除、启动时判定上次是否崩在起播 */
    fun beginEmbedSession() = playerSettingsStore.beginEmbedSession()
    fun endEmbedSession() = playerSettingsStore.endEmbedSession()
    fun recoverPendingEmbedSession() = playerSettingsStore.recoverPendingEmbedSession()
    /** 判定 mediacodec_embed + mediacodec 不可用：写黑名单组合并置自动回退 */
    fun markEmbedComboUnusable() = playerSettingsStore.markEmbedComboUnusable()
    fun getHdrMode(): String = playerSettingsStore.getHdrMode()
    fun setHdrMode(mode: String) = playerSettingsStore.setHdrMode(mode)

    /** 色彩兼容模式（默认关闭，不改变现有用户画面） */
    fun isColorCompatMode(): Boolean = playerSettingsStore.isColorCompatMode()
    fun setColorCompatMode(enabled: Boolean) = playerSettingsStore.setColorCompatMode(enabled)
    fun getRtspTransport(): String = playerSettingsStore.getRtspTransport()
    fun setRtspTransport(transport: String) = playerSettingsStore.setRtspTransport(transport)
    fun getExoSurfaceView(): Boolean = playerSettingsStore.getExoSurfaceView()
    fun setExoSurfaceView(useSurfaceView: Boolean) = playerSettingsStore.setExoSurfaceView(useSurfaceView)
    fun getDeinterlace(): String = playerSettingsStore.getDeinterlace()
    fun setDeinterlace(value: String) = playerSettingsStore.setDeinterlace(value)
    fun resetPlayerSettings() = playerSettingsStore.resetPlayerSettings()
    fun getPlayerType(): String = playerSettingsStore.getPlayerType()
    fun setPlayerType(type: String) = playerSettingsStore.setPlayerType(type)
    fun getTimeoutSwitchSource(): Int = playerSettingsStore.getTimeoutSwitchSource()
    fun setTimeoutSwitchSource(value: Int) = playerSettingsStore.setTimeoutSwitchSource(value)
    fun getTimeoutMs(): Long = playerSettingsStore.getTimeoutMs()
    fun getReconnectIndex(): Int = playerSettingsStore.getReconnectIndex()
    fun setReconnectIndex(value: Int) = playerSettingsStore.setReconnectIndex(value)
    fun getReconnectDelayMs(): Long = playerSettingsStore.getReconnectDelayMs()
    fun getScreenLock(): Boolean = playerSettingsStore.getScreenLock()
    fun setScreenLock(enabled: Boolean) = playerSettingsStore.setScreenLock(enabled)
    fun getLiquidGlass(): Boolean = playerSettingsStore.getLiquidGlass()
    fun setLiquidGlass(enabled: Boolean) = playerSettingsStore.setLiquidGlass(enabled)
    fun getSpeedParams(): String = playerSettingsStore.getSpeedParams()
    fun setSpeedParams(params: String) = playerSettingsStore.setSpeedParams(params)
    fun getSpeedConfig(): SpeedConfig = playerSettingsStore.getSpeedConfig()
    fun isPerChannelPlayerSettings(): Boolean = playerSettingsStore.isPerChannelPlayerSettings()
    fun setPerChannelPlayerSettings(enabled: Boolean) = playerSettingsStore.setPerChannelPlayerSettings(enabled)
    fun getChannelSettings(idx: Int): ChannelPlayerSettings? = playerSettingsStore.getChannelSettings(idx)
    fun setChannelSettings(idx: Int, settings: ChannelPlayerSettings) = playerSettingsStore.setChannelSettings(idx, settings)
    fun removeChannelSettings(idx: Int) = playerSettingsStore.removeChannelSettings(idx)

    // -----------------------------------------------------------------
    // EPG 设置（委托 EpgSettingsStore）
    // -----------------------------------------------------------------

    fun getEpgTimezoneOffset(): Int = epgSettingsStore.getEpgTimezoneOffset()
    fun setEpgTimezoneOffset(value: Int) = epgSettingsStore.setEpgTimezoneOffset(value)
    fun getEpgTimezoneOffsetHours(): Int = epgSettingsStore.getEpgTimezoneOffsetHours()
    fun getEpgCacheSchedule(): Int = epgSettingsStore.getEpgCacheSchedule()
    fun setEpgCacheSchedule(value: Int) = epgSettingsStore.setEpgCacheSchedule(value)
    fun getEpgCacheHour(): Int = epgSettingsStore.getEpgCacheHour()

    // -----------------------------------------------------------------
    // 网络设置（委托 NetworkSettingsStore）
    // -----------------------------------------------------------------

    fun getHttpReferer(): String = networkSettingsStore.getHttpReferer()
    fun setHttpReferer(value: String) = networkSettingsStore.setHttpReferer(value)
    fun getHttpProxy(): String = networkSettingsStore.getHttpProxy()
    fun setHttpProxy(value: String) = networkSettingsStore.setHttpProxy(value)
    fun getHttpHeaders(): String = networkSettingsStore.getHttpHeaders()
    fun setHttpHeaders(value: String) = networkSettingsStore.setHttpHeaders(value)

    // -----------------------------------------------------------------
    // 书签（委托 BookmarkStore）
    // -----------------------------------------------------------------

    fun getBookmarks(url: String): List<BookmarkItem> = bookmarkStore.getBookmarks(url)
    fun getAllBookmarks(): List<BookmarkItem> = bookmarkStore.getAllBookmarks()
    fun addBookmark(url: String, position: Long, name: String = ""): List<BookmarkItem> =
        bookmarkStore.addBookmark(url, position, name)
    fun deleteBookmark(url: String, position: Long): Boolean = bookmarkStore.deleteBookmark(url, position)
    fun clearBookmarks(url: String) = bookmarkStore.clearBookmarks(url)
    fun clearAllBookmarks() = bookmarkStore.clearAllBookmarks()

    // -----------------------------------------------------------------
    // 续播（委托 ResumeStore）
    // -----------------------------------------------------------------

    fun getResumeList(): List<ResumeItem> = resumeStore.getResumeList()
    fun getResume(url: String): ResumeItem? = resumeStore.getResume(url)
    fun saveResume(item: ResumeItem): List<ResumeItem> = resumeStore.saveResume(item)
    fun removeResume(url: String): Boolean = resumeStore.removeResume(url)
    fun clearResume() = resumeStore.clearResume()

    // -----------------------------------------------------------------
    // 开机自启动
    // -----------------------------------------------------------------

    fun getBootStart(): Boolean = prefs.getBoolean(KEY_BOOT_START, false)
    fun setBootStart(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_BOOT_START, enabled).apply()
    }

    fun isScreenSaverEnabled(): Boolean =
        prefs.getBoolean(KEY_SCREEN_SAVER_ENABLED, DEFAULT_SCREEN_SAVER_ENABLED)

    fun setScreenSaverEnabled(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_SCREEN_SAVER_ENABLED, enabled).apply()
    }

    fun getScreenSaverTimeoutMinutes(): Int =
        prefs.getInt(KEY_SCREEN_SAVER_TIMEOUT_MIN, DEFAULT_SCREEN_SAVER_TIMEOUT_MIN)
            .coerceIn(1, 60)

    fun setScreenSaverTimeoutMinutes(minutes: Int) {
        prefs.edit().putInt(KEY_SCREEN_SAVER_TIMEOUT_MIN, minutes.coerceIn(1, 60)).apply()
    }

    // -----------------------------------------------------------------
    // 分屏模式
    // -----------------------------------------------------------------

    fun getSplitMode(): Boolean = prefs.getBoolean(KEY_SPLIT_MODE, false)
    fun setSplitMode(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_SPLIT_MODE, enabled).apply()
    }

    // -----------------------------------------------------------------
    // 横屏分屏模式（TV/横屏播放页：左视频+右常驻面板；关闭=全屏）
    // -----------------------------------------------------------------

    fun getLandscapeSplitMode(): Boolean = prefs.getBoolean(KEY_LANDSCAPE_SPLIT_MODE, true)
    fun setLandscapeSplitMode(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_LANDSCAPE_SPLIT_MODE, enabled).apply()
    }

    // -----------------------------------------------------------------
    // 全屏播放页 TV 底栏布局样式（0..11，名称与结构见 TvLayout.TV_BOTTOM_BAR_STYLES）
    // -----------------------------------------------------------------

    fun getBottomBarStyle(): Int = prefs.getInt(KEY_BOTTOM_BAR_STYLE, 0)
    fun setBottomBarStyle(value: Int) {
        prefs.edit().putInt(KEY_BOTTOM_BAR_STYLE, value.coerceIn(0, 11)).apply()
    }

    // -----------------------------------------------------------------
    // 二级分组模式（0=传统, 1=列表分组, 2=二级模式1, 3=二级模式2）
    // -----------------------------------------------------------------

    fun getGroupMode(): Int = prefs.getInt(KEY_GROUP_MODE, DEFAULT_GROUP_MODE)
    fun setGroupMode(value: Int) {
        prefs.edit().putInt(KEY_GROUP_MODE, value.coerceIn(0, 3)).apply()
    }

    // -----------------------------------------------------------------
    // 日志等级
    // -----------------------------------------------------------------

    fun getLogLevel(): String = prefs.getString(KEY_LOG_LEVEL, DEFAULT_LOG_LEVEL) ?: DEFAULT_LOG_LEVEL
    fun setLogLevel(level: String) {
        prefs.edit().putString(KEY_LOG_LEVEL, level).apply()
    }

    // -----------------------------------------------------------------
    // 主题模式
    // -----------------------------------------------------------------

    fun getThemeMode(): String = prefs.getString(KEY_THEME_MODE, DEFAULT_THEME_MODE) ?: DEFAULT_THEME_MODE
    fun setThemeMode(mode: String) {
        prefs.edit().putString(KEY_THEME_MODE, mode).apply()
    }

    // -----------------------------------------------------------------
    // 最近打开文件/URL
    // -----------------------------------------------------------------

    fun getRecentFiles(): List<RecentEntry> {
        val json = prefs.getString(KEY_RECENT_FILES, "[]") ?: "[]"
        return parseRecentFiles(json)
    }

    fun addRecentFile(entry: RecentEntry) {
        val cur = getRecentFiles().toMutableList()
        cur.removeAll { it.uri == entry.uri }
        cur.add(0, entry)
        if (cur.size > MAX_RECENT_FILES) {
            cur.subList(MAX_RECENT_FILES, cur.size).clear()
        }
        saveRecentFiles(cur)
    }

    fun removeRecentFile(uri: String) {
        val cur = getRecentFiles().toMutableList()
        cur.removeAll { it.uri == uri }
        saveRecentFiles(cur)
    }

    fun clearRecentFiles() {
        prefs.edit().putString(KEY_RECENT_FILES, "[]").apply()
    }

    private fun saveRecentFiles(list: List<RecentEntry>) {
        val arr = JSONArray()
        list.forEach { item ->
            arr.put(JSONObject().apply {
                put("uri", item.uri)
                put("name", item.name)
                put("type", item.type)
                put("ts", item.timestamp)
            })
        }
        prefs.edit().putString(KEY_RECENT_FILES, arr.toString()).apply()
    }

    private fun parseRecentFiles(json: String): List<RecentEntry> {
        if (json.isEmpty()) return emptyList()
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).mapNotNull { idx ->
                val obj = arr.optJSONObject(idx) ?: return@mapNotNull null
                RecentEntry(
                    uri = obj.optString("uri"),
                    name = obj.optString("name"),
                    type = obj.optString("type"),
                    timestamp = obj.optLong("ts", 0),
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    // -----------------------------------------------------------------
    // 局域网管理设置
    // -----------------------------------------------------------------

    fun getAdminAutoStop(): Boolean = prefs.getBoolean(KEY_ADMIN_AUTO_STOP, DEFAULT_ADMIN_AUTO_STOP)
    fun setAdminAutoStop(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_ADMIN_AUTO_STOP, enabled).apply()
    }

    // -----------------------------------------------------------------
    // 节目提醒
    // -----------------------------------------------------------------

    fun getReminders(): List<ReminderItem> {
        val json = prefs.getString(KEY_REMINDERS, "[]") ?: "[]"
        return parseReminders(json)
    }

    fun hasReminder(id: String): Boolean = getReminders().any { it.id == id }

    fun addReminder(item: ReminderItem): Boolean {
        val cur = getReminders().toMutableList()
        if (cur.any { it.id == item.id }) return false
        cur.add(item)
        saveReminders(cur)
        return true
    }

    fun removeReminder(id: String): Boolean {
        val cur = getReminders().toMutableList()
        val removed = cur.removeAll { it.id == id }
        if (removed) saveReminders(cur)
        return removed
    }

    fun clearReminders() {
        prefs.edit().putString(KEY_REMINDERS, "[]").apply()
    }

    fun setReminders(list: List<ReminderItem>) {
        saveReminders(list)
    }

    private fun saveReminders(list: List<ReminderItem>) {
        val arr = JSONArray()
        list.forEach { item ->
            arr.put(JSONObject().apply {
                put("id", item.id)
                put("channel_idx", item.channelIdx)
                put("channel_name", item.channelName)
                put("tvg_id", item.tvgId)
                put("program_title", item.programTitle)
                put("start_ts", item.startTs)
                put("stop_ts", item.stopTs)
                put("created_at", item.createdAt)
            })
        }
        prefs.edit().putString(KEY_REMINDERS, arr.toString()).apply()
    }

    private fun parseReminders(json: String): List<ReminderItem> {
        if (json.isEmpty()) return emptyList()
        return try {
            val arr = JSONArray(json)
            (0 until arr.length()).mapNotNull { idx ->
                val obj = arr.optJSONObject(idx) ?: return@mapNotNull null
                ReminderItem(
                    id = obj.optString("id"),
                    channelIdx = obj.optInt("channel_idx", -1),
                    channelName = obj.optString("channel_name"),
                    tvgId = obj.optString("tvg_id"),
                    programTitle = obj.optString("program_title"),
                    startTs = obj.optLong("start_ts", 0),
                    stopTs = obj.optLong("stop_ts", 0),
                    createdAt = obj.optLong("created_at", 0),
                )
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    // -----------------------------------------------------------------
    // TV 开机直接播放
    // -----------------------------------------------------------------

    fun isDirectPlayOnBoot(): Boolean = prefs.getBoolean(KEY_DIRECT_PLAY_ON_BOOT, DEFAULT_DIRECT_PLAY_ON_BOOT)
    fun setDirectPlayOnBoot(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_DIRECT_PLAY_ON_BOOT, enabled).apply()
    }

    // -----------------------------------------------------------------
    // TV 屏保超时（分钟，0=关闭）
    // -----------------------------------------------------------------

    fun getScreensaverTimeout(): Int = prefs.getInt(KEY_SCREENSAVER_TIMEOUT, DEFAULT_SCREENSAVER_TIMEOUT)
    fun setScreensaverTimeout(minutes: Int) {
        prefs.edit().putInt(KEY_SCREENSAVER_TIMEOUT, minutes.coerceAtLeast(0)).apply()
    }

    // -----------------------------------------------------------------
    // 竖屏全屏模式
    // -----------------------------------------------------------------

    fun isPortraitFullscreen(): Boolean = prefs.getBoolean(KEY_PORTRAIT_FULLSCREEN, DEFAULT_PORTRAIT_FULLSCREEN)
    fun setPortraitFullscreen(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_PORTRAIT_FULLSCREEN, enabled).apply()
    }

    // -----------------------------------------------------------------
    // 侧边栏风格显示设置开关项
    // -----------------------------------------------------------------

    fun isOsdShowTime(): Boolean = prefs.getBoolean(KEY_OSD_SHOW_TIME, true)
    fun setOsdShowTime(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_SHOW_TIME, enabled).apply() }

    fun isOsdShowNetSpeed(): Boolean = prefs.getBoolean(KEY_OSD_SHOW_NETSPEED, true)
    fun setOsdShowNetSpeed(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_SHOW_NETSPEED, enabled).apply() }

    fun isOsdHideChannelNum(): Boolean = prefs.getBoolean(KEY_OSD_HIDE_CHANNEL_NUM, false)
    fun setOsdHideChannelNum(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_HIDE_CHANNEL_NUM, enabled).apply() }

    fun isOsdDisableEpg(): Boolean = prefs.getBoolean(KEY_OSD_DISABLE_EPG, false)
    fun setOsdDisableEpg(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_DISABLE_EPG, enabled).apply() }

    fun isOsdDisableFavorite(): Boolean = prefs.getBoolean(KEY_OSD_DISABLE_FAVORITE, false)
    fun setOsdDisableFavorite(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_DISABLE_FAVORITE, enabled).apply() }

    fun isOsdShowListIcon(): Boolean = prefs.getBoolean(KEY_OSD_SHOW_LIST_ICON, true)
    fun setOsdShowListIcon(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_SHOW_LIST_ICON, enabled).apply() }

    fun isOsdShowBottomIcon(): Boolean = prefs.getBoolean(KEY_OSD_SHOW_BOTTOM_ICON, true)
    fun setOsdShowBottomIcon(enabled: Boolean) { prefs.edit().putBoolean(KEY_OSD_SHOW_BOTTOM_ICON, enabled).apply() }

    // -----------------------------------------------------------------
    // 界面模式（自动 / 手机 / 平板 / TV）
    // -----------------------------------------------------------------

    /** 手动界面模式：auto / phone / tablet / tv */
    fun getUiModePreference(): String =
        prefs.getString(KEY_UI_MODE_OVERRIDE, DEFAULT_UI_MODE_OVERRIDE) ?: DEFAULT_UI_MODE_OVERRIDE

    fun setUiModePreference(value: String) {
        prefs.edit().putString(KEY_UI_MODE_OVERRIDE, value).apply()
    }

    // -----------------------------------------------------------------
    // 强制 TV 模式（调试/模拟器用）
    // -----------------------------------------------------------------

    fun isForceTvMode(): Boolean = prefs.getBoolean("force_tv_mode", false)
    fun setForceTvMode(enabled: Boolean) { prefs.edit().putBoolean("force_tv_mode", enabled).apply() }

    companion object {
        /** SharedPreferences 文件名。internal 供启动早期（UserPrefs.init 之前）直接读取 */
        internal const val PREFS_NAME = "iptv_user_prefs"

        private const val KEY_LAST_CHANNEL_URL = "last_channel_url"
        private const val KEY_AUTO_RESUME = "auto_resume_on_start"
        private const val DEFAULT_AUTO_RESUME = false

        private const val KEY_BOOT_START = "boot_start"
        private const val KEY_SPLIT_MODE = "split_mode"
        private const val KEY_LANDSCAPE_SPLIT_MODE = "landscape_split_mode"
        private const val KEY_BOTTOM_BAR_STYLE = "bottom_bar_style"
        private const val KEY_GROUP_MODE = "group_mode"
        private const val DEFAULT_GROUP_MODE = 3

        private const val KEY_LOG_LEVEL = "log_level"
        private const val DEFAULT_LOG_LEVEL = "info"

        private const val KEY_THEME_MODE = "theme_mode"
        private const val DEFAULT_THEME_MODE = "dark"

        // 屏保（默认开启：仅在「无操作 + 无面板 + 未播放」时出现，不会遮挡正在播放的视频；
        // 长时间停留首页/暂停时可省电并降低 OLED 烧屏风险）
        private const val KEY_SCREEN_SAVER_ENABLED = "screensaver_enabled"
        private const val KEY_SCREEN_SAVER_TIMEOUT_MIN = "screensaver_timeout_min"
        private const val DEFAULT_SCREEN_SAVER_ENABLED = true
        private const val DEFAULT_SCREEN_SAVER_TIMEOUT_MIN = 5

        private const val KEY_RECENT_FILES = "recent_files"
        private const val MAX_RECENT_FILES = 20

        private const val KEY_ADMIN_AUTO_STOP = "admin_auto_stop"
        private const val DEFAULT_ADMIN_AUTO_STOP = true

        private const val KEY_REMINDERS = "epg_reminders"

        private const val KEY_DIRECT_PLAY_ON_BOOT = "direct_play_on_boot"
        private const val DEFAULT_DIRECT_PLAY_ON_BOOT = false

        private const val KEY_SCREENSAVER_TIMEOUT = "screensaver_timeout"
        private const val DEFAULT_SCREENSAVER_TIMEOUT = 5

        private const val KEY_PORTRAIT_FULLSCREEN = "portrait_fullscreen"
        private const val DEFAULT_PORTRAIT_FULLSCREEN = false

        private const val KEY_UI_MODE_OVERRIDE = "ui_mode_override"
        private const val DEFAULT_UI_MODE_OVERRIDE = "auto"

        // SharedPreferences key 值保留 "ku9_*" 以兼容用户已有设置
        private const val KEY_OSD_SHOW_TIME = "ku9_show_time"
        private const val KEY_OSD_SHOW_NETSPEED = "ku9_show_netspeed"
        private const val KEY_OSD_HIDE_CHANNEL_NUM = "ku9_hide_channel_num"
        private const val KEY_OSD_DISABLE_EPG = "ku9_disable_epg"
        private const val KEY_OSD_DISABLE_FAVORITE = "ku9_disable_favorite"
        private const val KEY_OSD_SHOW_LIST_ICON = "ku9_show_list_icon"
        private const val KEY_OSD_SHOW_BOTTOM_ICON = "ku9_show_bottom_icon"

        @Volatile
        private var INSTANCE: UserPrefs? = null

        fun getInstance(): UserPrefs =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: UserPrefs().also { INSTANCE = it }
            }

        fun init(context: Context) = getInstance().init(context)
    }
}
