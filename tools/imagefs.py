# SPDX-License-Identifier: GPL-3.0-only
"""Bounded reader for uncompressed QNX ImageFS payloads."""

from __future__ import annotations

import json
import struct
from pathlib import Path, PurePosixPath
from typing import Any

from filesystem_readers import safe_segment, sha256_file


ATTR_SIZE = 24
S_IFMT = 0o170000
S_IFREG = 0o100000
S_IFDIR = 0o040000
S_IFLNK = 0o120000
MAX_ENTRIES = 2_000_000
MAX_PATH_BYTES = 64 * 1024


def _read_exact(stream: Any, length: int, what: str) -> bytes:
    data = stream.read(length)
    if len(data) != length:
        raise ValueError(f"truncated ImageFS while reading {what}")
    return data


def _cstring(data: bytes, start: int, end: int, what: str) -> tuple[bytes, int]:
    stop = data.find(b"\0", start, end)
    if stop < 0:
        raise ValueError(f"unterminated ImageFS {what}")
    if stop - start > MAX_PATH_BYTES:
        raise ValueError(f"ImageFS {what} exceeds path limit")
    return data[start:stop], stop + 1


def _safe_relative(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("ImageFS path is not UTF-8") from exc
    if value == "":
        return "."
    if value.startswith(("/", "\\")) or "\\" in value:
        raise ValueError(f"unsafe ImageFS path {value!r}")
    path = PurePosixPath(value)
    if value == ".":
        return "."
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"unsafe ImageFS path {value!r}")
    for part in path.parts:
        safe_segment(part)
    return path.as_posix()


def inventory_imagefs(image: Path) -> dict[str, Any]:
    size = image.stat().st_size
    with image.open("rb") as stream:
        header = _read_exact(stream, 88, "header")
        if header[:7] != b"imagefs":
            raise ValueError("ImageFS signature missing at offset zero")
        flags = header[7]
        endian = ">" if flags & 0x01 else "<"
        image_size, hdr_dir_size, dir_offset = struct.unpack_from(endian + "III", header, 8)
        if image_size < 92 or image_size > size or image_size > 0xFFFFFFFF:
            raise ValueError(f"invalid ImageFS declared size {image_size} (source {size})")
        if not 88 <= dir_offset <= hdr_dir_size <= image_size - 4:
            raise ValueError("invalid ImageFS directory bounds")

        stream.seek(dir_offset)
        entries: list[dict[str, Any]] = []
        seen_exact: set[str] = set()
        collisions: list[dict[str, Any]] = []
        position = dir_offset
        while position < hdr_dir_size:
            if len(entries) >= MAX_ENTRIES:
                raise ValueError("ImageFS entry count exceeds limit")
            stream.seek(position)
            attr_head = _read_exact(stream, 4, "directory entry header")
            entry_size, extattr_offset = struct.unpack(endian + "HH", attr_head)
            if entry_size == 0:
                stream.seek(position)
                if any(_read_exact(stream, hdr_dir_size - position, "directory padding")):
                    raise ValueError(f"zero-sized ImageFS dirent before nonzero bytes at {position:#x}")
                position = hdr_dir_size
                break
            if entry_size < ATTR_SIZE or position + entry_size > hdr_dir_size or entry_size & 3:
                raise ValueError(f"invalid ImageFS dirent size {entry_size} at {position:#x}")
            body = _read_exact(stream, entry_size - 4, "directory entry")
            entry = attr_head + body
            ino, mode, gid, uid, mtime = struct.unpack_from(endian + "IIIII", entry, 4)
            kind = mode & S_IFMT
            item: dict[str, Any] = {
                "offset": position,
                "dirent_bytes": entry_size,
                "extattr_offset": extattr_offset,
                "inode": ino,
                "mode": mode,
                "uid": uid,
                "gid": gid,
                "mtime": mtime,
            }
            payload = entry[ATTR_SIZE:]
            if kind == S_IFREG:
                if len(payload) < 8:
                    raise ValueError("short ImageFS regular-file entry")
                data_offset, data_size = struct.unpack_from(endian + "II", payload)
                raw_path, _ = _cstring(payload, 8, len(payload), "file path")
                if data_offset > image_size - 4 or data_size > image_size - 4 - data_offset:
                    raise ValueError(f"ImageFS file span outside image at {position:#x}")
                item.update(type="file", path=_safe_relative(raw_path), data_offset=data_offset,
                            bytes=data_size)
            elif kind == S_IFDIR:
                raw_path, _ = _cstring(payload, 0, len(payload), "directory path")
                item.update(type="directory", path=_safe_relative(raw_path))
            elif kind == S_IFLNK:
                if len(payload) < 4:
                    raise ValueError("short ImageFS symlink entry")
                sym_offset, sym_size = struct.unpack_from(endian + "HH", payload)
                if sym_offset < 2 or 4 + sym_offset + sym_size > len(payload):
                    raise ValueError("ImageFS symlink target outside entry")
                raw_path = payload[4:4 + sym_offset]
                if not raw_path.endswith(b"\0"):
                    raise ValueError("ImageFS symlink path is not NUL-terminated at target offset")
                raw_path = raw_path[:-1]
                target = payload[4 + sym_offset:4 + sym_offset + sym_size]
                item.update(type="symlink", path=_safe_relative(raw_path),
                            target=target.decode("utf-8", errors="backslashreplace"),
                            target_bytes=target.hex())
            else:
                raw_path, _ = _cstring(payload, 8 if len(payload) >= 8 else 0,
                                       len(payload), "special-node path")
                item.update(type="special", special_type=kind,
                            path=_safe_relative(raw_path))

            path = item["path"]
            if path in seen_exact:
                collisions.append({"path": path, "entry_offset": position,
                                   "reason": "duplicate path; retain all records, do not overwrite"})
            else:
                seen_exact.add(path)
            entries.append(item)
            position += entry_size

        if position != hdr_dir_size:
            raise ValueError("ImageFS directory table did not end at declared boundary")
        return {"source_bytes": size, "source_sha256": sha256_file(image),
                "image_size": image_size, "flags": flags,
                "byte_order": "big" if endian == ">" else "little",
                "directory_offset": dir_offset, "directory_end": hdr_dir_size,
                "trailer_offset": image_size - 4, "entries": entries,
                "duplicate_paths": collisions}


