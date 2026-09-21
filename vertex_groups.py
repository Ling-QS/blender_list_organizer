import bmesh
import bpy

from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Menu, Operator, Panel, PropertyGroup, UIList

from . import folders
from .common import get_active_object
from .folders import (
    FolderAddOperator,
    FolderAssignOperator,
    FolderClearSoloOperator,
    FolderCopyToSelectedOperator,
    FolderIsolateOperator,
    FolderMoveFilteredOperator,
    FolderMoveOperator,
    FolderRemoveMemberOperator,
    FolderRemoveOperator,
    FolderTagOperator,
    FolderToggleVisibilityOperator,
    FolderUnhideAllOperator,
    FolderViewSwitchOperator,
    GroupByFolderOperator,
)

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


def migrate_folder_data_to_mesh():
    """Move folder data written by versions before 1.8 from objects onto meshes.

    Vertex groups are stored on the mesh datablock (names and weights), so their
    folders belong there too - objects sharing a mesh then share one tree. The
    legacy object-level properties stay registered so this can still read them;
    the first object that has data for a mesh wins and the legacy copy is cleared.
    """
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        if obj.library is not None or obj.data.library is not None:
            # Linked data cannot be written to; the legacy folders of a linked object
            # are not ours to move onto its mesh.
            continue

        legacy_folders = obj.vgo_folders
        legacy_assignments = obj.vgo_assignments
        if not legacy_folders and not legacy_assignments:
            continue

        mesh = obj.data
        legacy_settings = obj.vgo_settings
        if not mesh.vgo_folders:
            for folder in legacy_folders:
                moved = mesh.vgo_folders.add()
                moved.name = folder.name
                moved.uid = folder.uid
                moved.visible = folder.visible
                moved.isolate = folder.isolate
            for item in legacy_assignments:
                moved_item = mesh.vgo_assignments.add()
                moved_item.vertex_group_name = item.vertex_group_name
                moved_item.folder_uids = item.folder_uids
                moved_item.folder_uid = item.folder_uid

            mesh.vgo_folder_index = max(0, min(obj.vgo_folder_index, len(mesh.vgo_folders) - 1))
            settings = mesh.vgo_settings
            settings.search = legacy_settings.search
            settings.vertex_group_name_snapshot = legacy_settings.vertex_group_name_snapshot
            settings.group_by_folder = legacy_settings.group_by_folder

        # Clearing the legacy copy keeps the file tidy and makes this run once.
        legacy_folders.clear()
        legacy_assignments.clear()
        obj.vgo_folder_index = 0
        legacy_settings.search = ""
        legacy_settings.vertex_group_name_snapshot = ""
        legacy_settings.group_by_folder = False


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
    )


class VGO_Assignment(PropertyGroup):
    vertex_group_name: StringProperty(name="Vertex Group")
    folder_uids: StringProperty(name="Folder IDs", description="Folders this group is filed in")
    folder_uid: StringProperty(name="Folder ID (legacy)", options={"HIDDEN"})


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


class VGO_UL_folders(UIList):
    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        folders.draw_folder_item(layout, context, data, KIND, item)



class VGO_UL_visible_groups(UIList):
    def filter_items(self, context, data, propname):
        obj = data
        vis = get_visibility_context(obj)
        items = getattr(data, propname)
        flags = [
            self.bitflag_filter_item if is_vertex_group_visible(obj, item.name, vis=vis) else 0
            for item in items
        ]
        if obj.data.vgo_settings.group_by_folder:
            order = folders.member_display_order(KIND.data_of(obj), KIND, items)
        else:
            order = list(range(len(items)))

        return flags, order

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        obj = data
        row = layout.row(align=True)
        group_icon = "GROUP_VERTEX" if item.index == obj.vertex_groups.active_index else "DOT"
        # The tag replaces the state icon here: a member row is tight, and the folder's tag is the
        # more useful thing to see. The folder list itself shows both side by side.
        tag = folders.get_member_tag_folder(obj.data, KIND, item.name)
        if tag is not None:
            group_icon = folders.folder_tag_icon(tag) or group_icon
        row.prop(item, "name", text="", emboss=False, icon=group_icon, translate=False)
        row.prop(
            item,
            "lock_weight",
            text="",
            icon="LOCKED" if item.lock_weight else "UNLOCKED",
            emboss=False,
        )


