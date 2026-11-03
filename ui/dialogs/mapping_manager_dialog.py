from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from core.log_manager import LogManager
from models.channel_mappings import mapping_manager
from utils.error_handler import show_error, show_warning, show_info, show_confirm
from ..floating_dialog import FloatingDialog


class _UpdateCheckWorker(QThread):
    """后台线程：执行远程映射更新检查，避免阻塞 UI 线程"""
    finished = Signal(dict)  # 检查完成，携带 status dict

    def run(self):
        try:
            status = mapping_manager.check_remote_update_status()
        except Exception as e:
            status = {'has_update': False, 'last_cache_time': 0,
                      'local_count': 0, 'remote_count': 0, 'error': str(e)}
        self.finished.emit(status)


class _RefreshCacheWorker(QThread):
    """后台线程：执行远程缓存刷新，避免阻塞 UI 线程"""
    finished = Signal(bool, str)  # (success, error_message)

    def run(self):
        try:
            mapping_manager.refresh_cache()
            self.finished.emit(True, '')
        except Exception as e:
            self.finished.emit(False, str(e))


class MappingManagerDialog(FloatingDialog):
    """频道映射管理器对话框"""

    def __init__(self, parent=None):
        super().__init__(parent, stay_on_top=False)
        self.logger = LogManager()
        self._update_check_worker = None
        self._refresh_worker = None
        from ..styles import AppStyles
        colors = AppStyles._get_colors()
        if AppStyles._visual_style == 'frosted':
            self.opacity = int(colors.get('frosted_opacity', 0.8) * 255)
        else:
            self.opacity = colors.get('window_opacity', 220)

        self.language_manager = getattr(parent, 'language_manager', None)
        if not self.language_manager:
            from core.language_manager import LanguageManager
            self.language_manager = LanguageManager()

        self.setWindowTitle(self.language_manager.tr('mapping_manager', 'Channel Mapping Manager'))
        self.setMinimumSize(600, 400)
        self.setup_ui()
        self.load_data()

        from ..theme_manager import get_theme_manager
        get_theme_manager().register_window(self)

    def closeEvent(self, event):
        for worker_attr in ('_update_check_worker', '_refresh_worker'):
            worker = getattr(self, worker_attr, None)
            if worker and worker.isRunning():
                worker.requestInterruption()
                worker.wait(3000)
            if worker:
                worker.deleteLater()
                setattr(self, worker_attr, None)
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)

    def _tr(self, key: str, fallback: str) -> str:
        v = self.language_manager.tr(key, fallback)
        return v if v else fallback

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        _ = self._tr

        from ui.styles import AppStyles
        self.setStyleSheet(AppStyles.dialog_style())

        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        text_color = colors.get('window_text')
        text_secondary = colors.get('player_panel_secondary')
        player_panel_hint = colors.get('player_panel_hint')

        info_box = QtWidgets.QFrame()
        r = AppStyles._get_style_border_radius()
        info_box.setStyleSheet(f"""
            QFrame {{
                background-color: {colors['alternate_base']};
                border-radius: {r}px;
                border: 1px solid {colors['mid']};
                padding: 4px;
            }}
            QLabel {{ color: {text_color}; border: none; background: transparent; }}
        """)
        info_layout = QtWidgets.QVBoxLayout(info_box)
        info_layout.setContentsMargins(16, 10, 16, 10)

        title_label = QtWidgets.QLabel(_('mapping_tip_title', 'Channel Name Mapping'))
        title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {text_color}; border: none; background: transparent;")
        info_layout.addWidget(title_label)

        tip_text = _('mapping_tip_desc',
            'Remote mapping automatically standardizes channel names.\n'
            'If the mapping file is updated, click the button below to refresh.')
        tip_label = QtWidgets.QLabel(tip_text)
        tip_label.setStyleSheet(f"color: {text_secondary}; border: none; background: transparent; line-height: 1.5;")
        tip_label.setWordWrap(True)
        info_layout.addWidget(tip_label)
        layout.addWidget(info_box)

        refresh_layout = QtWidgets.QHBoxLayout()
        refresh_layout.addStretch()

        self.refresh_cache_btn = QtWidgets.QPushButton(_('refresh_remote_mapping', 'Refresh Remote Mapping'))
        self.refresh_cache_btn.setStyleSheet(AppStyles.common_button_style())
        self.refresh_cache_btn.clicked.connect(self.refresh_cache)
        self.refresh_cache_btn.setToolTip(_('refresh_cache_tooltip', '刷新映射缓存'))
        refresh_layout.addWidget(self.refresh_cache_btn)
        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)

        self.update_status_label = QtWidgets.QLabel('')
        self.update_status_label.setStyleSheet(
            f"color: {text_secondary}; font-size: 11px; border: none; background: transparent; padding: 4px 8px;"
        )
        self.update_status_label.setWordWrap(True)
        layout.addWidget(self.update_status_label)
        layout.addSpacing(4)

        manual_group = QtWidgets.QGroupBox(_('manual_mapping_section', 'Manual Mapping (Advanced)'))
        manual_group.setStyleSheet(AppStyles.common_group_box_style())
        manual_layout = QtWidgets.QVBoxLayout(manual_group)
        manual_layout.setSpacing(8)

        hint_label = QtWidgets.QLabel(_('manual_mapping_hint',
            'Only needed when remote mapping cannot correctly identify a channel.'))
        hint_label.setStyleSheet(f"color: {player_panel_hint}; font-size: 11px; border: none; background: transparent;")
        hint_label.setWordWrap(True)
        manual_layout.addWidget(hint_label)

        search_row = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setStyleSheet(AppStyles.common_line_edit_style())
        self.search_input.setPlaceholderText(_('search_channel_name', 'Search channel name...'))
        self.search_input.textChanged.connect(self.filter_mappings)
        search_row.addWidget(self.search_input)

        self.search_options = QtWidgets.QComboBox()
        self.search_options.setStyleSheet(AppStyles.common_combo_box_style())
        self.search_options.currentTextChanged.connect(self.filter_mappings)
        self.search_options.addItems([
            _('search_all_fields', 'All Fields'),
            _('search_standard_name_only', 'Standard Name'),
            _('search_raw_name_only', 'Raw Name'),
            _('search_group_only', 'Group'),
        ])
        search_row.addWidget(self.search_options)
        manual_layout.addLayout(search_row)

        self.mapping_table = QtWidgets.QTableWidget()
        self.mapping_table.setStyleSheet(AppStyles.table_style())
        self.mapping_table.setColumnCount(5)
        self.mapping_table.setHorizontalHeaderLabels([
            _('serial_number', 'No.'),
            _('standard_name', 'Standard Name'),
            _('raw_name', 'Raw Name'),
            _('group', 'Group'),
            _('logo_address', 'Logo Address')
        ])
        # 列宽：序号固定窄列；标准/原始/分组可拖动调节；Logo 列伸缩兜底。
        # 初始宽度保证不横向滚动即可见前 4 列（序号/标准名称/原始名称/分组）
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.mapping_table.setColumnWidth(0, 44)
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.mapping_table.setColumnWidth(1, 150)
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.mapping_table.setColumnWidth(2, 180)
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.mapping_table.setColumnWidth(3, 120)
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        # 隐藏纵向行号表头：序号由第0列普通内容列承担，避免视觉上像表头
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.mapping_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapping_table.setMaximumHeight(200)
        manual_layout.addWidget(self.mapping_table)

        btn_row = QtWidgets.QHBoxLayout()
        self.add_mapping_btn = QtWidgets.QPushButton(_('add_mapping', 'Add'))
        self.add_mapping_btn.setStyleSheet(AppStyles.common_button_style())
        self.add_mapping_btn.clicked.connect(self.add_mapping)
        self.add_mapping_btn.setToolTip(_('add_mapping_tooltip', '添加自定义映射'))
        self.edit_mapping_btn = QtWidgets.QPushButton(_('edit_mapping', 'Edit'))
        self.edit_mapping_btn.setStyleSheet(AppStyles.common_button_style())
        self.edit_mapping_btn.clicked.connect(self.edit_mapping)
        self.edit_mapping_btn.setToolTip(_('edit_mapping_tooltip', '编辑选中映射'))
        self.delete_mapping_btn = QtWidgets.QPushButton(_('delete_mapping', 'Delete'))
        self.delete_mapping_btn.setStyleSheet(AppStyles.common_button_style())
        self.delete_mapping_btn.clicked.connect(self.delete_mapping)
        self.delete_mapping_btn.setToolTip(_('delete_mapping_tooltip', '删除选中映射'))
        btn_row.addWidget(self.add_mapping_btn)
        btn_row.addWidget(self.edit_mapping_btn)
        btn_row.addWidget(self.delete_mapping_btn)
        btn_row.addStretch()
        manual_layout.addLayout(btn_row)

        layout.addWidget(manual_group)

        bottom_row = QtWidgets.QHBoxLayout()
        self.export_mappings_btn = QtWidgets.QPushButton(_('export_user_mappings', 'Export'))
        self.export_mappings_btn.setStyleSheet(AppStyles.common_button_style())
        self.export_mappings_btn.clicked.connect(self.export_mappings)
        self.export_mappings_btn.setToolTip(_('export_mappings_tooltip', '导出映射到文件'))
        self.import_mappings_btn = QtWidgets.QPushButton(_('import_user_mappings', 'Import'))
        self.import_mappings_btn.setStyleSheet(AppStyles.common_button_style())
        self.import_mappings_btn.clicked.connect(self.import_mappings)
        self.import_mappings_btn.setToolTip(_('import_mappings_tooltip', '从文件导入映射'))
        bottom_row.addWidget(self.export_mappings_btn)
        bottom_row.addWidget(self.import_mappings_btn)
        bottom_row.addStretch()
        self.close_btn = QtWidgets.QPushButton(_('close', 'Close'))
        self.close_btn.setStyleSheet(AppStyles.common_button_style())
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setToolTip(_('close_tooltip', '关闭'))
        bottom_row.addWidget(self.close_btn)
        layout.addLayout(bottom_row)

    def load_data(self):
        self.load_user_mappings()
        self._check_update_status_async()

    def _check_update_status_async(self):
        """启动后台线程检查远程更新状态，不阻塞 UI"""
        _ = self._tr
        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        player_panel_hint = colors.get('player_panel_hint')
        self.update_status_label.setText(_('checking_update', 'Checking for updates...'))
        self.update_status_label.setStyleSheet(
            f"color: {player_panel_hint}; font-size: 11px; border: none; background: transparent; padding: 4px 8px;"
        )
        worker = _UpdateCheckWorker(self)
        worker.finished.connect(self._on_update_check_done)
        worker.finished.connect(worker.deleteLater)
        self._update_check_worker = worker
        worker.start()

    def _on_update_check_done(self, status: dict):
        """更新检查完成后在 UI 线程中更新标签"""
        _ = self._tr
        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        color = colors.get('success')
        if status.get('error'):
            text = _('update_check_failed', 'Update check failed: {}').format(status['error'])
            color = colors.get('error')
        elif status.get('has_update'):
            text = _('update_available',
                'New version available! Click the button above to refresh.')
            color = colors.get('warning')
        else:
            last_time = status.get('last_cache_time', 0)
            local_count = status.get('local_count', 0)
            if last_time > 0:
                from datetime import datetime
                dt = datetime.fromtimestamp(last_time)
                time_str = dt.strftime('%Y-%m-%d %H:%M')
                text = _('mapping_status_ok',
                    'Up to date | Loaded: {} mappings | Last: {}').format(local_count, time_str)
            else:
                text = _('mapping_status_no_cache',
                    'No cached data yet ({} mappings loaded)').format(local_count)
        self.update_status_label.setText(text)
        self.update_status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; border: none; background: transparent; padding: 4px 8px;"
        )
        self._update_check_worker = None

    def load_user_mappings(self):
        self.mapping_table.setRowCount(0)
        row = 0
        for standard_name, mapping_data in mapping_manager.user_mappings.items():
            for raw_name in mapping_data.get('raw_names', []):
                self.mapping_table.insertRow(row)
                serial_item = QtWidgets.QTableWidgetItem(str(row + 1))
                serial_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                serial_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.mapping_table.setItem(row, 0, serial_item)
                self.mapping_table.setItem(row, 1, QtWidgets.QTableWidgetItem(standard_name))
                self.mapping_table.setItem(row, 2, QtWidgets.QTableWidgetItem(raw_name))
                group = mapping_data.get('group_name', '')
                self.mapping_table.setItem(row, 3, QtWidgets.QTableWidgetItem(group))
                logo_url = mapping_data.get('logo_url', '')
                self.mapping_table.setItem(row, 4, QtWidgets.QTableWidgetItem(logo_url))
                row += 1
        self.mapping_table.resizeColumnsToContents()
        if row == 0:
            from ui.styles import AppStyles
            tr = self.language_manager.tr if self.language_manager else (lambda k, d='': d)
            self.mapping_table.setRowCount(1)
            self.mapping_table.setSpan(0, 0, 1, 5)
            empty_item = QtWidgets.QTableWidgetItem(tr('mapping_empty', '暂无自定义映射，请在下方添加'))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            colors = AppStyles._get_colors()
            empty_item.setForeground(QColor(colors.get('player_panel_secondary')))
            self.mapping_table.setItem(0, 0, empty_item)

    def filter_mappings(self):
        if not hasattr(self, 'mapping_table'):
            return
        search_text = self.search_input.text().lower()
        search_option = self.search_options.currentText()
        _ = self._tr
        option_map: dict[str, str] = {}
        option_map[_('search_all_fields', 'All Fields')] = 'all'
        option_map[_('search_standard_name_only', 'Standard Name')] = 'standard'
        option_map[_('search_raw_name_only', 'Raw Name')] = 'raw'
        option_map[_('search_group_only', 'Group')] = 'group'
        mode = option_map.get(search_option, 'all')

        col_map = {'all': None, 'standard': 1, 'raw': 2, 'group': 3}
        target_col = col_map.get(mode)

        for row in range(self.mapping_table.rowCount()):
            if not search_text:
                should_show = True
            elif target_col is None:
                should_show = any(
                    self.mapping_table.item(row, c) and search_text in self.mapping_table.item(row, c).text().lower()
                    for c in range(1, self.mapping_table.columnCount())
                )
            else:
                item = self.mapping_table.item(row, target_col)
                should_show = item and search_text in item.text().lower()
            self.mapping_table.setRowHidden(row, not should_show)

    def add_mapping(self):
        dialog = MappingEditDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            mapping_data = dialog.get_mapping_data()
            if mapping_data:
                mapping_manager.add_user_mapping(
                    mapping_data['raw_name'],
                    mapping_data['standard_name'],
                    mapping_data.get('logo_url'),
                    mapping_data.get('group_name')
                )
                self.load_user_mappings()
                self.logger.info(f"Added mapping: {mapping_data['raw_name']} -> {mapping_data['standard_name']}")

    def edit_mapping(self):
        selected_rows = self.mapping_table.selectionModel().selectedRows()
        if not selected_rows:
            show_warning(
                self._tr('warning', 'Warning'),
                self._tr('select_mapping_to_edit', 'Please select a mapping to edit'),
                parent=self
            )
            return
        row = selected_rows[0].row()
        standard_name = self.mapping_table.item(row, 1).text()
        raw_name = self.mapping_table.item(row, 2).text()
        group_name = self.mapping_table.item(row, 3).text()
        logo_url = self.mapping_table.item(row, 4).text()
        dialog = MappingEditDialog(self, standard_name, raw_name, group_name, logo_url)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            new_data = dialog.get_mapping_data()
            if new_data:
                mapping_manager.remove_user_mapping_entry(standard_name, raw_name)
                mapping_manager.add_user_mapping(
                    new_data['raw_name'],
                    new_data['standard_name'],
                    new_data.get('logo_url'),
                    new_data.get('group_name')
                )
                self.load_user_mappings()
                self.logger.info(f"Edited mapping: {raw_name} -> {new_data['standard_name']}")

    def delete_mapping(self):
        selected_rows = self.mapping_table.selectionModel().selectedRows()
        if not selected_rows:
            show_warning(
                self._tr('warning', 'Warning'),
                self._tr('select_mapping_to_delete', 'Please select a mapping to delete'),
                parent=self
            )
            return
        row = selected_rows[0].row()
        standard_name = self.mapping_table.item(row, 1).text()
        raw_name = self.mapping_table.item(row, 2).text()
        reply = show_confirm(
            self._tr('confirm_delete_mapping', 'Confirm Delete Mapping'),
            self._tr('delete_mapping_confirm', "Delete mapping '{}' → '{}'?").format(raw_name, standard_name),
            parent=self
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            mapping_manager.remove_user_mapping_entry(standard_name, raw_name)
            self.load_user_mappings()
            self.logger.info(f"Deleted mapping: {raw_name} -> {standard_name}")

    def refresh_cache(self):
        """异步刷新远程映射缓存，不阻塞 UI"""
        self.refresh_cache_btn.setEnabled(False)
        self.refresh_cache_btn.setText(self._tr('refreshing', 'Refreshing...'))
        worker = _RefreshCacheWorker(self)
        worker.finished.connect(self._on_refresh_done)
        worker.finished.connect(worker.deleteLater)
        self._refresh_worker = worker
        worker.start()

    def _on_refresh_done(self, success: bool, error_msg: str):
        """刷新完成后在 UI 线程中恢复按钮并更新状态"""
        self.refresh_cache_btn.setEnabled(True)
        self.refresh_cache_btn.setText(self._tr('refresh_remote_mapping', 'Refresh Remote Mapping'))
        self._refresh_worker = None
        if success:
            self._check_update_status_async()
            show_info(
                self._tr('success', 'Success'),
                self._tr('cache_refreshed', 'Remote mapping cache refreshed'),
                parent=self
            )
        else:
            show_error(
                self._tr('error', 'Error'),
                self._tr('refresh_failed', 'Refresh failed: {}').format(error_msg),
                parent=self
            )



    def export_mappings(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self._tr('export_mappings_title', 'Export Mappings'),
            "user_mappings.csv",
            "CSV (*.csv)"
        )
        if file_path:
            try:
                import csv
                with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['standard_name', 'raw_names', 'logo_url', 'group_name'])
                    for std_name, data in mapping_manager.user_mappings.items():
                        writer.writerow([
                            std_name,
                            ','.join(data.get('raw_names', [])),
                            data.get('logo_url', ''),
                            data.get('group_name', '')
                        ])
                show_info(
                    self._tr('success', 'Success'),
                    f"{self._tr('exported_to', 'Exported to')} {file_path}",
                    parent=self
                )
            except Exception as e:
                show_error(
                    self._tr('error', 'Error'),
                    f"{self._tr('export_failed', 'Export failed')}: {e}",
                    parent=self
                )

    def import_mappings(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self._tr('import_mappings_title', 'Import Mappings'),
            "",
            "CSV (*.csv)"
        )
        if file_path:
            try:
                import csv
                imported = {}
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        std_name = row.get('standard_name', '').strip()
                        if not std_name:
                            continue
                        imported[std_name] = {
                            'raw_names': [n.strip() for n in row.get('raw_names', '').split(',') if n.strip()],
                            'logo_url': row.get('logo_url', '').strip(),
                            'group_name': row.get('group_name', '').strip()
                        }
                mapping_manager.import_user_mappings(imported)
                self.load_user_mappings()
                show_info(
                    self._tr('success', 'Success'),
                    self._tr('import_success', 'Mappings imported successfully'),
                    parent=self
                )
            except Exception as e:
                show_error(
                    self._tr('error', 'Error'),
                    f"{self._tr('import_failed', 'Import failed')}: {e}",
                    parent=self
                )

    def update_ui_texts(self):
        _ = self._tr
        try:
            self.setWindowTitle(_('mapping_manager', 'Channel Mapping Manager'))
            self.refresh_cache_btn.setText(_('refresh_remote_mapping', 'Refresh Remote Mapping'))
            manual_group_title = _('manual_mapping_section', 'Manual Mapping (Advanced)')
            if hasattr(self, 'mapping_table'):
                for w in self.findChildren(QtWidgets.QGroupBox):
                    if hasattr(w, 'setTitle'):
                        w.setTitle(manual_group_title)
                        break
            if hasattr(self, 'search_input'):
                self.search_input.setPlaceholderText(_('search_channel_name', 'Search channel name...'))
            if hasattr(self, 'search_options'):
                current = self.search_options.currentText() or ''
                self.search_options.clear()
                items = [
                    _('search_all_fields', 'All Fields'),
                    _('search_standard_name_only', 'Standard Name'),
                    _('search_raw_name_only', 'Raw Name'),
                    _('search_group_only', 'Group'),
                ]
                self.search_options.addItems(items)
                idx = 0
                for i, item in enumerate(items):
                    if item == current:
                        idx = i
                        break
                self.search_options.setCurrentIndex(idx)
            if hasattr(self, 'mapping_table'):
                self.mapping_table.setHorizontalHeaderLabels([
                    _('serial_number', 'No.'),
                    _('standard_name', 'Standard Name'),
                    _('raw_name', 'Raw Name'),
                    _('group', 'Group'),
                    _('logo_address', 'Logo Address')
                ])
            if hasattr(self, 'add_mapping_btn'):
                self.add_mapping_btn.setText(_('add_mapping', 'Add'))
            if hasattr(self, 'edit_mapping_btn'):
                self.edit_mapping_btn.setText(_('edit_mapping', 'Edit'))
            if hasattr(self, 'delete_mapping_btn'):
                self.delete_mapping_btn.setText(_('delete_mapping', 'Delete'))
            if hasattr(self, 'export_mappings_btn'):
                self.export_mappings_btn.setText(_('export_user_mappings', 'Export'))
            if hasattr(self, 'import_mappings_btn'):
                self.import_mappings_btn.setText(_('import_user_mappings', 'Import'))
            if hasattr(self, 'close_btn'):
                self.close_btn.setText(_('close', 'Close'))
            self.logger.info("映射管理器UI文本已更新")
        except Exception as e:
            self.logger.error(f"更新映射管理器UI文本失败: {e}")

    def reapply_styles(self):
        from ..styles import AppStyles
        colors = AppStyles._get_colors()
        info_box = self.findChild(QtWidgets.QFrame)
        if info_box:
            r = AppStyles._get_style_border_radius()
            info_box.setStyleSheet(f"""
                QFrame {{
                    background-color: {colors['alternate_base']};
                    border-radius: {r}px;
                    border: 1px solid {colors['mid']};
                    padding: 4px;
                }}
                QLabel {{ color: {colors['window_text']}; border: none; background: transparent; }}
            """)
        for child in self.findChildren(QtWidgets.QPushButton):
            child.setStyleSheet(AppStyles.common_button_style())
        for child in self.findChildren(QtWidgets.QLineEdit):
            child.setStyleSheet(AppStyles.common_line_edit_style())
        for child in self.findChildren(QtWidgets.QComboBox):
            child.setStyleSheet(AppStyles.common_combo_box_style())
        for child in self.findChildren(QtWidgets.QGroupBox):
            child.setStyleSheet(AppStyles.common_group_box_style())
        if hasattr(self, 'mapping_table'):
            self.mapping_table.setStyleSheet(AppStyles.list_style())
        if hasattr(self, 'update_status_label'):
            self.update_status_label.setStyleSheet(
                f"color: {colors['player_panel_hint']}; font-size: 11px; border: none; background: transparent; padding: 4px 8px;"
            )


