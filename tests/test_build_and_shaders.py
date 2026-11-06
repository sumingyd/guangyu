"""构建脚本与着色器路径解析的回归测试（纯逻辑，不需要 Qt / 真实打包）。"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build  # noqa: E402
import services.mpv_shader as mpv_shader  # noqa: E402


def _add_data_pairs(args):
    pairs = []
    for i, arg in enumerate(args):
        if arg == "--add-data":
            src, dest = args[i + 1].rsplit(build.DATA_SEP, 1)
            pairs.append((Path(src).name, dest))
    return pairs


def test_shaders_are_part_of_bundled_data_dirs():
    # 发布包曾漏打包 shaders/，导致所有 GLSL 预设静默失效
    assert "shaders" in build.DATA_DIRS


def test_data_args_cover_runtime_dirs(monkeypatch, tmp_path):
    for name in ("resources", "i18n", "shaders"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(build, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(build, "DATA_DIRS", ["resources", "i18n", "shaders"])

    pairs = _add_data_pairs(build._data_args())
    assert ("resources", "resources") in pairs
    assert ("i18n", "i18n") in pairs
    assert ("shaders", "shaders") in pairs


def test_every_platform_builder_bundles_shaders(monkeypatch, tmp_path):
    for name in ("resources", "i18n", "shaders"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(build, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(build, "DATA_DIRS", ["resources", "i18n", "shaders"])
    monkeypatch.setattr(build, "prepare_macos_dependencies", lambda: None)
    monkeypatch.setattr(build, "prepare_windows_dependencies", lambda: None)
    monkeypatch.setattr(build, "prepare_linux_dependencies", lambda: None)
    monkeypatch.setattr(build, "_macos_icns_path", lambda: None)

    for builder in (build.build_macos, build.build_windows, build.build_linux):
        args = builder()
        assert ("shaders", "shaders") in _add_data_pairs(args), builder.__name__


def test_frozen_shader_dirs_include_meipass_and_exe_dir(monkeypatch, tmp_path):
    exe_dir = tmp_path / "app"
    bundle_dir = tmp_path / "bundle"
    exe_dir.mkdir()
    bundle_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "GuangYu.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)

    dirs = mpv_shader._candidate_shader_dirs()
    assert dirs == [
        str(exe_dir / "shaders"),
        str(bundle_dir / "shaders"),
    ]


def test_shader_lookup_falls_back_to_bundled_dir(monkeypatch, tmp_path):
    user_dir = tmp_path / "user"
    bundle_dir = tmp_path / "bundle"
    user_dir.mkdir()
    bundle_dir.mkdir()
    shader_file = bundle_dir / "custom_shader.glsl"
    shader_file.write_text("// shader")
    monkeypatch.setattr(
        mpv_shader, "_candidate_shader_dirs", lambda: [str(user_dir), str(bundle_dir)]
    )

    facade = SimpleNamespace(_SHADER_PRESET_FILES={})
    shader = mpv_shader.MpvShader(facade)
    assert shader._find_shader_files("custom_shader") == [str(shader_file)]
    assert shader._get_shaders_dir() == str(user_dir)


def test_shader_lookup_prefers_user_override(monkeypatch, tmp_path):
    user_dir = tmp_path / "user"
    bundle_dir = tmp_path / "bundle"
    user_dir.mkdir()
    bundle_dir.mkdir()
    (bundle_dir / "ravu_lite_r4.glsl").write_text("// bundled")
    user_shader = user_dir / "ravu_lite_r4.glsl"
    user_shader.write_text("// user")
    monkeypatch.setattr(
        mpv_shader, "_candidate_shader_dirs", lambda: [str(user_dir), str(bundle_dir)]
    )

    shader = mpv_shader.MpvShader(SimpleNamespace(_SHADER_PRESET_FILES={}))
    assert shader._find_shader_files("ravu_lite_r4") == [str(user_shader)]


def test_list_available_shaders_merges_dirs(monkeypatch, tmp_path):
    user_dir = tmp_path / "user"
    bundle_dir = tmp_path / "bundle"
    user_dir.mkdir()
    bundle_dir.mkdir()
    (user_dir / "a.glsl").write_text("// a")
    (bundle_dir / "a.glsl").write_text("// a bundled")
    (bundle_dir / "b.hook").write_text("// b")
    monkeypatch.setattr(
        mpv_shader, "_candidate_shader_dirs", lambda: [str(user_dir), str(bundle_dir)]
    )

    shader = mpv_shader.MpvShader(MagicMock())
    names = {item["filename"] for item in shader.list_available_shaders()}
    assert names == {"a.glsl", "b.hook"}
