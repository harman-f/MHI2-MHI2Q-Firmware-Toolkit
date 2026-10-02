# MHI2 flash layout, image sizes, boot chain, and recovery evidence

This is a deeper evidence note for the image-format guide. It separates three things that are easy to conflate:

1. update-package member sizes and signatures;
2. physical NOR/NAND offsets observed in historical recovery notes;
3. addresses and lengths inside a decompressed QNX image.

The address tables below are not a universal MHI2/MHI2Q specification. The MMX NOR tables are transcribed from a wiki report comparing one G11 H22 unit with a “normal” G11 layout. RCC values are recovery write targets reported for particular firmware examples. The MU1440 sizes/signatures are measured from one Škoda MU1440 archive. No firmware bytes are included here.

## 1. Sample basis and size conventions

Measured baseline:

- Package: Škoda MHI2_ER_SKG13_P4526_MU1440.7z
- Archive bytes: 2,288,860,862
- Archive SHA-256: b23225d68999f0613f2652c898ce36c74d6c1d63a36f29ff5d4faf500c60e5a5
- Basis: local extraction manifest and raw extracted members; the archive and extracted firmware remain local-only.
- Units: table sizes are exact byte counts. MiB means 1,048,576 bytes; sizes printed in hexadecimal are byte counts or byte offsets as labelled.

These are examples for this MU, not expected sizes for every train or firmware. An update member's byte length is not the same as its installed partition capacity, uncompressed filesystem length, or sum of regular-file bytes.

| Update member | Sample member bytes | Leading bytes / structural evidence | What the size means |
| --- | ---: | --- | --- |
| RCC ifs-root.ifs | 22,611,484 (21.56 MiB) | At file offset 0: ARM code; QNX marker EB 7E FF 00 at offset 0x08 | Serialized IFS update member; not an RCC flash partition-size declaration |
| RCC ifs-emergency.ifs | 3,738,972 (3.57 MiB) | QNX marker EB 7E FF 00 at offset 0x08 | Serialized emergency IFS. Its decoded ImageFS is 9,035,508 bytes |
| RCC efs-system.efs | 25,165,824 (24 MiB) | Filesystem is recognized by the QNX EFS reader; do not infer its flash placement from extension | Serialized EFS member |
| MMX mifs-stage1.img | 3,145,728 (3 MiB), both /50/ and /70/ | 41 FF 44 FF 4F FF 44 FF; Android-style 8-byte wrapper followed by little-endian header | Padded wrapper file. The 50/70 kernel payloads differ |
| MMX eifs.img | 6,291,456 (6 MiB) | Same 8-byte wrapper signature | Padded wrapper file; sample package contains /50/ only |
| MMX mifs-stage2.img /50/ | 48,234,496 (46 MiB) | ASCII LZOZ at offset 0; 0x200-byte header/table, block payload starts at file offset 0x800 | Compressed container size. Its 37 LZO1Z blocks decode to a 75,529,244-byte ImageFS stream |
| MMX mifs-stage2.img /70/ | 44,040,192 (42 MiB) | Same LZOZ structure | Different compressed size; decoded ImageFS stream is byte-identical to /50/ in this sample |
| MMX efs-system.img /50/ and /70/ | 2,097,152 (2 MiB) each | QNX EFS reader recognizes both | Two different raw member hashes despite equal size |
| MMX efs-persist.img /50/ | 4,194,304 (4 MiB) | QNX EFS reader recognizes it | Sample archive member size |
| MMX efs-persist.img /70/ | 8,388,608 (8 MiB) | QNX EFS reader recognizes it | Sample archive member size; twice /50/ |
| MMX app.img /50/ and /70/ | 1,438,613,504 (1,371.75 MiB) each | Both begin EB 10 90; bytes 510–511 are 55 AA | Large raw app image, not its used-file total. Extracted regular files total 736,111,706 bytes (/50/) and 822,645,100 bytes (/70/) |

### Signatures and nested lengths

