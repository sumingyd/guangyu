#!/usr/bin/env python3
"""
GuangYu 打包脚本
使用 PyInstaller 将项目打包为可执行文件
支持 Windows (.exe) 和 macOS (.app)
"""

import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


def _download(url, dest, expected_sha256):
    """下载文件并强制校验 SHA256。

    先写入 .part 临时文件，校验通过后才原子替换目标文件，
    避免下载中断留下半截文件被后续步骤误用。
    """
    if not expected_sha256:
        print("错误: 下载校验失败：未提供预期 SHA256，拒绝使用未校验的二进制")
        sys.exit(1)
    dest_path = Path(dest)
    part_path = dest_path.with_name(dest_path.name + ".part")
    print(f"下载: {url}")
    print(f"保存到: {dest}")
    part_path.unlink(missing_ok=True)
    try:
        urllib.request.urlretrieve(url, str(part_path))
        actual_hash = hashlib.sha256(part_path.read_bytes()).hexdigest()
        print(f"SHA256: {actual_hash}")
        if actual_hash.lower() != expected_sha256.lower():
            print(f"错误: SHA256 校验失败！期望: {expected_sha256[:16]}... 实际: {actual_hash[:16]}...")
            part_path.unlink(missing_ok=True)
            sys.exit(1)
        os.replace(part_path, dest_path)
    finally:
        part_path.unlink(missing_ok=True)
    print("SHA256 校验通过")
    print(f"下载完成: {dest}")


