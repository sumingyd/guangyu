"""更新器纯逻辑单测：产物命名、安装目标推导、版本比较、替换回滚。"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from controllers import update_controller as uc  # noqa: E402


def test_platform_asset_names_derived_from_app_name():
    assert uc._get_platform_asset_name("Windows", "AMD64") == "GuangYu-Windows-x86_64.exe"
    assert uc._get_platform_asset_name("Darwin", "arm64") == "GuangYu-macOS-ARM64.zip"
    assert uc._get_platform_asset_name("Linux", "aarch64") == "GuangYu-Linux-ARM64.tar.gz"
    assert uc._get_platform_asset_name("Linux", "x86_64") == "GuangYu-Linux-x86_64.tar.gz"
    assert uc._get_platform_asset_name("FreeBSD", "x86_64") is None


def test_install_target_uses_runtime_executable_name():
    """Windows/Linux 安装目标必须是运行时真实可执行文件，而不是旧硬编码名。"""
    win_target = uc.resolve_install_target("Windows", os.path.join("C:", "Apps", "MyPlayer.exe"))
    assert os.path.basename(win_target) == "MyPlayer.exe"

    linux_target = uc.resolve_install_target("Linux", "/opt/guangyu/bin/MyPlayer")
    assert os.path.basename(linux_target) == "MyPlayer"


def test_install_target_resolves_macos_bundle():
    exe = "/Applications/GuangYu.app/Contents/MacOS/GuangYu"
    assert os.path.basename(uc.resolve_install_target("Darwin", exe)) == "GuangYu.app"

    # 非 bundle 结构时退回可执行文件本身
    plain = "/usr/local/bin/GuangYu"
    assert os.path.basename(uc.resolve_install_target("Darwin", plain)) == "GuangYu"


def test_parse_version_ignores_prerelease_suffix():
    assert uc.parse_version("v50.0.6.2") == (50, 0, 6, 2)
    assert uc.parse_version("V50.0.6.2") == (50, 0, 6, 2)
    assert uc.parse_version("50.0.6.2-rc2") == (50, 0, 6, 2)
    assert uc.parse_version("") == ()
    assert uc.parse_version("(API限制)") == ()


def test_is_newer_version_boundaries():
    assert uc.is_newer_version("50.0.6.1", "50.0.6.2") is True
    assert uc.is_newer_version("50.0.6.2", "50.0.6.2") is False
    assert uc.is_newer_version("50.0.6.9", "50.0.6.10") is True
    # 预发布后缀不能被当成额外的版本段（50.0.6.2-rc2 不应大于 50.0.6.2）
    assert uc.is_newer_version("50.0.6.2", "50.0.6.2-rc2") is False
    assert uc.is_newer_version("50.0.6.2", "v50.0.7") is True
    assert uc.is_newer_version("50.0.6.2", "") is False


def test_swap_in_place_replaces_target_and_keeps_backup(tmp_path):
    target = tmp_path / "GuangYu.exe"
    target.write_text("old", encoding="utf-8")
    new_file = tmp_path / "download.exe"
    new_file.write_text("new", encoding="utf-8")

    backup = uc.swap_in_place(str(new_file), str(target))

    assert target.read_text(encoding="utf-8") == "new"
    assert os.path.basename(backup) == "GuangYu.exe.old"
    assert open(backup, encoding="utf-8").read() == "old"
    assert not new_file.exists()


def test_swap_in_place_rolls_back_when_move_fails(tmp_path, monkeypatch):
    target = tmp_path / "GuangYu.exe"
    target.write_text("old", encoding="utf-8")
    new_file = tmp_path / "download.exe"
    new_file.write_text("new", encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(uc.shutil, "move", _boom)

    with pytest.raises(OSError):
        uc.swap_in_place(str(new_file), str(target))

    # 旧文件必须原样可用，不能出现"旧版已删、新版未就位"
    assert target.read_text(encoding="utf-8") == "old"
    assert not os.path.exists(str(target) + uc.BACKUP_SUFFIX)


def test_swap_in_place_replaces_directory_bundle(tmp_path):
    target = tmp_path / "GuangYu.app"
    (target / "Contents" / "MacOS").mkdir(parents=True)
    (target / "Contents" / "Info.plist").write_text("old", encoding="utf-8")

    new_app = tmp_path / "extract" / "GuangYu.app"
    (new_app / "Contents" / "MacOS").mkdir(parents=True)
    (new_app / "Contents" / "Info.plist").write_text("new", encoding="utf-8")

    uc.swap_in_place(str(new_app), str(target))

    assert (target / "Contents" / "Info.plist").read_text(encoding="utf-8") == "new"
    assert (target.parent / "GuangYu.app.old" / "Contents" / "Info.plist").exists()


def test_find_app_bundle_requires_complete_structure(tmp_path):
    incomplete = tmp_path / "Broken.app"
    incomplete.mkdir()
    assert uc.find_app_bundle(str(tmp_path)) is None

    good = tmp_path / "GuangYu.app"
    (good / "Contents" / "MacOS").mkdir(parents=True)
    (good / "Contents" / "Info.plist").write_text("plist", encoding="utf-8")
    (good / "Contents" / "MacOS" / "GuangYu").write_text("bin", encoding="utf-8")

    assert uc.find_app_bundle(str(tmp_path)) == str(good)


def test_find_linux_executable_prefers_install_name(tmp_path):
    (tmp_path / "GuangYu").write_text("bin", encoding="utf-8")
    (tmp_path / "install.sh").write_text("script", encoding="utf-8")

    assert uc.find_linux_executable(str(tmp_path), "GuangYu") == str(tmp_path / "GuangYu")

    # 目录下只有一个可执行文件时才作为兜底采用，避免误选脚本
    # POSIX 下兜底判断依赖真实的可执行位，这里显式赋予
    single = tmp_path / "single"
    single.mkdir()
    fallback_bin = single / "GuangYu"
    fallback_bin.write_text("bin", encoding="utf-8")
    fallback_bin.chmod(0o755)
    assert uc.find_linux_executable(str(single), "NotExist") == str(fallback_bin)


def test_start_download_without_asset_does_not_download():
    """资产匹配失败时不得回退到 Release HTML 页面发起下载。"""
    controller = uc.UpdateController(MagicMock())
    controller._show_no_package_message = MagicMock()

    controller._start_download()

    assert controller._download_thread is None
    controller._show_no_package_message.assert_called_once()


def test_pending_download_without_asset_shows_message():
    controller = uc.UpdateController(MagicMock())
    controller._show_no_package_message = MagicMock()
    controller._pending_download = True

    controller._on_update_found("50.0.6.2", "50.0.6.1", "")

    assert controller._update_available is True
    assert controller._download_thread is None
    controller._show_no_package_message.assert_called_once()