class VGO_OT_add_folder(FolderAddOperator, Operator):
    bl_idname = "vgo.add_folder"
    bl_label = "Add Vertex Group Folder"
    bl_description = "Create a folder for organizing vertex groups"
    kind = KIND


class VGO_OT_remove_folder(FolderRemoveOperator, Operator):
    bl_idname = "vgo.remove_folder"
    bl_label = "Remove Vertex Group Folder"
    bl_description = "Remove the selected folder; vertex groups stay on the object"
    kind = KIND


class VGO_OT_move_folder(FolderMoveOperator, Operator):
    bl_idname = "vgo.move_folder"
    bl_label = "Move Vertex Group Folder"
    bl_description = "Move the selected folder up or down in the folder list"
    kind = KIND


class VGO_OT_remove_from_folder(FolderRemoveMemberOperator, Operator):
    bl_idname = "vgo.remove_from_folder"
    bl_label = "Remove Vertex Group from Folder"
    bl_description = "Take the active vertex group out of the selected folder"
    kind = KIND


class VGO_OT_toggle_filed(FolderViewSwitchOperator, Operator):
    bl_idname = "vgo.toggle_filed"
    bl_label = "Show Filed Vertex Groups"
    bl_description = "Show or hide the vertex groups filed in at least one folder"
    kind = KIND
    attr = "show_filed"
    other_attr = "show_unfiled"


class VGO_OT_toggle_unfiled(FolderViewSwitchOperator, Operator):
    bl_idname = "vgo.toggle_unfiled"
    bl_label = "Show Unfiled Vertex Groups"
    bl_description = "Show or hide the vertex groups that are in no folder"
    kind = KIND
    attr = "show_unfiled"
    other_attr = "show_filed"


class VGO_OT_unhide_all_folders(FolderUnhideAllOperator, Operator):
    bl_idname = "vgo.unhide_all_folders"
    bl_label = "Unhide All Folders"
    bl_description = "Turn the hide switch of every folder back on"
    kind = KIND


class VGO_OT_clear_solo(FolderClearSoloOperator, Operator):
    bl_idname = "vgo.clear_solo"
    bl_label = "Clear All Solo"
    bl_description = "Drop solo from every folder"
    kind = KIND


class VGO_OT_set_folder_tag(FolderTagOperator, Operator):
    bl_idname = "vgo.set_folder_tag"
    bl_label = "Set Folder Tag"
    bl_description = "Tag the selected folder with this icon"
    kind = KIND


class VGO_PT_folder_tag_popup(Panel):
    """The folder label palette, opened as a popup from the controls row."""

    bl_label = "Folder Label"
    bl_idname = "VGO_PT_folder_tag_popup"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_ui_units_x = 14

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        if obj is None:
            return False
        data = obj.data
        return folders.is_editable(data) and folders.get_selected_folder(data, KIND) is not None

    def draw(self, context):
        folders.draw_folder_tag_popup(self.layout, KIND, context)


class VGO_OT_copy_folders_to_selected(FolderCopyToSelectedOperator, Operator):
    bl_idname = "vgo.copy_folders_to_selected"
    bl_label = "Copy Folders to Selected Objects"
    kind = KIND


# The weights copied by vgo.copy_selected_weights, kept for the session: a scratch pad for one
# edit rather than part of the file, so it survives undo the way a clipboard should.
_WEIGHT_CLIPBOARD = []


def vgo_weight_context(context):
    """What the two weight-clipboard operators need, or None when they cannot run."""
    obj = get_active_object(context)
    if obj is None or obj.mode != "EDIT" or not obj.vertex_groups:
        return None
    group = obj.vertex_groups.active
    if group is None:
        return None
    return obj, group


def vgo_deform_layer(bm):
    """The bmesh deform layer, created if the mesh has none yet.

    These operators only work in edit mode, and there a vertex group's weights live in the
    bmesh deform layer: writing through ``vertex_groups`` would land on the mesh behind the
    edit session and be lost when it ends.
    """
    layer = bm.verts.layers.deform.active
    if layer is None:
        layer = bm.verts.layers.deform.new()
    return layer


