import os
import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox
from core.log_manager import global_logger as logger
from core.application_state import app_state


class FileOpsMixin:
    """从 IPTVPlayer 提取的文件操作/本地视频职责"""

    def update_recent_files_menu(self):
        self.recent_menu.clear()
        recent_files = self.config.load_recent_files()
        if not recent_files:
            no_recent_action = QAction(self.language_manager.tr("no_recent_files", "No recent files"), self)
            no_recent_action.setEnabled(False)
            self.recent_menu.addAction(no_recent_action)
        else:
            for file_path in recent_files:
                action = QAction(file_path, self)
                action.triggered.connect(lambda checked, path=file_path: self.open_recent_file(path))
                self.recent_menu.addAction(action)

    def open_recent_file(self, file_path):
        self.settings_ops.open_recent_file(file_path)

    def _apply_m3u_content(self, content, file_path):
        tr = self.language_manager.tr
        _unnamed = tr('unnamed', '未命名')
        _uncategorized = tr('uncategorized', '未分类')
        try:
            if self.channel_model.load_from_file(content):
                self.channel_model._source_file_path = file_path
                new_channels = []
                for i, ch in enumerate(self.channel_model.channels):
                    new_channels.append({
                        "id": i + 1,
                        "name": ch.get('name', _unnamed),
                        "url": ch.get('url', ''),
                        "logo": ch.get('logo', ''),
                        "group": ch.get('group', _uncategorized),
                        "_groups": ch.get('_groups', [ch.get('group', _uncategorized)]),
                        "tvg_id": ch.get('tvg_id', ''),
                        "tvg_chno": ch.get('tvg_chno', ''),
                        "tvg_shift": ch.get('tvg_shift', ''),
                        "catchup": ch.get('catchup', ''),
                        "catchup_days": ch.get('catchup_days', ''),
                        "catchup_source": ch.get('catchup_source', ''),
                        "resolution": ch.get('resolution', ''),
                        "current_program": '',
                        "source": '',
                        "_raw_extinf": ch.get('_raw_extinf', ''),
                        "_all_tags": ch.get('_all_tags', {})
                    })

                # 本地块整体替换，再按「本地在前、订阅在后」重建聚合表
                self._apply_local_block(
                    new_channels, file_path,
                    header_attrs=getattr(self.channel_model, '_last_header_attrs', None),
                )

                if app_state.channel_count > 0:
                    self.current_channel = app_state.get_channel_by_index(0)
                    display_name = self._get_display_channel_name(self.current_channel)
                    self.channel_name.setText(display_name)

                if hasattr(self, 'playlist_tab'):
                    self.playlist_tab.setCurrentIndex(1)
                self.populate_channel_list(source='local')
                # 文件头 epg_url 登记为补充源（已配置同地址源时跳过）
                self.settings_ops._apply_header_epg_url(schedule_populate=False)
                try:
                    # 立刻刷新顶部当前节目与节目单面板，避免停留在上一个频道
                    if app_state.channel_count > 0:
                        self.update_channel_info_on_selection()
                        self._populate_epg_list()
                    # EPG 未加载或解析时用的不是这份频道表时，后台按当前频道表重载
                    self.settings_ops._ensure_epg_for_playlist_channels()
                except Exception as refresh_err:
                    logger.warning(f"刷新最近打开文件的节目信息失败: {refresh_err}")
                self.status_bar.showMessage(f"{tr('file_opened', 'File opened')}: {file_path}")
                logger.info(f"成功打开最近文件: {file_path}, 共 {app_state.channel_count} 个频道")
            else:
                self.status_bar.showMessage(tr("file_format_error", "文件格式错误") or '')
        except Exception as ex:
            logger.error(f"应用M3U内容失败: {str(ex)}")
            self.status_bar.showMessage(f"{tr('file_open_failed', 'Failed to open file')}: {str(ex)}")

    def open_playlist(self):
        self.settings_ops.open_playlist()

    def _open_stream(self):
        self.settings_ops._open_stream()

    def _open_video_file(self):
        from ui.dialogs.video_open_dialog import VideoOpenDialog
        dialog = VideoOpenDialog(self, language_manager=self.language_manager)
        if dialog.exec() == 1:
            path = dialog.get_selected_path()
            if path:
                self._open_video_path(path)

    def _open_video_path(self, path):
        tr = self.language_manager.tr
        if os.path.isfile(path):
            self._add_local_video_and_track(path)
            return

        if os.path.isdir(path):
            from services.mpv_player_service import MpvPlayerController
            bdmv = MpvPlayerController._detect_bdmv_path(path)
            if bdmv:
                name = os.path.basename(os.path.dirname(bdmv)) or os.path.basename(bdmv)
                channel = {
                    'name': name,
                    'url': path,
                    'group': tr("bluray", "蓝光原盘"),
                    '_groups': [tr("bluray", "蓝光原盘")],
                }
                self._add_to_local_list(channel)
                self.config.add_recent_file(path)
                self.update_recent_files_menu()
                return

            video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.m2ts', '.webm')
            audio_exts = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus', '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta', '.dts', '.ac3', '.mid', '.midi')
            media_exts = video_exts + audio_exts
            video_files = []
            list_error = None
            try:
                for f in os.listdir(path):
                    if f.lower().endswith(media_exts):
                        video_files.append(os.path.join(path, f))
                video_files.sort(key=lambda x: x.lower())
            except PermissionError:
                list_error = 'permission'
            except Exception:
                pass

            if list_error == 'permission':
                QMessageBox.warning(
                    self, tr("open_video", "打开视频"),
                    tr("no_permission_folder", "无权限访问该文件夹"),
                )
                return

            if not video_files:
                QMessageBox.information(
                    self, tr("open_video", "打开视频"),
                    tr("no_media_in_folder", "所选文件夹中未找到支持的音视频文件"),
                )
                return

            folder_name = os.path.basename(path) or os.path.split(path)[-1] or tr('video', '视频')
            for vf in video_files:
                name = os.path.splitext(os.path.basename(vf))[0]
                channel = {
                    'name': name,
                    'url': vf,
                    'group': folder_name,
                    '_groups': [folder_name],
                }
                self._add_to_local_list(channel)
            self.config.add_recent_file(path)
            self.update_recent_files_menu()

    def _create_local_video_channel(self, path: str, group_key: str = "local_video", group_default: str = "本地视频") -> dict:
        name = os.path.splitext(os.path.basename(path))[0]
        audio_exts = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus', '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta', '.dts', '.ac3', '.mid', '.midi')
        if path.lower().endswith(audio_exts):
            group = self.language_manager.tr("local_audio", "本地音频")
        else:
            group = self.language_manager.tr(group_key, group_default)
        return {
            'name': name,
            'url': path,
            'group': group,
            '_groups': [group],
        }

    def _add_local_video_and_track(self, path: str, group_key: str = "local_video", group_default: str = "本地视频"):
        channel = self._create_local_video_channel(path, group_key, group_default)
        self._add_to_local_list(channel)
        self.config.add_recent_file(path)
        self.update_recent_files_menu()

    def _add_to_local_list(self, channel):
        item = copy.deepcopy(channel)
        item.setdefault('source', '')
        self._local_channels.append(item)
        self._local_channels_dirty = True
        rebuild = getattr(self, '_rebuild_channel_aggregation', None)
        if callable(rebuild):
            rebuild()
        new_idx = len(self._local_channels) - 1
        self.playlist_tab.setCurrentIndex(1)
        self._update_groups_for('local')
        self._populate_channel_list_for(
            self.local_channel_list, self._local_channels,
            self.local_group_combo.currentText()
        )
        for i in range(self.local_channel_list.count()):
            item = self.local_channel_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == new_idx:
                self.local_channel_list.setCurrentItem(item)
                break
        self.current_channel = channel
        self.update_channel_info_on_selection()
        self.play_channel(channel)

    def save_as(self):
        self.settings_ops.save_as()

    def show_usage_instructions(self):
        self.settings_ops.show_usage_instructions()

    def save_window_layout(self):
        self.settings_ops.save_window_layout()