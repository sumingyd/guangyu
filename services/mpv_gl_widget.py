"""macOS 上使用 mpv render API 渲染视频到 QOpenGLWidget。

mpv v0.41+ 在 macOS 上不再支持 wid 嵌入式渲染，标准方案是使用
vo=libmpv + render API，由宿主程序提供 OpenGL 上下文并把帧渲染到 FBO。

实现要点：
- 子类化 QOpenGLWidget，让 Qt 负责 GL 上下文的生命周期
- render context 的创建逻辑在 _create_render_context_impl() 中，
  被 initializeGL() / setup_render_context() / paintGL() 三处复用：
  · initializeGL() 是标准入口（Qt 在第一次 paintGL 前调用，已 makeCurrent）
  · setup_render_context() 主动 makeCurrent 创建，处理 initializeGL()
    已被 show()+repaint() 过早触发的情况（initializeGL 只调用一次）
  · paintGL() 兜底，确保 render context 一定能被创建
- 在 paintGL() 中调用 mpv_render_context_render 把帧绘制到默认 FBO
- mpv 通过 update_callback 通知需要重绘，信号转发到 GUI 线程触发 update()
- macOS OpenGL 3.2+ 仅支持 Core Profile，使用 CompatibilityProfile+3.2 是无效组合
"""

import sys
import ctypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from core.log_manager import global_logger as logger


