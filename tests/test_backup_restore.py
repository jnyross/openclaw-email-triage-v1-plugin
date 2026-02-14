from __future__ import annotations

from pathlib import Path

from openclaw_email_triage_v1_plugin.backup import (
    BackupError,
    create_snapshot,
    restore_snapshot,
    write_env_restore_file,
)


def test_backup_and_restore_round_trip_file(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "openclaw.toml"
    source_file.write_text("enabled=true\n")

    backups = tmp_path / "backups"
    result = create_snapshot(
        source_paths=[source_file],
        output_dir=backups,
        create_archive=False,
    )

    source_file.write_text("enabled=false\n")

    restore_result = restore_snapshot(
        snapshot_dir=result.snapshot_dir,
        target_root=tmp_path,
        apply=True,
        include_source_paths=[str(source_file)],
    )

    restored_path = tmp_path / source_file.relative_to("/")
    assert restored_path.read_text() == "enabled=true\n"
    assert len(restore_result.actions) == 1


def test_backup_fails_on_missing_path_when_not_allowed(tmp_path) -> None:
    missing = tmp_path / "missing.conf"
    try:
        create_snapshot(
            source_paths=[missing],
            output_dir=tmp_path / "out",
            allow_missing=False,
        )
        assert False, "Expected BackupError"
    except BackupError:
        pass


def test_backup_records_missing_path_when_allowed(tmp_path) -> None:
    missing = tmp_path / "missing.conf"
    result = create_snapshot(
        source_paths=[missing],
        output_dir=tmp_path / "out",
        allow_missing=True,
        create_archive=False,
    )
    metadata = (result.snapshot_dir / "metadata.json").read_text()
    assert '"status": "missing"' in metadata


def test_restore_dry_run_does_not_modify_target(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "plugins.toml"
    source_file.write_text("v=1\n")

    result = create_snapshot(
        source_paths=[source_file],
        output_dir=tmp_path / "backups",
        create_archive=False,
    )

    source_file.write_text("v=2\n")

    dry = restore_snapshot(
        snapshot_dir=result.snapshot_dir,
        target_root=tmp_path,
        apply=False,
        include_source_paths=[str(source_file)],
    )

    restored_path = tmp_path / source_file.relative_to("/")
    assert not restored_path.exists()
    assert len(dry.actions) == 1
    assert dry.actions[0].applied is False


def test_write_env_restore_file(tmp_path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    conf = src / "runtime.env"
    conf.write_text("x=1\n")

    monkeypatch.setenv("EMAIL_TRIAGE_ENGINE", "v1")
    monkeypatch.setenv("EMAIL_TRIAGE_FAIL_OPEN", "true")

    backup = create_snapshot(
        source_paths=[conf],
        output_dir=tmp_path / "backups",
        create_archive=False,
        env_vars=["EMAIL_TRIAGE_ENGINE", "EMAIL_TRIAGE_FAIL_OPEN", "MISSING_VAR"],
    )

    env_file = write_env_restore_file(
        snapshot_dir=backup.snapshot_dir,
        output_path=tmp_path / "restore-env.sh",
    )

    text = env_file.read_text()
    assert "export EMAIL_TRIAGE_ENGINE='v1'" in text
    assert "export EMAIL_TRIAGE_FAIL_OPEN='true'" in text
    assert "MISSING_VAR" not in text
