import threading
from typing import overload
from core.log_manager import LogManager
from PySide6.QtCore import QObject, Signal
from PySide6 import QtWidgets
from utils.singleton import Singleton

logger = LogManager()

def _load_builtin_translations():
    """从 i18n/*.json 加载翻译数据，失败时回退到空字典。"""
    import json
    import os
    result = {}
    i18n_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'i18n')
    for lang in ('zh', 'en'):
        path = os.path.join(i18n_dir, f'{lang}.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                result[lang] = json.load(f)
        except Exception as e:
            logger.warning(f"加载翻译文件失败 {path}: {e}")
            result[lang] = {}
    return result


_builtin_translations_cache = None


def _get_builtin_translations():
    global _builtin_translations_cache
    if _builtin_translations_cache is None:
        _builtin_translations_cache = _load_builtin_translations()
    return _builtin_translations_cache


BUILTIN_TRANSLATIONS = _get_builtin_translations



class _LanguageSignalHelper(QObject):
    language_changed = Signal()


class LanguageManager(Singleton):

    def __new__(cls, *args, **kwargs) -> 'LanguageManager':
        return super().__new__(cls, *args, **kwargs)

    def __init__(self):
        if self._initialized:
            return
        self._signal_helper = _LanguageSignalHelper()
        self._lock = threading.Lock()
        self.current_language = 'zh'
        self.translations = {}
        self.available_languages = {}
        self._initialized = True

    @property
    def language_changed(self):
        return self._signal_helper.language_changed

    def load_available_languages(self):
        if hasattr(self, '_languages_loaded') and self._languages_loaded:
            return self.available_languages

        self.available_languages = {}
        for lang_code, data in BUILTIN_TRANSLATIONS().items():
            self.available_languages[lang_code] = {
                'file': f'builtin:{lang_code}',
                'display_name': data.get('language_name', lang_code),
                'data': data
            }

        loaded_languages = list(self.available_languages.keys())
        logger.debug(f"成功加载 {len(loaded_languages)} 种内置语言: {', '.join(loaded_languages)}")

        self._languages_loaded = True
        return self.available_languages

    def set_language(self, lang_code):
        with self._lock:
            if lang_code in self.available_languages:
                self.current_language = lang_code
                self.translations = self.available_languages[lang_code]['data']
            else:
                logger.warning(f"语言 {lang_code} 不可用")
                return False
        self.language_changed.emit()
        return True

    def get_translation(self, key, default=None):
        with self._lock:
            return self.translations.get(key, default)

    @overload
    def tr(self, key: str, default: str) -> str: ...

    @overload
    def tr(self, key: str, default: None = None) -> str | None: ...

    def tr(self, key, default=None):
        return self.get_translation(key, default)

    def get_language_list(self):
        languages = []
        for lang_code, lang_info in self.available_languages.items():
            languages.append({
                'code': lang_code,
                'name': lang_info['display_name'],
                'file': lang_info['file']
            })
        return languages

    def update_ui_texts(self, main_window):
        if not self.translations:
            return

        try:
            from core.version import CURRENT_VERSION
            version = CURRENT_VERSION
            new_title = f"{self.tr('app_title', 'ISEP')} v{version}"
            main_window.setWindowTitle(new_title)
            # 同步更新自定义标题栏标签（无边框窗口 setWindowTitle 不可见）
            if hasattr(main_window, '_title_label') and main_window._title_label:
                main_window._title_label.setText(new_title)

            if hasattr(main_window, 'epg_title'):
                main_window.epg_title.setText(self.tr('epg_title', 'Program Guide'))
            if hasattr(main_window, 'playlist_title'):
                main_window.playlist_title.setText(self.tr('playlist_title', 'Playlist'))
            if hasattr(main_window, 'epg_date_label'):
                current_text = main_window.epg_date_label.text()
                zh_day_map = {'今天': 'today', '昨天': 'yesterday', '明天': 'tomorrow'}
                en_day_map = {'Today': 'today', 'Yesterday': 'yesterday', 'Tomorrow': 'tomorrow'}
                day_key = zh_day_map.get(current_text) or en_day_map.get(current_text)
                if day_key:
                    main_window.epg_date_label.setText(self.tr(day_key, current_text))
            if hasattr(main_window, 'epg_empty_label'):
                if not getattr(main_window, 'current_channel', None):
                    main_window.epg_empty_label.setText(self.tr('no_epg_open_playlist', '暂无节目信息，点击打开或导入订阅'))
                else:
                    main_window.epg_empty_label.setText(self.tr('no_epg_data', 'No program information'))

            if hasattr(main_window, 'playlist_tab'):
                main_window.playlist_tab.setTabText(0, self.tr('subscription_tab', 'Subscription'))
                main_window.playlist_tab.setTabText(1, self.tr('local_tab', 'Local'))
            # 常驻可见的四个列表切换按钮（QTabBar 已隐藏，仅这些按钮上屏）
            tab_btns = getattr(main_window, '_playlist_tab_btns', None)
            if tab_btns:
                tab_keys = ('subscription_tab', 'local_tab', 'favorites_tab', 'history_tab')
                for i, btn in enumerate(tab_btns):
                    if i < len(tab_keys):
                        text = self.tr(tab_keys[i], btn.text())
                        btn.setText(text)
                        btn.setToolTip(text)
            # 底部"更多"菜单（创建时已记录 (key, fallback)）
            more_menu = getattr(main_window, '_more_menu', None)
            if more_menu:
                for act in more_menu.actions():
                    data = act.data()
                    if isinstance(data, (tuple, list)) and len(data) == 2:
                        act.setText(self.tr(data[0], data[1]))
            # 自定义标题栏按钮 tooltip
            window_ctrl = getattr(main_window, 'window_ctrl', None)
            if window_ctrl:
                for attr, key in (
                    ('_stay_on_top_btn', 'tooltip_stay_on_top'),
                    ('_minimize_btn', 'tooltip_minimize'),
                    ('_maximize_btn', 'tooltip_maximize'),
                    ('_close_btn', 'tooltip_close'),
                ):
                    btn = getattr(window_ctrl, attr, None)
                    if btn:
                        btn.setToolTip(self.tr(key, btn.toolTip()))
            for empty_attr in ['sub_empty_label', 'local_empty_label']:
                el = getattr(main_window, empty_attr, None)
                if el:
                    el.setText(self.tr('no_channels', 'No channels'))

            # 分组下拉框首项"全部频道"需随语言刷新（复用已有的重建逻辑，
            # 缓存列表中仍为旧语言文本，会触发重建并保留真实分组）
            update_groups = getattr(main_window, '_update_groups_for', None)
            if callable(update_groups):
                for source in ('subscription', 'local'):
                    try:
                        update_groups(source)
                    except Exception as e:
                        logger.debug(f"刷新分组下拉框失败 ({source}): {e}")

            if hasattr(main_window, 'video_info'):
                main_window.video_info.setText(self.tr('not_playing', 'Not playing'))
            if hasattr(main_window, 'audio_info'):
                main_window.audio_info.setText("--")
            if hasattr(main_window, 'network_info'):
                main_window.network_info.setText("--")
            if hasattr(main_window, 'hdr_badge'):
                main_window.hdr_badge.hide()

            if hasattr(main_window, 'channel_name'):
                main_window.channel_name.setText(self.tr('no_channel_selected', 'No channel selected'))
            if hasattr(main_window, 'current_program'):
                main_window.current_program.setText("")
            if hasattr(main_window, 'program_desc'):
                main_window.program_desc.setText(self.tr('open_playlist_or_import', 'Open a playlist file or import channels to start watching'))
            if hasattr(main_window, 'remain_label'):
                main_window.remain_label.setText(self.tr('waiting_to_play', 'Waiting to play...'))
            if hasattr(main_window, '_set_exit_catchup_visible'):
                main_window._set_exit_catchup_visible(
                    getattr(main_window, '_more_catchup_action', None) is not None
                    and main_window._more_catchup_action.isVisible(),
                    self.tr('exit_catchup', '⏪ Exit Catchup'),
                )

            self._update_dialogs(main_window)

            logger.info(f"UI文本已更新到语言: {self.current_language}")

        except Exception as e:
            logger.error(f"更新UI文本失败: {str(e)}")

    def _update_dialogs(self, main_window):
        try:
            for widget in main_window.findChildren(QtWidgets.QDialog):
                if hasattr(widget, 'update_ui_texts'):
                    widget.update_ui_texts()
            # 扫描整理窗口是无 parent 的独立顶层窗口，不在 findChildren 结果里
            scan_dialog = getattr(main_window, '_scan_dialog', None)
            if scan_dialog is not None and hasattr(scan_dialog, 'update_ui_texts'):
                scan_dialog.update_ui_texts()
        except Exception as e:
            logger.debug(f"更新对话框失败: {e}")
