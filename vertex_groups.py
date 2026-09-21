import bmesh

from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import PropertyGroup

from . import folders

KIND = folders.VERTEX_GROUPS
# Blender's own specials menu for vertex groups: our entries are appended to it
# and the panel's menu button opens it, so foreign items added there show up too.
NATIVE_MENU = "MESH_MT_vertex_group_context_menu"
# Starting height of the two lists in the panel, in rows.
FOLDER_ROWS = 5
GROUP_ROWS = 16


# The folder, assignment and visibility machinery is shared with the shape key
# organizer (see folders.py); the wrappers below keep the vertex group
# vocabulary that the panels and operators use. They take an object, because that
# is how Blender exposes vertex groups, and hand the mesh to the shared layer:
# vertex group names, weights and therefore our folders all live on the mesh, so
# objects that share a mesh share one folder tree.


def get_visible_vertex_groups(obj):
    return folders.get_visible_members(KIND.data_of(obj), KIND)


def get_visible_vertex_group_names(obj):
    return folders.get_visible_member_names(KIND.data_of(obj), KIND)


def get_visibility_context(obj):
    return folders.get_visibility_context(KIND.data_of(obj), KIND)


def is_vertex_group_visible(obj, group_name, vis=None):
    return folders.is_member_visible(KIND.data_of(obj), KIND, group_name, vis=vis)


def get_vertex_group_folder_uids(obj, group_name):
    return folders.get_member_folder_uids(KIND.data_of(obj), KIND, group_name)


def get_selected_folder(obj):
    return folders.get_selected_folder(KIND.data_of(obj), KIND)


def get_or_create_folder(obj, name):
    return folders.get_or_create_folder(KIND.data_of(obj), KIND, name)


def get_active_visible_group(obj):
    return folders.get_active_visible_member(KIND.data_of(obj), KIND, obj)


def get_active_group_pair(obj):
    return folders.get_active_member_pair(KIND.data_of(obj), KIND, obj)


def sync_vertex_group_assignment_names(obj):
    return folders.sync_assignment_names(KIND.data_of(obj), KIND)


def clean_missing_vertex_groups(obj):
    folders.clean_missing_assignments(KIND.data_of(obj), KIND)


def get_group_by_name(obj, name):
    for group in obj.vertex_groups:
        if group.name == name:
            return group
    return None


def get_selected_armature(context, mesh_obj):
    for obj in context.selected_objects:
        if obj != mesh_obj and obj.type == "ARMATURE":
            return obj
    return None


def get_empty_vertex_groups(obj, groups, ignore_zero_weights):
    """Subset of ``groups`` with no assigned vertices.

    One bmesh pass over the deform layer that stops as soon as every group has
    been seen, instead of walking every vertex through RNA.
    """
    targets = {group.index for group in groups}
    if not targets:
        return []

    seen = set()
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        layer = bm.verts.layers.deform.active
        if layer is not None:
            for vertex in bm.verts:
                for index, weight in vertex[layer].items():
                    if index not in targets or index in seen:
                        continue
                    if ignore_zero_weights and weight == 0.0:
                        continue
                    seen.add(index)
                if len(seen) == len(targets):
                    break
    finally:
        bm.free()

    return [group for group in groups if group.index not in seen]


def update_folder_tag(folder, context):
    """Repaint as soon as a tag changes.

    The tag is written from a popup, and the lists that draw it are elsewhere on screen: without this the new
    icon only appeared once something else happened to redraw the editor.
    """
    folders.tag_redraw()


class VGO_Folder(PropertyGroup):
    uid: StringProperty(name="Folder ID")
    name: StringProperty(name="Name", default="")
    visible: BoolProperty(
        name="Visible",
        description="Show this folder's vertex groups; a soloed folder ignores it",
        default=True,
    )
    isolate: BoolProperty(
        name="Isolate",
        description="Show only this folder; click again to leave solo",
        default=False,
    )
    tag: EnumProperty(
        name="Label",
        description="Icon that tags this folder and the groups filed in it",
        items=folders.folder_tag_items(),
        default="NONE",
        update=update_folder_tag,
    )


class VGO_Assignment(PropertyGroup):
    vertex_group_name: StringProperty(name="Vertex Group")
    folder_uids: StringProperty(name="Folder IDs", description="Folders this group is filed in")


class VGO_Settings(PropertyGroup):
    search: StringProperty(name="Search", description="Filter vertex groups by name")
    invert_filter: BoolProperty(
        name="Invert Filter",
        description="Show the groups the search hides, and hide the ones it matches",
        default=False,
    )
    vertex_group_name_snapshot: StringProperty(name="Vertex Group Snapshot", default="", options={"HIDDEN"})
    group_by_folder: BoolProperty(
        name="Folder Order",
        description="Show the list grouped by folder without reordering the groups",
        default=False,
    )
    show_filed: BoolProperty(
        name="Filed",
        description="Show the vertex groups that are filed in at least one folder",
        default=True,
    )
    show_unfiled: BoolProperty(
        name="Unfiled",
        description="Show the vertex groups that are in no folder",
        default=True,
    )


from .vertex_group_list import (  # noqa: F401  (re-exported names)
    VGO_UL_folders,
    VGO_UL_visible_groups,
)
from .vertex_group_ops import (  # noqa: F401  (re-exported names)
    _WEIGHT_CLIPBOARD,
    VGO_OT_add_folder,
    VGO_OT_remove_folder,
    VGO_OT_move_folder,
    VGO_OT_remove_from_folder,
    VGO_OT_toggle_filed,
    VGO_OT_toggle_unfiled,
    VGO_OT_unhide_all_folders,
    VGO_OT_clear_solo,
    VGO_OT_set_folder_tag,
    VGO_PT_folder_tag_popup,
    VGO_OT_copy_folders_to_selected,
    VGO_OT_copy_selected_weights,
    VGO_OT_paste_selected_weights,
    VGO_OT_toggle_folder_visibility,
    VGO_OT_isolate_folder,
    VGO_OT_assign_to_folder,
    VGO_OT_move_filtered_to_selected_folder,
    VGO_OT_toggle_group_by_folder,
    VGO_OT_add_vertex_group,
    VGO_OT_remove_vertex_group,
    VGO_OT_move_vertex_group,
    VGO_OT_activate_pair_group,
    VGO_OT_scroll_to_active_group,
    VGO_OT_lock_filtered_groups,
    VGO_OT_delete_filtered_groups,
    VGO_OT_delete_filtered_empty_groups,
    VGO_OT_delete_empty_groups,
    VGO_OT_clear_filtered_groups,
    VGO_OT_remove_selected_from_filtered_groups,
    VGO_OT_archive_deform_groups,
    vgo_weight_context,
    vgo_deform_layer,
)
from .vertex_group_panel import (  # noqa: F401  (re-exported names)
    VGO_MT_filter_menu,
    VGO_PT_vertex_group_organizer,
    draw_vertex_group_specials,
    register_menus,
    unregister_menus,
    classes,
)
