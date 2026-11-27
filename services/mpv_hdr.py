"""MpvHdr — 从 MpvPlayerController 提取的子控制器。

HDR 输出模式（与界面、右键菜单保持一致，只有三个）：
- passthrough: 直通。按片源元数据输出 HDR，需要系统 HDR 开启；
  PQ 片源用 target-colorspace-hint-mode=source 真正透传元数据。
- tonemap: 色调映射到 SDR。关闭 colorspace hint，让 target-prim/trc/peak
  真正决定输出（bt.709 + 系统对应的 SDR gamma + 100nit），高光做压缩。
- disable: 强制 SDR。同样关闭 colorspace hint，但用 clip 曲线不压缩高光，
  画面更亮、超过 SDR 的高光会被硬切。

旧配置里的 auto / scrgb 会在读取时归一到 passthrough（历史上三者实现相同）。
"""

from PySide6.QtCore import QTimer

import os

from core.log_manager import global_logger as logger
from utils.platform_utils import is_windows, is_macos, is_android, is_linux

HDR_MODE_PASSTHROUGH = 'passthrough'
HDR_MODE_TONEMAP = 'tonemap'
HDR_MODE_DISABLE = 'disable'
HDR_MODES = (HDR_MODE_PASSTHROUGH, HDR_MODE_TONEMAP, HDR_MODE_DISABLE)
_LEGACY_HDR_MODE_MAP = {'auto': HDR_MODE_PASSTHROUGH, 'scrgb': HDR_MODE_PASSTHROUGH}


def normalize_hdr_mode(mode) -> str:
    """把历史配置值归一到当前三种模式，未知值回退到 disable。"""
    value = str(mode or '').strip().lower()
    value = _LEGACY_HDR_MODE_MAP.get(value, value)
    return value if value in HDR_MODES else HDR_MODE_DISABLE


