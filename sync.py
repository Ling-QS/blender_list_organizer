"""Shape key value mirroring: the sync box and the pass that runs it.

Split out of ``shape_keys.py``: this is a self-contained subsystem with its own
registry, its own depsgraph entry point and its own slice of the panel, and it is
the part that runs on every depsgraph update, so it is worth reading on its own.
"""

import bpy
import re
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, PointerProperty
from bpy.types import PropertyGroup

# ``key_blocks["Name"].value`` - the only data path that drives a shape key's value.
_KEY_VALUE_PATH = re.compile(r'^key_blocks\["(?P<name>.+)"\]\.value$')

# How wide the gap above the sync box is, in separators.
SYNC_BOX_GAP = 0.5

# Names of the objects whose sync switch is on, plus the values each of them had
# at the previous update. Only objects listed here are inspected, so a scene
# without sync costs nothing per depsgraph update, and only keys that actually
# changed are written to the targets.
#
# The registry is keyed by name because it has to survive a file load, but the value
# cache is keyed by pointer: renaming an object used to throw its baseline away and
# re-baseline on the next pass, which quietly swallowed one edit.
_SYNC_OBJECT_NAMES = set()
_SYNCED_VALUES = {}
# Set while the registry is known to be stale: the add-on was just registered, so
# the first depsgraph pass has to look at the file once. Reading bpy.data during
# registration itself is not allowed (Blender restricts it there).
_SYNC_REGISTRY_STALE = True
# Set while a render is running, by the render handlers the add-on registers.
_RENDERING = False


def start_render(*_args):
    """Stand the mirror down for the duration of a render.

    A render walks frames through the depsgraph, and every update would otherwise run the mirror and write
    new key values into the original data. The frame being rendered has already been evaluated from that
    data, so those writes cannot reach it - they only make the result depend on the order the frames happen
    to be asked for. Standing down is the predictable behaviour: a render plays what the file holds.
    """
    global _RENDERING
    _RENDERING = True


def finish_render(*_args):
    """Let the mirror run again once the render ends, however it ended."""
    global _RENDERING
    _RENDERING = False


def is_rendering():
    """Whether a render is running, and with it the mirror paused."""
    return _RENDERING


def request_sync_registry_rebuild():
    global _SYNC_REGISTRY_STALE
    _SYNC_REGISTRY_STALE = True


def _on_sync_toggle(settings, context):
    obj = settings.id_data
    if obj is None:
        return
    if settings.enabled:
        _SYNC_OBJECT_NAMES.add(obj.name)
    else:
        _SYNC_OBJECT_NAMES.discard(obj.name)
        _SYNCED_VALUES.pop(obj.as_pointer(), None)


class SKO_SyncSettings(PropertyGroup):
    """Per object shape key mirroring, toggled in the panel's sync box."""

    enabled: BoolProperty(
        name="Sync Shape Keys",
        description="Mirror this object's shape key edits to the target collection",
        default=False,
        update=_on_sync_toggle,
    )
    animated: BoolProperty(
        name="Sync Animated Values",
        description="Also mirror values moved by an action or a driver; off means only manual edits sync",
        default=False,
    )
    collection: PointerProperty(
        name="Target Collection",
        description="Direct members of this collection receive matching shape key values",
        type=bpy.types.Collection,
    )


def collect_syncing_objects():
    """Rebuild the sync registry, e.g. right after a file was loaded."""
    global _SYNC_REGISTRY_STALE
    _SYNC_OBJECT_NAMES.clear()
    _SYNCED_VALUES.clear()
    for obj in bpy.data.objects:
        settings = getattr(obj, "sko_sync", None)
        if settings is not None and settings.enabled:
            _SYNC_OBJECT_NAMES.add(obj.name)
    _SYNC_REGISTRY_STALE = False


def _syncing_objects():
    """Yield the objects that currently have sync switched on, in name order.

    A stable order keeps the outcome reproducible when several sources change in
    the same pass; a set would hand them out in hash order, which differs between
    Blender sessions.
    """
    for name in sorted(_SYNC_OBJECT_NAMES):
        obj = bpy.data.objects.get(name)
        if obj is None or not obj.sko_sync.enabled:
            _SYNC_OBJECT_NAMES.discard(name)
            if obj is not None:
                _SYNCED_VALUES.pop(obj.as_pointer(), None)
            continue
        yield obj


