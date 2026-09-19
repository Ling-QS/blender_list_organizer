"""Shape key value mirroring: the sync box and the pass that runs it.

Split out of ``shape_keys.py``: this is a self-contained subsystem with its own
registry, its own depsgraph entry point and its own slice of the panel, and it is
the part that runs on every depsgraph update, so it is worth reading on its own.
"""

import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, PointerProperty
from bpy.types import PropertyGroup

# Names of the objects whose sync switch is on, plus the values each of them had
# at the previous update. Only objects listed here are inspected, so a scene
# without sync costs nothing per depsgraph update, and only keys that actually
# changed are written to the targets.
_SYNC_OBJECT_NAMES = set()
_SYNCED_VALUES = {}
# Set while the registry is known to be stale: the add-on was just registered, so
# the first depsgraph pass has to look at the file once. Reading bpy.data during
# registration itself is not allowed (Blender restricts it there).
_SYNC_REGISTRY_STALE = True


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
        _SYNCED_VALUES.pop(obj.name, None)


class SKO_SyncSettings(PropertyGroup):
    """Per object shape key mirroring, toggled in the panel's sync box."""

    enabled: BoolProperty(
        name="Sync Shape Keys",
        description="Mirror this object's shape key edits to the target collection",
        default=False,
        update=_on_sync_toggle,
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
            _SYNCED_VALUES.pop(name, None)
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
                    written.setdefault(target.name, {})[name] = value
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
    if _SYNC_REGISTRY_STALE:
        collect_syncing_objects()

    written = {}
    for obj in _syncing_objects():
        settings = obj.sko_sync
        if settings.collection is None or not obj.data.shape_keys:
            _SYNCED_VALUES.pop(obj.name, None)
            continue

        values = {key.name: key.value for key in obj.data.shape_keys.key_blocks}
        previous = _SYNCED_VALUES.get(obj.name)
        _SYNCED_VALUES[obj.name] = values
        if previous is None:
            continue  # first sighting of this object only baselines it

        changed = {name: value for name, value in values.items() if previous.get(name) != value}
        echo = written.get(obj.name)
        if echo:
            changed = {name: value for name, value in changed.items() if echo.get(name) != value}
        if changed:
            copied += push_shape_key_values(obj, settings.collection, changed, written)

    # Everything this pass wrote is up to date now: refresh those caches, so the
    # next pass does not mistake our own write for an edit.
    for name, values_written in written.items():
        cached = _SYNCED_VALUES.get(name)
        if cached is not None:
            cached.update(values_written)
    return copied


def draw_shape_key_sync(layout, obj):
    """The sync box at the bottom of the shape key panel."""
    settings = getattr(obj, "sko_sync", None)
    if settings is None:
        return

    box = layout.box()
    row = box.row(align=True)
    row.prop(settings, "enabled", text=iface_("Sync Keys"))
    target_row = row.row(align=True)
    target_row.enabled = settings.enabled
    target_row.prop(settings, "collection", text="")
