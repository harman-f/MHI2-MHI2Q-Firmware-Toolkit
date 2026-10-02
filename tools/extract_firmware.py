#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract MHI2 MMX and RCC components from an archive or raw image.

Output must be a new directory. External parsers are required only for the
selected components that need them. A failed run freezes partial output.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
from typing import Any

QNXMOUNT_COMMIT = "0379c064975d5bbe3595ac7e3d149ea789406794"

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from android_image import decompress_module
from binary_probe import analyze_binary
from filesystem_readers import (
    extract_rcc_root,
    inventory_qnx6,
    materialize_qnx6,
    safe_member_path,
    safe_segment,
    sha256_file,
)
from imagefs import materialize_imagefs
from mifs_stage2 import decompress_container
from qnx_ifs import decompress_ucl_ifs


def detect_path(explicit: Path | None, environment: str, required_module: str) -> Path | None:
    candidate = explicit or (Path(os.environ[environment]) if os.environ.get(environment) else None)
    if candidate is not None:
        return candidate.resolve(strict=True)
    if importlib.util.find_spec(required_module) is not None:
        return None
    raise FileNotFoundError(f"{required_module} unavailable; set {environment} or use its --path option")


def detect_7zip(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve(strict=True)
    if os.environ.get("MHI2_7ZIP"):
        return Path(os.environ["MHI2_7ZIP"]).resolve(strict=True)
    found = shutil.which("7z") or shutil.which("7za")
    if found:
        return Path(found).resolve(strict=True)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidate = Path(base) / "7-Zip" / "7z.exe"
            if candidate.is_file():
                return candidate.resolve(strict=True)
    raise FileNotFoundError("7-Zip unavailable; pass --seven-zip or set MHI2_7ZIP")


def list_members(seven_zip: Path, archive: Path) -> list[dict[str, Any]]:
    result = subprocess.run([str(seven_zip), "l", "-slt", str(archive)], check=True,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    members: list[dict[str, Any]] = []
    record: dict[str, str] = {}
    for line in result.stdout.splitlines() + [""]:
        if not line:
            attributes = record.get("Attributes", "")
            if any(field.startswith("l") for field in attributes.split()):
                raise ValueError(f"symbolic-link archive member is not accepted: {record.get('Path', '')!r}")
            if "Size" in record and "D" not in record.get("Attributes", ""):
                path = record.get("Path", "").replace("\\", "/")
                rel = PurePosixPath(path)
                if not path or rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
                    raise ValueError(f"unsafe archive member: {path!r}")
                for part in rel.parts:
                    safe_segment(part)
                members.append({"path": path, "size": int(record["Size"]), "crc": record.get("CRC", "")})
            record = {}
            continue
        key, separator, value = line.partition(" = ")
        if separator:
            record[key] = value
    return members


def package_prefix(members: list[dict[str, Any]], requested: str | None) -> str:
    groups: dict[str, set[str]] = {}
    for member in members:
        parts = member["path"].split("/")
        for index, part in enumerate(parts):
            if part in ("MMX2", "RCC"):
                groups.setdefault("/".join(parts[:index]), set()).add(part)
                break
    if requested is not None:
        prefix = requested.strip("/")
        if prefix not in groups:
            raise ValueError(f"package prefix {prefix!r} not found; choices: {sorted(groups)}")
        return prefix
    candidates = [prefix for prefix, components in groups.items() if components == {"MMX2", "RCC"}]
    if not candidates:
        candidates = list(groups)
    if len(candidates) != 1:
        raise ValueError(f"ambiguous firmware package; use --package-prefix: {sorted(candidates)}")
    return candidates[0]


def select_members(members: list[dict[str, Any]], prefix: str, variant_option: str, source: Path,
                   components: set[str] | None = None) -> tuple[list[dict[str, Any]], list[str], list[str], list[str], list[str], list[str], list[str], list[str]]:
    components = components or {"rcc", "mmx"}
    base = f"{prefix}/" if prefix else ""
    available = sorted({parts[2] for member in members
                        if member["path"].startswith(base + "MMX2/app/")
                        if len(parts := member["path"][len(base):].split("/")) >= 5 and parts[2].isdigit() and parts[-1] == "app.img"})
    if not available:
        raise ValueError("no MMX2/app/<variant>/default/app.img member found")
    if variant_option == "auto":
        variants = ["50"] if "AU57X" in source.name.upper() and "50" in available else available
    elif variant_option == "both":
        variants = available
    else:
        variants = [variant_option]
    if any(variant not in available for variant in variants):
        raise ValueError(f"requested variant unavailable: {variants}; available: {available}")

    selected: list[dict[str, Any]] = []
    for member in members:
        path = member["path"]
        if not path.startswith(base):
            continue
        relative = path[len(base):]
        parts = relative.split("/")
        if parts[0] == "RCC" and "rcc" in components:
            selected.append(member)
        elif parts[0] == "MMX2" and len(parts) == 2 and ("mmx" in components or "java" in components):
            selected.append(member)
        elif (parts[0] == "MMX2" and len(parts) >= 4 and parts[2] in variants
              and ("mmx" in components or ("java" in components and parts[1] == "mifs-stage2"))):
            selected.append(member)
        elif relative == "metainfo2.txt":
            selected.append(member)
    paths = [member["path"] for member in selected]
    if len({path.casefold() for path in paths}) != len(paths):
        raise ValueError("archive members collide on case-insensitive hosts")
    app_images = ([base + f"MMX2/app/{variant}/default/app.img" for variant in variants]
                  if "mmx" in components else [])
    if any(path not in paths for path in app_images):
        raise ValueError("expected app image missing from selection")
    rcc_roots = [path for path in paths if path.startswith(base + "RCC/ifs-root/") and path.endswith("/ifs-root.ifs")]
    rcc_efs = [path for path in paths if path.startswith(base + "RCC/") and path.lower().endswith(".efs")]
    mmx_efs = [path for path in paths if path.startswith(base + "MMX2/efs-") and path.lower().endswith(".img")]
    rcc_emergency = [path for path in paths if path.startswith(base + "RCC/") and path.lower().endswith("ifs-emergency.ifs")]
    mifs_stage2 = [path for path in paths if path.startswith(base + "MMX2/mifs-stage2/") and path.lower().endswith("mifs-stage2.img")]
    android_images = [path for path in paths if path.startswith((base + "MMX2/eifs/", base + "MMX2/mifs-stage1/")) and path.lower().endswith(".img")]
    return selected, app_images, rcc_roots, rcc_efs, rcc_emergency, mifs_stage2, mmx_efs, android_images


def unparsed_image_members(selected_paths: list[str], parsed_paths: set[str]) -> list[str]:
    """List selected filesystem/image payloads not handled by a parser."""
    image_suffixes = {".bin", ".efs", ".ifs", ".img"}
    return sorted(path for path in selected_paths
                  if PurePosixPath(path).suffix.casefold() in image_suffixes
                  and path not in parsed_paths)


def opaque_report_filename(member_path: str, content_sha256: str) -> str:
    """Return a deterministic report name unique to both member path and content."""
    safe_name = PurePosixPath(member_path).stem.replace(" ", "_")
    path_tag = hashlib.sha256(member_path.encode("utf-8")).hexdigest()[:12]
    return f"opaque-{safe_name}-{path_tag}-{content_sha256[:12]}.json"


def identify_known_raw_payload(member_path: str, payload: bytes) -> dict[str, Any] | None:
    """Recognize the tested MU quickboot selector by path and embedded markers."""
    folded = member_path.casefold()
    if "/qb-primary/" not in folded and "/qb-recovery/" not in folded:
        return None
    markers = (b"KERNEL_PRIMARY", b"KERNEL_RECOVERY", b"ANDROID!")
    present = [marker.decode("ascii") for marker in markers if marker in payload]
    if len(present) != len(markers):
        return None
    return {"source": member_path,
            "classification": "boot-selection-loader candidate; raw payload retained",
            "filesystem_tree": False,
            "marker_strings": present,
            "evidence_limit": "Static strings and member path only; executable behavior not dynamically verified."}


def normalize_components(requested: list[str] | None) -> set[str]:
    if not requested or "all" in requested:
        if requested and len(requested) > 1:
            raise ValueError("--component all cannot be combined with another component")
        return {"rcc", "mmx"}
    return set(requested)


def count_excluded_70_members(members: list[dict[str, Any]], prefix: str,
                              components: set[str], variants: list[str]) -> int:
    if "70" in variants or not ({"mmx", "java"} & components):
        return 0
    base = f"{prefix}/" if prefix else ""
    count = 0
    for item in members:
        path = item["path"]
        if not path.startswith(base + "MMX2/"):
            continue
        parts = path[len(base):].split("/")
        if len(parts) < 4 or parts[2] != "70":
            continue
        if "mmx" in components or ("java" in components and parts[1] == "mifs-stage2"):
            count += 1
    return count


def load_qnx(qnxmount_root: Path | None, dependency_root: Path | None) -> tuple[Any, Any]:
    for path in (dependency_root, qnxmount_root):
        if path is not None:
            sys.path.insert(0, str(path))
    from qnxmount.qnx6.interface import QNX6FS
    from qnxmount.stream import Stream
    return Stream, QNX6FS


def copy_raw(source: Path, raw_root: Path) -> Path:
    target = raw_root / source.name
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=8 * 1024 * 1024)
    if target.stat().st_size != source.stat().st_size or sha256_file(target) != sha256_file(source):
        raise IOError(f"raw copy verification failed: {target}")
    return target


def looks_like_qnx_efs(source: Path) -> bool:
    """Recognize QSSL_F3S boot metadata used by MMX2 .img EFS members."""
    with source.open("rb") as stream:
        return b"QSSL_F3S" in stream.read(4096)


def looks_like_qnx6_app(source: Path) -> bool:
    """Conservatively recognize the observed QNX6 app-image boot sector."""
    if source.stat().st_size < 512:
        return False
    with source.open("rb") as stream:
        sector = stream.read(512)
    return sector[:3] == b"\xEB\x10\x90" and sector[510:512] == b"\x55\xAA"


def extract_rcc_efs(image_path: Path, output: Path) -> dict[str, Any]:
    """Materialize one QNX EFS partition without creating host symlinks."""
    from qnxmount.efs.interface import scan_partitions

    partitions = list(scan_partitions(image_path))
    if len(partitions) != 1:
        raise ValueError(f"expected one QNX EFS partition in {image_path}, found {len(partitions)}")
    filesystem = partitions[0]
    relative_image = image_path.relative_to(output / "raw")
    tree = output / "filesystems" / relative_image
    tree.mkdir(parents=True, exist_ok=False)
    counts = {"directory": 0, "file": 0, "symlink": 0, "other": 0}
    bytes_written = 0
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    pending = [(filesystem.root, PurePosixPath(""), 0)]
    while pending:
        parent, prefix, depth = pending.pop()
        if depth > 100:
            raise ValueError("EFS directory nesting exceeds safety limit")
        for entry in filesystem.read_dir(parent):
            name = str(entry.name)
            safe_segment(name)
            relative = prefix / name
            logical_path = relative.as_posix()
            if logical_path.casefold() in seen:
                raise ValueError(f"duplicate/colliding EFS path: {logical_path}")
            seen.add(logical_path.casefold())
            target = tree.joinpath(*relative.parts)
            mode = entry.stat.mode
            detail = {"path": logical_path, "mode": mode, "uid": entry.stat.uid,
                      "gid": entry.stat.gid, "mtime": entry.stat.mtime,
                      "ctime": entry.stat.ctime}
            if stat.S_ISDIR(mode):
                target.mkdir(parents=True, exist_ok=False)
                pending.append((entry, relative, depth + 1))
                detail["type"] = "directory"
                counts["directory"] += 1
            elif stat.S_ISREG(mode):
                data = filesystem.read_file(entry)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(data)
                detail.update({"type": "file", "bytes": len(data),
                               "sha256": sha256_file(target)})
                bytes_written += len(data)
                counts["file"] += 1
            elif stat.S_ISLNK(mode):
                detail.update({"type": "symlink", "target": filesystem.read_file(entry).decode("utf-8", errors="replace"),
                               "representation": "metadata only; no host link created"})
                counts["symlink"] += 1
            else:
                detail["type"] = "other"
                counts["other"] += 1
            entries.append(detail)
    metadata_path = tree / "_image_metadata.json"
    if metadata_path.exists():
        raise ValueError("EFS contains a path reserved for extraction metadata")
    metadata = {"source_image": relative_image.as_posix(),
                "source_sha256": sha256_file(image_path),
                "source_bytes": image_path.stat().st_size,
                "counts": counts, "regular_file_bytes": bytes_written,
                "entries": entries}
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, indent=2)
    return {"source": relative_image.as_posix(),
            "tree": str(tree.relative_to(output)).replace("\\", "/"),
            "metadata": str(metadata_path.relative_to(output)).replace("\\", "/"),
            "counts": counts, "regular_file_bytes": bytes_written}


