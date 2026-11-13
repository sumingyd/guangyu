from PySide6.QtCore import QTimer
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from core.log_manager import global_logger as logger


class EpgReminderService:
    CHECK_INTERVAL_SEC = 10
    EARLY_NOTIFY_SEC = 60

    def __init__(self, config_manager=None):
        self._config = config_manager
        self._lock = threading.RLock()
        self._reminders: List[Dict[str, Any]] = []
        self._notified_ids: set = set()
        self._timer = None
        self._on_reminder_callback: Optional[Callable] = None
        self._load_from_config()

    def _load_from_config(self):
        with self._lock:
            if not self._config:
                return
            try:
                count = int(self._config.get_value('EpgReminders', 'count', '0') or '0')
                for i in range(count):
                    raw = self._config.get_value('EpgReminders', f'r_{i}', '')
                    if raw:
                        self._reminders.append(json.loads(raw))
            except Exception as e:
                logger.error(f"加载EPG提醒失败: {e}")

    def _save_to_config(self):
        if not self._config:
            return
        with self._lock:
            try:
                old_count = int(self._config.get_value('EpgReminders', 'count', '0') or '0')
                self._config.set_value('EpgReminders', 'count', str(len(self._reminders)))
                for i, r in enumerate(self._reminders):
                    self._config.set_value('EpgReminders', f'r_{i}', json.dumps(r, ensure_ascii=False))
                for i in range(len(self._reminders), old_count + 1):
                    try:
                        self._config.remove_option('EpgReminders', f'r_{i}')
                    except Exception as e:
                        logger.debug(f"_save_to_config: {e}")
                self._config.save_config()
            except Exception as e:
                logger.error(f"保存EPG提醒失败: {e}")

    def set_callback(self, callback: Callable):
        self._on_reminder_callback = callback

    def add_reminder(self, channel_name: str, program_title: str,
                     start_time: str, end_time: str,
                     tvg_id: str = '', auto_switch: bool = False) -> bool:
        reminder_id = f"{channel_name}_{program_title}_{start_time}"
        # 已经开始播出的节目再加提醒永远不会触发（检查条件是 0 < diff <= 60），
        # 直接拒绝并让调用方给出明确提示，避免状态栏显示“已设置提醒”却毫无反应
        try:
            if datetime.fromisoformat(start_time) <= datetime.now():
                logger.info(f"忽略已开播节目的提醒: {channel_name} - {program_title} @ {start_time}")
                return False
        except (ValueError, TypeError):
            logger.warning(f"提醒时间格式非法，忽略: {channel_name} - {program_title} @ {start_time}")
            return False
        with self._lock:
            for r in self._reminders:
                if r.get('id') == reminder_id:
                    return False
            reminder = {
                'id': reminder_id,
                'channel_name': channel_name,
                'program_title': program_title,
                'start_time': start_time,
                'end_time': end_time,
                'tvg_id': tvg_id,
                'auto_switch': auto_switch,
                'created_at': datetime.now().isoformat(),
            }
            self._reminders.append(reminder)
            self._save_to_config()
            logger.info(f"添加EPG提醒: {channel_name} - {program_title} @ {start_time}")
            return True

    def remove_reminder(self, reminder_id: str):
        with self._lock:
            self._reminders = [r for r in self._reminders if r.get('id') != reminder_id]
            self._notified_ids.discard(reminder_id)
            self._save_to_config()

    def get_reminders(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._reminders)

    def has_reminder(self, channel_name: str, program_title: str, start_time: str) -> bool:
        reminder_id = f"{channel_name}_{program_title}_{start_time}"
        with self._lock:
            return any(r.get('id') == reminder_id for r in self._reminders)

    def start_check_timer(self):
        if self._timer is not None:
            return
        self._timer = QTimer()
        self._timer.setInterval(self.CHECK_INTERVAL_SEC * 1000)
        self._timer.timeout.connect(self._check_reminders)
        self._timer.start()
        logger.debug("EPG提醒定时器已启动")

    def stop_check_timer(self):
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    def _check_reminders(self):
        now = datetime.now()
        triggered = []
        with self._lock:
            for reminder in self._reminders:
                try:
                    start_time = datetime.fromisoformat(reminder['start_time'])
                    diff = (start_time - now).total_seconds()
                    rid = reminder['id']
                    if 0 < diff <= self.EARLY_NOTIFY_SEC and rid not in self._notified_ids:
                        self._notified_ids.add(rid)
                        triggered.append(reminder)
                    elif diff < -3600:
                        self._notified_ids.discard(rid)
                except Exception as e:
                    logger.debug(f"检查提醒异常: {e}")
        self.cleanup_expired()
        auto_switched = False
        for reminder in triggered:
            if reminder.get('auto_switch') and not auto_switched:
                auto_switched = True
                if self._on_reminder_callback:
                    self._on_reminder_callback(reminder)
            else:
                reminder_no_switch = dict(reminder)
                reminder_no_switch['auto_switch'] = False
                if self._on_reminder_callback:
                    self._on_reminder_callback(reminder_no_switch)

    def cleanup_expired(self):
        now = datetime.now()
        with self._lock:
            before = len(self._reminders)
            new_reminders = []
            for r in self._reminders:
                try:
                    end = datetime.fromisoformat(r.get('end_time', r.get('start_time', '')))
                    if end > now - timedelta(hours=1):
                        new_reminders.append(r)
                except (ValueError, TypeError):
                    new_reminders.append(r)
            self._reminders = new_reminders
            if len(self._reminders) != before:
                self._save_to_config()