- The MMX Stage-1/EIFS wrapper begins with bytes 41 FF 44 FF 4F FF 44 FF, rendered in the source wiki as “AÿDÿOÿDÿ”. The extractor reads the eight little-endian 32-bit header words and uses page_size and kernel_size to bound the zlib stream. In this MU, page_size is 2,048 bytes; the decompressed payload contains a QNX startup header at offset 8.
- In the sample /50/ mifs-stage1 wrapper, kernel_size is 2,984,374 bytes; its decompressed QNX kernel is 6,841,260 bytes and declares imagefs_size 6,734,492 bytes. The /70/ wrapper has the same outer file length but a distinct kernel-size field and hash.
- In sample eifs.img, kernel_size is 5,572,424 bytes; decompressed kernel is 12,959,872 bytes and declares imagefs_size 12,853,104 bytes.
- QNX IFS startup header marker EB 7E FF 00 occurs at offset 8 in both sampled RCC IFS files. The header itself is 256 bytes. Its stored_size and imagefs_size describe the serialized and uncompressed image components; they are not flash addresses.
- Stage-2 LZOZ declares a 2,097,152-byte expanded block size and contains 37 blocks in this sample. Both 50/70 outputs hash to 4456de46a33e3731da95ef386da035e43990037fe9ccaeea171657732e8cddb1.
- The sample app.img boot bytes EB 10 90 and trailer 55 AA are observations only. They do not, by themselves, identify the complete filesystem/container format or justify treating its first sector as a conventional PC MBR. The QNX6 reader successfully parses the image in the extraction baseline; further sector-field interpretation needs independent validation.

QNX's public documentation describes the IFS startup header as boot/startup metadata and distinguishes stored size from uncompressed ImageFS size. That distinction is essential: neither the QNX memory addresses nor the header sizes should be substituted for physical flash offsets.

## 2. MMX NOR: historical address maps

The following maps are copied from the retained wiki page “Manual FW update /50/ vs /70/ folders”. It calls both maps G11 and distinguishes a 2013 H22 unit from its “Normal” comparison. The wiki author says the H22 partitioning differed from what they had seen on G11 units and only assumes that this unit needs /50/ update folders. Treat this as an observed, hardware-specific map awaiting validation against a raw NOR dump, not as a general MHI2 map and not as proof that /50/ always means H22.

All offsets are relative to the MMX NOR base as shown in that wiki table. End addresses are exclusive.

| Region | H22 start | H22 size | H22 end | “Normal” start | “Normal” size | “Normal” end |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BCT | 0x00000000 | 0x00040000 | 0x00040000 | 0x00000000 | 0x00040000 | 0x00040000 |
| PT | 0x00040000 | 0x00020000 | 0x00060000 | 0x00040000 | 0x00020000 | 0x00060000 |
| STAGE1_RECOVERY | 0x00060000 | 0x00040000 | 0x000A0000 | 0x00060000 | 0x00040000 | 0x000A0000 |
| STAGE2_RECOVERY | 0x000A0000 | 0x00040000 | 0x000E0000 | 0x000A0000 | 0x00040000 | 0x000E0000 |
| STAGE1_PRIMARY | 0x000E0000 | 0x00040000 | 0x00120000 | 0x000E0000 | 0x00040000 | 0x00120000 |
| STAGE2_PRIMARY | 0x00120000 | 0x00040000 | 0x00160000 | 0x00120000 | 0x00040000 | 0x00160000 |
| KERNEL_RECOVERY | 0x00160000 | 0x00600000 | 0x00760000 | 0x00160000 | 0x00600000 | 0x00760000 |
| KERNEL_PRIMARY | 0x00760000 | 0x00300000 | 0x00A60000 | 0x00760000 | 0x00300000 | 0x00A60000 |
| MAIN_STAGE2 | 0x00A60000 | 0x02E00000 | 0x03860000 | 0x00A60000 | 0x02A00000 | 0x03460000 |
| SWDL | 0x03860000 | 0x00020000 | 0x03880000 | 0x03460000 | 0x00020000 | 0x03480000 |
| SPLASH | 0x03880000 | 0x00180000 | 0x03A00000 | 0x03480000 | 0x00180000 | 0x03600000 |
| SYSTEM | 0x03A00000 | 0x00200000 | 0x03C00000 | 0x03600000 | 0x00200000 | 0x03800000 |
| PERSIST | 0x03C00000 | 0x00400000 | 0x04000000 | 0x03800000 | 0x00800000 | 0x04000000 |

