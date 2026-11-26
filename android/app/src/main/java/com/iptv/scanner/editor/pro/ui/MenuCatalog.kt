package com.iptv.scanner.editor.pro.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.automirrored.filled.ListAlt
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.BlurOn
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CloudSync
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Devices
import androidx.compose.material.icons.filled.Equalizer
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.PictureInPicture
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Replay
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.ScreenshotMonitor
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SyncAlt
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.VideoSettings
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.ViewModule
import androidx.compose.material.icons.filled.Web
import androidx.compose.ui.graphics.vector.ImageVector
import com.iptv.scanner.editor.pro.data.IptvSource

/**
 * 菜单共享数据层：一份条目定义，两套渲染。
 *
 * - 条目、分组、顺序、动作、动态文案、置灰与可见性都定义在本文件；
 * - 右侧玻璃两列面板（MainMenuPanel）与 TV 侧边栏（TvUnifiedPanel.MenuColumn）
 *   只实现各自的布局与样式，通过 [MenuSurface] 标记决定条目出现在哪个渲染面；
 * - 动作统一经 [dispatchMenuAction] 派发，渲染面只提供 [MenuHost]（关面板、
 *   SAF 启动器等宿主差异），不再各自闭包捕获 viewModel。
 */

/** 条目所属渲染面 */
enum class MenuSurface {
    /** 两套渲染都出现 */
    BOTH,

    /** 只在右侧玻璃两列面板出现 */
    RIGHT_ONLY,

    /** 只在 TV 侧边栏出现 */
    SIDEBAR_ONLY;

    fun appearsOn(target: MenuSurface): Boolean = when (this) {
        BOTH -> true
        RIGHT_ONLY -> target == RIGHT_ONLY
        SIDEBAR_ONLY -> target == SIDEBAR_ONLY
    }
}

enum class MenuHostKind { RIGHT_PANEL, TV_SIDEBAR }

/**
 * 渲染面宿主：只承载两侧实现不同的部分。
 * 其余动作一律走 [dispatchMenuAction]。
 */
class MenuHost(
    val kind: MenuHostKind,
    /** 关闭当前宿主面板（右侧菜单 = 关菜单；侧边栏 = 关侧边栏与统一面板） */
    val closeHost: () -> Unit = {},
    /** 打开播放列表：SAF 不可用时各自走文件浏览器，可用时拉起系统选择器 */
    val launchPlaylist: () -> Unit = {},
    /** 打开本地音视频文件 */
    val launchVideo: () -> Unit = {},
    /** 主题单选弹窗（纯 UI 状态，只能由宿主弹） */
    val openThemePicker: () -> Unit = {},
    /** 界面模式单选弹窗 */
    val openUiModePicker: () -> Unit = {},
    /** 全屏底栏样式弹窗 */
    val openBottomBarStylePicker: () -> Unit = {}
)

/** 菜单动作：动作 id + 可选参数（订阅源 URL、多画面布局名） */
data class MenuAction(
    val id: MenuActionId,
    val arg: String? = null
)

enum class MenuActionId {
    SELECT_SOURCE,
    SOURCE_MANAGER,
    EPG_SOURCES,
    OPEN_URL,
    OPEN_PLAYLIST,
    OPEN_LOCAL_VIDEO,
    CHANNELS,
    EPG,
    CHANNEL_MAPPING,
    TOGGLE_FAVORITE,
    PLAYER_SETTINGS,
    SUBTITLE,
    VIDEO,
    AUDIO,
    PLAYBACK,
    MULTI_VIEW_ENTER,
    MULTI_VIEW_EXIT,
    THEME_PICKER,
    TOGGLE_LIQUID_GLASS,
    TOGGLE_GLASS_REFRACTION,
    UI_MODE_PICKER,
    BOTTOM_BAR_STYLE_PICKER,
    VIEW_SETTINGS,
    TOGGLE_SHOW_TIME,
    TOGGLE_NET_SPEED,
    TOGGLE_HIDE_CHANNEL_NUM,
    TOGGLE_SHOW_LIST_ICON,
    TOGGLE_SHOW_BOTTOM_ICON,
    TOGGLE_DISABLE_EPG,
    TOGGLE_DISABLE_FAVORITE,
    NETWORK,
    GITHUB_PROXY,
    TOOLS,
    SCREENSHOT,
    AVSYNC,
    CLIP_EXPORT,
    AUDIO_VISUALIZER,
    LYRICS,
    RECENT,
    SAVE_AS_M3U,
    REFRESH,
    ABOUT,
    CLEAR_CHANNEL_SETTINGS,
    TOGGLE_AUTO_RESUME,
    TOGGLE_BOOT_START,
    TOGGLE_SCREEN_SAVER,
    CYCLE_SCREEN_SAVER_TIMEOUT,
    PIP,
    EXIT
}

