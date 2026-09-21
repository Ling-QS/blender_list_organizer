"""The vertex group operators: one class per user action.

Split out of the organizer's model module. Each validates its context and then drives the model.
"""

import bmesh

from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator, Panel

from .. import folders
import bpy
from ..common import get_active_object, request_list_scroll, scroll_targets
from ..folders import (
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

# Taken from the model module at import time: the package imports that one first, so it has run to the end.
from .model import (
    KIND,
    clean_missing_vertex_groups,
    get_active_visible_group,
    get_empty_vertex_groups,
    get_group_by_name,
    get_or_create_folder,
    get_selected_armature,
    get_visible_vertex_groups,
    sync_vertex_group_assignment_names,
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
    """The folder label palette, opened as a floating popup from the controls row.

    ``INSTANCED`` is what keeps it floating: without it Blender also lists the panel in the Properties editor,
    so it shows up permanently under the organizer as well as when called.
    """

    bl_label = "Folder Label"
    bl_idname = "VGO_PT_folder_tag_popup"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_options = {"INSTANCED"}

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


class VGO_OT_scroll_to_active_group(Operator):
    bl_idname = "vgo.scroll_to_active_group"
    bl_label = "Scroll to Active Group"
    bl_description = "Bring the active vertex group into view in the list"
    bl_options = {"REGISTER"}

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or not obj.vertex_groups:
            return {"CANCELLED"}
        active = obj.vertex_groups.active
        if active is None:
            return {"CANCELLED"}

        # Nothing is written to the object and no row is hidden: the list is handed stand-in active rows
        # for a draw each and scrolls itself. See request_list_scroll.
        rows = scroll_targets(active.index, len(obj.vertex_groups))
        request_list_scroll(obj.as_pointer(), context.area, obj.data.vgo_settings, rows)
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