Both maps end at 0x04000000 (64 MiB) and share the boot-critical prefix through the start of MAIN_STAGE2. The H22 map gives MAIN_STAGE2 4 MiB more, while “Normal” gives PERSIST 4 MiB more. These arithmetic totals validate internal consistency of the table, not that any particular unit uses it.

The names suggest primary/recovery copies of stages and kernels, but that semantic interpretation is not proof of selection policy or fallback behavior. The package also carries mifs-stage1, mifs-stage2, and EFS images whose sizes should fit the relevant variant, but do not assume that every member is written to a same-named NOR region without matching the unit's partition table and firmware procedure.

## 3. MMX NAND and QNX6 app partitions

The retained wiki's “Manual Firmware Restore” identifies app.img as being written to MMX NAND partition type 177. Another wiki page shows a QNX fdisk listing for device mnand0 with:

- a primary partition of type 177, cylinders 0–357;
- an extended partition of type 5, cylinders 358–29285;
- logical partitions labelled with QNX6 types 178 and 179;
- QNX6 filesystem names/labels in the command sequence: app, boardbook, speech, gracenote, mmebackup, icab, adb, gecache, ols, navdb, media, ota.

QNX documents partition types 177, 178, and 179 as QNX6/Power-Safe partitions. The wiki command's -n size units, exact sector geometry, and partition ordering are not sufficiently clear to reconstruct a byte-exact NAND map from that page alone. The cylinder boundaries and labels are therefore recorded as historical evidence, not translated to byte offsets here.

For the MU1440 app image, the outer file is 1,438,613,504 bytes for both variants. The extractor counts 5,232 regular files, 484 directories, and 1,034 symlinks under /50/; /70/ has 5,334 files, 485 directories, and 1,034 symlinks. Regular-file byte totals are much smaller than the raw image and are not partition capacities. Do not infer unused space from those totals without the filesystem's allocation metadata.

## 4. RCC: what is known at address level

The retained wiki's manual-restore example reports the following RCC NOR write targets for one MHI2 firmware example:

| Component | Reported RCC NOR offset | Sample MU1440 update member size | Evidence strength |
| --- | ---: | ---: | --- |
| IPL | 0x00000000 | Not used in the example; page says normally not needed | Wiki restore example only |
| ifs-root | 0x00540000 | 22,611,484 bytes | Example command plus MU1440 package measurement; not validated as a universal slot size |
| efs-system | 0x01D40000 | 25,165,824 bytes | Example command plus package measurement |
| DSP | 0x03D00000 | 811,444 bytes | Example command plus package measurement |

The manual RCC device mapping shown by the same wiki uses a 64 MiB window, but it does not give a complete RCC partition table with all boundaries, redundancy, erase geometry, or reserved regions. Do not interpolate a complete layout from these four write targets.

A separate historical backup audit found RCC IFS-root Stage-2 signatures at several dump-relative offsets, most often 0x00BA0000, with additional observations at 0x00C20000, 0x00BE0000, 0x00BC0000, and 0x00C00000. Those are offsets in captured RCC backup artifacts and can vary. They are not the 0x00540000 update-write target above. An update member, a whole flash device dump, and an embedded Stage-2 reconstruction are different binary views; identify the input artifact before comparing addresses.

For an actual RCC dump parser, the safe behavior is to report candidate signature offsets and validated QNX lengths, hashes, and overlaps. Prefer live flash metadata or a per-dump sidecar when available; do not hard-code one Stage-2 offset.

## 5. Boot chain: findings and limits

### What the source/wiki evidence supports

The MMX is a Tegra-based subsystem. The retained wiki's boot-process notes describe a Tegra Boot Configuration Table (BCT), boot stages, recovery/primary kernels, and UART output. An example BCT decode reports two Stage-1 loader copies and an example load/entry address around 0x84008000. These numbers belong to that one BCT/sample, not all hardware.

