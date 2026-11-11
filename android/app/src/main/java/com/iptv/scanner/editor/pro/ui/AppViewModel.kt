package com.iptv.scanner.editor.pro.ui

import android.app.Application
import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.media.MediaMetadataRetriever
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.iptv.scanner.editor.pro.data.IptvChannel
import com.iptv.scanner.editor.pro.data.IptvEpgList
import com.iptv.scanner.editor.pro.data.IptvEpgProgram
import com.iptv.scanner.editor.pro.data.IptvEpgSource
import com.iptv.scanner.editor.pro.data.IptvGroup
import com.iptv.scanner.editor.pro.data.IptvRepository
import com.iptv.scanner.editor.pro.data.IptvSource
import com.iptv.scanner.editor.pro.data.IptvStatus
import com.iptv.scanner.editor.pro.data.MappingEntry
import com.iptv.scanner.editor.pro.data.ReminderItem
import com.iptv.scanner.editor.pro.data.RecentEntry
import com.iptv.scanner.editor.pro.data.ResumeItem
import com.iptv.scanner.editor.pro.data.BookmarkItem
import com.iptv.scanner.editor.pro.data.ChannelPlayerSettings
import com.iptv.scanner.editor.pro.data.ScanResult
import com.iptv.scanner.editor.pro.data.ScanStatus
import com.iptv.scanner.editor.pro.data.SubtitleItem
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.mpv.MpvController
import com.iptv.scanner.editor.pro.player.CatchupHelper
import com.iptv.scanner.editor.pro.player.CatchupProgram
import com.iptv.scanner.editor.pro.player.ExoPlayerWrapper
import com.iptv.scanner.editor.pro.player.FccService
import com.iptv.scanner.editor.pro.player.PlayMode
import com.iptv.scanner.editor.pro.player.SubPlayer
import com.iptv.scanner.editor.pro.player.SubPlayerState
import com.iptv.scanner.editor.pro.player.PlaybackState
import com.iptv.scanner.editor.pro.player.Player
import com.iptv.scanner.editor.pro.data.SpeedConfig
import com.iptv.scanner.editor.pro.player.PlayerCapabilities
import com.iptv.scanner.editor.pro.player.PlayerType
import com.iptv.scanner.editor.pro.player.ProgressHelper
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

data class ChannelDisplayInfo(
    val name: String = "",
    val logo: String = "",
    val group: String = "",
    val idx: Int = -1,
    val isLocal: Boolean = false
)

sealed class InitState {
    object Idle : InitState()
    object Initializing : InitState()
    data class Ready(val status: IptvStatus) : InitState()
    data class Failed(val message: String) : InitState()
}

enum class ChannelTab { SUB, LOCAL, FAV, HIST }

enum class PortraitTab { CHANNELS, FAVORITES, TOOLS, SETTINGS }

enum class ListViewMode { LIST, THUMBNAIL }

enum class ListSourceTab { SUBSCRIPTION, LOCAL }

data class OsdInfo(val title: String, val subtitle: String = "", val extra: String = "")

data class LyricsLine(val time: Long, val text: String)

enum class FileBrowserMode { PLAYLIST, MEDIA }

enum class SourceTab { PLAYLIST, EPG }

sealed class UpdateState {
    object Idle : UpdateState()
    object Checking : UpdateState()
    data class UpdateAvailable(val latestVersion: String, val downloadUrl: String, val releaseUrl: String) : UpdateState()
    object UpToDate : UpdateState()
    data class Error(val message: String) : UpdateState()
}

sealed class ApkDownloadState {
    object Idle : ApkDownloadState()
    data class Downloading(val progress: Int) : ApkDownloadState()  // 0-100
    object Completed : ApkDownloadState()
    data class Error(val message: String) : ApkDownloadState()
}

enum class EpgTimelineRange { ALL, FAVORITES, CURRENT_GROUP }

data class EpgTimelineRow(
    val channelIdx: Int,
    val channelName: String,
    /** 显示名：同名多路流追加分辨率后缀（channelName 仍是身份兜底用的原始名称） */
    val displayName: String = "",
    val programs: List<IptvEpgProgram>,
    /** 节目数据是否已加载（懒加载骨架行=false，可见窗口内由 ensureEpgTimelineRowsLoaded 填充） */
    val programsLoaded: Boolean = true
)

enum class SearchScope { ALL, CHANNELS, PROGRAMS }

sealed class SearchResult {
    data class ChannelResult(val idx: Int, val channel: IptvChannel) : SearchResult()
    data class ProgramResult(
        val channelIdx: Int,
        val channelName: String,
        val program: IptvEpgProgram
    ) : SearchResult()
}

enum class HdrMode { DISABLE, AUTO, TONEMAP, PASSTHROUGH }

class AppViewModel(app: Application) : AndroidViewModel(app) {

    internal val repository = IptvRepository.getInstance()
    internal val userPrefs = UserPrefs.getInstance().also { it.init(app) }
    internal val fccService = FccService()

// 播放器架构：MPV / ExoPlayer 两内核可切换，每种内核都支持硬解/软解
//
// - mpvSingleton：MpvController 单例（MPVLib.create 只能调一次，需复用）
// - exoWrapper：ExoPlayerWrapper 实例（通过 setHardwareDecode 切换硬解/软解）
// - mpv：公共字段（类型为 Player 接口），当前活跃的播放器实例
// - playerType：当前播放器类型（MPV / EXO）
// - playerCapabilities：当前播放器能力（UI 据此决定哪些功能面板可用）
//
// 切换播放器类型时：
// 1. 停止当前播放器并 detach View
// 2. 切换 _player 到新播放器实例
// 3. MainPlayerScreen 根据 playerType 创建对应的 View（MPVView / PlayerView）
// 4. 新 View 的 factory 中调用 player.attachView(view) 绑定
    internal val mpvSingleton: MpvController = MpvController.getInstance()
    internal var exoWrapper: ExoPlayerWrapper? = null

    internal val _playerType = MutableStateFlow(
        PlayerType.fromName(userPrefs.getPlayerType())
    )
    val playerType: StateFlow<PlayerType> = _playerType.asStateFlow()

    /** 内核切换后待播放的 URL（延迟播放机制：等 Compose 重建视图后再 playFile） */
    internal val _pendingSwitchPlayUrl = MutableStateFlow("")
    val pendingSwitchPlayUrl: StateFlow<String> = _pendingSwitchPlayUrl.asStateFlow()

internal val _player = MutableStateFlow<Player>(
when (_playerType.value) {
PlayerType.MPV -> mpvSingleton
PlayerType.EXO -> {
ExoPlayerWrapper(getApplication()).also {
exoWrapper = it
// 4K 首帧看门狗：SurfaceView 不吐首帧时切 TextureView（仅同一次进程请求一次）
it.onRequestTextureViewFallback = {
    if (exoSurfaceView.value) {
        showOsd("画面输出已切换", "4K 首帧超时，已改用 TextureView 输出")
        setExoSurfaceView(false)
    }
}
}
}
}
)

    /** 当前播放器实例（Player 接口类型，UI 用 mpv.xxx 调用 Player 接口方法） */
    val mpv: Player get() = _player.value

    val playerCapabilities: StateFlow<PlayerCapabilities> =
        _player.map { it.capabilities }
            .stateIn(viewModelScope, SharingStarted.Eagerly, mpvSingleton.capabilities)

    // UI 模式（手机触摸 / 平板触摸 / TV 遥控器）
    internal val _uiMode = MutableStateFlow(UiModeDetector.detect(app))
    val uiMode: StateFlow<UiMode> = _uiMode.asStateFlow()

    /** 设置页「界面模式」：自动 / 手机 / 平板 / TV */
    internal val _uiModePref = MutableStateFlow(
        UiModePreference.fromStorage(userPrefs.getUiModePreference())
    )
    val uiModePref: StateFlow<UiModePreference> = _uiModePref.asStateFlow()

    /**
     * 切换界面模式：持久化后立即重算布局，不用重启。
     * 同时清理旧布局的悬浮层，避免侧边栏/底栏状态残留到新布局。
     */
    fun setUiModePreference(pref: UiModePreference) {
        _uiModePref.value = pref
        userPrefs.setUiModePreference(pref.storageValue)
        val old = _uiMode.value
        val next = UiModeDetector.detect(getApplication())
        if (old == next) return
        _uiMode.value = next
        closeAllPanels()
        _landscapeSidebarVisible.value = false
        _stylePickerOpen.value = false
        _stylePreview.value = null
        _controlsVisible.value = false
        _controlsPinned.value = false
        if (next == UiMode.TV) {
            // TV 无独立首页，且不允许进入分屏
            _landscapeSplitMode.value = false
            _showHome.value = false
        } else {
            _landscapeSplitMode.value = userPrefs.getLandscapeSplitMode()
            // 未选台时回到触摸布局首页；正在播放则停留在播放页
            if (_currentIdx.value < 0) _showHome.value = true
        }
        Log.i("AppViewModel", "uiMode ${old.name} -> ${next.name} (pref=${pref.storageValue})")
    }

    // 初始化状态

    internal val _initState = MutableStateFlow<InitState>(InitState.Idle)
    val initState: StateFlow<InitState> = _initState.asStateFlow()

    internal val _iptvStatus = MutableStateFlow<IptvStatus?>(null)
    val iptvStatus: StateFlow<IptvStatus?> = _iptvStatus.asStateFlow()

    // 所有属性初始化完成后再启动初始化（Kotlin 按声明顺序初始化，init 块必须在所有 StateFlow 声明之后）
    init {
        startInitialization()
    }

    internal var statusPollJob: Job? = null

    /** 订阅源重载单飞 Job：并发请求直接合并，避免重载风暴 */
    internal var sourceReloadJob: Job? = null

    /** 最近一次「自动」订阅源重载时间戳（毫秒）：残留检测自触发重载必须有冷却 */
    internal var lastAutoSourceReloadAt = 0L

    /** 本次进程内自动重载已执行次数：上限 1 次，防止「残留→重载→仍残留」死循环 */
    internal var autoSourceReloadCount = 0

    /** EPG 重载单飞 Job：同一时刻只允许一个 reloadEpg 在跑，期间请求合并 */
    internal var epgReloadJob: Job? = null

    // 频道列表
    internal val _channels = MutableStateFlow<List<IptvChannel>>(emptyList())
    val channels: StateFlow<List<IptvChannel>> = _channels.asStateFlow()

    internal val _groups = MutableStateFlow<List<String>>(emptyList())
    val groups: StateFlow<List<String>> = _groups.asStateFlow()

    internal val _currentIdx = MutableStateFlow(-1)
    val currentIdx: StateFlow<Int> = _currentIdx.asStateFlow()

