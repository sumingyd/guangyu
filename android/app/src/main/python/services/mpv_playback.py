"""MpvPlayback — 从 MpvPlayerController 提取的子控制器。"""

import ctypes
import os
import threading

from PySide6.QtCore import QTimer
from core.log_manager import global_logger as logger
from utils.platform_utils import (
    is_windows, is_macos, is_linux, is_android,
)
from services.mpv_common import (
    mpv_event,
    mpv_event_end_file,
    mpv_event_log_message,
    mpv_event_property,
    MPV_EVENT_NONE,
    MPV_EVENT_END_FILE,
    MPV_EVENT_FILE_LOADED,
    MPV_EVENT_PROPERTY_CHANGE,
    MPV_EVENT_LOG_MESSAGE,
    MPV_FORMAT_STRING,
    MPV_FORMAT_FLAG,
    MPV_END_FILE_REASON_EOF,
    MPV_END_FILE_REASON_ERROR,
    MPV_END_FILE_REASON_STOP,
    MPV_END_FILE_REASON_QUIT,
    get_property_string as _mpv_get_property_string,
    get_property_int as _mpv_get_property_int,
    get_property_double as _mpv_get_property_double,
    create_mpv_handle,
    initialize_mpv,
    destroy_mpv,
    terminate_destroy_mpv,
    set_property_string as _mpv_set_property_string,
    set_property_int64 as _mpv_set_property_int64,
    set_option_string as _mpv_set_option_string,
    send_command as _mpv_send_command,
    observe_property as _mpv_observe_property,
    get_property_node as _mpv_get_property_node,
    DEFAULT_USER_AGENT,
)


