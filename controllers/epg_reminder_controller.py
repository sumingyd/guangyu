from PySide6.QtWidgets import QSystemTrayIcon
from typing import Dict, Any, List
from core.log_manager import global_logger as logger
from controllers.main_window_protocol import UiProtocol
from ui.dialogs.reminder_popup import ReminderPopup


class EpgReminderController:
    def __init__(self, main_window: UiProtocol):
        self.window: UiProtocol = main_window
        self._service = None
        self._active_popups: List[ReminderPopup] = []

    def init_service(self, config_manager):
        from services.epg_reminder_service import EpgReminderService
        self._service = EpgReminderService(config_manager)
        self._service.set_callback(self._on_reminder_triggered)
        self._service.start_check_timer()

    @property
    def service(self):
        return self._service

    def add_reminder(self, channel_name: str, program_title: str,
                     start_time: str, end_time: str,
                     tvg_id: str = '', auto_switch: bool = False) -> bool:
        if not self._service:
            return False
        return self._service.add_reminder(channel_name, program_title, start_time, end_time, tvg_id, auto_switch)

    def remove_reminder(self, reminder_id: str):
        if self._service:
            self._service.remove_reminder(reminder_id)

    def has_reminder(self, channel_name: str, program_title: str, start_time: str) -> bool:
        if not self._service:
            return False
        return self._service.has_reminder(channel_name, program_title, start_time)

    def get_reminders(self) -> List[Dict[str, Any]]:
        if self._service:
            return self._service.get_reminders()
        return []

    def _on_reminder_triggered(self, reminder: Dict[str, Any]):
        w = self.window
        tr = w.language_manager.tr
        channel_name = reminder.get('channel_name', '')
        program_title = reminder.get('program_title', '')
        start_time = reminder.get('start_time', '')
        auto_switch = reminder.get('auto_switch', False)

        if auto_switch:
            self._switch_to_channel(channel_name, reminder.get('tvg_id', ''))
            msg = tr('reminder_auto_switch', '提醒: 即将开播 {title}，已自动切换到 {channel}')
            w.status_bar_show_message(msg.format(title=program_title, channel=channel_name))

        msg = tr('reminder_notify', '提醒: {channel} 即将开播 {title}')
        w.status_bar_show_message(msg.format(channel=channel_name, title=program_title))
        self._show_reminder_popup(channel_name, program_title, start_time, auto_switch)

    def _switch_to_channel(self, channel_name: str, tvg_id: str = ''):
        w = self.window
        channels = (getattr(w, '_sub_channels', None) or []) + (getattr(w, '_local_channels', None) or [])
        for ch in channels:
            if ch.get('name', '') == channel_name or (tvg_id and ch.get('tvg_id', '') == tvg_id):
                w.current_channel = ch
                w.update_channel_info_on_selection()
                w.play_channel(ch)
                return

    def _show_reminder_popup(self, channel_name: str, program_title: str,
                             start_time: str = '', auto_switch: bool = False):
        w = self.window
        try:
            tvg_id = ''
            reminders = self.get_reminders()
            for r in reminders:
                if r.get('channel_name') == channel_name and r.get('program_title') == program_title and r.get('start_time') == start_time:
                    tvg_id = r.get('tvg_id', '')
                    break
            switch_cb = lambda cn=channel_name, tid=tvg_id: self._switch_to_channel(cn, tid)

            def snooze_cb(cn=channel_name, pt=program_title, st=start_time, auto=auto_switch):
                from PySide6.QtCore import QTimer
                QTimer.singleShot(
                    5 * 60 * 1000,
                    lambda: self._show_reminder_popup(cn, pt, st, auto))

            def dismiss_cb(cn=channel_name, pt=program_title, st=start_time):
                self.remove_reminder(f"{cn}_{pt}_{st}")

            popup = ReminderPopup(
                w, channel_name, program_title,
                start_time_str=start_time,
                auto_switch=auto_switch,
                on_switch_callback=switch_cb,
                on_snooze_callback=snooze_cb,
                on_dismiss_callback=dismiss_cb
            )
            popup.show()
            self._active_popups.append(popup)
            popup.destroyed.connect(lambda obj=None, p_id=id(popup): self._on_popup_destroyed(p_id))
        except Exception as e:
            logger.debug(f"提醒弹窗显示失败: {e}")
            self._show_reminder_notification(channel_name, program_title)

    def _on_popup_destroyed(self, popup_id):
        self._active_popups = [p for p in self._active_popups if id(p) != popup_id]

    def get_active_popups(self) -> list:
        return list(self._active_popups)

    def _show_reminder_notification(self, channel_name: str, program_title: str):
        w = self.window
        try:
            tray = getattr(w, '_system_tray', None)
            if tray and tray.isSystemTrayAvailable():
                tr = w.language_manager.tr
                msg = tr('reminder_tray_msg', '{channel}: {title} 即将开播')
                tray.showMessage(
                    tr('reminder_tray_title', 'EPG节目提醒'),
                    msg.format(channel=channel_name, title=program_title),
                    QSystemTrayIcon.MessageIcon.Information,
                    5000
                )
        except Exception as e:
            logger.debug(f"系统托盘通知失败: {e}")

    def toggle_reminder_for_program(self, channel_name: str, program_title: str,
                                    start_time: str, end_time: str,
                                    tvg_id: str = ''):
        if not self._service:
            return
        if self.has_reminder(channel_name, program_title, start_time):
            reminder_id = f"{channel_name}_{program_title}_{start_time}"
            self._service.remove_reminder(reminder_id)
            tr = self.window.language_manager.tr
            self.window.status_bar_show_message(tr('reminder_removed', '已取消提醒'))
        else:
            added = self.add_reminder(channel_name, program_title, start_time, end_time, tvg_id)
            tr = self.window.language_manager.tr
            if added:
                self.window.status_bar_show_message(tr('reminder_added', '已设置提醒'))
            else:
                self.window.status_bar_show_message(
                    tr('reminder_program_started', '节目已开始，无法设置提醒'))
