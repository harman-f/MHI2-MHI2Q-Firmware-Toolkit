# SPDX-License-Identifier: GPL-3.0-only
"""Filesystem readers/materializers used by the portable extraction CLI."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


WINDOWS_INVALID = set('<>:"/\\|?*')
WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_segment(name: str) -> None:
    if not name or name in (".", "..") or name.endswith((" ", ".")):
        raise ValueError(f"unsafe filesystem path segment: {name!r}")
    if any(char in WINDOWS_INVALID or ord(char) < 32 for char in name):
        raise ValueError(f"Windows-incompatible filesystem path segment: {name!r}")
    if WINDOWS_RESERVED.fullmatch(name):
        raise ValueError(f"Windows reserved filesystem path segment: {name!r}")


def safe_member_path(root: Path, member: str) -> Path:
    relative = PurePosixPath(member)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError(f"unsafe archive member path: {member!r}")
    for part in relative.parts:
        safe_segment(part)
    target = root.joinpath(*relative.parts)
    if os.path.commonpath((str(root.resolve()), str(target.resolve()))) != str(root.resolve()):
        raise ValueError(f"archive member escapes output root: {member!r}")
    return target


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "special"


def inventory_qnx6(filesystem: Any, *, entry_limit: int = 100_000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack = [("", 1, frozenset())]
    while stack:
        parent, inode_number, ancestors = stack.pop()
        if inode_number in ancestors:
            raise ValueError(f"QNX6 directory cycle at {parent!r}")
        for entry in filesystem.get_dir(inode_number).entries:
            name = entry.content.name
            if name in (".", ".."):
                continue
            safe_segment(name)
            relative = f"{parent}/{name}" if parent else name
            folded = relative.casefold()
            if folded in seen:
                raise ValueError(f"duplicate or case-colliding QNX6 path: {relative!r}")
            seen.add(folded)
            inode_id = int(entry.inode_number)
            inode = filesystem.get_inode(inode_id)
            kind = _kind(int(inode.mode))
            record = {"path": relative, "inode": inode_id, "type": kind,
                      "size": int(inode.size), "mode_octal": oct(int(inode.mode)),
                      "uid": int(inode.uid), "gid": int(inode.gid),
                      "ftime": int(inode.ftime), "mtime": int(inode.mtime),
                      "atime": int(inode.atime), "ctime": int(inode.ctime)}
            records.append(record)
            if kind == "directory":
                stack.append((relative, inode_id, ancestors | {inode_number}))
            if len(records) > entry_limit:
                raise ValueError(f"QNX6 entry limit exceeded ({entry_limit})")
    return sorted(records, key=lambda item: item["path"].casefold())


def _write_qnx6_file(filesystem: Any, inode: Any, target: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    written = 0
    buffer = bytearray()
    with target.open("xb") as destination:
        for offset in range(0, int(inode.size), filesystem.blocksize):
            needed = min(filesystem.blocksize, int(inode.size) - offset)
            block = filesystem.parse_block_pointer(inode, offset).raw_body[:needed]
            if len(block) != needed:
                raise IOError(f"short QNX6 read at offset {offset}: {target}")
            buffer.extend(block)
            digest.update(block)
            written += len(block)
            if len(buffer) >= 1024 * 1024:
                destination.write(buffer)
                buffer.clear()
        if buffer:
            destination.write(buffer)
    if written != int(inode.size) or target.stat().st_size != int(inode.size):
        raise IOError(f"QNX6 size mismatch for {target}")
    return written, digest.hexdigest()


def materialize_qnx6(image: Path, variant: str, output: Path, stream_type: Any,
                     filesystem_type: Any, source_sha256: str) -> dict[str, Any]:
    tree = output / "filesystems" / "MMX2" / "app" / variant / "default" / "app.img"
    tree.mkdir(parents=True, exist_ok=False)
    with stream_type(image) as stream:
        filesystem = filesystem_type(stream)
        records = inventory_qnx6(filesystem)
        counts: Counter[str] = Counter()
        total_bytes = 0
        for record in records:
            target = tree.joinpath(*record["path"].split("/"))
            inode = filesystem.get_inode(record["inode"])
            if record["type"] == "directory":
                target.mkdir(parents=True, exist_ok=False)
            elif record["type"] == "file":
                target.parent.mkdir(parents=True, exist_ok=True)
                size, digest = _write_qnx6_file(filesystem, inode, target)
                record.update({"bytes_written": size, "sha256": digest})
                total_bytes += size
            elif record["type"] == "symlink":
                record.update({"target": filesystem.read_file(inode).decode("utf-8", errors="surrogateescape").rstrip("\x00"),
                               "materialization": "metadata only; no host symlink created"})
            else:
                record["materialization"] = "metadata only; no host device/FIFO created"
            counts[record["type"]] += 1
        superblocks = (filesystem.parser.qnx6_bootblock.superblock0,
                       filesystem.parser.qnx6_bootblock.superblock1)
    relative_image = image.relative_to(output / "raw")
    metadata = {"source_image": relative_image.as_posix(), "source_bytes": image.stat().st_size,
                "source_sha256": source_sha256, "filesystem": "QNX6",
                "blocksize": filesystem.blocksize,
                "superblocks": [{"serial": sb.serial, "crc": sb.crc, "blocksize": sb.blocksize}
                                for sb in superblocks],
                "active_superblock_serial": filesystem.active_superblock.serial,
                "entries": records, "counts": dict(counts),
                "regular_file_bytes": total_bytes,
                "symlink_policy": "targets preserved in metadata; no host links created"}
    metadata_path = output / "metadata" / f"mmx2-app-{variant}.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2, ensure_ascii=True)
    return {"variant": variant,
            "tree": str(tree.relative_to(output)).replace("\\", "/"),
            "metadata": str(metadata_path.relative_to(output)).replace("\\", "/"),
            "source_sha256": source_sha256, "counts": dict(counts),
            "regular_file_bytes": total_bytes,
            "active_superblock_serial": filesystem.active_superblock.serial,
            "safe_entry_count": len(records)}


def extract_rcc_root(image_path: Path, output: Path, dumpifs_dir: Path | None) -> dict[str, Any]:
    if dumpifs_dir is not None:
        import sys
        sys.path.insert(0, str(dumpifs_dir))
    import dumpifs

    image = dumpifs.qifs(str(image_path), quiet=True)
    relative_image = image_path.relative_to(output / "raw")
    tree = output / "filesystems" / relative_image
    tree.mkdir(parents=True, exist_ok=False)
    entries = image.ifs["image"]["entries"]
    counts: Counter[str] = Counter()
    bytes_written = 0
    links: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    materialized: set[str] = set()
    for entry in entries:
        name = str(entry.get("name", ""))
        kind = entry.get("type")
        if not name and kind == dumpifs.qifs.DIRENT_TYPE_DIR:
            counts["root_directory_entry"] += 1
            continue
        relative = PurePosixPath(name)
        if not name or relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise ValueError(f"unsafe RCC IFS path: {name!r}")
        for part in relative.parts:
            safe_segment(part)
        target = tree.joinpath(*relative.parts)
        if kind == dumpifs.qifs.DIRENT_TYPE_DIR:
            target.mkdir(parents=True, exist_ok=True)
            counts["directory"] += 1
        elif kind == dumpifs.qifs.DIRENT_TYPE_FILE:
            if target.exists():
                if name not in materialized:
                    raise ValueError(f"RCC IFS file collides with a non-file: {name!r}")
                duplicates.append({"path": name, "inode": entry.get("ino"),
                                   "size": entry.get("size"),
                                   "policy": "first file retained; original entries remain in metadata"})
                continue
            data = image.get_file(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            bytes_written += len(data)
            counts["file_entry"] += 1
            counts["materialized_file"] += 1
            materialized.add(name)
        elif kind == dumpifs.qifs.DIRENT_TYPE_SYMLINK:
            links.append({"path": name, "target": str(entry.get("dst", "")),
                          "mode": entry.get("mode"), "uid": entry.get("uid"),
                          "gid": entry.get("gid"), "inode": entry.get("ino"),
                          "representation": "metadata only; no host symlink created"})
            counts["symlink"] += 1
        else:
            counts["other"] += 1
    metadata = {"source_image": str(relative_image).replace("\\", "/"),
                "source_sha256": sha256_file(image_path), "source_bytes": image_path.stat().st_size,
                "filesystem_mountpoint": image.ifs["image"].get("mountpoint"),
                "startup_header": image.ifs.get("startup_header", {}),
                "image_header": {key: value for key, value in image.ifs["image"].items()
                                 if key not in ("entries", "name_index")},
                "entries": entries, "counts": dict(counts), "regular_file_bytes": bytes_written,
                "symlinks": links, "duplicate_files": duplicates}
    metadata_path = tree / "_image_metadata.json"
    if metadata_path.exists():
        raise ValueError("RCC IFS contains a path reserved for extraction metadata")
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2)
    return {"tree": str(tree.relative_to(output)).replace("\\", "/"),
            "metadata": str(metadata_path.relative_to(output)).replace("\\", "/"),
            "counts": dict(counts), "regular_file_bytes": bytes_written,
            "duplicate_file_paths": len(duplicates)}