def push_shape_key_values(source, collection, values, written=None):
    """Copy ``values`` onto same-named keys of the collection's other meshes.

    ``written`` collects what was copied per object name, so the same pass can
    tell its own echoes apart from real edits.
    """
    copied = 0
    for target in collection.objects:
        if target is source or target.type != "MESH" or not target.data.shape_keys:
            continue
        if target.library is not None or target.data.library is not None:
            # A linked mesh cannot take the mirrored values.
            continue
        blocks = target.data.shape_keys.key_blocks
        for name, value in values.items():
            key = blocks.get(name)
            if key is not None and key.value != value:
                key.value = value
                copied += 1
                if written is not None:
                    written.setdefault(target.as_pointer(), {})[name] = value
    return copied


def sync_shape_key_values():
    """Mirror edits of every syncing object to that object's target collection.

    Returns how many keys were copied. Called on every depsgraph update, so each
    source is first compared against its previous values: an object nobody
    touches costs one dictionary build per update and nothing else.

    Copies made by this pass are never pushed back as if they were edits. Without
    that, a second syncing object in the same collection would hand the value it
    was just given back to everybody on the next update - overwriting whatever
    the object being edited has moved on to, which is what made a dragged slider
    snap back.
    """
    copied = 0
    if _RENDERING:
        # A render walks frames through the depsgraph; the mirror stands down for it. See start_render.
        return copied
    if _SYNC_REGISTRY_STALE:
        collect_syncing_objects()

    written = {}
    for obj in _syncing_objects():
        settings = obj.sko_sync
        pointer = obj.as_pointer()
        if settings.collection is None or not obj.data.shape_keys:
            _SYNCED_VALUES.pop(pointer, None)
            continue

        values = {key.name: key.value for key in obj.data.shape_keys.key_blocks}
        previous = _SYNCED_VALUES.get(pointer)
        _SYNCED_VALUES[pointer] = values
        if previous is None:
            continue  # first sighting of this object only baselines it

        changed = {name: value for name, value in values.items() if previous.get(name) != value}
        if changed and not settings.animated:
            # A key under an action or a driver moves by itself, so mirroring it is opt-in: this keeps a
            # manual-edit sync from quietly turning into a live mirror of somebody's animation.
            driven = animated_key_names(obj)
            if driven:
                changed = {name: value for name, value in changed.items() if name not in driven}
        echo = written.get(pointer)
        if echo:
            changed = {name: value for name, value in changed.items() if echo.get(name) != value}
        if changed:
            copied += push_shape_key_values(obj, settings.collection, changed, written)

    # Everything this pass wrote is up to date now: refresh those caches, so the
    # next pass does not mistake our own write for an edit.
    for pointer, values_written in written.items():
        cached = _SYNCED_VALUES.get(pointer)
        if cached is not None:
            cached.update(values_written)
    return copied


def animated_key_names(obj):
    """The shape keys whose value is under an action or a driver.

    Such a value moves on its own, so mirroring it is a different decision from mirroring a slider the user
    dragged - which is why the sync box has a second switch, off by default.

    Layered actions (Blender 4.4 and newer) keep their curves under layer -> strip -> channelbag; ``Action``
    has no ``fcurves`` collection of its own any more.
    """
    keys = obj.data.shape_keys
    animation = keys.animation_data if keys is not None else None
    if animation is None:
        return frozenset()

    paths = [driver.data_path for driver in animation.drivers]
    action = animation.action
    if action is not None:
        for layer in action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    paths.extend(fcurve.data_path for fcurve in channelbag.fcurves)

    return frozenset(
        match.group("name")
        for match in (_KEY_VALUE_PATH.match(path) for path in paths)
        if match is not None
    )


def draw_shape_key_sync(layout, obj):
    """The sync box at the bottom of the shape key panel."""
    settings = getattr(obj, "sko_sync", None)
    if settings is None:
        return

    # A wider gap than the rows above get: the box is a section of its own rather than another row of the
    # shape key settings.
    layout.separator(factor=SYNC_BOX_GAP)

    box = layout.box()
    row = box.row(align=True)
    # A button that stays pressed rather than a checkbox: the switch is what this box is there for, and the
    # highlight says at a glance whether the object is mirroring.
    row.operator("sko.toggle_sync", text=iface_("Sync Keys"), depress=settings.enabled)
    # Which objects are mirrored comes before what is mirrored: the target is the switch's other half, while
    # the animated values only refine it. The gap keeps those two apart as the separate choices they are.
    target_row = row.row(align=True)
    target_row.enabled = settings.enabled
    target_row.prop(settings, "collection", text="")
    row.separator()
    animated_row = row.row(align=True)
    animated_row.enabled = settings.enabled
    animated_row.prop(settings, "animated", text=iface_("Animated Sync"))