def _run(cmd, **kwargs):
    print(f"执行: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, **kwargs)


PROJECT_ROOT = Path(__file__).parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.version import CURRENT_VERSION  # noqa: E402

IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')

APP_NAME = "GuangYu"
BUNDLE_ID = "com.iptv-scanner-editor-pro.app"

DATA_SEP = ';' if IS_WINDOWS else ':'

# 构建先写入 dist.new，成功后再替换 dist：
# 构建失败或中断时不会破坏已有的 dist/ 产物，可随时回退。
DIST_DIR = PROJECT_ROOT / "dist"
DIST_STAGING = PROJECT_ROOT / "dist.new"
DIST_PREVIOUS = PROJECT_ROOT / "dist.prev"

_PNG_ICON = PROJECT_ROOT / "resources" / "logo.png"
ICO_ICON = PROJECT_ROOT / "resources" / "logo.ico"

# 需要打包进产物的数据目录。shaders/ 缺失会导致所有 GLSL 预设静默失效，
# 因此与 mpv/ffmpeg 一样在 _data_args() 中强制校验。
DATA_DIRS = ["mpv", "ffmpeg", "resources", "i18n", "shaders"]


HIDDEN_IMPORTS = [
    "PySide6.QtNetwork",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "numpy",
    "requests",
    "aiohttp",
    "asyncio",
    "utils.platform_utils",
    "controllers",
    "controllers.catchup_controller",
    "controllers.channel_controller",
    "controllers.epg_controller",
    "controllers.epg_reminder_controller",
    "controllers.event_handler",
    "controllers.favorites_controller",
    "controllers.main_window_protocol",
    "controllers.media_controller",
    "controllers.multi_screen_controller",
    "controllers.pip_controller",
    "controllers.playback_controller",
    "controllers.progress_controller",
    "controllers.settings_file_ops",
    "controllers.subscription_controller",
    "controllers.subscription_ui_controller",
    "controllers.ui_controller",
    "controllers.update_controller",
    "controllers.window_controller",
    "mixins",
    "mixins.server_mixin",
    "mixins.tray_mixin",
    "mixins.update_mixin",
    "mixins.thumbnail_mixin",
    "mixins.file_ops_mixin",
    "mixins.panel_mixin",
    "mixins.progress_mixin",
    "mixins.playback_mixin",
    "mixins.epg_mixin",
    "mixins.channel_mixin",
    "mixins.settings_mixin",
    "mixins.window_mixin",
    "mixins.control_panel_mixin",
    "mixins.playlist_panel_mixin",
    "mixins.event_mixin",
    "core",
    "core.application_state",
    "core.config_manager",
    "core.language_manager",
    "core.log_manager",
    "core.panel_visibility",
    "core.play_state",
    "core.subscription_manager",
    "core.version",
    "models",
    "models.channel_mappings",
    "models.channel_model",
    "services",
    "services.batch_edit_service",
    "services.channel_classifier",
    "services.channel_cleaner",
    "services.channel_rating_service",
    "services.channel_quick_jump_service",
    "services.channel_dedup_service",
    "services.stream_quality_scorer",
    "services.epg_matcher",
    "services.epg_reminder_service",
    "services.epg_search_service",
    "services.favorites_service",
    "services.fcc_service",
    "services.logo_cache_service",
    "services.logo_matcher",
    "services.m3u_parser",
    "services.mpv_common",
    "services.mpv_gl_widget",
    "services.mpv_player_service",
    "services.ffprobe_validator_service",
    "services.mpv_validator_service",
    "services.scanner_service",
    "services.thumbnail_service",
    "services.url_parser_service",
    "server",
    "server.app",
    "server.routes",
    "ui",
    "ui.dialogs",
    "ui.dialogs.about_dialog",
    "ui.dialogs.epg_timeline_dialog",
    "ui.dialogs.file_association_dialog",
    "ui.dialogs.mapping_manager_dialog",
    "ui.dialogs.scan_channel_dialog",
    "ui.dialogs.reminder_popup",
    "ui.dialogs.reminder_manager_dialog",
    "ui.dialogs.unified_search_dialog",
    "ui.dialogs.video_open_dialog",
    "ui.dialogs.epg_search_dialog",
    "ui.dialogs.global_search_dialog",
    "ui.dialogs.subtitle_style_dialog",
    "ui.dialogs.video_eq_dialog",
    "ui.dialogs.audio_eq_dialog",
    "ui.dialogs.playback_queue_dialog",
    "ui.dialogs.resume_position_dialog",
    "ui.dialogs.network_enhance_dialog",
    "ui.dialogs.burst_screenshot_dialog",
    "ui.dialogs.bookmark_dialog",
    "ui.dialogs.av_sync_dialog",
    "ui.dialogs.stream_quality_dialog",
    "ui.dialogs.video_3d_dialog",
    "controllers.file_queue_controller",
    "controllers.resume_playback_controller",
    "controllers.bookmark_controller",
    "services.subtitle_download_service",
    "ui.epg_timeline_widget",
    "ui.floating_dialog",
    "ui.multi_screen_widget",
    "ui.virtual_channel_list",
    "ui.menu_proxy_style",
    "ui.cache_progress_slider",
    "ui.channel_transition_overlay",
    "ui.styles",
    "ui.theme_manager",
    "utils",
    "utils.config_notifier",
    "utils.error_handler",
    "utils.general_utils",
    "utils.hdr_detect",
    "utils.logging_helper",
    "utils.mac_blur_helper",
    "utils.memory_manager",
    "utils.progress_manager",
    "utils.resource_cleaner",
    "utils.scan_state_manager",
    "utils.singleton",
    "utils.thread_safety",
]

# 需要完整收集的包（含 C 扩展、数据文件、子模块）。
# numpy 仅用 --hidden-import 不够，其 C 扩展（如 _multiarray_umath）必须用 --collect-all 才能正确打包，
# 否则用户运行时报 "Importing the numpy C-extensions failed"。
COLLECT_ALL = [
    "numpy",
]


def _log_environment():
    print(f"当前 Python 版本: {sys.version}")
    print(f"当前工作目录: {os.getcwd()}")
    print(f"当前平台: {sys.platform}")
    print(f"项目根目录: {PROJECT_ROOT}")


def _check_pyinstaller():
    try:
        import PyInstaller
    except ImportError:
        print("错误: PyInstaller 未安装，请运行: pip install -r requirements.txt")
        sys.exit(1)
    print(f"PyInstaller 版本: {PyInstaller.__version__}")


def _data_args():
    """统一的 --add-data 清单，所有平台共用，避免各平台漏收集资源。"""
    args = []
    for name in DATA_DIRS:
        src = PROJECT_ROOT / name
        if not src.exists():
            print(f"错误: 缺少打包资源目录: {src}")
            sys.exit(1)
        args.extend(["--add-data", f"{src}{DATA_SEP}{name}"])
    return args


def _hidden_import_args():
    args = []
    for imp in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", imp])
    for pkg in COLLECT_ALL:
        args.extend(["--collect-all", pkg])
    return args


def _pyinstaller_base(onefile: bool):
    """所有平台共用的 PyInstaller 参数。

    产物先写入 dist.new；只有构建成功后才提升为 dist/，
    因此构建中断不会破坏上一次可用的发布产物。
    """
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", APP_NAME,
        "--distpath", str(DIST_STAGING),
        "--workpath", str(PROJECT_ROOT / "build"),
    ]
    if onefile:
        cmd.append("--onefile")
    return cmd


def _macos_icns_path():
    """构建前从 AppIcon.iconset 生成 .icns，供 --icon 与 .app 内图标使用。"""
    iconset = PROJECT_ROOT / "resources" / "AppIcon.iconset"
    if not iconset.is_dir():
        print("警告: resources/AppIcon.iconset 不存在，macOS 将使用默认图标")
        return None
    out_dir = PROJECT_ROOT / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    icns = out_dir / "logo.icns"
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", "-o", str(icns), str(iconset)],
            check=True, timeout=60,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"错误: 生成 macOS 图标失败（iconutil）: {e}")
        sys.exit(1)
    print(f"macOS 图标已生成: {icns}")
    return icns


def _staging_output_path():
    if IS_MACOS:
        return DIST_STAGING / f"{APP_NAME}.app"
    if IS_WINDOWS:
        return DIST_STAGING / f"{APP_NAME}.exe"
    return DIST_STAGING / APP_NAME


def _fail_build(message):
    print(f"错误: {message}")
    if DIST_STAGING.exists():
        shutil.rmtree(DIST_STAGING, ignore_errors=True)
    sys.exit(1)