class MpvPlayback:
    """MpvPlayback — 通过 facade 访问 mpv 实例和播放器。"""

    def __init__(self, facade):
        self._facade = facade

    def _adjust_buffer_for_content(self):
        try:
            if not self._facade.mpv_handle:
                return
            url = self._facade.current_url
            if not url:
                return
            u = url.lower()
            is_network = (u.startswith(('http://', 'https://', 'rtmp://', 'rtsp://', 'rtp://', 'udp://')) or
                          '.m3u8' in u)
            is_net_drive = not is_network and self._facade._is_network_drive(url)
            if not is_network and not is_net_drive:
                return
            w = self._facade._get_mpv_property_int('width') or 0
            h = self._facade._get_mpv_property_int('height') or 0
            duration = self._facade._get_mpv_property_double('duration') or 0
            file_size = 0
            try:
                fs_str = self._facade._get_mpv_property_string('file-size')
                if fs_str:
                    file_size = int(fs_str)
            except Exception as _e:
                logger.debug(f"unexpected error: {_e}")
            is_4k = (w >= 3840 or h >= 2160)
            is_hdr = False
            try:
                gamma = (self._facade._get_mpv_property_string('video-params/gamma') or '').lower()
                vf = (self._facade._get_mpv_property_string('video-format') or '').lower()
                # 统一 HDR 检测（与 detect_hdr_type 对齐）
                is_hdr = ('pq' in gamma or 'smpte2084' in gamma or
                          'hlg' in gamma or 'arib-std-b67' in gamma or
                          'dovi' in vf or 'dvhe' in vf or 'dvh1' in vf or 'dav1' in vf)
            except Exception as _e:
                logger.debug(f"unexpected error: {_e}")
            is_large_file = file_size > 10 * 1024 * 1024 * 1024 or (duration > 3600 and is_4k)
            if not is_4k and not is_hdr and not is_large_file:
                return
            cache_secs = 120
            max_bytes_mib = 1024
            probesize = 50000000
            analyzeduration = 10
            if is_4k and is_hdr:
                cache_secs = 180
                max_bytes_mib = 2048
                probesize = 100000000
                analyzeduration = 15
            elif is_4k:
                cache_secs = 150
                max_bytes_mib = 1536
                probesize = 80000000
                analyzeduration = 12
            if is_large_file:
                cache_secs = max(cache_secs, 240)
                max_bytes_mib = max(max_bytes_mib, 3072)
            self._facade._set_cache_param('cache-secs', str(cache_secs))
            self._facade._set_cache_param('demuxer-max-bytes', f'{max_bytes_mib}MiB')
            self._facade._set_mpv_string('demuxer-max-back-bytes', f'{max_bytes_mib // 2}MiB')
            self._facade._set_mpv_string('demuxer-lavf-probesize', str(probesize))
            self._facade._set_mpv_string('demuxer-lavf-analyzeduration', str(analyzeduration))
            self._facade.logger.info(
                f"动态缓冲调整: {w}x{h} HDR={is_hdr} large={is_large_file} "
                f"-> cache={cache_secs}s max={max_bytes_mib}MiB "
                f"probesize={probesize}"
            )
        except Exception as e:
            self._facade.logger.debug(f"动态缓冲调整失败: {e}")

    def _apply_osd_colors(self):
        if not self._facade.mpv_handle or self._facade._terminated:
            return
        try:
            from ui.styles import AppStyles
            colors = AppStyles._get_colors()
            osd_fg = colors.get('osd_text', '#ffffff')
            osd_border = colors.get('osd_border', '#000000')
            osd_shadow = colors.get('osd_shadow', '#000000')
            self._facade._set_mpv_string('osd-color', osd_fg)
            self._facade._set_mpv_string('osd-border-color', osd_border)
            self._facade._set_mpv_string('osd-shadow-color', osd_shadow)
            font_family = colors.get('font_family', "'Segoe UI', 'Microsoft YaHei', sans-serif")
            mpv_font = font_family.split(",")[0].strip("' \"")
            self._facade._set_mpv_string('osd-font', mpv_font)
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

    def _capture_thumbnail(self):
        if not self._facade.is_playing or not self._facade.current_url:
            return
        # 纯音频频道（如电视伴音）没有视频帧，截图必然失败
        if not self._facade._has_video_track():
            self._facade.logger.debug("纯音频频道，跳过缩略图截图")
            return
        try:
            import hashlib
            from utils.app_paths import get_cache_dir
            cache_dir = os.path.join(get_cache_dir(), 'thumbnails')
            os.makedirs(cache_dir, exist_ok=True)
            url_hash = hashlib.md5(self._facade.current_url.encode('utf-8')).hexdigest()
            filepath = os.path.join(cache_dir, f"{url_hash}.png")
            if os.path.exists(filepath):
                return
            # 异步执行截图，避免在 GUI 线程阻塞 mpv 渲染管线导致播放卡顿
            import threading
            handle = self._facade.mpv_handle
            if not handle or self._facade._terminated:
                return

            def _do_screenshot():
                with self._facade._lock:
                    if self._facade._terminated or self._facade.mpv_handle is not handle:
                        return
                try:
                    from services.mpv_common import send_command as _async_send
                    _async_send(handle, ['screenshot-to-file', filepath, 'video'])
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")
            threading.Thread(target=_do_screenshot, daemon=True).start()
            QTimer.singleShot(1500, lambda: self._facade._check_thumbnail_saved(filepath) if not self._facade._terminated else None)
        except Exception as e:
            self._facade.logger.debug(f"缩略图截取失败: {e}")

    def _check_thumbnail_saved(self, filepath):
        try:
            if self._facade._terminated:
                return
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                self._facade._safe_emit(self._facade.thumbnail_captured, self._facade.current_url)
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

    @staticmethod
    def _detect_bdmv_path(path):
        if not path or not os.path.isdir(path):
            return None
        bdmv_dir = os.path.join(path, 'BDMV')
        if os.path.isdir(bdmv_dir):
            stream_dir = os.path.join(bdmv_dir, 'STREAM')
            if os.path.isdir(stream_dir):
                m2ts_files = [f for f in os.listdir(stream_dir) if f.lower().endswith('.m2ts')]
                if m2ts_files:
                    return path
        for item in os.listdir(path):
            sub = os.path.join(path, item)
            if os.path.isdir(sub):
                sub_bdmv = os.path.join(sub, 'BDMV')
                if os.path.isdir(sub_bdmv):
                    stream_dir = os.path.join(sub_bdmv, 'STREAM')
                    if os.path.isdir(stream_dir):
                        m2ts_files = [f for f in os.listdir(stream_dir) if f.lower().endswith('.m2ts')]
                        if m2ts_files:
                            return sub
        return None

    def _ensure_mpv_initialized(self):
        if self._facade._mpv_initialized:
            return True

        try:
            import services.mpv_common as _mpv_mod
            if not _mpv_mod._ensure_libmpv_loaded():
                error_msg = getattr(_mpv_mod, '_last_load_error', '') or "libmpv加载失败"
                self._facade.logger.error(error_msg)
                self._facade._safe_emit(self._facade.play_error, error_msg)
                return False

            if not _mpv_mod.MPV_AVAILABLE or _mpv_mod.libmpv is None:
                error_msg = getattr(_mpv_mod, '_last_load_error', '') or "libmpv加载失败"
                self._facade.logger.error(error_msg)
                self._facade._safe_emit(self._facade.play_error, error_msg)
                return False

            self._facade.mpv_handle = create_mpv_handle()
            if not self._facade.mpv_handle:
                error_msg = "创建mpv实例失败"
                self._facade.logger.error(error_msg)
                self._facade._safe_emit(self._facade.play_error, error_msg)
                return False

            self._facade.video_widget.show()
            self._facade.video_widget.repaint()

            # macOS使用vo=libmpv + render API时不需要设置wid
            _skip_wid = False
            if is_macos():
                try:
                    from services.mpv_gl_widget import MpvGLWidget
                    _skip_wid = isinstance(self._facade.video_widget, MpvGLWidget)
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")

            if not _skip_wid:
                try:
                    from PySide6.QtWidgets import QApplication
                    QApplication.processEvents()
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")

                if is_linux():
                    self._facade.logger.info(
                        f"Linux窗口环境: QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM', '<未设置>')}, "
                        f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '<未设置>')}, "
                        f"WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', '<未设置>')}"
                    )

                window_id = self._facade.video_widget.winId()
                if hasattr(window_id, 'value'):
                    window_id = window_id.value

                try:
                    window_id_int = int(window_id)
                    if window_id_int > 0:
                        ret = _mpv_set_option_string(self._facade.mpv_handle, 'wid', f"{window_id_int}")
                        if ret < 0:
                            self._facade.logger.error(f"设置wid失败，错误码: {ret}, 窗口ID: {window_id_int}")
                        else:
                            self._facade.logger.info(f"设置窗口ID成功: {window_id_int}")
                    else:
                        self._facade.logger.warning(f"窗口ID无效: {window_id_int}")
                except Exception as e:
                    self._facade.logger.error(f"设置窗口ID失败: {str(e)}")

            hdr_mode = self._facade._playback_settings.get('hdr_output_mode', 'disable')

            try:
                if is_windows():
                    from utils.hdr_detect import is_windows_hdr_enabled
                    _system_hdr_enabled = is_windows_hdr_enabled()
                elif is_macos():
                    from utils.hdr_detect import is_macos_hdr_enabled
                    _system_hdr_enabled = is_macos_hdr_enabled()
                elif is_android():
                    from utils.hdr_detect import is_android_hdr_enabled
                    _system_hdr_enabled = is_android_hdr_enabled()
                elif is_linux():
                    from utils.hdr_detect import is_linux_hdr_enabled
                    _system_hdr_enabled = is_linux_hdr_enabled()
                else:
                    _system_hdr_enabled = False
            except Exception as e:
                self._facade.logger.warning(f"HDR检测失败，保守使用SDR模式: {e}")
                _system_hdr_enabled = False  # noqa: F841

            self._facade._hdr_fallback_tonemap = False
            # vo 推导：auto 时始终使用 gpu-next（支持 HDR 和 SDR，gpu 不支持 HDR 信号输出）。
            # 这样无论用户启动时选什么 HDR 模式，运行时切换到 passthrough/scrgb 时，
            # vo 已经是 gpu-next，配合 target-colorspace-hint=yes 可以动态切换 swapchain。
            user_vo = str(self._facade._playback_settings.get('vo', 'auto')).lower()
            if user_vo not in ('auto', 'gpu', 'gpu-next', 'libmpv', 'direct3d'):
                user_vo = 'auto'
            if user_vo == 'auto':
                vo = 'gpu-next'
            else:
                vo = user_vo
                if hdr_mode in ('passthrough', 'scrgb', 'auto') and vo != 'gpu-next':
                    self._facade.logger.warning(
                        f"HDR模式({hdr_mode})建议使用gpu-next，但用户选了vo={vo}，HDR信号可能异常"
                    )

            # gpu-api和gpu-context必须在vo之前设置
            # 否则mpv内部锁定渲染后端后，gpu-context设置会被拒绝(错误码-7)
            # 第三阶段：支持 Vulkan GPU API，可在某些 GPU 上获得更好的性能
            gpu_api = str(self._facade._playback_settings.get('gpu_api', 'auto')).lower()
            if is_windows():
                if gpu_api == 'vulkan':
                    _mpv_set_option_string(self._facade.mpv_handle, 'gpu-api', 'vulkan')
                    _mpv_set_option_string(self._facade.mpv_handle, 'gpu-context', 'win')
                    self._facade.logger.info("使用 Vulkan GPU API（用户配置）")
                else:
                    _mpv_set_option_string(self._facade.mpv_handle, 'gpu-api', 'd3d11')
                    _mpv_set_option_string(self._facade.mpv_handle, 'd3d11-sync-interval', '1')
                # d3d11-output-csp 控制 swapchain 的初始色彩空间和底层 DXGI 格式：
                # - srgb → R8G8B8A8_UNORM（仅支持 sRGB，运行时无法切换到 PQ）
                # - pq   → R10G10B10A2_UNORM（支持 PQ 和 sRGB 之间动态切换）
                # - auto → 根据初始 target-trc 选择（默认 auto 时通常选 sRGB）
                #
                # 根因：d3d11-output-csp=auto 在初始化时创建了 R8G8B8A8_UNORM 格式的 swapchain，
                # 此格式不支持 PQ 色彩空间。运行时设置 target-trc=pq 后，target-colorspace-hint=yes
                # 会让 mpv 调用 SetColorSpace1 尝试切换到 PQ，但 R8G8B8A8_UNORM 格式不支持 PQ，
                # 切换失败，PQ 信号在 sRGB swapchain 上显示为极暗画面（用户反馈的"HDR直通画面暗"）。
                #
                # 修复：对于 HDR 模式（passthrough/scrgb/auto），设置 d3d11-output-csp=pq，
                # 让 mpv 创建 R10G10B10A2_UNORM 格式的 swapchain，运行时可通过 SetColorSpace1
                # 在 PQ 和 sRGB 之间动态切换。reinit_for_hdr_change() 切换 HDR 模式时会重新
                # 初始化 mpv，所以根据新的 hdr_mode 设置正确的 d3d11-output-csp。
                # 对于 tonemap/disable 模式，使用 srgb 即可。
                #
                # 注意：Windows 显示合成器总是支持 HDR 交换链（即使显示器是 SDR），
                # 所以 d3d11-output-csp=pq 能成功创建 swapchain。当系统 HDR 未启用时，
                # _apply_hdr_on_file_loaded() 会回退到 tonemap（target-trc=srgb），
                # target-colorspace-hint=yes 会让 mpv 将 swapchain 切换回 sRGB。
                if hdr_mode in ('passthrough', 'scrgb', 'auto'):
                    _mpv_set_option_string(self._facade.mpv_handle, 'd3d11-output-csp', 'pq')
                else:
                    _mpv_set_option_string(self._facade.mpv_handle, 'd3d11-output-csp', 'srgb')
                _mpv_set_option_string(self._facade.mpv_handle, 'target-colorspace-hint', 'yes')
                # 预设 SDR 默认值，避免 mpv auto 检测到 bt.1886（gamma≈2.4）
                # 而 _apply_wcg_config/_reset_hdr_params 设置 srgb（gamma≈2.2）时
                # 产生 gamma 跳变（首次播放 WCG 色彩偏暗）
                sdr_trc_init = self._facade._get_sdr_target_trc()
                _mpv_set_option_string(self._facade.mpv_handle, 'target-trc', sdr_trc_init)
                _mpv_set_option_string(self._facade.mpv_handle, 'target-peak', '100')
            elif is_macos():
                # macOS上mpv v0.41+的gpu-context选项不再支持wid嵌入
                # 使用vo=libmpv + render API渲染到QOpenGLWidget（IINA等播放器的标准方案）
                # 注意：即使用户在订阅设置中选了 gpu/gpu-next，macOS 也强制走 libmpv，
                # 因为 wid 嵌入在 mpv v0.41+ 已失效。这里日志提示用户其选择被覆盖。
                if vo != 'libmpv':
                    self._facade.logger.info(
                        f"macOS: 用户选择的vo={vo}被覆盖为libmpv（mpv v0.41+不再支持wid嵌入）"
                    )
                ret_vo = _mpv_set_option_string(self._facade.mpv_handle, 'vo', 'libmpv')
                if ret_vo >= 0:
                    self._facade.logger.info("macOS: 设置vo=libmpv成功，将使用render API渲染")
                    self._facade._use_render_api = True
                else:
                    self._facade.logger.warning(f"macOS: 设置vo=libmpv失败(错误码:{ret_vo})，回退wid嵌入")
                    self._facade._use_render_api = False
                    for ctx_val in ['cocoa', 'coregraphics', 'macos']:
                        ret_ctx = _mpv_set_option_string(self._facade.mpv_handle, 'gpu-context', ctx_val)
                        if ret_ctx >= 0:
                            self._facade.logger.info(f"设置gpu-context={ctx_val}成功")
                            break
                        self._facade.logger.warning(f"设置gpu-context={ctx_val}失败(错误码:{ret_ctx})")
                _mpv_set_option_string(self._facade.mpv_handle, 'force-window', 'no')
            elif is_linux():
                _mpv_set_option_string(self._facade.mpv_handle, 'gpu-api', 'opengl')
                ret_ctx = _mpv_set_option_string(self._facade.mpv_handle, 'gpu-context', 'x11')
                if ret_ctx < 0:
                    self._facade.logger.warning(f"设置gpu-context=x11失败(错误码:{ret_ctx})，尝试x11egl")
                    ret_ctx = _mpv_set_option_string(self._facade.mpv_handle, 'gpu-context', 'x11egl')
                    if ret_ctx < 0:
                        self._facade.logger.error(f"设置gpu-context=x11egl也失败(错误码:{ret_ctx})，wid嵌入可能无法工作")
                    else:
                        self._facade.logger.info("设置gpu-context=x11egl成功")
                else:
                    self._facade.logger.info("设置gpu-context=x11成功")
                _mpv_set_option_string(self._facade.mpv_handle, 'force-window', 'no')

            # 注意：_use_render_api 保存在 facade（MpvPlayerController）上，
            # MpvPlayback 自身没有该属性。之前误用 getattr(self, ...) 恒为 False，
            # 导致 macOS 上 vo 被再次改写为非 libmpv，无画面。
            if not (is_macos() and getattr(self._facade, '_use_render_api', False)):
                _mpv_set_option_string(self._facade.mpv_handle, 'vo', vo)
            # 硬解模式：auto-copy（默认，copy-back 保证 vf 滤镜可用）/ auto（原生，最快但滤镜受限）/ no（软解）
            # 兼容旧配置：bool True→auto-copy，False→no；字符串 'True'/'False' 同样处理
            hwdec_raw = self._facade._playback_settings.get('hwdec', 'auto-copy')
            if isinstance(hwdec_raw, bool):
                hwdec = 'auto-copy' if hwdec_raw else 'no'
            else:
                hwdec_str = str(hwdec_raw).lower()
                if hwdec_str in ('auto', 'auto-copy', 'no'):
                    hwdec = hwdec_str
                elif hwdec_str in ('true', '1', 'yes'):
                    hwdec = 'auto-copy'  # 旧 bool True 升级到 auto-copy，保证滤镜可用
                else:
                    hwdec = 'no'
            _mpv_set_option_string(self._facade.mpv_handle, 'hwdec', hwdec)
            _mpv_set_option_string(self._facade.mpv_handle, 'osc', 'no')
            _mpv_set_option_string(self._facade.mpv_handle, 'osd-bar', 'no')

            _mpv_set_property_string(self._facade.mpv_handle, 'osd-font-size', '18')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-border-size', '2')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-shadow-offset', '1.5')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-spacing', '0.5')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-margin-x', '24')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-margin-y', '24')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-align-x', 'left')
            _mpv_set_property_string(self._facade.mpv_handle, 'osd-align-y', 'top')
            self._facade._apply_osd_colors()
            # 按模块设置日志级别。默认只投递 warn 及以上，避免 debug 日志在 UI 线程
            # 被 100ms 的 _process_events 定时器批量解码转发导致播放卡顿
            # （demuxer/vd/ad/hwdec 的 debug 日志在播放期间会持续大量生成）。
            # 需要诊断编解码/探测问题时，设置环境变量 MPV_DEBUG_LOG=1 开启 debug 日志。
            # 注意：还需调用 mpv_request_log_messages 才能让 MPV_EVENT_LOG_MESSAGE
            # 事件被投递到事件队列，否则日志永远不会输出。
            if os.environ.get('MPV_DEBUG_LOG', '0') == '1':
                _mpv_set_property_string(
                    self._facade.mpv_handle, 'msg-level',
                    'all=fatal,demuxer=debug,vd=debug,ad=debug,hwdec=debug'
                )
                _log_request_level = b'debug'
            else:
                _mpv_set_property_string(self._facade.mpv_handle, 'msg-level', 'all=fatal')
                _log_request_level = b'warn'
            try:
                # 必须通过 _mpv_mod.libmpv 访问，不能用模块级导入的 libmpv
                # （模块级导入时 libmpv 是 None，_ensure_libmpv_loaded() 后才被赋值）
                _mpv_mod.libmpv.mpv_request_log_messages(self._facade.mpv_handle, _log_request_level)
            except Exception as _e:
                self._facade.logger.debug(f"mpv_request_log_messages 调用失败: {_e}")
            _mpv_set_property_string(self._facade.mpv_handle, 'terminal', 'no')
            _mpv_set_property_string(self._facade.mpv_handle, 'no-window-dragging', 'yes')
            _mpv_set_property_string(self._facade.mpv_handle, 'window-scale', '1.0')
            _mpv_set_property_string(self._facade.mpv_handle, 'border', 'no')

            _mpv_set_property_string(self._facade.mpv_handle, 'keep-open', 'yes')
            _mpv_set_property_string(self._facade.mpv_handle, 'idle', 'yes')
            _mpv_set_property_string(self._facade.mpv_handle, 'ytdl', 'no')

            # mpv 新版废弃 video-aspect-override=-1，需用 'no' + video-aspect-mode=container
            _mpv_set_property_string(self._facade.mpv_handle, 'video-aspect-override', 'no')
            _mpv_set_property_string(self._facade.mpv_handle, 'video-aspect-mode', 'container')
            _mpv_set_property_string(self._facade.mpv_handle, 'keepaspect', 'yes')
            _mpv_set_property_string(self._facade.mpv_handle, 'panscan', '0.0')

            ua = self._facade._playback_settings.get('user_agent', DEFAULT_USER_AGENT)
            if ua:
                _mpv_set_property_string(self._facade.mpv_handle, 'user-agent', ua)

            if not self._facade._playback_settings.get('tls_verify', True):
                _mpv_set_property_string(self._facade.mpv_handle, 'tls-verify', 'no')

            _mpv_set_property_string(self._facade.mpv_handle, 'mute', 'no')
            _mpv_set_property_string(self._facade.mpv_handle, 'audio', 'yes')
            _mpv_set_property_string(self._facade.mpv_handle, 'audio-device', 'auto')

            net_to = self._facade._playback_settings.get('network_timeout_sec', 0)
            if net_to > 0:
                _mpv_set_property_string(self._facade.mpv_handle, 'network-timeout', str(net_to))

            # 性能与卡顿优化：
            # - framedrop：视频输出慢时丢帧策略，默认 vo（VO 慢时丢帧），用户可配置
            # - cache-pause-initial=no：初始缓存阶段不暂停，避免直播流启动卡顿
            # - video-sync：音画同步基准，默认 audio（以音频时钟为基准），用户可配置
            framedrop_raw = str(self._facade._playback_settings.get('framedrop', 'vo')).lower()
            if framedrop_raw not in ('vo', 'decoder', 'insert', 'none', 'never'):
                framedrop_raw = 'vo'
            _mpv_set_property_string(self._facade.mpv_handle, 'framedrop', framedrop_raw)
            _mpv_set_property_string(self._facade.mpv_handle, 'cache-pause-initial', 'no')
            video_sync_raw = str(self._facade._playback_settings.get('video_sync', 'audio')).lower()
            if video_sync_raw not in ('audio', 'display-resample', 'display-tempo', 'resample',
                                      'display-desync', 'desync'):
                video_sync_raw = 'audio'
            _mpv_set_property_string(self._facade.mpv_handle, 'video-sync', video_sync_raw)

            # 反交错：使用 yadif=mode=1 (bob) vf 滤镜代替 mpv 的 deinterlace 属性
            # 原因：deinterlace=yes 内部用 yadif mode=0（frame mode），50i→25p 帧率减半，运动卡顿
            # yadif=mode=1 (field/bob mode) 输出 50i→50p，保持运动流畅同时消除梳齿条纹
            deinterlace_raw = str(self._facade._playback_settings.get('deinterlace', 'no')).lower()
            if deinterlace_raw not in ('yes', 'no', 'auto'):
                deinterlace_raw = 'no'
            if deinterlace_raw in ('yes', 'auto'):
                self._facade._enable_deinterlace_filter()

            passthrough = self._facade._playback_settings.get('audio_passthrough', 'never')
            if passthrough and passthrough != 'never':
                passthrough_map = {
                    'all': 'yes',
                    'hd_codecs': 'ac3,eac3,dts,dts-hd,truehd',
                    'lossless': 'flac,alac,truehd,dts-hd',
                    'spdif_only': 'ac3,eac3,dts',
                }
                pt_val = passthrough_map.get(passthrough, '')
                if pt_val:
                    _mpv_set_property_string(self._facade.mpv_handle, 'audio-spdif', pt_val)
                    _mpv_set_property_string(self._facade.mpv_handle, 'audio-passthrough', pt_val)
                    self._facade.logger.info(f"音频直通已启用: {passthrough} -> {pt_val}")

            cpu_count = os.cpu_count() or 1
            threads = max(2, cpu_count // 2)
            _mpv_set_property_string(self._facade.mpv_handle, 'vd-lavc-threads', str(threads))

            if not initialize_mpv(self._facade.mpv_handle):
                error_msg = "初始化mpv失败"
                self._facade.logger.error(error_msg)
                self._facade._safe_emit(self._facade.play_error, error_msg)
                destroy_mpv(self._facade.mpv_handle)
                self._facade.mpv_handle = None
                return False

            try:
                _mpv_observe_property(self._facade.mpv_handle, 1, 'pause', MPV_FORMAT_FLAG)
            except Exception as e:
                self._facade.logger.warning(f"订阅pause属性失败: {str(e)}")

            self._facade.logger.info("mpv播放器初始化成功")

            if is_macos() and getattr(self._facade, '_use_render_api', False):
                try:
                    if hasattr(self._facade.video_widget, 'setup_render_context'):
                        if not self._facade.video_widget.setup_render_context(self._facade.mpv_handle):
                            self._facade.logger.error("macOS render context创建失败，视频可能无法显示")
                except Exception as e:
                    self._facade.logger.error(f"macOS render context初始化异常: {e}")

            if is_macos():
                try:
                    _ver = self._facade._get_mpv_property_string('mpv-version') or '?'
                    _vo = self._facade._get_mpv_property_string('vo') or '?'
                    _ga = self._facade._get_mpv_property_string('gpu-api') or '?'
                    _gc = self._facade._get_mpv_property_string('gpu-context') or '?'
                    self._facade.logger.info(f"macOS mpv诊断: version={_ver}, vo={_vo}, gpu-api={_ga}, gpu-context={_gc}")
                except Exception as e:
                    self._facade.logger.debug(f"macOS mpv诊断读取失败: {e}")

            try:
                _vo = self._facade._get_mpv_property_string('vo') or '?'
                _tp = self._facade._get_mpv_property_string('target-prim') or '?'
                _tt = self._facade._get_mpv_property_string('target-trc') or '?'
                _tm = self._facade._get_mpv_property_string('tone-mapping') or '?'
                _tch = self._facade._get_mpv_property_string('target-colorspace-hint') or '?'
                _ga = self._facade._get_mpv_property_string('gpu-api') or '?'
                _gc = self._facade._get_mpv_property_string('gpu-context') or '?'
                _csp = self._facade._get_mpv_property_string('d3d11-output-csp') or '?'
                _tpk = self._facade._get_mpv_property_string('target-peak') or '?'
                _gmm = self._facade._get_mpv_property_string('gamut-mapping-mode') or '?'
                self._facade.logger.info(
                    f"HDR诊断: vo={_vo}, gpu-api={_ga}, gpu-context={_gc}, "
                    f"target-prim={_tp}, target-trc={_tt}, tone-mapping={_tm}, "
                    f"target-colorspace-hint={_tch}, d3d11-output-csp={_csp}, "
                    f"target-peak={_tpk}, gamut-mapping-mode={_gmm}, "
                    f"hdr_mode={hdr_mode}"
                )
            except Exception as e:
                self._facade.logger.debug(f"HDR诊断读取失败: {e}")

            # 重建事件轮询定时器前先释放旧实例，避免 HDR 重初始化后
            # 两个定时器同时轮询同一个事件队列（重复 drain、泄漏）
            _old_event_timer = getattr(self._facade, 'event_timer', None)
            if _old_event_timer:
                try:
                    _old_event_timer.stop()
                    _old_event_timer.deleteLater()
                except Exception as _e:
                    logger.debug(f"释放旧 event_timer 失败: {_e}")
            self._facade.event_timer = QTimer()
            self._facade.event_timer.timeout.connect(self._facade._process_events)
            self._facade.event_timer.start(100)

            self._facade._mpv_initialized = True
            return True

        except Exception as e:
            error_msg = f"初始化mpv播放器失败: {str(e)}"
            self._facade.logger.error(error_msg)
            self._facade._safe_emit(self._facade.play_error, error_msg)
            if self._facade.mpv_handle:
                destroy_mpv(self._facade.mpv_handle)
                self._facade.mpv_handle = None
            return False

    def _fix_unc_path(self, path):
        if not path:
            return path
        if not is_windows():
            return path
        if path.startswith('//'):
            path = '\\\\' + path[2:]
            return path.replace('/', '\\')
        if path.startswith('\\\\'):
            return path.replace('/', '\\')
        if len(path) >= 2 and path[1] == ':':
            return path.replace('/', '\\')
        return path

    def _get_video_resolution(self):
        """获取当前视频分辨率，返回 (width, height)"""
        try:
            w = self._facade._get_mpv_property_int('width') or 0
            h = self._facade._get_mpv_property_int('height') or 0
            return w, h
        except Exception:
            return 0, 0

    def _guess_protocol(self, url):
        if not url:
            return '未知'
        u = url.lower()
        if u.startswith('bd://'):
            return 'BLURAY'
        if '.m3u8' in u or u.startswith('hls+'):
            return 'HLS'
        if '.mpd' in u or u.startswith('dash+'):
            return 'DASH'
        if u.startswith('rtsp://'):
            return 'RTSP'
        if u.startswith('rtp://') or u.startswith('udp://'):
            return 'RTP/UDP'
        if u.startswith('srt://'):
            return 'SRT'
        if u.startswith('http://') or u.startswith('https://'):
            return 'HTTP'
        if u.startswith('file://') or ('://' not in url):
            if MpvPlayback._is_network_drive(url):
                return 'NET-FILE'
            return 'FILE'
        return '未知'

    def _has_video_track(self):
        """检查当前播放的流是否包含真实视频轨（非 albumart）。

        用于截图前判断：纯音频频道（如电视伴音）没有视频帧，
        screenshot-to-file 会失败并产生 ERROR 日志。
        """
        try:
            track_list_str = self._facade._get_mpv_property_string('track-list') or ''
            if not track_list_str:
                return False
            import json
            tracks = json.loads(track_list_str)
            for t in tracks:
                if t.get('type') == 'video' and not t.get('albumart', False):
                    return True
            return False
        except Exception:
            return False

    def _is_4k_or_above(self) -> bool:
        """检测当前视频是否为 4K 及以上分辨率"""
        w, h = self._facade._get_video_resolution()
        return w >= 3840 or h >= 2160

    @staticmethod
    def _is_network_drive(path):
        if not is_windows():
            path_lower = path.lower()
            return path_lower.startswith('//') or path_lower.startswith('\\\\')
        try:
            path_lower = path.lower()
            if path_lower.startswith('//') or path_lower.startswith('\\\\'):
                return True
            drive = os.path.splitdrive(path)[0]
            if not drive or len(drive) != 2 or drive[1] != ':':
                return False
            kernel32 = ctypes.windll.kernel32
            DRIVE_REMOTE = 4
            return kernel32.GetDriveTypeW(drive + '\\') == DRIVE_REMOTE
        except Exception:
            return False

    def _is_network_url(self, url):
        if not url:
            return False
        return url.lower().startswith(('http://', 'https://', 'rtsp://', 'rtp://', 'udp://', 'rtmp://'))

    def _normalize_url(self, url):
        if not url:
            return url
        u = url.lower()
        is_network = (u.startswith(('http://', 'https://', 'rtmp://', 'rtsp://', 'rtp://', 'udp://', 'file://')) or
                      '.m3u8' in u)
        if is_network:
            return url
        if self._facade._is_network_drive(url):
            fixed = self._facade._fix_unc_path(url)
            bdmv = self._facade._detect_bdmv_path(fixed)
            if bdmv:
                self._facade.logger.info(f"检测到蓝光原盘结构: {bdmv}")
                return f'bd://{bdmv}'
            if fixed != url:
                self._facade.logger.debug(f"网络路径格式修正: {url[:80]}... -> {fixed[:80]}...")
            return fixed
        bdmv = self._facade._detect_bdmv_path(url)
        if bdmv:
            self._facade.logger.info(f"检测到蓝光原盘结构: {bdmv}")
            return f'bd://{bdmv}'
        try:
            from pathlib import Path
            path = Path(url)
            if path.is_absolute():
                normalized = path.resolve().as_uri()
                if normalized != url:
                    self._facade.logger.debug(f"本地文件路径已规范化: {url[:80]}... -> {normalized[:80]}...")
                return normalized
        except Exception as e:
            self._facade.logger.debug(f"路径规范化失败，使用原始URL: {e}")
        return url

    def _prefetch_next_channels(self, next_urls):
        prefetch_count = self._facade._playback_settings.get('fcc_prefetch_count', 2)
        urls_to_prefetch = []
        for i, next_url in enumerate(next_urls[:prefetch_count]):
            if not next_url or not next_url.strip():
                continue
            urls_to_prefetch.append(next_url)

        if not urls_to_prefetch:
            return

        try:
            import services.network_preheat_service  # noqa: F401
            for next_url in urls_to_prefetch:
                dns_prefetcher = getattr(self, '_dns_prefetcher', None)
                if dns_prefetcher:
                    dns_prefetcher.prefetch(next_url)
                conn_preheater = getattr(self, '_connection_preheater', None)
                if conn_preheater:
                    conn_preheater.preheat(next_url)
            self._facade.logger.debug(f"预取{len(urls_to_prefetch)}个相邻频道的DNS/TCP连接")
        except Exception as e:
            self._facade.logger.debug(f"预取相邻频道失败(非致命): {e}")

    def _process_events(self):
        if self._facade._terminated:
            return
        with self._facade._lock:
            handle = self._facade.mpv_handle
            if not handle:
                return
        # 单次最多处理的事件数：mpv 在缓冲/日志爆发时事件可能持续到达，
        # 无上限 drain 会长时间占用 UI 线程导致画面卡顿
        max_events = 200
        processed = 0
        try:
            while not self._facade._terminated and processed < max_events:
                processed += 1
                with self._facade._lock:
                    if self._facade._terminated or self._facade.mpv_handle is not handle:
                        return
                    from services.mpv_common import libmpv as _libmpv
                    event_ptr = _libmpv.mpv_wait_event(handle, 0.0)
                    if not event_ptr:
                        return
                    event = ctypes.cast(event_ptr, ctypes.POINTER(mpv_event)).contents

                if event.event_id == MPV_EVENT_NONE:
                    return

                if event.event_id == MPV_EVENT_PROPERTY_CHANGE:
                    if event.data:
                        try:
                            import ctypes as _ctypes
                            prop = _ctypes.cast(event.data, _ctypes.POINTER(mpv_event_property)).contents
                            if prop.name:
                                name = _ctypes.cast(prop.name, _ctypes.c_char_p).value
                                if name and name.decode('utf-8', errors='ignore') == 'pause':
                                    if prop.format == MPV_FORMAT_FLAG and prop.data:
                                        val_ptr = _ctypes.cast(prop.data, _ctypes.POINTER(_ctypes.c_int)).contents
                                        new_paused = bool(val_ptr.value)
                                        if new_paused != self._facade.is_paused:
                                            self._facade.is_paused = new_paused
                                            self._facade._safe_emit(self._facade.play_state_changed, not new_paused)
                                    elif prop.format == MPV_FORMAT_STRING and prop.data:
                                        val_ptr = _ctypes.cast(prop.data, _ctypes.POINTER(_ctypes.c_char_p)).contents
                                        if val_ptr:
                                            val = val_ptr.decode('utf-8', errors='ignore')
                                            new_paused = (val == 'yes')
                                            if new_paused != self._facade.is_paused:
                                                self._facade.is_paused = new_paused
                                                self._facade._safe_emit(self._facade.play_state_changed, not new_paused)
                        except Exception as _e:
                            self._facade.logger.debug(f"处理 pause 属性变更事件失败: {_e}")

                elif event.event_id == MPV_EVENT_FILE_LOADED:
                    self._facade._reconnect_count = 0
                    self._facade._switching_channel = False
                    self._facade.is_playing = True
                    # 新文件加载成功后重置位置日志计数，否则计数器只增不减，
                    # 后续频道的前几次位置日志会被吞掉
                    self._facade._pos_log_count = 0
                    self._facade._schedule_media_info_start()
                    self._facade._adjust_buffer_for_content()
                    self._facade._apply_hdr_on_file_loaded()
                    if self._facade.audio_visual:
                        self._facade.audio_visual.auto_enable_if_audio()
                    self._facade._safe_emit(self._facade.file_loaded)

                elif event.event_id == MPV_EVENT_END_FILE:
                    if event.data:
                        end_file = ctypes.cast(event.data, ctypes.POINTER(mpv_event_end_file)).contents
                        reason = end_file.reason
                        if reason == MPV_END_FILE_REASON_EOF:
                            if self._facade._user_stopped:
                                self._facade.logger.debug("END_FILE_EOF: 用户已停止，忽略")
                            elif self._facade.current_url and self._facade._is_network_url(self._facade.current_url):
                                self._facade.logger.info("END_FILE_EOF: 流播放到终点，请求续播")
                                self._facade.is_playing = False
                                self._facade.is_paused = False
                                self._facade._safe_emit(self._facade.play_state_changed, False)
                                self._facade._safe_emit(self._facade.timeshift_continue_requested)
                            else:
                                self._facade.logger.debug("END_FILE_EOF: 非网络流，正常结束")
                                ended_url = self._facade.current_url or ''
                                # 保存播放位置（用于断点续播）
                                try:
                                    pos_sec = self._facade._get_mpv_property_double('time-pos') or 0.0
                                    dur_sec = self._facade._get_mpv_property_double('duration') or 0.0
                                    if ended_url and pos_sec > 0:
                                        self._facade._safe_emit(
                                            self._facade.local_file_position_to_save,
                                            ended_url, float(pos_sec), float(dur_sec)
                                        )
                                except Exception as e:
                                    self._facade.logger.debug(f"保存播放位置失败: {e}")
                                self._facade.is_playing = False
                                self._facade.is_paused = False
                                self._facade._safe_emit(self._facade.play_state_changed, False)
                                self._facade._safe_emit(self._facade.local_file_ended, ended_url)
                        elif reason == MPV_END_FILE_REASON_ERROR:
                            if self._facade._switching_channel:
                                # 旧流被主动 stop 时产生的是 REASON_STOP，因此切换窗口内
                                # 收到的 ERROR 只可能来自新 URL 拉流失败。之前统一按
                                # "频道切换噪声"忽略，导致换台到坏源时 UI 停在假播放，
                                # 这里清除标记后继续走正常失败/重连路径。
                                self._facade._switching_channel = False
                                self._facade.logger.warning(
                                    "END_FILE错误: 换台后新源加载失败，按播放失败处理")
                            if self._facade._user_stopped:
                                self._facade.logger.debug("END_FILE错误: 用户已停止，忽略")
                            elif self._facade.current_url:
                                is_net_file = self._facade._is_network_drive(self._facade.current_url)
                                is_network_url = self._facade.current_url.lower().startswith(
                                    ('http://', 'https://', 'rtsp://', 'rtp://', 'udp://', 'rtmp://'))
                                if not is_net_file and not is_network_url:
                                    self._facade.logger.debug(f"END_FILE错误(本地文件)，不重连: reason={reason}")
                                    self._facade.is_playing = False
                                    self._facade.is_paused = False
                                    self._facade._safe_emit(self._facade.play_state_changed, False)
                                else:
                                    err_str = (
                                        self._facade._get_mpv_error_string(end_file.error)
                                        if hasattr(end_file, 'error')
                                        else f"error_code={reason}"
                                    )
                                    self._facade.logger.warning(
                                        f"END_FILE错误，尝试重连: {err_str}, "
                                        f"is_net_file={is_net_file}"
                                    )
                                    self._facade.is_playing = False
                                    self._facade.is_paused = False
                                    self._facade._safe_emit(self._facade.play_state_changed, False)
                                    if self._facade._reconnect_count < self._facade._max_reconnect:
                                        self._facade._reconnect_count += 1
                                        self._facade.logger.info(f"断线自动重连 ({self._facade._reconnect_count}/{self._facade._max_reconnect})")
                                        self._facade._safe_emit(self._facade.reconnect_requested, self._facade.current_url)
                                    else:
                                        self._facade.logger.error("已达最大重连次数，停止重连")
                                        self._facade._reconnect_count = 0
                                        # 重连耗尽必须让用户看到明确错误，否则界面只会停在"已暂停"
                                        self._facade._safe_emit(
                                            self._facade.play_error,
                                            "重连失败，请检查网络或更换频道")
                        elif reason in (MPV_END_FILE_REASON_STOP, MPV_END_FILE_REASON_QUIT):
                            self._facade.logger.debug(f"END_FILE: 正常停止/退出 reason={reason}")
                        else:
                            self._facade.logger.warning(f"END_FILE: 未知reason={reason}")

                elif event.event_id == MPV_EVENT_LOG_MESSAGE:
                    # 将 mpv 内部日志转发到 app logger（仅 demuxer/vd/ad/hwdec 模块的 debug 日志，
                    # 由 msg-level 和 mpv_request_log_messages 共同控制）
                    if event.data:
                        try:
                            log_msg = ctypes.cast(event.data, ctypes.POINTER(mpv_event_log_message)).contents
                            prefix = log_msg.prefix.decode('utf-8', errors='ignore') if log_msg.prefix else ''
                            level = log_msg.level.decode('utf-8', errors='ignore') if log_msg.level else ''
                            text = log_msg.text.decode('utf-8', errors='ignore').rstrip() if log_msg.text else ''
                            if not text:
                                continue
                            if level in ('error', 'fatal'):
                                logger.error(f"[mpv:{prefix}] {text}")
                            elif level == 'warn':
                                logger.warning(f"[mpv:{prefix}] {text}")
                            else:
                                logger.debug(f"[mpv:{prefix}] {text}")
                        except Exception as _e:
                            logger.debug(f"处理 mpv 日志消息失败: {_e}")

        except Exception as e:
            self._facade.logger.error(f"处理 mpv 事件失败：{str(e)}")

    def _reset_demuxer_options(self):
        try:
            self._facade._set_mpv_string('demuxer', '')
            self._facade._set_mpv_string('demuxer-lavf-format', '')
            self._facade._set_mpv_string('demuxer-lavf-probesize', '5000000')
            self._facade._set_mpv_string('demuxer-lavf-analyzeduration', '5')
            self._facade._set_mpv_string('demuxer-lavf-buffersize', '')
            self._facade._set_mpv_string('cache', 'no')
            self._facade._set_mpv_string('cache-secs', '')
            self._facade._set_mpv_string('demuxer-max-bytes', '')
            self._facade._set_mpv_string('demuxer-max-back-bytes', '')
            self._facade._set_mpv_string('demuxer-readahead-secs', '')
            self._facade._set_mpv_string('force-seekable', '')
            self._facade._set_mpv_string('demuxer-seekable-cache', 'no')
            self._facade._set_mpv_string('demuxer-cache-wait', 'no')
            self._facade._set_mpv_string('rtsp-transport', '')
            self._facade.logger.debug("[mpv] 已重置demuxer/cache选项")
        except Exception as e:
            self._facade.logger.debug(f"重置demuxer选项失败: {e}")

    def _schedule_media_info_start(self):
        # 重入标记保存在 facade 上（play() 会把它重置为 False），
        # 之前读取 self 上的同名属性恒为 False，防重入完全失效
        if getattr(self._facade, '_media_info_scheduled', False):
            return
        self._facade._media_info_scheduled = True

        if hasattr(self._facade, '_live_info_timer') and self._facade._live_info_timer:
            self._facade._live_info_timer.stop()

        if hasattr(self._facade, '_media_info_timer') and self._facade._media_info_timer:
            try:
                self._facade._media_info_timer.stop()
                self._facade._media_info_timer.deleteLater()
            except Exception as _e:
                logger.debug(f"释放旧 media_info_timer 失败: {_e}")
        # 用真正的单次定时器（而不是对实例调用静态 singleShot），
        # 这样 stop() 才能真正取消"延迟启动 live info"的动作
        self._facade._media_info_timer = QTimer()
        self._facade._media_info_timer.setSingleShot(True)
        self._facade._media_info_timer.timeout.connect(self._facade._start_live_info_timer)
        self._facade._media_info_timer.start(1000)

        QTimer.singleShot(3000, self._facade._capture_thumbnail)

    def _setup_bluray_options(self):
        try:
            self._facade._set_mpv_string('demuxer', '')
            self._facade._set_mpv_string('demuxer-lavf-format', '')
            self._facade._set_mpv_string('demuxer-lavf-probesize', '100000000')
            self._facade._set_mpv_string('demuxer-lavf-analyzeduration', '20')
            self._facade._set_mpv_string('cache', 'yes')
            self._facade._set_cache_param('cache-secs', '180')
            self._facade._set_cache_param('demuxer-max-bytes', '2048MiB')
            self._facade._set_mpv_string('demuxer-max-back-bytes', '1024MiB')
            self._facade._set_cache_param('demuxer-readahead-secs', '60')
            self._facade._set_mpv_string('force-seekable', 'yes')
            self._facade._set_mpv_string('demuxer-seekable-cache', 'yes')
            self._facade.logger.debug("[mpv] 蓝光原盘选项已设置: cache=180s, probesize=100M, max=2048MiB")
        except Exception as e:
            self._facade.logger.debug(f"设置蓝光原盘选项失败: {e}")

    def _setup_network_drive_options(self):
        try:
            self._facade._set_mpv_string('demuxer', '')
            self._facade._set_mpv_string('demuxer-lavf-format', '')
            self._facade._set_mpv_string('demuxer-lavf-probesize', '50000000')
            self._facade._set_mpv_string('demuxer-lavf-analyzeduration', '10')
            # mpv 规定 demuxer-lavf-buffersize 最大值为 10485760（10MiB），
            # 超出会被拒绝并导致整个网络挂载盘配置失败（参考 app.log 错误：
            # "The demuxer-lavf-buffersize option must be <= 10485760"）
            self._facade._set_mpv_string('demuxer-lavf-buffersize', '10485760')
            self._facade._set_mpv_string('cache', 'yes')
            self._facade._set_cache_param('cache-secs', '60')
            self._facade._set_cache_param('demuxer-max-bytes', '512MiB')
            self._facade._set_mpv_string('demuxer-max-back-bytes', '256MiB')
            self._facade._set_cache_param('demuxer-readahead-secs', '30')
            self._facade._set_mpv_string('force-seekable', 'yes')
            self._facade._set_mpv_string('demuxer-seekable-cache', 'yes')
            self._facade.logger.debug("[mpv] 网络挂载盘选项已设置: cache=yes, probesize=50M, readahead=30s")
        except Exception as e:
            self._facade.logger.debug(f"设置网络挂载盘选项失败: {e}")

    def _setup_protocol_options(self, url, program_duration=0):
        if not self._facade.mpv_handle or not url:
            return
        u = url.lower()

        # FCC 频道检测：rtp2httpd 等 FCC 代理已预先加入组播并转发流，
        # 数据到达速度快且编码通常为 H.264/H.265，可使用更小的探测参数加速首帧。
        # 非 FCC 频道保留大 probesize 以兼容 CAVS 等编码。
        is_fcc = '?fcc=' in u

        is_network = (u.startswith(('http://', 'https://', 'rtmp://', 'rtsp://', 'rtp://', 'udp://')) or
                      '.m3u8' in u)
        if u.startswith('bd://'):
            self._facade._setup_bluray_options()
            return
        if not is_network:
            if self._facade._is_network_drive(url):
                self._facade._setup_network_drive_options()
                return
            self._facade._reset_demuxer_options()
            return

        settings = self._facade._playback_settings

        # 用户自定义 probesize/analyzeduration 覆盖（0 表示使用各流类型的自动值）
        _probe_override = int(settings.get('probesize_override', 0) or 0)
        _analyze_override = float(settings.get('analyzeduration_override', 0) or 0)

        def _probe(probesize, analyzeduration):
            """应用用户覆盖值（如果已配置）"""
            p = str(_probe_override) if _probe_override > 0 else str(probesize)
            a = str(_analyze_override) if _analyze_override > 0 else str(analyzeduration)
            self._facade._set_mpv_string('demuxer-lavf-probesize', p)
            self._facade._set_mpv_string('demuxer-lavf-analyzeduration', a)

        is_vod = ('playseek' in u or 'starttime=' in u or 'endtime=' in u or
                  'catchup' in u or 'timeshift' in u or 'playback' in u)

        cache_secs = max(program_duration, 3600) if program_duration > 0 else 3600
        cache_secs = min(cache_secs, 14400)
        max_bytes_mib = min(max(cache_secs * 2 // 60, 256), 4096)

        if u.startswith('rtsp://'):
            rtsp_transport = settings.get('rtsp_transport', 'tcp')
            self._facade._set_mpv_string('rtsp-transport', rtsp_transport)
            rtsp_ua = settings.get('rtsp_user_agent', 'VLC/3.0.18Libmpv')
            self._facade._set_mpv_string('user-agent', rtsp_ua)
            self._facade._set_mpv_string('cache', 'yes')
            self._facade._set_cache_param('cache-secs', str(cache_secs))
            self._facade._set_mpv_string('demuxer-lavf-format', '')
            if rtsp_transport == 'udp':
                _probe(500000, 1)
                self._facade._set_cache_param('demuxer-max-bytes', f'{max_bytes_mib}MiB')
                self._facade._set_mpv_string('demuxer-max-back-bytes', f'{max_bytes_mib}MiB')
                self._facade._set_cache_param('demuxer-readahead-secs', '5')
                self._facade._set_mpv_string('force-seekable', 'no')
                self._facade.logger.debug(f"[mpv] rtsp-udp-live cache={cache_secs} transport={rtsp_transport}")
            elif is_vod:
                _probe(5000000, 5)
                self._facade._set_mpv_string('force-seekable', 'yes')
                self._facade.logger.debug(f"[mpv] rtsp-vod cache={cache_secs} transport={rtsp_transport}")
            else:
                # 直播流需要足够的探测数据让 demuxer 识别编码格式（如 CAVS）
                # probesize=32 太少会导致 CAVS 流无法被识别（track-list 为空）
                _probe(5000000, 5)
                self._facade.logger.debug(f"[mpv] rtsp-tcp-live cache={cache_secs} transport={rtsp_transport}")
            return

        looks_ts = ('/rtp/' in u or u.endswith('.ts') or 'proto=http' in u or u.startswith('udp://'))
        if looks_ts:
            self._facade._set_mpv_string('demuxer', 'lavf')
            self._facade._set_mpv_string('demuxer-lavf-format', 'mpegts')
            if is_vod:
                _probe(5000000, 5)
                self._facade._set_mpv_string('force-seekable', 'yes')
            elif is_fcc:
                # FCC 快速换台：rtp2httpd 代理已预加入组播，流数据即时可用。
                # probesize 2MB 足够识别各种编码，analyzeduration 2s 进一步减少首帧等待。
                # （probesize 500KB 太小会导致部分频道无法识别编码 → 不出画面）
                _probe(2000000, 2)
            else:
                # 非 FCC 直播流需要足够的探测数据让 demuxer 识别编码格式（如 CAVS）
                # probesize=32 太少会导致 CAVS 流无法被识别（track-list 为空）
                _probe(5000000, 5)
            self._facade._set_mpv_string('demuxer-lavf-buffersize', '128000')
            self._facade._set_mpv_string('cache', 'yes')
            self._facade._set_mpv_string('force-seekable', 'yes')
            self._facade._set_mpv_string('demuxer-seekable-cache', 'yes')
            self._facade._set_cache_param('cache-secs', str(cache_secs))
            self._facade._set_cache_param('demuxer-max-bytes', f'{max_bytes_mib}MiB')
            self._facade._set_mpv_string('demuxer-max-back-bytes', f'{max_bytes_mib}MiB')
            self._facade._set_cache_param('demuxer-readahead-secs', '300')
            self._facade.logger.debug(
                f"[mpv] ts demux=mpegts cache={cache_secs}s "
                f"back={max_bytes_mib}MiB dur={program_duration}s fcc={is_fcc}"
            )
            return

        if '.m3u8' in u or 'format=hls' in u:
            self._facade._set_mpv_string('demuxer-lavf-format', '')
            self._facade._set_mpv_string('cache', 'yes')
            self._facade._set_cache_param('cache-secs', str(cache_secs))
            self._facade._set_cache_param('demuxer-max-bytes', f'{max_bytes_mib}MiB')
            self._facade._set_mpv_string('demuxer-max-back-bytes', f'{max_bytes_mib}MiB')
            self._facade._set_mpv_string('force-seekable', 'yes')
            self._facade._set_cache_param('demuxer-readahead-secs', '120')
            # HLS 流也需要设置 probesize/analyzeduration，否则使用 mpv 默认值
            # 可能导致部分 HLS 流（含损坏分片）无法正确识别编码
            _probe(5000000, 5)

            if settings.get('hls_start_at_live_edge', False):
                self._facade._set_mpv_string('hls-playlist-start', 'no')
            readahead = settings.get('hls_readahead_secs', 0)
            if readahead > 0:
                self._facade._set_cache_param('demuxer-readahead-secs', str(readahead))
            self._facade.logger.debug(f"[mpv] hls cache=yes seekable=yes vod={is_vod}")
            return

        self._facade._set_mpv_string('demuxer-lavf-format', '')
        if is_fcc and not is_vod:
            # FCC 频道：适度降低探测参数加速首帧（保留足够数据兼容各种编码）
            _probe(2000000, 2)
        else:
            # 显式设置 probesize/analyzeduration，确保 CAVS 等编码能被 demuxer 正确识别
            # （mpv 默认值可能因版本/平台不同而不一致）
            _probe(5000000, 5)
        self._facade._set_mpv_string('cache', 'yes')
        self._facade._set_cache_param('cache-secs', str(cache_secs))
        self._facade._set_cache_param('demuxer-max-bytes', f'{max_bytes_mib}MiB')
        self._facade._set_mpv_string('demuxer-max-back-bytes', f'{max_bytes_mib}MiB')
        self._facade._set_mpv_string('force-seekable', 'yes')
        self._facade._set_cache_param('demuxer-readahead-secs', '120')
        self._facade._set_mpv_string('demuxer-cache-wait', 'no')
        self._facade.logger.debug(f"[mpv] generic http cache=yes seekable=yes fcc={is_fcc}")

        if (u.startswith('http://') or u.startswith('https://')):
            headers = settings.get('http_headers', '')
            if headers:
                header_val = headers.replace('\r\n', '\n').replace('\n', '\\n')
                self._facade._set_mpv_string('http-header-fields', header_val)
                self._facade.logger.debug("[mpv] http-headers set")

            ua = settings.get('user_agent', DEFAULT_USER_AGENT)
            if ua:
                self._facade._set_mpv_string('user-agent', ua)

            # HTTP Referer
            referer = settings.get('http_referer', '') or ''
            if referer:
                self._facade._set_mpv_string('referrer', referer)
                self._facade.logger.debug(f"[mpv] referrer set: {referer[:50]}")
            else:
                self._facade._set_mpv_string('referrer', '')

            # HTTP/HTTPS 代理
            proxy = settings.get('http_proxy', '') or ''
            if proxy:
                # mpv 的 http-proxy 选项对 HTTP/HTTPS 流生效
                self._facade._set_mpv_string('http-proxy', proxy)
                self._facade.logger.debug(f"[mpv] http-proxy set: {proxy[:50]}")
            else:
                self._facade._set_mpv_string('http-proxy', '')

    def _start_live_info_timer(self):
        if hasattr(self._facade, '_live_info_timer') and self._facade._live_info_timer:
            self._facade._live_info_timer.timeout.disconnect()
            self._facade._live_info_timer.stop()
            self._facade._live_info_timer.deleteLater()
        self._facade._static_info_counter = self._facade._STATIC_INFO_REFRESH_TICKS
        self._facade._live_info_timer = QTimer()
        self._facade._live_info_timer.timeout.connect(self._facade._update_live_info)
        self._facade._live_info_timer.start(500)

    def _stop_live_info_timer(self):
        if hasattr(self._facade, '_live_info_timer') and self._facade._live_info_timer:
            self._facade._live_info_timer.stop()

    def _update_live_info(self):
        if self._facade._terminated or not self._facade.mpv_handle:
            return

        self._facade._static_info_counter = getattr(self._facade, '_static_info_counter', 0) + 1
        if self._facade._static_info_counter >= self._facade._STATIC_INFO_REFRESH_TICKS:
            self._facade._static_info_counter = 0
            info = self._facade.get_live_media_info()
            if info:
                self._facade._safe_emit(self._facade.live_media_info_updated, info)

        if self._facade.is_playing:
            try:
                current_time = self._facade.get_current_time()
                total_time = self._facade.get_total_time()
                position = self._facade.get_position()

                self._facade._pos_log_count = getattr(self._facade, '_pos_log_count', 0) + 1
                if self._facade._pos_log_count in (1, 2, 3, 5, 10):
                    self._facade.logger.debug(
                        f"[SRC{self._facade._pos_log_count}] total={total_time} "
                        f"cur={current_time} pos={position} "
                        f"url={self._facade.current_url[:60] if self._facade.current_url else 'None'}..."
                    )

                self._facade._safe_emit(
                    self._facade.playback_position_updated,
                    int(current_time or 0),
                    int(total_time or 0),
                    float(position or 0)
                )
            except RuntimeError:
                pass

    def add_subtitle_file(self, file_path):
        try:
            if not self._facade.mpv_handle:
                return False
            return self._facade.send_command(['sub-add', file_path, 'select']) == 0
        except Exception as e:
            self._facade.logger.error(f"加载外部字幕失败: {e}")
            return False

    def chapter_next(self) -> bool:
        """跳转到下一章"""
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return False
            return self._facade.send_command(['add', 'chapter', '1']) == 0
        except Exception as e:
            self._facade.logger.debug(f"下一章失败: {e}")
            return False

    def chapter_prev(self) -> bool:
        """跳转到上一章"""
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return False
            return self._facade.send_command(['add', 'chapter', '-1']) == 0
        except Exception as e:
            self._facade.logger.debug(f"上一章失败: {e}")
            return False

    def ensure_ready_for_load(self):
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return
            self._facade._set_mpv_string('pause', 'no')
            eof = self._facade._get_mpv_property_string('eof-reached')
            if eof and eof.lower() == 'yes':
                self._facade.send_command(['stop'])

        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

    def get_aspect_ratio(self) -> str:
        """读取当前画面比例（与 set_aspect_ratio 配对，用于播放设置持久化）"""
        return self._facade._current_aspect_ratio

    def get_audio_pts(self) -> float:
        """获取音频当前时间戳（秒）"""
        try:
            v = self._facade._get_mpv_property_double('audio-pts')
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    def get_available_seek_range(self) -> dict:
        empty = {'max_back': 0, 'max_forward': 0, 'cache_duration': 0,
                 'buffer_start': 0, 'buffer_end': 0, 'time_pos': 0}
        if self._facade._terminated or not self._facade.mpv_handle:
            return empty
        try:
            time_pos = self._facade._get_mpv_property_double('time-pos') or 0
            buffer_start = 0.0
            buffer_end = 0.0
            cache_duration = 0.0
            cache_state_str = self._facade._get_mpv_property_string('demuxer-cache-state')
            if cache_state_str:
                try:
                    import json
                    cache_state = json.loads(cache_state_str)
                    seekable_ranges = cache_state.get('seekable-ranges', [])
                    if seekable_ranges:
                        first = seekable_ranges[0]
                        buffer_start = first.get('start', 0)
                        buffer_end = first.get('end', 0)
                        cache_duration = buffer_end - buffer_start
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")
            if cache_duration <= 0:
                cache_dur = self._facade._get_mpv_property_double('demuxer-cache-duration') or 0
                if cache_dur > 0:
                    cache_duration = cache_dur
                    buffer_start = max(0, time_pos - cache_dur)
                    buffer_end = time_pos
            max_back = int(cache_duration) if cache_duration > 0 else 0
            max_forward = min(60, max(0, int(cache_duration * 0.1)))
            return {
                'max_back': max_back,
                'max_forward': max_forward,
                'cache_duration': cache_duration,
                'buffer_start': buffer_start,
                'buffer_end': buffer_end,
                'time_pos': time_pos
            }
        except Exception as e:
            self._facade.logger.debug(f"获取可回退范围失败: {e}")
            return empty

    def get_avdiff(self) -> float:
        """获取音视频时间差（秒，float）
        - 正值表示音频落后于视频
        - 负值表示音频领先于视频
        - 接近 0 表示同步良好
        """
        try:
            v = self._facade._get_mpv_property_double('avdiff')
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    def get_buffer_state(self):
        try:
            if self._facade._terminated or not self._facade.mpv_handle:
                return None
            cache_state_str = self._facade._get_mpv_property_string('demuxer-cache-state')
            cache_duration = 0
            buffering = False
            if cache_state_str:
                try:
                    import json
                    cache_state = json.loads(cache_state_str)
                    seekable_ranges = cache_state.get('seekable-ranges', [])
                    if seekable_ranges:
                        first = seekable_ranges[0]
                        cache_duration = first.get('end', 0) - first.get('start', 0)
                    buffering = cache_state.get('eof', False) is False and cache_state.get('underrun', False)
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")
            if cache_duration <= 0:
                dur = self._facade._get_mpv_property_double('demuxer-cache-duration') or 0
                if dur > 0:
                    cache_duration = dur
            paused_for_cache = self._facade._get_mpv_property_string('paused-for-cache')
            if paused_for_cache == 'yes':
                buffering = True
            return {
                'cache_duration': cache_duration,
                'buffering': buffering
            }
        except Exception:
            return None

    def get_chapter_count(self) -> int:
        """获取章节总数"""
        try:
            v = self._facade._get_mpv_property_int('chapter-count')
            if v is None:
                v = self._facade._get_mpv_property_int('chapters')
            return int(v) if v is not None else 0
        except Exception:
            return 0

    def get_chapter_list(self):
        """获取视频内置章节列表
        返回 [{title, time}, ...]，time 为秒（float）
        失败或无章节返回 []
        """
        try:
            if self._facade._terminated or not self._facade.mpv_handle:
                return []
            raw = self._facade._get_mpv_property_string('chapter-list')
            if not raw:
                return []
            import json
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            result = []
            for i, ch in enumerate(data):
                if not isinstance(ch, dict):
                    continue
                result.append({
                    'id': ch.get('id', i),
                    'title': ch.get('title', '') or '',
                    'time': float(ch.get('time', 0.0) or 0.0),
                })
            return result
        except Exception as e:
            self._facade.logger.debug(f"获取章节列表失败: {e}")
            return []

    def get_current_chapter(self):
        """获取当前章节索引（int），无章节返回 -1"""
        try:
            v = self._facade._get_mpv_property_int('chapter')
            if v is not None:
                return v
            s = self._facade._get_mpv_property_string('chapter')
            if s and s not in ('no', ''):
                try:
                    return int(s)
                except ValueError:
                    return -1
            return -1
        except Exception:
            return -1

    def get_current_time(self):
        try:
            time_seconds = self._facade._get_mpv_property_double('time-pos')
            if time_seconds is not None:
                return int(time_seconds * 1000)

            time_seconds = self._facade._get_mpv_property_double('playback-time')
            if time_seconds is not None:
                return int(time_seconds * 1000)

            percent = self._facade._get_mpv_property_double('percent-pos')
            if percent is not None:
                duration_seconds = self._facade._get_mpv_property_double('duration')
                if duration_seconds is not None:
                    time_seconds = duration_seconds * (percent / 100.0)
                    return int(time_seconds * 1000)

            return 0
        except Exception:
            return 0

    def get_current_track(self, track_type='audio'):
        try:
            if not self._facade.mpv_handle:
                return None
            prop = f'{track_type}-track' if track_type in ('audio', 'sub') else track_type
            result = self._facade._get_mpv_property_int(prop)
            if result is not None:
                return result
            str_val = self._facade._get_mpv_property_string(prop)
            if str_val and str_val not in ('no', ''):
                try:
                    return int(str_val)
                except ValueError:
                    return None
            return None
        except Exception:
            return None

    def get_http_proxy(self) -> str:
        try:
            return self._facade._playback_settings.get('http_proxy', '') or ''
        except Exception:
            return ''

    def get_http_referer(self) -> str:
        try:
            return self._facade._playback_settings.get('http_referer', '') or ''
        except Exception:
            return ''

    def get_live_media_info(self):
        if not self._facade.mpv_handle:
            return None
        try:
            def get_str(prop):
                return self._facade._get_mpv_property_string(prop)

            def get_int(prop):
                val = self._facade._get_mpv_property_int(prop)
                if val is not None:
                    return val
                s = get_str(prop)
                if s:
                    try:
                        return int(s)
                    except ValueError:
                        return 0
                return 0

            def get_double(prop):
                val = self._facade._get_mpv_property_double(prop)
                if val is not None:
                    return val
                s = get_str(prop)
                if s:
                    try:
                        return float(s)
                    except ValueError:
                        return 0.0
                return 0.0

            w = get_int('width')
            h = get_int('height')
            fps = get_double('container-fps')
            if fps == 0:
                fps = get_double('estimated-vf-fps')
            if fps == 0:
                fps = get_double('fps')

            hw = get_str('hwdec-current') or ''
            vcodec = get_str('video-codec') or ''
            acodec = get_str('audio-codec') or ''

            v_br = get_double('video-params/bitrate')
            demux_br = get_double('demuxer-bitrate')
            if v_br == 0 and demux_br > 0:
                v_br = demux_br
            a_br = get_double('audio-params/bitrate')
            if v_br == 0 and a_br == 0 and demux_br == 0:
                est_br = get_double('demuxer-cache-state/bytes-per-second') or 0
                if est_br > 0:
                    v_br = est_br

            container = get_str('file-format') or ''

            audio_channels = get_int('audio-params/channel-count')
            sample_rate = get_int('audio-params/samplerate')

            pix_fmt = get_str('video-params/pixelformat') or ''

            colormatrix = get_str('video-params/colormatrix') or ''
            color_primaries = get_str('video-params/primaries') or ''
            gamma = get_str('video-params/gamma') or ''
            colorlevels = get_str('video-params/colorlevels') or ''
            sig_peak = get_double('video-params/sig-peak')
            sig_avg = get_double('video-params/sig-avg')

            if (getattr(self._facade, '_last_info_debug', None)
                    != (w, h, vcodec, acodec)):
                self._facade._last_info_debug = (w, h, vcodec, acodec)
                self._facade.logger.debug(
                    f"媒体信息：width={w}, height={h}, vcodec='{vcodec}', "
                    f"acodec='{acodec}', fps={fps}, container='{container}'"
                )

            if not vcodec and not acodec and w == 0:
                demuxer = get_str('demuxer') or ''
                v_format = get_str('video-format') or ''
                a_format = get_str('audio-format') or ''
                self._facade.logger.info(
                    f"demuxer: {demuxer}, video-format: {v_format}, "
                    f"audio-format: {a_format} "
                    f"(demuxer probing in progress, info may update later)"
                )

                track_list_str = get_str('track-list') or ''
                if track_list_str and not getattr(self._facade, '_track_list_logged', False):
                    self._facade._track_list_logged = True
                    self._facade.logger.info(f"track-list: {track_list_str[:500]}")
                paused = get_str('pause') or ''
                core_idle = get_str('core-idle') or ''
                demuxer_cache = get_str('demuxer-cache-state') or ''
                self._facade.logger.debug(f"pause={paused}, core-idle={core_idle}, cache-state={demuxer_cache[:200]}")

            info = {
                'width': w,
                'height': h,
                'fps': fps,
                'hwdec': hw,
                'video_codec': vcodec,
                'audio_codec': acodec,
                'container': container,
                'audio_channels': audio_channels,
                'sample_rate': sample_rate,
                'pixel_format': pix_fmt,
                'video_bitrate': v_br,
                'audio_bitrate': a_br,
                'demuxer_bitrate': demux_br,
                'colormatrix': colormatrix,
                'color_primaries': color_primaries,
                'gamma': gamma,
                'colorlevels': colorlevels,
                'sig_peak': sig_peak,
                'sig_avg': sig_avg,
                'demuxer': get_str('demuxer') or '',
                'protocol': get_str('protocol') or '',
                'video_format': get_str('video-format') or '',
                'audio_format': get_str('audio-format') or '',
                'aspect_ratio': get_str('video-params/aspect') or '',
                'dwidth': get_int('dwidth'),
                'dheight': get_int('dheight'),
                'video_fps': get_double('estimated-vf-fps') or 0,
                'audio_bitrate_demux': get_double('audio-params/bitrate') or 0,
                'cache_speed': get_double('cache-speed') or 0,
                'cache_used': get_double('demuxer-cache-state/demo-range/avg') or 0,
                'buffering': get_int('cache-buffering-state') or 0,
                'video_depth': get_int('video-params/bits-per-component') or 0,
                'interlaced': get_str('video-params/interlaced') or '',
                'audio_depth': get_int('audio-params/bits-per-sample') or 0,
                'frame_drop_count': get_int('frame-drop-count') or 0,
                'decoder_frame_drop_count': get_int('decoder-frame-drop-count') or 0,
                'mistimed_frame_count': get_int('mistimed-frame-count') or 0,
                'vo_delay': get_double('vo-delayed-frame-count') or 0,
                'cache_size': get_double('demuxer-cache-state/total-bytes') or 0,
                'cache_range_end': get_double('demuxer-cache-state/seeking-ranges/0/end') or 0,
                'video_rotate': get_int('video-params/rotate') or 0,
                'audio_layout': get_str('audio-params/channel-layout') or '',
                'egl_type': get_str('current-vo') or '',
                'current_gpu_api': get_str('current-gpu-api') or '',
                'gpu_context': get_str('gpu-context') or '',
            }
            return info
        except Exception as e:
            self._facade.logger.error(f"获取媒体信息失败：{str(e)}")
            return None

    def get_mute(self):
        try:
            val = self._facade._get_mpv_property_string('mute')
            return val == 'yes'
        except Exception:
            return False

    def get_position(self):
        try:
            percent_pos = self._facade._get_mpv_property_double('percent-pos')
            if percent_pos is not None:
                return percent_pos / 100.0
            return 0
        except Exception:
            return 0

    def get_speed(self):
        return self._facade._current_speed

    def get_thumbnail_path(self, url):
        if not url:
            return None
        import hashlib
        from utils.app_paths import get_cache_dir
        cache_dir = os.path.join(get_cache_dir(), 'thumbnails')
        filepath = os.path.join(cache_dir, f"{hashlib.md5(url.encode('utf-8')).hexdigest()}.png")
        if os.path.exists(filepath):
            return filepath
        return None

    def get_timeshift_range(self):
        try:
            if not self._facade.mpv_handle:
                return (0, 0)
            current = self._facade._get_mpv_property_double('time-pos') or 0
            return (max(0, current - 900), current)
        except Exception:
            return (0, 0)

    def get_total_time(self):
        try:
            duration_seconds = self._facade._get_mpv_property_double('duration')
            if duration_seconds is not None:
                return int(duration_seconds * 1000)

            duration_seconds = self._facade._get_mpv_property_double('length')
            if duration_seconds is not None:
                return int(duration_seconds * 1000)

            return 0
        except Exception:
            return 0

    def get_track_list(self, track_type='audio'):
        try:
            if self._facade._terminated or not self._facade.mpv_handle:
                return []
            track_list_str = self._facade._get_mpv_property_string('track-list')
            if not track_list_str:
                return []
            import json
            tracks = json.loads(track_list_str)
            result = []
            for t in tracks:
                if t.get('type') == track_type:
                    result.append({
                        'id': t.get('id', 0),
                        'lang': t.get('lang', ''),
                        'title': t.get('title', ''),
                        'default': t.get('default', False),
                        'codec': t.get('codec', ''),
                    })
            return result
        except Exception:
            return []

    def get_video_pts(self) -> float:
        """获取视频当前时间戳（秒）"""
        try:
            v = self._facade._get_mpv_property_double('video-pts')
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    def get_video_resolution(self):
        try:
            width = self._facade._get_mpv_property_int('width')
            height = self._facade._get_mpv_property_int('height')
            if width and height and width > 0 and height > 0:
                return f"{width}x{height}"
            return None
        except Exception:
            return None

    def get_volume(self):
        try:
            volume_value = self._facade._get_mpv_property_double('volume')
            if volume_value is not None:
                self._facade._last_volume = int(volume_value)
            return self._facade._last_volume
        except Exception:
            return self._facade._last_volume

    def is_eof_reached(self):
        try:
            eof = self._facade._get_mpv_property_string('eof-reached')
            return eof and eof.lower() == 'yes'
        except Exception:
            return False

    def pause(self):
        try:
            if self._facade.mpv_handle and not self._facade._terminated:
                with self._facade._lock:
                    if not self._facade.mpv_handle or self._facade._terminated:
                        return
                    result = _mpv_send_command(self._facade.mpv_handle, ['cycle', 'pause'])
                if result < 0:
                    self._facade.logger.error(f"切换暂停状态失败: {result}")
                    self._facade.is_paused = not self._facade.is_paused
                    self._facade.is_playing = not self._facade.is_paused
                    self._facade._safe_emit(self._facade.play_state_changed, self._facade.is_playing)
                else:
                    try:
                        actual_paused = self._facade._get_mpv_property_int('pause')
                        self._facade.is_paused = bool(actual_paused)
                    except Exception:
                        self._facade.is_paused = not self._facade.is_paused
                    self._facade.is_playing = not self._facade.is_paused

                    if self._facade.is_paused:
                        self._facade.logger.info("播放已暂停（继续缓冲中）")
                    else:
                        self._facade.logger.info("恢复播放")

                    self._facade._safe_emit(self._facade.play_state_changed, self._facade.is_playing)
        except Exception as e:
            self._facade.logger.error(f"暂停播放失败: {str(e)}")

    def play(self, url, channel_name=None, program_duration=0, **kwargs):
        try:
            if not self._facade._ensure_mpv_initialized():
                self._facade.logger.error("mpv播放器初始化失败，无法播放")
                self._facade._safe_emit(self._facade.play_error, "mpv播放器初始化失败")
                return False

            # 先保存旧频道的播放位置，再更新 current_url
            # 根因修复：之前 current_url = url 在前，导致 old_url 读取的是新 URL，
            # 旧频道的播放位置被错误地保存到新频道的 URL 下
            _prev_url = self._facade.current_url
            self._facade.current_url = url
            self._facade._user_stopped = False
            self._facade._switching_channel = True

            if not self._facade.mpv_handle:
                self._facade.logger.error("mpv播放器未初始化")
                self._facade._safe_emit(self._facade.play_error, "mpv播放器未初始化")
                return False

            if self._facade._terminated:
                return False

            # 切换频道前显式停止当前播放，让 mpv 释放 hwdec/D3D11 解码器资源
            # 避免 keep-open=yes + idle=yes 导致旧解码器未释放，新文件 hwdec 初始化失败（黑屏）
            if (self._facade.is_playing or self._facade.is_paused) and not self._facade._user_stopped:
                # 保存本地视频播放位置（stop 触发的 END_FILE reason=STOP 不会保存位置）
                old_url = _prev_url or ''
                if old_url and not self._facade._is_network_url(old_url):
                    try:
                        pos_sec = self._facade._get_mpv_property_double('time-pos') or 0.0
                        dur_sec = self._facade._get_mpv_property_double('duration') or 0.0
                        if old_url and pos_sec > 0:
                            self._facade._safe_emit(
                                self._facade.local_file_position_to_save,
                                old_url, float(pos_sec), float(dur_sec)
                            )
                            self._facade.logger.debug(
                                f"切换前保存本地视频断点: {old_url[:60]} "
                                f"pos={pos_sec:.1f}s"
                            )
                    except Exception as e:
                        self._facade.logger.debug(f"切换前保存播放位置失败: {e}")
                try:
                    with self._facade._lock:
                        if self._facade.mpv_handle and not self._facade._terminated:
                            _mpv_send_command(self._facade.mpv_handle, ['stop'])
                except Exception as e:
                    self._facade.logger.debug(f"切换前停止旧播放失败: {e}")
                # 重置内部状态，但不发 play_state_changed 信号避免 UI 闪烁
                self._facade.is_playing = False
                self._facade.is_paused = False
                self._facade.media_info = {}
                # 清理可能残留的视频滤镜（flip/crop/360），避免新文件加载时冲突
                try:
                    self._facade.clear_all_video_filters()
                except Exception as _e:
                    self._facade.logger.debug(f"清理视频滤镜失败: {_e}")

            # event_timer 保存在 facade 上；此前用 hasattr(self, 'event_timer')
            # 判断恒为 False，stop() 之后无法重新启动事件轮询（收不到 FILE_LOADED）
            if getattr(self._facade, 'event_timer', None) and not self._facade.event_timer.isActive():
                self._facade.event_timer.start(100)

            if hasattr(self._facade, '_media_info_timer') and self._facade._media_info_timer:
                self._facade._media_info_timer.stop()

            self._facade._media_info_scheduled = False
            self._facade._track_list_logged = False

            self._facade._setup_protocol_options(url, program_duration)

            if self._facade.audio_visual:
                self._facade.audio_visual.prepare_before_loadfile(url)

            is_vod = 'starttime=' in url.lower() or 'endtime=' in url.lower() or 'playseek' in url.lower()
            if is_vod:
                self._facade._set_mpv_string('prefetch-playlist', 'no')
            else:
                self._facade._set_mpv_string('prefetch-playlist', 'yes')

            mpv_url = self._facade._normalize_url(url)
            with self._facade._lock:
                if not self._facade.mpv_handle or self._facade._terminated:
                    return False
                result = _mpv_send_command(self._facade.mpv_handle, ['loadfile', mpv_url])

            if result < 0:
                error_msg = f"播放失败: {result}"
                self._facade.logger.error(error_msg)
                self._facade._safe_emit(self._facade.play_error, error_msg)
                return False

            self._facade._set_mpv_string('pause', 'no')

            if self._facade._current_speed != 1.0:
                self._facade._set_mpv_string('speed', str(self._facade._current_speed))

            self._facade.is_paused = False

            self._facade._safe_emit(self._facade.play_state_changed, True)

            self._facade._schedule_media_info_start()

            self._facade.logger.debug(f"开始播放: {url}")
            return True
        except Exception as e:
            error_msg = f"播放失败: {str(e)}"
            self._facade.logger.error(error_msg)
            self._facade._safe_emit(self._facade.play_error, error_msg)
            return False

    def play_with_prefetch(self, url, next_urls=None, program_duration=0):
        try:
            self._facade.current_url = url
            self._facade._user_stopped = False
            self._facade._switching_channel = True

            if not self._facade.mpv_handle or self._facade._terminated:
                self._facade._safe_emit(self._facade.play_error, "mpv播放器未初始化")
                return False

            self._facade._setup_protocol_options(url, program_duration)

            is_vod = 'starttime=' in url.lower() or 'endtime=' in url.lower() or 'playseek' in url.lower()
            if is_vod:
                self._facade._set_mpv_string('prefetch-playlist', 'no')
            else:
                self._facade._set_mpv_string('prefetch-playlist', 'yes')

            mpv_url = self._facade._normalize_url(url)
            with self._facade._lock:
                if not self._facade.mpv_handle or self._facade._terminated:
                    return False
                result = _mpv_send_command(self._facade.mpv_handle, ['loadfile', mpv_url])

            if result < 0:
                self._facade.logger.error(f"预取播放失败: {result}")
                return False

            self._facade._set_mpv_string('pause', 'no')
            if self._facade._current_speed != 1.0:
                self._facade._set_mpv_string('speed', str(self._facade._current_speed))

            self._facade.is_paused = False
            self._facade.is_playing = True
            self._facade._safe_emit(self._facade.play_state_changed, True)
            self._facade._schedule_media_info_start()

            if next_urls:
                self._facade._prefetch_next_channels(next_urls)

            self._facade.logger.debug(f"开始播放(预取模式): {url}")
            return True
        except Exception as e:
            self._facade.logger.error(f"预取播放失败: {str(e)}")
            return self._facade.play(url)

    def reinit_for_hdr_change(self, new_hdr_mode):
        try:
            from utils.hdr_detect import clear_hdr_cache
            clear_hdr_cache()
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        saved_url = self._facade.current_url
        saved_position = 0.0
        was_paused = bool(self._facade.is_paused)
        if self._facade.mpv_handle:
            try:
                saved_position = self._facade._get_mpv_property_double('time-pos') or 0.0
            except Exception as _e:
                logger.debug(f"unexpected error: {_e}")
        self._facade.stop()
        for timer_attr in ['_media_info_timer', '_live_info_timer', 'event_timer']:
            timer = getattr(self._facade, timer_attr, None)
            if timer:
                try:
                    timer.stop()
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")
        # 在销毁旧 mpv_handle 前释放 macOS render context，避免 GL 资源泄漏
        if is_macos() and hasattr(self._facade.video_widget, 'cleanup'):
            try:
                self._facade.video_widget.cleanup()
            except Exception as e:
                self._facade.logger.debug(f"HDR切换时清理render context失败: {e}")
        with self._facade._lock:
            handle = self._facade.mpv_handle
            self._facade.mpv_handle = None
        if handle:
            try:
                _mpv_send_command(handle, ['quit'])
            except Exception as _e:
                logger.debug(f"unexpected error: {_e}")
            with self._facade._lock:
                terminate_destroy_mpv(handle)
        self._facade._mpv_initialized = False
        self._facade._terminated = False
        self._facade._playback_settings['hdr_output_mode'] = new_hdr_mode
        if not self._facade._ensure_mpv_initialized():
            self._facade.logger.error("HDR模式切换后重新初始化mpv失败")
            return
        # 只要存在原 URL 就重播：暂停态下 is_playing=False，原先会被跳过，
        # 旧流已停、新实例不加载任何内容，却仍被当作直播，且没有自动恢复路径。
        if saved_url:
            from PySide6.QtCore import QTimer
            self._facade.play(saved_url)
            pos = saved_position
            seek_retries = [0]

            def _restore_after_reload():
                if self._facade._terminated or not self._facade.mpv_handle:
                    return
                if not self._facade.is_playing:
                    return
                # 等待 file-loaded 事件后再 seek，确保播放器就绪
                file_loaded = False
                try:
                    file_loaded = self._facade._get_mpv_property_double('time-pos') is not None
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")
                if not file_loaded:
                    if seek_retries[0] < 5:
                        seek_retries[0] += 1
                        QTimer.singleShot(500, _restore_after_reload)
                    else:
                        self._facade.logger.warning(f"HDR切换后恢复播放位置失败（重试 {seek_retries[0]} 次后放弃）")
                    return
                if pos > 0:
                    self._facade.send_command(['seek', str(pos), 'absolute'])
                # 按切换前的暂停状态恢复
                if was_paused:
                    self._facade._set_mpv_string('pause', 'yes')
                    self._facade.is_paused = True
                    self._facade.is_playing = False
                    self._facade._safe_emit(self._facade.play_state_changed, False)
            QTimer.singleShot(1500, _restore_after_reload)
        self._facade.logger.info(f"HDR模式已切换为: {new_hdr_mode}")

    def seek(self, position):
        try:
            if self._facade.mpv_handle and not self._facade._terminated:
                duration_seconds = self._facade._get_mpv_property_double('duration')
                if duration_seconds:
                    target_position = duration_seconds * position
                    result = self._facade.send_command(['seek', f'{target_position}', 'absolute'])
                    if result < 0:
                        seek_percent = position * 100.0
                        self._facade.send_command(['seek', f'{seek_percent}', 'absolute-percent'])
                else:
                    seek_percent = position * 100.0
                    self._facade.send_command(['seek', f'{seek_percent}', 'absolute-percent'])
        except Exception as e:
            self._facade.logger.error(f"设置播放位置失败: {str(e)}")

    def seek_absolute(self, target_seconds):
        try:
            if self._facade.mpv_handle and not self._facade._terminated and target_seconds >= 0:
                result = self._facade.send_command(['seek', f'{target_seconds:.3f}', 'absolute'])
                if result < 0:
                    self._facade.logger.warning(f"绝对seek到{target_seconds:.1f}秒失败，错误码: {result}")
                else:
                    self._facade.logger.info(f"绝对seek成功: {target_seconds:.1f}秒")
                return result
        except Exception as e:
            self._facade.logger.error(f"绝对seek失败: {str(e)}")
        return -1

    def seek_relative_seconds(self, seconds):
        try:
            if self._facade.mpv_handle and not self._facade._terminated and seconds != 0:
                result = self._facade.send_command(['seek', f'{seconds:.1f}', 'relative'])
                if result < 0:
                    self._facade.logger.warning(f"相对seek {seconds}秒失败，错误码: {result}")
                else:
                    self._facade.logger.debug(f"相对seek: {seconds}秒")
        except Exception as e:
            self._facade.logger.error(f"相对seek失败: {str(e)}")

    def send_command(self, cmd_args):
        if self._facade._terminated:
            return -1
        with self._facade._lock:
            if not self._facade.mpv_handle:
                return -1
            return _mpv_send_command(self._facade.mpv_handle, cmd_args)

    def set_aspect_ratio(self, ratio):
        try:
            if not self._facade.mpv_handle:
                return
            # mpv 新版废弃 video-aspect-override=-1，需用 'no' + video-aspect-mode=container 替代
            ratio_lower = ratio.lower() if ratio else 'default'
            if ratio_lower == '16:9':
                self._facade._set_mpv_string('video-aspect-override', '16:9')
                self._facade._set_mpv_string('video-aspect-mode', 'container')
                self._facade._set_mpv_string('keepaspect', 'yes')
                self._facade._set_mpv_string('panscan', '0.0')
            elif ratio_lower == '4:3':
                self._facade._set_mpv_string('video-aspect-override', '4:3')
                self._facade._set_mpv_string('video-aspect-mode', 'container')
                self._facade._set_mpv_string('keepaspect', 'yes')
                self._facade._set_mpv_string('panscan', '0.0')
            elif ratio_lower == 'stretch':
                self._facade._set_mpv_string('video-aspect-override', 'no')
                self._facade._set_mpv_string('video-aspect-mode', 'container')
                self._facade._set_mpv_string('keepaspect', 'no')
                self._facade._set_mpv_string('panscan', '0.0')
            elif ratio_lower == 'fill':
                self._facade._set_mpv_string('video-aspect-override', 'no')
                self._facade._set_mpv_string('video-aspect-mode', 'container')
                self._facade._set_mpv_string('keepaspect', 'yes')
                self._facade._set_mpv_string('panscan', '1.0')
            elif ratio_lower == 'crop':
                self._facade._set_mpv_string('video-aspect-override', 'no')
                self._facade._set_mpv_string('video-aspect-mode', 'container')
                self._facade._set_mpv_string('keepaspect', 'yes')
                self._facade._set_mpv_string('panscan', '1.0')
            else:
                self._facade._set_mpv_string('video-aspect-override', 'no')
                self._facade._set_mpv_string('video-aspect-mode', 'container')
                self._facade._set_mpv_string('keepaspect', 'yes')
                self._facade._set_mpv_string('panscan', '0.0')
            # 缓存当前比例，供 get_aspect_ratio 读出
            # 用于 PlaybackSettingsController 在切换频道前持久化播放设置
            self._facade._current_aspect_ratio = ratio_lower
            self._facade.logger.debug(f"设置画面比例: {ratio}")
        except Exception as e:
            self._facade.logger.error(f"设置画面比例失败: {str(e)}")

    def set_chapter(self, idx: int) -> bool:
        """切换到指定章节（索引从 0 开始）"""
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return False
            current = self._facade.get_current_chapter()
            if current is not None and current == idx:
                return True
            with self._facade._lock:
                if not self._facade.mpv_handle or self._facade._terminated:
                    return False
                result = _mpv_set_property_int64(self._facade.mpv_handle, 'chapter', int(idx))
            if result < 0:
                result2 = self._facade._set_mpv_string('chapter', str(idx))
                if result2 < 0:
                    result3 = self._facade.send_command(['set', 'chapter', str(idx)])
                    if result3 == 0:
                        return True
                    self._facade.logger.debug(f"切换章节失败: chapter={idx}, int64={result}, str={result2}, cmd={result3}")
                    return False
            return True
        except Exception as e:
            self._facade.logger.error(f"切换章节失败: {e}")
            return False

    def set_http_headers(self, headers: str):
        try:
            self._facade._playback_settings['http_headers'] = headers or ''
        except Exception as e:
            self._facade.logger.debug(f"设置 HTTP Headers 失败: {e}")

    def set_http_proxy(self, proxy: str) -> bool:
        """设置 HTTP/HTTPS 代理（运行时生效，对下次 loadfile 起作用）
        支持格式：
          http://host:port
          https://host:port
          socks5://host:port
          socks5h://host:port
        """
        try:
            self._facade._playback_settings['http_proxy'] = proxy or ''
            return self._facade._set_mpv_string('http-proxy', proxy or '') >= 0
        except Exception as e:
            self._facade.logger.debug(f"设置 HTTP 代理失败: {e}")
            return False

    def set_http_referer(self, referer: str) -> bool:
        """设置 HTTP Referer（运行时生效，对下次 loadfile 起作用）"""
        try:
            self._facade._playback_settings['http_referer'] = referer or ''
            return self._facade._set_mpv_string('referrer', referer or '') >= 0
        except Exception as e:
            self._facade.logger.debug(f"设置 Referer 失败: {e}")
            return False

    def set_mute(self, muted):
        try:
            if self._facade.mpv_handle and not self._facade._terminated:
                self._facade._set_mpv_string('mute', 'yes' if muted else 'no')
        except Exception as e:
            self._facade.logger.error(f"设置静音失败: {str(e)}")

    def set_property_string(self, name, value):
        self._facade._set_mpv_string(name, value)

    def set_speed(self, speed):
        try:
            self._facade._current_speed = speed
            if self._facade.mpv_handle:
                self._facade._set_mpv_string('speed', str(speed))
                self._facade.logger.debug(f"设置播放速度: {speed}x")
        except Exception as e:
            self._facade.logger.error(f"设置播放速度失败: {str(e)}")

    def set_track(self, track_type, track_id):
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return False
            prop = f'{track_type}-track' if track_type in ('audio', 'sub') else track_type
            cmd_prop = 'aid' if track_type == 'audio' else ('sid' if track_type == 'sub' else prop)
            track_str = str(track_id)
            current = self._facade.get_current_track(track_type)
            if current is not None and str(current) == track_str:
                return True
            # 'no'/'auto' 等非数字取值只能走字符串属性，直接 int() 会抛异常被吞掉
            if not track_str.lstrip('-').isdigit():
                with self._facade._lock:
                    if not self._facade.mpv_handle or self._facade._terminated:
                        return False
                    result = self._facade._set_mpv_string(prop, track_str)
                if result < 0:
                    result = self._facade.send_command(['set', cmd_prop, track_str])
                if result < 0:
                    self._facade.logger.error(f"切换轨道失败: {prop}={track_str}, 错误码={result}")
                    return False
                return True
            with self._facade._lock:
                if not self._facade.mpv_handle or self._facade._terminated:
                    return False
                result = _mpv_set_property_int64(self._facade.mpv_handle, prop, int(track_id))
            if result < 0:
                result2 = self._facade._set_mpv_string(prop, str(track_id))
                if result2 < 0:
                    cmd_prop = 'aid' if track_type == 'audio' else ('sid' if track_type == 'sub' else prop)
                    result3 = self._facade.send_command(['set', cmd_prop, str(track_id)])
                    if result3 == 0:
                        return True
                    self._facade.logger.error(
                        f"切换轨道失败: {prop}={track_id}, "
                        f"int64错误码={result}, string错误码={result2}, "
                        f"command错误码={result3}"
                    )
                    return False
            return True
        except Exception as e:
            self._facade.logger.error(f"切换轨道失败: {e}")
            return False

    def set_volume(self, volume):
        try:
            self._facade._last_volume = volume
            if self._facade.mpv_handle and not self._facade._terminated:
                self._facade._set_mpv_string('volume', f"{volume}")
        except Exception as e:
            self._facade.logger.error(f"设置音量失败: {str(e)}")

    def show_osd(self, text: str, duration: int = 3000):
        self._facade.send_command(['show-text', text, str(duration)])

    def stop(self):
        try:
            self._facade._user_stopped = True
            was_playing = self._facade.is_playing or self._facade.current_url

            with self._facade._lock:
                if self._facade.mpv_handle and not self._facade._terminated:
                    _mpv_send_command(self._facade.mpv_handle, ['stop'])

            if hasattr(self._facade, '_media_info_timer') and self._facade._media_info_timer:
                self._facade._media_info_timer.stop()
            if hasattr(self._facade, '_live_info_timer') and self._facade._live_info_timer:
                self._facade._live_info_timer.stop()

            self._facade.is_playing = False
            self._facade.is_paused = False
            self._facade._safe_emit(self._facade.play_state_changed, False)
            self._facade.current_url = None
            self._facade.media_info = {}

            if getattr(self._facade, 'event_timer', None):
                self._facade.event_timer.stop()

            if was_playing:
                self._facade.logger.info("停止播放")
            if self._facade.audio_visual:
                self._facade.audio_visual.clear_visual()
        except Exception as e:
            self._facade.logger.error(f"停止播放失败: {str(e)}")

    def terminate(self):
        # 防止重入：终止标记在 facade 上，之前读 self 上的同名属性恒为 False，
        # 重复调用会反复执行销毁流程
        if getattr(self._facade, '_terminated', False):
            self._facade.logger.debug("terminate() 已在执行中，跳过重复调用")
            return
        try:
            self._facade._terminated = True
            self._facade.logger.info("正在终止MPV播放器...")

            if is_macos() and hasattr(self._facade.video_widget, 'cleanup'):
                try:
                    self._facade.video_widget.cleanup()
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")

            # 定时器都挂在 facade 上，之前 getattr(self, ...) 拿到的是 None，
            # 终止时其实一个定时器都没停
            for timer_attr in ['_media_info_timer', '_live_info_timer', 'event_timer']:
                timer = getattr(self._facade, timer_attr, None)
                if timer:
                    try:
                        timer.stop()
                    except Exception as _e:
                        logger.debug(f"unexpected error: {_e}")

            with self._facade._lock:
                handle = self._facade.mpv_handle
                self._facade.mpv_handle = None

            if handle:
                try:
                    _mpv_send_command(handle, ['quit'])
                except Exception as e:
                    self._facade.logger.debug(f"发送quit命令失败（可能已关闭）: {e}")

                # 只让 Qt 处理一轮待处理事件（投递挂起的跨线程信号），
                # 不再用 150ms 的 processEvents 空转等待——mpv_handle 在进入
                # 这里之前已置 None，原循环条件第一次判断就为真，空转没有意义
                try:
                    from PySide6.QtWidgets import QApplication
                    from PySide6.QtCore import QEventLoop
                    QApplication.processEvents(
                        QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                    )
                except Exception as _e:
                    logger.debug(f"终止前处理挂起事件失败: {_e}")

                try:
                    terminate_destroy_mpv(handle)
                except Exception as e:
                    self._facade.logger.debug(f"销毁mpv handle失败: {e}")

            self._facade.is_playing = False
            self._facade.is_paused = False
            self._facade.current_url = None
            self._facade.media_info = {}

            # 关闭 FCC 持久化 UDP socket
            try:
                from services.fcc_service import _close_udp_socket
                _close_udp_socket()
            except Exception as _e:
                logger.debug(f"unexpected error: {_e}")

            self._facade.logger.info("MPV播放器已完全终止")
        except Exception as e:
            self._facade.logger.error(f"终止MPV播放器失败: {str(e)}")

    def update_osd_theme(self):
        self._facade._apply_osd_colors()