    val currentChannel: StateFlow<IptvChannel?> = combine(_currentIdx, _channels) { idx, channels ->
        channels.getOrNull(idx)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    internal val _channelDisplayInfo = MutableStateFlow(ChannelDisplayInfo())
    val channelDisplayInfo: StateFlow<ChannelDisplayInfo> = _channelDisplayInfo.asStateFlow()

    // 多画面状态（TV 端多画面功能）
    //
    // 主画面（index=0）用 MPV（单例）。
    // 副画面（index=1+）用 ExoPlayer（SubPlayer），支持多实例同时播放。
    internal val _multiViewState = MutableStateFlow(MultiViewState())
    val multiViewState: StateFlow<MultiViewState> = _multiViewState.asStateFlow()

    /** 副画面播放器实例池（key=视口索引，value=SubPlayer） */
    internal val subPlayers = mutableMapOf<Int, SubPlayer>()

    /** 副画面播放器状态流（UI 观察用，key=视口索引） */
    internal val _subPlayerStates = MutableStateFlow<Map<Int, SubPlayerState>>(emptyMap())
    val subPlayerStates: StateFlow<Map<Int, SubPlayerState>> = _subPlayerStates.asStateFlow()

    // 频道列表面板状态

/** 竖屏底部 Tab（首页/列表/工具/设置） */

/** 列表页视图模式 */

/** 列表页数据源 */

internal val _portraitTab = MutableStateFlow(PortraitTab.CHANNELS)
val portraitTab: StateFlow<PortraitTab> = _portraitTab.asStateFlow()

/** 列表页视图模式：列表 / 缩略图 */
internal val _listViewMode = MutableStateFlow(ListViewMode.THUMBNAIL)
val listViewMode: StateFlow<ListViewMode> = _listViewMode.asStateFlow()

/** 列表页数据源：订阅 / 本地 */
internal val _listSourceTab = MutableStateFlow(ListSourceTab.SUBSCRIPTION)
val listSourceTab: StateFlow<ListSourceTab> = _listSourceTab.asStateFlow()

/** 上次校正页签时的（订阅数, 本地数）；null=本次进程尚未校正过（冷启动） */
internal var listSourceTabCounts: Pair<Int, Int>? = null

/** 竖屏首页/播放器模式切换：true=首页（浏览），false=播放器界面
 * 初始始终为 true：竖屏先显示首页，横屏/TV 分支不检查 showHome 不受影响 */
internal val _showHome = MutableStateFlow(true)
val showHome: StateFlow<Boolean> = _showHome.asStateFlow()

/** 切换到播放器界面（选择频道/打开文件后调用） */

/** 切换回首页（播放器界面的返回按钮调用，视频继续播放） */

// MPV 旋转修复代理方法（供 MainPlayerScreen 的 LaunchedEffect 调用）

/** 获取当前播放路径（供旋转后检查播放状态使用） */

/** 切换列表视图模式 */

/** 预览图开关：false=显示台标，true=显示实时画面截图 */
internal val _thumbnailEnabled = MutableStateFlow(false)
val thumbnailEnabled: StateFlow<Boolean> = _thumbnailEnabled.asStateFlow()

/** 频道媒体信息缓存：url -> (width, height, fps, bitrate, audioChannels) */
internal val _mediaInfoMap = MutableStateFlow<Map<String, String>>(emptyMap())
val mediaInfoMap: StateFlow<Map<String, String>> = _mediaInfoMap.asStateFlow()

/** 实时测量的网络延迟：url -> latency(ms)，在获取预览图/媒体信息时同时测量 */
internal val _liveLatencyMap = MutableStateFlow<Map<String, Int>>(emptyMap())
val liveLatencyMap: StateFlow<Map<String, Int>> = _liveLatencyMap.asStateFlow()

/** 刷新所有预览图：清除旧的并强制重新获取 */

/** 清除所有预览图，回退到台标 */

/** 切换列表数据源 */

    /** 获取指定频道的缓存 EPG 当前节目（用于频道列表显示） */

/** 打开 EPG 面板（不重载视频） */

    /** 频道信息详情面板 */
    internal val _channelInfoOpen = MutableStateFlow(false)
    val channelInfoOpen: StateFlow<Boolean> = _channelInfoOpen.asStateFlow()

    /** 判断指定频道是否已收藏 */

    internal val _channelsTab = MutableStateFlow(ChannelTab.SUB)
    val channelsTab: StateFlow<ChannelTab> = _channelsTab.asStateFlow()

    internal val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    internal val _selectedGroup = MutableStateFlow("")
    val selectedGroup: StateFlow<String> = _selectedGroup.asStateFlow()

    // 收藏 / 历史 / 队列
    internal val _favorites = MutableStateFlow<Set<Int>>(emptySet())
    val favorites: StateFlow<Set<Int>> = _favorites.asStateFlow()

    internal val _history = MutableStateFlow<List<Int>>(emptyList())
    val history: StateFlow<List<Int>> = _history.asStateFlow()

    internal val _queue = MutableStateFlow<List<Int>>(emptyList())
    val queue: StateFlow<List<Int>> = _queue.asStateFlow()

    // 超时换源 / 断线重连 / 倍速控制（与侧边栏对齐）

    /** 超时换源定时器：播放超时后自动切到下一个源 */
    internal var timeoutSwitchJob: Job? = null
internal var switchPlayJob: Job? = null

    internal var consecutiveTimeoutCount = 0

    /** 超时换源档位（0-5），0=5s ... 5=30s */
    internal val _timeoutSwitchSource = MutableStateFlow(userPrefs.getTimeoutSwitchSource())
    val timeoutSwitchSource: StateFlow<Int> = _timeoutSwitchSource.asStateFlow()

    /** 断线重连定时器 */
    internal var reconnectJob: Job? = null

    internal var fileErrorSwitchJob: Job? = null

    /** 断线重连档位（0-5），0=关闭 ... 5=20s */
    internal val _reconnectIndex = MutableStateFlow(userPrefs.getReconnectIndex())
    val reconnectIndex: StateFlow<Int> = _reconnectIndex.asStateFlow()

    /** 倍速双步进配置 */
    internal val _speedConfig = MutableStateFlow(userPrefs.getSpeedConfig())
    val speedConfig: StateFlow<SpeedConfig> = _speedConfig.asStateFlow()

    // 时移 URL 重建冷却（与 PC 端 catchup_controller.URL_REBUILD_COOLDOWN 对齐）
    /** URL 重建冷却时间（秒），防止频繁重建导致服务器拒绝 */
    internal val urlRebuildCooldown = 3.0

    /** 上次 URL 重建的时间戳（System.nanoTime 转秒） */
    internal var lastUrlRebuildTime: Double = 0.0

    /** 是否有待执行的冷却后 seek */
    internal var urlRebuildPending: Boolean = false

    /** 冷却后待执行的 seek 百分比（0-100） */
    internal var pendingSeekAfterCooldown: Double? = null

    /** 冷却定时器 Job */
    internal var cooldownJob: Job? = null

    /** 时移续播 Job */
    internal var continueTimeshiftJob: Job? = null

    // Shuffle 模式（与 PC 端 FileQueueController.toggle_shuffle 对齐）
    /** shuffle 开关：开启后 nextChannel 随机选择（避免短期重复） */
    internal val _shuffleMode = MutableStateFlow(false)
    val shuffleMode: StateFlow<Boolean> = _shuffleMode.asStateFlow()

    /** shuffle 历史栈：记录已播放索引，避免短期重复（与 PC 端 _shuffle_history 对齐） */
    internal val shuffleHistory = mutableListOf<Int>()
    internal val shuffleHistoryMax = 50
    /** shuffle 撤销栈：prevChannel 时弹出，用于回到上一个随机播放的频道 */
    internal val shuffleBackStack = mutableListOf<Int>()

    // EPG
    /** key=channel idx, value=EPG 节目列表 */
    internal val epgCache = mutableMapOf<Int, List<IptvEpgProgram>>()

    /** EPG 缓存版本号，每次更新缓存时递增，用于触发 UI 刷新 */
    internal val _epgCacheVersion = MutableStateFlow(0)
    val epgCacheVersion: StateFlow<Int> = _epgCacheVersion.asStateFlow()

    internal val _currentEpg = MutableStateFlow<List<IptvEpgProgram>>(emptyList())
    val currentEpg: StateFlow<List<IptvEpgProgram>> = _currentEpg.asStateFlow()

    /** key=channel idx, value=该频道 EPG 的匹配来源（信息弹窗展示"匹配到哪个源/哪个频道"） */
    internal val epgMetaCache = mutableMapOf<Int, com.iptv.scanner.editor.pro.data.EpgMatchMeta>()

    internal val _currentEpgMeta = MutableStateFlow<com.iptv.scanner.editor.pro.data.EpgMatchMeta?>(null)
    val currentEpgMeta: StateFlow<com.iptv.scanner.editor.pro.data.EpgMatchMeta?> =
        _currentEpgMeta.asStateFlow()

    internal val _epgLoading = MutableStateFlow(false)
    val epgLoading: StateFlow<Boolean> = _epgLoading.asStateFlow()

    /** TV 统一面板中焦点频道的 EPG（独立于当前播放频道的 EPG） */
    internal val _focusedEpg = MutableStateFlow<List<IptvEpgProgram>>(emptyList())
    val focusedEpg: StateFlow<List<IptvEpgProgram>> = _focusedEpg.asStateFlow()

    internal val _focusedEpgLoading = MutableStateFlow(false)
    val focusedEpgLoading: StateFlow<Boolean> = _focusedEpgLoading.asStateFlow()

    // 播放状态（catchup/timeshift 状态机）
    internal val _playbackState = MutableStateFlow(PlaybackState())
    val playbackState: StateFlow<PlaybackState> = _playbackState.asStateFlow()

    /** 退出 catchup 按钮是否显示（catchup/timeshift 模式时显示） */
    val showExitCatchup: StateFlow<Boolean> = _playbackState.map { it.mode.isCatchupOrTimeshift }
        .stateIn(viewModelScope, SharingStarted.Eagerly, false)

    // OSD（顶部反馈信息）

/** 歌词行（与 PC 端 LyricsWidget 对齐） */

    internal val _osd = MutableStateFlow<OsdInfo?>(null)
    val osd: StateFlow<OsdInfo?> = _osd.asStateFlow()

    /** OSD 持久模式（菜单触发时启用，不自动隐藏，再次选中 OSD 时关闭） */
    internal val _osdPinned = MutableStateFlow(false)
    val osdPinned: StateFlow<Boolean> = _osdPinned.asStateFlow()

    internal var osdHideJob: Job? = null

    /** 切台时右上角频道号显示（3秒自动隐藏） */
    internal val _channelNumDisplay = MutableStateFlow("")
    val channelNumDisplay: StateFlow<String> = _channelNumDisplay.asStateFlow()
    internal var channelNumHideJob: Job? = null

    // 面板开关（手机模式：抽屉式；TV 模式：全屏覆盖式）
    internal val _channelsPanelOpen = MutableStateFlow(false)
    val channelsPanelOpen: StateFlow<Boolean> = _channelsPanelOpen.asStateFlow()

    internal val _epgPanelOpen = MutableStateFlow(false)
    val epgPanelOpen: StateFlow<Boolean> = _epgPanelOpen.asStateFlow()

    internal val _menuPanelOpen = MutableStateFlow(false)
    val menuPanelOpen: StateFlow<Boolean> = _menuPanelOpen.asStateFlow()

    /** 主菜单内的「全屏底栏样式」选择弹窗：BACK 键需优先只关它而不关整个菜单 */
    internal val _stylePickerOpen = MutableStateFlow(false)
    val stylePickerOpen: StateFlow<Boolean> = _stylePickerOpen.asStateFlow()
    fun setStylePickerOpen(value: Boolean) { _stylePickerOpen.value = value }

    /** 底栏样式实时预览：非 null 时底栏按该样式渲染并跟随弹窗焦点切换，null=用已确定样式 */
    internal val _stylePreview = MutableStateFlow<Int?>(null)
    val stylePreview: StateFlow<Int?> = _stylePreview.asStateFlow()
    fun setStylePreview(value: Int?) { _stylePreview.value = value }

    /** 文件浏览器面板（SAF 不可用时的替代方案，浏览本地 M3U/媒体文件） */
    internal val _fileBrowserOpen = MutableStateFlow(false)
    val fileBrowserOpen: StateFlow<Boolean> = _fileBrowserOpen.asStateFlow()

    /** 文件浏览器模式：PLAYLIST（选择 M3U 导入）/ MEDIA（选择音视频文件播放） */
    internal val _fileBrowserMode = MutableStateFlow(FileBrowserMode.PLAYLIST)
    val fileBrowserMode: StateFlow<FileBrowserMode> = _fileBrowserMode.asStateFlow()

    /** TV 端统一面板（三列：模式切换 + 频道列表/主菜单 + EPG 节目单） */
    internal val _tvUnifiedPanelOpen = MutableStateFlow(false)
    val tvUnifiedPanelOpen: StateFlow<Boolean> = _tvUnifiedPanelOpen.asStateFlow()

    internal val _controlsVisible = MutableStateFlow(true)
    val controlsVisible: StateFlow<Boolean> = _controlsVisible.asStateFlow()

    /** 横屏沉浸侧边栏可见性 */
    internal val _landscapeSidebarVisible = MutableStateFlow(false)
    val landscapeSidebarVisible: StateFlow<Boolean> = _landscapeSidebarVisible.asStateFlow()

    /** 控制层持久模式（菜单 OSD 按钮触发，不自动隐藏，再次选中关闭） */
    internal val _controlsPinned = MutableStateFlow(false)
    val controlsPinned: StateFlow<Boolean> = _controlsPinned.asStateFlow()

    /** TV 端控制面板自动隐藏定时器（几秒后自动隐藏） */
    internal var tvControlsAutoHideJob: kotlinx.coroutines.Job? = null

    // 订阅源管理
    internal val _sources = MutableStateFlow<List<IptvSource>>(emptyList())
    val sources: StateFlow<List<IptvSource>> = _sources.asStateFlow()

    internal val _sourceLoading = MutableStateFlow(false)
    val sourceLoading: StateFlow<Boolean> = _sourceLoading.asStateFlow()

    internal val _sourceMessage = MutableStateFlow("")
    val sourceMessage: StateFlow<String> = _sourceMessage.asStateFlow()

    internal val _sourceManagerOpen = MutableStateFlow(false)
    val sourceManagerOpen: StateFlow<Boolean> = _sourceManagerOpen.asStateFlow()

    /** 订阅源管理面板初始焦点是否直接落到 URL 输入框（仅零频道播放页直达时为 true） */
    internal val _sourceManagerFocusUrl = MutableStateFlow(false)
    val sourceManagerFocusUrl: StateFlow<Boolean> = _sourceManagerFocusUrl.asStateFlow()

    // EPG 订阅源
    internal val _epgSources = MutableStateFlow<List<IptvEpgSource>>(emptyList())
    val epgSources: StateFlow<List<IptvEpgSource>> = _epgSources.asStateFlow()

    // 订阅源管理 Tab
    internal val _sourceTab = MutableStateFlow(SourceTab.PLAYLIST)
    val sourceTab: StateFlow<SourceTab> = _sourceTab.asStateFlow()

    /** 频道缩略图路径缓存：url -> file_path */
    internal val _thumbnailPaths = MutableStateFlow<Map<String, String>>(emptyMap())
    val thumbnailPaths: StateFlow<Map<String, String>> = _thumbnailPaths.asStateFlow()

    /** 缩略图生成进度：null=未在生成, Pair(current, total)=正在生成 */
    internal val _thumbnailGenProgress = MutableStateFlow<Pair<Int, Int>?>(null)
    val thumbnailGenProgress: StateFlow<Pair<Int, Int>?> = _thumbnailGenProgress.asStateFlow()

    /** 当前选中的订阅源 URL（空=全部） */
    /** 播放工具 push 面板（截图/切片/EPG时间轴/搜索等播放相关工具） */
    internal val _playerToolsOpen = MutableStateFlow(false)
    val playerToolsOpen: StateFlow<Boolean> = _playerToolsOpen.asStateFlow()

    internal val _selectedSource = MutableStateFlow("")
    val selectedSource: StateFlow<String> = _selectedSource.asStateFlow()

    // 播放器设置面板（主菜单 → 设置 → 播放器设置）
    // 兜底方案：当黑屏检测不可靠时（如 estimated-vfps 仍有值但渲染黑屏），
    // 用户可手动切换 vo（gpu / mediacodec_embed），立即生效并持久化
    internal val _playerSettingsOpen = MutableStateFlow(false)
    val playerSettingsOpen: StateFlow<Boolean> = _playerSettingsOpen.asStateFlow()

    // 当前播放器 vo/hwdec（从 UserPrefs 读取，供 UI 显示当前选择）
    internal val _currentVo = MutableStateFlow(userPrefs.getVo())
    val currentVo: StateFlow<String> = _currentVo.asStateFlow()

    /** arm32 电视/盒子：设置页隐藏 copy-back（auto-copy/auto）选项 */
    val isArm32TvDevice: Boolean = userPrefs.isArm32TvDevice()

    /** 手机/平板（arm64 手持）：GPU 路径默认走 mediacodec 直通 */
    val isHandheldDevice: Boolean = userPrefs.isHandheldDevice()

    /** 自适应渲染路径原因：subtitle / filter / fallback，null=默认或手动选择 */
    val renderPathReason: StateFlow<String?> get() = mpvSingleton.renderPathReason

    internal val _currentHwdec = MutableStateFlow(userPrefs.getHwdec())
    val currentHwdec: StateFlow<String> = _currentHwdec.asStateFlow()

    // mpv 实际生效的硬解（hwdec-current）：可能因黑名单/会话降级/arm32 而不同于用户选择
    val actualHwdec: StateFlow<String> get() = mpvSingleton.actualHwdec
    // 当前设备是否处于硬解崩溃黑名单
    val hwdecBlacklisted: StateFlow<Boolean> get() = mpvSingleton.hwdecBlacklisted
    // mpv 实际生效的 vo（arm64 TV 默认 mediacodec_embed，起播失败会自动回退 gpu）
    val actualVo: StateFlow<String> get() = mpvSingleton.actualVo
    // 是否发生过 mediacodec_embed → gpu 的自动回退
    val voAutoFallback: StateFlow<Boolean> get() = mpvSingleton.voAutoFallback

    // RTSP 传输协议（tcp/udp），供 UI 显示和切换
    internal val _currentRtspTransport = MutableStateFlow(userPrefs.getRtspTransport())
    val currentRtspTransport: StateFlow<String> = _currentRtspTransport.asStateFlow()

    // ExoPlayer 视频渲染视图（true=SurfaceView, false=TextureView）
    internal val _exoSurfaceView = MutableStateFlow(userPrefs.getExoSurfaceView())
    val exoSurfaceView: StateFlow<Boolean> = _exoSurfaceView.asStateFlow()

// 反交错（no/auto），供 UI 显示和切换
internal val _currentDeinterlace = MutableStateFlow(userPrefs.getDeinterlace())
val currentDeinterlace: StateFlow<String> = _currentDeinterlace.asStateFlow()

// 日志等级（debug/info/warn/error），与 PC 端 core/log_manager.py 对齐
internal val _logLevel = MutableStateFlow(userPrefs.getLogLevel())
val logLevel: StateFlow<String> = _logLevel.asStateFlow()

    /** 当前是否使用硬件解码（所有播放器内核通用，UI 通过 collectAsState 自动响应） */
    internal val _hardwareDecode = MutableStateFlow(userPrefs.getHwdec() != "no")

    init {
// 默认渲染路径（TV 的 mediacodec_embed / 手机的 gpu-next 直通）起播失败自动回退时，同步界面状态并提示用户
mpvSingleton.onVoAutoFallback = { vo ->
    _currentVo.value = vo
    showOsd("画面输出已切换", "当前渲染方式：$vo（原默认渲染路径不可用）")
}
// 注册文件加载错误回调：当 mpv 报告文件加载失败时换源，
// 添加短暂延迟避免坏流导致 mpv 核心状态未清理就加载下一个流。
mpvSingleton.onFileError = {
// 停止态守卫：stopPlay 在 mpv.stop() 前已清空 currentPlaybackUrl，停止后
// mpv.stop() 触发的 END_FILE(error) 到达时无流可处理，直接跳过。
// 不能用 mode==IDLE 判断：播放本地视频时 mode 可能仍为 IDLE。
// 注意 stale 检查在此场景会失效——停止后 mpv getPath() 返回空串，
// 而 stale 分支要求 mpvPath.isNotEmpty() 才跳过，导致穿透到自动换台逻辑。
if (currentPlaybackUrl.isEmpty()) {
    Log.i(TAG, "onFileError: skipped, playback stopped (currentPlaybackUrl empty)")
} else if (mpv.isCoreDead()) {
    // 内核已终止：换源/重连都不可能成功，明确提示用户切换内核，避免静默失效
    Log.e(TAG, "onFileError: player core is dead, aborting auto-switch")
    consecutiveTimeoutCount = 0
    showOsd("播放器内核异常", "mpv 核心已退出，请切换播放器内核")
} else if (mpv.fileLoaded.value) {
    Log.i(TAG, "onFileError: skipped, file already loaded (stale callback)")
} else if (playChannelDebounceJob?.isActive == true) {
    Log.i(TAG, "onFileError: skipped, channel switch in progress (debounce job active)")
} else {
    val mpvPath = try { mpvSingleton.getPath() } catch (_: Throwable) { "" }
    if (mpvPath.isNotEmpty() && mpvPath != currentPlaybackUrl) {
        Log.i(TAG, "onFileError: skipped, mpv path='$mpvPath' != currentUrl='$currentPlaybackUrl' (stale END_FILE from previous channel)")
    } else if (_playbackState.value.mode.isCatchup || _playbackState.value.mode.isTimeshift) {
Log.w(TAG, "onFileError: in catchup/timeshift mode, skipping auto-switch")
showOsd("回看失败", "该节目可能无法回看或已过期")
_playbackState.value = PlaybackState(mode = PlayMode.LIVE)
val curIdx = _currentIdx.value
if (curIdx >= 0) {
val ch = _channels.value.getOrNull(curIdx)
if (ch != null) mpv.playFile(ch.url)
}
} else {
Log.w(TAG, "onFileError: file failed to load, triggering switch after delay")
mpvSingleton.markNeedPreStop()
timeoutSwitchJob?.cancel()
fileErrorSwitchJob?.cancel()
consecutiveTimeoutCount++
val maxConsecutive = minOf(10, maxOf(3, _channels.value.size / 3))
if (consecutiveTimeoutCount > maxConsecutive) {
    Log.w(TAG, "onFileError: stopped after $consecutiveTimeoutCount consecutive errors")
    consecutiveTimeoutCount = 0
    showOsd("自动换源已停止", "连续加载失败，请检查网络或切换播放器内核")
} else if (consecutiveTimeoutCount <= 3 && currentPlaybackUrl.isNotEmpty()) {
    showOsd("重新连接", "频道断流，尝试重连 ($consecutiveTimeoutCount/3)")
    val retryUrl = currentPlaybackUrl
    val retryIdx = _currentIdx.value
    fileErrorSwitchJob = viewModelScope.launch {
        delay(800)
        if (mpv.fileLoaded.value) {
            Log.i(TAG, "onFileError: skipped reconnect, file already loaded")
            return@launch
        }
        Log.i(TAG, "onFileError: reconnecting to same channel: $retryUrl")
        if (retryIdx >= 0) {
            // 同址重连时 onChannelChange 会因端点相同早退，必须强制重发 JOIN，
            // 让代理重新把组播数据推给新连接
            fccService.resendJoin(retryUrl)
            playChannel(retryIdx, silent = true)
        } else {
            fccService.resendJoin(retryUrl)
            mpv.playFile(retryUrl)
        }
    }
} else {
showOsd("加载失败", "当前频道无法播放，自动切换")
fileErrorSwitchJob = viewModelScope.launch {
delay(1000)
if (mpv.fileLoaded.value) {
Log.i(TAG, "onFileError: skipped auto-switch, file already loaded (user manually switched)")
return@launch
}
if (_playerType.value == PlayerType.MPV) {
Log.w(TAG, "onFileError: forcing mpv state reset before switch")
mpvSingleton.forceRecreate()
mpvSingleton.markNeedPreStop()
delay(500)
}
nextChannel()
}
}
}
}
}
    }

    init {
    // 时移 EOF 自动续播：监听 mpv eofReached，在时移模式下自动重建 URL 续播
    // （与 PC 端 catchup_controller.continue_timeshift 对齐）
    viewModelScope.launch {
        mpvSingleton.eofReached.collect { eof ->
            if (eof && _playbackState.value.mode.isTimeshift) {
                Log.i(TAG, "eofReached in timeshift mode, triggering continueTimeshift")
                continueTimeshiftJob?.cancel()
                continueTimeshiftJob = viewModelScope.launch {
                    delay(500) // 短暂延迟避免与 end-file 事件竞态
                    if (_playbackState.value.mode.isTimeshift) {
                        continueTimeshift()
                    }
                }
            }
        }
    }
    }

    val hardwareDecode: StateFlow<Boolean> = _hardwareDecode.asStateFlow()

    // 局域网管理服务器
    internal val _adminServerUrl = MutableStateFlow("")
    val adminServerUrl: StateFlow<String> = _adminServerUrl.asStateFlow()

    internal val _adminServerToken = MutableStateFlow("")
    val adminServerToken: StateFlow<String> = _adminServerToken.asStateFlow()

    internal val _adminServerRunning = MutableStateFlow(false)
    val adminServerRunning: StateFlow<Boolean> = _adminServerRunning.asStateFlow()

    /** 自动停止倒计时（秒），0 表示无倒计时。启动后 5 分钟自动停止，避免长时间占用端口和电量 */
    internal val _adminCountdown = MutableStateFlow(0)

/** 遥控器数字键输入缓冲（如输入 "1","2","3" → 切换到频道 123） */
internal var _channelInputBuffer: String? = null
internal var _channelInputJob: kotlinx.coroutines.Job? = null
    val adminCountdown: StateFlow<Int> = _adminCountdown.asStateFlow()
    internal var adminCountdownJob: Job? = null

    /** 虚拟遥控器命令轮询协程 */
    internal var remotePollJob: Job? = null
    internal var playerStatusJob: Job? = null

    // 更多功能面板（主菜单 → 播放 → 视频/音频/字幕/播放/截图/视图/关于）
    // 与 PC 端 controllers 对齐，直接调 MpvController，不走 Python
    internal val _videoSettingsOpen = MutableStateFlow(false)
    val videoSettingsOpen: StateFlow<Boolean> = _videoSettingsOpen.asStateFlow()

    internal val _audioSettingsOpen = MutableStateFlow(false)
    val audioSettingsOpen: StateFlow<Boolean> = _audioSettingsOpen.asStateFlow()

    internal val _subtitleSettingsOpen = MutableStateFlow(false)
    val subtitleSettingsOpen: StateFlow<Boolean> = _subtitleSettingsOpen.asStateFlow()

    // 字幕在线搜索面板
    internal val _subtitleSearchOpen = MutableStateFlow(false)
    val subtitleSearchOpen: StateFlow<Boolean> = _subtitleSearchOpen.asStateFlow()
    internal val _subtitleSearching = MutableStateFlow(false)
    val subtitleSearching: StateFlow<Boolean> = _subtitleSearching.asStateFlow()
    internal val _subtitleSearchResults = MutableStateFlow<List<SubtitleItem>>(emptyList())
    val subtitleSearchResults: StateFlow<List<SubtitleItem>> = _subtitleSearchResults.asStateFlow()
    internal val _subtitleSearchError = MutableStateFlow("")
    val subtitleSearchError: StateFlow<String> = _subtitleSearchError.asStateFlow()
    internal val _subtitleDownloading = MutableStateFlow(false)
    val subtitleDownloading: StateFlow<Boolean> = _subtitleDownloading.asStateFlow()

    internal val _playbackPanelOpen = MutableStateFlow(false)
    val playbackPanelOpen: StateFlow<Boolean> = _playbackPanelOpen.asStateFlow()

    internal val _screenshotPanelOpen = MutableStateFlow(false)
    val screenshotPanelOpen: StateFlow<Boolean> = _screenshotPanelOpen.asStateFlow()

    internal val _viewSettingsOpen = MutableStateFlow(false)
    val viewSettingsOpen: StateFlow<Boolean> = _viewSettingsOpen.asStateFlow()

    internal val _aboutPanelOpen = MutableStateFlow(false)
    val aboutPanelOpen: StateFlow<Boolean> = _aboutPanelOpen.asStateFlow()

    // 版本检查（与 PC 端 UpdateController 对齐）
    /** 版本检查状态 */

    internal val _updateState = MutableStateFlow<UpdateState>(UpdateState.Idle)
    val updateState: StateFlow<UpdateState> = _updateState.asStateFlow()

    /** 更新提示对话框是否显示 */
    internal val _updateDialogOpen = MutableStateFlow(false)
    val updateDialogOpen: StateFlow<Boolean> = _updateDialogOpen.asStateFlow()

    // 应用内 APK 下载更新（替代浏览器跳转，TV 端友好）
    /** 下载状态：空闲 / 下载中 / 下载完成 / 下载失败 */

    internal val _apkDownloadState = MutableStateFlow<ApkDownloadState>(ApkDownloadState.Idle)
    val apkDownloadState: StateFlow<ApkDownloadState> = _apkDownloadState.asStateFlow()

    /** 当前下载任务的 DownloadManager ID（用于取消/查询） */
    @Volatile
    internal var apkDownloadId: Long = -1L

    /** 下载完成 BroadcastReceiver 实例（用于注销） */
    @Volatile
    internal var apkDownloadReceiver: BroadcastReceiver? = null

    /** 下载进度轮询协程 Job */
    @Volatile
    internal var apkProgressJob: Job? = null

    /** 退出确认对话框是否显示（BACK 键退出时提示：立即退出 / 进入 PiP） */
    internal val _exitConfirmOpen = MutableStateFlow(false)
    val exitConfirmOpen: StateFlow<Boolean> = _exitConfirmOpen.asStateFlow()

    /** 打开网络流 URL 输入对话框 */
    internal val _openUrlDialogOpen = MutableStateFlow(false)
    val openUrlDialogOpen: StateFlow<Boolean> = _openUrlDialogOpen.asStateFlow()

    // 频道映射面板
    internal val _mappingPanelOpen = MutableStateFlow(false)
    val mappingPanelOpen: StateFlow<Boolean> = _mappingPanelOpen.asStateFlow()

    /** 映射列表（远程 + 用户） */
    internal val _mappingList = MutableStateFlow<List<MappingEntry>>(emptyList())
    val mappingList: StateFlow<List<MappingEntry>> = _mappingList.asStateFlow()

    /** 映射加载中 */
    internal val _mappingLoading = MutableStateFlow(false)
    val mappingLoading: StateFlow<Boolean> = _mappingLoading.asStateFlow()

    /** 映射刷新状态文本 */
    internal val _mappingStatusText = MutableStateFlow("")
    val mappingStatusText: StateFlow<String> = _mappingStatusText.asStateFlow()

    // A/V 同步监控面板
    internal val _avSyncPanelOpen = MutableStateFlow(false)
    val avSyncPanelOpen: StateFlow<Boolean> = _avSyncPanelOpen.asStateFlow()

    /** A/V 差值（秒，正值=音频领先，负值=视频领先） */
    internal val _avDiff = MutableStateFlow(0.0)
    val avDiff: StateFlow<Double> = _avDiff.asStateFlow()

    /** 音频 PTS（秒） */
    internal val _audioPts = MutableStateFlow(0.0)
    val audioPts: StateFlow<Double> = _audioPts.asStateFlow()

    /** 视频 PTS（秒） */
    internal val _videoPts = MutableStateFlow(0.0)
    val videoPts: StateFlow<Double> = _videoPts.asStateFlow()

    /** 当前音频延迟（秒） */
    internal val _currentAudioDelay = MutableStateFlow(0.0)
    val currentAudioDelay: StateFlow<Double> = _currentAudioDelay.asStateFlow()

    /** avdiff 历史采样（用于波形图，最多 200 点） */
    internal val _avDiffHistory = MutableStateFlow<List<Float>>(emptyList())
    val avDiffHistory: StateFlow<List<Float>> = _avDiffHistory.asStateFlow()

    /** 字幕自动同步开关 */
    internal val _subSyncEnabled = MutableStateFlow(false)
    val subSyncEnabled: StateFlow<Boolean> = _subSyncEnabled.asStateFlow()

    /** 字幕自动同步采样协程 */
    internal var avSyncJob: Job? = null
    internal var subSyncJob: Job? = null

    // 网络增强面板
    internal val _networkPanelOpen = MutableStateFlow(false)
    val networkPanelOpen: StateFlow<Boolean> = _networkPanelOpen.asStateFlow()

    // 工具面板
    internal val _toolsPanelOpen = MutableStateFlow(false)
    val toolsPanelOpen: StateFlow<Boolean> = _toolsPanelOpen.asStateFlow()

    // URL 范围扫描面板（与 PC 端 controllers/scan_controller.py 对齐，后端为 StandaloneScanner）
    internal val _scanPanelOpen = MutableStateFlow(false)
    val scanPanelOpen: StateFlow<Boolean> = _scanPanelOpen.asStateFlow()
    internal val _scanStatus = MutableStateFlow<ScanStatus?>(null)
    val scanStatus: StateFlow<ScanStatus?> = _scanStatus.asStateFlow()
    internal val _scanResults = MutableStateFlow<List<ScanResult>>(emptyList())
    val scanResults: StateFlow<List<ScanResult>> = _scanResults.asStateFlow()
    internal val _scanLoading = MutableStateFlow(false)
    val scanLoading: StateFlow<Boolean> = _scanLoading.asStateFlow()
    internal val _scanError = MutableStateFlow("")
    val scanError: StateFlow<String> = _scanError.asStateFlow()
    internal var scanPollJob: Job? = null

    // 节目提醒（与 PC 端 services/epg_reminder_service.py 对齐）
    //
    // - 启动时从 UserPrefs 加载
    // - 10 秒间隔轮询检查，60 秒提前触发弹窗
    // - 触发后通过 _triggeredReminder 暴露给 UI 显示弹窗
    // - 用户点击"切换频道"切到目标频道；点击"稍后"关闭弹窗
    // - 节目结束超过 1 小时自动清理
    internal val _reminderPanelOpen = MutableStateFlow(false)
    val reminderPanelOpen: StateFlow<Boolean> = _reminderPanelOpen.asStateFlow()
    internal val _reminders = MutableStateFlow<List<ReminderItem>>(emptyList())
    val reminders: StateFlow<List<ReminderItem>> = _reminders.asStateFlow()
    internal val _triggeredReminder = MutableStateFlow<ReminderItem?>(null)
    val triggeredReminder: StateFlow<ReminderItem?> = _triggeredReminder.asStateFlow()
    internal var reminderCheckJob: Job? = null
    /** 已通知过的提醒 ID 集合，避免同一节目重复弹窗 */
    internal val notifiedReminderIds = mutableSetOf<String>()

    // 续播位置（与 PC 端 controllers/resume_playback_controller.py 对齐）
    //
    // - 启动时从 UserPrefs 加载
    // - 自动保存：每 10 秒检查（仅 VOD/本地视频，跳过直播流）
    // - 自动恢复：fileLoaded 时延迟 400ms seek
    // - skipNextResume：队列/书签切换时跳过下次自动恢复
    internal val _resumePanelOpen = MutableStateFlow(false)
    val resumePanelOpen: StateFlow<Boolean> = _resumePanelOpen.asStateFlow()
    internal val _resumeList = MutableStateFlow<List<ResumeItem>>(emptyList())
    val resumeList: StateFlow<List<ResumeItem>> = _resumeList.asStateFlow()
    internal var resumeSaveJob: Job? = null
/** 当前正在播放的 URL（用于自动保存） */
internal var currentPlaybackUrl: String = ""
internal var currentPlaybackName: String = ""
/** 当前播放是否为本地视频文件（UI 据此显示暂停按钮等） */
internal val _isLocalVideoPlaying = MutableStateFlow(false)
val isLocalVideoPlaying: StateFlow<Boolean> = _isLocalVideoPlaying.asStateFlow()
internal var currentIsLocalFile: Boolean
    get() = _isLocalVideoPlaying.value
    set(value) { _isLocalVideoPlaying.value = value }

    /** 跳过下次自动恢复（队列/书签切换时设置） */
    internal var skipNextResumeFlag: Boolean = false

    // 书签（与 PC 端 controllers/bookmark_controller.py 对齐）
    //
    // - 以 URL 分组，同 URL 0.5s 容差内覆盖
    // - 当前 URL 书签列表 + 全部书签列表（"当前文件/所有文件"视图切换）
    // - 跳转时若跨 URL，调用 skipNextResume 避免续播位置覆盖书签位置
    internal val _bookmarkPanelOpen = MutableStateFlow(false)
    val bookmarkPanelOpen: StateFlow<Boolean> = _bookmarkPanelOpen.asStateFlow()
    /** 视图模式：true=当前文件，false=所有文件 */
    internal val _bookmarkShowCurrent = MutableStateFlow(true)
    val bookmarkShowCurrent: StateFlow<Boolean> = _bookmarkShowCurrent.asStateFlow()
    /** 当前 URL 的书签列表 */
    internal val _currentBookmarks = MutableStateFlow<List<BookmarkItem>>(emptyList())
    val currentBookmarks: StateFlow<List<BookmarkItem>> = _currentBookmarks.asStateFlow()
    /** 所有书签列表（按 createdAt 降序） */
    internal val _allBookmarks = MutableStateFlow<List<BookmarkItem>>(emptyList())
    val allBookmarks: StateFlow<List<BookmarkItem>> = _allBookmarks.asStateFlow()

    // EPG 时间线视图（与 PC 端 EpgTimelineDialog + Web 端 renderEpgTimeline 对齐）
    //
    // 多频道 × 24h 横向网格，Canvas 自绘，支持：
    // - 频道范围筛选（全部/收藏/当前分组）
    // - 日期切换（±7 天）
    // - 当前时间竖线 + 自动滚动到当前时间
    // - 节目块点击：过去→回看，当前/未来→提醒

    /** 时间线频道范围（与 Web 端 select 一致） */

    /** 时间线单行数据（一个频道 + 当日节目列表） */

    internal val _epgTimelineOpen = MutableStateFlow(false)
    val epgTimelineOpen: StateFlow<Boolean> = _epgTimelineOpen.asStateFlow()

    internal val _epgTimelineLoading = MutableStateFlow(false)
    val epgTimelineLoading: StateFlow<Boolean> = _epgTimelineLoading.asStateFlow()

    internal val _epgTimelineRows = MutableStateFlow<List<EpgTimelineRow>>(emptyList())
    val epgTimelineRows: StateFlow<List<EpgTimelineRow>> = _epgTimelineRows.asStateFlow()

    /** EPG 时间线按行懒加载：进行中的行索引（防同窗口重复并发加载） */
    internal val epgTimelinePendingRows = mutableSetOf<Int>()

    /** EPG 时间线数据代次：范围/日期切换时递增，使仍在途的旧懒加载结果失效 */
    internal var epgTimelineGeneration = 0

    internal val _epgTimelineRange = MutableStateFlow(EpgTimelineRange.ALL)
    val epgTimelineRange: StateFlow<EpgTimelineRange> = _epgTimelineRange.asStateFlow()

    /** 日期偏移（0=今天，-1=昨天，1=明天，范围 ±7） */
    internal val _epgTimelineDateOffset = MutableStateFlow(0)
    val epgTimelineDateOffset: StateFlow<Int> = _epgTimelineDateOffset.asStateFlow()

    /** 时间线加载状态文本（用于 UI 显示） */
    internal val _epgTimelineStatus = MutableStateFlow("")
    val epgTimelineStatus: StateFlow<String> = _epgTimelineStatus.asStateFlow()

    // 全局搜索（与 PC 端 UnifiedSearchDialog + Web 端 search 面板对齐）
    //
    // 搜索范围：
    // - 频道：name / group / url（与 PC 端一致）
    // - 节目：title / desc（与 EpgPanel 局部搜索一致，比 PC 端多搜 desc）
    //
    // 节目搜索异步遍历 epgCache（已加载的频道），上限 200 条（与 PC 端一致）。

    /** 搜索范围 */

    /** 搜索结果（密封类：频道 / 节目） */

    internal val _searchPanelOpen = MutableStateFlow(false)
    val searchPanelOpen: StateFlow<Boolean> = _searchPanelOpen.asStateFlow()

    internal val _searchResults = MutableStateFlow<List<SearchResult>>(emptyList())
    val searchResults: StateFlow<List<SearchResult>> = _searchResults.asStateFlow()

    internal val _searchLoading = MutableStateFlow(false)
    val searchLoading: StateFlow<Boolean> = _searchLoading.asStateFlow()

    internal val _searchScope = MutableStateFlow(SearchScope.ALL)
    val searchScope: StateFlow<SearchScope> = _searchScope.asStateFlow()

    internal var searchJob: Job? = null

    // 流质量检测（与 PC 端 get_live_media_info + Web 端 stream_quality 面板对齐）
    //
    // 详细展示 mpv 实时流信息：视频/音频/网络/缓存/丢帧/硬件解码。
    // 数据来源：mpv.getPropertyString/Int/Double（只读，无需持久化）。

    internal val _streamQualityPanelOpen = MutableStateFlow(false)
    val streamQualityPanelOpen: StateFlow<Boolean> = _streamQualityPanelOpen.asStateFlow()

    // 新增功能面板（与 PC 端功能对齐）

    /** 主题模式：dark / light / system */
    internal val _themeMode = MutableStateFlow(userPrefs.getThemeMode())
    val themeMode: StateFlow<String> = _themeMode.asStateFlow()

    /** 液态玻璃效果开关（Android 12+ 生效，低版本降级为纯色） */
    internal val _liquidGlass = MutableStateFlow(userPrefs.getLiquidGlass())
    val liquidGlass: StateFlow<Boolean> = _liquidGlass.asStateFlow()

    fun setLiquidGlass(enabled: Boolean) {
        _liquidGlass.value = enabled
        userPrefs.setLiquidGlass(enabled)
    }

    // 侧边栏风格显示设置开关项
    internal val _osdShowTime = MutableStateFlow(userPrefs.isOsdShowTime())
    val osdShowTime: StateFlow<Boolean> = _osdShowTime.asStateFlow()
    internal val _perChannelSettingsEnabled = MutableStateFlow(userPrefs.isPerChannelPlayerSettings())
    internal val _osdShowNetSpeed = MutableStateFlow(userPrefs.isOsdShowNetSpeed())
    val osdShowNetSpeed: StateFlow<Boolean> = _osdShowNetSpeed.asStateFlow()
    internal val _osdHideChannelNum = MutableStateFlow(userPrefs.isOsdHideChannelNum())
    val osdHideChannelNum: StateFlow<Boolean> = _osdHideChannelNum.asStateFlow()
    internal val _osdDisableEpg = MutableStateFlow(userPrefs.isOsdDisableEpg())
    val osdDisableEpg: StateFlow<Boolean> = _osdDisableEpg.asStateFlow()
    internal val _osdDisableFavorite = MutableStateFlow(userPrefs.isOsdDisableFavorite())
    val osdDisableFavorite: StateFlow<Boolean> = _osdDisableFavorite.asStateFlow()
    internal val _osdShowListIcon = MutableStateFlow(userPrefs.isOsdShowListIcon())
    val osdShowListIcon: StateFlow<Boolean> = _osdShowListIcon.asStateFlow()
    internal val _osdShowBottomIcon = MutableStateFlow(userPrefs.isOsdShowBottomIcon())
    val osdShowBottomIcon: StateFlow<Boolean> = _osdShowBottomIcon.asStateFlow()

    /** 最近打开文件面板 */
    internal val _recentPanelOpen = MutableStateFlow(false)
    val recentPanelOpen: StateFlow<Boolean> = _recentPanelOpen.asStateFlow()
    internal val _recentFiles = MutableStateFlow<List<RecentEntry>>(emptyList())
    val recentFiles: StateFlow<List<RecentEntry>> = _recentFiles.asStateFlow()

    /** 切片导出面板 */
    internal val _clipExportPanelOpen = MutableStateFlow(false)
    val clipExportPanelOpen: StateFlow<Boolean> = _clipExportPanelOpen.asStateFlow()
    internal val _clipExportProgress = MutableStateFlow(0)
    val clipExportProgress: StateFlow<Int> = _clipExportProgress.asStateFlow()
    internal val _clipExportStatus = MutableStateFlow("")
    val clipExportStatus: StateFlow<String> = _clipExportStatus.asStateFlow()

    /** 音频可视化面板 */
    internal val _audioVisualizerOpen = MutableStateFlow(false)
    val audioVisualizerOpen: StateFlow<Boolean> = _audioVisualizerOpen.asStateFlow()
    /** 频谱数据（0-1 归一化，64 个频段） */
    internal val _audioSpectrum = MutableStateFlow(FloatArray(AppViewModel.AUDIO_SPECTRUM_BANDS) { 0f })
    val audioSpectrum: StateFlow<FloatArray> = _audioSpectrum.asStateFlow()
    /** 频谱不可用原因（空=正常）。真频谱失败时给用户明确提示，绝不提供模拟数据 */
    internal val _audioSpectrumError = MutableStateFlow("")
    val audioSpectrumError: StateFlow<String> = _audioSpectrumError.asStateFlow()
    fun setAudioSpectrumError(msg: String) {
        _audioSpectrumError.value = msg
    }

    // ---------------- 空闲停绘（C） ----------------
    // 判定：连续 [IDLE_TIMEOUT_MS] 无用户输入 + 最近 2s 无音频能量 + 无任何面板打开 + 屏保未激活。
    // 处于空闲时，频谱回调不再向 UI 推送新数据（停止重绘与重组），音频恢复或用户按键时立刻恢复。
    internal val _idle = MutableStateFlow(false)
    val idle: StateFlow<Boolean> = _idle.asStateFlow()

    /** 屏保激活标志（D 使用）。屏保需要自己的动画，激活期间不算空闲 */
    internal val _screenSaverActive = MutableStateFlow(false)

    // ---------------- 屏保（D） ----------------
    /** 屏保是否正在显示 */
    internal val _screenSaverVisible = MutableStateFlow(false)
    val screenSaverVisible: StateFlow<Boolean> = _screenSaverVisible.asStateFlow()

    /** 屏保开关（设置项，持久化到 UserPrefs） */
    internal val _screenSaverEnabled = MutableStateFlow(userPrefs.isScreenSaverEnabled())
    val screenSaverEnabled: StateFlow<Boolean> = _screenSaverEnabled.asStateFlow()

    /** 进入屏保前的等待时间（分钟） */
    internal val _screenSaverTimeoutMinutes = MutableStateFlow(userPrefs.getScreenSaverTimeoutMinutes())
    val screenSaverTimeoutMinutes: StateFlow<Int> = _screenSaverTimeoutMinutes.asStateFlow()

    /** 应用是否在前台（后台不进入屏保） */
    @Volatile
    internal var appForeground: Boolean = true

    fun setScreenSaverEnabled(enabled: Boolean) {
        _screenSaverEnabled.value = enabled
        userPrefs.setScreenSaverEnabled(enabled)
        if (!enabled) dismissScreenSaver("disabled")
        Log.i(TAG, "[SS] enabled=$enabled")
    }

    fun setScreenSaverTimeoutMinutes(minutes: Int) {
        val v = minutes.coerceIn(1, 60)
        _screenSaverTimeoutMinutes.value = v
        userPrefs.setScreenSaverTimeoutMinutes(v)
        Log.i(TAG, "[SS] timeout=${v}min")
    }

    fun noteAppForeground(foreground: Boolean) {
        appForeground = foreground
        if (!foreground) dismissScreenSaver("background")
    }

    fun dismissScreenSaver(reason: String = "input") {
        if (!_screenSaverVisible.value) return
        _screenSaverVisible.value = false
        _screenSaverActive.value = false
        lastUserInputAt = android.os.SystemClock.elapsedRealtime()
        Log.i(TAG, "[SS] dismiss reason=$reason")
    }

    private fun evaluateScreenSaver() {
        if (!_screenSaverEnabled.value) return
        if (!appForeground) return
        if (_screenSaverVisible.value) return
        val playing = _playbackState.value.mode.isPlaying && !_player.value.paused.value
        val timeoutMs = _screenSaverTimeoutMinutes.value * 60_000L
        val now = android.os.SystemClock.elapsedRealtime()
        val idleFor = now - lastUserInputAt
        if (!playing && !anyPanelOpen && idleFor >= timeoutMs) {
            _screenSaverVisible.value = true
            _screenSaverActive.value = true
            Log.i(
                TAG,
                "[SS] show idleFor=${idleFor}ms timeout=${_screenSaverTimeoutMinutes.value}min" +
                    " playing=$playing panelsOpen=${anyPanelOpen}"
            )
        }
    }

    @Volatile
    internal var lastUserInputAt: Long = android.os.SystemClock.elapsedRealtime()

    @Volatile
    internal var lastAudioAt: Long = 0L

    /** 观测点：进入空闲次数 / 空闲期间丢弃的频谱帧数 */
    internal val idleEnterCount = java.util.concurrent.atomic.AtomicInteger()
    internal val spectrumFramesDropped = java.util.concurrent.atomic.AtomicInteger()

    /** 记录一次用户操作（按键/触摸），立即退出空闲与屏保 */
    fun noteUserInput() {
        lastUserInputAt = android.os.SystemClock.elapsedRealtime()
        if (_screenSaverVisible.value) dismissScreenSaver("user-input")
        if (_idle.value) {
            _idle.value = false
            Log.i(TAG, "[IDLE] exit reason=user-input enterCount=${idleEnterCount.get()} droppedFrames=${spectrumFramesDropped.get()}")
        }
    }

    private fun evaluateIdle() {
        val now = android.os.SystemClock.elapsedRealtime()
        val silentFor = now - lastAudioAt
        val inputIdleFor = now - lastUserInputAt
        val panelsOpen = anyPanelOpen
        val shouldIdle = silentFor > AUDIO_SILENCE_MS &&
            inputIdleFor >= IDLE_TIMEOUT_MS && !panelsOpen && !_screenSaverActive.value
        if (shouldIdle && !_idle.value) {
            _idle.value = true
            idleEnterCount.incrementAndGet()
            Log.i(
                TAG,
                "[IDLE] enter after ${inputIdleFor}ms no-input / ${silentFor}ms silent" +
                    " enterCount=${idleEnterCount.get()}"
            )
        } else if (!shouldIdle && _idle.value) {
            _idle.value = false
            Log.i(
                TAG,
                "[IDLE] exit reason=" + when {
                    _screenSaverActive.value -> "screensaver"
                    panelsOpen -> "panel-open"
                    silentFor <= AUDIO_SILENCE_MS -> "audio"
                    else -> "input"
                } + " droppedFrames=${spectrumFramesDropped.get()}"
            )
        }
    }

    init {
        // 每 1s 评估一次空闲状态（廉价定时器，空闲后视觉侧不再产生新帧）
        viewModelScope.launch {
            while (true) {
                delay(1_000L)
                evaluateIdle()
                evaluateScreenSaver()
            }
        }
    }

    /** 歌词面板 */
    internal val _lyricsOpen = MutableStateFlow(false)
    val lyricsOpen: StateFlow<Boolean> = _lyricsOpen.asStateFlow()
    /** 当前歌词行列表 */
    internal val _lyricsLines = MutableStateFlow<List<LyricsLine>>(emptyList())
    val lyricsLines: StateFlow<List<LyricsLine>> = _lyricsLines.asStateFlow()
    /** 当前高亮的歌词行索引 */
    internal val _currentLyricLine = MutableStateFlow(-1)
    val currentLyricLine: StateFlow<Int> = _currentLyricLine.asStateFlow()

    // DLNA 投屏状态流（需在 anyPanelOpenFlow 组合之前初始化）
    internal val _dlnaPanelOpen = MutableStateFlow(false)
    val dlnaPanelOpen: StateFlow<Boolean> = _dlnaPanelOpen.asStateFlow()
    internal val _dlnaScanning = MutableStateFlow(false)
    val dlnaScanning: StateFlow<Boolean> = _dlnaScanning.asStateFlow()
    internal val _dlnaDevices = MutableStateFlow<List<com.iptv.scanner.editor.pro.player.DlnaDevice>>(emptyList())
    val dlnaDevices: StateFlow<List<com.iptv.scanner.editor.pro.player.DlnaDevice>> = _dlnaDevices.asStateFlow()
    /** 当前投播中的设备（null=未投屏） */
    internal val _dlnaConnected = MutableStateFlow<com.iptv.scanner.editor.pro.player.DlnaDevice?>(null)
    val dlnaConnected: StateFlow<com.iptv.scanner.editor.pro.player.DlnaDevice?> = _dlnaConnected.asStateFlow()

    val anyPanelOpenFlow: StateFlow<Boolean> = combine(
        _channelsPanelOpen, _epgPanelOpen, _menuPanelOpen, _tvUnifiedPanelOpen,
        _fileBrowserOpen, _sourceManagerOpen, _playerSettingsOpen, _videoSettingsOpen,
        _audioSettingsOpen, _subtitleSettingsOpen, _subtitleSearchOpen, _playbackPanelOpen,
        _screenshotPanelOpen, _viewSettingsOpen, _aboutPanelOpen, _mappingPanelOpen,
        _avSyncPanelOpen, _networkPanelOpen, _toolsPanelOpen, _scanPanelOpen,
        _reminderPanelOpen, _resumePanelOpen, _bookmarkPanelOpen, _epgTimelineOpen,
        _searchPanelOpen, _streamQualityPanelOpen, _recentPanelOpen, _clipExportPanelOpen,
        _audioVisualizerOpen, _lyricsOpen, _exitConfirmOpen, _channelInfoOpen,
        _dlnaPanelOpen,
        _openUrlDialogOpen, _updateDialogOpen, _landscapeSidebarVisible, _playerToolsOpen
    ) { arr -> arr.any { it } }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    /** PiP 回调（Activity 注入，ViewModel 不能直接调用 Activity 方法）
     *  使用 WeakReference 防止 Configuration Change 后旧 Activity 泄漏 */
    internal var _onEnterPip: java.lang.ref.WeakReference<() -> Unit>? = null
    var onEnterPip: (() -> Unit)?
        get() = _onEnterPip?.get()
        set(value) {
            _onEnterPip = if (value != null) java.lang.ref.WeakReference(value) else null
        }

    /** 全屏切换回调（Activity 注入，切换横竖屏） */
    internal var _onToggleFullscreen: java.lang.ref.WeakReference<() -> Unit>? = null
    var onToggleFullscreen: (() -> Unit)?
        get() = _onToggleFullscreen?.get()
        set(value) {
            _onToggleFullscreen = if (value != null) java.lang.ref.WeakReference(value) else null
        }

    fun toggleFullscreen() {
        onToggleFullscreen?.invoke()
    }

    /**
     * 应用内强制横屏布局。
     *
     * 大屏设备（sw>=600dp，Android 12L+）系统会忽略 Activity 的
     * requestedOrientation 请求，导致「点击全屏按钮屏幕不旋转」。
     * 该状态让 UI 在物理方向不变时也渲染横屏播放布局（应用内伪全屏），
     * 与系统旋转成功时（configuration 变为横屏）的效果对齐。
     */
    internal val _forceLandscapeLayout = MutableStateFlow(false)
    val forceLandscapeLayout: StateFlow<Boolean> = _forceLandscapeLayout.asStateFlow()
    fun setForceLandscapeLayout(value: Boolean) {
        _forceLandscapeLayout.value = value
    }

    // ------------------------------------------------------------------
    // DLNA 投屏：搜索局域网电视/盒子，把当前频道流推给电视播放
    // ------------------------------------------------------------------
    fun toggleDlnaPanel() {
        _dlnaPanelOpen.value = !_dlnaPanelOpen.value
        if (_dlnaPanelOpen.value) scanDlna()
    }

    fun dismissDlnaPanel() {
        _dlnaPanelOpen.value = false
    }

    /**
     * SSDP 搜索局域网 DLNA 设备。
     * @param host 非空时向该 IP 发单播 M-SEARCH（组播被路由器/模拟器 NAT 拦截时的兜底）
     */
    fun scanDlna(host: String? = null) {
        if (_dlnaScanning.value) return
        _dlnaScanning.value = true
        _dlnaDevices.value = emptyList()
        viewModelScope.launch {
            val devices = try {
                if (host.isNullOrBlank()) {
                    com.iptv.scanner.editor.pro.player.DlnaCast.search(getApplication())
                } else {
                    com.iptv.scanner.editor.pro.player.DlnaCast.searchHost(getApplication(), host.trim())
                }
            } catch (e: Exception) {
                Log.e(TAG, "scanDlna failed", e)
                emptyList()
            }
            _dlnaDevices.value = devices
            _dlnaScanning.value = false
            if (devices.isEmpty()) {
                showOsd(
                    "投屏",
                    if (host.isNullOrBlank()) "未发现设备，请确认电视与本机在同一网络"
                    else "未发现设备，请确认电视 IP 是否正确且已开启投屏"
                )
            }
        }
    }

    /** 投播当前频道到指定设备 */
    fun castToDevice(device: com.iptv.scanner.editor.pro.player.DlnaDevice) {
        val url = getCurrentPlaybackUrl()
        if (url.isEmpty()) {
            showOsd("投屏", "请先选择要播放的频道")
            return
        }
        val chName = channels.value.getOrNull(_currentIdx.value)?.name ?: "IPTV"
        showOsd("投屏中", "正在连接 ${device.name}")
        viewModelScope.launch {
            val ok = try {
                com.iptv.scanner.editor.pro.player.DlnaCast.cast(device, url, chName)
            } catch (e: Exception) {
                Log.e(TAG, "castToDevice failed", e)
                false
            }
            if (ok) {
                _dlnaConnected.value = device
                _dlnaPanelOpen.value = false
                showOsd("投屏成功", "正在 ${device.name} 上播放")
            } else {
                showOsd("投屏失败", "设备无响应，请重试")
            }
        }
    }

    /** 停止电视端播放并断开投屏 */
    fun stopDlnaCast() {
        val device = _dlnaConnected.value ?: return
        viewModelScope.launch {
            try {
                com.iptv.scanner.editor.pro.player.DlnaCast.stop(device)
            } catch (_: Exception) {
            }
            _dlnaConnected.value = null
            showOsd("投屏已断开", device.name)
        }
    }

    /** 刷新 UI 状态 */
    internal val _refreshing = MutableStateFlow(false)
    val refreshing: StateFlow<Boolean> = _refreshing.asStateFlow()

    // HDR 输出模式（与 PC 端 hdr_output_mode 对齐）
    //
    // 模式：auto / tonemap / passthrough / disable
    // Android 端不改变 vo（保持用户选择），只在文件加载时应用 HDR 配置。

    /** HDR 输出模式 */

    internal val _hdrMode = MutableStateFlow(
        runCatching { HdrMode.valueOf(userPrefs.getHdrMode().uppercase()) }.getOrDefault(HdrMode.DISABLE)
    )
    val hdrMode: StateFlow<HdrMode> = _hdrMode.asStateFlow()

    /** 色彩兼容模式（默认关闭；开启后强制保守 SDR 参数，仅 gpu/gpu-next 生效） */
    internal val _colorCompatMode = MutableStateFlow(
        runCatching { userPrefs.isColorCompatMode() }.getOrDefault(false)
    )
    val colorCompatMode: StateFlow<Boolean> = _colorCompatMode.asStateFlow()

    // 初始化流程

    // 频道列表加载

    /** 加载所有频道和分组 */

    /** 删除指定索引的频道（本地列表管理） */

    /** 清空所有本地频道（source 为空的频道） */

    /** 加载用户偏好（收藏/历史/队列/提醒/续播位置/书签） */

    // 频道列表面板状态

    // 频道播放

    internal var playChannelDebounceJob: Job? = null

    internal var uiUpdateJob: kotlinx.coroutines.Job? = null

    // 超时换源 / 断线重连 / 倍速控制 setter

    /** 设置超时换源档位（0-5） */

    /** 设置断线重连档位（0-5） */

    /** 倍速恢复 1.0x */

    /** 设置倍速参数字符串（格式：min,max,slowStep,fastStep,fastStep2,threshold） */

    // EPG 时区偏移（与侧边栏 TIME_ZONE_SELECT 对齐）

    /** EPG 时区偏移档位（0-25） */
    internal val _epgTimezoneOffset = MutableStateFlow(userPrefs.getEpgTimezoneOffset())
    val epgTimezoneOffset: StateFlow<Int> = _epgTimezoneOffset.asStateFlow()

    /** 设置 EPG 时区偏移档位 */

    // EPG 缓存定时策略（与侧边栏 EPGCACHE_SELECT 对齐）

    /** EPG 缓存定时档位（0-11） */
    internal val _epgCacheSchedule = MutableStateFlow(userPrefs.getEpgCacheSchedule())
    val epgCacheSchedule: StateFlow<Int> = _epgCacheSchedule.asStateFlow()

    /** 设置 EPG 缓存定时档位 */

    // 画面锁定 / 换源不黑屏（与侧边栏 EYE_PROTECTION 对齐）

    /** 画面锁定开关（true=换源保持画面，false=换源黑屏） */
    internal val _screenLock = MutableStateFlow(userPrefs.getScreenLock())
    val screenLock: StateFlow<Boolean> = _screenLock.asStateFlow()

    /** 设置画面锁定 */

    // 分屏模式（手机端：视频+频道列表并排显示）

    /** 分屏模式开关（仅 PHONE 模式生效） */
    internal val _splitMode = MutableStateFlow(userPrefs.getSplitMode())
    val splitMode: StateFlow<Boolean> = _splitMode.asStateFlow()

    /** 切换分屏模式 */

    // 横屏分屏模式（TV/横屏播放页：左视频+控制条，右常驻面板；关闭=传统全屏）

    /**
     * 横屏分屏开关（默认开启；全屏按钮切换）。
     * TV 端不进分屏布局，恒为全屏页面（手机横屏行为不变）。
     */
    internal val _landscapeSplitMode =
        MutableStateFlow(_uiMode.value != UiMode.TV && userPrefs.getLandscapeSplitMode())
    val landscapeSplitMode: StateFlow<Boolean> = _landscapeSplitMode.asStateFlow()

    /**
     * 分屏播放页"焦点归零"重置信号：Compose 焦点系统无活跃焦点节点时（初焦被异步
     * 加载重组清掉、或电视端时序异常），方向键会一路落到 Activity.onKeyDown 兜底。
     * 此时递增此 tick，LandscapeSplitLayout 监听到后把焦点重新请求到视频区。
     */
    internal val _splitFocusResetTick = MutableStateFlow(0L)
    val splitFocusResetTick: StateFlow<Long> = _splitFocusResetTick.asStateFlow()

    /**
     * 分屏焦点树当前是否持有活跃焦点（TvSplitLayout 根 Row 的 onFocusChanged 同步维护，
     * 仅主线程读写）。Activity 的 DPAD 兜底用它区分两种情况：
     * - false：焦点树真无活跃焦点（初焦被重组清掉等），需要归零回视频区；
     * - true：焦点仍在树内、只是方向键几何搜索到边缘无候选——必须原地保持焦点，
     *   若也无差别归零，用户每次按到边缘焦点都会跳回视频区（"切着切着焦点消失"的根源）。
     */
    var splitTreeHasFocus: Boolean = false

    /** 设置横屏分屏模式（TV 端禁止进入分屏，直接保持全屏页面） */
    fun setLandscapeSplitMode(value: Boolean) {
        if (_uiMode.value == UiMode.TV && value) return
        _landscapeSplitMode.value = value
        userPrefs.setLandscapeSplitMode(value)
        // 进入分屏：全屏专属悬浮层（左右侧边栏/主菜单/全屏底栏/样式预览弹窗）全部收起。
        // 这些悬浮窗仅在全屏布局可呼出，若状态残留会导致分屏内 anyPanelOpen=true
        // 拦截 DPAD 切台/seek，表现为分屏页方向键失灵
        if (value) {
            _landscapeSidebarVisible.value = false
            _menuPanelOpen.value = false
            _stylePickerOpen.value = false
            _stylePreview.value = null
            _controlsVisible.value = false
            _controlsPinned.value = false
        }
    }

    // 全屏播放页 TV 底栏布局样式（0..11，名称与结构见 TvLayout.TV_BOTTOM_BAR_STYLES 单一数据源）
    internal val _bottomBarStyle = MutableStateFlow(userPrefs.getBottomBarStyle())
    val bottomBarStyle: StateFlow<Int> = _bottomBarStyle.asStateFlow()

    /** 设置底栏布局样式（设置页/样式弹窗切换，0..TV_BOTTOM_BAR_STYLES.size-1） */
    fun setBottomBarStyle(value: Int) {
        _bottomBarStyle.value = value.coerceIn(0, TV_BOTTOM_BAR_STYLES.size - 1)
        userPrefs.setBottomBarStyle(value)
    }

    // 二级分组模式（与侧边栏 GROUP_PARS_SET_SELECT 对齐）

    /** 分组模式（0-3） */
    internal val _groupMode = MutableStateFlow(userPrefs.getGroupMode())
    val groupMode: StateFlow<Int> = _groupMode.asStateFlow()

    /** 设置分组模式 */

    // 开机自启动（与侧边栏 BOOT_START 对齐）

    /** 开机自启动开关 */
    internal val _bootStart = MutableStateFlow(userPrefs.getBootStart())
    val bootStart: StateFlow<Boolean> = _bootStart.asStateFlow()

    /** 设置开机自启动 */

    /** 启动自动续播开关 */
    internal val _autoResume = MutableStateFlow(userPrefs.isAutoResumeOnStart())
    val autoResume: StateFlow<Boolean> = _autoResume.asStateFlow()

    /** 设置启动自动续播 */

    // 数字选台（与侧边栏 CHANNEL_NUMBER 对齐）

    /** 当前数字选台输入缓存 */
    internal val _channelNumberInput = MutableStateFlow("")
    val channelNumberInput: StateFlow<String> = _channelNumberInput.asStateFlow()

    /** 数字选台超时定时器 */
    internal var channelNumberJob: Job? = null

    /** 从 URL 中提取主机名（用于 DNS 预解析） */

    // 频道级播放器设置（per-channel override）
    //
    // 开启"频道记忆"后，每个频道可独立记忆播放器内核 / vo / hwdec / HDR 模式。
    // 切换频道时自动应用该频道的设置，实现不同频道用不同最佳配置。

    /** 自动保存当前播放器设置到指定频道（频道记忆开启时，切换频道前自动调用） */

    /** 清除指定频道的专属播放器设置 */

    /** 查询指定频道是否有专属设置 */

    // 多画面控制
    //
    // 主画面（index=0）用当前播放器（MPV）
    // 副画面（index=1+）用 ExoPlayer（SubPlayer），支持多实例同时播放

    /** 上一频道 */

    /** 停止播放 */

    // Catchup / Timeshift

    // EPG

    internal var thumbnailJob: Job? = null

    /** 获取当前正在播放的 EPG 节目（用于控制面板第二行显示） */

    /** EPG 面板展开时获取完整（未裁剪）的 EPG 数据 */

    /** 计算当前进度条信息（用于 UI 进度条渲染） */

    // 收藏 / 历史 / 队列

    /** 切换当前频道收藏状态，返回是否已收藏 */

    /** 添加频道到队列 */

    /** 从队列移除 */

    /** 清空历史 */

    /** 清空队列 */

    // OSD

    /** 显示 OSD（5 秒后自动隐藏，持久模式下不自动隐藏） */

    /** 隐藏 OSD（同时清除持久模式） */

    // 面板控制

    /** TV 端统一面板切换（打开时关闭其他面板，关闭时恢复控制层） */

    val anyPanelOpen: Boolean
        get() = _playerToolsOpen.value || _landscapeSidebarVisible.value ||
                _channelsPanelOpen.value || _epgPanelOpen.value ||
                _menuPanelOpen.value || _tvUnifiedPanelOpen.value || _fileBrowserOpen.value ||
                _sourceManagerOpen.value ||
                _playerSettingsOpen.value ||
                _videoSettingsOpen.value || _audioSettingsOpen.value ||
                _subtitleSettingsOpen.value || _subtitleSearchOpen.value || _playbackPanelOpen.value ||
                _screenshotPanelOpen.value || _viewSettingsOpen.value ||
                _aboutPanelOpen.value || _updateDialogOpen.value || _exitConfirmOpen.value || _openUrlDialogOpen.value ||
                _mappingPanelOpen.value || _avSyncPanelOpen.value ||
                _networkPanelOpen.value || _toolsPanelOpen.value || _scanPanelOpen.value ||
                _reminderPanelOpen.value || _resumePanelOpen.value || _bookmarkPanelOpen.value ||
                _epgTimelineOpen.value || _searchPanelOpen.value ||
                _streamQualityPanelOpen.value ||
                _recentPanelOpen.value || _clipExportPanelOpen.value ||
                _audioVisualizerOpen.value || _lyricsOpen.value ||
                _stylePickerOpen.value

    /** 打开文件浏览器面板（SAF 不可用时的替代方案） */
    /** 打开应用内文件浏览器选择音视频文件播放（SAF 不可用时的兜底） */

    // 更多功能面板切换（主菜单 → 播放 → 各子面板）

    /** 打开/关闭字幕在线搜索面板 */

    // 版本检查（与 PC 端 UpdateController 对齐）

    /** 获取当前应用版本号（从 PackageManager 读取，与 build.gradle versionName 一致） */

    /** 获取编译日期（从 APK 的 lastUpdateTime 提取） */

    /** 关闭更新提示对话框 */

    /** 注销 APK 下载 BroadcastReceiver（如已注册） */

    /** 显示退出确认对话框 */

    /** 关闭退出确认对话框 */

    /** 比较版本号（与 PC 端 _is_newer_version 对齐），判断 latest 是否比 current 新 */

    // URL 范围扫描（与 PC 端扫描功能对齐，后端 StandaloneScanner）

    /** 打开/关闭 URL 范围扫描面板 */

    /** 停止扫描 */

    /** 单次刷新状态（打开面板时用，若仍在运行则启动轮询） */

    /** 加载扫描结果缓存（用于频道列表显示延迟标识） */

    /** 测量单个频道的 HTTP 延迟(ms)，超时3秒 */

    /** 批量获取频道媒体信息 */

    /** 启动扫描状态轮询（800ms 间隔，扫描中实时加载结果，扫描结束后自动停止轮询） */

    /** 停止扫描状态轮询（不停止扫描本身） */

    /** 清空所有扫描结果（仅前端列表） */

    // 频道网络验证（#5）

    /** 启动频道网络验证 */

    // 批量编辑（#4）

    /** 批量编辑频道，成功后刷新频道列表 */

    // 单条频道编辑（#6）

    /** 更新单条频道字段，成功后刷新频道列表 */

    // 节目提醒管理（与 PC 端 controllers/epg_reminder_controller.py 对齐）
    //
    // 入口：
    // - toggleReminder(program, channel)：EPG 点击当前/未来节目时调用
    // - toggleReminderPanel()：工具菜单 → 提醒管理
    // - acceptTriggeredReminder() / dismissTriggeredReminder()：弹窗按钮
    //
    // 定时检查：
    // - startReminderCheck()：启动后每 10 秒检查一次
    // - checkReminders()：60 秒提前触发；节目结束超 1 小时清理

    /** 检查某节目提醒是否已存在（UI 显示状态用） */

    /** 打开/关闭提醒管理面板 */

    /** 删除指定提醒 */

    /** 清空全部提醒 */

    /** 用户点击"切换频道"：切到提醒对应频道并关闭弹窗 */

    /** 用户点击"稍后"：仅关闭弹窗，不切台 */

    /** 启动定时检查（10 秒间隔，对齐 PC 端 QTimer） */

    /** 停止定时检查 */

    // 续播位置管理（与 PC 端 controllers/resume_playback_controller.py 对齐）
    //
    // 入口：
    // - toggleResumePanel()：工具菜单 → 续播位置
    // - playResume(item)：从断点列表恢复指定项
    // - removeResume(url) / clearResumeList()：列表管理
    //
    // 自动保存：startResumeAutoSave() 每 10 秒检查
    // 自动恢复：onFileLoaded 时调用 tryRestoreResume
    // 跳过下次恢复：skipNextResume()（队列/书签切换时设置）

    /** 打开/关闭续播位置面板 */

    /** 删除指定 URL 的断点 */

    /** 清空全部断点 */

    /** 获取当前播放 URL（供 UI 层 LaunchedEffect 触发恢复用） */

    /** 格式化秒为 mm:ss 或 hh:mm:ss */

    // 书签管理（与 PC 端 controllers/bookmark_controller.py 对齐）
    //
    // 入口：
    // - toggleBookmarkPanel()：工具菜单 → 书签
    // - addBookmark(name)：在当前位置添加书签
    // - gotoBookmark(item)：跳转到书签位置（跨 URL 时切台 + skipNextResume）
    // - deleteBookmark(item) / clearCurrentBookmarks() / clearAllBookmarks()
    // - setBookmarkShowCurrent(show)：切换"当前文件/所有文件"视图

    /** 打开/关闭书签面板 */

    /** 切换视图：true=当前文件，false=所有文件 */

    /** 删除指定书签 */

    /** 清除当前 URL 的所有书签 */

    /** 清除所有书签 */

    /** 刷新当前 URL 的书签（playChannel/playLocalVideo 后调用） */

    // EPG 时间线视图（与 PC 端 EpgTimelineDialog + Web 端 renderEpgTimeline 对齐）
    //
    // 多频道 × 24h 横向网格，复用 epgCache 避免重复加载，最多 30 频道。

    /** 打开/关闭 EPG 时间线视图 */

    /** 切换频道范围并重新加载 */

    /** 切换日期（offset 范围 ±7 天） */

    /** 时间解析辅助（与 EpgPanel.kt parseTimeToMs 对齐，避免私有函数跨文件可见性问题） */

    // 全局搜索（与 PC 端 UnifiedSearchDialog + Web 端 search 面板对齐）
    //
    // 频道搜索本地过滤，节目搜索异步遍历 epgCache，上限 200 条。

    /** 打开/关闭全局搜索面板 */

    /** 切换搜索范围 */

    // 流质量检测（与 PC 端 get_live_media_info + Web 端 stream_quality 面板对齐）
    //
    // 详细展示 mpv 实时流信息，数据只读无需持久化。

    /** 打开/关闭流质量检测面板 */

    // 画中画 (PiP) — 与 PC 端 PipController 对齐

    /** 手动进入 PiP 模式（由 Activity 的 enterPipManual() 实现） */

    // 主题模式切换 — 与 PC 端 ThemeManager color_mode 对齐

    /** 设置主题模式：dark / light / system */

    // 最近打开 — 与 PC 端 recent_menu 对齐

    /** 从最近打开列表中恢复播放 */

    // 另存为 — 导出频道列表为 M3U（与 PC 端 save_as 对齐）

    /** 导出当前频道列表为 M3U 文件，写入下载目录 */

    // 刷新 UI — 重新加载频道/EPG（与 PC 端 F5 refresh 对齐）

    // 画面比例切换 — 循环：默认 → 16:9 → 4:3 → 拉伸 → 默认

    internal val aspectRatioModes = listOf("默认" to null, "16:9" to "16:9", "4:3" to "4:3", "拉伸" to "stretch")
    internal val _aspectRatioIdx = MutableStateFlow(0)
    val aspectRatioIdx: StateFlow<Int> = _aspectRatioIdx.asStateFlow()

    /** 循环切换画面比例 */

    // 切片导出 — 利用 ffmpeg（与 PC 端 ClipExportDialog 对齐）

    // 音频可视化 — 频谱波形（与 PC 端 audio_visual 对齐）

    internal var spectrumJob: kotlinx.coroutines.Job? = null
    internal var visualizer: android.media.audiofx.Visualizer? = null
    // 频谱采样引用计数：分屏左列常驻频谱与右侧信息 Tab/音频可视化面板可同时存活，
    // 只有最后一个使用方退出时才真正停掉 Visualizer
    internal var spectrumRefs = 0

    // 歌词 — 加载/显示/同步（与 PC 端 LyricsWidget 对齐）

    internal var lyricsSyncJob: kotlinx.coroutines.Job? = null

    /** 从文件 URI 加载 LRC 歌词 */

    /** 解析 LRC 格式歌词 [mm:ss.xx]文本 */

    /** 清除当前歌词 */

    // 从 URI 打开播放列表（文件关联入口）

    /** 从外部 URI 导入播放列表 */

    // HDR 模式切换（与 PC 端 _apply_hdr_on_file_loaded / _set_hdr_mode 对齐）
    //
    // Android 端 4 种模式：DISABLE / AUTO / TONEMAP / PASSTHROUGH
    // - 不改变 vo（保持用户持久化选择），只在文件加载时应用 HDR 配置
    // - PASSTHROUGH 使用 target-colorspace-hint 让 Android 系统自动切换 HDR 显示模式
    // - AUTO 模式：检测设备 HDR 能力，支持则直通，不支持则色调映射
    // - 支持 HDR10/HDR10+/HLG/WCG（bt.2020 色域）/杜比视界（8.1 版本兼容）

    // 文件操作（打开播放列表 / 打开网络流 / 打开本地视频）
    // 与 PC 端 文件 菜单组对齐

    // 连拍截图（与 PC 端 BurstScreenshotDialog 对齐）
    // 按可配置间隔定时截图，复用 takeScreenshot()

    internal val _burstActive = MutableStateFlow(false)
    val burstActive: StateFlow<Boolean> = _burstActive.asStateFlow()

    internal val _burstCount = MutableStateFlow(0)
    val burstCount: StateFlow<Int> = _burstCount.asStateFlow()

    internal val _burstTotal = MutableStateFlow(0)
    val burstTotal: StateFlow<Int> = _burstTotal.asStateFlow()

    internal var burstJob: kotlinx.coroutines.Job? = null

    /** 停止连拍截图 */

    // 订阅源管理（主菜单 → 文件 → 订阅源管理）

/** 设置当前选中的订阅源（空=全部） */

/** 加载频道缩略图路径 */

/** 播放时自动截取缩略图（延迟几秒让画面加载，切台时自动取消上一个截图任务） */

    // 播放器设置（vo / hwdec）
    //
    // 兜底方案：当黑屏检测不可靠时（如 estimated-vfps 仍有值但渲染黑屏），
    // 用户可手动切换 vo（gpu / mediacodec_embed），立即生效并持久化。

    /** 切换 VO（gpu/gpu-next/mediacodec_embed），切换后重新加载当前频道 */

    /** 查询当前播放器是否使用硬件解码 */

    // 备份与恢复（订阅源 + EPG 源 + 收藏/历史/队列 + 播放器设置）
    //
    // 解决卸载重装数据丢失问题：
    // - 导出：完整配置打包写入 Downloads/IPTV_backup_YYYYMMDD_HHmmss.json
    // - 导入：从备份文件恢复所有配置，触发 reload 加载频道

    /** 导出完整配置到下载目录 */

    /** 从指定 URI 恢复配置（由 SAF 文件选择器回调触发） */

    /** 构建完整备份 JSON：Python 配置 + UserPrefs */

    /** 恢复完整备份：Python 配置 + UserPrefs */

    /** 写入备份文件到下载目录（Android 10+ 用 MediaStore，旧版本用公共目录） */

    /** 从指定 URI 读取备份文件 */

    /** 轮询订阅源加载状态，完成后自动刷新频道列表 */

    // 局域网管理服务器（TV 端遥控器输入不便，手机浏览器扫码管理）

    /** 设置局域网管理是否自动关闭 */

    /** 获取局域网管理是否自动关闭 */

    /** 停止虚拟遥控器命令轮询 */

    /** 收集当前播放状态并上报到 Python 端 */

    /** 设置自定义访问令牌（仅在服务器未运行时生效） */

    // 频道映射 CRUD（通过 IptvRepository 调用 Python bridge）

    // A/V 同步监控（仅 MPV 播放器支持，其他播放器属性返回 null）

    internal var subSyncWindow = ArrayDeque<Float>()

    // 网络增强（HTTP Referer / Proxy / Headers，仅 MPV 播放器支持）

    /** 加载持久化的网络设置（面板打开时调用） */

    /** 保存网络设置到持久化存储 + 应用 */

    /** 清除所有网络设置 */

    // ViewModel 生命周期

    override fun onCleared() {
        super.onCleared()
        statusPollJob?.cancel()
        osdHideJob?.cancel()
        avSyncJob?.cancel()
        subSyncJob?.cancel()
        reminderCheckJob?.cancel()
        resumeSaveJob?.cancel()
        // 关闭 FCC：先同步向旧端点补发 LEAVE，再关闭持久化 UDP socket
        try { fccService.shutdown() } catch (_: Throwable) {}
        // 清理主播放器（MPV 需要 stop + detach，避免 native 资源泄漏）
        // Activity.onDestroy 已先调用一次，这里兜底确保释放
        try {
            val p = _player.value
            p.stop()
            p.detach()
        } catch (_: Throwable) {}
        // 清理副画面播放器（ExoPlayer 实例）
        try {
            releaseAllSubPlayers()
        } catch (_: Throwable) {}
        // 清理 APK 下载资源（避免 receiver 泄漏）
        try {
            apkProgressJob?.cancel()
            apkProgressJob = null
            if (apkDownloadId > 0) {
                val app = getApplication<Application>()
                val dm = app.getSystemService(Context.DOWNLOAD_SERVICE) as? DownloadManager
                dm?.remove(apkDownloadId)
                unregisterApkDownloadReceiver(app)
            }
        } catch (_: Throwable) {}
        // 退出前保存最后一次位置
        try { autoSaveResume() } catch (_: Exception) {}
        // 停止局域网管理服务器（避免退出后端口/socket 残留）
        // viewModelScope 已取消，用后台线程同步调用 Python 端 stop_admin_server
        try {
            adminCountdownJob?.cancel()
            stopRemoteCommandPolling()
            // 使用 GlobalScope 非阻塞启动，避免 runBlocking 反模式
            GlobalScope.launch(Dispatchers.IO) {
                try {
                    withTimeoutOrNull(3000L) {
                        repository.stopAdminServer()
                    }
                } catch (_: Throwable) {}
            }
        } catch (_: Throwable) {}
    }

    // 工具函数

    /** 类似 Kotlin 的 takeIf 但用于 if-else 表达式 */
    internal fun <T> T.ifElse(other: T, predicate: () -> Boolean): T =
        if (predicate()) this else other

    companion object {
        internal const val TAG = "AppViewModel"
        internal const val GITHUB_LATEST_API = "https://api.github.com/repos/sumingyd/guangyu/releases/latest"
        /** 频谱频段数（可视化面板/信息 Tab 等所有界面共用） */
        internal const val AUDIO_SPECTRUM_BANDS = 64

        /** 空闲停绘：连续无操作多久进入空闲（60s） */
        internal const val IDLE_TIMEOUT_MS = 60_000L

        /** 最近多久没有音频能量即视为静音（2s） */
        internal const val AUDIO_SILENCE_MS = 2_000L

        /** 频谱能量阈值：超过即视为有声音（0-1 归一化） */
        internal const val AUDIO_ACTIVE_THRESHOLD = 0.02f

        fun factory(app: Application): ViewModelProvider.AndroidViewModelFactory =
            object : ViewModelProvider.AndroidViewModelFactory(app) {}
    }
}