def materialize_imagefs(image: Path, output_tree: Path, metadata_path: Path, *, display_root: Path | None = None) -> dict[str, Any]:
    """Create a new tree; represent links and special nodes only in metadata."""
    inventory = inventory_imagefs(image)
    if output_tree.exists() or metadata_path.exists():
        raise FileExistsError("ImageFS output or metadata already exists; choose fresh additive paths")
    output_tree.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    written: set[str] = set()
    duplicates = {item["path"] for item in inventory["duplicate_paths"]}
    with image.open("rb") as source:
        for entry in inventory["entries"]:
            record = {key: value for key, value in entry.items() if key not in ("offset", "dirent_bytes", "extattr_offset")}
            rel = entry["path"]
            if rel == ".":
                records.append(record)
                continue
            destination = output_tree.joinpath(*PurePosixPath(rel).parts)
            if entry["type"] == "directory":
                destination.mkdir(parents=True, exist_ok=True)
            elif entry["type"] == "file":
                if rel in duplicates or rel in written:
                    record["materialized"] = False
                    record["materialize_note"] = "duplicate path retained only in metadata"
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as output:
                        source.seek(entry["data_offset"])
                        remaining = entry["bytes"]
                        while remaining:
                            chunk = _read_exact(source, min(1024 * 1024, remaining), rel)
                            output.write(chunk)
                            remaining -= len(chunk)
                    record.update(materialized=True, sha256=sha256_file(destination))
                    written.add(rel)
            else:
                record["materialized"] = False
                record["materialize_note"] = "metadata only; no host link/device node created"
            records.append(record)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump({**{key: value for key, value in inventory.items() if key != "entries"},
                   "entries": records,
                   "materialized_files": len(written),
                   "materialized_bytes": sum(p.stat().st_size for p in output_tree.rglob("*") if p.is_file())},
                  stream, indent=2)
    tree_display = (output_tree.relative_to(display_root).as_posix() if display_root else output_tree.name)
    metadata_display = (metadata_path.relative_to(display_root).as_posix() if display_root else metadata_path.name)
    return {"tree": tree_display, "metadata": metadata_display,
            "entry_count": len(records), "file_count": len(written),
            "symlink_count": sum(1 for item in records if item["type"] == "symlink"),
            "special_count": sum(1 for item in records if item["type"] == "special"),
            "bytes": sum(p.stat().st_size for p in output_tree.rglob("*") if p.is_file())}
