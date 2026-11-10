package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * APTV 风格竖屏强调色（红粉），仅用于竖屏页面对齐 APTV 视觉，不影响横屏/TV 主题。
 */
internal val AptvAccent: Color get() = tvPalette.accentGraphic
internal val AptvAccentText: Color get() = tvPalette.accentText
internal val AptvAccentFill: Color get() = tvPalette.accentFill

/**
 * APTV 风格开关：竖屏 APTV 页面（PortraitPanelDialog push 页等）内提供 true，
 * 共用基座组件（PanelScaffold/SectionLabel 等）据此切换 APTV 样式；默认 false 保持原样式。
 */
internal val LocalAptvStyle = compositionLocalOf { false }

/**
 * 液态玻璃开关：通过 CompositionLocal 传递，竖屏 AptvGroupCard / PortraitPanelDialog 等读取此值。
 */
internal val LocalLiquidGlass = compositionLocalOf { false }


/** APTV 分组节头：灰色小字 */
@Composable
internal fun AptvSectionHeader(title: String) {
    Text(
        text = title,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 13.sp,
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 24.dp, top = 16.dp, bottom = 6.dp)
    )
}

/**
 * 玻璃底座容器：液态玻璃开启时把内容包成静态玻璃（磨砂+描边+高光），
 * 关闭/降级时原样透传（无任何背景）。用于头部按钮、搜索框、Mini 播放条等小部件。
 */
@Composable
internal fun AptvGlassChip(
    modifier: Modifier = Modifier,
    cornerRadius: androidx.compose.ui.unit.Dp = 20.dp,
    content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit
) {
    val liquidGlass = LocalLiquidGlass.current
    if (liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported()) {
        // 轻量单层玻璃（与玻璃按钮同风格）：小部件上叠加厚霜/双描边会出现「两层玻璃」观感
        // 浅色主题：白底上白描边不可见，描边改用深灰蓝低透明度提供轮廓（与 LightGlass 一致）
        // 亮玻璃 / 暗玻璃两套材质全部取自 palette token（effect.glass_*），
        // 由 palette.json 的深/浅两套值决定，不在代码里写死白/黑 alpha。
        val shape = androidx.compose.foundation.shape.RoundedCornerShape(cornerRadius)
        androidx.compose.foundation.layout.Box(
            modifier = modifier
                .clip(shape)
                .background(tvPalette.glassFill, shape)
                .border(1.dp, tvPalette.glassBorder, shape)
                .background(
                    androidx.compose.ui.graphics.Brush.verticalGradient(
                        0f to tvPalette.glassGloss,
                        1f to Color.Transparent
                    ),
                    shape
                ),
            content = content
        )
    } else {
        androidx.compose.foundation.layout.Box(modifier = modifier, content = content)
    }
}

/**
 * 玻璃胶囊按钮：液态玻璃开启时为半透明磨砂 + 白描边 + 顶部高光（iOS 拟态玻璃按钮），
 * 关闭/降级时回落到 Material3 OutlinedButton 原样式。
 * 与 material3.OutlinedButton 同签名，面板文件删除 import 即可零改动切换。
 */
@Composable
internal fun OutlinedButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit
) {
    val liquidGlass = LocalLiquidGlass.current
    if (liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported()) {
        val contentColor = tvPalette.textPrimary
        val shape = RoundedCornerShape(50)
        Box(
            modifier = modifier
                .clip(shape)
                .background(tvPalette.glassFillSoft, shape)
                .border(
                    1.dp,
                    tvPalette.glassBorder,
                    shape
                )
                .background(
                    androidx.compose.ui.graphics.Brush.verticalGradient(
                        0f to tvPalette.glassGloss,
                        0.5f to Color.Transparent,
                        1f to tvPalette.glassShadow
                    ),
                    shape
                )
                .clickable(enabled = enabled) { onClick() }
                .padding(horizontal = 18.dp, vertical = 9.dp),
            contentAlignment = androidx.compose.ui.Alignment.Center
        ) {
            androidx.compose.runtime.CompositionLocalProvider(
                androidx.compose.material3.LocalContentColor provides
                    if (enabled) contentColor else contentColor.copy(alpha = 0.38f)
            ) {
                Row(
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    content = content
                )
            }
        }
    } else {
        androidx.compose.material3.OutlinedButton(
            onClick = onClick,
            modifier = modifier,
            enabled = enabled,
            content = content
        )
    }
}