def _promote_staging():
    """把 dist.new 提升为 dist/，上一版保留在 dist.prev/ 便于回退。"""
    if DIST_PREVIOUS.exists():
        shutil.rmtree(DIST_PREVIOUS)
    if DIST_DIR.exists():
        DIST_DIR.rename(DIST_PREVIOUS)
        print(f"旧产物已备份到: {DIST_PREVIOUS}")
    DIST_STAGING.rename(DIST_DIR)
    print(f"新产物已就位: {DIST_DIR}")


def _find_macos_libmpv():
    search_paths = [
        Path("/opt/homebrew/lib/libmpv.2.dylib"),
        Path("/usr/local/lib/libmpv.2.dylib"),
    ]
    for p in search_paths:
        if p.exists():
            return p
    try:
        result = _run(["brew", "--prefix", "mpv"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            brew_prefix = result.stdout.strip()
            candidate = Path(brew_prefix) / "lib" / "libmpv.2.dylib"
            if candidate.exists():
                return candidate
    except Exception:
        pass
    return None


def _find_libxcb_cursor():
    """查找系统中的 libxcb-cursor.so.0

    Qt6 的 xcb 平台插件依赖此库，PyInstaller 不会自动收集系统库，
    因此需要手动查找并打包，避免用户在 Ubuntu 22.04+/Debian 12+ 等
    未预装 libxcb-cursor0 的系统上无法启动应用。
    """
    # 1. 通过 ldconfig 缓存查找（最可靠，能解析符号链接的真实路径）
    try:
        result = _run(["ldconfig", "-p"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "libxcb-cursor.so.0" in line:
                    parts = line.strip().split("=>")
                    if len(parts) == 2:
                        p = parts[1].strip()
                        if p and os.path.exists(p):
                            return p
    except Exception:
        pass

    # 2. 按架构在常见系统目录中查找
    machine = os.uname().machine if hasattr(os, "uname") else ""
    arch_dirs = []
    if machine == "aarch64":
        arch_dirs = ["/usr/lib/aarch64-linux-gnu/", "/usr/lib64/", "/lib/aarch64-linux-gnu/"]
    elif machine == "x86_64":
        arch_dirs = ["/usr/lib/x86_64-linux-gnu/", "/usr/lib64/", "/lib/x86_64-linux-gnu/"]
    arch_dirs.extend(["/usr/local/lib/", "/usr/lib/", "/lib/"])

    for d in arch_dirs:
        p = os.path.join(d, "libxcb-cursor.so.0")
        if os.path.exists(p):
            return p

    return None


def _verify_libmpv_cocoa(dylib_path):
    result = _run(["nm", "-gU", str(dylib_path)], capture_output=True, text=True)
    if result.returncode == 0 and 'cocoa' in result.stdout.lower():
        print("  cocoa GPU context 支持: 已确认")
        return True
    print("  警告: 未检测到cocoa GPU context支持，macOS下可能无法显示视频")
    return False


def _fix_dylib_install_name(dylib_path):
    try:
        result = _run(["otool", "-L", str(dylib_path)], capture_output=True, text=True)
        if result.returncode != 0:
            return
        needs_fix = False
        for line in result.stdout.splitlines():
            if '/usr/local/' in line or '/opt/homebrew/' in line:
                needs_fix = True
                break
        if not needs_fix:
            return
        print("  修复dylib引用路径为@rpath...")
        _run(["install_name_tool", "-id", "@rpath/libmpv.2.dylib", str(dylib_path)])
        for old_prefix in ["/usr/local/lib/", "/opt/homebrew/lib/"]:
            _run(["install_name_tool", "-change", f"{old_prefix}libmpv.2.dylib",
                  "@rpath/libmpv.2.dylib", str(dylib_path)])
        # arm64 要求动态库必须有有效签名；install_name_tool 改写
        # LC_ID_DYLIB / LC_LOAD_DYLIB 后原签名立即失效，不重签会被内核拒绝加载。
        sign = _run(["codesign", "--force", "--sign", "-", str(dylib_path)],
                    capture_output=True, text=True)
        if sign.returncode != 0:
            print(f"  警告: install_name 修复后 ad-hoc 重签名失败: {sign.stderr.strip()}")
        else:
            print("  dylib 已 ad-hoc 重签名")
    except Exception as e:
        print(f"  修复dylib引用路径失败: {e}")


def prepare_macos_dependencies():
    mpv_dir = PROJECT_ROOT / "mpv"
    mpv_dir.mkdir(exist_ok=True)
    dylib_dest = mpv_dir / "libmpv.2.dylib"

    if dylib_dest.exists():
        print(f"libmpv.2.dylib 已就绪: {dylib_dest}")
        _verify_libmpv_cocoa(dylib_dest)
        _fix_dylib_install_name(dylib_dest)
    else:
        src = _find_macos_libmpv()
        if src:
            shutil.copy2(src, dylib_dest)
            print(f"libmpv.2.dylib 已从 {src} 复制到 {dylib_dest}")
            _verify_libmpv_cocoa(dylib_dest)
            _fix_dylib_install_name(dylib_dest)
        else:
            print("错误: 未找到 libmpv.2.dylib")
            print("  请先安装: brew install mpv")
            print("  或手动放置到: mpv/libmpv.2.dylib")
            sys.exit(1)

    ffmpeg_dir = PROJECT_ROOT / "ffmpeg"
    ffmpeg_dir.mkdir(exist_ok=True)
    ffprobe_dest = ffmpeg_dir / "ffprobe"

    if not ffprobe_dest.exists():
        ffprobe_found = False
        for src in [
            Path("/opt/homebrew/bin/ffprobe"),
            Path("/usr/local/bin/ffprobe"),
        ]:
            if src.exists():
                shutil.copy2(src, ffprobe_dest)
                os.chmod(ffprobe_dest, 0o755)
                print(f"ffprobe 已从 {src} 复制到 {ffprobe_dest}")
                ffprobe_found = True
                break

        if not ffprobe_found:
            result = _run(["which", "ffprobe"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                src = Path(result.stdout.strip())
                shutil.copy2(src, ffprobe_dest)
                os.chmod(ffprobe_dest, 0o755)
                print(f"ffprobe 已从 {src} 复制到 {ffprobe_dest}")
                ffprobe_found = True

        if not ffprobe_found:
            import platform
            mac_arch = platform.machine()
            if mac_arch == 'arm64':
                ffprobe_url = "https://www.osxexperts.net/ffprobe81arm.zip"
            else:
                ffprobe_url = "https://www.osxexperts.net/ffprobe80intel.zip"

            expected_hash = os.environ.get("FFPROBE_SHA256", "").strip()
            if not expected_hash:
                print("错误: 本机未安装 ffprobe，且未配置 FFPROBE_SHA256")
                print("  为避免引入未经校验的第三方二进制，构建已中止。")
                print("  处理方式（任选其一）:")
                print("    1) brew install ffmpeg")
                print("    2) 手动把 ffprobe 放到 ffmpeg/ffprobe")
                print("    3) 首次人工下载后执行 shasum -a 256，再用 FFPROBE_SHA256=<hash> 重跑构建")
                sys.exit(1)

            zip_path = PROJECT_ROOT / "_ffprobe_download.zip"
            try:
                _download(ffprobe_url, str(zip_path), expected_hash)
                extract_dir = PROJECT_ROOT / "_ffprobe_extract"
                extract_dir.mkdir(exist_ok=True)
                _run(["unzip", "-o", str(zip_path), "-d", str(extract_dir)], check=True)
                extracted = list(extract_dir.rglob("ffprobe"))
                if extracted:
                    shutil.copy2(extracted[0], ffprobe_dest)
                    os.chmod(ffprobe_dest, 0o755)
                    print(f"ffprobe 已下载并放置到: {ffprobe_dest}")
                else:
                    print("错误: 下载的 zip 中未找到 ffprobe")
                    sys.exit(1)
            finally:
                for p in [zip_path, PROJECT_ROOT / "_ffprobe_extract"]:
                    if p.exists():
                        if p.is_dir():
                            shutil.rmtree(p)
                        else:
                            p.unlink()
    else:
        print(f"ffprobe 已就绪: {ffprobe_dest}")


def prepare_windows_dependencies():
    mpv_dir = PROJECT_ROOT / "mpv"
    if not (mpv_dir / "libmpv-2.dll").exists():
        print("错误: 未找到 mpv/libmpv-2.dll，请手动放置到 mpv/ 目录")
        sys.exit(1)
    print(f"libmpv-2.dll 已就绪: {mpv_dir / 'libmpv-2.dll'}")

    ffmpeg_dir = PROJECT_ROOT / "ffmpeg"
    if not (ffmpeg_dir / "ffprobe.exe").exists():
        print("错误: 未找到 ffmpeg/ffprobe.exe，请手动放置到 ffmpeg/ 目录")
        sys.exit(1)
    print(f"ffprobe.exe 已就绪: {ffmpeg_dir / 'ffprobe.exe'}")


def build_macos():
    prepare_macos_dependencies()
    cmd = _pyinstaller_base(onefile=False)
    cmd.extend([
        "--windowed",
        "--osx-bundle-identifier", BUNDLE_ID,
        # mac 专有模块是运行时按需 import 的，PyInstaller 静态分析看不到
        "--hidden-import", "objc",
        "--hidden-import", "AppKit",
    ])
    icns = _macos_icns_path()
    if icns:
        cmd.extend(["--icon", str(icns)])
    cmd.extend(_data_args())
    cmd.extend(_hidden_import_args())
    cmd.append(str(PROJECT_ROOT / "main.py"))
    return cmd


def build_windows():
    prepare_windows_dependencies()
    cmd = _pyinstaller_base(onefile=True)
    cmd.append("--windowed")
    if ICO_ICON.exists():
        cmd.extend(["--icon", str(ICO_ICON)])
    else:
        print(f"警告: 图标不存在，跳过: {ICO_ICON}")
    cmd.extend(_data_args())
    cmd.extend(_hidden_import_args())
    cmd.append(str(PROJECT_ROOT / "main.py"))
    return cmd


def _linux_missing_shared_deps(lib_path):
    """用 ldd 检查共享库未解析的依赖，返回缺失的库名列表。

    只在打包机上有 ldd 时可用；检查失败时返回空列表（不阻断构建）。
    """
    try:
        result = subprocess.run(
            ['ldd', str(lib_path)], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"提示: 无法执行 ldd 检查 {lib_path}: {e}")
        return []
    missing = []
    for line in (result.stdout or '').splitlines():
        line = line.strip()
        if 'not found' in line:
            missing.append(line.split('=>')[0].strip())
    return missing


def prepare_linux_dependencies():
    mpv_dir = PROJECT_ROOT / "mpv"
    mpv_dir.mkdir(exist_ok=True)
    has_mpv = any((mpv_dir / name).exists() for name in ['libmpv.so.2', 'libmpv.so.1', 'libmpv.so'])
    if not has_mpv:
        # 与 Windows 分支保持一致：缺少 libmpv 时产物根本无法播放，
        # 不允许"构建成功但用户装上不能播"，必须显式失败。
        print("错误: mpv/ 目录缺少 libmpv.so*，发布包将无法播放视频")
        print("  请放置 libmpv 到 mpv/ 目录，或执行: sudo apt install libmpv-dev")
        print("  仅调试打包流程时可设置 GUANGYU_ALLOW_SYSTEM_LIBMPV=1 跳过此检查")
        if os.environ.get("GUANGYU_ALLOW_SYSTEM_LIBMPV") != "1":
            sys.exit(1)
        print("警告: 已按 GUANGYU_ALLOW_SYSTEM_LIBMPV=1 继续，产物依赖系统 libmpv")
    else:
        print(f"libmpv.so 已就绪: {mpv_dir}")
        libmpv_file = next(
            (mpv_dir / name for name in ['libmpv.so.2', 'libmpv.so.1', 'libmpv.so']
             if (mpv_dir / name).exists()),
            None,
        )
        missing = _linux_missing_shared_deps(libmpv_file) if libmpv_file else []
        if missing:
            print("错误: libmpv 依赖的共享库在打包机上未解析，用户机器上同样会加载失败:")
            for name in missing:
                print(f"  - {name}")
            print("  请在打包机安装对应运行库（或改用静态链接的 libmpv）后重试")
            if os.environ.get("GUANGYU_ALLOW_SYSTEM_LIBMPV") != "1":
                sys.exit(1)
            print("警告: 已按 GUANGYU_ALLOW_SYSTEM_LIBMPV=1 继续，产物可能无法加载 libmpv")
        else:
            print("libmpv 依赖检查通过（ldd 无未解析项）")

    ffmpeg_dir = PROJECT_ROOT / "ffmpeg"
    ffmpeg_dir.mkdir(exist_ok=True)
    ffprobe_path = ffmpeg_dir / "ffprobe"
    if not ffprobe_path.exists():
        print("错误: 未找到 ffmpeg/ffprobe，请手动放置到 ffmpeg/ 目录")
        print("  或执行: sudo apt install ffmpeg")
        sys.exit(1)
    # PyInstaller 6.x 按源文件权限复制 data 文件；缺少执行位时打包后无法调用
    try:
        ffprobe_path.chmod(ffprobe_path.stat().st_mode | 0o111)
    except OSError as e:
        print(f"警告: 无法为 ffprobe 添加执行权限: {e}")
    print(f"ffprobe 已就绪: {ffprobe_path}")

    # 打包 libxcb-cursor.so.0：Qt6 的 xcb 平台插件依赖此库，
    # PyInstaller 不会自动收集系统库，需手动打包以避免用户手动安装 libxcb-cursor0
    libs_dir = PROJECT_ROOT / "libs"
    libs_dir.mkdir(exist_ok=True)
    xcb_cursor_dest = libs_dir / "libxcb-cursor.so.0"
    xcb_cursor_src = _find_libxcb_cursor()
    if xcb_cursor_src:
        shutil.copy2(xcb_cursor_src, xcb_cursor_dest)
        print(f"libxcb-cursor.so.0 已从 {xcb_cursor_src} 复制到 {xcb_cursor_dest}")
    else:
        print("错误: 未找到 libxcb-cursor.so.0，Qt 在 Ubuntu 22.04+/Debian 12+ 上可能无法启动")
        print("  请安装: sudo apt install libxcb-cursor0")
        if os.environ.get("GUANGYU_ALLOW_SYSTEM_LIBMPV") != "1":
            sys.exit(1)
        print("警告: 已按 GUANGYU_ALLOW_SYSTEM_LIBMPV=1 继续，用户需自行安装 libxcb-cursor0")


def _linux_data_args():
    """Linux 专用 --add-data 清单：剔除 mpv/ffmpeg 里的 Windows/macOS 二进制。

    仓库里这些目录同时存放各平台文件（libmpv-2.dll、ffprobe.exe 等），
    直接整目录打包会把几十 MB 的无关二进制塞进 Linux 产物。
    """
    staging_root = PROJECT_ROOT / "build" / "linux-data"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    ignore = shutil.ignore_patterns("*.dll", "*.exe", "*.dylib", "*.ico")
    args = []
    for name in DATA_DIRS:
        src = PROJECT_ROOT / name
        if not src.exists():
            print(f"错误: 缺少打包资源目录: {src}")
            sys.exit(1)
        dest = staging_root / name
        shutil.copytree(src, dest, ignore=ignore)
        args.extend(["--add-data", f"{dest}{DATA_SEP}{name}"])
    return args


def build_linux():
    prepare_linux_dependencies()
    cmd = _pyinstaller_base(onefile=True)
    cmd.append("--windowed")
    if _PNG_ICON.exists():
        cmd.extend(["--icon", str(_PNG_ICON)])
    # 将 libxcb-cursor.so.0 打包到解压后的根目录，
    # PyInstaller 运行时会把 _MEIPASS 加入 LD_LIBRARY_PATH，Qt 的 xcb 平台插件即可找到此库
    xcb_cursor_lib = PROJECT_ROOT / "libs" / "libxcb-cursor.so.0"
    if xcb_cursor_lib.exists():
        cmd.extend(["--add-binary", f"{xcb_cursor_lib}{DATA_SEP}."])
    cmd.extend(_linux_data_args())
    cmd.extend(_hidden_import_args())
    cmd.append(str(PROJECT_ROOT / "main.py"))
    return cmd



def post_process_windows():
    """Windows 打包后处理：在 exe 同级目录创建备用 mpv/ 和 ffmpeg/ 目录。

    onefile 模式的 _MEIPASS 临时目录可能因 UPX 解压失败、杀毒软件删除、
    临时目录被清理等原因丢失 dll。find_libmpv_path() 会从 exe 同级目录的
    mpv/ 查找备用 dll，此函数确保备用 dll 就位。
    """
    dist_dir = DIST_DIR
    exe_path = dist_dir / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print(f"警告: 可执行文件未找到: {exe_path}")
        return

    # 复制 libmpv-2.dll 到 dist/mpv/（备用路径，_MEIPASS 解压失败时使用）
    src_dll = PROJECT_ROOT / "mpv" / "libmpv-2.dll"
    if src_dll.exists():
        dest_mpv_dir = dist_dir / "mpv"
        dest_mpv_dir.mkdir(parents=True, exist_ok=True)
        dest_dll = dest_mpv_dir / "libmpv-2.dll"
        shutil.copy2(str(src_dll), str(dest_dll))
        print(f"备用 libmpv-2.dll 已复制: {dest_dll}")
    else:
        print("警告: mpv/libmpv-2.dll 不存在，跳过备用 dll 复制")

    # 复制 ffprobe.exe 到 dist/ffmpeg/（备用路径）
    src_ffprobe = PROJECT_ROOT / "ffmpeg" / "ffprobe.exe"
    if src_ffprobe.exists():
        dest_ffmpeg_dir = dist_dir / "ffmpeg"
        dest_ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        dest_ffprobe = dest_ffmpeg_dir / "ffprobe.exe"
        shutil.copy2(str(src_ffprobe), str(dest_ffprobe))
        print(f"备用 ffprobe.exe 已复制: {dest_ffprobe}")
    else:
        print("警告: ffmpeg/ffprobe.exe 不存在，跳过备用 ffprobe 复制")


def post_process_macos_app():
    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        print(f"警告: .app 未找到: {app_path}")
        return

    info_plist_path = app_path / "Contents" / "Info.plist"
    if info_plist_path.exists():
        with open(info_plist_path, 'rb') as f:
            plist = plistlib.load(f)
    else:
        plist = {}

    plist.update({
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleIdentifier': BUNDLE_ID,
        'CFBundleVersion': CURRENT_VERSION,
        'CFBundleShortVersionString': CURRENT_VERSION,
        'CFBundlePackageType': 'APPL',
        'CFBundleInfoDictionaryVersion': '6.0',
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'CFBundleIconFile': 'logo',
        'CFBundleIconName': 'logo',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'M3U Playlist',
                'CFBundleTypeRole': 'Viewer',
                'LSItemContentTypes': ['public.m3u-playlist'],
                'CFBundleTypeExtensions': ['m3u', 'm3u8'],
            },
        ],
        'UTImportedTypeDeclarations': [
            {
                'UTTypeIdentifier': 'public.m3u-playlist',
                'UTTypeConformsTo': ['public.text'],
                'UTTypeDescription': 'M3U Playlist',
                'UTTypeTagSpecification': {
                    'public.filename-extension': ['m3u', 'm3u8'],
                },
            },
        ],
    })

    with open(info_plist_path, 'wb') as f:
        plistlib.dump(plist, f)

    print(f"Info.plist 已更新: {info_plist_path}")

    resources_dir = app_path / "Contents" / "Resources"
    resources_dir.mkdir(parents=True, exist_ok=True)

    logo_png = PROJECT_ROOT / "resources" / "logo.png"
    if logo_png.exists():
        shutil.copy2(str(logo_png), str(resources_dir / "logo.png"))
        print(f"图标已复制: {resources_dir / 'logo.png'}")

    iconset_dir = PROJECT_ROOT / "resources" / "AppIcon.iconset"
    built_icns = PROJECT_ROOT / "build" / "logo.icns"
    if built_icns.exists():
        shutil.copy2(str(built_icns), str(resources_dir / "logo.icns"))
        print(f"logo.icns 已复制: {resources_dir / 'logo.icns'}")
    elif iconset_dir.exists():
        try:
            subprocess.run(
                ['iconutil', '-c', 'icns', '-o', str(resources_dir / 'logo.icns'), str(iconset_dir)],
                check=True, timeout=30,
            )
            print(f"logo.icns 已生成: {resources_dir / 'logo.icns'}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("提示: iconutil 不可用，跳过 .icns 生成（macOS 上需要）")
            if logo_png.exists():
                print("  将使用 logo.png 作为图标")

    print(f"macOS .app 打包完成: {app_path}")


def _write_macos_entitlements():
    """生成 hardened runtime 所需的 entitlements（输出到 build/，不写入仓库）。"""
    ent_dir = PROJECT_ROOT / "build"
    ent_dir.mkdir(exist_ok=True)
    ent_path = ent_dir / "macos_entitlements.plist"
    entitlements = {
        # PyInstaller 引导器 + Python 运行时
        "com.apple.security.cs.allow-jit": True,
        "com.apple.security.cs.allow-unsigned-executable-memory": True,
        # 包内 libmpv/ffprobe/PySide6 框架签名链不同，需要放宽库校验
        "com.apple.security.cs.disable-library-validation": True,
        # mpv_common 通过 DYLD_LIBRARY_PATH 指向 Contents/Resources/mpv
        "com.apple.security.cs.allow-dyld-environment-variables": True,
    }
    with open(ent_path, "wb") as f:
        plistlib.dump(entitlements, f)
    return ent_path


def code_sign_and_notarize_macos(app_path):
    """对 .app 做 hardened runtime 签名，并在配置了凭据时提交公证。

    全部由环境变量驱动，未设置时只跳过并提示，不会让本地构建失败：
    - MACOS_CODESIGN_IDENTITY: 如 "Developer ID Application: Foo (TEAMID)"
    - APPLE_ID / APPLE_TEAM_ID / APPLE_APP_PASSWORD: notarytool 凭据
    """
    identity = os.environ.get("MACOS_CODESIGN_IDENTITY", "").strip()
    if not identity:
        print("提示: 未设置 MACOS_CODESIGN_IDENTITY，跳过签名/公证（产物仅适合本机测试）")
        return
    if not app_path.exists():
        print(f"警告: 未找到 .app，跳过签名: {app_path}")
        return

    ent_path = _write_macos_entitlements()
    print(f"使用证书签名: {identity}")
    sign = _run([
        "codesign", "--force", "--deep", "--options", "runtime",
        "--timestamp", "--entitlements", str(ent_path),
        "--sign", identity, str(app_path),
    ], capture_output=True, text=True)
    if sign.returncode != 0:
        _fail_build(f"codesign 失败: {sign.stderr.strip() or sign.stdout.strip()}")

    verify = _run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)],
        capture_output=True, text=True,
    )
    if verify.returncode != 0:
        _fail_build(f"codesign 校验失败: {verify.stderr.strip() or verify.stdout.strip()}")
    print("签名完成")

    apple_id = os.environ.get("APPLE_ID", "").strip()
    team_id = os.environ.get("APPLE_TEAM_ID", "").strip()
    password = os.environ.get("APPLE_APP_PASSWORD", "").strip()
    if not (apple_id and team_id and password):
        print("提示: 未配置 APPLE_ID/APPLE_TEAM_ID/APPLE_APP_PASSWORD，跳过公证")
        return

    zip_path = DIST_DIR / f"{APP_NAME}-notarize.zip"
    try:
        shutil.make_archive(
            str(zip_path.with_suffix('')), 'zip',
            root_dir=str(app_path.parent), base_dir=app_path.name,
        )
        print("正在提交 Apple 公证（可能需要几分钟）...")
        # 直接用 subprocess，避免 _run 把含密码的命令打印到 CI 日志
        result = subprocess.run([
            "xcrun", "notarytool", "submit", str(zip_path),
            "--apple-id", apple_id, "--team-id", team_id,
            "--password", password, "--wait",
        ], capture_output=True, text=True)
        if result.returncode != 0:
            _fail_build(
                "公证失败: "
                + (result.stdout or "")[-2000:]
                + (result.stderr or "")[-1000:]
            )
        print("公证通过，正在 stapling...")
        staple = _run(["xcrun", "stapler", "staple", str(app_path)],
                      capture_output=True, text=True)
        if staple.returncode != 0:
            _fail_build(f"stapler 失败: {staple.stderr.strip()}")
        print("公证与 stapling 完成")
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass


def post_process_linux():
    dist_dir = DIST_DIR
    exe_path = dist_dir / APP_NAME
    if not exe_path.exists():
        print(f"警告: 可执行文件未找到: {exe_path}")
        return

    logo_png = PROJECT_ROOT / "resources" / "logo.png"
    if not logo_png.exists():
        print("警告: logo.png 不存在，跳过 Linux 图标安装")
        return

    icon_dir = dist_dir / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(logo_png), str(icon_dir / f"{APP_NAME}.png"))
    shutil.copy2(str(logo_png), str(dist_dir / f"{APP_NAME}.png"))
    print(f"图标已复制: {icon_dir / APP_NAME}.png")

    desktop_content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=IPTV Channel Scanner and Editor
Exec=/usr/local/bin/{APP_NAME}
TryExec=/usr/local/bin/{APP_NAME}
Icon={APP_NAME}
Categories=AudioVideo;Video;Network;
Terminal=false
StartupWMClass={APP_NAME}
"""
    desktop_path = dist_dir / f"{APP_NAME}.desktop"
    with open(desktop_path, 'w', encoding='utf-8') as f:
        f.write(desktop_content)
    print(f".desktop 文件已生成: {desktop_path}")

    install_script = f"""#!/bin/bash
# 安装 {APP_NAME} 到系统
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXE="$SCRIPT_DIR/{APP_NAME}"

sudo cp "$EXE" /usr/local/bin/{APP_NAME}
sudo chmod +x /usr/local/bin/{APP_NAME}

sudo mkdir -p /usr/local/share/icons/hicolor/256x256/apps
sudo cp "$SCRIPT_DIR/icons/{APP_NAME}.png" /usr/local/share/icons/hicolor/256x256/apps/{APP_NAME}.png

sudo mkdir -p /usr/local/share/pixmaps
sudo cp "$SCRIPT_DIR/{APP_NAME}.png" /usr/local/share/pixmaps/{APP_NAME}.png

cat > /tmp/{APP_NAME}.desktop << DESKTOP
[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=IPTV Channel Scanner and Editor
Exec=/usr/local/bin/{APP_NAME}
Icon={APP_NAME}
Categories=AudioVideo;Video;Network;
Terminal=false
StartupWMClass={APP_NAME}
DESKTOP

sudo cp /tmp/{APP_NAME}.desktop /usr/local/share/applications/{APP_NAME}.desktop
sudo desktop-file-install /usr/local/share/applications/{APP_NAME}.desktop 2>/dev/null || true
sudo update-desktop-database /usr/local/share/applications/ 2>/dev/null || true
sudo gtk-update-icon-cache -f /usr/local/share/icons/hicolor/ 2>/dev/null || true

echo "安装完成! 可以从应用菜单启动 {APP_NAME}"
"""
    install_path = dist_dir / "install.sh"
    with open(install_path, 'w', encoding='utf-8') as f:
        f.write(install_script)
    import stat
    install_path.chmod(install_path.stat().st_mode | stat.S_IEXEC)
    print(f"安装脚本已生成: {install_path}")

    print("Linux 打包后处理完成")


def clean_build():
    """清理中间产物，但保留 dist/ 作为可回退的上一版产物。"""
    print("清理之前的构建结果...")
    build_dir = PROJECT_ROOT / "build"
    if build_dir.exists():
        print(f"移除构建目录: {build_dir}")
        shutil.rmtree(build_dir)
    if DIST_STAGING.exists():
        print(f"移除未完成产物: {DIST_STAGING}")
        shutil.rmtree(DIST_STAGING)
    if DIST_PREVIOUS.exists():
        print(f"移除旧备份: {DIST_PREVIOUS}")
        shutil.rmtree(DIST_PREVIOUS)
    spec_file = PROJECT_ROOT / f"{APP_NAME}.spec"
    if spec_file.exists():
        print(f"移除 spec 文件: {spec_file}")
        spec_file.unlink()
    print("清理完成")


def run_build():
    if IS_MACOS:
        cmd = build_macos()
    elif IS_LINUX:
        cmd = build_linux()
    else:
        cmd = build_windows()

    print("开始打包...")
    print(f"执行命令: {' '.join(cmd)}")

    # 直接继承 stdout/stderr：长时间打包时可以看到实时进度，
    # 也不会因为 300 秒超时把正常构建误判为失败。
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    print(f"返回码: {result.returncode}")
    if result.returncode != 0:
        _fail_build("打包失败，dist/ 中保留的仍是上一次可用产物")

    expected = _staging_output_path()
    if not expected.exists():
        _fail_build(f"打包命令返回成功但未找到产物: {expected}")

    _promote_staging()

    if IS_MACOS:
        post_process_macos_app()
        code_sign_and_notarize_macos(DIST_DIR / f"{APP_NAME}.app")
        print(f"打包完成! .app 位于: dist/{APP_NAME}.app")
    elif IS_LINUX:
        post_process_linux()
        print(f"打包完成! 可执行文件位于: dist/{APP_NAME}")
    else:
        post_process_windows()
        print(f"打包完成! 可执行文件位于: dist/{APP_NAME}.exe")


def main():
    print("=== GuangYu 打包脚本 ===")
    _log_environment()
    _check_pyinstaller()
    clean_build()
    try:
        run_build()
    except Exception as e:
        print(f"打包过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        if DIST_STAGING.exists():
            shutil.rmtree(DIST_STAGING, ignore_errors=True)
        sys.exit(1)
    print("=== 打包脚本执行完成 ===")


if __name__ == "__main__":
    main()
