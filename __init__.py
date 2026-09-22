import bpy
from bpy.app.handlers import persistent
from bpy.props import CollectionProperty, IntProperty, PointerProperty

from . import shape_keys, vertex_groups
from .shape_keys import (
    SKO_Assignment,
    SKO_Folder,
    SKO_Settings,
    SKO_SyncSettings,
    sync_shape_key_assignment_names,
)
from .translations import translations_dict
from .vertex_groups import (
    VGO_Assignment,
    VGO_Folder,
    VGO_Settings,
    sync_vertex_group_assignment_names,
)


ADDON_ID = __name__

# Depsgraph updates fire on every weight paint stroke, sculpt dab and playback
# frame, but the rename-following scan only has to keep up with edits a human
# made. The handler therefore only queues a one-shot timer; the scan itself is
# throttled to this interval.
SYNC_INTERVAL = 0.25

classes = vertex_groups.classes + shape_keys.classes


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


@persistent
def on_depsgraph_update(_scene, _depsgraph):
    # Shape key mirroring has to feel immediate, so it runs inline for the
    # objects that opted in; the folder name scan is throttled through a
    # one-shot timer instead. Rationale, measurements and the alternatives that
    # were rejected live in README > "Why the depsgraph handler exists".
    shape_keys.sync_shape_key_values()
    if not bpy.app.timers.is_registered(sync_all_assignment_names):
        bpy.app.timers.register(sync_all_assignment_names, first_interval=SYNC_INTERVAL)


@persistent
def on_load_post(_dummy):
    # The sync registry lives in memory, so it has to be rebuilt for a new file.
    shape_keys.collect_syncing_objects()
    # Build the per-key flag entries right away: the list classes cannot, because Blender
    # draws them in a read-only context, so their rows would come up without a pin widget
    # until the throttled scan below happened to run.
    sync_all_assignment_names()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Vertex group folders live on the mesh, like the groups themselves do.
    bpy.types.Mesh.vgo_folders = CollectionProperty(type=VGO_Folder)
    bpy.types.Mesh.vgo_assignments = CollectionProperty(type=VGO_Assignment)
    bpy.types.Mesh.vgo_settings = PointerProperty(type=VGO_Settings)
    bpy.types.Mesh.vgo_folder_index = IntProperty(default=0)

    bpy.types.Mesh.sko_folders = CollectionProperty(type=SKO_Folder)
    bpy.types.Mesh.sko_assignments = CollectionProperty(type=SKO_Assignment)
    bpy.types.Mesh.sko_settings = PointerProperty(type=SKO_Settings)
    bpy.types.Mesh.sko_folder_index = IntProperty(default=0)

    bpy.types.Object.sko_sync = PointerProperty(type=SKO_SyncSettings)

    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    if on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_post)

    # The mirror stands down while a render runs, and comes back however the render ended.
    for handler, handlers in (
        (shape_keys.start_render, bpy.app.handlers.render_init),
        (shape_keys.finish_render, bpy.app.handlers.render_complete),
        (shape_keys.finish_render, bpy.app.handlers.render_cancel),
    ):
        if handler not in handlers:
            handlers.append(handler)

    # bpy.data cannot be read while registering, so this only flags the registry
    # as stale; the first depsgraph pass rebuilds it.
    shape_keys.request_sync_registry_rebuild()

    shape_keys.register_menus()
    vertex_groups.register_menus()

    bpy.app.translations.register(ADDON_ID, translations_dict)


def unregister():
    bpy.app.translations.unregister(ADDON_ID)

    shape_keys.unregister_menus()
    vertex_groups.unregister_menus()

    if bpy.app.timers.is_registered(sync_all_assignment_names):
        bpy.app.timers.unregister(sync_all_assignment_names)

    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    if on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_post)

    for handler, handlers in (
        (shape_keys.start_render, bpy.app.handlers.render_init),
        (shape_keys.finish_render, bpy.app.handlers.render_complete),
        (shape_keys.finish_render, bpy.app.handlers.render_cancel),
    ):
        if handler in handlers:
            handlers.remove(handler)

    del bpy.types.Object.sko_sync

    del bpy.types.Mesh.vgo_folder_index
    del bpy.types.Mesh.vgo_settings
    del bpy.types.Mesh.vgo_assignments
    del bpy.types.Mesh.vgo_folders

    del bpy.types.Mesh.sko_folder_index
    del bpy.types.Mesh.sko_settings
    del bpy.types.Mesh.sko_assignments
    del bpy.types.Mesh.sko_folders

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