def run(args: argparse.Namespace) -> dict[str, Any]:
    components = normalize_components(args.component)
    source = args.source.resolve(strict=True)
    output = args.output.resolve() if args.output else None
    if not args.plan and output is None:
        raise ValueError("--output is required unless --plan is used")
    if output is not None and output.exists():
        raise ValueError(f"refusing to reuse an existing output: {output}")
    source_hash = sha256_file(source)
    if args.expected_sha256 and source_hash.casefold() != args.expected_sha256.casefold():
        raise ValueError(f"source SHA-256 mismatch: {source_hash}")

    is_archive = source.suffix.lower() in (".7z", ".zip")
    if not is_archive and source.suffix.lower() not in (".img", ".bin", ".ifs", ".efs"):
        raise ValueError("source must be .7z, .zip, .img, .bin, .ifs, or .efs")
    members: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    app_images: list[str] = []
    rcc_roots: list[str] = []
    rcc_efs: list[str] = []
    mmx_efs: list[str] = []
    android_images: list[str] = []
    rcc_emergency: list[str] = []
    mifs_stage2: list[str] = []
    unknown_raw: list[str] = []
    prefix = ""
    variants: list[str] = []
    seven_zip: Path | None = None
    if is_archive:
        seven_zip = detect_7zip(args.seven_zip)
        members = list_members(seven_zip, source)
        prefix = package_prefix(members, args.package_prefix)
        selected, app_images, rcc_roots, rcc_efs, rcc_emergency, mifs_stage2, mmx_efs, android_images = select_members(
            members, prefix, args.variant, source, components)
        variants = sorted({path.split("/")[-3] for path in app_images or mifs_stage2})
    elif source.suffix.lower() in (".img", ".bin"):
        with source.open("rb") as stream:
            magic = stream.read(4)
        if magic == b"LZOZ":
            mifs_stage2 = [source.name]
            inferred = source.parent.parent.name if source.parent.name == "default" else "unknown"
            variants = [inferred] if inferred in ("50", "70") else []
        elif magic == b"A\xffD\xff":
            android_images = [source.name]
        elif looks_like_qnx_efs(source):
            rcc_efs = [source.name]
        elif looks_like_qnx6_app(source):
            inferred = source.parent.parent.name if source.parent.name == "default" else "50"
            variant = args.variant if args.variant not in ("auto", "both") else inferred
            variants = [variant]
            app_images = [source.name]
        else:
            unknown_raw = [source.name]
    elif source.suffix.lower() == ".ifs":
        if "emergency" in source.name.casefold():
            rcc_emergency = [source.name]
        else:
            rcc_roots = [source.name]
    else:
        rcc_efs = [source.name]

    plan = {"source": source.name, "source_bytes": source.stat().st_size,
            "source_sha256": source_hash, "archive_prefix": prefix, "variants": variants,
            "components": sorted(components),
            "selected_member_count": len(selected), "selected_member_bytes": sum(item["size"] for item in selected),
            "app_images": app_images, "rcc_roots": rcc_roots, "rcc_efs": rcc_efs,
            "mmx_efs": mmx_efs,
            "rcc_emergency": rcc_emergency, "mifs_stage2": mifs_stage2,
            "android_images": android_images, "unknown_raw": unknown_raw,
            "excluded_mmx70_members": count_excluded_70_members(members, prefix, components, variants)}
    if args.plan:
        return {"status": "PLAN", **plan}

    qnx_root = dependency_root = dumpifs_dir = None
    Stream = QNX6FS = None
    if app_images or rcc_efs or mmx_efs:
        qnx_root = detect_path(args.qnxmount_root, "MHI2_QNXMOUNT_ROOT", "qnxmount")
        dependency_root = detect_path(args.dependency_root, "MHI2_QNXMOUNT_DEPS", "crcmod")
        Stream, QNX6FS = load_qnx(qnx_root, dependency_root)
    if rcc_roots:
        dumpifs_dir = detect_path(args.dumpifs_dir, "MHI2_DUMPIFS_DIR", "dumpifs")
        if dumpifs_dir is not None:
            sys.path.insert(0, str(dumpifs_dir))
        try:
            import dumpifs  # noqa: F401  # validates python-lzo before any output is created
        except ModuleNotFoundError as exc:
            raise RuntimeError("RCC IFS needs dumpifs and python-lzo in this Python runtime; use the prepared Python 3.11 runtime or install dependencies") from exc
    emergency_to_parse = [] if args.skip_emergency else rcc_emergency
    if mifs_stage2:
        try:
            import lzo
        except ModuleNotFoundError as exc:
            raise RuntimeError("MMX MIFS stage 2 needs python-lzo with LZO1Z support") from exc
    assert output is not None
    output.mkdir(parents=True, exist_ok=False)
    try:
        raw_root = output / "raw"
        raw_root.mkdir()
        if is_archive:
            assert seven_zip is not None
            command = [str(seven_zip), "x", "-y", f"-o{raw_root}", str(source)]
            command.extend(item["path"].replace("/", "\\") for item in selected)
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log_text = (result.stdout + result.stderr).replace(str(source), "<SOURCE>")
            log_text = log_text.replace(str(raw_root), "<RAW_OUTPUT>")
            with (output / "7zip-extract.log").open("x", encoding="utf-8") as stream:
                stream.write(log_text)
            if result.returncode:
                raise IOError(f"7-Zip extraction failed: exit {result.returncode}")
        else:
            copy_raw(source, raw_root)

        extracted: list[dict[str, Any]] = []
        for member in selected:
            path = safe_member_path(raw_root, member["path"])
            if not path.is_file() or path.stat().st_size != member["size"]:
                raise IOError(f"extracted member missing or wrong size: {member['path']}")
            extracted.append({**member, "sha256": sha256_file(path)})

        recognized_raw_components: list[dict[str, Any]] = []
        for member in extracted:
            if PurePosixPath(member["path"]).suffix.casefold() not in {".bin", ".efs", ".ifs", ".img"}:
                continue
            image_path = safe_member_path(raw_root, member["path"])
            with image_path.open("rb") as stream:
                classification = identify_known_raw_payload(member["path"], stream.read(2 * 1024 * 1024))
            if classification is not None:
                recognized_raw_components.append(classification)

        apps: list[dict[str, Any]] = []
        for member_path, variant in zip(app_images, variants):
            assert Stream is not None and QNX6FS is not None
            image = safe_member_path(raw_root, member_path)
            image_hash = sha256_file(image)
            with Stream(image) as stream:
                entries = inventory_qnx6(QNX6FS(stream))
            result = materialize_qnx6(image, variant, output, Stream, QNX6FS, image_hash)
            result["safe_entry_count"] = len(entries)
            apps.append(result)
            print(f"MMX2 app/{variant}: {result['counts']}", flush=True)

        rcc_results: list[dict[str, Any]] = []
        for member_path in rcc_roots:
            image = safe_member_path(raw_root, member_path)
            rcc_results.append(extract_rcc_root(image, output, dumpifs_dir))

        emergency_results: list[dict[str, Any]] = []
        for member_path in emergency_to_parse:
            image = safe_member_path(raw_root, member_path)
            relative_image = image.relative_to(raw_root)
            decoded = output / "decoded" / relative_image.with_suffix(".imagefs")
            decode = decompress_ucl_ifs(image, decoded)
            tree = output / "filesystems" / relative_image.parent / (relative_image.stem + "-imagefs")
            filesystem = materialize_imagefs(
                decoded, tree,
                output / "metadata" / f"imagefs-emergency-{relative_image.parent.parent.name}.json", display_root=output)
            emergency_results.append({"source": relative_image.as_posix(),
                                      "decoded_imagefs": str(decoded.relative_to(output)).replace("\\", "/"),
                                      "decode": decode, "filesystem": filesystem})

        stage2_results: list[dict[str, Any]] = []
        java_exports: list[dict[str, Any]] = []
        for member_path in mifs_stage2:
            image = safe_member_path(raw_root, member_path)
            relative_image = image.relative_to(raw_root)
            decoded = output / "decoded" / relative_image.with_suffix(".imagefs")
            decoded.parent.mkdir(parents=True, exist_ok=True)
            try:
                import lzo
            except ModuleNotFoundError as exc:
                raise RuntimeError("MMX MIFS stage 2 needs python-lzo with LZO1Z support") from exc
            decode_result = decompress_container(
                image, decoded,
                decompress=lambda data, max_size: lzo.decompress(
                    data, False, max_size, algorithm="LZO1Z"))
            filesystem_tree = output / "filesystems" / relative_image.parent / (relative_image.stem + "-imagefs")
            helper_result = materialize_imagefs(
                decoded, filesystem_tree,
                output / "metadata" / f"imagefs-mifs-{relative_image.parent.parent.name}.json", display_root=output)
            jxe_paths = [path for path in filesystem_tree.rglob("*")
                         if path.is_file() and path.name.casefold() == "lsd.jxe"]
            if "java" in components:
                for jxe in jxe_paths:
                    digest = sha256_file(jxe)
                    relative_jxe = jxe.relative_to(filesystem_tree)
                    export = output / "java" / relative_image.parent.parent.name / "source" / relative_jxe
                    export.parent.mkdir(parents=True, exist_ok=True)
                    with jxe.open("rb") as reader, export.open("xb") as writer:
                        shutil.copyfileobj(reader, writer, length=8 * 1024 * 1024)
                    if sha256_file(export) != digest:
                        raise IOError(f"Java source export hash mismatch: {export}")
                    java_exports.append({"variant": relative_image.parent.parent.name,
                                         "source": str(jxe.relative_to(output)).replace("\\", "/"),
                                         "source_sha256": digest, "source_bytes": jxe.stat().st_size,
                                         "export": str(export.relative_to(output)).replace("\\", "/")})
            conversions: list[dict[str, Any]] = []
            stage2_results.append({"source": str(relative_image).replace("\\", "/"),
                                   "decoded_imagefs": str(decoded.relative_to(output)).replace("\\", "/"),
                                   "decode": decode_result, "filesystem": helper_result,
                                   "lsd_jxe_count": len(jxe_paths), "jxe_decompilations": conversions})

        efs_results: list[dict[str, Any]] = []
        for member_path in [*rcc_efs, *mmx_efs]:
            image = safe_member_path(raw_root, member_path)
            efs_results.append(extract_rcc_efs(image, output))

        android_results: list[dict[str, Any]] = []
        for member_path in android_images:
            image = safe_member_path(raw_root, member_path)
            relative_image = image.relative_to(raw_root)
            module_name = relative_image.stem
            decoded_base = output / "decoded" / relative_image.parent / module_name
            kernel_path = decoded_base.with_name(module_name + "-kernel.bin")
            imagefs_path = decoded_base.with_name(module_name + "-inner.imagefs")
            decode = decompress_module(image, kernel_path, imagefs_path)
            tree = output / "filesystems" / relative_image.parent / (module_name + "-imagefs")
            metadata = output / "metadata" / f"imagefs-{module_name}-{relative_image.parent.parent.name}.json"
            filesystem = materialize_imagefs(imagefs_path, tree, metadata, display_root=output)
            android_results.append({"source": relative_image.as_posix(),
                                    "kernel": str(kernel_path.relative_to(output)).replace("\\", "/"),
                                    "decoded_imagefs": str(imagefs_path.relative_to(output)).replace("\\", "/"),
                                    "decode": decode, "filesystem": filesystem})

        selected_image_paths = [item["path"] for item in selected]
        parsed_paths = set(app_images + rcc_roots + rcc_efs + mmx_efs + mifs_stage2 + android_images)
        selected_image_paths.extend(app_images + rcc_roots + rcc_efs + mmx_efs +
                                    rcc_emergency + mifs_stage2 + android_images + unknown_raw)
        if not args.skip_emergency:
            parsed_paths.update(rcc_emergency)
        unparsed_components = unparsed_image_members(selected_image_paths, parsed_paths)
        opaque_binary_analysis: list[dict[str, Any]] = []
        if unparsed_components:
            metadata_root = output / "metadata"
            metadata_root.mkdir(parents=True, exist_ok=True)
            for member_path in unparsed_components:
                image = safe_member_path(raw_root, member_path)
                analysis = analyze_binary(image, max_strings=64)
                analysis["source"] = member_path
                content_sha256 = sha256_file(image)
                report_path = metadata_root / opaque_report_filename(member_path, content_sha256)
                with report_path.open("x", encoding="utf-8") as stream:
                    json.dump(analysis, stream, indent=2)
                opaque_binary_analysis.append({
                    "source": member_path,
                    "analysis": str(report_path.relative_to(output)).replace("\\", "/"),
                    "classifications": analysis["classifications"],
                    "marker_names": sorted(analysis["markers"]),
                })
        jxe_total = sum(item["lsd_jxe_count"] for item in stage2_results)
        external_postprocessing = (["LSD JXE to JAR/Java decompilation"] if jxe_total else [])
        completeness = "PARTIAL" if unparsed_components else "PASS"
        manifest = {"status": completeness, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "source_class": "LOCAL-ONLY; read-only", "target_class": "LOCAL-ONLY; additive derived output",
                    **plan, "unparsed_components": unparsed_components,
                    "external_postprocessing": external_postprocessing,
                    "java_exports": java_exports,
                    "selected_members": extracted, "app_filesystems": apps,
                    "recognized_raw_components": recognized_raw_components,
                    "opaque_binary_analysis": opaque_binary_analysis,
                    "rcc_root_filesystems": rcc_results,
                    "qnx_efs_filesystems": efs_results,
                    "rcc_efs_filesystems": [item for item in efs_results if item["source"].startswith("RCC/")],
                    "mmx_efs_filesystems": [item for item in efs_results if item["source"].startswith("MMX2/")],
                    "rcc_emergency_filesystems": emergency_results,
                    "mifs_stage2_filesystems": stage2_results,
                    "android_module_filesystems": android_results,
                    "tools": {"seven_zip": ({"executable": seven_zip.name, "sha256": sha256_file(seven_zip)}
                                              if seven_zip else None),
                              "qnxmount": ({"source": "external checkout" if qnx_root else "python environment",
                                            "expected_commit": QNXMOUNT_COMMIT}
                                           if apps or efs_results else None),
                              "dumpifs": ({"source": "external checkout" if dumpifs_dir else "python environment",
                                           "module_sha256": sha256_file(dumpifs_dir / "dumpifs.py")
                                           if dumpifs_dir and (dumpifs_dir / "dumpifs.py").is_file() else None}
                                          if rcc_results else None),
                              "qnx_ifs_decoder": ({"module": "tools/qnx_ifs.py",
                                                   "sha256": sha256_file(Path(__file__).with_name("qnx_ifs.py")),
                                                   "ucl_module_sha256": sha256_file(Path(__file__).with_name("ucl_nrv2b.py"))}
                                                  if emergency_results else None)},
                    "errors": [], "deletion_authorized": False,
                    "recycle_bin_result": "not applicable"}
        with (output / "extraction_manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        return {"status": completeness, "output": output.name, "archive_prefix": prefix,
                "variants": variants, "selected_member_count": len(selected),
                "components": sorted(components), "java_exports": java_exports,
                "unparsed_components": unparsed_components,
                "external_postprocessing": external_postprocessing,
                "recognized_raw_components": recognized_raw_components,
                "opaque_binary_analysis": opaque_binary_analysis,
                "app_filesystems": apps, "rcc_root_filesystems": rcc_results,
                "qnx_efs_filesystems": efs_results,
                "rcc_efs_filesystems": [item for item in efs_results if item["source"].startswith("RCC/")],
                "mmx_efs_filesystems": [item for item in efs_results if item["source"].startswith("MMX2/")],
                "rcc_emergency_filesystems": emergency_results,
                "mifs_stage2_filesystems": stage2_results,
                "android_module_filesystems": android_results}
    except BaseException as exc:
        with (output / "FREEZE_LEDGER.md").open("x", encoding="utf-8") as stream:
            stream.write(f"# Extraction freeze\n\nSource: {source.name}\n\nTarget: {output.name}\n\n"
                         f"Failure: {type(exc).__name__}: {exc}\n\nPartial output retained; no cleanup attempted.\n")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help=".7z, .zip, .img, .bin, .ifs, or .efs")
    parser.add_argument("--output", type=Path, help="new local export directory")
    parser.add_argument("--plan", action="store_true", help="show archive selection without creating output")
    parser.add_argument("--variant", choices=("auto", "50", "70", "both"), default="auto")
    parser.add_argument("--component", action="append", choices=("all", "rcc", "mmx", "java"),
                        help="repeat to combine scopes; default/all = RCC + MMX; java selects Stage 2 and exports LSD JXE")
    parser.add_argument("--package-prefix", help="select one package inside a nested archive")
    parser.add_argument("--expected-sha256", help="optional source integrity pin")
    parser.add_argument("--seven-zip", type=Path)
    parser.add_argument("--qnxmount-root", type=Path)
    parser.add_argument("--dependency-root", type=Path)
    parser.add_argument("--dumpifs-dir", type=Path)
    parser.add_argument("--skip-emergency", action="store_true",
                        help="retain and hash Emergency IFS raw, but mark its filesystem tree unparsed")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), indent=2), flush=True)
    except (Exception, SystemExit) as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