class VGO_OT_copy_selected_weights(Operator):
    bl_idname = "vgo.copy_selected_weights"
    bl_label = "Copy Weights from Selected Points"
    bl_description = "Copy the weight the selected vertices have in the active vertex group"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return vgo_weight_context(context) is not None

    def execute(self, context):
        found = vgo_weight_context(context)
        if found is None:
            return {"CANCELLED"}
        obj, group = found

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        layer = bm.verts.layers.deform.active

        weights = []
        if layer is not None:
            for vert in bm.verts:
                if not vert.select:
                    continue
                deform = vert[layer]
                if group.index in deform:
                    weights.append((vert.index, deform[group.index]))

        if not weights:
            self.report({"WARNING"}, iface_("Select vertices that have a weight first."))
            return {"CANCELLED"}

        _WEIGHT_CLIPBOARD[:] = weights
        self.report({"INFO"}, iface_("Copied the weights of {} vertices.").format(len(weights)))
        return {"FINISHED"}


class VGO_OT_paste_selected_weights(Operator):
    bl_idname = "vgo.paste_selected_weights"
    bl_label = "Paste Weights to Selected Points"
    bl_description = "Give the selected vertices the copied weights in the active vertex group"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_WEIGHT_CLIPBOARD) and vgo_weight_context(context) is not None

    def execute(self, context):
        found = vgo_weight_context(context)
        if found is None:
            return {"CANCELLED"}
        obj, group = found
        if not _WEIGHT_CLIPBOARD:
            self.report({"WARNING"}, iface_("Nothing has been copied yet."))
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        layer = vgo_deform_layer(bm)
        stored = dict(_WEIGHT_CLIPBOARD)

        applied = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            weight = stored.get(vert.index)
            if weight is None:
                continue
            vert[layer][group.index] = weight
            applied += 1

        if not applied:
            self.report(
                {"WARNING"},
                iface_("None of the selected vertices has a copied weight."),
            )
            return {"CANCELLED"}

        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, iface_("Pasted weights to {} vertices.").format(applied))
        return {"FINISHED"}


class VGO_OT_toggle_folder_visibility(FolderToggleVisibilityOperator, Operator):
    bl_idname = "vgo.toggle_folder_visibility"
    bl_label = "Toggle Folder Visibility"
    bl_description = "Show or hide this folder's vertex groups"
    kind = KIND


class VGO_OT_isolate_folder(FolderIsolateOperator, Operator):
    bl_idname = "vgo.isolate_folder"
    bl_label = "Isolate Folder"
    bl_description = "Show only this folder; click again to leave solo"
    kind = KIND


class VGO_OT_assign_to_folder(FolderAssignOperator, Operator):
    bl_idname = "vgo.assign_to_folder"
    bl_label = "Move Vertex Group to Folder"
    bl_description = "Assign the active vertex group to the selected folder"
    kind = KIND


class VGO_OT_move_filtered_to_selected_folder(FolderMoveFilteredOperator, Operator):
    bl_idname = "vgo.move_filtered_to_selected_folder"
    bl_label = "Move Filtered to Selected Folder"
    bl_description = "Move all currently filtered vertex groups to the selected folder"
    kind = KIND


class VGO_OT_toggle_group_by_folder(GroupByFolderOperator, Operator):
    bl_idname = "vgo.toggle_group_by_folder"
    bl_label = "Folder Order in List"
    bl_description = "Show the list grouped by folder without reordering the groups"
    kind = KIND


class VGO_OT_add_vertex_group(Operator):
    bl_idname = "vgo.add_vertex_group"
    bl_label = "Add Vertex Group"
    bl_description = "Create a vertex group"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        sync_vertex_group_assignment_names(obj)
        group = obj.vertex_groups.new(name="Group")
        obj.vertex_groups.active_index = group.index
        return {"FINISHED"}


class VGO_OT_remove_vertex_group(Operator):
    bl_idname = "vgo.remove_vertex_group"
    bl_label = "Remove Vertex Group"
    bl_description = "Remove the selected filtered vertex group"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        group = get_active_visible_group(obj)
        if not group:
            return {"CANCELLED"}

        obj.vertex_groups.active_index = group.index
        bpy.ops.object.vertex_group_remove()
        clean_missing_vertex_groups(obj)
        return {"FINISHED"}


