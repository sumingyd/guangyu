import json
import os
import threading
from datetime import datetime
from typing import Dict, Any, List
from core.log_manager import global_logger as logger
from utils.platform_utils import get_android_data_dir


class FavoritesService:
    MAX_HISTORY = 50
    HISTORY_KEY = 'url'
    FAVORITES_FILE = 'favorites.json'

    def __init__(self, config_manager=None):
        self._config = config_manager
        self._lock = threading.RLock()
        self._favorites: List[Dict[str, Any]] = []
        self._play_history: List[Dict[str, Any]] = []
        self._favorites_url_set: set = set()
        self._data_dir = self._get_data_dir()
        self._load_from_config()

    def _get_data_dir(self):
        import sys
        from utils.app_paths import get_data_dir
        # Android：新布局的 data/ 子目录（不再直接落在根目录）
        if get_android_data_dir():
            return get_data_dir()
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(current_dir)

    def _load_from_config(self):
        with self._lock:
            if not self._config:
                return
            fav_count = int(self._config.get_value('Favorites', 'count', '0') or '0')
            for i in range(fav_count):
                raw = self._config.get_value('Favorites', f'ch_{i}', '')
                if raw:
                    try:
                        ch = json.loads(raw)
                        self._favorites.append(ch)
                        url = ch.get('url', '')
                        if url:
                            self._favorites_url_set.add(url)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"跳过损坏的收藏条目#{i}: {e}")

            hist_count = int(self._config.get_value('PlayHistory', 'count', '0') or '0')
            for i in range(hist_count):
                raw = self._config.get_value('PlayHistory', f'ch_{i}', '')
                if raw:
                    try:
                        ch = json.loads(raw)
                        self._play_history.append(ch)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"跳过损坏的历史条目#{i}: {e}")

    def _save_favorites_to_config(self):
        if not self._config:
            return
        with self._lock:
            try:
                old_count = int(self._config.get_value('Favorites', 'count', '0') or '0')
                self._config.set_value('Favorites', 'count', str(len(self._favorites)))
                for i, ch in enumerate(self._favorites):
                    self._config.set_value('Favorites', f'ch_{i}', json.dumps(ch, ensure_ascii=False))
                for i in range(len(self._favorites), old_count + 1):
                    self._config.remove_option('Favorites', f'ch_{i}')
                self._config.save_config()
            except Exception as e:
                logger.error(f"保存收藏失败: {e}")

    def _save_history_to_config(self):
        if not self._config:
            return
        with self._lock:
            try:
                old_count = int(self._config.get_value('PlayHistory', 'count', '0') or '0')
                self._config.set_value('PlayHistory', 'count', str(len(self._play_history)))
                for i, ch in enumerate(self._play_history):
                    self._config.set_value('PlayHistory', f'ch_{i}', json.dumps(ch, ensure_ascii=False))
                for i in range(len(self._play_history), old_count + 1):
                    self._config.remove_option('PlayHistory', f'ch_{i}')
                self._config.save_config()
            except Exception as e:
                logger.error(f"保存历史失败: {e}")

    @staticmethod
    def _channel_key(channel: Dict[str, Any]) -> str:
        return channel.get('url', '')

    def is_favorite(self, channel: Dict[str, Any]) -> bool:
        with self._lock:
            return self._channel_key(channel) in self._favorites_url_set

    def toggle_favorite(self, channel: Dict[str, Any]) -> bool:
        with self._lock:
            key = self._channel_key(channel)
            if key in self._favorites_url_set:
                self._favorites = [f for f in self._favorites if f.get('url', '') != key]
                self._favorites_url_set.discard(key)
                self._save_favorites_to_config()
                return False
            else:
                entry = {
                    'name': channel.get('name', ''),
                    'url': key,
                    'logo': channel.get('logo', '') or channel.get('logo_url', ''),
                    'group': channel.get('group', ''),
                    'tvg_id': channel.get('tvg_id', ''),
                }
                self._favorites.append(entry)
                self._favorites_url_set.add(key)
                self._save_favorites_to_config()
                return True

    def add_to_favorites(self, channel: Dict[str, Any]):
        with self._lock:
            key = self._channel_key(channel)
            if key not in self._favorites_url_set:
                entry = {
                    'name': channel.get('name', ''),
                    'url': key,
                    'logo': channel.get('logo', '') or channel.get('logo_url', ''),
                    'group': channel.get('group', ''),
                    'tvg_id': channel.get('tvg_id', ''),
                }
                self._favorites.append(entry)
                self._favorites_url_set.add(key)
                self._save_favorites_to_config()

    def remove_from_favorites(self, channel: Dict[str, Any]):
        with self._lock:
            key = self._channel_key(channel)
            if key in self._favorites_url_set:
                self._favorites = [f for f in self._favorites if f.get('url', '') != key]
                self._favorites_url_set.discard(key)
                self._save_favorites_to_config()

    def get_favorites(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._favorites)

    def record_play(self, channel: Dict[str, Any]):
        with self._lock:
            key = self._channel_key(channel)
            if not key:
                return
            self._play_history = [h for h in self._play_history if h.get('url', '') != key]
            entry = {
                'name': channel.get('name', ''),
                'url': key,
                'logo': channel.get('logo', '') or channel.get('logo_url', ''),
                'group': channel.get('group', ''),
                'tvg_id': channel.get('tvg_id', ''),
                'play_time': datetime.now().isoformat(),
            }
            self._play_history.insert(0, entry)
            if len(self._play_history) > self.MAX_HISTORY:
                self._play_history = self._play_history[:self.MAX_HISTORY]
            self._save_history_to_config()

    def get_play_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._play_history)

    def clear_play_history(self):
        with self._lock:
            self._play_history.clear()
            self._save_history_to_config()

    def remove_from_history(self, url: str):
        with self._lock:
            self._play_history = [h for h in self._play_history if h.get('url', '') != url]
            self._save_history_to_config()

    def clear_favorites(self):
        with self._lock:
            self._favorites.clear()
            self._favorites_url_set.clear()
            self._save_favorites_to_config()