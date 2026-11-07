"""
更新检查控制器 - 负责异步版本检查、在线下载和安装更新
"""

from core.version import APP_USER_AGENT, APP_NAME
import asyncio
import os
import re
import shutil
import sys
import platform
import subprocess
import tempfile

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QProgressDialog, QMessageBox
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from core.log_manager import global_logger as logger
from controllers.main_window_protocol import UiProtocol
from utils.delay_constants import DelayMs


REPO_SLUG = "sumingyd/guangyu"
GITHUB_LATEST_API = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
RELEASE_PAGE_URL = f"https://github.com/{REPO_SLUG}/releases/latest"
BACKUP_SUFFIX = ".old"


def _get_platform_asset_name(system=None, machine=None):
    """返回当前平台对应的 Release asset 文件名

    资产名统一由 core.version.APP_NAME 派生，避免产物改名后这里漏改；
    兼容旧命名（ISEP-xxx / IPTV Scanner Editor Pro-xxx）由调用方另行处理。
    """
    system = system or platform.system()
    if system == "Windows":
        return f"{APP_NAME}-Windows-x86_64.exe"
    elif system == "Darwin":
        return f"{APP_NAME}-macOS-ARM64.zip"
    elif system == "Linux":
        machine = machine or platform.machine()
        if machine in ("aarch64", "arm64"):
            return f"{APP_NAME}-Linux-ARM64.tar.gz"
        return f"{APP_NAME}-Linux-x86_64.tar.gz"
    return None


def _macos_bundle_path(executable):
    """从 .../Xxx.app/Contents/MacOS/<exe> 反推 .app 路径；非 bundle 结构返回 None"""
    exe = os.path.abspath(executable)
    macos_dir = os.path.dirname(exe)
    contents_dir = os.path.dirname(macos_dir)
    bundle = os.path.dirname(contents_dir)
    if (os.path.basename(macos_dir) == "MacOS"
            and os.path.basename(contents_dir) == "Contents"
            and bundle.endswith(".app")):
        return bundle
    return None


def resolve_install_target(system=None, executable=None):
    """推导当前安装的可执行文件/App 路径（安装目标的唯一真源）

    - macOS：返回 .app bundle 路径（运行中可整体替换）
    - 其它平台：返回运行时真实可执行文件路径（名字取自 sys.executable，不硬编码产物名）
    """
    system = system or platform.system()
    exe = os.path.abspath(executable or sys.executable)
    if system == "Darwin":
        return _macos_bundle_path(exe) or exe
    return exe


def parse_version(text):
    """解析版本号开头的数字段为整数元组

    宽松解析但不会把预发布标记误当成版本段：
      "v50.0.6.2" / "V50.0.6.2" / "50.0.6.2-rc2" -> (50, 0, 6, 2)
    无法解析返回空元组。
    """
    if not text:
        return ()
    match = re.match(r"^[vV]?\s*(\d+(?:\.\d+)*)", str(text).strip())
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer_version(current_version, latest_version):
    """latest 是否比 current 新（逐段数值比较，长度不足补 0）"""
    current_parts = parse_version(current_version)
    latest_parts = parse_version(latest_version)
    if not current_parts or not latest_parts:
        return False
    max_length = max(len(current_parts), len(latest_parts))
    current_parts = current_parts + (0,) * (max_length - len(current_parts))
    latest_parts = latest_parts + (0,) * (max_length - len(latest_parts))
    return latest_parts > current_parts


def _remove_path(path):
    """删除文件或目录，失败只记日志（用于清理备份与解压残留）"""
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    except OSError as e:
        logger.debug(f"删除路径失败: {path}: {e}")


def restore_backup(backup_path, target_path):
    """用备份恢复原安装；返回是否恢复成功"""
    try:
        _remove_path(target_path)
        if os.path.exists(backup_path):
            os.rename(backup_path, target_path)
        return True
    except OSError as e:
        logger.error(f"恢复旧版本失败: {e}")
        return False