class VGO_OT_move_vertex_group(Operator):
    bl_idname = "vgo.move_vertex_group"
    bl_label = "Move Vertex Group"
    bl_description = "Move the active vertex group up or down in Blender's real vertex group order"
    bl_options = {"REGISTER", "UNDO"}

    direction: StringProperty(default="UP")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        group = get_active_visible_group(obj)
        if not group:
            return {"CANCELLED"}

        obj.vertex_groups.active_index = group.index
        bpy.ops.object.vertex_group_move(direction=self.direction)
        return {"FINISHED"}


class VGO_OT_activate_pair_group(Operator):
    bl_idname = "vgo.activate_pair_group"
    bl_label = "Activate Vertex Group"
    bl_description = "Make this vertex group active"
    bl_options = {"REGISTER", "UNDO"}

    group_name: StringProperty()

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        sync_vertex_group_assignment_names(obj)
        group = get_group_by_name(obj, self.group_name)
        if not group:
            return {"CANCELLED"}

        obj.vertex_groups.active_index = group.index
        return {"FINISHED"}


class VGO_OT_lock_filtered_groups(Operator):
    bl_idname = "vgo.lock_filtered_groups"
    bl_label = "Lock Filtered Vertex Groups"
    bl_description = "Change lock state only for currently filtered vertex groups"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="LOCK")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        groups = get_visible_vertex_groups(obj)
        for group in groups:
            if self.action == "LOCK":
                group.lock_weight = True
            elif self.action == "UNLOCK":
                group.lock_weight = False
            elif self.action == "INVERT":
                group.lock_weight = not group.lock_weight

        self.report({"INFO"}, iface_("Updated {} filtered vertex groups.").format(len(groups)))
        return {"FINISHED"}


class VGO_OT_delete_filtered_groups(Operator):
    bl_idname = "vgo.delete_filtered_groups"
    bl_label = "Delete Filtered Vertex Groups"
    bl_description = "Delete only currently filtered vertex groups"
    bl_options = {"REGISTER", "UNDO"}

    only_unlocked: BoolProperty(default=False)

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        groups = list(get_visible_vertex_groups(obj))
        removed = 0
        for group in groups:
            current = get_group_by_name(obj, group.name)
            if current and (not self.only_unlocked or not current.lock_weight):
                obj.vertex_groups.remove(current)
                removed += 1

        clean_missing_vertex_groups(obj)
        self.report({"INFO"}, iface_("Deleted {} filtered vertex groups.").format(removed))
        return {"FINISHED"}


class VGO_OT_delete_filtered_empty_groups(Operator):
    bl_idname = "vgo.delete_filtered_empty_groups"
    bl_label = "Delete Filtered Empty Vertex Groups"
    bl_description = "Delete filtered vertex groups that have no assigned vertices"
    bl_options = {"REGISTER", "UNDO"}

    ignore_zero_weights: BoolProperty(
        name="Ignore Zero Weights",
        description="Treat vertices assigned with zero weight as unassigned",
        default=False,
    )

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.type != "MESH":
            return {"CANCELLED"}

        to_remove = get_empty_vertex_groups(
            obj,
            get_visible_vertex_groups(obj),
            self.ignore_zero_weights,
        )

        removed = 0
        for group in to_remove:
            current = get_group_by_name(obj, group.name)
            if current:
                obj.vertex_groups.remove(current)
                removed += 1

        clean_missing_vertex_groups(obj)
        self.report({"INFO"}, iface_("Deleted {} empty vertex groups.").format(removed))
        return {"FINISHED"}


class VGO_OT_delete_empty_groups(Operator):
    """Delete empty groups everywhere, not just the ones the filter shows."""

    bl_idname = "vgo.delete_empty_groups"
    bl_label = "Delete Empty Vertex Groups"
    bl_description = "Delete every vertex group that has no assigned vertices"
    bl_options = {"REGISTER", "UNDO"}

    ignore_zero_weights: BoolProperty(
        name="Ignore Zero Weights",
        description="Treat vertices assigned with zero weight as unassigned",
        default=False,
    )

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.type != "MESH":
            return {"CANCELLED"}

        to_remove = get_empty_vertex_groups(obj, obj.vertex_groups, self.ignore_zero_weights)

        removed = 0
        for group in to_remove:
            current = get_group_by_name(obj, group.name)
            if current:
                obj.vertex_groups.remove(current)
                removed += 1

        clean_missing_vertex_groups(obj)
        self.report({"INFO"}, iface_("Deleted {} empty vertex groups.").format(removed))
        return {"FINISHED"}