/**
 * 玻璃主按钮：与 material3.Button 同签名。液态玻璃开启时为品牌色半透明胶囊 + 白描边 + 高光，
 * 关闭/降级时回落 Material3 Button 原样式。
 */
@Composable
internal fun Button(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit
) {
    val liquidGlass = LocalLiquidGlass.current
    if (liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported()) {
        val shape = RoundedCornerShape(50)
        Box(
            modifier = modifier
                .clip(shape)
                .background(tvPalette.accentFill.copy(alpha = if (enabled) 1f else 0.35f), shape)
                .border(1.dp, tvPalette.accentOn.copy(alpha = 0.42f), shape)
                .background(
                    androidx.compose.ui.graphics.Brush.verticalGradient(
                        0f to tvPalette.accentOn.copy(alpha = 0.22f),
                        0.5f to Color.Transparent,
                        1f to tvPalette.glassShadow
                    ),
                    shape
                )
                .clickable(enabled = enabled) { onClick() }
                .padding(horizontal = 18.dp, vertical = 9.dp),
            contentAlignment = androidx.compose.ui.Alignment.Center
        ) {
            androidx.compose.runtime.CompositionLocalProvider(
                androidx.compose.material3.LocalContentColor provides
                    if (enabled) tvPalette.accentOn else tvPalette.accentOn.copy(alpha = 0.50f)
            ) {
                Row(
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    content = content
                )
            }
        }
    } else {
        androidx.compose.material3.Button(
            onClick = onClick,
            modifier = modifier,
            enabled = enabled,
            content = content
        )
    }
}

/**
 * 玻璃圆形图标按钮：与 material3.IconButton 同签名。液态玻璃开启时为圆形磨砂底 + 白描边，
 * 关闭/降级时回落 Material3 IconButton 原样式。
 */
@Composable
internal fun IconButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit
) {
    val liquidGlass = LocalLiquidGlass.current
    if (liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported()) {
        Box(
            modifier = modifier
                .size(34.dp)
                .clip(androidx.compose.foundation.shape.CircleShape)
                .background(
                    tvPalette.glassFillSoft,
                    androidx.compose.foundation.shape.CircleShape
                )
                .border(
                    1.dp,
                    tvPalette.glassBorder,
                    androidx.compose.foundation.shape.CircleShape
                )
                .background(
                    androidx.compose.ui.graphics.Brush.verticalGradient(
                        0f to tvPalette.glassGloss,
                        1f to Color.Transparent
                    ),
                    androidx.compose.foundation.shape.CircleShape
                )
                .clickable(enabled = enabled, onClick = onClick),
            contentAlignment = androidx.compose.ui.Alignment.Center,
            content = content
        )
    } else {
        androidx.compose.material3.IconButton(
            onClick = onClick,
            modifier = modifier,
            enabled = enabled
        ) {
            androidx.compose.foundation.layout.Box(
                contentAlignment = androidx.compose.ui.Alignment.Center,
                content = content
            )
        }
    }
}

/** APTV 分组卡片容器：液态玻璃卡（跟随开关，降级为实底卡） */
@Composable
internal fun AptvGroupCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit
) {
    val liquidGlass = LocalLiquidGlass.current
    LiquidGlassSurface(
        enabled = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
        cornerRadius = 12.dp,
        staticGlass = true,
        // 关闭/降级：原 55% surfaceVariant 实底
        fallbackColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp)
    ) {
        Column(content = content)
    }
}

