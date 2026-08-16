"""Blb v3 parser. Reads .blk file, decrypts blocksInfo, decompresses blocks.
Ported from Escartem/AnimeStudio/Blb3File.cs.
"""
import struct, io
from pathlib import Path
from typing import List
import lz4.block

from blb_crypto import decrypt as blb_decrypt

COMP_NONE = 0
COMP_LZ4 = 1
COMP_LZ4HC = 2
COMP_OODLE = 9
FLAG_COMP_MASK = 0x3F


class Block:
    __slots__ = ("compressed_size", "uncompressed_size", "flags")
    def __init__(self, c, u, f):
        self.compressed_size = c
        self.uncompressed_size = u
        self.flags = f


class Blb3File:
    """Single Blb v3 bundle. .blk files are containers of multiple bundles."""
    def __init__(self, data: bytes, offset: int = 0):
        self.offset = offset
        assert data[offset:offset+4] == b"Blb\x03", f"Not Blb v3 at {offset:#x}: {data[offset:offset+4]!r}"
        size = struct.unpack("<I", data[offset+0x04:offset+0x08])[0]
        self._hk = data[offset+0x0C:offset+0x1C]
        assert len(self._hk) == 16

        bi = bytearray(data[offset+0x1C:offset+0x1C + size])
        blb_decrypt(self._hk, bi)

        bio = io.BytesIO(bytes(bi))
        def u32(): return struct.unpack("<I", bio.read(4))[0]
        def i32(): return struct.unpack("<i", bio.read(4))[0]
        def i64(): return struct.unpack("<q", bio.read(8))[0]

        self.uncompressed_size = u32()
        last_uncompressed_size = u32()
        bio.read(4)
        _blob_off = i32()
        _blob_size = u32()
        comp_type = bio.read(1)[0]
        uncomp_size = 1 << bio.read(1)[0]
        if bio.tell() % 4:
            bio.read(4 - bio.tell() % 4)

        blocks_info_count = i32()
        nodes_count = i32()

        # Each i64 is relative to its own pre-read position
        off1 = i64()
        off2 = i64()
        off3 = i64()
        base = bio.tell() - 24
        blocks_info_off = base + off1
        nodes_info_off = base + 8 + off2
        flag_info_off = base + 16 + off3

        bio.seek(blocks_info_off)
        blocks: List[Block] = []
        for i in range(blocks_info_count):
            csize = u32()
            usize = last_uncompressed_size if i == blocks_info_count - 1 else uncomp_size
            blocks.append(Block(csize, usize, comp_type))

        # First entry is cumulative; convert to per-block deltas
        for i in range(len(blocks) - 1, 0, -1):
            blocks[i].compressed_size -= blocks[i - 1].compressed_size
            blocks[i].flags = COMP_NONE if blocks[i].compressed_size == blocks[i].uncompressed_size else comp_type

        bio.seek(nodes_info_off)
        nodes = []
        for i in range(nodes_count):
            offset_v = i32()
            node_size = i32()  # ponytail: was `size`, shadowed outer bisize and broke block_data_offset
            pos = bio.tell()
            bio.seek(flag_info_off + (i // 32) * 4)
            flag = u32()
            bio.seek(pos)
            is_dir_flag = ((flag >> (i % 32)) & 1) != 0
            path_off = bio.tell() + i64()
            pos = bio.tell()
            bio.seek(path_off)
            nb = bytearray()
            while True:
                b = bio.read(1)
                if not b or b == b"\x00":
                    break
                nb += b
            name = nb.decode("utf-8", errors="replace")
            bio.seek(pos)
            nodes.append({"offset": offset_v, "size": node_size, "name": name, "is_dir": is_dir_flag == 4})

        self.blocks = blocks
        self.nodes = nodes
        self.block_data_offset = offset + 0x1C + size  # use OUTER `size` (bisize), not shadowed node_size
        self.block_data = data[self.block_data_offset:]

    def decompress_block(self, idx: int) -> bytes:
        blk = self.blocks[idx]
        start = sum(self.blocks[j].compressed_size for j in range(idx))
        compressed = bytearray(self.block_data[start:start + blk.compressed_size])
        if blk.compressed_size > 6:  # ponytail: AnimeStudio/BlbFile.cs guard
            blb_decrypt(self._hk, compressed)
        comp = blk.flags & FLAG_COMP_MASK
        if comp == COMP_NONE:
            return bytes(compressed[:blk.uncompressed_size])
        if comp in (COMP_LZ4, COMP_LZ4HC):
            return lz4.block.decompress(bytes(compressed), uncompressed_size=blk.uncompressed_size)
        if comp == COMP_OODLE:
            from oodle import oodle_decompress
            return oodle_decompress(bytes(compressed), blk.uncompressed_size)
        # Fallback: unknown type - try LZ4
        try:
            return lz4.block.decompress(bytes(compressed), uncompressed_size=blk.uncompressed_size)
        except Exception as e:
            raise RuntimeError(f"Unsupported compression type: {comp} (block {idx}); LZ4 fallback also failed: {e}")

    def decompress_all(self) -> bytes:
        out = bytearray()
        for i in range(len(self.blocks)):
            out += self.decompress_block(i)
        return bytes(out)

    def extract_node(self, node):
        """Extract a file node's content from the decompressed block stream."""
        all_data = self.decompress_all()
        return all_data[node["offset"]:node["offset"] + node["size"]]


def scan_bundles(data: bytes, min_size: int = 50, max_size: int = 500) -> list:
    """Find all valid Blb v3 bundle starts in container data."""
    out = []
    i = 0
    while i < len(data) - 8:
        if data[i:i+4] == b"Blb\x03":
            size = struct.unpack("<I", data[i+4:i+8])[0]
            if min_size <= size <= max_size:
                try:
                    out.append((i, Blb3File(data, i)))
                except Exception:
                    pass
                # Skip past this bundle's blocksInfo + compressed data (best effort)
                # Total bundle length = 0x1C + size + sum(blocks.compressed_size)
                # But we need to parse first to know lengths. Use blocksInfo offset.
                i += 0x1C + size
                continue
        i += 1
    return out


def load_all_bundles(path) -> list:
    """Load all Blb bundles from a .blk container."""
    with open(path, "rb") as f:
        data = f.read()
    return scan_bundles(data)