/** 渲染用的条目模型：文案与状态已在数据层算好 */
data class MenuEntryModel(
    val id: String,
    val title: String,
    val subtitle: String,
    val icon: ImageVector,
    val action: MenuAction? = null,
    val highlight: Boolean = false,
    val isToggle: Boolean = false,
    val toggleValue: Boolean = false,
    val enabled: Boolean = true,
    val disabledReason: String = "",
    /** 该条目在侧边栏渲染面不可执行时的禁用原因；为空表示两侧都可用 */
    val sidebarDisabledReason: String = "",
    val surface: MenuSurface = MenuSurface.BOTH,
    val visible: (MenuRuntimeState) -> Boolean = { true }
)

data class MenuSectionModel(
    val id: String,
    val title: String,
    val entries: List<MenuEntryModel>
)

/** 菜单运行时状态：所有动态文案 / 开关 / 置灰 / 可见性都从这里取值 */
data class MenuRuntimeState(
    val surfaceDirect: Boolean = false,
    val hasChannel: Boolean = false,
    val isFavorite: Boolean = false,
    val themeMode: String = "dark",
    val uiModeLabel: String = "",
    val bottomBarStyleLabel: String = "",
    val liquidGlass: Boolean = false,
    val glassRefraction: Boolean = false,
    val showTime: Boolean = false,
    val showNetSpeed: Boolean = false,
    val hideChannelNum: Boolean = false,
    val disableEpg: Boolean = false,
    val disableFavorite: Boolean = false,
    val showListIcon: Boolean = false,
    val showBottomIcon: Boolean = false,
    val sources: List<IptvSource> = emptyList(),
    val selectedSource: String = "",
    val multiViewLayout: MultiViewLayout? = null,
    val perChannelEnabled: Boolean = false,
    val hasChannelSettings: Boolean = false,
    val githubProxyEnabled: Boolean = false,
    val githubProxySelected: String = "",
    val autoResume: Boolean = false,
    val bootStart: Boolean = false,
    val screenSaverEnabled: Boolean = false,
    val screenSaverTimeout: Int = 5
)

object MenuCatalog {

    private const val SURFACE_REASON = "直写 Surface 播放中不可用，切回 GPU 后恢复"

    fun sections(state: MenuRuntimeState, surface: MenuSurface): List<MenuSectionModel> {
        val all = listOf(
            sourcesSection(state),
            channelsSection(state),
            playbackSection(state),
            multiViewSection(state),
            appearanceSection(state),
            displaySection(state),
            networkSection(state),
            toolsSection(state),
            filesSection(state),
            systemSection(state)
        )
        return all.mapNotNull { section ->
            val entries = section.entries
                .filter { it.visible(state) && it.surface.appearsOn(surface) }
                .map { entry ->
                    // 宿主能力缺失的条目在侧边栏保留可见，但置灰并给出原因
                    if (surface == MenuSurface.SIDEBAR_ONLY && entry.sidebarDisabledReason.isNotEmpty()) {
                        entry.copy(enabled = false, disabledReason = entry.sidebarDisabledReason)
                    } else entry
                }
            if (entries.isEmpty()) null else section.copy(entries = entries)
        }
    }