/** APTV 设置行：红底圆角图标 + 标题 + 右侧值 + 箭头 */
@Composable
internal fun AptvRow(
    icon: ImageVector,
    title: String,
    value: String = "",
    disabled: Boolean = false,
    trailing: (@Composable () -> Unit)? = null,
    modifier: Modifier = Modifier,
    onClick: () -> Unit = {}
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            // 行高固定为 48dp（= 28dp 图标 + 2×10dp 内边距），保证命中区与视觉行高一致，
            // 不随内容/换行浮动；clickable 挂在这一整行上（不是文字节点）
            .heightIn(min = 48.dp)
            // tvFocusBorder 必须在 clickable 之前（外层）：onFocusChanged 只能观察到
            // 链中内层方向的 focus target，放在 clickable 之后收不到焦点事件（无高亮/放大）
            .then(if (disabled) Modifier else Modifier.tvFocusBorder())
            .then(
                if (disabled) Modifier
                else Modifier.clickable(role = androidx.compose.ui.semantics.Role.Button, onClick = onClick)
            )
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .clip(RoundedCornerShape(7.dp))
                .background(
                    tvPalette.accentFill.copy(alpha = if (disabled) 0.30f else 1f)
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(icon, contentDescription = null, tint = tvPalette.accentOn, modifier = Modifier.size(16.dp))
        }
        Spacer(modifier = Modifier.width(12.dp))
        Text(
            text = title,
            color = if (disabled) MaterialTheme.colorScheme.onSurface.copy(alpha = 0.35f) else MaterialTheme.colorScheme.onSurface,
            fontSize = 15.sp,
            modifier = Modifier.weight(1f)
        )
        if (value.isNotEmpty()) {
            Text(
                text = value,
                // 深色主题的行底曾被玻璃高光抬到中灰（#7E8087），用 onSurfaceVariant(#AAA)
                // 只有 3.1:1；行值属于正文，改用 onSurface（深色=白，浅色=#333）
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
            Spacer(modifier = Modifier.width(6.dp))
        }
        if (trailing != null) {
            Spacer(modifier = Modifier.width(4.dp))
            trailing()
            Spacer(modifier = Modifier.width(4.dp))
        }
        if (!disabled) {
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.55f),
                modifier = Modifier.size(18.dp)
            )
        }
    }
}

/**
 * APTV 风格开关行：图标+标题+Switch，用于设置页通用分组。
 */
@Composable
internal fun AptvSwitchRow(
    icon: ImageVector,
    title: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            // tvFocusBorder 在 clickable 之前（外层）才能收到焦点事件
            .tvFocusBorder()
            .clickable { onCheckedChange(!checked) }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .clip(RoundedCornerShape(7.dp))
                .background(if (checked) tvPalette.accentFill else tvPalette.accentFill.copy(alpha = 0.45f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(icon, contentDescription = null, tint = tvPalette.accentOn, modifier = Modifier.size(16.dp))
        }
        Spacer(modifier = Modifier.width(12.dp))
        Text(
            text = title,
            color = MaterialTheme.colorScheme.onSurface,
            fontSize = 15.sp,
            modifier = Modifier.weight(1f)
        )
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            // 整行已可聚焦（clickable）：内层 Switch 若单独成为焦点节点，
            // 方向键会命中这个小组件、且外层 tvFocusBorder 观察不到子节点焦点（无行高亮），
            // 与 MiniPlayerBar 内播放按钮同样的处理：不参与焦点
            modifier = Modifier.focusProperties { canFocus = false }
        )
    }
}

