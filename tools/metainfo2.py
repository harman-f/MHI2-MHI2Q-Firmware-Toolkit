#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Audit and refresh supported MHI2 metainfo2.txt integrity fields.

This parser is intentionally conservative: it preserves ordering/repeated
sections, never executes unknown lines, and only rewrites values it can
resolve against a supplied package root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
from typing import Any

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
KEY_RE = re.compile(r'^(\s*)([A-Za-z0-9_]+)(\s*=\s*)"([^"]*)"(\s*(?:[#;].*)?)(\r?\n)?$')
META_RE = re.compile(r"^\s*MetafileChecksum\s*=", re.I)
SIGNATURE_KEY_RE = re.compile(r"^signature\d*$", re.I)
CHECKSUM_KEY_RE = re.compile(r"^checksum(\d*)$", re.I)
ROLE_NAMES = {"file", "application", "bootloader", "dir"}
DEFAULT_CHECKSUM_SIZE = 524288


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def chunk_sha1_file(path: Path, checksum_size: int = DEFAULT_CHECKSUM_SIZE) -> tuple[int, list[str]]:
    if checksum_size < 0:
        raise ValueError("CheckSumSize must be >= 0")
    size = 0
    digests: list[str] = []
    with path.open("rb") as stream:
        if checksum_size == 0:
            data = stream.read()
            return len(data), [sha1_bytes(data)]
        while True:
            chunk = stream.read(checksum_size)
            if not chunk:
                break
            size += len(chunk)
            digests.append(sha1_bytes(chunk))
    # Historical update-hashes.py emits no digest for an empty file in
    # chunked mode. Keep that behavior explicit.
    return size, digests