    private fun sourcesSection(state: MenuRuntimeState): MenuSectionModel {
        val entries = buildList {
            // 订阅源列表：动态项，当前源高亮。侧边栏用独立的源切换列，故仅右侧出现。
            state.sources.filter { it.enabled }.forEachIndexed { idx, src ->
                add(
                    MenuEntryModel(
                        id = "source:$idx",
                        title = src.name.ifEmpty { "源${idx + 1}" },
                        subtitle = src.url.take(40),
                        icon = Icons.Default.Web,
                        action = MenuAction(MenuActionId.SELECT_SOURCE, src.url),
                        highlight = src.url == state.selectedSource,
                        surface = MenuSurface.BOTH
                    )
                )
            }
            add(
                MenuEntryModel(
                    id = "sources:manage",
                    title = "订阅源管理",
                    subtitle = "添加、编辑、删除 M3U 订阅源",
                    icon = Icons.Default.Settings,
                    action = MenuAction(MenuActionId.SOURCE_MANAGER)
                )
            )
            add(
                MenuEntryModel(
                    id = "sources:epg",
                    title = "EPG 订阅源",
                    subtitle = "管理节目单订阅地址",
                    icon = Icons.Default.CalendarMonth,
                    action = MenuAction(MenuActionId.EPG_SOURCES)
                )
            )
            add(
                MenuEntryModel(
                    id = "sources:url",
                    title = "打开网络流",
                    subtitle = "输入 M3U / M3U8 URL",
                    icon = Icons.Default.Link,
                    action = MenuAction(MenuActionId.OPEN_URL)
                )
            )
            add(
                MenuEntryModel(
                    id = "sources:playlist",
                    title = "打开播放列表",
                    subtitle = "选择 M3U/M3U8 文件",
                    icon = Icons.Default.FileOpen,
                    action = MenuAction(MenuActionId.OPEN_PLAYLIST)
                )
            )
        }
        return MenuSectionModel("sources", "订阅源", entries)
    }

    private fun channelsSection(state: MenuRuntimeState): MenuSectionModel {
        val notSelectedReason = "未选择频道"
        return MenuSectionModel(
            id = "channels",
            title = "频道管理",
            entries = listOf(
                MenuEntryModel(
                    id = "channels:list",
                    title = "频道列表",
                    subtitle = "订阅 / 本地 / 收藏 / 历史",
                    icon = Icons.AutoMirrored.Filled.ListAlt,
                    action = MenuAction(MenuActionId.CHANNELS),
                    highlight = true
                ),
                MenuEntryModel(
                    id = "channels:epg",
                    title = "节目单 EPG",
                    subtitle = "当前频道节目 / 日期切换",
                    icon = Icons.Default.CalendarMonth,
                    action = MenuAction(MenuActionId.EPG)
                ),
                MenuEntryModel(
                    id = "channels:mapping",
                    title = "频道映射",
                    subtitle = "远程映射 + 用户映射管理",
                    icon = Icons.Default.SyncAlt,
                    action = MenuAction(MenuActionId.CHANNEL_MAPPING)
                ),
                MenuEntryModel(
                    id = "channels:favorite",
                    title = if (state.isFavorite) "取消收藏" else "收藏",
                    subtitle = if (state.hasChannel) "当前频道" else notSelectedReason,
                    icon = Icons.Default.Favorite,
                    action = MenuAction(MenuActionId.TOGGLE_FAVORITE),
                    highlight = state.hasChannel,
                    enabled = state.hasChannel,
                    disabledReason = if (state.hasChannel) "" else notSelectedReason
                ),
                MenuEntryModel(
                    id = "channels:clear-settings",
                    title = "清除频道专属设置",
                    subtitle = "恢复使用全局设置",
                    icon = Icons.Default.Delete,
                    action = MenuAction(MenuActionId.CLEAR_CHANNEL_SETTINGS),
                    highlight = true,
                    surface = MenuSurface.BOTH,
                    visible = { it.perChannelEnabled && it.hasChannel && it.hasChannelSettings }
                )
            )
        )
    }