def swap_in_place(new_path, target_path):
    """用 new_path 替换 target_path，成功返回备份路径

    运行中的可执行文件/App 不能被覆盖写，但允许改名；因此先改名备份再落位。
    落位失败时立即回滚，保证 target_path 始终可用。
    """
    backup_path = target_path + BACKUP_SUFFIX
    _remove_path(backup_path)
    os.rename(target_path, backup_path)
    try:
        shutil.move(new_path, target_path)
    except Exception:
        try:
            os.rename(backup_path, target_path)
        except OSError as rollback_error:
            logger.error(f"更新回滚失败，旧版本保留在 {backup_path}: {rollback_error}")
        raise
    return backup_path


def _is_complete_app_bundle(path):
    """校验 .app 结构完整（Info.plist + Contents/MacOS 内有可执行文件）"""
    contents_dir = os.path.join(path, "Contents")
    macos_dir = os.path.join(contents_dir, "MacOS")
    if not (os.path.isfile(os.path.join(contents_dir, "Info.plist")) and os.path.isdir(macos_dir)):
        return False
    try:
        return any(
            os.path.isfile(os.path.join(macos_dir, name))
            for name in os.listdir(macos_dir)
        )
    except OSError:
        return False


def find_app_bundle(extract_dir):
    """在解压目录中查找结构完整的 .app，找不到返回 None"""
    try:
        names = os.listdir(extract_dir)
    except OSError:
        return None
    for name in names:
        path = os.path.join(extract_dir, name)
        if name.endswith(".app") and os.path.isdir(path) and _is_complete_app_bundle(path):
            return path
    return None


def find_linux_executable(extract_dir, expected_name=""):
    """在解压目录中查找更新后的可执行文件

    优先按当前安装名（从 sys.executable 派生）查找；找不到时仅在目录下
    恰好有一个可执行文件时才采用，避免误把脚本当成主程序。
    """
    if expected_name:
        candidate = os.path.join(extract_dir, expected_name)
        if os.path.isfile(candidate):
            return candidate
    try:
        executables = [
            os.path.join(extract_dir, name)
            for name in os.listdir(extract_dir)
            if os.path.isfile(os.path.join(extract_dir, name))
            and os.access(os.path.join(extract_dir, name), os.X_OK)
        ]
    except OSError:
        return None
    return executables[0] if len(executables) == 1 else None


# 旧版资产名（用于向后兼容，匹配 GitHub Release 中的旧版文件：ISEP-xxx / IPTV Scanner Editor Pro-xxx）
_LEGACY_ASSET_NAMES = {
    "Windows": ("ISEP-Windows-x86_64.exe", "IPTV Scanner Editor Pro-Windows-x86_64.exe"),
    "Darwin": ("ISEP-macOS-ARM64.zip", "IPTV Scanner Editor Pro-macOS-ARM64.zip"),
    "Linux-ARM64": ("ISEP-Linux-ARM64.tar.gz", "IPTV Scanner Editor Pro-Linux-ARM64.tar.gz"),
    "Linux-x86_64": ("ISEP-Linux-x86_64.tar.gz", "IPTV Scanner Editor Pro-Linux-x86_64.tar.gz"),
}


def _get_legacy_asset_name():
    """返回当前平台对应的旧版 Release asset 文件名元组（用于向后兼容）"""
    system = platform.system()
    if system == "Windows":
        return _LEGACY_ASSET_NAMES["Windows"]
    elif system == "Darwin":
        return _LEGACY_ASSET_NAMES["Darwin"]
    elif system == "Linux":
        machine = platform.machine()
        if machine in ("aarch64", "arm64"):
            return _LEGACY_ASSET_NAMES["Linux-ARM64"]
        return _LEGACY_ASSET_NAMES["Linux-x86_64"]
    return None


def _is_frozen():
    """是否以 PyInstaller 打包模式运行"""
    return getattr(sys, 'frozen', False)