/**
 * 双模式选择组：APTV 模式下渲染为 iOS 风格选择行（标题+当前值+管头，点击弹底部列表），
 * 非 APTV 模式下保持 FilterChip 平铺不变。
 *
 * @param title 行标题（如"旋转"、"翻转"）
 * @param options 选项列表 (key, label)，如 listOf(0 to "0°", 90 to "90°")
 * @param selectedKey 当前选中的 key
 * @param onSelect 选中回调
 * @param disabled 是否禁用
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun SelectionGroup(
    title: String,
    options: List<Pair<String, String>>,
    selectedKey: String,
    onSelect: (String) -> Unit,
    disabled: Boolean = false
) {
    if (LocalAptvStyle.current) {
        var showSheet by remember { mutableStateOf(false) }
        val selectedLabel = options.find { it.first == selectedKey }?.second ?: ""

        Row(
            modifier = Modifier
                .fillMaxWidth()
                // TV 遥控器焦点高亮（clickable 外层）
                .then(if (disabled) Modifier else Modifier.tvFocusBorder())
                .then(if (disabled) Modifier else Modifier.clickable { showSheet = true })
                .padding(vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = title,
                color = if (disabled) MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f) else MaterialTheme.colorScheme.onSurface,
                fontSize = 15.sp,
                modifier = Modifier.weight(1f)
            )
            Text(
                text = selectedLabel,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 14.sp
            )
            Spacer(modifier = Modifier.width(6.dp))
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                modifier = Modifier.size(18.dp)
            )
        }

        if (showSheet) {
            androidx.compose.ui.window.Popup(
                onDismissRequest = { showSheet = false },
                properties = androidx.compose.ui.window.PopupProperties(focusable = true)
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(tvPalette.overlay)
                        .clickable { showSheet = false }
                ) {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .align(Alignment.BottomCenter),
                        color = MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
                        tonalElevation = 6.dp
                    ) {
                        Column {
                            Text(
                                text = title,
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Medium,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp)
                            )
                            HorizontalDivider(
                                color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f)
                            )
                            options.forEach { (key, label) ->
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { onSelect(key); showSheet = false }
                                        .padding(horizontal = 20.dp, vertical = 14.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = label,
                                        fontSize = 16.sp,
                                        color = MaterialTheme.colorScheme.onSurface,
                                        modifier = Modifier.weight(1f)
                                    )
                                    if (key == selectedKey) {
                                        Icon(
                                            Icons.Default.Check,
                                            contentDescription = null,
                                            tint = tvPalette.accentGraphic,
                                            modifier = Modifier.size(20.dp)
                                        )
                                    }
                                }
                            }
                            Spacer(modifier = Modifier.height(20.dp))
                        }
                    }
                }
            }
        }
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            options.forEach { (key, label) ->
                FilterChip(
                    selected = selectedKey == key,
                    onClick = { onSelect(key) },
                    label = { Text(label) }
                )
            }
        }
    }
}

/**
 * 双模式开关行：APTV 模式下渲染为 iOS 风格开关行（标题左+Switch右），
 * 非 APTV 模式下保持传入的 content 不变。
 */
@Composable
internal fun SwitchRow(
    title: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    disabled: Boolean = false
) {
    if (LocalAptvStyle.current) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = title,
                color = if (disabled) MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f) else MaterialTheme.colorScheme.onSurface,
                fontSize = 15.sp,
                modifier = Modifier.weight(1f)
            )
            androidx.compose.material3.Switch(
                checked = checked,
                onCheckedChange = onCheckedChange,
                enabled = !disabled,
                colors = androidx.compose.material3.SwitchDefaults.colors(
                    checkedThumbColor = tvPalette.accentOn,
                    checkedTrackColor = tvPalette.accentFill,
                    uncheckedThumbColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    uncheckedTrackColor = MaterialTheme.colorScheme.surfaceVariant
                )
            )
        }
    } else {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(title, color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, modifier = Modifier.weight(1f))
            androidx.compose.material3.Switch(
                checked = checked,
                onCheckedChange = onCheckedChange,
                enabled = !disabled
            )
        }
    }
}

/** APTV 风格面板标题栏：大标题 + 红色副标题 + 关闭按钮（竖屏 push 页头部） */
@Composable
internal fun AptvPanelHeader(
    title: String,
    subtitle: String = "",
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
    actions: @Composable () -> Unit = {}
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 1
            )
            if (subtitle.isNotEmpty()) {
                Text(
                    text = subtitle,
                    color = tvPalette.accentText,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            actions()
            Icon(
                Icons.Default.Close,
                contentDescription = "关闭",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .size(24.dp)
                    .clickable(onClick = onClose)
            )
        }
    }
}
/**
 * iOS 风格居中卡片弹窗：圆角 + 标题 + 消息 + 横排按钮（取消左/确认右）。
 * APTV 模式下确认按钮用 AptvAccent，非 APTV 用 primary。
 */
@Composable
internal fun AptvAlertDialog(
    title: String,
    message: String,
    confirmText: String = "确认",
    dismissText: String = "取消",
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    destructive: Boolean = false
) {
    androidx.compose.ui.window.Dialog(
        onDismissRequest = onDismiss,
        properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 40.dp)
        ) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text(
                    text = title,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.fillMaxWidth()
                )
                if (message.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = message,
                        fontSize = 14.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        lineHeight = 20.sp,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = dismissText,
                        fontSize = 16.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .clickable(onClick = onDismiss)
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = confirmText,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Medium,
                        color = if (destructive) MaterialTheme.colorScheme.error else tvPalette.accentText,
                        modifier = Modifier
                            .clickable(onClick = onConfirm)
                            .padding(horizontal = 12.dp, vertical = 8.dp)
                    )
                }
            }
        }
    }
}

