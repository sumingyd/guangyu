"""MpvShader — 从 MpvPlayerController 提取的子控制器。"""

import os
import sys

from core.log_manager import global_logger as logger


def _candidate_shader_dirs() -> list:
    """返回按优先级排列的着色器目录候选。

    打包后（PyInstaller onefile）内置资源在 sys._MEIPASS 下，
    而用户可写的 shaders/ 通常放在可执行文件旁边；两者都要支持，
    否则发布版会"找不到任何着色器"，用户手动放置也不会生效。
    """
    dirs = []
    if getattr(sys, 'frozen', False):
        dirs.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), 'shaders'))
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        dirs.append(os.path.join(meipass, 'shaders'))
    if not getattr(sys, 'frozen', False):
        # 开发模式：项目根目录下的 shaders/
        dirs.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shaders'))

    result = []
    for d in dirs:
        if d not in result:
            result.append(d)
    return result


class MpvShader:
    """MpvShader — 通过 facade 访问 mpv 实例和播放器。"""

    def __init__(self, facade):
        self._facade = facade

    def _find_shader_files(self, preset: str) -> list:
        """查找预设对应的所有着色器文件路径

        :return: 文件路径列表（可能多个，如 Anime4K 需要 3 个文件）
        """
        if preset == 'off':
            return []
        shader_dirs = [d for d in _candidate_shader_dirs() if os.path.isdir(d)]
        if not shader_dirs:
            return []

        # 1. 如果预设名在 _SHADER_PRESET_FILES 中，按精确文件名查找
        if preset in self._facade._SHADER_PRESET_FILES:
            paths = []
            for fname in self._facade._SHADER_PRESET_FILES[preset]:
                for shaders_dir in shader_dirs:
                    path = os.path.join(shaders_dir, fname)
                    if os.path.isfile(path):
                        paths.append(path)
                        break
            if paths:
                return paths

        # 2. 回退：前缀匹配查找单个文件
        extensions = ('.glsl', '.hook', '.glsl.hook')
        for shaders_dir in shader_dirs:
            for ext in extensions:
                # 精确匹配：preset.ext
                path = os.path.join(shaders_dir, f'{preset}{ext}')
                if os.path.isfile(path):
                    return [path]
                # 前缀匹配：preset_*.ext
                for fname in os.listdir(shaders_dir):
                    if fname.lower().startswith(preset.lower()) and fname.lower().endswith(ext):
                        return [os.path.join(shaders_dir, fname)]
        return []

    def _get_shaders_dir(self) -> str:
        """获取着色器目录路径（优先已存在的目录，否则返回可写目录）"""
        candidates = _candidate_shader_dirs()
        for d in candidates:
            if os.path.isdir(d):
                return d
        target = candidates[0]
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as _e:
            logger.debug(f"无法创建着色器目录 {target}: {_e}")
        return target

    def clear_motion_compensation(self) -> bool:
        """清除运动补偿滤镜"""
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        try:
            self._facade.send_command(['vf', 'remove', '@iptv_mc'])
            self._facade.logger.info("运动补偿滤镜已移除")
            return True
        except Exception:
            return False

    def clear_super_resolution(self) -> bool:
        """清除分辨率提升（恢复默认缩放算法 + 移除细节增强滤镜）"""
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        # 恢复默认缩放
        self._facade._set_mpv_string('scale', 'bilinear')
        self._facade._set_mpv_string('cscale', 'bilinear')
        self._facade._set_mpv_string('dscale', 'bilinear')
        # 移除滤镜
        try:
            self._facade.send_command(['vf', 'remove', '@iptv_sr'])
            self._facade.logger.info("分辨率提升已清除（缩放恢复默认，细节增强已移除）")
            return True
        except Exception:
            return False

    def clear_user_shader(self) -> bool:
        """清除用户着色器"""
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        ret = self._facade._set_mpv_string('glsl-shaders', '')
        if ret >= 0:
            self._facade.logger.info("用户着色器已清除")
            return True
        return False

    def get_motion_compensation(self) -> dict:
        """读取当前运动补偿设置

        :return: {'strength': str, 'target_fps': int, 'active': bool}
        """
        result = {'strength': 'off', 'target_fps': 60, 'active': False}
        if not self._facade.mpv_handle or self._facade._terminated:
            return result
        try:
            vf = self._facade._get_mpv_property_string('vf')
            if not vf:
                return result
            import json
            data = json.loads(vf) if isinstance(vf, str) else vf
            for item in data.get('vf', []):
                label = item.get('label', '') or ''
                if label != 'iptv_mc':
                    continue
                graph = (item.get('params', {}) or {}).get('graph', '') or ''
                if 'minterpolate' not in graph:
                    continue
                result['active'] = True
                # 解析 fps
                import re
                m = re.search(r'fps=(\d+)', graph)
                if m:
                    result['target_fps'] = int(m.group(1))
                # 解析强度
                if 'mi_mode=blend' in graph:
                    result['strength'] = 'low'
                elif 'me=hexbs' in graph:
                    result['strength'] = 'high'
                elif 'mi_mode=mci' in graph:
                    result['strength'] = 'medium'
                break
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        return result

    def get_super_resolution(self) -> dict:
        """读取当前分辨率提升设置

        :return: {'scale_algo': str, 'detail_enhance': int, 'active': bool}
        """
        result = {'scale_algo': 'off', 'detail_enhance': 0, 'active': False}
        if not self._facade.mpv_handle or self._facade._terminated:
            return result

        # 读取 scale 属性
        scale_val = self._facade._get_mpv_property_string('scale') or 'bilinear'
        if scale_val in self._facade._SCALE_OPTIONS:
            result['scale_algo'] = scale_val
            if scale_val != 'bilinear':
                result['active'] = True

        # 读取 unsharp 滤镜
        try:
            vf = self._facade._get_mpv_property_string('vf')
            if vf:
                import json
                data = json.loads(vf) if isinstance(vf, str) else vf
                for item in data.get('vf', []):
                    label = item.get('label', '') or ''
                    if label != 'iptv_sr':
                        continue
                    graph = (item.get('params', {}) or {}).get('graph', '') or ''
                    if 'unsharp' in graph:
                        import re
                        m = re.search(r'5:5:([\d.]+)', graph)
                        if m:
                            amount = float(m.group(1))
                            result['detail_enhance'] = int(round(amount / 1.5 * 100))
                            result['active'] = True
                    break
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        return result

    def get_user_shader(self) -> str:
        """读取当前着色器路径"""
        if not self._facade.mpv_handle or self._facade._terminated:
            return ''
        return self._facade._get_mpv_property_string('glsl-shaders') or ''

    def list_available_shaders(self) -> list:
        """列出可用的着色器文件

        :return: [{'preset': str, 'path': str, 'filename': str}]
        """
        result = []
        seen = set()
        for shaders_dir in _candidate_shader_dirs():
            if not os.path.isdir(shaders_dir):
                continue
            for fname in sorted(os.listdir(shaders_dir)):
                if fname in seen:
                    continue
                if not fname.lower().endswith(('.glsl', '.hook')):
                    continue
                path = os.path.join(shaders_dir, fname)
                if not os.path.isfile(path):
                    continue
                seen.add(fname)
                # 从文件名提取预设名
                name_base = fname
                for ext in ('.glsl.hook', '.glsl', '.hook'):
                    if name_base.lower().endswith(ext):
                        name_base = name_base[:-len(ext)]
                        break
                result.append({
                    'preset': name_base,
                    'path': path,
                    'filename': fname,
                })
        return result

    def set_motion_compensation(self, strength: str, target_fps: int = 60) -> bool:
        """设置运动补偿插帧

        :param strength: 'off' / 'low' / 'medium' / 'high'
        :param target_fps: 目标帧率（50/60/120），0 表示自动匹配显示器
        :return: 成功与否
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        # 先移除旧滤镜
        try:
            self._facade.send_command(['vf', 'remove', '@iptv_mc'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

        if strength not in self._facade._MC_PRESETS:
            strength = 'off'
        preset = self._facade._MC_PRESETS[strength]
        if preset is None:
            self._facade.logger.info("运动补偿已关闭")
            return True

        # 限制目标帧率到合理范围
        fps = int(target_fps)
        if fps not in (50, 60, 90, 120, 144, 240):
            fps = 60

        # 4K 及以上：先降采样到 1080p 再做运动补偿，避免 CPU 瓶颈
        # minterpolate 是 CPU 端滤镜，4K 像素量是 1080p 的 4 倍，直接处理会严重卡顿
        if self._facade._is_4k_or_above():
            filter_str = (
                f'@iptv_mc:lavfi=['
                f'scale=1920:1080:flags=fast_bilinear,'
                f'minterpolate=fps={fps}:{preset}'
                f']'
            )
            self._facade.logger.info(
                "检测到 4K+ 视频，运动补偿已自动降采样到 1080p 处理"
            )
        else:
            filter_str = f'@iptv_mc:lavfi=[minterpolate=fps={fps}:{preset}]'
        ret = self._facade.send_command(['vf', 'add', filter_str])
        if ret != 0:
            cur_hwdec = ''
            try:
                cur_hwdec = self._facade._get_mpv_property_string('hwdec') or ''
            except Exception as _e:
                logger.debug(f"unexpected error: {_e}")
            self._facade.logger.warning(
                f"运动补偿滤镜添加失败(ret={ret})，strength='{strength}'，fps={fps}，"
                f"当前 hwdec='{cur_hwdec}'。"
                f"若为原生硬解(auto)，请在播放设置中改为 copy-back(auto-copy) 或软解(no)"
            )
            return False
        self._facade.logger.info(f"运动补偿滤镜已添加: strength={strength}, fps={fps}")
        return True

    def set_super_resolution(self, scale_algo: str = 'off', detail_enhance: int = 0) -> bool:
        """设置分辨率提升

        :param scale_algo: 缩放算法
            'off' / 'bilinear' / 'bicubic' / 'lanczos' / 'spline' / 'ewa_lanczos' / 'ewa_lanczossharp'
        :param detail_enhance: 细节增强强度（0-100，0=关闭）
        :return: 成功与否
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return False

        success = True

        # 1. 设置缩放算法（mpv 属性，不需要 copy-back）
        if scale_algo in self._facade._SCALE_OPTIONS:
            # 4K+ 视频下 EWA Lanczos 系列对 GPU 压力极大，自动降级为 lanczos
            if self._facade._is_4k_or_above() and scale_algo in ('ewa_lanczos', 'ewa_lanczossharp'):
                self._facade.logger.info(
                    f"4K+ 视频检测到 {scale_algo}，自动降级为 lanczos 以保证流畅度"
                )
                scale_algo = 'lanczos'
            ret1 = self._facade._set_mpv_string('scale', scale_algo)
            ret2 = self._facade._set_mpv_string('cscale', scale_algo)
            self._facade._set_mpv_string('dscale', scale_algo if scale_algo != 'ewa_lanczossharp' else 'ewa_lanczos')
            if ret1 < 0 or ret2 < 0:
                self._facade.logger.warning(f"缩放算法设置失败: scale={scale_algo}")
                success = False
            else:
                self._facade.logger.info(f"缩放算法已设置: {scale_algo}")
        elif scale_algo == 'off':
            # 恢复默认
            self._facade._set_mpv_string('scale', 'bilinear')
            self._facade._set_mpv_string('cscale', 'bilinear')
            self._facade._set_mpv_string('dscale', 'bilinear')
            self._facade.logger.info("缩放算法已恢复默认")
        else:
            self._facade.logger.warning(f"未知缩放算法: {scale_algo}")
            success = False

        # 2. 设置细节增强（unsharp lavfi 滤镜）
        try:
            self._facade.send_command(['vf', 'remove', '@iptv_sr'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

        detail = max(0, min(100, int(detail_enhance)))
        if detail > 0:
            # unsharp=luma_msize=5:luma_amount=X:chroma_msize=5:chroma_amount=0
            # amount 范围 0.0~1.5，映射 detail 0-100
            amount = round(detail / 100.0 * 1.5, 3)
            # 4K+ 视频下 unsharp 是 CPU 端滤镜，先降采样再处理
            if self._facade._is_4k_or_above():
                filter_str = (
                    f'@iptv_sr:lavfi=['
                    f'scale=1920:1080:flags=fast_bilinear,'
                    f'unsharp=5:5:{amount}:5:5:0.0'
                    f']'
                )
                self._facade.logger.info(
                    f"4K+ 视频检测到，细节增强已降采样到 1080p 处理: detail={detail}"
                )
            else:
                filter_str = f'@iptv_sr:lavfi=[unsharp=5:5:{amount}:5:5:0.0]'
            ret = self._facade.send_command(['vf', 'add', filter_str])
            if ret != 0:
                cur_hwdec = ''
                try:
                    cur_hwdec = self._facade._get_mpv_property_string('hwdec') or ''
                except Exception as _e:
                    logger.debug(f"unexpected error: {_e}")
                self._facade.logger.warning(
                    f"细节增强滤镜添加失败(ret={ret})，detail={detail}，"
                    f"当前 hwdec='{cur_hwdec}'。"
                    f"若为原生硬解(auto)，请在播放设置中改为 copy-back(auto-copy) 或软解(no)"
                )
                success = False
            else:
                self._facade.logger.info(f"细节增强滤镜已添加: detail={detail} (amount={amount})")

        return success

    def set_user_shader(self, preset: str) -> bool:
        """设置用户着色器

        :param preset: 预设名（'off'/'ravu'/'fsrcnnx'/'anime4k'/'krig'/'ssim'）
                       或自定义文件路径
        :return: 成功与否
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return False

        if preset == 'off' or not preset:
            ret = self._facade._set_mpv_string('glsl-shaders', '')
            if ret >= 0:
                self._facade.logger.info("用户着色器已清除")
                return True
            return False

        # 判断是预设名还是文件路径
        if os.path.isfile(preset):
            shader_paths = [preset]
        else:
            shader_paths = self._facade._find_shader_files(preset)

        if not shader_paths:
            self._facade.logger.warning(
                f"着色器文件未找到: preset='{preset}'，"
                f"请在 shaders/ 目录放置对应文件"
            )
            return False

        # MPV glsl-shaders 属性接受逗号分隔的多个路径
        shader_str = ','.join(shader_paths)
        ret = self._facade._set_mpv_string('glsl-shaders', shader_str)
        if ret < 0:
            self._facade.logger.warning(f"着色器设置失败: paths='{shader_str}'")
            return False
        self._facade.logger.info(f"用户着色器已加载: {preset} -> {shader_str}")
        return True