    private fun playbackSection(state: MenuRuntimeState): MenuSectionModel {
        val gate = state.surfaceDirect
        return MenuSectionModel(
            id = "playback",
            title = "播放设置",
            entries = listOf(
                MenuEntryModel(
                    id = "playback:player",
                    title = "播放器设置",
                    subtitle = "内核 / VO / HWDEC / HDR",
                    icon = Icons.Default.Settings,
                    action = MenuAction(MenuActionId.PLAYER_SETTINGS)
                ),
                MenuEntryModel(
                    id = "playback:subtitle",
                    title = "字幕",
                    subtitle = if (gate) SURFACE_REASON else "轨 / 显示 / 延迟 / 缩放",
                    icon = Icons.Default.ClosedCaption,
                    action = MenuAction(MenuActionId.SUBTITLE),
                    enabled = !gate,
                    disabledReason = if (gate) SURFACE_REASON else ""
                ),
                MenuEntryModel(
                    id = "playback:video",
                    title = "视频",
                    subtitle = if (gate) SURFACE_REASON else "图像调整 / 旋转 / 翻转",
                    icon = Icons.Default.VideoSettings,
                    action = MenuAction(MenuActionId.VIDEO),
                    enabled = !gate,
                    disabledReason = if (gate) SURFACE_REASON else ""
                ),
                MenuEntryModel(
                    id = "playback:audio",
                    title = "音频",
                    subtitle = "音轨 / 延迟 / EQ / 音调",
                    icon = Icons.Default.Equalizer,
                    action = MenuAction(MenuActionId.AUDIO)
                ),
                MenuEntryModel(
                    id = "playback:play",
                    title = "播放",
                    subtitle = "速度 / 循环 / 随机 / AB",
                    icon = Icons.Default.PlayCircle,
                    action = MenuAction(MenuActionId.PLAYBACK)
                )
            )
        )
    }

    private fun multiViewSection(state: MenuRuntimeState): MenuSectionModel {
        val current = state.multiViewLayout
        val entries = if (current != null && current != MultiViewLayout.SINGLE) {
            val other = when (current) {
                MultiViewLayout.DUAL -> MultiViewLayout.QUAD
                MultiViewLayout.QUAD -> MultiViewLayout.NINE
                MultiViewLayout.NINE -> MultiViewLayout.DUAL
                else -> MultiViewLayout.DUAL
            }
            listOf(
                MenuEntryModel(
                    id = "multiview:switch",
                    title = "切换为${other.displayName}",
                    subtitle = "当前 ${current.displayName}",
                    icon = Icons.Default.ViewModule,
                    action = MenuAction(MenuActionId.MULTI_VIEW_ENTER, other.name)
                ),
                MenuEntryModel(
                    id = "multiview:exit",
                    title = "退出多画面",
                    subtitle = "退出多画面模式",
                    icon = Icons.AutoMirrored.Filled.ExitToApp,
                    action = MenuAction(MenuActionId.MULTI_VIEW_EXIT),
                    highlight = true
                )
            )
        } else {
            listOf(
                MenuEntryModel(
                    id = "multiview:dual",
                    title = "双画面",
                    subtitle = "左右分屏",
                    icon = Icons.Default.ViewModule,
                    action = MenuAction(MenuActionId.MULTI_VIEW_ENTER, MultiViewLayout.DUAL.name)
                ),
                MenuEntryModel(
                    id = "multiview:quad",
                    title = "四画面",
                    subtitle = "2x2 网格",
                    icon = Icons.Default.GridView,
                    action = MenuAction(MenuActionId.MULTI_VIEW_ENTER, MultiViewLayout.QUAD.name)
                ),
                MenuEntryModel(
                    id = "multiview:nine",
                    title = "九画面",
                    subtitle = "3x3 网格",
                    icon = Icons.Default.GridView,
                    action = MenuAction(MenuActionId.MULTI_VIEW_ENTER, MultiViewLayout.NINE.name)
                )
            )
        }
        return MenuSectionModel("multiview", "多画面", entries)
    }

