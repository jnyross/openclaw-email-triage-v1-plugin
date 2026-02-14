from __future__ import annotations

import json
import os
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class BackupError(RuntimeError):
    """Raised when backup or restore operations cannot proceed safely."""


@dataclass(frozen=True)
class BackupResult:
    snapshot_dir: Path
    metadata_path: Path
    archive_path: Path | None


@dataclass(frozen=True)
class RestoreAction:
    source: Path
    destination: Path
    kind: str
    applied: bool


@dataclass(frozen=True)
class RestoreResult:
    snapshot_dir: Path
    actions: list[RestoreAction]



def _utc_now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")



def _resolve_source(path: str | Path) -> Path:
    expanded = Path(path).expanduser()
    return expanded.resolve()



def _source_to_storage_rel(path: Path) -> Path:
    if path.is_absolute():
        return Path(*path.parts[1:])
    return path



def _path_kind(path: Path) -> str:
    if path.is_dir():
        return "dir"
    if path.is_file():
        return "file"
    raise BackupError(f"Unsupported path kind (not file/dir): {path}")



def _copy_to_snapshot(source: Path, destination: Path) -> str:
    kind = _path_kind(source)
    if kind == "file":
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=shutil.copy2)
    return kind



def _load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        parsed = json.load(f)
    if not isinstance(parsed, dict):
        raise BackupError(f"Expected JSON object in {path}")
    return parsed



def _normalize_target_dest(source_path: str, target_root: Path) -> Path:
    source = Path(source_path)
    if source.is_absolute():
        rel = Path(*source.parts[1:])
    else:
        rel = source
    return target_root / rel



def create_snapshot(
    *,
    source_paths: list[str | Path],
    output_dir: str | Path,
    allow_missing: bool = False,
    create_archive: bool = True,
    env_vars: list[str] | None = None,
) -> BackupResult:
    if not source_paths:
        raise BackupError("No source paths provided for backup")

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    snapshot_dir = output / f"openclaw-runtime-backup-{_utc_now_stamp()}"
    files_root = snapshot_dir / "files"
    files_root.mkdir(parents=True, exist_ok=False)

    entries: list[dict[str, Any]] = []
    for raw_path in source_paths:
        source = _resolve_source(raw_path)
        source_str = str(Path(raw_path).expanduser())
        if not source.exists():
            if allow_missing:
                entries.append(
                    {
                        "source_path": source_str,
                        "resolved_path": str(source),
                        "status": "missing",
                    }
                )
                continue
            raise BackupError(f"Source path does not exist: {raw_path}")

        storage_rel = _source_to_storage_rel(source)
        storage_path = files_root / storage_rel
        kind = _copy_to_snapshot(source, storage_path)

        entries.append(
            {
                "source_path": source_str,
                "resolved_path": str(source),
                "status": "backed_up",
                "kind": kind,
                "storage_rel_path": str(storage_rel),
            }
        )

    env_dump: dict[str, str | None] = {}
    for name in env_vars or []:
        env_dump[name] = os.environ.get(name)

    metadata = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "snapshot_dir": str(snapshot_dir),
        "entries": entries,
        "env_vars": env_dump,
    }

    metadata_path = snapshot_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

    archive_path: Path | None = None
    if create_archive:
        archive_path = output / f"{snapshot_dir.name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(snapshot_dir, arcname=snapshot_dir.name)

    return BackupResult(
        snapshot_dir=snapshot_dir,
        metadata_path=metadata_path,
        archive_path=archive_path,
    )



def restore_snapshot(
    *,
    snapshot_dir: str | Path,
    target_root: str | Path = "/",
    apply: bool = False,
    include_source_paths: list[str] | None = None,
) -> RestoreResult:
    snapshot = Path(snapshot_dir).expanduser().resolve()
    metadata_path = snapshot / "metadata.json"
    if not metadata_path.exists():
        raise BackupError(f"Snapshot metadata missing: {metadata_path}")

    metadata = _load_json(metadata_path)
    entries = metadata.get("entries")
    if not isinstance(entries, list):
        raise BackupError("Snapshot metadata is missing entries list")

    include_set = {str(Path(p).expanduser()) for p in (include_source_paths or [])}
    target = Path(target_root).expanduser().resolve()

    actions: list[RestoreAction] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "backed_up":
            continue

        source_path = str(entry.get("source_path", ""))
        if include_set and source_path not in include_set:
            continue

        storage_rel = entry.get("storage_rel_path")
        kind = entry.get("kind")
        if not isinstance(storage_rel, str) or kind not in {"file", "dir"}:
            raise BackupError("Invalid entry in metadata")

        src = snapshot / "files" / storage_rel
        if not src.exists():
            raise BackupError(f"Snapshot data missing for entry: {storage_rel}")

        dest = _normalize_target_dest(source_path, target)

        if apply:
            if kind == "file":
                if dest.exists() and dest.is_dir():
                    raise BackupError(f"Cannot restore file over directory: {dest}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            else:
                if dest.exists() and dest.is_file():
                    raise BackupError(f"Cannot restore directory over file: {dest}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dest, dirs_exist_ok=True, copy_function=shutil.copy2)

        actions.append(RestoreAction(source=src, destination=dest, kind=kind, applied=apply))

    return RestoreResult(snapshot_dir=snapshot, actions=actions)



def write_env_restore_file(
    *,
    snapshot_dir: str | Path,
    output_path: str | Path,
    shell: str = "sh",
) -> Path:
    snapshot = Path(snapshot_dir).expanduser().resolve()
    metadata = _load_json(snapshot / "metadata.json")
    env_vars = metadata.get("env_vars")
    if not isinstance(env_vars, dict):
        raise BackupError("Snapshot metadata has no env_vars object")

    lines: list[str] = []
    if shell in {"sh", "bash", "zsh"}:
        lines.append("#!/usr/bin/env sh")
        for key in sorted(env_vars.keys()):
            value = env_vars[key]
            if value is None:
                continue
            escaped = str(value).replace("'", "'\"'\"'")
            lines.append(f"export {key}='{escaped}'")
    else:
        raise BackupError(f"Unsupported shell format: {shell}")

    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    os.chmod(out, 0o700)
    return out