class MappingEditDialog(FloatingDialog):

    def __init__(self, parent=None, standard_name="", raw_name="", group_name="", logo_url=""):
        super().__init__(parent, stay_on_top=False)
        self.standard_name = standard_name
        self.raw_name = raw_name
        self.group_name = group_name
        self.logo_url = logo_url

        if parent and hasattr(parent, 'language_manager'):
            self.language_manager = parent.language_manager
        else:
            from core.language_manager import LanguageManager
            self.language_manager = LanguageManager()
            self.language_manager.load_available_languages()
            self.language_manager.set_language('zh')

        tr = self.language_manager.tr
        self.setWindowTitle((tr('edit_mapping', 'Edit Mapping') or 'Edit Mapping') if standard_name else (tr('add_mapping', 'Add Mapping') or 'Add Mapping'))
        self.setup_ui()

        from ..theme_manager import get_theme_manager
        get_theme_manager().register_window(self)

    def done(self, result):
        from ..theme_manager import get_theme_manager
        try:
            get_theme_manager().unregister_window(self)
        except Exception:
            pass
        super().done(result)

    def _tr(self, key: str, fallback: str) -> str:
        v = self.language_manager.tr(key, fallback)
        return v if v else fallback

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        _ = self._tr
        from ui.styles import AppStyles
        self.setStyleSheet(AppStyles.dialog_style())

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self.standard_name_input = QtWidgets.QLineEdit(self.standard_name)
        self.standard_name_input.setStyleSheet(AppStyles.common_line_edit_style())
        form.addRow(_('standard_name', 'Standard Name') + ":", self.standard_name_input)

        self.raw_name_input = QtWidgets.QLineEdit(self.raw_name)
        self.raw_name_input.setStyleSheet(AppStyles.common_line_edit_style())
        form.addRow(_('raw_name', 'Raw Name') + ":", self.raw_name_input)

        self.group_name_input = QtWidgets.QLineEdit(self.group_name)
        self.group_name_input.setStyleSheet(AppStyles.common_line_edit_style())
        form.addRow(_('group', 'Group') + ":", self.group_name_input)

        self.logo_url_input = QtWidgets.QLineEdit(self.logo_url)
        self.logo_url_input.setStyleSheet(AppStyles.common_line_edit_style())
        form.addRow(_('logo_address', 'Logo URL') + ":", self.logo_url_input)

        layout.addLayout(form)

        btn_bar, self.ok_btn, self.cancel_btn = self.build_confirm_buttons(self.accept)
        layout.addWidget(btn_bar)

    def get_mapping_data(self):
        standard_name = self.standard_name_input.text().strip()
        raw_name = self.raw_name_input.text().strip()
        if not standard_name or not raw_name:
            show_warning(
                self._tr('input_error', 'Input Error'),
                self._tr('name_required', 'Standard name and raw name are required'),
                parent=self
            )
            return None
        return {
            'standard_name': standard_name,
            'raw_name': raw_name,
            'group_name': self.group_name_input.text().strip() or None,
            'logo_url': self.logo_url_input.text().strip() or None
        }

    def reapply_styles(self):
        from ..styles import AppStyles
        for child in self.findChildren(QtWidgets.QLineEdit):
            child.setStyleSheet(AppStyles.common_line_edit_style())
        for child in self.findChildren(QtWidgets.QPushButton):
            child.setStyleSheet(AppStyles.common_button_style())