    private fun appearanceSection(state: MenuRuntimeState): MenuSectionModel = MenuSectionModel(
        id = "appearance",
        title = "外观",
        entries = listOf(
            MenuEntryModel(
                id = "appearance:theme",
                title = "主题",
                subtitle = "当前：" + when (state.themeMode) {
                    "light" -> "浅色模式"
                    "system" -> "跟随系统"
                    else -> "深色模式"
                } + " · 点击选择",
                icon = Icons.Default.DarkMode,
                action = MenuAction(MenuActionId.THEME_PICKER),
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "appearance:liquid-glass",
                title = "液态玻璃",
                subtitle = "UI背景半透明玻璃质感",
                icon = Icons.Default.AutoAwesome,
                action = MenuAction(MenuActionId.TOGGLE_LIQUID_GLASS),
                isToggle = true,
                toggleValue = state.liquidGlass,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "appearance:refraction",
                title = "液态玻璃折射",
                subtitle = "边缘折射与玻璃厚度",
                icon = Icons.Default.BlurOn,
                action = MenuAction(MenuActionId.TOGGLE_GLASS_REFRACTION),
                isToggle = true,
                toggleValue = state.glassRefraction,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "appearance:ui-mode",
                title = "界面模式",
                subtitle = "当前：${state.uiModeLabel} · 点击选择",
                icon = Icons.Default.Devices,
                action = MenuAction(MenuActionId.UI_MODE_PICKER),
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "appearance:bottom-bar",
                title = "全屏底栏样式",
                subtitle = "当前：${state.bottomBarStyleLabel} · 点击选择",
                icon = Icons.Default.AspectRatio,
                action = MenuAction(MenuActionId.BOTTOM_BAR_STYLE_PICKER),
                // 底栏样式弹窗依赖右侧菜单的预览与按键路由，侧边栏无法承载
                sidebarDisabledReason = "侧边栏无法调整，请在右侧菜单中修改"
            )
        )
    )

