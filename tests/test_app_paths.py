"""路径解析与数据迁移测试（Windows / macOS / Linux 三端用户目录）。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import app_paths


@pytest.fixture(autouse=True)
def _reset_path_state():
    app_paths.reset_for_tests()
    yield
    app_paths.reset_for_tests()


def _clear_platform_env(monkeypatch):
    for key in ('ANDROID_ARGUMENT', 'IPTV_DATA_DIR', 'IPTV_CONFIG_DIR'):
        monkeypatch.delenv(key, raising=False)


def test_windows_uses_appdata_and_localappdata(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    _clear_platform_env(monkeypatch)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'Roaming'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))

    assert app_paths.get_config_dir() == str(tmp_path / 'Roaming' / 'GuangYu')
    assert app_paths.get_cache_dir() == str(tmp_path / 'Local' / 'GuangYu')
    assert app_paths.get_log_dir() == app_paths.get_config_dir()


def test_macos_uses_application_support_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(tmp_path) if p == '~' else p)

    assert app_paths.get_config_dir() == str(
        tmp_path / 'Library' / 'Application Support' / 'GuangYu')
    assert app_paths.get_cache_dir() == str(tmp_path / 'Library' / 'Caches' / 'GuangYu')


def test_linux_uses_xdg_config_and_cache_home(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    _clear_platform_env(monkeypatch)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg-config'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'xdg-cache'))

    assert app_paths.get_config_dir() == str(tmp_path / 'xdg-config' / 'GuangYu')
    assert app_paths.get_cache_dir() == str(tmp_path / 'xdg-cache' / 'GuangYu')


def test_migrate_legacy_files_and_dirs(tmp_path):
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    new_config = tmp_path / 'user-config'
    new_cache = tmp_path / 'user-cache'

    (legacy / 'config.ini').write_text('[Player]\nvolume = 35\n', encoding='utf-8')
    (legacy / 'resume_positions.json').write_text('{"u": {"position": 30}}', encoding='utf-8')
    (legacy / 'bookmarks.json').write_text('{"u": []}', encoding='utf-8')
    (legacy / 'logo_cache').mkdir()
    (legacy / 'logo_cache' / 'cctv1.png').write_bytes(b'logo')
    (legacy / 'screenshots').mkdir()
    (legacy / 'screenshots' / 'shot.png').write_bytes(b'shot')

    migrated = app_paths.migrate_legacy_data(
        config_dir=str(new_config), cache_dir=str(new_cache), legacy_dir=str(legacy))

    assert (new_config / 'config.ini').read_text(encoding='utf-8') == '[Player]\nvolume = 35\n'
    assert (new_config / 'resume_positions.json').exists()
    assert (new_config / 'bookmarks.json').exists()
    assert (new_cache / 'logo_cache' / 'cctv1.png').read_bytes() == b'logo'
    assert (new_cache / 'screenshots' / 'shot.png').read_bytes() == b'shot'
    assert len(migrated) == 5
    # 迁移必须留下可读记录
    migration_log = new_config / 'migration.log'
    assert migration_log.exists()
    assert '迁移' in migration_log.read_text(encoding='utf-8')
    # 回退策略：复制而非移动，迁移失败也不会丢旧数据
    assert (legacy / 'config.ini').exists()


def test_migrate_does_not_overwrite_existing_user_config(tmp_path):
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    new_config = tmp_path / 'user-config'
    new_config.mkdir()
    (legacy / 'config.ini').write_text('[Player]\nvolume = 10\n', encoding='utf-8')
    (legacy / 'bookmarks.json').write_text('{"old": []}', encoding='utf-8')
    (new_config / 'config.ini').write_text('[Player]\nvolume = 80\n', encoding='utf-8')

    migrated = app_paths.migrate_legacy_data(
        config_dir=str(new_config), cache_dir=str(tmp_path / 'user-cache'),
        legacy_dir=str(legacy))

    assert migrated == []
    assert 'volume = 80' in (new_config / 'config.ini').read_text(encoding='utf-8')
    assert not (new_config / 'bookmarks.json').exists()


def test_unwritable_user_dir_falls_back_to_legacy_dir(tmp_path, monkeypatch):
    blocker = tmp_path / 'blocked'
    blocker.write_text('not a directory', encoding='utf-8')
    legacy = tmp_path / 'legacy'

    monkeypatch.setattr(app_paths, '_preferred_config_dir',
                        lambda: str(blocker / 'GuangYu'))
    monkeypatch.setattr(app_paths, 'get_legacy_base_dir', lambda: str(legacy))

    resolved = app_paths.get_config_dir()

    assert resolved == str(legacy)
    messages = app_paths.get_degraded_messages()
    assert any('不可写' in m for m in messages)
    # 降级必须留下用户可读记录
    record = legacy / 'path_fallback.log'
    assert record.exists()
    assert '不可写' in record.read_text(encoding='utf-8')
