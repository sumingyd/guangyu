from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QListWidget

from core.log_manager import global_logger as logger


class ThumbnailMixin:
    """从 IPTVPlayer 提取的缩略图/Logo 回调职责"""

    def _on_logo_cache_loaded(self, url, pixmap):
        self.ui_ctrl._on_logo_cache_loaded(url, pixmap)

    def _on_logo_cache_failed(self, url):
        """台标地址取不到图：记录失败并让该频道按优先级回退到下一来源。"""
        try:
            from services.logo_resolver import get_logo_resolver
            get_logo_resolver().invalidate_url(url)
        except Exception as e:
            logger.debug(f"记录台标失败状态出错: {e}")

        timer = getattr(self, '_logo_fallback_timer', None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(300)
            timer.timeout.connect(self._refresh_logos_after_failure)
            self._logo_fallback_timer = timer
        if not timer.isActive():
            timer.start()

    def _refresh_logos_after_failure(self):
        """失败原因汇入后再统一刷新可见台标，避免逐条失败触发刷新风暴。"""
        try:
            pairs = (
                (getattr(self, 'sub_channel_list', None), getattr(self, '_sub_channels', None)),
                (getattr(self, 'local_channel_list', None), getattr(self, '_local_channels', None)),
            )
            for list_widget, channels in pairs:
                if list_widget is None or not channels:
                    continue
                self.channel_ctrl.reset_visible_logo_pixmaps(list_widget)
                self._load_visible_icons(list_widget, channels)
            self.channel_ctrl.update_channel_info_on_selection()
        except Exception as e:
            logger.debug(f"台标来源回退刷新失败: {e}")

    def _on_thumbnail_ready(self, channel_name, url):
        self._update_grid_thumbnail(url)

    def _on_player_thumbnail_captured(self, url):
        self._update_grid_thumbnail(url)

    def _update_grid_thumbnail(self, url):
        from services.thumbnail_service import get_thumbnail_path
        thumb_path = get_thumbnail_path(url)
        if not thumb_path:
            return
        for list_widget in (self.sub_channel_list, self.local_channel_list):
            if list_widget.viewMode() != QListWidget.ViewMode.IconMode:
                continue
            channels = self._sub_channels if list_widget is self.sub_channel_list else self._local_channels
            match_idx = None
            for ci, ch in enumerate(channels or []):
                if ch.get('url', '') == url:
                    match_idx = ci
                    break
            if match_idx is None:
                continue
            item = list_widget.item(match_idx)
            if item and item.data(Qt.ItemDataRole.UserRole) == match_idx:
                px = QPixmap(thumb_path)
                if not px.isNull():
                    scaled = px.scaled(210, 118, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    item.setIcon(QIcon(scaled))