    private fun displaySection(state: MenuRuntimeState): MenuSectionModel = MenuSectionModel(
        id = "display",
        title = "界面显示",
        entries = listOf(
            MenuEntryModel(
                id = "display:view",
                title = "视图",
                subtitle = "视频比例 / OSD",
                icon = Icons.Default.ViewInAr,
                action = MenuAction(MenuActionId.VIEW_SETTINGS)
            ),
            MenuEntryModel(
                id = "display:time",
                title = "显示时间",
                subtitle = "右上角时间组",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_SHOW_TIME),
                isToggle = true,
                toggleValue = state.showTime,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "display:net-speed",
                title = "显示网速",
                subtitle = "右下角网速",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_NET_SPEED),
                isToggle = true,
                toggleValue = state.showNetSpeed,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "display:hide-number",
                title = "隐藏序号",
                subtitle = "频道列表不显示序号",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_HIDE_CHANNEL_NUM),
                isToggle = true,
                toggleValue = state.hideChannelNum,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "display:list-icon",
                title = "列表图标",
                subtitle = "频道列表显示台标",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_SHOW_LIST_ICON),
                isToggle = true,
                toggleValue = state.showListIcon,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "display:bottom-icon",
                title = "底部图标",
                subtitle = "底部信息栏显示图标",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_SHOW_BOTTOM_ICON),
                isToggle = true,
                toggleValue = state.showBottomIcon,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "display:disable-epg",
                title = "关闭EPG",
                subtitle = "不加载节目单",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_DISABLE_EPG),
                isToggle = true,
                toggleValue = state.disableEpg,
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "display:disable-favorite",
                title = "关闭收藏",
                subtitle = "不显示收藏星标",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.TOGGLE_DISABLE_FAVORITE),
                isToggle = true,
                toggleValue = state.disableFavorite,
                surface = MenuSurface.BOTH
            )
        )
    )

    private fun networkSection(state: MenuRuntimeState): MenuSectionModel = MenuSectionModel(
        id = "network",
        title = "网络",
        entries = listOf(
            MenuEntryModel(
                id = "network:enhance",
                title = "网络增强",
                subtitle = "Referer / Proxy / Headers",
                icon = Icons.Default.Public,
                action = MenuAction(MenuActionId.NETWORK)
            ),
            MenuEntryModel(
                id = "network:github-proxy",
                title = "GitHub 加速代理",
                subtitle = if (state.githubProxyEnabled) "已开启 · ${state.githubProxySelected}" else "已关闭",
                icon = Icons.Default.CloudSync,
                action = MenuAction(MenuActionId.GITHUB_PROXY),
                surface = MenuSurface.BOTH
            )
        )
    )

    private fun toolsSection(state: MenuRuntimeState): MenuSectionModel {
        val gate = state.surfaceDirect
        return MenuSectionModel(
            id = "tools",
            title = "工具设置",
            entries = listOf(
                MenuEntryModel(
                    id = "tools:main",
                    title = "工具",
                    subtitle = "搜索 / 提醒 / 续播 / 书签",
                    icon = Icons.Default.Tune,
                    action = MenuAction(MenuActionId.TOOLS)
                ),
                MenuEntryModel(
                    id = "tools:screenshot",
                    title = "截图",
                    subtitle = if (gate) SURFACE_REASON else "单张 / 连拍 / 含字幕",
                    icon = Icons.Default.ScreenshotMonitor,
                    action = MenuAction(MenuActionId.SCREENSHOT),
                    enabled = !gate,
                    disabledReason = if (gate) SURFACE_REASON else ""
                ),
                MenuEntryModel(
                    id = "tools:avsync",
                    title = "A/V 同步",
                    subtitle = "实时数值 / 波形",
                    icon = Icons.Default.GraphicEq,
                    action = MenuAction(MenuActionId.AVSYNC)
                ),
                MenuEntryModel(
                    id = "tools:clip-export",
                    title = "切片导出",
                    subtitle = "裁剪视频片段 / GIF",
                    icon = Icons.Default.ContentCut,
                    action = MenuAction(MenuActionId.CLIP_EXPORT),
                    surface = MenuSurface.BOTH
                ),
                MenuEntryModel(
                    id = "tools:audio-visualizer",
                    title = "音频可视化",
                    subtitle = "实时频谱波形",
                    icon = Icons.Default.GraphicEq,
                    action = MenuAction(MenuActionId.AUDIO_VISUALIZER),
                    surface = MenuSurface.BOTH
                ),
                MenuEntryModel(
                    id = "tools:lyrics",
                    title = "歌词",
                    subtitle = "加载 LRC / 同步高亮",
                    icon = Icons.Default.MusicNote,
                    action = MenuAction(MenuActionId.LYRICS),
                    surface = MenuSurface.BOTH
                )
            )
        )
    }

    private fun filesSection(state: MenuRuntimeState): MenuSectionModel = MenuSectionModel(
        id = "files",
        title = "文件",
        entries = listOf(
            MenuEntryModel(
                id = "files:open-local",
                title = "打开本地文件",
                subtitle = "播放视频/音频文件",
                icon = Icons.Default.Movie,
                action = MenuAction(MenuActionId.OPEN_LOCAL_VIDEO)
            ),
            MenuEntryModel(
                id = "files:recent",
                title = "最近打开",
                subtitle = "最近打开的列表/视频",
                icon = Icons.Default.History,
                action = MenuAction(MenuActionId.RECENT),
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "files:save-as-m3u",
                title = "另存为 M3U",
                subtitle = "导出当前频道列表",
                icon = Icons.Default.FileDownload,
                action = MenuAction(MenuActionId.SAVE_AS_M3U),
                surface = MenuSurface.BOTH
            )
        )
    )

    private fun systemSection(state: MenuRuntimeState): MenuSectionModel = MenuSectionModel(
        id = "system",
        title = "系统",
        entries = listOf(
            // 启动与屏保：此前只在手机端设置页可见，电视端补齐
            MenuEntryModel(
                id = "system:auto-resume",
                title = "自动续播",
                subtitle = "启动时恢复上次播放的频道",
                icon = Icons.Default.Replay,
                action = MenuAction(MenuActionId.TOGGLE_AUTO_RESUME),
                isToggle = true,
                toggleValue = state.autoResume
            ),
            MenuEntryModel(
                id = "system:boot-start",
                title = "开机自启动",
                subtitle = "开机后自动进入应用",
                icon = Icons.Default.PowerSettingsNew,
                action = MenuAction(MenuActionId.TOGGLE_BOOT_START),
                isToggle = true,
                toggleValue = state.bootStart
            ),
            MenuEntryModel(
                id = "system:screen-saver",
                title = "屏保",
                subtitle = "无操作时显示待机画面",
                icon = Icons.Default.Bedtime,
                action = MenuAction(MenuActionId.TOGGLE_SCREEN_SAVER),
                isToggle = true,
                toggleValue = state.screenSaverEnabled
            ),
            MenuEntryModel(
                id = "system:screen-saver-timeout",
                title = "屏保等待",
                subtitle = if (state.screenSaverEnabled) "${state.screenSaverTimeout} 分钟 · 点击切换" else "先开启屏保",
                icon = Icons.Default.Schedule,
                action = MenuAction(MenuActionId.CYCLE_SCREEN_SAVER_TIMEOUT),
                enabled = state.screenSaverEnabled,
                disabledReason = if (state.screenSaverEnabled) "" else "先开启屏保"
            ),
            MenuEntryModel(
                id = "system:refresh",
                title = "刷新",
                subtitle = "重新加载频道和 EPG",
                icon = Icons.Default.Refresh,
                action = MenuAction(MenuActionId.REFRESH),
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "system:about",
                title = "关于",
                subtitle = "版本信息 / 功能特性",
                icon = Icons.Default.Info,
                action = MenuAction(MenuActionId.ABOUT)
            ),
            MenuEntryModel(
                id = "system:pip",
                title = "画中画",
                subtitle = "进入 PiP 小窗口播放",
                icon = Icons.Default.PictureInPicture,
                action = MenuAction(MenuActionId.PIP),
                surface = MenuSurface.BOTH
            ),
            MenuEntryModel(
                id = "system:exit",
                title = "退出",
                subtitle = "关闭应用",
                icon = Icons.AutoMirrored.Filled.ExitToApp,
                action = MenuAction(MenuActionId.EXIT)
            )
        )
    )
}

