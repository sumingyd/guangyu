"""
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu
媒体控制控制器 - 负责右键菜单、截图、音轨/字幕、倍速/画面比例等媒体相关控制
从 pyqt_player.py 提取的独立模块
"""

import os
import re

from core.log_manager import global_logger as logger
from controllers.main_window_protocol import PlaybackProtocol
from controllers.context_menu_controller import ContextMenuController
from controllers.preset_controller import PresetController
from controllers.lyrics_controller import LyricsController
from utils.thread_safety import safe_single_shot
from utils.delay_constants import DelayMs


class MediaController:
    """媒体控制控制器 - 统一管理媒体相关的所有控制逻辑"""

    SPEED_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0, 5.0]
    ASPECT_CYCLE = ['default', '16:9', '4:3', 'stretch', 'fill']
    # 右键菜单 HDR 输出模式 (mode, i18n_key)，与设置窗口 hdr_items 保持一致
    _HDR_MODES = [
        ('disable', 'hdr_disable'),
        ('tonemap', 'hdr_tonemap'),
        ('passthrough', 'hdr_passthrough'),
    ]

    def __init__(self, main_window: PlaybackProtocol):
        self.window: PlaybackProtocol = main_window
        self._current_aspect_idx = 0
        self._context_menu = ContextMenuController(self)
        self._preset = PresetController(self)
        self._lyrics = LyricsController(self)

    def is_osd_visible(self):
        return getattr(self.window, '_osd_visible', False)


    def show_video_context_menu(self, pos):
        return self._context_menu.show_video_context_menu(pos)

    def take_screenshot(self):
        return self._context_menu.take_screenshot()

    def _take_screenshot(self):
        return self._context_menu._take_screenshot()

    def _populate_audio_menu(self, menu):
        return self._context_menu._populate_audio_menu(menu)

    def _on_audio_track_selected(self, track_id, label, actions):
        return self._context_menu._on_audio_track_selected(track_id, label, actions)

    def _populate_subtitle_menu(self, menu):
        return self._context_menu._populate_subtitle_menu(menu)

    def _on_sub_track_selected(self, track_id, label, actions):
        return self._context_menu._on_sub_track_selected(track_id, label, actions)

    def _try_fallback_track(self, pc, track_type, failed_id):
        return self._context_menu._try_fallback_track(pc, track_type, failed_id)

    def _menu_anchor(self, attr):
        return self._context_menu._menu_anchor(attr)

    def _exec_menu_upward(self, menu, btn):
        return self._context_menu._exec_menu_upward(menu, btn)

    def show_audio_track_menu(self):
        return self._context_menu.show_audio_track_menu()

    def show_sub_track_menu(self):
        return self._context_menu.show_sub_track_menu()

    def show_speed_menu(self):
        return self._context_menu.show_speed_menu()

    def show_aspect_menu(self):
        return self._context_menu.show_aspect_menu()

    def _load_external_subtitle(self):
        return self._context_menu._load_external_subtitle()

    def _show_subtitle_style_dialog(self):
        return self._context_menu._show_subtitle_style_dialog()

    def _download_subtitle(self):
        return self._context_menu._download_subtitle()

    def _toggle_sub_visibility(self):
        return self._context_menu._toggle_sub_visibility()

    def _adjust_sub_delay(self, delta):
        return self._context_menu._adjust_sub_delay(delta)

    def _adjust_sub_scale(self, delta):
        return self._context_menu._adjust_sub_scale(delta)

    def _set_sub_scale(self, scale):
        return self._context_menu._set_sub_scale(scale)

    def _adjust_sub_pos(self, delta):
        return self._context_menu._adjust_sub_pos(delta)

    def _set_sub_pos(self, pos):
        return self._context_menu._set_sub_pos(pos)

    def toggle_subtitle_visibility(self):
        return self._context_menu.toggle_subtitle_visibility()

    def adjust_subtitle_delay(self, delta):
        return self._context_menu.adjust_subtitle_delay(delta)

    def adjust_subtitle_scale(self, delta):
        return self._context_menu.adjust_subtitle_scale(delta)

    def _show_video_eq_dialog(self):
        return self._context_menu._show_video_eq_dialog()

    def adjust_video_eq(self, key, delta):
        return self._context_menu.adjust_video_eq(key, delta)

    def cycle_video_rotate(self, step):
        return self._context_menu.cycle_video_rotate(step)

    def toggle_video_flip(self):
        return self._context_menu.toggle_video_flip()

    def apply_video_eq_on_load(self):
        return self._context_menu.apply_video_eq_on_load()

    def set_motion_compensation(self, strength, target_fps):
        return self._context_menu.set_motion_compensation(strength, target_fps)

    def set_super_resolution(self, scale_algo, detail_enhance):
        return self._context_menu.set_super_resolution(scale_algo, detail_enhance)

    def set_user_shader(self, preset):
        return self._context_menu.set_user_shader(preset)

    def apply_smart_preset(self, preset_name):
        return self._preset.apply_smart_preset(preset_name)

    def toggle_scene_detect(self, enabled):
        return self._context_menu.toggle_scene_detect(enabled)

    def _on_scene_changed(self, params, scene_type):
        return self._context_menu._on_scene_changed(params, scene_type)

    def _apply_scene_params(self, params, scene_type):
        return self._context_menu._apply_scene_params(params, scene_type)

    def get_scene_detect_status(self):
        return self._context_menu.get_scene_detect_status()

    def list_custom_presets(self):
        return self._preset.list_custom_presets()

    def save_custom_preset(self, name, settings, description):
        return self._preset.save_custom_preset(name, settings, description)

    def delete_custom_preset(self, name):
        return self._preset.delete_custom_preset(name)

    def apply_custom_preset(self, name):
        return self._preset.apply_custom_preset(name)

    def bind_channel_preset(self, channel_name, preset_name):
        return self._preset.bind_channel_preset(channel_name, preset_name)

    def get_channel_preset(self, channel_name):
        return self._preset.get_channel_preset(channel_name)

    def export_presets(self, file_path):
        return self._preset.export_presets(file_path)

    def import_presets(self, file_path, overwrite):
        return self._preset.import_presets(file_path, overwrite)

    def _show_audio_eq_dialog(self):
        return self._context_menu._show_audio_eq_dialog()

    def adjust_audio_delay(self, delta):
        return self._context_menu.adjust_audio_delay(delta)

    def adjust_audio_pitch(self, delta):
        return self._context_menu.adjust_audio_pitch(delta)

    def set_channel_volumes(self, volumes):
        return self._context_menu.set_channel_volumes(volumes)

    def get_audio_channel_info(self):
        return self._context_menu.get_audio_channel_info()

    def start_channel_monitor(self):
        return self._context_menu.start_channel_monitor()

    def stop_channel_monitor(self):
        return self._context_menu.stop_channel_monitor()

    def get_channel_levels(self):
        return self._context_menu.get_channel_levels()

    def apply_audio_eq_on_load(self):
        return self._context_menu.apply_audio_eq_on_load()

    def _show_playback_queue_dialog(self):
        return self._context_menu._show_playback_queue_dialog()

    def _show_resume_list_dialog(self):
        return self._context_menu._show_resume_list_dialog()

    def _show_network_enhance_dialog(self):
        return self._context_menu._show_network_enhance_dialog()

    def _show_burst_screenshot_dialog(self):
        return self._context_menu._show_burst_screenshot_dialog()

    def _show_bookmark_dialog(self):
        return self._context_menu._show_bookmark_dialog()

    def _show_av_sync_dialog(self):
        return self._context_menu._show_av_sync_dialog()

    def _show_stream_quality_dialog(self):
        return self._context_menu._show_stream_quality_dialog()

    def _show_media_properties_dialog(self):
        return self._context_menu._show_media_properties_dialog()

    def _show_3d_dialog(self):
        return self._context_menu._show_3d_dialog()

    def _populate_hdr_submenu(self, parent_menu):
        return self._context_menu._populate_hdr_submenu(parent_menu)

    def _set_hdr_mode(self, mode):
        return self._context_menu._set_hdr_mode(mode)

    def add_bookmark_now(self):
        return self._context_menu.add_bookmark_now()

    def chapter_next(self):
        return self._context_menu.chapter_next()

    def chapter_prev(self):
        return self._context_menu.chapter_prev()

    def get_queue_controller(self):
        return self._context_menu.get_queue_controller()

    def cycle_queue_mode(self):
        return self._context_menu.cycle_queue_mode()

    def toggle_shuffle(self):
        return self._context_menu.toggle_shuffle()

    def play_next_file(self):
        return self._context_menu.play_next_file()

    def play_previous_file(self):
        return self._context_menu.play_previous_file()

    def ab_loop_set_a(self):
        return self._context_menu.ab_loop_set_a()

    def ab_loop_set_b(self):
        return self._context_menu.ab_loop_set_b()

    def ab_loop_clear(self):
        return self._context_menu.ab_loop_clear()

    def frame_step(self):
        return self._context_menu.frame_step()

    def frame_back_step(self):
        return self._context_menu.frame_back_step()

    def adjust_speed(self, delta):
        return self._context_menu.adjust_speed(delta)

    def cycle_speed(self):
        return self._context_menu.cycle_speed()

    def cycle_aspect_ratio(self):
        return self._context_menu.cycle_aspect_ratio()

    def _save_aspect_ratio(self, ratio):
        return self._context_menu._save_aspect_ratio(ratio)

    def restore_aspect_ratio(self):
        return self._context_menu.restore_aspect_ratio()

    def _set_speed(self, speed):
        return self._context_menu._set_speed(speed)

    def _set_volume(self, volume):
        return self._context_menu._set_volume(volume)

    def _set_aspect(self, ratio):
        return self._context_menu._set_aspect(ratio)

    def update_catchup_indicator(self):
        return self._context_menu.update_catchup_indicator()

    def _is_audio_only(self):
        return self._context_menu._is_audio_only()

    def _populate_visual_menu(self, menu):
        return self._context_menu._populate_visual_menu(menu)

    def _set_visual_style(self, style_key):
        return self._context_menu._set_visual_style(style_key)

    def _populate_lyrics_menu(self, menu):
        return self._lyrics._populate_lyrics_menu(menu)

    def _toggle_lyrics(self, show):
        return self._lyrics._toggle_lyrics(show)

    def _create_lyrics_widget(self):
        return self._lyrics._create_lyrics_widget()

    def _refresh_lyrics(self):
        return self._lyrics._refresh_lyrics()

    def _load_external_lyrics(self):
        return self._lyrics._load_external_lyrics()

