"""Extract bone weights from Mesh in bundles 178 and 471 of 08476697.blk."""
import os
import sys

try:
    import UnityPy
except ImportError:
    print("UnityPy not installed")
    sys.exit(1)

sys.path.insert(0, r'G:\XXMI-Launcher-Portable\Mods\Mods\NilouHeadShrink\scripts')
from blb_parser import load_all_bundles

BLK = r'G:\HoYoPlay\games\Genshin Impact\GenshinImpact_Data\StreamingAssets\AssetBundles\blocks\00\08476697.blk'
all_bundles = load_all_bundles(BLK)

# Decompress bundles 178 and 471
for bundle_idx in [178, 471]:
    offset, blb3file = all_bundles[bundle_idx]
    data = blb3file.decompress_all()
    print(f"\n=== Bundle {bundle_idx} ({len(data):,} bytes) ===")
    env = UnityPy.load(data)
    for obj in env.objects:
        if obj.type.name == 'Mesh':
            try:
                mesh = obj.read()
                print(f"  Mesh '{mesh.m_Name}'")
                # Check bone data
                print(f"    m_BindPose: {len(mesh.m_BindPose)}")
                print(f"    m_BoneIndices: {mesh.m_BoneIndices.m_NumElems if hasattr(mesh, 'm_BoneIndices') else 'N/A'}")
                print(f"    m_BoneWeights: {len(mesh.m_BoneWeights)} weights")
                print(f"    m_VertexCount: {mesh.m_VertexCount}")
                # Sample bone weights
                if mesh.m_BoneWeights:
                    print(f"    First 5 vertex bone weights:")
                    for i, bw in enumerate(mesh.m_BoneWeights[:5]):
                        indices = bw.boneIndex  # 4 bone indices
                        weights = bw.weight       # 4 weights
                        print(f"      vert {i}: bones={indices} weights={weights}")
                # Sample bind poses
                if mesh.m_BindPose:
                    print(f"    First 3 bind poses:")
                    for i, bp in enumerate(mesh.m_BindPose[:3]):
                        # bp is a matrix4x4f
                        print(f"      pose[{i}]: row0={bp[0]}...")
            except Exception as e:
                print(f"  Mesh read error: {e}")
        elif obj.type.name == 'GameObject':
            try:
                go = obj.read()
                print(f"  GameObject '{go.m_Name}'")
            except Exception as e:
                print(f"  GameObject read error: {e}")
        elif obj.type.name == 'Transform':
            try:
                tr = obj.read()
                print(f"  Transform '{tr.m_GameObject.read().m_Name if tr.m_GameObject else '?'}'")
            except Exception as e:
                pass
        elif obj.type.name == 'Avatar':
            try:
                av = obj.read()
                print(f"  Avatar '{av.m_Name}'")
            except Exception as e:
                print(f"  Avatar read error: {e}")