/**
 * 单一动作分发表：两套渲染都只调用这里，宿主差异通过 [MenuHost] 注入。
 */
fun AppViewModel.dispatchMenuAction(action: MenuAction, host: MenuHost) {
    when (action.id) {
        MenuActionId.SELECT_SOURCE -> {
            action.arg?.let { setSelectedSource(it) }
            host.closeHost()
            refreshUi()
        }
        MenuActionId.SOURCE_MANAGER -> {
            setSourceTab(SourceTab.PLAYLIST)
            host.closeHost()
            toggleSourceManager()
        }
        MenuActionId.EPG_SOURCES -> {
            setSourceTab(SourceTab.EPG)
            host.closeHost()
            toggleSourceManager()
        }
        MenuActionId.OPEN_URL -> {
            host.closeHost()
            toggleOpenUrlDialog()
        }
        MenuActionId.OPEN_PLAYLIST -> host.launchPlaylist()
        MenuActionId.OPEN_LOCAL_VIDEO -> host.launchVideo()
        MenuActionId.CHANNELS -> {
            host.closeHost()
            showChannelsPanel()
        }
        MenuActionId.EPG -> {
            host.closeHost()
            showEpgPanel()
        }
        MenuActionId.CHANNEL_MAPPING -> {
            host.closeHost()
            toggleMappingPanel()
        }
        // 收藏就地切换，不关面板（两侧行为一致）
        MenuActionId.TOGGLE_FAVORITE -> toggleFavorite()
        MenuActionId.PLAYER_SETTINGS -> {
            host.closeHost()
            togglePlayerSettings()
        }
        MenuActionId.SUBTITLE -> {
            host.closeHost()
            toggleSubtitleSettings()
        }
        MenuActionId.VIDEO -> {
            host.closeHost()
            toggleVideoSettings()
        }
        MenuActionId.AUDIO -> {
            host.closeHost()
            toggleAudioSettings()
        }
        MenuActionId.PLAYBACK -> {
            host.closeHost()
            togglePlaybackPanel()
        }
        MenuActionId.MULTI_VIEW_ENTER -> {
            host.closeHost()
            val layout = action.arg
                ?.let { name -> runCatching { MultiViewLayout.valueOf(name) }.getOrNull() }
                ?: MultiViewLayout.DUAL
            enterMultiView(layout)
        }
        MenuActionId.MULTI_VIEW_EXIT -> {
            host.closeHost()
            exitMultiView()
        }
        // 弹窗类：纯 UI 状态，由宿主弹出
        MenuActionId.THEME_PICKER -> host.openThemePicker()
        MenuActionId.UI_MODE_PICKER -> host.openUiModePicker()
        MenuActionId.BOTTOM_BAR_STYLE_PICKER -> host.openBottomBarStylePicker()
        // 开关类：就地切换，不关面板
        MenuActionId.TOGGLE_LIQUID_GLASS -> setLiquidGlass(!liquidGlass.value)
        MenuActionId.TOGGLE_GLASS_REFRACTION -> setGlassRefraction(!glassRefraction.value)
        MenuActionId.TOGGLE_SHOW_TIME -> setOsdShowTime(!osdShowTime.value)
        MenuActionId.TOGGLE_NET_SPEED -> setOsdShowNetSpeed(!osdShowNetSpeed.value)
        MenuActionId.TOGGLE_HIDE_CHANNEL_NUM -> setOsdHideChannelNum(!osdHideChannelNum.value)
        MenuActionId.TOGGLE_SHOW_LIST_ICON -> setOsdShowListIcon(!osdShowListIcon.value)
        MenuActionId.TOGGLE_SHOW_BOTTOM_ICON -> setOsdShowBottomIcon(!osdShowBottomIcon.value)
        MenuActionId.TOGGLE_DISABLE_EPG -> setOsdDisableEpg(!osdDisableEpg.value)
        MenuActionId.TOGGLE_DISABLE_FAVORITE -> setOsdDisableFavorite(!osdDisableFavorite.value)
        MenuActionId.VIEW_SETTINGS -> {
            host.closeHost()
            toggleViewSettings()
        }
        MenuActionId.NETWORK -> {
            host.closeHost()
            toggleNetworkPanel()
        }
        MenuActionId.GITHUB_PROXY -> {
            host.closeHost()
            toggleGithubProxyPanel()
        }
        MenuActionId.TOOLS -> {
            host.closeHost()
            toggleToolsPanel()
        }
        MenuActionId.SCREENSHOT -> {
            host.closeHost()
            toggleScreenshotPanel()
        }
        MenuActionId.AVSYNC -> {
            host.closeHost()
            toggleAvSyncPanel()
        }
        MenuActionId.CLIP_EXPORT -> {
            host.closeHost()
            toggleClipExportPanel()
        }
        MenuActionId.AUDIO_VISUALIZER -> {
            host.closeHost()
            toggleAudioVisualizer()
        }
        MenuActionId.LYRICS -> {
            host.closeHost()
            toggleLyricsPanel()
        }
        MenuActionId.RECENT -> {
            host.closeHost()
            toggleRecentPanel()
        }
        MenuActionId.SAVE_AS_M3U -> {
            host.closeHost()
            saveAsM3u()
        }
        MenuActionId.REFRESH -> {
            host.closeHost()
            refreshUi()
        }
        MenuActionId.ABOUT -> {
            host.closeHost()
            toggleAboutPanel()
        }
        // 清除频道专属设置：就地执行，不关面板
        MenuActionId.CLEAR_CHANNEL_SETTINGS -> {
            val idx = currentIdx.value
            if (idx >= 0) clearChannelSettings(idx)
        }
        // 启动与屏保：就地切换，不关面板
        MenuActionId.TOGGLE_AUTO_RESUME -> setAutoResume(!autoResume.value)
        MenuActionId.TOGGLE_BOOT_START -> setBootStart(!bootStart.value)
        MenuActionId.TOGGLE_SCREEN_SAVER -> setScreenSaverEnabled(!screenSaverEnabled.value)
        MenuActionId.CYCLE_SCREEN_SAVER_TIMEOUT -> {
            val next = when (screenSaverTimeoutMinutes.value) {
                1 -> 5
                5 -> 10
                10 -> 30
                30 -> 60
                else -> 1
            }
            setScreenSaverTimeoutMinutes(next)
        }
        MenuActionId.PIP -> {
            host.closeHost()
            enterPip()
        }
        // 侧边栏保持既有行为：只提示用系统返回键退出；右侧菜单走真实退出确认
        MenuActionId.EXIT -> {
            if (host.kind == MenuHostKind.TV_SIDEBAR) {
                showOsd("退出", "请使用系统返回键退出")
            } else {
                host.closeHost()
                showExitConfirm()
            }
        }
    }
}
