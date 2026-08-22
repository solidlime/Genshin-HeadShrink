"""Shared minimal bpy stub for headless unit tests.

Both test modules (test_preview_adjust.py / test_units_ui.py) import this
unconditionally so the stub is identical regardless of import order. The old
per-file ``if 'bpy' not in sys.modules`` guards raced on whichever file was
imported first and produced order-dependent failures.

Only what class definitions and headless operator tests need is provided;
tests that require specific state assign it on these objects directly.
"""
import types


def _prop_fn(*args, **kwargs):
    return None


class _Base:
    """Base for PropertyGroup/Operator/etc.

    Carries a recording ``report()`` so headless operator tests can assert
    on reported messages (op._reports) without real Blender.
    """

    def __init__(self):
        self._reports = []

    def report(self, level, msg):
        self._reports.append((set(level), msg))


bpy = types.ModuleType('bpy')

bpy.props = types.SimpleNamespace(
    StringProperty=_prop_fn, FloatVectorProperty=_prop_fn,
    EnumProperty=_prop_fn, PointerProperty=_prop_fn,
    CollectionProperty=_prop_fn, PropertyGroup=_Base,
    FloatProperty=_prop_fn, BoolProperty=_prop_fn,
    IntProperty=_prop_fn,
)

bpy.types = types.SimpleNamespace(
    PropertyGroup=_Base, Operator=_Base, Panel=_Base, UIList=_Base,
    AddonPreferences=_Base)

bpy.utils = types.SimpleNamespace(
    register_class=lambda c: None, unregister_class=lambda c: None)

bpy.path = types.SimpleNamespace(abspath=lambda p: p)

# dict-like collections (.get) + list-like objects; tests may reassign either.
bpy.data = types.SimpleNamespace(objects=[], collections={})

bpy.context = types.SimpleNamespace()

bpy.app = types.SimpleNamespace(
    timers=types.SimpleNamespace(register=lambda fn, **kw: None))


def reset():
    """Restore mutable stub state to pristine (cross-test-file isolation).

    Call from ``setUpModule()`` in each test file so leaked assignments
    (e.g. ``hs.bpy.data.collections = ...``) from a previously imported
    test module cannot change behavior of this file's tests.
    """
    bpy.data = types.SimpleNamespace(objects=[], collections={})
    bpy.context = types.SimpleNamespace()
    bpy.app = types.SimpleNamespace(
        timers=types.SimpleNamespace(register=lambda fn, **kw: None))