class MpvHdr:
    """MpvHdr — 通过 facade 访问 mpv 实例和播放器。"""

    # 网络流在 FILE_LOADED 时 video-params 可能还是空的，延时复查三次
    _RECHECK_DELAYS_MS = (700, 1600, 3200)

    def __init__(self, facade):
        self._facade = facade

    # ==================== 对外入口 ====================

    def _apply_hdr_on_file_loaded(self):
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return
            mode = self._current_mode()

            vp_prim = (self._facade._get_mpv_property_string('video-params/primaries') or '').lower()
            vp_gamma = (self._facade._get_mpv_property_string('video-params/gamma') or '').lower()
            vp_peak = self._facade._get_mpv_property_double('video-params/sig-peak') or 0
            vp_format = (self._facade._get_mpv_property_string('video-format') or '').lower()
            vp_cm = (self._facade._get_mpv_property_string('video-params/colormatrix') or '').lower()

            self._facade.logger.info(
                f"视频HDR参数: primaries={vp_prim}, gamma={vp_gamma}, "
                f"sig_peak={vp_peak}, format={vp_format}, colormatrix={vp_cm}"
            )

            # gamma 是 HDR 判定的主依据。网络/直播流在 FILE_LOADED 时常常还没探测完，
            # 直接按 SDR 重置会让 HDR 片源整段显示错误，这里延时复查而不是立刻下结论。
            if not vp_gamma:
                if self._schedule_hdr_recheck():
                    self._facade.logger.info("视频色彩参数尚未就绪，延时复查HDR")
                    return
                self._facade.logger.warning("多次复查后仍无色彩参数，按SDR处理")

            hdr_type = self.detect_hdr_type(vp_cm, vp_gamma, vp_peak, vp_format, vp_prim)
            self._facade.logger.info(f"HDR类型判定: {hdr_type}")
            # 基础层传输特性单独判断：杜比视界片源也要按基础层（PQ / HLG）输出
            is_pq = 'pq' in vp_gamma or 'smpte2084' in vp_gamma
            is_hlg = 'hlg' in vp_gamma or 'arib-std-b67' in vp_gamma

            if hdr_type == 'WCG':
                self._facade.logger.info("WCG视频（宽色域SDR），保持bt.2020色域")
                self._facade._apply_wcg_config()
                return

            if not (is_pq or is_hlg):
                self._facade.logger.info("非HDR视频，重置HDR参数为默认值")
                self._facade._reset_hdr_params()
                return

            if hdr_type == 'DV':
                # 面板支持 DV 才尝试原样送屏；否则一律按基础层输出，绝不猜测
                dv_profile, dv_panel, dv_convert, dv_path = self._resolve_dv_path()
                self._facade.logger.info(
                    f"杜比视界: profile={dv_profile or '未知'} 面板直通={dv_panel} "
                    f"渲染转换={dv_convert} 路径={dv_path}")
                if dv_path == 'dv-passthrough':
                    self._facade._apply_passthrough_config(is_pq)
                    return
                if dv_path == 'base-warn':
                    # profile 5 且渲染器不能正确转换：按基础层输出避免黑屏，
                    # 但必须如实告知颜色可能异常，不能假装正常
                    self._show_osd("杜比视界 profile 5：当前设备无法正确转换，颜色可能异常")
                    self._facade.logger.warning(
                        "杜比视界 profile 5 且渲染器无转换能力，按基础层输出，颜色可能异常")

            system_hdr = self._check_system_hdr()

            if mode == HDR_MODE_PASSTHROUGH:
                if not system_hdr:
                    self._facade.logger.warning("系统未启用HDR，直通回退到色调映射")
                    self._show_osd("系统 HDR 未开启，已回退色调映射")
                    self._facade._apply_tonemap_config(
                        is_hlg=is_hlg, system_hdr=False, force_sdr=False)
                else:
                    self._facade._apply_passthrough_config(is_pq)
                return

            if mode == HDR_MODE_DISABLE:
                self._facade._apply_disable_config(system_hdr=system_hdr)
                return

            self._facade._apply_tonemap_config(
                is_hlg=is_hlg, system_hdr=system_hdr, force_sdr=True)

        except Exception as e:
            self._facade.logger.error(f"应用HDR设置失败: {e}")

    # ==================== 内部工具 ====================

    def _current_mode(self) -> str:
        return normalize_hdr_mode(
            self._facade._playback_settings.get('hdr_output_mode', HDR_MODE_DISABLE))

    def _hdr_screen_name(self):
        """播放窗口所在显示器名；Qt 在 Windows 上返回显示器友好名。"""
        try:
            widget = getattr(self._facade, 'video_widget', None)
            screen = widget.screen() if widget is not None and hasattr(widget, 'screen') else None
            if screen is None:
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                screen = app.primaryScreen() if app is not None else None
            return screen.name() if screen is not None else None
        except Exception as _e:
            logger.debug(f"获取播放窗口显示器失败: {_e}")
            return None

    def _check_system_hdr(self) -> bool:
        """运行时检测系统 HDR 状态；Windows 按播放窗口所在显示器判断。"""
        try:
            if is_windows():
                from utils.hdr_detect import is_windows_hdr_enabled
                enabled = is_windows_hdr_enabled(self._hdr_screen_name())
                logger.info(f"系统HDR状态: {'已启用' if enabled else '未启用'}")
                return enabled
            elif is_macos():
                from utils.hdr_detect import is_macos_hdr_enabled
                return is_macos_hdr_enabled()
            elif is_android():
                from utils.hdr_detect import is_android_hdr_enabled
                return is_android_hdr_enabled()
            elif is_linux():
                from utils.hdr_detect import is_linux_hdr_enabled
                return is_linux_hdr_enabled()
        except Exception as _e:
            logger.debug(f"系统HDR检测失败: {_e}")
        return False

    def _dv_source_profile(self):
        """片源杜比视界 profile。

        优先级：开发者强制值 → 播放会话设置 → 扫描阶段按 URL 登记的 profile →
        本地文件的兜底探测。mpv 本身不暴露 profile，直写路径也读不到 DV 标记，
        所以必须靠这条链路，不能依赖内核报告。
        """
        env = (os.environ.get('GUANGYU_DV_PROFILE') or '').strip()
        if env.isdigit():
            return int(env)
        try:
            raw = self._facade._playback_settings.get('dv_profile')
            if raw not in (None, ''):
                return int(raw)
        except (TypeError, ValueError):
            pass
        try:
            from utils.hdr_detect import get_dv_profile, probe_dv_profile
            path = self._facade._get_mpv_property_string('path') or ''
            profile = get_dv_profile(path)
            if profile is None:
                profile = probe_dv_profile(path)
            return profile
        except Exception:
            return None

    def _resolve_dv_path(self):
        """按“片源 profile × 面板能力 × 渲染器转换能力”决定杜比视界路径。

        只有面板明确支持且走解码器直写通路时才尝试 DV 原样输出；
        未知与不支持走同一条基础层安全路径，绝不猜测。
        """
        from utils.hdr_detect import (
            get_dolby_vision_output_capability,
            get_renderer_dv_convert_capability,
            DV_STATE_SUPPORTED,
        )
        profile = self._dv_source_profile()
        panel = get_dolby_vision_output_capability(self._hdr_screen_name())
        try:
            vo = (self._facade._get_mpv_property_string('current-vo') or '').lower()
        except Exception:
            vo = ''
        convert = get_renderer_dv_convert_capability(vo)

        if panel == DV_STATE_SUPPORTED and vo == 'mediacodec_embed':
            path = 'dv-passthrough'
        elif profile == 5 and convert != DV_STATE_SUPPORTED:
            path = 'base-warn'
        else:
            path = 'base'
        # 诊断面板要能看到探测原始值与最终路径
        self._facade._last_dv_decision = (
            f"profile={profile or '未知'}, 面板={panel}, 转换={convert}, 路径={path}")
        return profile, panel, convert, path

    def _sdr_hint_value(self) -> str:
        """SDR 内容/色调映射时的 colorspace hint。

        只有 tonemap/disable 两种模式需要“真正切到 SDR 输出”，此时 hint 必须关闭，
        否则 Windows 会按显示器 HDR 能力把输出重新拉回 PQ，target-* 全部失效。
        passthrough 模式下 SDR 内容沿用系统目标，避免 PQ swapchain 上的 SDR 发暗。
        """
        return 'no' if self._current_mode() in (HDR_MODE_TONEMAP, HDR_MODE_DISABLE) else 'yes'

    def _show_osd(self, text: str):
        try:
            show = getattr(self._facade, 'show_osd', None)
            if callable(show):
                show(text, 3000)
        except Exception as _e:
            logger.debug(f"显示HDR提示失败: {_e}")

    def _schedule_hdr_recheck(self) -> bool:
        """video-params 未就绪时延时复查；返回 True 表示已排队（本次不处理）。"""
        facade = self._facade
        attempts = int(getattr(facade, '_hdr_recheck_attempts', 0))
        if attempts >= len(self._RECHECK_DELAYS_MS):
            return False
        if getattr(facade, '_hdr_recheck_pending', False):
            return True
        url = facade.current_url
        facade._hdr_recheck_attempts = attempts + 1
        facade._hdr_recheck_pending = True
        delay = self._RECHECK_DELAYS_MS[attempts]

        def _retry():
            facade._hdr_recheck_pending = False
            try:
                if getattr(facade, '_terminated', False) or not facade.mpv_handle:
                    return
                if facade.current_url != url:
                    return
                self._apply_hdr_on_file_loaded()
            except Exception as _e:
                facade.logger.debug(f"HDR延时复查失败: {_e}")

        QTimer.singleShot(delay, _retry)
        return True

    # ==================== 三种输出模式 ====================

    def _apply_passthrough_config(self, is_pq=True):
        """按片源元数据直出 HDR。

        PQ（HDR10/HDR10+）：target-colorspace-hint=yes + hint-mode=source，
        由 Windows 合成器直接按片源元数据输出，不做 tone mapping。
        HLG：Windows 只有 PQ 容器，mpv 负责 HLG→PQ 转换，参考白 1000nit。
        """
        self._facade._set_mpv_string('target-colorspace-hint', 'yes')
        self._facade._set_mpv_string('gamut-mapping-mode', 'relative')
        self._facade._set_mpv_string('target-prim', 'bt.2020')
        self._facade._set_mpv_string('target-trc', 'pq')
        if is_pq:
            self._facade._set_mpv_string('target-colorspace-hint-mode', 'source')
            self._facade._set_mpv_string('tone-mapping', 'clip')
            self._facade._set_mpv_string('hdr-compute-peak', 'no')
            self._facade._set_mpv_string('target-peak', '10000')
            self._facade.logger.info(
                "HDR配置: 直通 → PQ按片源元数据输出 (hint=source, bt.2020/pq)")
        else:
            self._facade._set_mpv_string('target-colorspace-hint-mode', 'target')
            self._facade._set_mpv_string('tone-mapping', 'auto')
            self._facade._set_mpv_string('hdr-compute-peak', 'no')
            self._facade._set_mpv_string('target-peak', '1000')
            self._facade.logger.info(
                "HDR配置: 直通 → HLG转PQ (bt.2020/pq, target-peak=1000, compute-peak=no)")

    def _apply_tonemap_config(self, is_hlg=False, system_hdr=None, force_sdr=True):
        """HDR→SDR 色调映射。

        force_sdr=True 时关闭 colorspace hint，target-prim/trc/peak 才真正生效；
        passthrough 模式下因系统 HDR 关闭而回退时 force_sdr=False，沿用系统 SDR 目标。
        """
        sdr_trc = self._sdr_target_trc(system_hdr)
        self._facade._set_mpv_string(
            'target-colorspace-hint', 'no' if force_sdr else 'yes')
        self._facade._set_mpv_string('tone-mapping', 'auto')
        self._facade._set_mpv_string(
            'hdr-compute-peak', 'yes' if is_hlg else 'no')
        self._facade._set_mpv_string('target-prim', 'bt.709')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', 'perceptual')
        self._facade.logger.info(
            f"HDR配置: 色调映射 → SDR (bt.709/{sdr_trc}, target-peak=100, "
            f"gamut=perceptual, hint={'no' if force_sdr else 'yes'})")

    def _apply_disable_config(self, system_hdr=None):
        """强制 SDR：关闭 colorspace hint 并固定 bt.709/SDR 目标，用 clip 曲线。"""
        sdr_trc = self._sdr_target_trc(system_hdr)
        self._facade._set_mpv_string('target-colorspace-hint', 'no')
        self._facade._set_mpv_string('tone-mapping', 'clip')
        self._facade._set_mpv_string('hdr-compute-peak', 'no')
        self._facade._set_mpv_string('target-prim', 'bt.709')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', 'clip')
        self._facade.logger.info(
            f"HDR配置: 强制SDR (bt.709/{sdr_trc}, target-peak=100, clip, hint=no)")

    def _apply_wcg_config(self):
        """WCG 视频（宽色域 SDR）：保持 bt.2020 色域，SDR 亮度。"""
        sdr_trc = self._sdr_target_trc(None)
        self._facade._set_mpv_string('target-colorspace-hint', self._sdr_hint_value())
        self._facade._set_mpv_string('tone-mapping', 'auto')
        self._facade._set_mpv_string('hdr-compute-peak', 'no')
        self._facade._set_mpv_string('target-prim', 'bt.2020')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', 'relative')
        self._facade.logger.info(
            f"HDR配置: WCG → 保持bt.2020色域 (bt.2020/{sdr_trc}, target-peak=100)")

    def _sdr_target_trc(self, system_hdr=None) -> str:
        """SDR 输出的 target-trc。

        Windows HDR 模式下桌面运行在 sRGB 线性空间，SDR 内容需用 srgb gamma；
        SDR 桌面则用 bt.1886。
        """
        try:
            if is_windows():
                if system_hdr is None:
                    from utils.hdr_detect import is_windows_hdr_enabled
                    system_hdr = is_windows_hdr_enabled(self._hdr_screen_name())
                return 'srgb' if system_hdr else 'bt.1886'
        except Exception as _e:
            logger.debug(f"获取SDR目标gamma失败: {_e}")
        return 'bt.1886'

    def _get_sdr_target_trc(self):
        return self._sdr_target_trc(None)

    def _reset_hdr_params(self):
        """非 HDR 视频：回到 SDR 默认值（全部使用合法值，不用空串）。"""
        sdr_trc = self._sdr_target_trc(None)
        self._facade._set_mpv_string('target-colorspace-hint', self._sdr_hint_value())
        self._facade._set_mpv_string('tone-mapping', 'auto')
        self._facade._set_mpv_string('hdr-compute-peak', 'auto')
        self._facade._set_mpv_string('target-prim', 'bt.709')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', 'auto')
        self._facade.logger.info(
            f"HDR配置: 已重置为SDR默认值 (bt.709/{sdr_trc}, target-peak=100)")

    @staticmethod
    def detect_hdr_type(colormatrix: str, gamma: str, sig_peak: float,
                        video_format: str = '', primaries: str = '') -> str:
        """统一 HDR 类型检测逻辑（PC/Android/Web 三端共用此算法）。

        检测优先级：杜比视界 → PQ(HDR10) → HLG → WCG → SDR

        注意：
        - 杜比视界：mpv 会把 DV 片源的 colormatrix 报成 dolbyvision（p5 与 p8 都是），
          这里据此返回 'DV'；但 mpv 不暴露 DV profile，profile 需要扫描阶段提供。
        - mpv 运行时无法区分 HDR10 与 HDR10+（ST.2094-40 动态元数据不暴露为属性），
          统一返回 'HDR10'。HDR10+ 的检测仅在 ffprobe 扫描阶段通过 side_data 完成。
        - WCG（宽色域 SDR）：BT.2020 色域 + SDR 亮度，需要保持广色域避免压缩偏色。
        - sig_peak 用于辅助判断（mpv 中 1.0≈SDR 白电平，HDR 内容通常 >1.0），
          但不作为 HDR10/HDR10+ 的区分依据。
        """
        g = (gamma or '').lower()
        cm = (colormatrix or '').lower()
        prim = (primaries or '').lower()

        is_dv = 'dolbyvision' in cm or 'dovi' in cm
        is_pq = 'pq' in g or 'smpte2084' in g
        is_hlg = 'hlg' in g or 'arib-std-b67' in g
        is_bt2020 = ('bt.2020' in cm or 'bt2020' in cm or 'bt.2100' in cm or
                     'bt.2020' in prim or 'bt2020' in prim or 'bt.2100' in prim)

        if is_dv:
            return 'DV'
        if is_pq:
            return 'HDR10'
        if is_hlg:
            return 'HLG'
        if is_bt2020 and sig_peak <= 1.0:
            return 'WCG'
        if is_bt2020 and sig_peak > 1.0:
            return 'HLG'
        return 'SDR'