class UpdateCheckThread(QThread):
    """版本检查线程"""
    update_found = Signal(str, str, str)  # latest_version, current_version, download_url
    check_completed = Signal(bool, str)

    def run(self):
        from core.language_manager import LanguageManager
        tr = LanguageManager().tr
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            from core.version import CURRENT_VERSION
            current_version = CURRENT_VERSION

            latest_version, download_url, _ = loop.run_until_complete(
                asyncio.wait_for(self._get_latest_version(), timeout=15)
            )

            if latest_version and not latest_version.startswith("("):
                if self._is_newer_version(current_version, latest_version):
                    self.update_found.emit(latest_version, current_version, download_url or "")
                    self.check_completed.emit(True, tr('update_found', '发现新版本: {}').format(latest_version))
                else:
                    self.check_completed.emit(True, tr('already_latest', '当前已是最新版本'))
            else:
                self.check_completed.emit(False, tr('version_check_failed', '版本检查失败'))

        except asyncio.TimeoutError:
            self.check_completed.emit(False, tr('version_check_timeout', '版本检查超时'))
        except Exception as e:
            logger.error(f"版本检查异常: {e}")
            self.check_completed.emit(False, tr('version_check_error', '版本检查异常'))
        finally:
            try:
                if loop:
                    loop.close()
            except Exception as e:
                logger.debug(f"关闭事件循环失败: {e}")

    async def _get_latest_version(self):
        """从GitHub获取最新版本信息，返回 (版本号, 下载链接或None, Release页面链接)"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    GITHUB_LATEST_API,
                    headers={'User-Agent': APP_USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        version = str(data.get('tag_name', '')).strip()
                        if version[:1] in ('v', 'V'):
                            version = version[1:]
                        release_url = data.get('html_url', '')

                        # 查找当前平台对应的下载链接；匹配不到时保持 None，
                        # 避免把 Release 的 HTML 页面当成安装包下载。
                        download_url = None
                        asset_name = _get_platform_asset_name()
                        legacy_names = _get_legacy_asset_name() or ()
                        if asset_name:
                            for asset in data.get('assets', []):
                                name = asset.get('name', '')
                                if name == asset_name or name in legacy_names:
                                    download_url = asset.get('browser_download_url') or None
                                    break

                        return version, download_url, release_url
                    elif response.status == 403:
                        return "(API限制)", None, None
                    else:
                        return "(获取失败)", None, None
        except asyncio.TimeoutError:
            return "(请求超时)", None, None
        except Exception:
            return "(获取失败)", None, None

    def _is_newer_version(self, current_version, latest_version):
        """比较版本号，判断最新版本是否比当前版本新（预发布后缀不计入版本段）"""
        return is_newer_version(current_version, latest_version)


class UpdateDownloadThread(QThread):
    """更新文件下载线程"""
    progress = Signal(int, str)  # percentage (0-100, -1=unknown), message
    download_complete = Signal(str)  # file path
    download_error = Signal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._url = url
        self._cancel = False

    def run(self):
        from core.language_manager import LanguageManager
        tr = LanguageManager().tr
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._download())
        except Exception as e:
            logger.error(f"下载失败: {e}")
            self.download_error.emit(tr('download_failed', '下载失败'))
        finally:
            try:
                if loop:
                    loop.close()
            except Exception as e:
                logger.debug(f"关闭事件循环失败: {e}")

    async def _download(self):
        """异步下载更新文件"""
        import aiohttp
        import hashlib
        from core.language_manager import LanguageManager
        tr = LanguageManager().tr

        asset_name = _get_platform_asset_name() or "isep_update_file"
        filepath = os.path.join(tempfile.gettempdir(), asset_name)

        self.progress.emit(0, tr('connecting_server', '正在连接服务器...'))

        async with aiohttp.ClientSession() as session:
            # 优先从 Release 下载 SHA256 校验文件
            expected_sha256 = None
            try:
                sha256_url = self._url + '.sha256'
                async with session.get(
                    sha256_url,
                    headers={'User-Agent': APP_USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as sha_resp:
                    if sha_resp.status == 200:
                        sha_text = (await sha_resp.text()).strip()
                        # SHA256 文件格式: <hash>  <filename> 或纯 hash
                        expected_sha256 = sha_text.split()[0] if sha_text else None
                        if expected_sha256 and len(expected_sha256) == 64:
                            self.progress.emit(0, tr('sha256_acquired', '已获取 SHA256 校验值'))
                        else:
                            expected_sha256 = None
            except Exception as e:
                logger.warning(f"获取 SHA256 校验值失败，将跳过完整性校验: {e}")

            async with session.get(
                self._url,
                headers={'User-Agent': APP_USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=600)
            ) as response:
                if response.status != 200:
                    logger.error(f"下载失败: HTTP {response.status}")
                    self.download_error.emit(tr('download_failed', '下载失败'))
                    return

                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                sha256_hash = hashlib.sha256()

                with open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(65536):
                        if self._cancel:
                            f.close()
                            try:
                                os.remove(filepath)
                            except OSError:
                                pass
                            return
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int(downloaded * 100 / total)
                            msg = tr('downloaded_progress', '已下载 {}MB / {}MB').format(downloaded // 1048576, total // 1048576)
                            self.progress.emit(percent, msg)
                        else:
                            msg = tr('downloaded', '已下载 {}MB').format(downloaded // 1048576)
                            self.progress.emit(-1, msg)

                # SHA256 完整性校验
                if expected_sha256:
                    actual_sha256 = sha256_hash.hexdigest()
                    if actual_sha256.lower() != expected_sha256.lower():
                        try:
                            os.remove(filepath)
                        except OSError:
                            pass
                        logger.error(f"文件校验失败: SHA256 不匹配, 期望: {expected_sha256[:16]}..., 实际: {actual_sha256[:16]}...")
                        self.download_error.emit(tr('checksum_failed', '文件校验失败: SHA256 不匹配'))
                        return
                    self.progress.emit(100, tr('checksum_passed', '文件校验通过'))

                self.download_complete.emit(filepath)

    def cancel(self):
        """取消下载"""
        self._cancel = True


class _InstallExtractThread(QThread):
    """安装前解压线程（macOS/Linux），避免 subprocess.run 阻塞主线程

    解压到独立临时目录，并按真实产物结构（.app / 当前可执行名）定位，
    不再硬编码旧产物名。
    """
    extract_complete = Signal(str, str)  # platform_name, extracted_path
    extract_error = Signal(str)

    def __init__(self, platform_name: str, filepath: str, expected_name: str = "", parent=None):
        super().__init__(parent)
        self._platform_name = platform_name
        self._filepath = filepath
        self._expected_name = expected_name

    def run(self):
        from core.language_manager import LanguageManager
        tr = LanguageManager().tr
        try:
            extract_dir = tempfile.mkdtemp(prefix="guangyu_update_")
            if self._platform_name == "Darwin":
                subprocess.run(
                    ['unzip', '-oq', self._filepath, '-d', extract_dir],
                    check=True, timeout=120
                )
                new_app = find_app_bundle(extract_dir)
                if not new_app:
                    logger.error(f"更新包中未找到结构完整的 .app: {extract_dir}")
                    self.extract_error.emit(tr('update_package_invalid', '更新包不完整：未找到可用的应用'))
                    return
                self.extract_complete.emit("Darwin", new_app)
            elif self._platform_name == "Linux":
                subprocess.run(
                    ['tar', 'xzf', self._filepath, '-C', extract_dir],
                    check=True, timeout=120
                )
                new_exe = find_linux_executable(extract_dir, self._expected_name)
                if not new_exe:
                    logger.error(f"更新包中未找到可执行文件: {extract_dir}")
                    self.extract_error.emit(tr('update_package_invalid', '更新包不完整：未找到可用的应用'))
                    return
                os.chmod(new_exe, 0o755)
                self.extract_complete.emit("Linux", new_exe)
        except subprocess.TimeoutExpired:
            self.extract_error.emit(tr('extract_timeout', '解压超时'))
        except Exception as e:
            logger.error(f"解压失败: {e}")
            self.extract_error.emit(tr('extract_failed', '解压失败'))


class UpdateController:
    """更新检查控制器 - 管理版本检查、下载和安装"""

    def __init__(self, main_window: UiProtocol):
        self.window: UiProtocol = main_window
        self._update_checking = False
        self._update_checked = False
        self._check_thread = None
        self._download_url = ""
        self._latest_version = ""
        self._current_version = ""
        self._download_thread = None
        self._progress_dialog = None
        self._pending_download = False
        self._extract_thread = None
        self._update_available = False

    def check_for_updates(self):
        """异步检查新版本"""
        if self._update_checking:
            return
        if self._update_checked:
            return

        self._update_checking = True
        self._update_available = False
        try:
            old_thread = self._check_thread
            if old_thread and old_thread.isRunning():
                old_thread.requestInterruption()
                old_thread.wait(2000)

            self._check_thread = UpdateCheckThread()
            self._check_thread.setParent(self.window)
            self._check_thread.update_found.connect(self._on_update_found)
            self._check_thread.check_completed.connect(self._on_update_check_completed)
            self._check_thread.finished.connect(self._check_thread.deleteLater)
            self._check_thread.start()

        except Exception as e:
            logger.error(f"启动版本检查失败: {str(e)}")
            self._update_checking = False
            self._update_checked = True

    def download_and_install(self):
        """下载并安装更新

        如果已有下载链接则直接开始下载；
        否则先触发版本检查，检查完成后自动开始下载。
        """
        if self._download_url:
            self._start_download()
        else:
            self._pending_download = True
            self._update_checked = False
            self.check_for_updates()

    def _start_download(self):
        """启动下载线程"""
        if not self._download_url:
            # 没有可用的安装包时绝不能回退到 Release 页面（会把网页当安装包下载）
            logger.warning("无可用的更新包下载地址，已取消下载")
            self._show_no_package_message()
            return

        if self._download_thread and self._download_thread.isRunning():
            return

        language_manager = self.window.language_manager
        tr = language_manager.tr

        self._download_thread = UpdateDownloadThread(self._download_url)
        self._download_thread.setParent(self.window)
        self._download_thread.progress.connect(self._on_download_progress)
        self._download_thread.download_complete.connect(self._on_download_complete)
        self._download_thread.download_error.connect(self._on_download_error)
        self._download_thread.finished.connect(self._download_thread.deleteLater)
        self._download_thread.start()

        # 创建进度对话框
        self._progress_dialog = QProgressDialog(
            tr("update_checking", "Checking for updates..."),
            tr("cancel_button", "Cancel"),
            0, 100, self.window
        )
        self._progress_dialog.setWindowTitle(tr("update_progress_title", "Online Update"))
        self._progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setValue(0)
        self._progress_dialog.canceled.connect(self._on_download_canceled)

    def _on_download_progress(self, percent, message):
        if self._progress_dialog:
            if percent >= 0:
                self._progress_dialog.setValue(percent)
            else:
                # 未知总大小时使用忙碌模式
                self._progress_dialog.setRange(0, 0)
            self._progress_dialog.setLabelText(message)

    def _on_download_complete(self, filepath):
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        language_manager = self.window.language_manager
        tr = language_manager.tr

        # 如果从源码运行（非打包），无法自动安装，打开文件夹让用户手动操作
        if not _is_frozen():
            if platform.system() == "Windows":

                norm = os.path.normpath(filepath)
                if os.path.isfile(norm) or os.path.isdir(os.path.dirname(norm)):
                    subprocess.Popen(['explorer', '/select,', norm])
                else:
                    subprocess.Popen(['explorer', os.path.dirname(norm)])
            elif platform.system() == "Darwin":
                subprocess.Popen(['open', os.path.dirname(filepath)])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(filepath)])
            QMessageBox.information(
                self.window,
                tr("update_progress_title", "Online Update"),
                tr("update_complete", "Update downloaded, please restart the application")
            )
            return

        # 询问用户是否安装并重启
        reply = QMessageBox.question(
            self.window,
            tr("update_progress_title", "Online Update"),
            f"{tr('update_complete', 'Update downloaded, please restart the application')}\n"
            f"v{self._current_version} → v{self._latest_version}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._install_update(filepath)

    def _on_download_error(self, message):
        logger.error(f"下载更新失败: {message}")
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        language_manager = self.window.language_manager
        tr = language_manager.tr
        QMessageBox.critical(
            self.window,
            tr("update_progress_title", "Online Update"),
            tr('update_error', 'Update Failed. Please check your network and try again.')
        )

    def _on_download_canceled(self):
        if self._download_thread:
            self._download_thread.cancel()
            self._download_thread = None
        self._progress_dialog = None

    def _install_update(self, filepath):
        """安装更新：根据平台执行不同的安装逻辑"""
        system = platform.system()
        try:
            if system == "Windows":
                self._install_windows(filepath)
            elif system == "Darwin":
                self._install_macos(filepath)
            elif system == "Linux":
                self._install_linux(filepath)
        except Exception as e:
            logger.error(f"安装更新失败: {e}")
            language_manager = self.window.language_manager
            tr = language_manager.tr
            QMessageBox.critical(
                self.window,
                tr("update_progress_title", "Online Update"),
                tr('update_error', 'Update Failed. Please try again.')
            )

    def _message(self, key, default):
        try:
            return self.window.language_manager.tr(key, default)
        except Exception:
            return default

    def _verify_downloaded_file(self, filepath):
        try:
            return os.path.isfile(filepath) and os.path.getsize(filepath) > 0
        except OSError:
            return False

    def _show_install_error(self, detail=""):
        """安装失败的用户可见提示（不静默）"""
        text = self._message(
            "update_install_failed",
            "更新安装失败：无法替换程序文件，已保留当前版本并可继续使用。"
        )
        if detail:
            text = f"{text}\n{detail}"
        QMessageBox.critical(
            self.window,
            self._message("update_progress_title", "在线更新"),
            text
        )

    def _install_windows(self, filepath):
        """Windows: 用下载包替换当前 exe

        运行中的 exe 不能被覆盖写，但允许改名；先改名备份再落位，
        任一环节失败都回滚并提示，绝不启动一个不存在的目标。
        """
        target_exe = resolve_install_target("Windows")
        if not self._verify_downloaded_file(filepath):
            logger.error(f"更新包无效: {filepath}")
            self._show_install_error(filepath)
            return False

        try:
            backup = swap_in_place(filepath, target_exe)
        except Exception as e:
            logger.error(f"Windows 更新替换失败，旧版本保持不变: {e}")
            self._show_install_error(f"{target_exe}\n{e}")
            return False

        try:
            subprocess.Popen([target_exe], cwd=os.path.dirname(target_exe))
        except Exception as e:
            logger.error(f"Windows 新版本启动失败，回滚旧版本: {e}")
            restore_backup(backup, target_exe)
            self._show_install_error(f"{target_exe}\n{e}")
            return False

        _remove_path(backup)
        logger.info(f"Windows 更新完成，已用实际可执行名启动: {target_exe}")
        QApplication.quit()
        return True

    def _install_macos(self, filepath):
        """macOS: 解压 zip 后在主线程校验并替换 .app（失败回滚，不会先删旧版）"""
        target_app = resolve_install_target("Darwin")
        self._extract_thread = _InstallExtractThread(
            "Darwin", filepath, os.path.basename(target_app), self.window
        )
        self._extract_thread.extract_complete.connect(self._on_macos_extract_complete)
        self._extract_thread.extract_error.connect(self._on_extract_error)
        self._extract_thread.finished.connect(self._extract_thread.deleteLater)
        self._extract_thread.start()

    def _on_macos_extract_complete(self, _, new_app):
        """新 .app 已解压到独立临时目录：校验完整 → 备份旧 App → 落位 → 失败回滚"""
        target_app = resolve_install_target("Darwin")

        if not _is_complete_app_bundle(new_app):
            logger.error(f"更新包不完整，保持旧版本可用: {new_app}")
            self._show_install_error(new_app)
            return False

        try:
            backup = swap_in_place(new_app, target_app)
        except Exception as e:
            logger.error(f"macOS 替换 .app 失败，旧版本保持不变: {e}")
            self._show_install_error(f"{target_app}\n{e}")
            return False

        try:
            subprocess.Popen(['open', target_app])
        except Exception as e:
            logger.error(f"macOS 新版本启动失败，回滚旧版本: {e}")
            restore_backup(backup, target_app)
            self._show_install_error(f"{target_app}\n{e}")
            return False

        _remove_path(backup)
        logger.info(f"macOS 更新完成: {target_app}")
        QApplication.quit()
        return True

    def _install_linux(self, filepath):
        """Linux: 解压 tar.gz 后在主线程替换可执行文件（失败回滚并提示）"""
        target_exe = resolve_install_target("Linux")
        self._extract_thread = _InstallExtractThread(
            "Linux", filepath, os.path.basename(target_exe), self.window
        )
        self._extract_thread.extract_complete.connect(self._on_linux_extract_complete)
        self._extract_thread.extract_error.connect(self._on_extract_error)
        self._extract_thread.finished.connect(self._extract_thread.deleteLater)
        self._extract_thread.start()

    def _on_linux_extract_complete(self, _, new_exe):
        """按当前实际可执行名落位；失败回滚，并由主窗口给出可读提示"""
        target_exe = resolve_install_target("Linux")
        try:
            os.chmod(new_exe, 0o755)
            backup = swap_in_place(new_exe, target_exe)
        except Exception as e:
            logger.error(f"Linux 替换失败，旧版本保持不变: {e}")
            self._show_install_error(
                f"{target_exe}\n{e}\n"
                + self._message(
                    "update_install_permission_hint",
                    "若安装目录不可写，请用有权限的方式手动替换或重新安装。"
                )
            )
            return False

        try:
            subprocess.Popen([target_exe], start_new_session=True)
        except Exception as e:
            logger.error(f"Linux 新版本启动失败，回滚旧版本: {e}")
            restore_backup(backup, target_exe)
            self._show_install_error(f"{target_exe}\n{e}")
            return False

        _remove_path(backup)
        logger.info(f"Linux 更新完成: {target_exe}")
        QApplication.quit()
        return True

    def _on_extract_error(self, message):
        logger.error(f"解压失败: {message}")
        language_manager = self.window.language_manager
        tr = language_manager.tr
        QMessageBox.critical(
            self.window,
            tr("update_progress_title", "Online Update"),
            tr('update_error', 'Update Failed. Please try again.')
        )

    def _show_no_package_message(self):
        """提示当前平台没有可用的更新包（不静默、也不下载 HTML 页面）"""
        QMessageBox.information(
            self.window,
            self._message("update_progress_title", "在线更新"),
            self._message(
                "update_no_package",
                "当前平台没有可用的更新包，请前往 Release 页面手动下载："
            ) + "\n" + RELEASE_PAGE_URL
        )

    def _on_update_found(self, latest_version, current_version, download_url=""):
        """发现新版本时的处理"""
        self._latest_version = latest_version
        self._current_version = current_version
        self._download_url = download_url or ""
        self._update_available = True

        try:
            from ui.styles import AppStyles
            language_manager = self.window.language_manager

            original_title = self.window.windowTitle() or ""
            new_version_text = language_manager.tr(
                "new_version_available", "New Version Available"
            ) or "New Version Available"
            if new_version_text not in original_title:
                new_title = f"{original_title} - {new_version_text} {latest_version}"
                self.window.setWindowTitle(new_title)

            found_text = language_manager.tr('new_version_found', 'New version found')
            cur_text = language_manager.tr('current_version', 'Current Version')
            status_message = f"{found_text} {latest_version} ({cur_text} {current_version})"
            self.window.status_bar.showMessage(status_message, 10000)

            self.window.status_bar.setStyleSheet(AppStyles.statusbar_error_style())

            QTimer.singleShot(DelayMs.STATUS_RESET, self.window._reset_statusbar_style)

            logger.info(f"发现新版本: {latest_version} (当前版本: {current_version})")

        except Exception as e:
            logger.error(f"更新界面提示失败: {str(e)}")

        # 如果用户请求了下载（通过关于对话框的"在线更新"按钮），自动开始下载
        if self._pending_download:
            self._pending_download = False
            if self._download_url:
                self._start_download()
            else:
                self._show_no_package_message()

    def _on_update_check_completed(self, success, message):
        self._update_checking = False
        self._update_checked = True
        if success:
            logger.info(f"版本检查完成: {message}")
        else:
            logger.warning(f"版本检查失败: {message}")

        # 如果用户请求了下载但未发现新版本
        if self._pending_download:
            self._pending_download = False
            if not self._download_url:
                if self._update_available:
                    self._show_no_package_message()
                    return
                language_manager = self.window.language_manager
                tr = language_manager.tr
                QMessageBox.information(
                    self.window,
                    tr("update_progress_title", "Online Update"),
                    tr("update_success", "已是最新版本") if success else tr('update_error', 'Update Failed.')
                )