class MpvGLWidget(QOpenGLWidget):
    """使用 mpv render API 渲染视频的 QOpenGLWidget（macOS 专用）。"""

    # mpv 渲染线程通过此信号触发 GUI 线程的重绘请求
    _render_update_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._render_ctx = None
        self._mpv_handle = None
        self._on_render_update_cb = None
        self._gl_ready = False
        # 创建 render context 时所用的 GL 上下文；上下文被 Qt 重建后必须重新创建
        self._render_ctx_context = None
        self._connected_gl_context = None

        # macOS OpenGL 3.2+ 只支持 Core Profile；
        # CompatibilityProfile + version(3,2) 是无效组合，会导致上下文创建失败。
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 2)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        fmt.setSwapInterval(0)
        # 注意：QSurfaceFormat 无法请求浮点色彩缓冲（rgba16hf）。
        # 这里原先设置的 Red/Green/BlueBufferSize=16 在 macOS 上并不会生成 16-bit
        # 浮点 FBO，Qt 仍会给出 8-bit 缓冲，而 render 时 internal_format=0 也表示
        # "按 8-bit 处理"，两处声明互相矛盾。删掉这些无效请求，保留默认 8-bit；
        # 真正的 HDR/EDR 输出需要自建 GL_RGBA16F FBO 并开启 NSView EDR，
        # 属于必须真机验证的改动，暂不改动渲染链路。
        self.setFormat(fmt)

        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setMinimumSize(1, 1)

        # update_callback 来自 mpv 渲染线程，必须通过 QueuedConnection 转发到 GUI 线程
        self._render_update_signal.connect(
            self._on_render_update_main, Qt.ConnectionType.QueuedConnection
        )

        # 休眠唤醒/切换用户后 macOS 可能丢弃 GL 上下文，恢复前台时做一次上下文核对
        app = QGuiApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def setup_render_context(self, mpv_handle):
        """保存 mpv handle 并尝试创建 render context。

        mpv_render_context_create 要求调用线程已拥有当前 OpenGL 上下文。
        QOpenGLWidget 的 GL 上下文只在 initializeGL / paintGL / resizeGL 期间
        处于 current 状态。

        关键问题：QOpenGLWidget.initializeGL() 只会在第一次 paintGL() 之前
        调用一次。如果在此之前 video_widget.show()+repaint() 已经触发过
        一次 paintEvent（此时 _mpv_handle 还没设置），initializeGL() 会被
        调用但什么都不做，之后 update() 只触发 paintGL() 而不会再调用
        initializeGL()，导致 render context 永远不会创建。

        解决方案：这里主动 makeCurrent() 并尝试创建 render context；
        若 GL 上下文还未就绪（makeCurrent 失败），则回退到 update()
        让 Qt 在下一帧 paintEvent 前调用 initializeGL()。paintGL() 中
        也加了兜底逻辑，确保 render context 一定能被创建。
        """
        if sys.platform != 'darwin':
            return False
        try:
            from services.mpv_common import init_render_api, MPV_AVAILABLE
            if not MPV_AVAILABLE:
                logger.error("libmpv不可用，无法创建render context")
                return False
            init_render_api()
            self._mpv_handle = mpv_handle
            # 主动尝试创建 render context，处理 initializeGL() 已被过早调用的情况
            if not self._render_ctx:
                try:
                    self.makeCurrent()
                    try:
                        self._create_render_context_impl()
                    finally:
                        self.doneCurrent()
                except Exception as e:
                    # makeCurrent 失败说明 GL 上下文还未就绪，回退到 update() 触发 initializeGL
                    logger.debug(f"makeCurrent 创建 render context 失败，等待 initializeGL: {e}")
            # 触发 update：若 render context 已创建则走 paintGL 渲染；否则触发 initializeGL
            self.update()
            logger.info("mpv render context 初始化请求已提交(vo=libmpv, 等待GL上下文就绪)")
            return True
        except Exception as e:
            logger.error(f"setup_render_context失败: {e}")
            return False

    def cleanup(self):
        """释放 render context 资源。

        必须在 mpv_handle 销毁之前调用，否则会泄漏 GL 资源。
        mpv_render_context_free 要求在持有当前 GL 上下文的线程上调用，
        因此这里必须先 makeCurrent；上下文已不可用时宁可不释放也不能裸调，
        否则会在 mpv 内部触发 GL 调用崩溃。
        同时重置 _mpv_handle，避免后续 paintGL() 兜底逻辑使用
        已失效的 handle 创建 render context（HDR 切换场景）。
        """
        self._mpv_handle = None
        if not self._render_ctx:
            self._on_render_update_cb = None
            self._gl_ready = False
            return
        self._release_render_ctx(require_current=True)

    def _release_render_ctx(self, require_current=True):
        """在合适的 GL 上下文下释放 render context。

        require_current=True 时先 makeCurrent；拿不到当前上下文就直接放弃释放
        （保留引用，等 aboutToBeDestroyed 或进程退出），避免无上下文调用崩溃。
        """
        ctx = self._render_ctx
        if not ctx:
            return
        made_current = False
        if require_current:
            gl_ctx = self.context()
            if gl_ctx is None:
                logger.warning("释放 render context 跳过：GL 上下文尚未创建或已销毁")
                return
            try:
                self.makeCurrent()
                made_current = True
            except Exception as e:
                logger.warning(f"释放 render context 跳过：makeCurrent 失败: {e}")
                return
        self._render_ctx = None
        self._render_ctx_context = None
        self._on_render_update_cb = None
        self._gl_ready = False
        try:
            from services.mpv_common import render_context_free
            render_context_free(ctx)
        except Exception as e:
            logger.warning(f"render_context_free异常: {e}")
        finally:
            if made_current:
                try:
                    self.doneCurrent()
                except Exception as e:
                    logger.debug(f"释放 render context 后 doneCurrent 失败: {e}")

    # ------------------------------------------------------------------
    # render context 创建（公共逻辑）
    # ------------------------------------------------------------------
    def _create_render_context_impl(self):
        """创建 mpv render context。调用前必须已经 makeCurrent。

        被 initializeGL() / setup_render_context() / paintGL() 三处复用，
        保证无论 initializeGL() 是否被过早触发，render context 都能被创建。
        """
        if not self._mpv_handle:
            return False
        current_ctx = self.context()
        if self._render_ctx and self._render_ctx_context is not current_ctx:
            # Qt 重建了 GL 上下文：旧 render context 已随旧上下文失效。
            # 旧上下文一般已在 aboutToBeDestroyed 中释放；这里只丢弃引用兜底。
            logger.warning("检测到 GL 上下文已重建，重新创建 mpv render context")
            self._render_ctx = None
            self._render_ctx_context = None
            self._on_render_update_cb = None
            self._gl_ready = False
        if self._render_ctx:
            return False
        try:
            from services.mpv_common import (
                render_context_create,
                render_context_set_update_callback,
            )
            self._render_ctx = render_context_create(self._mpv_handle)
            if not self._render_ctx:
                logger.error("创建mpv render context失败")
                return False
            # 必须保留 CFUNCTYPE 实例引用，否则会被 GC 导致崩溃
            self._on_render_update_cb = ctypes.CFUNCTYPE(
                None, ctypes.c_void_p
            )(self._on_render_update_cb_impl)
            render_context_set_update_callback(
                self._render_ctx, self._on_render_update_cb, ctypes.c_void_p(0)
            )
            self._render_ctx_context = current_ctx
            self._gl_ready = True
            logger.info("mpv render context 创建成功(vo=libmpv, OpenGL Core Profile 3.2)")
            return True
        except Exception as e:
            logger.error(f"创建 render context 失败: {e}")
            self._gl_ready = False
            return False

    # ------------------------------------------------------------------
    # QOpenGLWidget 钩子
    # ------------------------------------------------------------------
    def initializeGL(self):
        """Qt 在第一次 paintEvent 前调用，此时 GL 上下文已 current。

        注意：initializeGL() 只会被调用一次。如果调用时 _mpv_handle 还没
        设置（例如 show()+repaint() 过早触发），这里会直接返回，render
        context 的创建由 setup_render_context() / paintGL() 兜底。
        """
        self._connect_gl_context_signals()
        self._create_render_context_impl()

    def _connect_gl_context_signals(self):
        """监听 GL 上下文销毁，在上下文消失前释放 mpv render context。

        全屏切换、屏幕/DPR 变化、休眠唤醒都可能让 Qt 重建 QOpenGLWidget 的
        GL 上下文。render context 绑定在旧上下文上，必须在旧上下文销毁前释放，
        否则新上下文里继续 render 会直接黑屏或崩溃。
        """
        ctx = self.context()
        if ctx is None or ctx is self._connected_gl_context:
            return
        try:
            ctx.aboutToBeDestroyed.connect(
                self._on_gl_context_about_to_destroy,
                Qt.ConnectionType.DirectConnection,
            )
            self._connected_gl_context = ctx
        except Exception as e:
            logger.warning(f"连接 GL 上下文销毁信号失败: {e}")

    def _on_gl_context_about_to_destroy(self):
        """GL 上下文即将销毁：在其仍为 current 时释放 render context。"""
        try:
            self._release_render_ctx(require_current=True)
        except Exception as e:
            logger.warning(f"GL 上下文销毁时释放 render context 失败: {e}")

    def paintGL(self):
        # 兜底：若 initializeGL() 被过早调用导致 render context 未创建，
        # 在 paintGL() 中补创建（此时 GL 上下文已 current）
        if self._mpv_handle and not self._render_ctx and not self._gl_ready:
            self._create_render_context_impl()
        if not self._gl_ready or not self._render_ctx:
            return
        try:
            fbo = self.defaultFramebufferObject()
            # defaultFramebufferObject 指向的是物理像素尺寸的 FBO，
            # 逻辑像素（self.width()）在 Retina 上只有一半，直接传会让 mpv
            # 只渲染左上角 1/4 区域、其余为黑边。必须换算成物理像素。
            dpr = self.devicePixelRatioF()
            w = max(1, round(self.width() * dpr))
            h = max(1, round(self.height() * dpr))
            from services.mpv_common import (
                render_context_render,
                render_context_report_swap,
            )
            # swapInterval=0 时若再开启 block_for_target_time，渲染会在 GUI 线程
            # 上阻塞到目标显示时刻（暂停/低帧率直播时表现为界面卡住）。
            # 帧更新由 mpv update_callback 驱动，这里不需要阻塞等待。
            ret = render_context_render(
                self._render_ctx, fbo, w, h, flip_y=True, block_for_target_time=False
            )
            if ret < 0:
                # 错误码改为 warning 级别，便于排查渲染问题
                logger.warning(f"mpv_render_context_render 错误码: {ret}")
            render_context_report_swap(self._render_ctx)
        except Exception as e:
            logger.warning(f"paintGL 异常: {e}")

    def resizeGL(self, w, h):
        if self._gl_ready:
            self.update()

    def _on_app_state_changed(self, state):
        """休眠唤醒/切换用户回到前台时核对 GL 上下文是否还是同一个。"""
        if state != Qt.ApplicationState.ApplicationActive:
            return
        if not self._mpv_handle:
            return
        # 上下文已被替换时不在这里直接创建（此时可能没有 current 上下文），
        # 交给下一次 paintGL/initializeGL 走 _create_render_context_impl 的兜底重建。
        if self._render_ctx and self._render_ctx_context is not self.context():
            logger.warning("唤醒后发现 GL 上下文已变化，等待重新创建 render context")
            self._gl_ready = False
            self._render_ctx = None
            self._render_ctx_context = None
        self.update()

    # ------------------------------------------------------------------
    # mpv update_callback 处理
    # ------------------------------------------------------------------
    def _on_render_update_cb_impl(self, _ctx_ptr):
        """由 mpv 渲染线程调用：通知有新帧需要重绘。

        不能在此直接调用 self.update()（跨线程访问 GUI），
        通过 signal 触发 GUI 线程响应。
        """
        try:
            self._render_update_signal.emit()
        except Exception:
            # 信号发射失败时静默忽略，避免在退出阶段崩溃
            pass

    def _on_render_update_main(self):
        """GUI 线程响应 mpv 重绘请求。"""
        if self._gl_ready:
            self.update()
