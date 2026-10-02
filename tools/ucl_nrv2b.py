# SPDX-License-Identifier: GPL-3.0-only
"""Bounded UCL NRV2B decoder for independent QNX IFS blocks.

The decoding flow is independently implemented for bounded MHI2 blocks. Its
NRV2B bit/code sequence was checked against Binary Refinery 0.11.2, BSD-3-Clause;
see ``dependencies/THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations


class _Input:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0
        self.bit_byte = 0
        self.bits_left = 0

    def bit(self) -> int:
        if self.bits_left == 0:
            if self.position >= len(self.data):
                raise ValueError("truncated NRV2B bitstream")
            self.bit_byte = self.data[self.position]
            self.position += 1
            self.bits_left = 8
        self.bits_left -= 1
        return (self.bit_byte >> self.bits_left) & 1

    def byte(self) -> int:
        if self.position >= len(self.data):
            raise ValueError("truncated NRV2B byte stream")
        value = self.data[self.position]
        self.position += 1
        return value


def decompress_nrv2b(data: bytes, *, max_output_bytes: int = 65536) -> bytes:
    """Decode one raw NRV2B chunk, rejecting malformed references/expansion."""
    if not data or not 0 < max_output_bytes <= 16 * 1024 * 1024:
        raise ValueError("invalid NRV2B input or output limit")
    source = _Input(data)
    output = bytearray()
    last_offset = 1

    def append_literal() -> None:
        if len(output) >= max_output_bytes:
            raise ValueError("NRV2B output exceeds configured block limit")
        output.append(source.byte())

    while source.position < len(data):
        while source.bit():
            append_literal()

        offset_code = 2 + source.bit()
        steps = 0
        while not source.bit():
            offset_code = 2 * offset_code + source.bit()
            steps += 1
            if steps > 32 or offset_code > 0xFFFFFFFF:
                raise ValueError("invalid NRV2B offset code")

        if offset_code == 2:
            offset = last_offset
        else:
            offset = (offset_code - 3) * 0x100 + source.byte()
            if offset & 0xFFFFFFFF == 0xFFFFFFFF:
                return bytes(output)
            offset += 1
            last_offset = offset

        length = source.bit()
        length = 2 * length + source.bit()
        if length == 0:
            length = 2 + source.bit()
            steps = 0
            while not source.bit():
                length = 2 * length + source.bit()
                steps += 1
                if steps > 32 or length > max_output_bytes:
                    raise ValueError("invalid NRV2B length code")
            length += 2
        length += int(offset > 0xD00)
        copy_count = length + 1
        if offset <= 0 or offset > len(output):
            raise ValueError(f"invalid NRV2B back-reference distance: {offset}")
        if len(output) + copy_count > max_output_bytes:
            raise ValueError("NRV2B output exceeds configured block limit")
        for _ in range(copy_count):
            output.append(output[-offset])

    return bytes(output)
