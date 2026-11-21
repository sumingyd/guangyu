"""切片导出 + GIF 制作服务

通过 ffmpeg 子进程实现：
- 视频片段导出（mp4/mkv/webm，可选重新编码或 stream copy）
- GIF 制作（先用 ffmpeg 抽帧，再用 Pillow 合成 GIF，避免 GIF 色板失真）

特性：
- 异步执行，通过回调通知进度和完成
- 自动定位 ffmpeg（打包目录或系统 PATH）
- 支持裁剪、缩放、帧率参数
- 失败时给出具体错误（如 ffmpeg 未找到）
"""
import os
import subprocess
import threading
import time
from typing import Callable, Optional

from core.log_manager import global_logger as logger


def _find_ffmpeg() -> Optional[str]:
    try:
        from utils.platform_utils import get_ffmpeg_path
        return get_ffmpeg_path()
    except Exception:
        return None


def _creation_flags() -> int:
    try:
        from utils.platform_utils import get_subprocess_creation_flags
        return get_subprocess_creation_flags()
    except Exception:
        return 0


class ClipExportService:
    """切片导出 + GIF 制作"""

    def __init__(self, main_window=None):
        self.window = main_window
        # 当前正在运行的子进程
        self._proc = None
        self._proc_lock = threading.Lock()
        # 是否请求取消
        self._cancel = False

    def _tr(self, key: str, default: str) -> str:
        """获取翻译（线程安全，LanguageManager 已用 self._lock 保护）"""
        try:
            if self.window and hasattr(self.window, 'language_manager'):
                return self.window.language_manager.tr(key, default)
        except Exception as e:
            logger.debug(f"_tr: {e}")
        return default

    def is_busy(self) -> bool:
        with self._proc_lock:
            return self._proc is not None

    def cancel(self):
        """请求取消当前导出"""
        self._cancel = True
        with self._proc_lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception as e:
                logger.debug(f"cancel: {e}")

    def shutdown(self):
        """进程退出前强制结束导出子进程。

        onefile 引导器在进程退出后要删除 _MEI 临时目录，残留的 ffmpeg 子进程
        会占住目录里的可执行文件，导致引导器弹出清理失败提示。
        """
        self._cancel = True
        with self._proc_lock:
            proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception as e:
                logger.debug(f"shutdown kill: {e}")
        try:
            proc.wait(timeout=1)
        except Exception as e:
            logger.debug(f"shutdown wait: {e}")

    # ---------- 视频切片导出 ----------
    def export_clip(self, source: str, start_sec: float, end_sec: float,
                    output_path: str, stream_copy: bool = True,
                    done_callback: Optional[Callable[[bool, str], None]] = None):
        """导出视频片段

        Args:
            source: 源文件路径
            start_sec: 起始秒
            end_sec: 结束秒
            output_path: 输出文件路径
            stream_copy: True=直接复制流（快，但要求容器兼容）；
                         False=重新编码（慢，但兼容性好）
            done_callback: 完成回调 (success, message)
        """
        if self.is_busy():
            if done_callback:
                done_callback(False, self._tr('clip_export_busy', '已有导出任务在运行'))
            return
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            if done_callback:
                done_callback(False, self._tr('clip_export_ffmpeg_not_found_clip',
                    '未找到 ffmpeg，无法导出。请将 ffmpeg 放到 ffmpeg/ 目录或安装到系统 PATH'))
            return
        duration = max(0.0, end_sec - start_sec)
        if duration <= 0:
            if done_callback:
                done_callback(False, self._tr('clip_export_invalid_duration', '时长无效（end <= start）'))
            return
        if not source or not os.path.exists(source):
            if done_callback:
                done_callback(False, self._tr('clip_export_source_not_found',
                    '源文件不存在: {path}').format(path=source))
            return
        # 构造命令
        cmd = [ffmpeg, '-y', '-ss', f'{start_sec:.3f}', '-i', source,
               '-t', f'{duration:.3f}']
        if stream_copy:
            cmd += ['-c', 'copy']
        else:
            # 重新编码（H.264 + AAC）
            cmd += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
                    '-c:a', 'aac', '-b:a', '128k']
        cmd += ['-avoid_negative_ts', 'make_zero', output_path]
        # 异步执行
        self._cancel = False
        t = threading.Thread(target=self._run_export,
                             args=(cmd, output_path, done_callback),
                             daemon=True)
        t.start()

    # ---------- GIF 制作 ----------
    def export_gif(self, source: str, start_sec: float, end_sec: float,
                   output_path: str, width: int = 480, fps: int = 15,
                   done_callback: Optional[Callable[[bool, str], None]] = None):
        """导出 GIF

        通过两步法生成高质量 GIF：
        1. 用 ffmpeg 抽帧到临时 PNG
        2. 用 Pillow 合成 GIF（带局部调色板优化）

        Args:
            source: 源文件路径
            start_sec: 起始秒
            end_sec: 结束秒
            output_path: 输出 GIF 路径
            width: GIF 宽度（像素，高度按比例）
            fps: 帧率（建议 10-15）
            done_callback: 完成回调 (success, message)
        """
        if self.is_busy():
            if done_callback:
                done_callback(False, self._tr('clip_export_busy', '已有导出任务在运行'))
            return
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            if done_callback:
                done_callback(False, self._tr('clip_export_ffmpeg_not_found_gif', '未找到 ffmpeg，无法生成 GIF'))
            return
        try:
            from PIL import Image
        except ImportError:
            if done_callback:
                done_callback(False, self._tr('clip_export_pillow_not_found',
                    '未安装 Pillow，无法生成 GIF（pip install Pillow）'))
            return
        duration = max(0.0, end_sec - start_sec)
        if duration <= 0:
            if done_callback:
                done_callback(False, self._tr('clip_export_invalid_duration_short', '时长无效'))
            return
        if not source or not os.path.exists(source):
            if done_callback:
                done_callback(False, self._tr('clip_export_source_not_found',
                    '源文件不存在: {path}').format(path=source))
            return
        # 临时目录
        tmp_dir = os.path.join(os.path.dirname(output_path), f'_gif_tmp_{int(time.time())}')
        os.makedirs(tmp_dir, exist_ok=True)
        # 异步执行
        self._cancel = False
        t = threading.Thread(
            target=self._run_gif,
            args=(ffmpeg, source, start_sec, duration, tmp_dir,
                  output_path, width, fps, done_callback),
            daemon=True,
        )
        t.start()

    # ---------- 工作线程 ----------
    def _run_export(self, cmd, output_path, done_callback):
        try:
            logger.info(f"切片导出: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=_creation_flags(),
            )
            with self._proc_lock:
                self._proc = proc
            try:
                stdout, stderr = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                with self._proc_lock:
                    self._proc = None
                self._call(done_callback, False, self._tr('clip_export_cancelled', '已取消'))
                return
            with self._proc_lock:
                self._proc = None
            if self._cancel:
                # 取消时删除部分文件
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception as e:
                    logger.debug(f"_run_export: {e}")
                self._call(done_callback, False, self._tr('clip_export_cancelled', '已取消'))
                return
            if proc.returncode == 0 and os.path.exists(output_path):
                self._call(done_callback, True,
                           self._tr('clip_export_exported', '已导出: {path}').format(path=output_path))
            else:
                err = stderr.decode('utf-8', errors='ignore')[-500:] if stderr else '未知错误'
                self._call(done_callback, False,
                           self._tr('clip_export_export_failed', '导出失败: {err}').format(err=err))
        except Exception as e:
            logger.error(f"切片导出异常: {e}")
            with self._proc_lock:
                self._proc = None
            self._call(done_callback, False,
                       self._tr('clip_export_exception', '异常: {err}').format(err=e))

    def _run_gif(self, ffmpeg, source, start_sec, duration, tmp_dir,
                 output_path, width, fps, done_callback):
        tmp_pattern = os.path.join(tmp_dir, 'frame_%05d.png')
        try:
            # 1. 抽帧
            cmd = [
                ffmpeg, '-y', '-ss', f'{start_sec:.3f}', '-i', source,
                '-t', f'{duration:.3f}',
                '-vf', f'fps={fps},scale={width}:-1:flags=lanczos',
                '-v', 'error', tmp_pattern,
            ]
            logger.info(f"GIF 抽帧: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=_creation_flags(),
            )
            with self._proc_lock:
                self._proc = proc
            try:
                stdout, stderr = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                with self._proc_lock:
                    self._proc = None
                self._cleanup_tmp(tmp_dir)
                self._call(done_callback, False, self._tr('clip_export_cancelled', '已取消'))
                return
            with self._proc_lock:
                self._proc = None
            if self._cancel:
                self._cleanup_tmp(tmp_dir)
                self._call(done_callback, False, self._tr('clip_export_cancelled', '已取消'))
                return
            if proc.returncode != 0:
                err = stderr.decode('utf-8', errors='ignore')[-500:] if stderr else '未知错误'
                self._cleanup_tmp(tmp_dir)
                self._call(done_callback, False,
                           self._tr('clip_export_extract_failed', '抽帧失败: {err}').format(err=err))
                return
            # 2. 用 Pillow 合成 GIF
            from PIL import Image
            frames = sorted([f for f in os.listdir(tmp_dir) if f.endswith('.png')])
            if not frames:
                self._cleanup_tmp(tmp_dir)
                self._call(done_callback, False, self._tr('clip_export_no_frames', '未抽到帧'))
                return
            images = []
            for fname in frames:
                if self._cancel:
                    break
                try:
                    img = Image.open(os.path.join(tmp_dir, fname)).convert('RGB')
                    images.append(img)
                except Exception as e:
                    logger.debug(f"读取帧失败 {fname}: {e}")
            if not images:
                self._cleanup_tmp(tmp_dir)
                self._call(done_callback, False, self._tr('clip_export_read_frames_failed', '读取帧失败'))
                return
            # 保存 GIF
            try:
                images[0].save(
                    output_path,
                    save_all=True,
                    append_images=images[1:],
                    duration=int(1000 / fps),
                    loop=0,
                    optimize=True,
                    disposal=2,
                )
            except Exception as e:
                self._cleanup_tmp(tmp_dir)
                self._call(done_callback, False,
                           self._tr('clip_export_save_gif_failed', '保存 GIF 失败: {err}').format(err=e))
                for img in images:
                    try:
                        img.close()
                    except Exception as e:
                        logger.debug(f"_run_gif: {e}")
                return
            for img in images:
                try:
                    img.close()
                except Exception as e:
                    logger.debug(f"_run_gif: {e}")
            self._cleanup_tmp(tmp_dir)
            if self._cancel:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception as e:
                    logger.debug(f"_run_gif: {e}")
                self._call(done_callback, False, self._tr('clip_export_cancelled', '已取消'))
                return
            self._call(done_callback, True,
                       self._tr('clip_export_generated', '已生成: {path}').format(path=output_path))
        except Exception as e:
            logger.error(f"GIF 生成异常: {e}")
            self._cleanup_tmp(tmp_dir)
            with self._proc_lock:
                self._proc = None
            self._call(done_callback, False,
                       self._tr('clip_export_exception', '异常: {err}').format(err=e))

    def _cleanup_tmp(self, tmp_dir: str):
        """清理临时目录"""
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception as e:
            logger.debug(f"_cleanup_tmp: {e}")

    def _call(self, callback, success, message):
        if callback:
            try:
                callback(success, message)
            except Exception as e:
                logger.debug(f"_call: {e}")