class VGO_OT_clear_filtered_groups(Operator):
    bl_idname = "vgo.clear_filtered_groups"
    bl_label = "Clear Filtered Vertex Groups"
    bl_description = "Remove all vertices from currently filtered vertex groups"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.type != "MESH":
            return {"CANCELLED"}

        vertex_indices = [vertex.index for vertex in obj.data.vertices]
        groups = get_visible_vertex_groups(obj)
        for group in groups:
            group.remove(vertex_indices)

        self.report({"INFO"}, iface_("Cleared {} filtered vertex groups.").format(len(groups)))
        return {"FINISHED"}


class VGO_OT_remove_selected_from_filtered_groups(Operator):
    bl_idname = "vgo.remove_selected_from_filtered_groups"
    bl_label = "Remove from Filtered Groups"
    bl_description = "Remove the selected vertices from currently filtered vertex groups"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        active_index = obj.vertex_groups.active_index
        count = 0
        for group in list(get_visible_vertex_groups(obj)):
            current = get_group_by_name(obj, group.name)
            if not current:
                continue
            obj.vertex_groups.active_index = current.index
            result = bpy.ops.object.vertex_group_remove_from()
            if "FINISHED" in result:
                count += 1

        obj.vertex_groups.active_index = active_index
        self.report({"INFO"}, iface_("Removed selected vertices from {} filtered groups.").format(count))
        return {"FINISHED"}


class VGO_OT_archive_deform_groups(Operator):
    bl_idname = "vgo.archive_deform_groups"
    bl_label = "Archive Deform Bone Groups"
    bl_description = "Create a deform folder and move vertex groups matching deform bones from the selected armature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return obj is not None and get_selected_armature(context, obj) is not None

    def execute(self, context):
        obj = get_active_object(context)
        armature = get_selected_armature(context, obj)
        if not obj or not armature:
            self.report({"WARNING"}, iface_("Select a mesh object and an armature at the same time."))
            return {"CANCELLED"}

        folder = get_or_create_folder(obj, iface_("Bone Deform"))
        if folder.tag == "NONE":
            # Tag the folder this creates, so the skeleton one reads at a glance.
            folder.tag = "BONE_DATA"
        deform_bone_names = {bone.name for bone in armature.data.bones if bone.use_deform}
        moved = 0

        for group in obj.vertex_groups:
            if group.name in deform_bone_names:
                folders.add_member_to_folder(obj.data, KIND, group.name, folder.uid)
                moved += 1

        self.report({"INFO"}, iface_("Archived {} deform vertex groups.").format(moved))
        return {"FINISHED"}


def draw_vertex_group_specials(self, context):
    """Our entries, appended to Blender's own vertex group specials menu.

    Only entries that make sense next to Blender's own go here. The actions that
    work on whatever the search/folder filter shows live in their own menu
    (``VGO_MT_filter_menu``), otherwise this one grows past the screen.
    """
    layout = self.layout
    layout.separator()
    layout.operator("vgo.delete_empty_groups", icon="X", text=iface_("Delete Empty Vertex Groups"))
    layout.operator("vgo.archive_deform_groups", icon="ARMATURE_DATA")
    # Both are edit-mode only; their polls grey them out everywhere else.
    layout.separator()
    layout.operator(
        "vgo.copy_selected_weights",
        icon="COPYDOWN",
        text=iface_("Copy Weights from Selected Points"),
    )
    layout.operator(
        "vgo.paste_selected_weights",
        icon="PASTEDOWN",
        text=iface_("Paste Weights to Selected Points"),
    )
    layout.separator()
    layout.operator(
        "vgo.copy_folders_to_selected",
        icon="DUPLICATE",
        text=iface_("Copy Folders to Selected Objects"),
    )


