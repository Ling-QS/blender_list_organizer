import bpy
from bpy.app.handlers import persistent
from bpy.props import CollectionProperty, IntProperty, PointerProperty

from . import icons, scan, shape_keys, vertex_groups
from .scan import sync_all_assignment_names  # noqa: F401  (re-exported: the API the tests and the README name)
from .shape_keys import (
    SKO_Assignment,
    SKO_Folder,
    SKO_Settings,
    SKO_SyncSettings,
)
from .translations import translations_dict
from .vertex_groups import (
    VGO_Assignment,
    VGO_Folder,
    VGO_Settings,
)


ADDON_ID = __name__

classes = vertex_groups.classes + shape_keys.classes


@persistent
def on_load_post(_dummy):
    # The sync registry lives in memory, so it has to be rebuilt for a new file. That also starts the
    # mirror timer again for the objects that had the switch on when the file was saved.
    shape_keys.collect_syncing_objects()
    # Build the per-key flag entries right away: the list classes cannot, because Blender
    # draws them in a read-only context, so their rows would come up without a pin widget
    # until the scan below happened to run.
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

    # The icons are not loaded here: a preview built this early comes back with nothing to draw. The first
    # panel draw asks for them instead, through icons.icon_kwargs().

    # bpy.data cannot be read while registering, so this only flags the registry
    # as stale; the first mirror tick rebuilds it.
    shape_keys.request_sync_registry_rebuild()

    shape_keys.register_menus()
    vertex_groups.register_menus()

    bpy.app.translations.register(ADDON_ID, translations_dict)


def unregister():
    bpy.app.translations.unregister(ADDON_ID)

    shape_keys.unregister_menus()
    vertex_groups.unregister_menus()
    icons.unregister()

    scan.cancel()
    shape_keys.cancel_mirror_timer()

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
