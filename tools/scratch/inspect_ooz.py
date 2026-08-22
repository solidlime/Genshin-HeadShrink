"""Inspect OOZ DLL exports + try simple call."""
import ctypes
from pathlib import Path

OOZ = Path(r'D:\Tools\AnimeStudio\AnimeStudio-net9-1ccfbc16bf7fe625e8295bac8074ac3b1b9a065b\bin\AnimeStudio.Ooz.dll')

dll = ctypes.WinDLL(str(OOZ))
print(f'DLL loaded: {OOZ.name}, size={OOZ.stat().st_size}')

# List exports
import subprocess
r = subprocess.run(['powershell', '-NoProfile', '-Command',
    f'[System.Reflection.Assembly]::LoadFile("{OOZ}")'],
    capture_output=True, text=True)
print('PE-load via PS:', r.stdout[:200])

# Try direct win32 exports via ctypes
# GetAllExports not native; use os
# Look for Ooz_ prefix
for name in ['Ooz_Decompress', 'OozDecompress', 'OodleLZ_Decompress', 'Ooz_GetDefault']:
    try:
        f = getattr(dll, name)
        print(f'  Export: {name} -> {f}')
    except AttributeError as e:
        print(f'  NOT FOUND: {name}')

# Try loading without argtypes
try:
    func = dll.Ooz_Decompress
    func.restype = ctypes.c_int
    # Try with 0 args to see error
    import sys
    sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
    import blb_parser
    with open(r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\02050112.blk', 'rb') as f:
        data = f.read()
    f3 = blb_parser.Blb3File(data, 0)
    blk0 = f3.blocks[0]
    comp = bytearray(f3.block_data[:blk0.compressed_size])
    blb_parser.blb_decrypt(f3._hk, comp)
    src = (ctypes.c_uint8 * len(comp)).from_buffer_copy(bytes(comp))
    out = (ctypes.c_uint8 * (1 << 18))()
    # Try various arg combos
    for n_extra in range(0, 5):
        zeros = [0] * n_extra
        try:
            rc = func(ctypes.cast(src, ctypes.c_void_p), len(comp),
                      ctypes.cast(out, ctypes.c_void_p), 1<<18,
                      *zeros)
            print(f'  with {n_extra} extra args: rc={rc}')
            break
        except TypeError as e:
            if 'takes' in str(e):
                print(f'  with {n_extra} extra args: {str(e)[:80]}')
            else:
                raise
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')