class VGO_MT_filter_menu(Menu):
    """Bulk actions that only touch what the filter shows."""

    bl_label = "Vertex Group Filter Operations"
    bl_idname = "VGO_MT_filter_menu"
    bl_description = folders.FILTER_MENU_DESCRIPTION

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "vgo.remove_selected_from_filtered_groups",
            icon="X",
            text=iface_("Remove from Filtered Groups"),
        )
        layout.operator("vgo.clear_filtered_groups", text=iface_("Clear Filtered Groups"))
        layout.operator("vgo.delete_filtered_groups", text=iface_("Delete Filtered Unlocked Groups")).only_unlocked = True
        layout.operator("vgo.delete_filtered_groups", text=iface_("Delete Filtered Groups")).only_unlocked = False
        layout.operator("vgo.delete_filtered_empty_groups", text=iface_("Delete Filtered Empty Groups"))
        layout.separator()
        layout.operator("vgo.lock_filtered_groups", icon="LOCKED", text=iface_("Lock Filtered")).action = "LOCK"
        layout.operator("vgo.lock_filtered_groups", icon="UNLOCKED", text=iface_("Unlock Filtered")).action = "UNLOCK"
        layout.operator("vgo.lock_filtered_groups", text=iface_("Invert Filtered Locks")).action = "INVERT"


def register_menus():
    if hasattr(bpy.types, NATIVE_MENU):
        getattr(bpy.types, NATIVE_MENU).append(draw_vertex_group_specials)


def unregister_menus():
    if hasattr(bpy.types, NATIVE_MENU):
        getattr(bpy.types, NATIVE_MENU).remove(draw_vertex_group_specials)


class VGO_PT_vertex_group_organizer(Panel):
    bl_label = "Vertex Group Organizer"
    bl_idname = "VGO_PT_vertex_group_organizer"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return get_active_object(context) is not None

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        mesh = obj.data
        settings = mesh.vgo_settings
        # Linked data cannot be written to. Say so instead of drawing buttons that quietly do
        # nothing, and keep drawing the rest: the folders are still worth looking at.
        if not folders.is_editable(mesh) or settings is None:
            layout.label(
                text=iface_("Linked data: folders are read-only."),
                icon="LIBRARY_DATA_DIRECTORY",
            )
        if settings is None:
            return
        visible = get_visible_vertex_groups(obj)

        split = layout.split(factor=0.36)
        left = split.column()
        right = split.column()

        row = left.row(align=True)
        row.operator(KIND.filed_op, text=iface_("Filed"), depress=settings.show_filed)
        # Solo hides the unfiled members, so the switch that normally shows them is dimmed
        # for as long as it cannot have any effect.
        unfiled_row = row.row(align=True)
        unfiled_row.enabled = not folders.has_isolated_folder(mesh, KIND)
        unfiled_row.operator(KIND.unfiled_op, text=iface_("Unfiled"), depress=settings.show_unfiled)

        left.template_list(
            "VGO_UL_folders",
            "",
            mesh,
            "vgo_folders",
            mesh,
            "vgo_folder_index",
            rows=FOLDER_ROWS,
            maxrows=folders.LIST_MAX_ROWS,
        )

        folders.draw_folder_controls(left, mesh, KIND)

        folders.draw_folder_actions(left, mesh, KIND)

        # The title goes inside the aligned column: an aligned column packs its
        # items tight, so the entries sit right under the title.
        pair_box = left.box()
        pair_col = pair_box.column(align=True)
        pair_col.label(text=iface_("Active Group"))
        pair_groups = get_active_group_pair(obj)
        if pair_groups:
            for group in pair_groups:
                row = pair_col.row(align=True)
                icon = "GROUP_VERTEX" if group.index == obj.vertex_groups.active_index else "ARROW_LEFTRIGHT"
                op = row.operator(
                    "vgo.activate_pair_group",
                    text=group.name,
                    icon=icon,
                    emboss=False,
                    depress=(group.index == obj.vertex_groups.active_index),
                    translate=False,
                )
                op.group_name = group.name
                row.prop(
                    group,
                    "lock_weight",
                    text="",
                    icon="LOCKED" if group.lock_weight else "UNLOCKED",
                    emboss=False,
                )

        if obj.vertex_groups and (
            obj.mode == "EDIT"
            or (obj.mode == "WEIGHT_PAINT" and obj.data.use_paint_mask_vertex)
        ):
            # These tools act on the active group, so they sit directly under it,
            # without a box of their own. The four buttons keep a 2x2 grid: a
            # plain row would wrap in the narrow left column.
            tools_col = left.column(align=True)
            tools = tools_col.grid_flow(
                row_major=True,
                columns=2,
                even_columns=True,
                even_rows=True,
                align=True,
            )
            tools.operator("object.vertex_group_assign", text=iface_("Assign"))
            tools.operator("object.vertex_group_remove_from", text=iface_("Remove"))
            tools.operator("object.vertex_group_select", text=iface_("Select"))
            tools.operator("object.vertex_group_deselect", text=iface_("Deselect"))
            tools_col.separator()
            tools_col.use_property_split = True
            tools_col.use_property_decorate = False
            tools_col.prop(context.scene.tool_settings, "vertex_group_weight", text=iface_("Weight"))
            tools_col.prop(context.scene.tool_settings, "use_auto_normalize", text=iface_("Auto Normalize"))

        header = right.row(align=True)
        header.prop(settings, "search", text="", icon="VIEWZOOM")
        header.prop(
            settings,
            "invert_filter",
            text="",
            icon="ARROW_LEFTRIGHT",
            toggle=True,
        )
        header.label(text=iface_("{} shown").format(len(visible)))
        list_row = right.row()
        list_row.template_list(
            "VGO_UL_visible_groups",
            "",
            obj,
            "vertex_groups",
            obj.vertex_groups,
            "active_index",
            rows=GROUP_ROWS,
            maxrows=folders.LIST_MAX_ROWS,
        )

        buttons = list_row.column(align=True)
        buttons.operator("vgo.add_vertex_group", text="", icon="ADD")
        buttons.operator("vgo.remove_vertex_group", text="", icon="REMOVE")
        buttons.separator()
        # Blender's own menu, with our entries appended: one list, shared with
        # whatever other add-ons put in it. The filter actions sit below it in
        # their own menu so neither list grows past the screen.
        buttons.menu(NATIVE_MENU, text="", icon="DOWNARROW_HLT")
        buttons.menu("VGO_MT_filter_menu", text="", icon="FILTER")
        buttons.separator()
        buttons.operator("vgo.move_vertex_group", text="", icon="TRIA_UP").direction = "UP"
        buttons.operator("vgo.move_vertex_group", text="", icon="TRIA_DOWN").direction = "DOWN"
        buttons.separator()
        # The folder-order view is a switch, not an action, so it lives here as a
        # button that stays pressed while it is on instead of in the menu.
        buttons.operator(
            "vgo.toggle_group_by_folder",
            text="",
            icon="APPEND_BLEND",
            depress=settings.group_by_folder,
        )

        if obj.vertex_groups and not visible:
            right.label(text=iface_("No vertex groups match the current filter."), icon="INFO")


