"""Oodle (Kraken) decompressor via oo2core_9_win64.dll (RAD Game Tools official).

Args (14):
    src, srcLen, dst, dstLen,
    fuzzSafe, checkCRC, verbosity,
    rawBuf, rawBufSize,
    callback, callbackUserData,
    decoderMemory, decoderMemorySize,
    threadPhase

Calling convention: Cdecl (CDLL).
Returns: number of bytes written to dst (>0=success, 0=fail, <0=error).
"""
import ctypes
from pathlib import Path

_OO2CORE = None
_DLL_CANDIDATES = [
    Path(__file__).parent / "oo2core_9_win64.dll",
    r"D:\Tools\oo2core_9_win64.dll",
]


def _load():
    global _OO2CORE
    if _OO2CORE is not None:
        return _OO2CORE
    for p in _DLL_CANDIDATES:
        if Path(p).exists():
            _OO2CORE = ctypes.CDLL(str(p))
            break
    if _OO2CORE is None:
        raise RuntimeError("oo2core_9_win64.dll not found")
    _OO2CORE.OodleLZ_Decompress.restype = ctypes.c_int
    _OO2CORE.OodleLZ_Decompress.argtypes = [
        ctypes.c_void_p, ctypes.c_int,            # src, srcLen
        ctypes.c_void_p, ctypes.c_int,            # dst, dstLen
        ctypes.c_int, ctypes.c_int, ctypes.c_int, # fuzzSafe, checkCRC, verbosity
        ctypes.c_void_p, ctypes.c_int,            # rawBuffer, rawBufferSize
        ctypes.c_void_p, ctypes.c_void_p,         # fpCallback, callbackUserData
        ctypes.c_void_p, ctypes.c_void_p,         # decoderMemory, decoderMemorySize
        ctypes.c_int,                             # threadPhase
    ]
    return _OO2CORE


def oodle_decompress(src: bytes, dst_size: int) -> bytes:
    """Decompress Oodle-compressed data. Returns decompressed bytes."""
    dll = _load()
    out = (ctypes.c_ubyte * dst_size)()
    src_buf = (ctypes.c_ubyte * len(src)).from_buffer_copy(src)
    n = dll.OodleLZ_Decompress(
        ctypes.cast(src_buf, ctypes.c_void_p), len(src),
        ctypes.cast(out, ctypes.c_void_p), dst_size,
        1,    # fuzzSafe
        0,    # checkCRC
        0,    # verbosity
        0, 0, # rawBuffer, rawBufferSize
        0, 0, # fpCallback, callbackUserData
        0, 0, # decoderMemory, decoderMemorySize
        3,    # threadPhase
    )
    if n < 0:
        raise RuntimeError(f"OodleLZ_Decompress returned {n} (src={len(src)}, dst={dst_size})")
    return bytes(out[:n]) if n > 0 else bytes(out)