The public Tegra boot-flow documentation describes the BootROM reading a BCT, using its memory configuration to initialize SDRAM, then loading a bootloader. It also documents USB recovery/RCM. Therefore a working replacement loader cannot be treated as “just write a new kernel”: it must either work within the existing trusted/accepted chain or correctly reproduce the early SoC initialization and storage/selection behavior. A download-to-IRAM path does not by itself prove that external SDRAM and all board peripherals are initialized.

The retained historical wiki also preserves a partial UART/JTAG reverse-engineering attempt: approximate Stage-1/Stage-2 sizes, a proposed primary/recovery selection marker, and kernel-loading observations. The author explicitly reports that the attempted path did not reach a working complete kernel boot; later load/configuration activity and some memory movement remained unclear. Treat this as a useful lead, not a verified boot specification.

The “qb-primary” and “qb-recovery” package members in the MU1440 sample are each 102,431 bytes and hash-identical. Their role remains unproven. Names and embedded strings are not enough to classify them as a complete replacement bootloader or even to prove where they execute.

### Quickboot: current static-analysis boundary

Quickboot is now treated as an opaque binary family rather than a parsed filesystem. The measured MU1440 primary/recovery members are byte-identical and contain the marker strings `KERNEL_PRIMARY`, `KERNEL_RECOVERY`, and `ANDROID!`. Those strings are consistent with a small boot-selection/dispatch role, but they do not establish the binary's executable format, load address, entry point, relocation model, or whether it embeds a compressed second stage.

Use `tools/binary_probe.py` on the locally extracted members to record exact marker offsets, entropy, printable strings and any ELF/QNX/ImageFS signatures. If the probe finds no standard container header, the next useful step is a raw ARM disassembly/decompiler pass in Ghidra with the load base treated as unknown evidence to be solved from call/data references rather than guessed. Until that is done, an automatic Quickboot unpacker or writer would be speculative.

The same probe is useful for other selected-but-unparsed members such as an RCC DSP binary. A raw binary should remain `PARTIAL` in the extraction manifest until a real container/executable parser validates its structure.


### Could a different bootloader be built?

In principle, reverse engineering and replacement are possible engineering goals. The existing evidence is not enough to make that a bounded or safe implementation task. The unresolved work includes:

- exact BCTs and board-specific DRAM/clock/PMIC initialization;
- boot-ROM acceptance/authentication constraints and the actual loader chain;
- complete primary/recovery selection, retries, and watchdog behavior;
- NOR/NAND geometry, erase blocks, bad-block/ECC behavior, and exact per-hardware partition tables;
- loading, decompression, relocation, and handoff semantics for each kernel/image;
- a tested recovery transport and a way to recover after a failed first-stage write.

A responsible feasibility study should begin with read-only identification and hashing of multiple unit-specific BCT/NOR/NAND backups, then correlate those with package members, serial traces, and a validated hardware matrix. Do not start with writing a replacement stage to a vehicle unit. At present the realistic conclusion is: **bootloader analysis is worthwhile; a drop-in replacement is not yet supported by the evidence or a demonstrated recovery plan.**

## 6. Recovery paths documented in the retained wiki

This is an inventory of reported recovery mechanisms, not a procedure or guarantee that every method applies to every unit.

| Recovery path | Domain | What the wiki says it can do | Important boundary |
| --- | --- | --- | --- |
| Normal firmware update/SWDL | RCC-managed package flow | Applies component updates from the update package and update metadata | Requires the update engine and enough of the existing system to remain functional |
| Boot the installed emergency IFS | RCC | IPL can select the emergency image and provide a maintenance environment | Fails if that image/partition is damaged |
| Load emergency IFS over serial ZMODEM | RCC | Wiki describes uploading the emergency IFS into RAM through the RCC IPL CLI, then booting it | Not persistent; described as dependent on a working MMX/SD-card path. The wiki documents ZMODEM, not XMODEM |
| MMX EFU | MMX | Wiki refers to a separate “red EFU”/Emergency Flash Utility route over UART | Distinct from the RCC “blue” emergency IFS; exact reachability depends on MMX boot stages and hardware |
| Tegra USB recovery / APX (RCM) | MMX | Wiki reports a Tegra USB recovery mode and a separately supplied host-side recovery workflow | BCT/tool/device compatibility and recovery authorization need separate validation |
| JTAG / external programmer | RCC or MMX | Wiki documents access and recovery discussions for wiped NOR | Board-specific wiring, voltage, pinout, and image provenance must be proven; high risk |
| Full flash restore from a known-good backup | RCC/MMX | Historical backup conventions retain raw flash images and selected metadata | Only safe when backup belongs to the exact unit/layout and integrity is verified |

