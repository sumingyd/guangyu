"""视频图像调整对话框 - 亮度/对比度/饱和度/色调/Gamma/锐度 + 旋转/镜像"""
import os
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QComboBox, QGroupBox, QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QInputDialog

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger
from utils.platform_utils import is_linux, is_macos


class VideoEqualizerDialog(FloatingDialog):
    """视频图像调整对话框
    滑块拖动时实时应用到 mpv；保存按钮持久化到 config
    """

    style_saved = Signal(dict)

    # 整数参数列表（mpv 取值 -100~100）
    _INT_KEYS = ('brightness', 'contrast', 'saturation', 'hue', 'gamma')
    # 锐度使用 -100~100 的整数滑块映射到 mpv 的 -1.0~1.0
    _SHARP_KEY = 'sharpness'

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('video_eq_title', '视频图像调整'))
        self.setMinimumSize(760, 520)
        self._loading = False
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        # 初始回填
        self._reload_from_config()

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        text_color = c.get('window_text')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                margin-top: 12px; padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
            QSlider::groove:horizontal {{
                height: 4px; background: {c.get('mid')}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px; height: 14px; margin: -5px 0;
                background: {c.get('accent')}; border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {c.get('accent')}; border: 2px solid {text_color};
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ===== 上半部分：三列水平排列 =====
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        # ---- 左列：图像参数 ----
        image_group = QGroupBox(tr('video_eq_group_image', '图像参数'))
        form = QFormLayout(image_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(4)
        form.setContentsMargins(6, 8, 6, 6)

        # 亮度/对比度/饱和度/色调/Gamma：-100 ~ 100
        self._int_sliders = {}
        self._int_labels = {}
        for key in self._INT_KEYS:
            label_key = f'video_eq_{key}'
            container, slider, value_label = self._make_int_slider(key, tr(label_key, key.capitalize()))
            form.addRow(tr(label_key, key.capitalize()), container)
            self._int_sliders[key] = slider
            self._int_labels[key] = value_label

        # 锐度：-100~100 整数滑块（映射到 -1.0~1.0）
        sharp_slider = QSlider(Qt.Orientation.Horizontal)
        sharp_slider.setRange(-100, 100)
        sharp_slider.setSingleStep(5)
        sharp_slider.setPageStep(20)
        sharp_slider.setValue(0)
        sharp_label = QLabel('0.00')
        sharp_label.setMinimumWidth(40)
        sharp_row = QHBoxLayout()
        sharp_row.addWidget(sharp_slider, 1)
        sharp_row.addWidget(sharp_label)
        sharp_container = QWidget()
        sharp_container.setLayout(sharp_row)
        sharp_slider.valueChanged.connect(lambda v: self._on_sharpness_changed(v, sharp_label))
        form.addRow(tr('video_eq_sharpness', '锐度'), sharp_container)
        self._sharpness_slider = sharp_slider
        self._sharpness_label = sharp_label

        top_row.addWidget(image_group, 1)

        # ---- 中列：画面变换 ----
        transform_group = QGroupBox(tr('video_eq_group_transform', '画面变换'))
        tform = QFormLayout(transform_group)
        tform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        tform.setSpacing(4)
        tform.setContentsMargins(6, 8, 6, 6)

        # 旋转
        self.rotate_combo = QComboBox()
        self.rotate_combo.addItem('0°', 0)
        self.rotate_combo.addItem('90°', 90)
        self.rotate_combo.addItem('180°', 180)
        self.rotate_combo.addItem('270°', 270)
        self.rotate_combo.currentIndexChanged.connect(self._on_rotate_changed)
        tform.addRow(tr('video_eq_rotate', '旋转'), self.rotate_combo)

        # 翻转
        self.flip_combo = QComboBox()
        self.flip_combo.addItem(tr('video_eq_flip_none', '无'), '')
        self.flip_combo.addItem(tr('video_eq_flip_horizontal', '水平翻转'), 'horizontal')
        self.flip_combo.addItem(tr('video_eq_flip_vertical', '垂直翻转'), 'vertical')
        self.flip_combo.addItem(tr('video_eq_flip_both', '双向翻转'), 'both')
        self.flip_combo.currentIndexChanged.connect(self._on_flip_changed)
        tform.addRow(tr('video_eq_flip', '镜像翻转'), self.flip_combo)

        # 切换文件时自动重置
        self.reset_on_new_check = QCheckBox(tr('video_eq_reset_on_new_file', '切换文件时自动重置'))
        self.reset_on_new_check.toggled.connect(self._on_reset_on_new_toggled)
        tform.addRow('', self.reset_on_new_check)

        # 自动裁剪黑边按钮
        crop_row = QHBoxLayout()
        self.autocrop_btn = QPushButton(tr('video_eq_autocrop', '自动裁剪黑边'))
        self.autocrop_btn.clicked.connect(self._on_autocrop_clicked)
        self.remove_crop_btn = QPushButton(tr('video_eq_remove_crop', '移除裁剪'))
        self.remove_crop_btn.clicked.connect(self._on_remove_crop_clicked)
        crop_row.addWidget(self.autocrop_btn)
        crop_row.addWidget(self.remove_crop_btn)
        crop_row.addStretch()
        tform.addRow('', crop_row)

        top_row.addWidget(transform_group, 1)

        # ---- 右列：视频增强 ----
        enhance_group = QGroupBox(tr('video_eq_group_enhance', '视频增强'))
        enhance_form = QFormLayout(enhance_group)
        enhance_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        enhance_form.setSpacing(4)
        enhance_form.setContentsMargins(6, 8, 6, 6)

        # 运动补偿强度
        self.mc_combo = QComboBox()
        self.mc_combo.addItem(tr('mc_off', '关闭'), 'off')
        self.mc_combo.addItem(tr('mc_low', '轻度（帧混合）'), 'low')
        self.mc_combo.addItem(tr('mc_medium', '中度（运动补偿）'), 'medium')
        self.mc_combo.addItem(tr('mc_high', '强力（高级补偿）'), 'high')
        self.mc_combo.setToolTip(tr('mc_hint', '需 copy-back 硬解或软解。中度以上会明显增加 CPU 负载'))
        self.mc_combo.currentIndexChanged.connect(self._on_mc_changed)
        enhance_form.addRow(tr('mc_strength_label', '运动补偿'), self.mc_combo)

        # 目标帧率
        self.mc_fps_combo = QComboBox()
        self.mc_fps_combo.addItem('50', 50)
        self.mc_fps_combo.addItem('60', 60)
        self.mc_fps_combo.addItem('90', 90)
        self.mc_fps_combo.addItem('120', 120)
        self.mc_fps_combo.addItem('144', 144)
        self.mc_fps_combo.currentIndexChanged.connect(self._on_mc_fps_changed)
        enhance_form.addRow(tr('mc_fps_label', '目标帧率'), self.mc_fps_combo)

        # 缩放算法
        self.sr_combo = QComboBox()
        self.sr_combo.addItem(tr('sr_off', '关闭'), 'off')
        self.sr_combo.addItem(tr('sr_bilinear', '双线性'), 'bilinear')
        self.sr_combo.addItem(tr('sr_bicubic', '双三次'), 'bicubic')
        self.sr_combo.addItem(tr('sr_lanczos', 'Lanczos'), 'lanczos')
        self.sr_combo.addItem(tr('sr_spline', '样条'), 'spline')
        self.sr_combo.addItem(tr('sr_ewa_lanczos', 'EWA Lanczos'), 'ewa_lanczos')
        self.sr_combo.addItem(tr('sr_ewa_lanczossharp', 'EWA Lanczos Sharp'), 'ewa_lanczossharp')
        self.sr_combo.setToolTip(tr('sr_hint', '缩放算法全局生效；细节增强需 copy-back 硬解或软解'))
        self.sr_combo.currentIndexChanged.connect(self._on_sr_changed)
        enhance_form.addRow(tr('sr_scale_label', '缩放算法'), self.sr_combo)

        # 细节增强滑块
        self.sr_detail_slider = QSlider(Qt.Orientation.Horizontal)
        self.sr_detail_slider.setRange(0, 100)
        self.sr_detail_slider.setSingleStep(5)
        self.sr_detail_slider.setPageStep(10)
        self.sr_detail_slider.setValue(0)
        self.sr_detail_label = QLabel('0')
        self.sr_detail_label.setMinimumWidth(30)
        self.sr_detail_slider.valueChanged.connect(
            lambda v: self._on_sr_detail_changed(v, self.sr_detail_label))
        sr_detail_row = QHBoxLayout()
        sr_detail_row.addWidget(self.sr_detail_slider, 1)
        sr_detail_row.addWidget(self.sr_detail_label)
        sr_detail_container = QWidget()
        sr_detail_container.setLayout(sr_detail_row)
        enhance_form.addRow(tr('sr_detail_label', '细节增强'), sr_detail_container)

        # 着色器预设选择
        self.shader_combo = QComboBox()
        self.shader_combo.addItem(tr('shader_off', '关闭'), 'off')
        self.shader_combo.addItem(tr('shader_ravu', 'RAVU 锐利放大'), 'ravu')
        self.shader_combo.addItem(tr('shader_fsrcnnx', 'FSRCNNX 超分辨率'), 'fsrcnnx')
        self.shader_combo.addItem(tr('shader_anime4k', 'Anime4K 动画增强'), 'anime4k')
        self.shader_combo.addItem(tr('shader_krig', 'KrigBilateral 色度升频'), 'krig')
        self.shader_combo.addItem(tr('shader_ssim', 'SSim 降频'), 'ssim')
        self.shader_combo.addItem(tr('shader_esrgan', 'ESRGAN 高质量超分'), 'esrgan')
        self.shader_combo.addItem(tr('shader_adaptive_sharpen', '自适应锐化'), 'adaptive_sharpen')
        self.shader_combo.setToolTip(
            tr('shader_hint',
               'GLSL 着色器在 GPU 运行。请将 .glsl/.hook 文件放在 shaders/ 目录')
        )
        # 动态添加已检测到的着色器文件
        pc = self.window.player_controller
        if pc and hasattr(pc, 'list_available_shaders'):
            try:
                available = pc.list_available_shaders()
                existing_data = {
                    self.shader_combo.itemData(i)
                    for i in range(self.shader_combo.count())
                    if self.shader_combo.itemData(i)
                }
                for item in available:
                    if item['preset'] not in existing_data:
                        self.shader_combo.addItem(
                            item['filename'], item['path']
                        )
            except Exception as e:
                logger.debug(f"_setup_ui: {e}")
        self.shader_combo.currentIndexChanged.connect(self._on_shader_changed)
        enhance_form.addRow(tr('shader_preset_label', 'AI 着色器'), self.shader_combo)

        top_row.addWidget(enhance_group, 1)
        layout.addLayout(top_row)

        # ===== 第三阶段：智能场景检测 + 预设管理 =====
        phase3_row = QHBoxLayout()

        # 智能场景检测
        scene_box = QGroupBox(tr('group_scene_detect', '智能场景检测'))
        scene_layout = QHBoxLayout(scene_box)
        scene_layout.setContentsMargins(6, 6, 6, 6)
        self.scene_detect_check = QCheckBox(tr('scene_detect_enable', '自动检测内容类型'))
        self.scene_detect_check.setToolTip(
            tr('scene_detect_hint',
               '根据视频分辨率、帧率、码率自动判断内容类型（动画/体育/电影），\n动态调整运动补偿和缩放参数')
        )
        self.scene_detect_check.toggled.connect(self._on_scene_detect_toggled)
        scene_layout.addWidget(self.scene_detect_check)
        self.scene_label = QLabel('')
        self.scene_label.setStyleSheet(
            f"color: {AppStyles.get_color('accent')}; font-size: 11px;"
        )
        scene_layout.addWidget(self.scene_label)
        scene_layout.addStretch()
        phase3_row.addWidget(scene_box, 1)

        # 预设管理
        preset_mgr_box = QGroupBox(tr('group_preset_manage', '预设管理'))
        preset_mgr_layout = QHBoxLayout(preset_mgr_box)
        preset_mgr_layout.setContentsMargins(6, 6, 6, 6)
        self.preset_mgr_combo = QComboBox()
        self.preset_mgr_combo.setMinimumWidth(120)
        self._refresh_preset_list()
        preset_mgr_layout.addWidget(self.preset_mgr_combo)
        self.btn_apply_preset = QPushButton(tr('btn_apply_preset', '应用'))
        self.btn_apply_preset.clicked.connect(self._on_apply_custom_preset)
        preset_mgr_layout.addWidget(self.btn_apply_preset)
        self.btn_save_preset = QPushButton(tr('btn_save_preset', '保存为...'))
        self.btn_save_preset.clicked.connect(self._on_save_custom_preset)
        preset_mgr_layout.addWidget(self.btn_save_preset)
        self.btn_delete_preset = QPushButton(tr('btn_delete_preset', '删除'))
        self.btn_delete_preset.clicked.connect(self._on_delete_custom_preset)
        preset_mgr_layout.addWidget(self.btn_delete_preset)
        phase3_row.addWidget(preset_mgr_box, 2)
        layout.addLayout(phase3_row)

        # ===== GPU API 选择 =====
        gpu_row = QHBoxLayout()
        gpu_label = QLabel(tr('gpu_api_label', 'GPU 渲染后端:'))
        gpu_row.addWidget(gpu_label)
        self.gpu_api_combo = QComboBox()
        auto_label = (tr('gpu_api_auto_linux', '自动 (OpenGL)') if is_linux()
                      else tr('gpu_api_auto', '自动 (D3D11)'))
        self.gpu_api_combo.addItem(auto_label, 'auto')
        self.gpu_api_combo.addItem(tr('gpu_api_d3d11', 'D3D11 (默认)'), 'd3d11')
        self.gpu_api_combo.addItem(tr('gpu_api_opengl', 'OpenGL'), 'opengl')
        self.gpu_api_combo.addItem(tr('gpu_api_vulkan', 'Vulkan (实验性)'), 'vulkan')
        self.gpu_api_combo.setToolTip(
            tr('gpu_api_hint',
               'Vulkan 可能在部分 GPU 上获得更好性能，需重启播放器生效')
        )
        if is_macos():
            # macOS 强制 vo=libmpv（render API），gpu-api 不参与渲染，选项无意义
            self.gpu_api_combo.setEnabled(False)
            self.gpu_api_combo.setToolTip(
                tr('gpu_api_unavailable_macos',
                   'macOS 使用 libmpv 渲染（vo=libmpv），GPU 后端由系统决定，此选项不生效')
            )
        gpu_row.addWidget(self.gpu_api_combo)
        gpu_row.addStretch()
        layout.addLayout(gpu_row)

        # ===== 智能预设 + 硬件信息（合并为一行） =====
        bottom_row = QHBoxLayout()

        # 智能预设按钮
        preset_box = QGroupBox(tr('video_eq_group_smart_preset', '智能预设'))
        preset_layout = QHBoxLayout(preset_box)
        preset_layout.setContentsMargins(6, 6, 6, 6)
        self.btn_preset_auto = QPushButton(tr('preset_auto', '智能推荐'))
        self.btn_preset_auto.clicked.connect(lambda: self._apply_smart_preset('auto'))
        self.btn_preset_perf = QPushButton(tr('preset_performance', '性能'))
        self.btn_preset_perf.clicked.connect(lambda: self._apply_smart_preset('performance'))
        self.btn_preset_quality = QPushButton(tr('preset_quality', '画质'))
        self.btn_preset_quality.clicked.connect(lambda: self._apply_smart_preset('quality'))
        self.btn_preset_anime = QPushButton(tr('preset_anime', '动画'))
        self.btn_preset_anime.clicked.connect(lambda: self._apply_smart_preset('anime'))
        self.btn_preset_sports = QPushButton(tr('preset_sports', '体育'))
        self.btn_preset_sports.clicked.connect(lambda: self._apply_smart_preset('sports'))
        for btn in (self.btn_preset_auto, self.btn_preset_perf, self.btn_preset_quality,
                    self.btn_preset_anime, self.btn_preset_sports):
            preset_layout.addWidget(btn)
        bottom_row.addWidget(preset_box, 1)

        # 硬件信息（紧凑标签）
        hw_box = QGroupBox(tr('video_eq_group_hardware', '硬件'))
        hw_layout = QVBoxLayout(hw_box)
        hw_layout.setContentsMargins(6, 6, 6, 6)
        self.hw_label = QLabel('')
        self.hw_label.setWordWrap(True)
        self.hw_label.setStyleSheet(
            f"color: {AppStyles.get_color('mid')}; font-size: 10px;"
        )
        hw_layout.addWidget(self.hw_label)
        try:
            from services.hardware_detect_service import get_hardware_detect_service
            hw = get_hardware_detect_service()
            self.hw_label.setText(hw.get_hardware_summary())
        except Exception as e:
            logger.warning(f"硬件检测失败: {e}")
            self.hw_label.setText(tr('hw_detect_failed', '硬件检测不可用'))
        bottom_row.addWidget(hw_box, 1)
        layout.addLayout(bottom_row)

        # ===== 操作按钮（标准设置式：恢复默认 | 应用 + 完成） =====
        def _on_done():
            self._apply_now()
            self._save()
            self.close()

        btn_bar, self.reset_btn, self.apply_btn, self.close_btn = self.build_settings_buttons(
            self._reset_all, self._apply_now, _on_done,
            reset_text=tr('video_eq_reset', '恢复默认'),
            apply_text=tr('video_eq_apply', '应用'),
            done_text=tr('video_eq_close', '完成'),
        )
        layout.addWidget(btn_bar)

    def _make_int_slider(self, key: str, label_text: str):
        """构造 -100~100 整数滑块 + 数值标签，返回 (container, slider, value_label)"""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(-100, 100)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        slider.setValue(0)
        value_label = QLabel('0')
        value_label.setMinimumWidth(36)
        slider.valueChanged.connect(lambda v, lbl=value_label, k=key: self._on_int_changed(k, v, lbl))
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        container = QWidget()
        container.setLayout(row)
        return container, slider, value_label

    # ---------- 数据加载/收集 ----------
    def _reload_from_config(self):
        """从配置加载并回填 UI"""
        try:
            cfg = self.window.config.load_video_eq()
        except Exception as e:
            logger.warning(f"加载视频 EQ 配置失败: {e}")
            cfg = {}
        self._loading = True
        try:
            self._set_ui_from_dict(cfg)
        finally:
            self._loading = False
        # 启动时同步应用到当前播放
        self._apply_now(silent=True)

    def _set_ui_from_dict(self, cfg: dict):
        """用字典回填所有 UI 控件"""
        for key in self._INT_KEYS:
            v = int(cfg.get(key, 0) or 0)
            v = max(-100, min(100, v))
            self._int_sliders[key].setValue(v)
            self._int_labels[key].setText(str(v))
        sharp = float(cfg.get('sharpness', 0.0) or 0.0)
        sharp = max(-1.0, min(1.0, sharp))
        self._sharpness_slider.setValue(int(round(sharp * 100)))
        self._sharpness_label.setText(f"{sharp:.2f}")
        rotate = int(cfg.get('video_rotate', 0) or 0)
        idx = self.rotate_combo.findData(rotate)
        if idx >= 0:
            self.rotate_combo.setCurrentIndex(idx)
        flip_mode = cfg.get('video_flip', '') or ''
        idx = self.flip_combo.findData(flip_mode)
        if idx >= 0:
            self.flip_combo.setCurrentIndex(idx)
        self.reset_on_new_check.setChecked(bool(cfg.get('reset_on_new_file', False)))
        # 运动补偿
        mc_strength = cfg.get('motion_comp', 'off') or 'off'
        idx = self.mc_combo.findData(mc_strength)
        if idx >= 0:
            self.mc_combo.setCurrentIndex(idx)
        mc_fps = int(cfg.get('motion_comp_fps', 60))
        idx = self.mc_fps_combo.findData(mc_fps)
        if idx >= 0:
            self.mc_fps_combo.setCurrentIndex(idx)
        # 分辨率提升
        sr_scale = cfg.get('superres_scale', 'off') or 'off'
        idx = self.sr_combo.findData(sr_scale)
        if idx >= 0:
            self.sr_combo.setCurrentIndex(idx)
        sr_detail = int(cfg.get('superres_detail', 0))
        sr_detail = max(0, min(100, sr_detail))
        self.sr_detail_slider.setValue(sr_detail)
        self.sr_detail_label.setText(str(sr_detail))
        # 用户着色器
        shader_preset = cfg.get('shader_preset', 'off') or 'off'
        idx = self.shader_combo.findData(shader_preset)
        if idx < 0:
            # 可能是自定义路径
            idx = self.shader_combo.findData('off')
        if idx >= 0:
            self.shader_combo.setCurrentIndex(idx)
        # 智能场景检测
        self.scene_detect_check.setChecked(
            bool(cfg.get('scene_detect_enabled', False))
        )
        # GPU API
        gpu_api = cfg.get('gpu_api', 'auto') or 'auto'
        idx = self.gpu_api_combo.findData(gpu_api)
        if idx >= 0:
            self.gpu_api_combo.setCurrentIndex(idx)

    def _collect_eq(self) -> dict:
        """从 UI 控件收集所有参数"""
        result = {}
        for key in self._INT_KEYS:
            result[key] = int(self._int_sliders[key].value())
        result['sharpness'] = round(self._sharpness_slider.value() / 100.0, 3)
        result['video_rotate'] = int(self.rotate_combo.currentData() or 0)
        result['video_flip'] = self.flip_combo.currentData() or ''
        result['reset_on_new_file'] = bool(self.reset_on_new_check.isChecked())
        # 运动补偿
        result['motion_comp'] = self.mc_combo.currentData() or 'off'
        result['motion_comp_fps'] = int(self.mc_fps_combo.currentData() or 60)
        # 分辨率提升
        result['superres_scale'] = self.sr_combo.currentData() or 'off'
        result['superres_detail'] = int(self.sr_detail_slider.value())
        # 用户着色器
        shader_data = self.shader_combo.currentData() or 'off'
        # 如果是文件路径则保存路径，否则保存预设名
        if isinstance(shader_data, str) and os.path.isfile(shader_data):
            result['shader_preset'] = shader_data
        else:
            result['shader_preset'] = shader_data
        # 智能场景检测
        result['scene_detect_enabled'] = bool(self.scene_detect_check.isChecked())
        # GPU API
        result['gpu_api'] = self.gpu_api_combo.currentData() or 'auto'
        return result

    # ---------- 事件处理 ----------
    def _on_int_changed(self, key: str, value: int, label: QLabel):
        label.setText(str(value))
        if self._loading:
            return
        pc = self.window.player_controller
        if pc and pc.is_playing:
            setter = getattr(pc, f'set_{key}', None)
            if setter:
                setter(value)
                self._show_osd(f"{self.window.language_manager.tr(f'osd_video_{key}', key.capitalize())}: {value:+d}")

    def _on_sharpness_changed(self, value: int, label: QLabel):
        v = round(value / 100.0, 3)
        label.setText(f"{v:.2f}")
        if self._loading:
            return
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.set_sharpness(v)
            self._show_osd(f"{self.window.language_manager.tr('osd_video_sharpness', 'Sharpness')}: {v:+.2f}")

    def _on_rotate_changed(self, idx: int):
        if self._loading:
            return
        degree = int(self.rotate_combo.currentData() or 0)
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.set_video_rotate(degree)
            self._show_osd(f"{self.window.language_manager.tr('osd_video_rotate', 'Rotate')}: {degree}°")

    def _on_flip_changed(self, idx: int):
        if self._loading:
            return
        mode = self.flip_combo.currentData() or ''
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.set_video_flip(mode)
            label = self.flip_combo.currentText()
            self._show_osd(f"{self.window.language_manager.tr('osd_video_flip', 'Flip')}: {label}")

    def _on_reset_on_new_toggled(self, checked: bool):
        if self._loading:
            return
        # 即时保存该选项
        try:
            cfg = self.window.config.load_video_eq()
            cfg['reset_on_new_file'] = bool(checked)
            self.window.config.save_video_eq(cfg)
        except Exception as e:
            logger.warning(f"保存 reset_on_new_file 失败: {e}")

    def _on_mc_changed(self, idx: int):
        if self._loading:
            return
        strength = self.mc_combo.currentData() or 'off'
        fps = int(self.mc_fps_combo.currentData() or 60)
        mc = getattr(self.window, 'media_ctrl', None)
        if mc:
            mc.set_motion_compensation(strength, fps)

    def _on_mc_fps_changed(self, idx: int):
        if self._loading:
            return
        strength = self.mc_combo.currentData() or 'off'
        fps = int(self.mc_fps_combo.currentData() or 60)
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and strength != 'off':
            mc.set_motion_compensation(strength, fps)

    def _on_sr_changed(self, idx: int):
        if self._loading:
            return
        scale_algo = self.sr_combo.currentData() or 'off'
        detail = int(self.sr_detail_slider.value())
        mc = getattr(self.window, 'media_ctrl', None)
        if mc:
            mc.set_super_resolution(scale_algo, detail)

    def _on_sr_detail_changed(self, value: int, label: QLabel):
        label.setText(str(value))
        if self._loading:
            return
        scale_algo = self.sr_combo.currentData() or 'off'
        mc = getattr(self.window, 'media_ctrl', None)
        if mc:
            mc.set_super_resolution(scale_algo, value)

    def _on_shader_changed(self, idx: int):
        if self._loading:
            return
        shader_data = self.shader_combo.currentData() or 'off'
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, 'set_user_shader'):
            mc.set_user_shader(shader_data)

    def _on_scene_detect_toggled(self, checked: bool):
        """开关智能场景检测"""
        if self._loading:
            return
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, 'toggle_scene_detect'):
            mc.toggle_scene_detect(checked)
        if checked:
            self.scene_label.setText(
                self.window.language_manager.tr('scene_detect_starting', '检测中...')
            )
        else:
            self.scene_label.setText('')

    def _refresh_preset_list(self):
        """刷新预设下拉列表"""
        self.preset_mgr_combo.clear()
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, 'list_custom_presets'):
            presets = mc.list_custom_presets()
            for p in presets:
                label = p['name']
                if p.get('builtin'):
                    label += f" ({self.window.language_manager.tr('builtin', '内置')})"
                self.preset_mgr_combo.addItem(label, p['name'])

    def _on_apply_custom_preset(self):
        """应用选中的预设"""
        name = self.preset_mgr_combo.currentData()
        if not name:
            return
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, 'apply_custom_preset'):
            mc.apply_custom_preset(name)
            # 同步 UI
            from services.preset_manager_service import get_preset_manager
            pm = get_preset_manager()
            settings = pm.get_preset(name)
            if settings:
                self._loading = True
                try:
                    mc_s = settings.get('motion_comp', 'off')
                    idx = self.mc_combo.findData(mc_s)
                    if idx >= 0:
                        self.mc_combo.setCurrentIndex(idx)
                    sr_s = settings.get('superres_scale', 'off')
                    idx = self.sr_combo.findData(sr_s)
                    if idx >= 0:
                        self.sr_combo.setCurrentIndex(idx)
                    sr_d = int(settings.get('superres_detail', 0))
                    self.sr_detail_slider.setValue(sr_d)
                    sp = settings.get('shader_preset', 'off')
                    idx = self.shader_combo.findData(sp)
                    if idx < 0:
                        idx = self.shader_combo.findData('off')
                    if idx >= 0:
                        self.shader_combo.setCurrentIndex(idx)
                    # 图像参数
                    for key in self._INT_KEYS:
                        if key in settings:
                            v = max(-100, min(100, int(settings[key])))
                            self._int_sliders[key].setValue(v)
                            self._int_labels[key].setText(str(v))
                    if 'sharpness' in settings:
                        sharp = max(-1.0, min(1.0, float(settings['sharpness'])))
                        self._sharpness_slider.setValue(int(round(sharp * 100)))
                        self._sharpness_label.setText(f"{sharp:.2f}")
                finally:
                    self._loading = False

    def _on_save_custom_preset(self):
        """保存当前设置为自定义预设"""
        tr = self.window.language_manager.tr
        name, ok = QInputDialog.getText(
            self, tr('save_preset_title', '保存预设'),
            tr('save_preset_prompt', '预设名称:'),
            text=tr('my_preset', '我的预设')
        )
        if not ok or not name.strip():
            return
        settings = self._collect_eq()
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, 'save_custom_preset'):
            if mc.save_custom_preset(name.strip(), settings):
                self._refresh_preset_list()
                # 选中新保存的预设
                idx = self.preset_mgr_combo.findData(name.strip())
                if idx >= 0:
                    self.preset_mgr_combo.setCurrentIndex(idx)

    def _on_delete_custom_preset(self):
        """删除选中的自定义预设"""
        name = self.preset_mgr_combo.currentData()
        if not name:
            return
        tr = self.window.language_manager.tr
        from utils.error_handler import show_confirm
        if show_confirm(tr('confirm_delete', '确认删除'),
                        tr('confirm_delete_preset',
                           '确定删除预设 "{name}" 吗？').format(name=name),
                        parent=self):
            mc = getattr(self.window, 'media_ctrl', None)
            if mc and hasattr(mc, 'delete_custom_preset'):
                if mc.delete_custom_preset(name):
                    self._refresh_preset_list()

    def _apply_smart_preset(self, preset_name: str):
        """应用智能预设"""
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, 'apply_smart_preset'):
            mc.apply_smart_preset(preset_name)
            # 同步 UI
            if preset_name == 'auto':
                try:
                    from services.hardware_detect_service import (
                        get_hardware_detect_service
                    )
                    hw = get_hardware_detect_service()
                    settings = hw.get_recommended_settings()
                except Exception:
                    settings = {}
            elif preset_name == 'performance':
                settings = {
                    'motion_comp': 'off', 'motion_comp_fps': 60,
                    'superres_scale': 'bilinear', 'superres_detail': 0,
                    'shader_preset': 'off',
                }
            elif preset_name == 'quality':
                settings = {
                    'motion_comp': 'medium', 'motion_comp_fps': 60,
                    'superres_scale': 'ewa_lanczossharp', 'superres_detail': 40,
                    'shader_preset': 'off',
                }
            elif preset_name == 'anime':
                settings = {
                    'motion_comp': 'low', 'motion_comp_fps': 60,
                    'superres_scale': 'ewa_lanczos', 'superres_detail': 20,
                    'shader_preset': 'anime4k',
                }
            elif preset_name == 'sports':
                settings = {
                    'motion_comp': 'high', 'motion_comp_fps': 60,
                    'superres_scale': 'lanczos', 'superres_detail': 30,
                    'shader_preset': 'off',
                }
            else:
                settings = {}
            # 回填 UI
            self._loading = True
            try:
                if settings:
                    mc_s = settings.get('motion_comp', 'off')
                    idx = self.mc_combo.findData(mc_s)
                    if idx >= 0:
                        self.mc_combo.setCurrentIndex(idx)
                    mc_fps = int(settings.get('motion_comp_fps', 60))
                    idx = self.mc_fps_combo.findData(mc_fps)
                    if idx >= 0:
                        self.mc_fps_combo.setCurrentIndex(idx)
                    sr_s = settings.get('superres_scale', 'off')
                    idx = self.sr_combo.findData(sr_s)
                    if idx >= 0:
                        self.sr_combo.setCurrentIndex(idx)
                    sr_d = int(settings.get('superres_detail', 0))
                    self.sr_detail_slider.setValue(sr_d)
                    self.sr_detail_label.setText(str(sr_d))
                    sp = settings.get('shader_preset', 'off')
                    idx = self.shader_combo.findData(sp)
                    if idx < 0:
                        idx = self.shader_combo.findData('off')
                    if idx >= 0:
                        self.shader_combo.setCurrentIndex(idx)
            finally:
                self._loading = False

    def _on_autocrop_clicked(self):
        """触发动态裁剪黑边"""
        svc = getattr(self.window, 'autocrop_service', None)
        if not svc:
            self._show_osd(self.window.language_manager.tr('osd_autocrop_unavailable', '裁剪服务未初始化'))
            return
        tr = self.window.language_manager.tr
        self.autocrop_btn.setEnabled(False)
        self._show_osd(tr('osd_autocrop_analyzing', '正在分析黑边...'))

        def _on_done(success, crop, message):
            def _ui_update():
                self.autocrop_btn.setEnabled(True)
                self._show_osd(message)
            from utils.thread_safety import invoke_on_thread
            invoke_on_thread(self, _ui_update)

        try:
            svc.analyze_and_apply(_on_done)
        except Exception as e:
            self.autocrop_btn.setEnabled(True)
            logger.error(f"自动裁剪黑边失败: {e}")
            self._show_osd(tr('autocrop_failed', '自动裁剪失败'))

    def _on_remove_crop_clicked(self):
        """移除裁剪滤镜"""
        svc = getattr(self.window, 'autocrop_service', None)
        if svc:
            ok = svc.remove_crop()
            tr = self.window.language_manager.tr
            self._show_osd(tr('osd_crop_removed', '已移除裁剪') if ok else tr('osd_crop_remove_failed', '移除失败'))

    def _apply_now(self, silent: bool = False):
        """应用所有参数到当前播放"""
        eq = self._collect_eq()
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.apply_video_eq(eq)
            # 应用运动补偿
            mc_strength = eq.get('motion_comp', 'off')
            mc_fps = int(eq.get('motion_comp_fps', 60))
            if hasattr(pc, 'set_motion_compensation'):
                pc.set_motion_compensation(mc_strength, mc_fps)
            # 应用分辨率提升
            sr_scale = eq.get('superres_scale', 'off')
            sr_detail = int(eq.get('superres_detail', 0))
            if hasattr(pc, 'set_super_resolution'):
                pc.set_super_resolution(sr_scale, sr_detail)
            # 应用用户着色器
            shader_preset = eq.get('shader_preset', 'off')
            if hasattr(pc, 'set_user_shader'):
                pc.set_user_shader(shader_preset)
            if not silent:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('video_eq_applied', '图像参数已应用'))
        elif not silent:
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('video_eq_applied', '图像参数已应用'))

    def _save(self):
        """保存到配置文件"""
        try:
            eq = self._collect_eq()
            self.window.config.save_video_eq(eq)
            self.style_saved.emit(eq)
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('video_eq_saved', '图像参数已保存'))
        except Exception as e:
            logger.error(f"保存视频 EQ 失败: {e}")

    def _reset_all(self):
        """重置所有参数为默认"""
        defaults = self.window.config.VIDEO_EQ_DEFAULTS.copy()
        self._loading = True
        try:
            self._set_ui_from_dict(defaults)
        finally:
            self._loading = False
        pc = self.window.player_controller
        if pc and pc.is_playing:
            # 仅重置图像参数，旋转/翻转也清除
            pc.reset_video_eq()
            pc.set_video_rotate(0)
            pc.set_video_flip('')
            if hasattr(pc, 'clear_video_crop'):
                pc.clear_video_crop()
            # 重置运动补偿和分辨率提升
            if hasattr(pc, 'clear_motion_compensation'):
                pc.clear_motion_compensation()
            if hasattr(pc, 'clear_super_resolution'):
                pc.clear_super_resolution()
            if hasattr(pc, 'clear_user_shader'):
                pc.clear_user_shader()
        tr = self.window.language_manager.tr
        if hasattr(self.window, '_show_osd_feedback'):
            self.window._show_osd_feedback(tr('video_eq_reset_done', '图像参数已重置'))

    def _show_osd(self, text: str):
        if hasattr(self.window, '_show_osd_feedback'):
            self.window._show_osd_feedback(text)

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