def read_preserved(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def write_preserved(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def dominant_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def metafile_checksum(text: str) -> str:
    kept = [line for line in text.splitlines(keepends=True) if not META_RE.match(line)]
    return hashlib.sha1("".join(kept).encode("utf-8")).hexdigest()


def parse(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []
    section: str | None = None
    for index, line in enumerate(text.splitlines(keepends=True)):
        bare = line.rstrip("\r\n")
        sm = SECTION_RE.match(bare)
        if sm:
            section = sm.group(1)
            rows.append({"line": index, "kind": "section", "section": section, "raw": line})
            continue
        km = KEY_RE.match(line)
        if km:
            rows.append({"line": index, "kind": "key", "section": section,
                         "key": km.group(2), "value": km.group(4), "raw": line})
            continue
        stripped = bare.strip()
        if stripped and not stripped.startswith(("#", ";")):
            suspicious.append({"line": index + 1, "section": section, "text": bare})
        rows.append({"line": index, "kind": "other", "section": section, "raw": line})
    return rows, suspicious


def section_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        if row["kind"] == "section":
            current = {"name": row["section"], "section_line": row["line"], "keys": {}}
            instances.append(current)
        elif row["kind"] == "key" and current is not None:
            current["keys"].setdefault(row["key"].casefold(), []).append(row)
    return instances


def signature_boundary(rows: list[dict[str, Any]]) -> int | None:
    lines = [row["line"] for row in rows
             if row["kind"] == "key" and SIGNATURE_KEY_RE.match(row["key"])]
    return max(lines) + 1 if lines else None


def resolve_mode(text: str, mode: str) -> tuple[str, int]:
    rows, _ = parse(text)
    boundary = signature_boundary(rows)
    if mode == "auto":
        mode = "signed-tail" if boundary is not None else "full"
    if mode == "signed-tail":
        return mode, boundary or 0
    if mode == "full":
        return mode, 0
    raise ValueError(f"unsupported mode: {mode}")


def base_for_section(section: str) -> PurePosixPath:
    parts = [part for part in section.replace("/", "\\").split("\\") if part]
    if parts and parts[-1].casefold() in ROLE_NAMES:
        parts = parts[:-1]
    return PurePosixPath(*parts)


def section_role(section: str) -> str:
    parts = [part for part in section.replace("/", "\\").split("\\") if part]
    return parts[-1].casefold() if parts else ""


def safe_package_path(root: Path, section: str, source: str) -> Path:
    base = base_for_section(section).as_posix()
    candidate = source.replace("\\", "/")
    if candidate.startswith("/"):
        raise ValueError("absolute source path")
    normalized = posixpath.normpath(posixpath.join(base, candidate))
    rel = PurePosixPath(normalized)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ValueError("source escapes package root")
    target = root.joinpath(*rel.parts)
    root_resolved = root.resolve()
    target_resolved = target.resolve(strict=False)
    if not target_resolved.is_relative_to(root_resolved):
        raise ValueError("source escapes package root")
    return target


def safe_section_directory(root: Path, section: str) -> Path:
    rel = base_for_section(section)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ValueError("directory section escapes package root")
    target = root.joinpath(*rel.parts)
    root_resolved = root.resolve()
    target_resolved = target.resolve(strict=False)
    if not target_resolved.is_relative_to(root_resolved):
        raise ValueError("directory section escapes package root")
    return target


def first_key(instance: dict[str, Any], name: str) -> dict[str, Any] | None:
    values = instance["keys"].get(name.casefold(), [])
    return values[0] if values else None


def checksum_rows(instance: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    found: list[tuple[int, dict[str, Any]]] = []
    for rows in instance["keys"].values():
        for row in rows:
            match = CHECKSUM_KEY_RE.match(row["key"])
            if match:
                found.append((int(match.group(1) or "0"), row))
    return sorted(found, key=lambda item: item[0])


def checksum_size(instance: dict[str, Any], default: int = DEFAULT_CHECKSUM_SIZE) -> int:
    row = first_key(instance, "CheckSumSize")
    if row is None or not row["value"]:
        return default
    try:
        value = int(row["value"], 10)
    except ValueError as exc:
        raise ValueError(f'invalid CheckSumSize {row["value"]!r}') from exc
    if value < 0:
        raise ValueError("CheckSumSize must be >= 0")
    return value


class LineEditor:
    def __init__(self, text: str):
        self.lines = text.splitlines(keepends=True)
        self.replacements: dict[int, str] = {}
        self.removals: set[int] = set()
        self.after: dict[int, list[str]] = {}

    def replace_value(self, row: dict[str, Any], value: str) -> None:
        old = self.lines[row["line"]]
        match = KEY_RE.match(old)
        if not match:
            raise ValueError("internal parser mismatch")
        ending = match.group(6) or ""
        self.replacements[row["line"]] = (
            f'{match.group(1)}{match.group(2)}{match.group(3)}"{value}"{match.group(5)}{ending}'
        )

    def remove(self, row: dict[str, Any]) -> None:
        self.removals.add(row["line"])

    def insert_after(self, line: int, new_lines: list[str]) -> None:
        self.after.setdefault(line, []).extend(new_lines)

    def render(self) -> str:
        output: list[str] = []
        for index, line in enumerate(self.lines):
            if index not in self.removals:
                output.append(self.replacements.get(index, line))
            output.extend(self.after.get(index, []))
        return "".join(output)


def _line_style(instance: dict[str, Any], newline: str) -> tuple[str, str]:
    for rows in instance["keys"].values():
        if rows:
            match = KEY_RE.match(rows[0]["raw"])
            if match:
                return match.group(1), newline
    return "", newline


def _record_change(changes: list[dict[str, Any]], row: dict[str, Any] | None,
                   key: str, old: str | None, new: str | None, reason: str,
                   action: str = "replace") -> None:
    changes.append({"line": (row["line"] + 1) if row else None,
                    "key": key, "old": old, "new": new,
                    "reason": reason, "action": action})


def _update_value(editor: LineEditor, changes: list[dict[str, Any]],
                  row: dict[str, Any] | None, expected: str, reason: str) -> None:
    if row is None:
        return
    if row["value"] != expected:
        _record_change(changes, row, row["key"], row["value"], expected, reason)
        editor.replace_value(row, expected)


def _update_checksum_series(editor: LineEditor, changes: list[dict[str, Any]],
                            instance: dict[str, Any], digests: list[str], reason: str,
                            newline: str) -> None:
    pairs = checksum_rows(instance)
    existing = {number: row for number, row in pairs}
    anchor_row = (max((row for _, row in pairs), key=lambda r: r["line"], default=None)
                  or first_key(instance, "CheckSumSize")
                  or first_key(instance, "FileSize"))
    if anchor_row is None and digests:
        return
    indent, _ = _line_style(instance, newline)
    inserts: list[str] = []
    for number, digest in enumerate(digests):
        row = existing.get(number)
        key = "CheckSum" if number == 0 else f"CheckSum{number}"
        if row is not None:
            _update_value(editor, changes, row, digest, reason)
        else:
            inserts.append(f'{indent}{key} = "{digest}"{newline}')
            _record_change(changes, None, key, None, digest, reason, "insert")
    for number, row in existing.items():
        if number >= len(digests):
            _record_change(changes, row, row["key"], row["value"], None,
                           "remove stale checksum block", "remove")
            editor.remove(row)
    if inserts and anchor_row is not None:
        editor.insert_after(anchor_row["line"], inserts)


def _existing_hash_header(data: bytes) -> tuple[str, str]:
    if not data:
        return "", "\n"
    newline = "\r\n" if b"\r\n" in data else "\n"
    text = data.decode("utf-8", errors="strict").replace("\r\n", "\n")
    header: list[str] = []
    for line in text.split("\n"):
        if not line or line.strip().startswith("#"):
            header.append(line)
        else:
            break
    while header and header[-1] == "":
        header.pop()
    return newline.join(header), newline


def build_hashes_bytes(directory: Path, checksum_size: int = DEFAULT_CHECKSUM_SIZE) -> tuple[bytes, int, list[dict[str, Any]]]:
    finalhash = directory / "hashes.txt"
    old = finalhash.read_bytes() if finalhash.is_file() else b""
    header, newline = _existing_hash_header(old)
    blocks: list[str] = []
    payload_bytes = 0
    entries: list[dict[str, Any]] = []
    directory_resolved = directory.resolve()
    files: list[Path] = []
    for path in directory.rglob("*"):
        if path == finalhash or not path.is_file():
            continue
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(directory_resolved):
            raise ValueError(
                f"directory member escapes section root: {path.relative_to(directory)}"
            )
        files.append(path)
    files.sort(key=lambda p: p.relative_to(directory).as_posix().casefold())
    for path in files:
        size, digests = chunk_sha1_file(path, checksum_size)
        payload_bytes += size
        lines = [f'FileName = "{path.name}"',
                 f'FileSize = "{size}"',
                 f'CheckSumSize = "{checksum_size}"']
        for number, digest in enumerate(digests):
            key = "CheckSum" if number == 0 else f"CheckSum{number}"
            lines.append(f'{key} = "{digest}"')
        blocks.append(newline.join(lines))
        entries.append({"path": path.relative_to(directory).as_posix(),
                        "bytes": size, "digests": digests})
    pieces: list[str] = []
    if header:
        pieces.append(header)
    pieces.extend(blocks)
    text = (newline + newline).join(pieces)
    if text and not text.endswith(newline):
        text += newline
    data = text.encode("utf-8")
    return data, payload_bytes + len(data), entries


def _plan_refresh(text: str, package_root: Path, mode: str = "auto") -> tuple[str, dict[str, Any], dict[Path, bytes]]:
    resolved_mode, editable_from = resolve_mode(text, mode)
    rows, suspicious = parse(text)
    instances = section_values(rows)
    newline = dominant_newline(text)
    editor = LineEditor(text)
    changes: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    sidecars: dict[Path, bytes] = {}
    sidecar_report: list[dict[str, Any]] = []
    editable_instances = [item for item in instances if item["section_line"] >= editable_from]

    def plan_hashes(directory: Path, chunk_size: int) -> tuple[bytes, int, list[dict[str, Any]]]:
        generated, total, entries = build_hashes_bytes(directory, chunk_size)
        sidecar = directory / "hashes.txt"
        old = sidecar.read_bytes() if sidecar.is_file() else b""
        if old != generated:
            sidecars[sidecar] = generated
            sidecar_report.append({
                "path": sidecar.relative_to(package_root).as_posix(),
                "old_sha1": sha1_bytes(old) if old else None,
                "new_sha1": sha1_bytes(generated),
                "bytes": len(generated),
                "entry_count": len(entries),
            })
        return generated, total, entries

    for instance in editable_instances:
        section = instance["name"]
        role = section_role(section)
        try:
            chunk_size = checksum_size(instance)
        except ValueError as exc:
            unresolved.append({"section": section, "reason": str(exc)})
            continue

        if role in {"file", "application", "bootloader"}:
            source_row = (first_key(instance, "Source") if role == "file"
                          else first_key(instance, "FileName"))
            file_size_row = first_key(instance, "FileSize")
            if source_row is None:
                if checksum_rows(instance) or file_size_row is not None:
                    unresolved.append({"section": section,
                                       "reason": f"{role} section is missing {'Source' if role == 'file' else 'FileName'}"})
                continue
            try:
                target = safe_package_path(package_root, section, source_row["value"])
            except ValueError as exc:
                unresolved.append({"section": section, "reason": str(exc)})
                continue
            if not target.is_file():
                unresolved.append({"section": section,
                                   "reason": f"payload not found: {target.relative_to(package_root)}"})
                continue
            size, digests = chunk_sha1_file(target, chunk_size)
            _update_value(editor, changes, file_size_row, str(size),
                          f"file size: {target.relative_to(package_root)}")
            _update_checksum_series(editor, changes, instance, digests,
                                    f"SHA-1 block(s): {target.relative_to(package_root)}", newline)

        elif role == "dir":
            file_size_row = first_key(instance, "FileSize")
            try:
                directory = safe_section_directory(package_root, section)
            except ValueError as exc:
                unresolved.append({"section": section, "reason": str(exc)})
                continue
            if not directory.is_dir():
                unresolved.append({"section": section,
                                   "reason": f"directory not found: {directory.relative_to(package_root)}"})
                continue
            try:
                generated, total_size, _ = plan_hashes(directory, chunk_size)
            except ValueError as exc:
                unresolved.append({"section": section, "reason": str(exc)})
                continue
            _update_value(editor, changes, file_size_row, str(total_size),
                          f"directory payload + hashes.txt bytes: {directory.relative_to(package_root)}")
            if chunk_size == 0:
                digests = [sha1_bytes(generated)]
            else:
                digests = [sha1_bytes(generated[offset:offset + chunk_size])
                           for offset in range(0, len(generated), chunk_size)]
            _update_checksum_series(editor, changes, instance, digests,
                                    f"SHA-1 of planned hashes.txt: {directory.relative_to(package_root)}", newline)

        final_script = first_key(instance, "FinalScript")
        final_checksum = first_key(instance, "FinalScriptChecksum")
        if final_script is not None and final_checksum is not None:
            try:
                script = safe_package_path(package_root, "", final_script["value"].removeprefix("./"))
            except ValueError as exc:
                unresolved.append({"section": section, "reason": f"FinalScript: {exc}"})
                continue
            if not script.is_file():
                unresolved.append({"section": section,
                                   "reason": f"FinalScript not found: {script.relative_to(package_root)}"})
                continue
            _, script_digests = chunk_sha1_file(script, DEFAULT_CHECKSUM_SIZE)
            if not script_digests:
                unresolved.append({"section": section, "reason": "FinalScript is empty"})
                continue
            _update_value(editor, changes, final_checksum, script_digests[0],
                          f"FinalScript first SHA-1 block: {script.relative_to(package_root)}")
            try:
                generated, total_size, _ = plan_hashes(script.parent, DEFAULT_CHECKSUM_SIZE)
            except ValueError as exc:
                unresolved.append({"section": section, "reason": f"FinalScript directory: {exc}"})
                continue
            dir_name = (PurePosixPath(final_script["value"].replace("\\", "/")).parent / "dir").as_posix()
            dir_name = dir_name.removeprefix("./").replace("/", "\\").casefold()
            matches = [candidate for candidate in editable_instances
                       if candidate["name"].replace("/", "\\").casefold() == dir_name]
            if matches:
                directory_instance = matches[0]
                _update_value(editor, changes, first_key(directory_instance, "FileSize"), str(total_size),
                              f"FinalScript directory payload + hashes.txt bytes: {script.parent.relative_to(package_root)}")
                dir_chunk = checksum_size(directory_instance)
                digests = ([sha1_bytes(generated)] if dir_chunk == 0 else
                           [sha1_bytes(generated[offset:offset + dir_chunk])
                            for offset in range(0, len(generated), dir_chunk)])
                _update_checksum_series(editor, changes, directory_instance, digests,
                                        f"FinalScript directory hashes.txt: {script.parent.relative_to(package_root)}", newline)
            else:
                unresolved.append({"section": section,
                                   "reason": f"FinalScript directory section not found in editable region: {dir_name}"})

    interim = editor.render()
    meta_rows, _ = parse(interim)
    _, meta_editable_from = resolve_mode(interim, resolved_mode)
    meta_candidates = [row for row in meta_rows
                       if row["kind"] == "key"
                       and row["key"].casefold() == "metafilechecksum"
                       and row["line"] >= meta_editable_from]
    if meta_candidates:
        expected = metafile_checksum(interim)
        second = LineEditor(interim)
        for row in meta_candidates:
            if row["value"] != expected:
                _record_change(changes, row, row["key"], row["value"], expected,
                               "SHA-1 of metainfo2 without MetafileChecksum line(s)")
                second.replace_value(row, expected)
        final = second.render()
    else:
        final = interim

    original_lines = text.splitlines(keepends=True)
    signed_prefix_preserved = None
    if resolved_mode == "signed-tail" and editable_from:
        prefix = "".join(original_lines[:editable_from])
        signed_prefix_preserved = final.startswith(prefix)

    for item in suspicious:
        item["region"] = "editable-tail" if item["line"] - 1 >= editable_from else "protected-prefix"

    report = {
        "status": "PASS" if not unresolved and not suspicious else "REVIEW",
        "mode": resolved_mode,
        "editable_from_line": editable_from + 1 if editable_from else 1,
        "signed_prefix_preserved": signed_prefix_preserved,
        "package_root": package_root.name,
        "changes": changes,
        "sidecar_changes": sidecar_report,
        "unresolved": unresolved,
        "suspicious_non_ini_lines": suspicious,
        "metafile_checksum": metafile_checksum(final),
    }
    return final, report, sidecars


def audit_and_refresh(text: str, package_root: Path, mode: str = "auto") -> tuple[str, dict[str, Any]]:
    refreshed, report, _ = _plan_refresh(text, package_root, mode)
    return refreshed, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("metainfo", type=Path)
    parser.add_argument("--root", type=Path, help="package root; defaults to metainfo parent")
    parser.add_argument("--mode", choices=("auto", "full", "signed-tail"), default="auto",
                        help="auto preserves the prefix through the last signature* line when present")
    parser.add_argument("--write", action="store_true",
                        help="replace metainfo and any planned hashes.txt sidecars in place")
    parser.add_argument("--output", type=Path,
                        help="write refreshed metainfo to a new file (refuses if hashes.txt sidecars also need changes)")
    args = parser.parse_args()
    if args.write and args.output:
        parser.error("--write and --output are mutually exclusive")

    metainfo = args.metainfo.resolve(strict=True)
    root = args.root.resolve(strict=True) if args.root else metainfo.parent.resolve()
    original = read_preserved(metainfo)
    refreshed, report, sidecars = _plan_refresh(original, root, args.mode)
    print(json.dumps(report, indent=2))

    if args.write:
        for path, data in sidecars.items():
            path.write_bytes(data)
        write_preserved(metainfo, refreshed)
    elif args.output:
        if sidecars:
            raise RuntimeError("planned hashes.txt changes exist; use --write on a copied package for a consistent result")
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_preserved(args.output, refreshed)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
