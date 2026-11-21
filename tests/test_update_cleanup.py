"""覆盖安装遗留的 <exe>.old 备份在下次启动时的清理。"""
import os
import sys

from controllers import update_controller as uc


def _frozen(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)


def test_removes_stale_exe_backup(tmp_path, monkeypatch):
    _frozen(monkeypatch)
    target = tmp_path / 'GuangYu.exe'
    target.write_text('new', encoding='utf-8')
    backup = tmp_path / 'GuangYu.exe.old'
    backup.write_text('old', encoding='utf-8')

    assert uc.cleanup_stale_backup(str(target)) is True
    assert not backup.exists()
    assert target.exists()


def test_removes_stale_app_bundle_backup(tmp_path, monkeypatch):
    _frozen(monkeypatch)
    target = tmp_path / 'GuangYu.app'
    target.mkdir()
    backup = tmp_path / 'GuangYu.app.old'
    backup.mkdir()
    (backup / 'Contents').mkdir()

    assert uc.cleanup_stale_backup(str(target)) is True
    assert not backup.exists()
    assert target.exists()


def test_no_backup_is_noop(tmp_path, monkeypatch):
    _frozen(monkeypatch)
    target = tmp_path / 'GuangYu.exe'
    target.write_text('new', encoding='utf-8')

    assert uc.cleanup_stale_backup(str(target)) is False
    assert target.exists()


def test_locked_backup_is_kept_for_next_start(tmp_path, monkeypatch):
    _frozen(monkeypatch)
    target = tmp_path / 'GuangYu.exe'
    target.write_text('new', encoding='utf-8')
    backup = tmp_path / 'GuangYu.exe.old'
    backup.write_text('old', encoding='utf-8')

    def _locked(_path):
        raise PermissionError('file is in use')

    monkeypatch.setattr(uc.os, 'remove', _locked)

    assert uc.cleanup_stale_backup(str(target)) is False
    assert backup.exists()
    assert target.exists()


def test_not_frozen_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    target = tmp_path / 'GuangYu.exe'
    target.write_text('new', encoding='utf-8')
    backup = tmp_path / 'GuangYu.exe.old'
    backup.write_text('old', encoding='utf-8')

    assert uc.cleanup_stale_backup(str(target)) is False
    assert backup.exists()
    assert os.path.exists(target)
