"""Following renames: the scan that keeps folder records pointed at the right members.

Folder membership is stored per member *name*, because neither a ``VertexGroup`` nor a ``ShapeKey`` is an
ID that could carry a property of its own. Renaming a member therefore has to be noticed and carried over
to its record, and this module is that notice.

Two things call into it:

* the panels, which arm the throttled one-shot timer as they draw - the lists are what shows a stale name,
  and drawing is also the moment the user is looking;
* the operators that need a fresh mapping, which call :func:`sync_all_assignment_names` directly rather
  than waiting for the timer.

Nothing here runs while the add-on is idle: the timer is armed by a draw, fires once, and unregisters
itself. The scan returns early for IDs that have no assignments, so a file that never uses the add-on
costs one pass over ``bpy.data.objects`` per draw-armed fire, and nothing after the early-out.
"""

import bpy

from .shape_keys import sync_shape_key_assignment_names
from .vertex_groups import sync_vertex_group_assignment_names

# Depsgraph updates fire on every weight paint stroke, sculpt dab and playback frame, which is why this
# scan is not driven by one: a draw can arm it and the interval keeps a rename from costing a pass per
# frame while a slider is dragged.
SCAN_INTERVAL = 0.25


def sync_all_assignment_names():
    """Follow renamed or removed vertex groups and shape keys across the file."""
    changed = False
    seen_meshes = set()
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mesh = obj.data
        if mesh.name in seen_meshes:
            continue
        seen_meshes.add(mesh.name)
        changed = sync_vertex_group_assignment_names(obj) or changed
        changed = sync_shape_key_assignment_names(mesh) or changed

    if changed:
        window_manager = getattr(bpy.context, "window_manager", None)
        for window in getattr(window_manager, "windows", ()):
            for area in window.screen.areas:
                area.tag_redraw()

    return None  # one-shot: unregisters itself so an idle file costs nothing


def arm():
    """Queue the scan, unless it is already queued.

    Cheap enough to call from a draw: it is one lookup in the timer registry.
    """
    if not bpy.app.timers.is_registered(sync_all_assignment_names):
        bpy.app.timers.register(sync_all_assignment_names, first_interval=SCAN_INTERVAL)


def cancel():
    """Drop a queued scan, e.g. while the add-on unregisters."""
    if bpy.app.timers.is_registered(sync_all_assignment_names):
        bpy.app.timers.unregister(sync_all_assignment_names)