classes = (
    VGO_Folder,
    VGO_Assignment,
    VGO_Settings,
    VGO_UL_folders,
    VGO_UL_visible_groups,
    VGO_OT_add_folder,
    VGO_OT_remove_folder,
    VGO_OT_move_folder,
    VGO_OT_toggle_filed,
    VGO_OT_toggle_unfiled,
    VGO_OT_unhide_all_folders,
    VGO_OT_clear_solo,
    VGO_OT_set_folder_tag,
    VGO_OT_copy_folders_to_selected,
    VGO_OT_copy_selected_weights,
    VGO_OT_paste_selected_weights,
    VGO_OT_toggle_folder_visibility,
    VGO_OT_isolate_folder,
    VGO_OT_assign_to_folder,
    VGO_OT_remove_from_folder,
    VGO_OT_move_filtered_to_selected_folder,
    VGO_OT_add_vertex_group,
    VGO_OT_remove_vertex_group,
    VGO_OT_toggle_group_by_folder,
    VGO_OT_move_vertex_group,
    VGO_OT_activate_pair_group,
    VGO_OT_lock_filtered_groups,
    VGO_OT_delete_filtered_groups,
    VGO_OT_delete_empty_groups,
    VGO_OT_delete_filtered_empty_groups,
    VGO_OT_clear_filtered_groups,
    VGO_OT_remove_selected_from_filtered_groups,
    VGO_OT_archive_deform_groups,
    VGO_MT_filter_menu,
    VGO_PT_folder_tag_popup,
    VGO_PT_vertex_group_organizer,
)