A serial transfer mentioned in these pages should not be casually called XMODEM: the retained RCC emergency-upload page specifically documents ZMODEM. Likewise, the documented RCC CLI is not the same interface as Tegra BootROM USB recovery or MMX EFU.

The old wiki contains operational commands and physical-access advice. They are intentionally not reproduced here: this toolkit is for host-side inspection/export, not flashing or hardware intervention. Always treat the source page as historical, check exact train/unit/version applicability, and prefer a verified complete backup before recovery research.

## 7. Evidence classification and next useful work

### Confirmed for the MU1440 sample

- Exact member sizes and SHA-256 values are in the local extraction manifest; selected values appear in the sample table above.
- Stage-1/EIFS and Stage-2 signatures and their nested output sizes were parsed and bounded by the current toolkit.
- /50/ and /70/ mifs-stage2 decode to the same 75,529,244-byte ImageFS hash in this archive.
- app.img has the same outer byte length for both variants but different SHA-256 values and different extracted file inventories.
- RCC IFS marker is at byte offset 8 in the two sampled IFS files.

### Historical or inferred, not a universal standard

- MMX NOR address maps and H22/“Normal” distinction: retained wiki page, without a matching raw NOR dump for independent validation in this toolkit task.
- RCC write targets: one wiki recovery example, not a complete partition table.
- RCC variable Stage-2 positions: local historical backup audit, not package member offsets.
- Bootloader stage sizes, selection behavior, and loader details: incomplete wiki reverse engineering.
- app.img first-sector bytes: observed only; no universal interpretation inferred.

### Recommended next evidence acquisition

For byte-exact maps, obtain non-destructive, unit-labelled raw MMX NOR and RCC flash backups from multiple hardware variants, plus the matching BCT, firmware train/MU, and any partition-table output. Preserve source hashes, record tool and acquisition method, and compare partition boundaries against the update member hashes. A map should be upgraded from “historical report” only after at least one exact binary boundary check and preferably a second unit of the same hardware layout.

## References

Historical source pages reviewed during this study:

- Recovery: “Manual FW update /50/ vs /70/ folders” (MMX NOR tables and unit-specific caveat).
- Recovery: “Manual Firmware Restore” and “update.txt - FW update” (sample component write addresses and package update flow).
- Recovery/RCC: “How to stop IPL, enter CLI, boot ifs-emergency.ifs and restore ifs.root-stage2” and “How to boot ifs-emergency.ifs via zmodem in CLI”.
- Recovery/MMX: “MMX Tegra Boot Process Details”, “BCT Decoding”, “USB Recovery Boot mode of MMX”, “Emergency Flash Utility (EFU) via TTL cable”, and “How to prepare mifs-stage1.img and eifs.img for flashing”.
- The measured MU1440 archive is documented by hash above; its raw data remains local-only and is not bundled.

Public technical references:

- QNX, [IFS startup header fields](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.building/topic/ipl/ipl_startup_header.html).
- QNX, [QNX 6 fdisk partition types](https://www.qnx.com/developers/docs/6.5.0SP1/neutrino/utilities/f/fdisk.html).
- NVIDIA, [Tegra Boot Flow](https://http.download.nvidia.com/tegra-public-appnotes/tegra-boot-flow.html).
- NVIDIA, [Boot Configuration Table overview](https://download.nvidia.com/tegra-public-appnotes/bct-overview.html).