/**
 * 全屏底栏样式迷你预览：按 4 种底栏样式的结构布局用缩微色块示意，
 * 供设置页行尾与样式选择弹窗使用（暗玻璃底色，两种主题下均可辨）。
 */
@Composable
internal fun BottomBarStyleMiniPreview(style: Int, modifier: Modifier = Modifier) {
    // 底座与示意线全部取 token：深色主题为深灰玻璃 + 白线，浅色主题为浅灰底 + 深灰线，
    // 不再固定暗底 + 白色半透明（浅色下白线会消失在浅底里）
    val barBg = tvPalette.panelControlBackground
    val line = tvPalette.textPrimary.copy(alpha = 0.80f)
    val lineDim = tvPalette.textPrimary.copy(alpha = 0.35f)
    Box(
        modifier = modifier
            .height(26.dp)
            .clip(RoundedCornerShape(5.dp))
            .background(barBg)
            .border(0.5.dp, tvPalette.glassBorder, RoundedCornerShape(5.dp))
            .padding(horizontal = 5.dp, vertical = 4.dp)
    ) {
        when (style) {
            // 样式 B：单行紧凑式 —— 台标 + 频道名 + 进度 + 控制点一行排布
            1 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(12.dp, 8.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                Spacer(Modifier.width(3.dp))
                Box(Modifier.size(14.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                Spacer(Modifier.width(4.dp))
                Box(Modifier.weight(1f).height(2.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                repeat(3) {
                    Box(Modifier.size(4.dp).clip(CircleShape).background(AptvAccent))
                    if (it < 2) Spacer(Modifier.width(2.dp))
                }
            }
            // 样式 C：居中控制台式 —— 顶部信息行居中 + 中央大控制点组
            2 -> Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Box(Modifier.size(20.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                Spacer(Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(7.dp).clip(CircleShape).background(AptvAccent))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                }
            }
            // 样式 D：左信息右控制式 —— 左两行信息 | 竖分隔 | 右控制点组
            3 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(22.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.height(3.dp))
                    Box(Modifier.size(14.dp, 2.dp).background(lineDim))
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.width(0.5.dp).height(14.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(6.dp).clip(CircleShape).background(AptvAccent))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                }
            }
            // 样式 E：居中悬浮式 —— 居中胶囊内 台标+文字线+控制点
            4 -> Row(
                modifier = Modifier.fillMaxSize(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center
            ) {
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .background(tvPalette.glassFillSoft)
                        .padding(horizontal = 6.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(Modifier.size(10.dp, 6.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(14.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.width(4.dp))
                    Box(Modifier.width(0.5.dp).height(7.dp).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(6.dp).clip(CircleShape).background(AptvAccent))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                }
            }
            // 样式 F：大台标信息式 —— 左大台标 + 中两行文字 | 右时钟列
            5 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(18.dp, 14.dp).clip(RoundedCornerShape(2.dp)).background(lineDim))
                Spacer(Modifier.width(5.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(26.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.height(3.dp))
                    Box(Modifier.size(16.dp, 2.dp).background(lineDim))
                }
                Spacer(Modifier.width(4.dp))
                Column(horizontalAlignment = Alignment.End) {
                    Box(Modifier.size(10.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(7.dp, 2.dp).background(lineDim))
                }
            }
            // 样式 G：进度优先式 —— 台标+频道行 / 粗进度条 / 节目+控制行
            6 -> Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp, 6.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(16.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                }
                Spacer(Modifier.height(3.dp))
                Box(Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(1.5.dp)).background(lineDim)) {
                    Box(Modifier.fillMaxWidth(0.4f).fillMaxHeight().background(AptvAccent))
                }
                Spacer(Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(14.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.weight(1f))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(5.dp).clip(CircleShape).background(line))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                }
            }
            // 样式 H：左控制右信息式 —— 左控制点组 | 竖分隔 | 右三行信息（D 镜像）
            7 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(6.dp).clip(CircleShape).background(AptvAccent))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(22.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(16.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(10.dp, 2.dp).background(lineDim.copy(alpha = 0.7f)))
                }
            }
            // 样式 I：三段等分式 —— 台标频道 | 节目进度 | 时钟控制 三段均分带竖分隔
            8 -> Row(modifier = Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(14.dp, 7.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(12.dp, 2.dp).background(line))
                }
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(18.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.fillMaxWidth(0.7f).height(2.dp).background(lineDim))
                }
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(14.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Row {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(4.dp).clip(CircleShape).background(AptvAccent))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    }
                }
            }
            // 样式 J：OSD 大字式 —— 左居中大字信息两行+进度 | 竖分隔 | 右双排控制点
            9 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Column(
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Box(Modifier.size(30.dp, 4.dp).clip(RoundedCornerShape(2.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(20.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.fillMaxWidth(0.5f).height(1.5.dp).background(lineDim.copy(alpha = 0.6f)))
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Row {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(5.dp).clip(CircleShape).background(AptvAccent))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    }
                    Spacer(Modifier.height(2.dp))
                    Row {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    }
                }
            }
            // 样式 K：控制台双行式 —— 上控制点组 + 下台标信息行（C 倒置）
            10 -> Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(7.dp).clip(CircleShape).background(AptvAccent))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                }
                Spacer(Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp, 5.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(16.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.weight(1f))
                    Box(Modifier.size(10.dp, 2.dp).background(lineDim))
                }
            }
            // 样式 L：卡片网格式 —— 左信息三行 | 中时钟块 | 右 2x2 按钮网格
            11 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(22.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(14.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(10.dp, 2.dp).background(lineDim.copy(alpha = 0.7f)))
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(12.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(8.dp, 2.dp).background(lineDim))
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column {
                    Row {
                        Box(Modifier.size(7.dp).clip(RoundedCornerShape(1.5.dp)).background(lineDim))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(7.dp).clip(RoundedCornerShape(1.5.dp)).background(lineDim))
                    }
                    Spacer(Modifier.height(2.dp))
                    Row {
                        Box(Modifier.size(7.dp).clip(RoundedCornerShape(1.5.dp)).background(lineDim))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(7.dp).clip(RoundedCornerShape(1.5.dp)).background(AptvAccent))
                    }
                }
            }
            // 样式 M：广播电视式 —— 贴底全宽：左大台标 | 中节目行列 | 右徽章+大时钟
            12 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(20.dp, 12.dp).clip(RoundedCornerShape(2.dp)).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(26.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(20.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(24.dp, 2.dp).background(lineDim.copy(alpha = 0.6f)))
                }
                Spacer(Modifier.width(4.dp))
                Column(horizontalAlignment = Alignment.End) {
                    Row {
                        Box(Modifier.size(6.dp, 2.dp).background(AptvAccent))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(6.dp, 2.dp).background(lineDim))
                    }
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(16.dp, 4.dp).clip(RoundedCornerShape(2.dp)).background(line))
                }
            }
            // 样式 N：机顶盒 OSD 式 —— 上区台标+EPG+REC+大时钟，底部技术参数行
            13 -> Column(verticalArrangement = Arrangement.Center) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(14.dp, 8.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.width(4.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Box(Modifier.size(18.dp, 2.dp).background(line))
                        Spacer(Modifier.height(2.dp))
                        Box(Modifier.size(12.dp, 2.dp).background(lineDim))
                    }
                    Box(Modifier.size(12.dp, 4.dp).clip(RoundedCornerShape(2.dp)).background(AptvAccent))
                }
                Spacer(Modifier.height(2.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(24.dp, 1.5.dp).background(lineDim.copy(alpha = 0.5f)))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(6.dp, 1.5.dp).background(lineDim))
                    Spacer(Modifier.width(3.dp))
                    Box(Modifier.size(6.dp, 1.5.dp).background(lineDim))
                }
            }
            // 样式 O：影院 EPG 卡式 —— 左大台标 | 右频道名+正在播放+简介+下一节目
            14 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(22.dp, 16.dp).clip(RoundedCornerShape(2.dp)).background(lineDim))
                Spacer(Modifier.width(5.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(16.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                        Spacer(Modifier.weight(1f))
                        Box(Modifier.size(8.dp, 2.dp).background(AptvAccent))
                    }
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(28.dp, 2.dp).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(22.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(18.dp, 2.dp).background(lineDim.copy(alpha = 0.6f)))
                }
            }
            // 样式 P：仪表盘 OSD 式 —— 左大台标+日期 | 中节目+彩条进度 | 右大时钟
            15 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(18.dp, 10.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(12.dp, 1.5.dp).background(lineDim.copy(alpha = 0.6f)))
                }
                Spacer(Modifier.width(4.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(20.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.fillMaxWidth().height(2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(lineDim)) {
                        Box(
                            Modifier.fillMaxWidth(0.5f).fillMaxHeight().background(
                                androidx.compose.ui.graphics.Brush.horizontalGradient(
                                    listOf(AptvAccent, tvPalette.accentBase)
                                )
                            )
                        )
                    }
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(14.dp, 1.5.dp).background(lineDim.copy(alpha = 0.5f)))
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.size(14.dp, 5.dp).clip(RoundedCornerShape(2.dp)).background(AptvAccent))
            }
            // 样式 Q：海报卡片式 —— 顶部细进度 + 左方台标 | 右频道名+三行节目 | 右端按钮点
            16 -> Column {
                Box(Modifier.fillMaxWidth().height(1.dp).background(lineDim)) {
                    Box(Modifier.fillMaxWidth(0.4f).fillMaxHeight().background(AptvAccent))
                }
                Spacer(Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(14.dp).clip(RoundedCornerShape(2.dp)).background(lineDim))
                    Spacer(Modifier.width(4.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Box(Modifier.size(16.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                        Spacer(Modifier.height(2.dp))
                        Box(Modifier.size(22.dp, 1.5.dp).background(lineDim))
                        Spacer(Modifier.height(1.dp))
                        Box(Modifier.size(18.dp, 1.5.dp).background(lineDim.copy(alpha = 0.6f)))
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Row {
                            Box(Modifier.size(4.dp).clip(CircleShape).background(lineDim))
                            Spacer(Modifier.width(2.dp))
                            Box(Modifier.size(5.dp).clip(CircleShape).background(AptvAccent))
                            Spacer(Modifier.width(2.dp))
                            Box(Modifier.size(4.dp).clip(CircleShape).background(lineDim))
                        }
                        Spacer(Modifier.height(2.dp))
                        Row {
                            Box(Modifier.size(4.dp).clip(CircleShape).background(lineDim))
                            Spacer(Modifier.width(2.dp))
                            Box(Modifier.size(4.dp).clip(CircleShape).background(lineDim))
                        }
                    }
                }
            }
            // 样式 R：节目时间轴式 —— 左频道块 | 中三档节目点线时间轴 | 右大时钟+按钮
            17 -> Row(verticalAlignment = Alignment.CenterVertically) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(14.dp, 8.dp).clip(RoundedCornerShape(1.dp)).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(10.dp, 1.5.dp).background(lineDim.copy(alpha = 0.6f)))
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(AptvAccent))
                        Spacer(Modifier.width(3.dp))
                        Box(Modifier.size(18.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                        Spacer(Modifier.width(3.dp))
                        Box(Modifier.size(14.dp, 1.5.dp).background(lineDim))
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim.copy(alpha = 0.5f)))
                        Spacer(Modifier.width(3.dp))
                        Box(Modifier.size(12.dp, 1.5.dp).background(lineDim.copy(alpha = 0.6f)))
                    }
                }
                Spacer(Modifier.width(4.dp))
                Box(Modifier.width(0.5.dp).height(16.dp).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size(12.dp, 3.dp).clip(RoundedCornerShape(1.5.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Row {
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(4.dp).clip(CircleShape).background(AptvAccent))
                        Spacer(Modifier.width(2.dp))
                        Box(Modifier.size(3.dp).clip(CircleShape).background(lineDim))
                    }
                }
            }
            // 样式 A：信息详情式 —— 左台标 + 右三行信息
            else -> Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(14.dp, 12.dp).clip(RoundedCornerShape(2.dp)).background(lineDim))
                Spacer(Modifier.width(4.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Box(Modifier.size(18.dp, 2.5.dp).clip(RoundedCornerShape(1.25.dp)).background(line))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(26.dp, 2.dp).background(lineDim))
                    Spacer(Modifier.height(2.dp))
                    Box(Modifier.size(12.dp, 2.dp).background(lineDim.copy(alpha = 0.7f)))
                }
            }
        }
    }
}