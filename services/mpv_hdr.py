"""MpvHdr — 从 MpvPlayerController 提取的子控制器。"""

from core.log_manager import global_logger as logger
from utils.platform_utils import is_windows, is_macos, is_android, is_linux


class MpvHdr:
    """MpvHdr — 通过 facade 访问 mpv 实例和播放器。"""

    def __init__(self, facade):
        self._facade = facade

    def _apply_hdr_on_file_loaded(self):
        try:
            if not self._facade.mpv_handle or self._facade._terminated:
                return
            hdr_mode = self._facade._playback_settings.get('hdr_output_mode', 'disable')

            vp_prim = (self._facade._get_mpv_property_string('video-params/primaries') or '').lower()
            vp_gamma = (self._facade._get_mpv_property_string('video-params/gamma') or '').lower()
            vp_peak = self._facade._get_mpv_property_double('video-params/sig-peak') or 0
            vp_format = (self._facade._get_mpv_property_string('video-format') or '').lower()
            vp_cm = (self._facade._get_mpv_property_string('video-params/colormatrix') or '').lower()

            # 说明：播放期不再做 DV 判定。mpv 的 video-format 是解码格式名（如 hevc），
            # 拿不到可靠的 DV 标记，继续判断只会漏判/误报。DV 片源按 HDR10 基础层处理。
            # 统一 HDR 检测（与 detect_hdr_type 对齐）
            is_pq = 'pq' in vp_gamma or 'smpte2084' in vp_gamma
            is_hlg = 'hlg' in vp_gamma or 'arib-std-b67' in vp_gamma
            is_bt2020 = ('bt.2020' in vp_prim or 'bt2020' in vp_prim or
                         'bt.2020' in vp_cm or 'bt2020' in vp_cm)

            self._facade.logger.info(
                f"视频HDR参数: primaries={vp_prim}, gamma={vp_gamma}, "
                f"sig_peak={vp_peak}, format={vp_format}"
            )

            is_hdr_video = is_pq or is_hlg

            # WCG 视频（宽色域 SDR）：BT.2020 色域但 SDR 亮度（gamma=srgb/bt.1886）
            # 这类视频需要保持 bt.2020 色域，避免被压缩到 bt.709 导致偏色
            # 无论 hdr_mode 是什么，WCG 都必须保持 bt.2020 色域
            is_wcg_video = (not is_hdr_video and is_bt2020)

            if is_wcg_video:
                self._facade.logger.info("WCG视频（宽色域SDR），保持bt.2020色域")
                self._facade._apply_wcg_config()
                return

            if not is_hdr_video:
                self._facade.logger.info("非HDR视频，重置HDR参数为默认值")
                self._facade._reset_hdr_params()
                return

            # 根据 HDR 视频类型动态设置 hdr10-opt（HDR10+ 动态元数据传递）：
            # - PQ 视频（HDR10/HDR10+）：启用 hdr10-opt=yes
            # - HLG 视频：禁用 hdr10-opt=no
            if is_pq:
                self._facade._set_mpv_string('hdr10-opt', 'yes')
                self._facade.logger.info("PQ视频，启用hdr10-opt传递HDR10+动态元数据")
            else:
                self._facade._set_mpv_string('hdr10-opt', 'no')
                self._facade.logger.info("非PQ视频（HLG），禁用hdr10-opt")

            def _check_system_hdr():
                """运行时检测系统 HDR 状态（比初始化时更准确，Qt 应用已完全就绪）。"""
                try:
                    if is_windows():
                        from utils.hdr_detect import is_windows_hdr_enabled
                        enabled = is_windows_hdr_enabled()
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
                    logger.debug(f"unexpected error: {_e}")
                return False

            # hdr_mode == 'disable' 时，HDR 视频仍需 tonemap 到 SDR
            # 但要保持 bt.2020 色域（而非压到 bt.709）
            if hdr_mode == 'disable':
                self._facade._apply_tonemap_config(is_hlg=is_hlg)
                return

            if hdr_mode == 'tonemap':
                self._facade._apply_tonemap_config(is_hlg=is_hlg)
                return

            if hdr_mode == 'passthrough':
                # 直通只有系统 HDR 真正开启时才生效，否则一律回退色调映射
                system_hdr = _check_system_hdr()
                if not system_hdr:
                    self._facade.logger.warning("运行时检测系统未启用HDR，passthrough模式回退到tonemap")
                    self._facade._apply_tonemap_config(is_hlg=is_hlg)
                else:
                    self._facade._apply_passthrough_config(is_pq)
                return

            if hdr_mode == 'scrgb':
                # scrgb 实际就是 PQ 直通（与 passthrough 等价），系统未开 HDR 时同样回退
                system_hdr = _check_system_hdr()
                if not system_hdr:
                    self._facade.logger.warning("运行时检测系统未启用HDR，scrgb模式回退到tonemap")
                    self._facade._apply_tonemap_config(is_hlg=is_hlg)
                else:
                    self._facade._apply_scrgb_config(is_pq)
                return

            if hdr_mode == 'auto':
                system_hdr_enabled = _check_system_hdr()
                if system_hdr_enabled:
                    self._facade._apply_scrgb_config(is_pq)
                else:
                    self._facade._apply_tonemap_config(is_hlg=is_hlg)
                return

        except Exception as e:
            self._facade.logger.error(f"应用HDR设置失败: {e}")

    def _apply_passthrough_config(self, is_pq=True):
        # d3d11-output-csp=pq + target-colorspace-hint=yes 已在初始化时设置
        #
        # PQ 视频（HDR10/HDR10+）：
        #   target-peak=10000 是 HDR 直通的关键：告诉 mpv 显示器能处理 10000 nits，
        #   mpv 不会做 tone mapping（target-peak=10000 同 hdr-compute-peak 矛盾，自动关闭），
        #   而是直接输出 PQ 信号让显示器/Windows 合成器处理。
        #   参考：mpv 官方 issue #7357、chiphell 论坛 mpv HDR 教程。
        #   tone-mapping=clip：不做 tone mapping，直接输出 PQ 信号。
        #
        # HLG 视频：
        #   HLG 是相对编码，亮度根据显示器自动缩放（参考：forasoft HLG 文档）。
        #   若设置 target-peak=10000，mpv 会将 HLG 的 1.0（参考白 1000 nits）映射到
        #   10000 nits，导致高光过度拉伸过曝，tone-mapping=clip 截断高光，形成阴阳脸
        #   （用户反馈的"HLG人脸阴阳脸"）。
        #
        #   target-peak=1000（HLG 参考白电平）：
        #   必须设置非零 target-peak 才能触发 target-colorspace-hint 将 swapchain
        #   切换到 PQ 色彩空间。target-peak='' （auto/0）时 mpv 无法确定输出为 HDR，
        #   不切换 swapchain，HLG→PQ 输出在 sRGB swapchain 上显示为极暗画面
        #   （用户反馈的"HLG黑乎乎"）。1000 是 HLG 标准参考白电平（1000 nits），
        #   不会导致 target-peak=10000 的过曝/阴阳脸问题。
        #   hdr-compute-peak=no：使用 HLG 信号嵌入峰值（sig_peak），
        #   不动态计算场景峰值。HLG 广播中高光元素（天空/反光）会将 compute-peak
        #   推高到 2000+ nits，导致 mpv 对 2000→1000 做 2:1 压缩，画面变暗。
        #   使用 sig_peak（通常 400-500 nits）避免不必要的 tonemapping，
        #   PQ 输出峰值更低，Windows DWM 压缩比也更小。
        #   tone-mapping=auto（gpu-next 中选 spline）让 mpv 平滑处理 HLG→PQ 转换。
        #
        # gamut-mapping-mode=relative：相对色域映射，保持色彩准确性，
        # 让显示器/Windows 合成器处理最终的色域压缩。
        # 注意：hdr10-opt 由 _apply_hdr_on_file_loaded 根据视频类型统一设置，这里不再设置。
        self._facade._set_mpv_string('target-prim', 'bt.2020')
        self._facade._set_mpv_string('target-trc', 'pq')
        self._facade._set_mpv_string('gamut-mapping-mode', 'relative')
        # 显式设置 tone-mapping 参数，避免从 WCG/SDR 切换时残留
        # tone-mapping-desat=0：不做去饱和度（mpv 默认 0.5 会对高光做 50% 去饱和度，
        #   导致 HLG 画面偏灰；从 SDR 切换时 desat='' → mpv 默认 0.5，从 WCG 切换时
        #   desat='0'，同一切换路径效果不一致）
        self._facade._set_mpv_string('tone-mapping-mode', 'auto')
        self._facade._set_mpv_string('tone-mapping-desat', '0')
        if is_pq:
            self._facade._set_mpv_string('tone-mapping', 'clip')
            self._facade._set_mpv_string('hdr-compute-peak', 'no')
            self._facade._set_mpv_string('target-peak', '10000')
            self._facade.logger.info("HDR配置: passthrough → PQ直通 (bt.2020/pq, target-peak=10000, gamut=relative)")
        else:
            # HLG 视频：让 mpv 自动处理 HLG→PQ 转换
            # target-peak=1000：HLG 参考白电平，触发 PQ swapchain 切换（修复首次播放黑屏）
            self._facade._set_mpv_string('tone-mapping', 'auto')
            self._facade._set_mpv_string('hdr-compute-peak', 'no')
            self._facade._set_mpv_string('target-peak', '1000')
            self._facade.logger.info(
                "HDR配置: passthrough → HLG自动转换 "
                "(bt.2020/pq, target-peak=1000, compute-peak=no, gamut=relative)"
            )

    def _apply_scrgb_config(self, is_pq=True):
        # 说明：该选项历史名为 scrgb，实际行为与 passthrough 完全相同，
        # 都是把 HDR 内容以 PQ 信号输出到 swapchain（d3d11-output-csp=pq +
        # target-colorspace-hint=yes 已在初始化时设置），由 Windows DWM 合成。
        # 界面文案已改为“PQ 直通（与直通等价）”，不再宣称 scRGB。
        self._facade._apply_passthrough_config(is_pq)
        self._facade.logger.info(f"HDR配置: PQ直通（scrgb 同 passthrough）→ {'PQ直通' if is_pq else 'HLG自动转换'}")

    def _apply_tonemap_config(self, is_hlg=False):
        # HDR→SDR 色调映射（与 Android 端 applyTonemapConfig 统一策略）：
        # 显式指定目标色域和 gamma，避免 mpv 自动推断失败
        # 统一策略：target-prim=bt.2020 保留广色域（WCG），在支持广色域的显示器上显示更丰富色彩
        # gamut-mapping-mode=perceptual 感知映射，减少色域裁剪损失
        # 注意：d3d11-output-csp 和 target-colorspace-hint 已在初始化时设置（option），
        # 运行时修改不会重建 swapchain，所以这里不再设置。
        # 重置 target-peak：passthrough/scrgb 模式设置了 10000，切换到 tonemap 时必须重置，
        # 否则 mpv 认为显示器能显示 10000 nits，不会做 HDR→SDR tone mapping，画面会过曝。
        # 注意：hdr10-opt 由 _apply_hdr_on_file_loaded 根据视频类型统一设置，这里不再设置。
        sdr_trc = self._facade._get_sdr_target_trc()
        # HLG 视频去饱和度降为 0，避免整体发灰
        # PQ 视频保留 0.5 的去饱和度，防止高光过饱和
        desat = '0' if is_hlg else '0.5'
        if is_hlg:
            # HLG tonemap 到 SDR：使用 auto（gpu-next 选 spline，感知均匀，保留中间调亮度）
            # hdr-compute-peak=yes：HLG 无嵌入 maxCLL 元数据，需动态计算场景峰值
            # 避免用 bt.2390（线性扩展段压缩中间调，比 spline 更暗）
            self._facade._set_mpv_string('tone-mapping', 'auto')
            self._facade._set_mpv_string('hdr-compute-peak', 'yes')
        else:
            self._facade._set_mpv_string('tone-mapping', 'auto')
            self._facade._set_mpv_string('hdr-compute-peak', 'no')
        self._facade._set_mpv_string('tone-mapping-mode', 'auto')
        self._facade._set_mpv_string('tone-mapping-desat', desat)
        self._facade._set_mpv_string('target-prim', 'bt.2020')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        # target-peak=100：显式 SDR 电平，确保 swapchain 切换到 sRGB 色彩空间
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', 'perceptual')
        self._facade.logger.info(
            f"HDR配置: tonemap → SDR (bt.2020/{sdr_trc}, target-peak=100, "
            f"gamut=perceptual, desat={desat}{' [HLG]' if is_hlg else ''})"
        )

    def _apply_wcg_config(self):
        """WCG 视频（宽色域 SDR）配置：保持 bt.2020 色域，SDR 亮度。

        WCG 视频是 BT.2020 色域但 SDR 亮度（gamma=srgb/bt.1886），
        需要保持 bt.2020 色域，避免被压缩到 bt.709 导致偏色。
        使用 gamut-mapping-mode=relative 让显示器/Windows 合成器处理色域映射。

        关键：必须显式重置所有 tone-mapping 参数，避免从 HDR10 passthrough
        切换时残留 target-peak=10000 / tone-mapping=clip 等参数导致画面发灰。
        """
        sdr_trc = self._facade._get_sdr_target_trc()
        # 显式设置所有参数（不用空字符串重置，避免 mpv 默认值不确定性）
        # tone-mapping=auto：与 SDR(_reset_hdr_params) 和 HLG passthrough 统一，
        # 避免 clip 触发不同的渲染管线路径（SDR→WCG 切换时 clip 可能导致色彩异常）
        self._facade._set_mpv_string('tone-mapping', 'auto')
        self._facade._set_mpv_string('tone-mapping-mode', 'auto')
        self._facade._set_mpv_string('tone-mapping-desat', '0')
        self._facade._set_mpv_string('hdr-compute-peak', 'no')
        self._facade._set_mpv_string('hdr10-opt', 'no')
        self._facade._set_mpv_string('target-prim', 'bt.2020')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        # target-peak=100：显式 SDR 电平，确保 target-colorspace-hint 将 swapchain
        # 切换到 sRGB 色彩空间。target-peak='' 时可能残留上次 HDR 视频的 PQ swapchain，
        # 导致 SDR 内容在 PQ swapchain 上显示为极暗画面。
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', 'relative')
        self._facade.logger.info(f"HDR配置: WCG → 保持bt.2020色域 (bt.2020/{sdr_trc}, target-peak=100, gamut=relative)")

    def _get_sdr_target_trc(self):
        """获取当前系统下 SDR 输出的正确 target-trc。

        Windows HDR 模式下桌面运行在 sRGB 线性空间，
        SDR 内容（包括 tonemap 后的 HDR 内容）需用 srgb gamma
        才能正确显示，否则会偏灰偏暗。
        """
        try:
            if is_windows():
                from utils.hdr_detect import is_windows_hdr_enabled
                if is_windows_hdr_enabled():
                    return 'srgb'
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        return 'bt.1886'

    def _reset_hdr_params(self):
        # 非 HDR 视频：显式指定 SDR 目标，确保 bt.2020 色域（WCG）视频能正确映射到 bt.709
        # d3d11-output-csp 和 target-colorspace-hint 已在初始化时设置
        # 重置 target-peak：passthrough/scrgb 模式设置了 10000，切换到非 HDR 视频时必须重置。
        # 重置 gamut-mapping-mode：passthrough/scrgb 设置了 relative，非 HDR 视频不需要。
        sdr_trc = self._facade._get_sdr_target_trc()
        self._facade._set_mpv_string('tone-mapping', '')
        self._facade._set_mpv_string('tone-mapping-mode', '')
        self._facade._set_mpv_string('tone-mapping-desat', '')
        self._facade._set_mpv_string('hdr-compute-peak', '')
        self._facade._set_mpv_string('hdr10-opt', 'no')
        self._facade._set_mpv_string('target-prim', 'bt.709')
        self._facade._set_mpv_string('target-trc', sdr_trc)
        # target-peak=100：显式 SDR 电平，确保 swapchain 切换到 sRGB 色彩空间
        self._facade._set_mpv_string('target-peak', '100')
        self._facade._set_mpv_string('gamut-mapping-mode', '')
        self._facade.logger.info(f"HDR配置: 已重置为SDR默认值 (bt.709/{sdr_trc}, target-peak=100)")

    def detect_hdr_type(colormatrix: str, gamma: str, sig_peak: float,
                        video_format: str = '', primaries: str = '') -> str:
        """统一 HDR 类型检测逻辑（PC/Android/Web 三端共用此算法）。

        检测优先级：PQ(HDR10) → HLG → WCG → SDR

        注意：
        - mpv 运行时无法区分 HDR10 与 HDR10+（ST.2094-40 动态元数据不暴露为属性），
          统一返回 'HDR10'。HDR10+ 的检测仅在 ffprobe 扫描阶段通过 side_data 完成。
        - 播放期拿不到可靠的 DV 标记（video-format 是解码格式名），因此不再返回 'DV'；
          DV 片源按 HDR10 基础层显示。DV 判定只在 ffprobe 扫描阶段用 codec_tag/side_data 完成。
        - WCG（宽色域 SDR）：BT.2020 色域 + SDR 亮度，需要保持广色域避免压缩偏色。
        - sig_peak 用于辅助判断（mpv 中 1.0≈SDR 白电平，HDR 内容通常 >1.0），
          但不作为 HDR10/HDR10+ 的区分依据。

        Args:
            colormatrix: 色彩矩阵（如 bt.709/bt.2020），来自 video-params/colormatrix
            gamma: 传输特性（如 pq/smpte2084/hlg/arib-std-b67/srgb/bt.1886）
            sig_peak: 信号峰值（mpv video-params/sig-peak，1.0≈SDR白）
            video_format: 保留参数（播放期不再据此判定 DV）
            primaries: 色彩原色（如 bt.709/bt.2020），来自 video-params/primaries
        """
        g = (gamma or '').lower()
        cm = (colormatrix or '').lower()
        prim = (primaries or '').lower()

        # PQ 视频（HDR10 / HDR10+）：SMPTE ST 2084 (PQ) EOTF
        is_pq = 'pq' in g or 'smpte2084' in g
        # HLG 视频：ARIB STD-B67 (HLG)
        is_hlg = 'hlg' in g or 'arib-std-b67' in g
        # BT.2020 色域检测（从 colormatrix 或 primaries 判断）
        is_bt2020 = ('bt.2020' in cm or 'bt2020' in cm or 'bt.2100' in cm or
                     'bt.2020' in prim or 'bt2020' in prim or 'bt.2100' in prim)

        # PQ → HDR10（运行时无法区分 HDR10+，hdr10-opt=yes 会自动传递动态元数据）
        if is_pq:
            return 'HDR10'
        # HLG
        if is_hlg:
            return 'HLG'
        # WCG：BT.2020 色域 + SDR 亮度（非 HDR），sig_peak 辅助排除极少数高亮度 SDR
        if is_bt2020 and sig_peak <= 1.0:
            return 'WCG'
        # BT.2020 + 高 sig_peak 但 gamma 未标记 → 可能是未正确标记的 HLG
        if is_bt2020 and sig_peak > 1.0:
            return 'HLG'
        return 'SDR'

