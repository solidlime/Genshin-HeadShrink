"""Synthetic integration test for build_headshrink_mod.py
Creates a tiny but valid dump (10 verts, stride=40, 30 indices), runs the build
script via in-process call, and checks output files + .ini structure.
# ponytail: replaced PowerShell pipe hell with one Python orchestration.
"""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).parent
BUILD = SCRIPTS / "build_headshrink_mod.py"

STRIDE = 40
N_VERTS = 10
N_INDICES = 30  # 10 triangles

def make_dump(d: Path):
    # Position: verts 0-9, headers from x,y,z + 28 bytes of dummy data per vert
    pos = bytearray()
    for v in range(N_VERTS):
        x, y, z = float(v), float(v) + 0.5, float(v) - 0.25
        pos += struct.pack('<3f', x, y, z)
        pos += b'\x00' * (STRIDE - 12)  # normal/tangent/etc all-zero
    (d / "Position.buf").write_bytes(bytes(pos))

    # IB: uint32 indices 0..N_VERTS-1 cycling (validated by build)
    ib = bytearray()
    for i in range(N_INDICES):
        ib += struct.pack('<I', i % N_VERTS)
    (d / "IB.ib").write_bytes(bytes(ib))

    # hash.json
    (d / "hash.json").write_text(json.dumps({
        "position": "7a1dc890",
        "ib": "5b0a37c2",
        "blend": "b043715a",
        "texcoord": "4f12ab88",
        "vertex_limit": "9c8e7f12",
    }, indent=2))

    # Blend/Texcoord optional
    (d / "Blend.buf").write_bytes(b'\x00' * 32 * N_VERTS)
    (d / "TexCoord.buf").write_bytes(b'\x00' * 12 * N_VERTS)


def write_spec(d: Path):
    spec = {
        "vert_count": N_VERTS,
        "blend_stride": 32,
        "texcoord_stride": 12,
        "groups": [
            {"name": "Head", "vertex_range": [0, 5], "ib_range": [0, 15]},
            {"name": "Body", "vertex_range": [5, 10], "ib_range": [15, 30]},
        ],
    }
    (d / "spec.json").write_text(json.dumps(spec, indent=2))


def main():
    with tempfile.TemporaryDirectory(prefix="headshrinksynth_") as tmp:
        tmp = Path(tmp)
        dump = tmp / "dump"
        out = tmp / "mod"
        dump.mkdir()
        out.mkdir()
        make_dump(dump)
        write_spec(dump)

        res = subprocess.run(
            [sys.executable, str(BUILD),
             "--char", "Synth",
             "--dump-dir", str(dump),
             "--output-dir", str(out),
             "--spec", str(dump / "spec.json"),
             "--scale", "Head=0.5",
             "--position-stride", str(STRIDE),
             "--index-bytes", "4",
             "--blend-stride", "32",
             "--texcoord-stride", "12"],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            print("STDOUT:", res.stdout)
            print("STDERR:", res.stderr)
            raise SystemExit(f"build script failed: returncode={res.returncode}")

        # Verify outputs.
        expected = ["SynthPosition.buf", "SynthBlend.buf", "SynthTexcoord.buf",
                    "SynthHead.ib", "SynthBody.ib", "Synth.ini"]
        missing = [e for e in expected if not (out / e).exists()]
        assert not missing, f"missing files: {missing}"

        # Check .ini structure
        ini = (out / "Synth.ini").read_text(encoding="utf-8")
        for needle in [
            "; Synth",
            "[Constants]",
            "global $active = 0",
            "[TextureOverrideSynthPosition]",
            "hash = 7a1dc890",
            "[TextureOverrideSynthBlend]",
            "handling = skip",
            "[TextureOverrideSynthIB]",
            "handling = skip",
            "[TextureOverrideSynthHead]",
            "match_first_index = 0",
            "drawindexed = 15, 0, 0",
            "[TextureOverrideSynthBody]",
            "match_first_index = 15",
            "drawindexed = 15, 0, 0",
            "[ResourceSynthPosition]",
            "stride = 40",
            "[ResourceSynthHeadIB]",
            "format = DXGI_FORMAT_R32_UINT",
            "[Present]",
            "post $active = 0",
        ]:
            assert needle in ini, f"missing in .ini: {needle}"
        assert ini.count("[Constants]") == 1, "duplicate [Constants]"
        assert ini.count("[Present]") == 1, "duplicate [Present]"
        assert "VertexLimitRaise" not in ini, "VertexLimitRaise must be removed"
        assert "drawindexed = auto" not in ini, "drawindexed=auto must be removed"

        # Confirm scale math: Head verts x=0..4 around bbox center 2.0 with scale 0.5
        # -> new_x = 2 + (x-2)*0.5 -> {1.0, 1.5, 2.0, 2.5, 3.0}. Body verts untouched.
        pos_after = (out / "SynthPosition.buf").read_bytes()
        expected_head_x = [1.0, 1.5, 2.0, 2.5, 3.0]
        for i, exp in enumerate(expected_head_x):
            x = struct.unpack_from('<3f', pos_after, i * STRIDE)[0]
            assert abs(x - exp) < 1e-5, f"v{i}.x expected {exp}, got {x}"
        # v5..v9 (Body) x should be exactly the original {5..9}, untouched
        for i in range(5, N_VERTS):
            x = struct.unpack_from('<3f', pos_after, i * STRIDE)[0]
            assert x == float(i), f"v{i}.x expected {float(i)}, got {x}"
        # Stride preserved: bytes 12..40 untouched (zeroes from creation).
        v0_after_12 = pos_after[12:40]
        assert v0_after_12 == b'\x00' * 28, "stride bytes 12..40 were modified (should be passthrough)"

        print(f"OK: synth dump -> {len(expected)} files written, .ini structure matches, scale math correct")


if __name__ == "__main__":
    main()
