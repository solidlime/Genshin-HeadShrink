"""Quick inspect Mona's Position.buf format."""
import struct, os

p = r'G:\XXMI-Launcher-Portable\Mods\Mods\MonaHeadShrink\MonaPosition.buf'
b = open(p, 'rb').read()
print(f'size = {len(b)} bytes, stride=40, vert_count = {len(b)//40}')

# vertex 0: first 12 bytes = xyz (float32x3), next bytes = ?
print(f'\nv0 xyz: {struct.unpack("<3f", b[0:12])}')
print(f'v0 bytes 12..24 (hex): {b[12:24].hex()}')
print(f'v0 bytes 24..40 (hex): {b[24:40].hex()}')

# try interpreting as float32
v0_post_xyz = b[12:40]
floats = struct.unpack('<7f', v0_post_xyz)
print(f'v0 post-xyz as 7 floats: {floats}')

# u32 / u8 patterns
print(f'v0 bytes 12..16 u32: {struct.unpack("<2I", b[12:20])}')

# Last vertex
N = len(b) // 40
print(f'\nLast vert (v{N-1}): xyz = {struct.unpack("<3f", b[-40:-28])}')
