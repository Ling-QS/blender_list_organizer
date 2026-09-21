"""The shape key operators: one class per user action.

Split out of ``shape_keys.py``. Each is a thin operator that validates its context and then drives the
model module; the folder operators live in ``shape_key_folders.py`` next door.
"""

from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy.types import Operator, Panel

from . import folders
import bpy
from .common import get_active_object, request_list_scroll
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

# Taken from the model module at import time: ``shape_keys`` imports these back at the end of its own
# file, so the cycle resolves there.
from .shape_keys import (
    KIND,
    sko_clean_missing_shape_keys,
    sko_get_active_visible_key,
    sko_get_key_by_name,
    sko_get_reference_key,
    sko_get_visible_shape_keys,
    sko_is_basis,
    sko_is_shape_key_visible,
    sko_key_index,
    sync_shape_key_assignment_names,
)


class SKO_OT_add_folder(FolderAddOperator, Operator):
    bl_idname = "sko.add_folder"
    bl_label = "Add Shape Key Folder"
    bl_description = "Create a folder for organizing shape keys"
    kind = KIND


class SKO_OT_remove_folder(FolderRemoveOperator, Operator):
    bl_idname = "sko.remove_folder"
    bl_label = "Remove Shape Key Folder"
    bl_description = "Remove the selected folder; shape keys stay on the mesh"
    kind = KIND


class SKO_OT_move_folder(FolderMoveOperator, Operator):
    bl_idname = "sko.move_folder"
    bl_label = "Move Shape Key Folder"
    bl_description = "Move the selected folder up or down in the folder list"
    kind = KIND


class SKO_OT_remove_from_folder(FolderRemoveMemberOperator, Operator):
    bl_idname = "sko.remove_from_folder"
    bl_label = "Remove Shape Key from Folder"
    bl_description = "Take the active shape key out of the selected folder"
    kind = KIND


class SKO_OT_toggle_filed(FolderViewSwitchOperator, Operator):
    bl_idname = "sko.toggle_filed"
    bl_label = "Show Filed Shape Keys"
    bl_description = "Show or hide the shape keys filed in at least one folder"
    kind = KIND
    attr = "show_filed"
    other_attr = "show_unfiled"


class SKO_OT_toggle_unfiled(FolderViewSwitchOperator, Operator):
    bl_idname = "sko.toggle_unfiled"
    bl_label = "Show Unfiled Shape Keys"
    bl_description = "Show or hide the shape keys that are in no folder"
    kind = KIND
    attr = "show_unfiled"
    other_attr = "show_filed"


class SKO_OT_unhide_all_folders(FolderUnhideAllOperator, Operator):
    bl_idname = "sko.unhide_all_folders"
    bl_label = "Unhide All Folders"
    bl_description = "Turn the hide switch of every folder back on"
    kind = KIND


class SKO_OT_clear_solo(FolderClearSoloOperator, Operator):
    bl_idname = "sko.clear_solo"
    bl_label = "Clear All Solo"
    bl_description = "Drop solo from every folder"
    kind = KIND


class SKO_OT_set_folder_tag(FolderTagOperator, Operator):
    bl_idname = "sko.set_folder_tag"
    bl_label = "Set Folder Tag"
    bl_description = "Tag the selected folder with this icon"
    kind = KIND


class SKO_PT_folder_tag_popup(Panel):
    """The folder label palette, opened as a floating popup from the controls row.

    ``INSTANCED`` is what keeps it floating: without it Blender also lists the panel in the Properties editor,
    so it shows up permanently under the organizer as well as when called.
    """

    bl_label = "Folder Label"
    bl_idname = "SKO_PT_folder_tag_popup"
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


class SKO_OT_copy_folders_to_selected(FolderCopyToSelectedOperator, Operator):
    bl_idname = "sko.copy_folders_to_selected"
    bl_label = "Copy Folders to Selected Objects"
    kind = KIND


class SKO_OT_toggle_folder_visibility(FolderToggleVisibilityOperator, Operator):
    bl_idname = "sko.toggle_folder_visibility"
    bl_label = "Toggle Folder Visibility"
    bl_description = "Show or hide this folder's shape keys"
    kind = KIND


class SKO_OT_isolate_folder(FolderIsolateOperator, Operator):
    bl_idname = "sko.isolate_folder"
    bl_label = "Isolate Folder"
    bl_description = "Show only this folder; click again to leave solo"
    kind = KIND


class SKO_OT_assign_to_folder(FolderAssignOperator, Operator):
    bl_idname = "sko.assign_to_folder"
    bl_label = "Move Shape Key to Folder"
    bl_description = "Assign the active shape key to the selected folder"
    kind = KIND


class SKO_OT_move_filtered_to_selected_folder(FolderMoveFilteredOperator, Operator):
    bl_idname = "sko.move_filtered_to_selected_folder"
    bl_label = "Move Filtered to Selected Folder"
    bl_description = "Move all currently filtered shape keys to the selected folder"
    kind = KIND


class SKO_OT_add_shape_key(Operator):
    bl_idname = "sko.add_shape_key"
    bl_label = "Add Shape Key"
    bl_description = "Create a shape key"
    bl_options = {"REGISTER", "UNDO"}

    from_mix: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return obj is not None and obj.mode != "EDIT"

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        sync_shape_key_assignment_names(mesh)
        # Blender's own operator names the keys the way its Shape Keys panel does
        # ("Basis" first, then "Key 1", "Key 2", ...); the Object API would fall
        # back to its "Key" default and produce "Key", "Key.001", ...
        if bpy.ops.object.shape_key_add(from_mix=self.from_mix) != {"FINISHED"}:
            return {"CANCELLED"}
        if not mesh.shape_keys or not mesh.shape_keys.key_blocks:
            return {"CANCELLED"}
        key = mesh.shape_keys.key_blocks[-1]

        obj.active_shape_key_index = sko_key_index(mesh, key)
        sync_shape_key_assignment_names(mesh)
        return {"FINISHED"}


class SKO_OT_remove_shape_key(Operator):
    bl_idname = "sko.remove_shape_key"
    bl_label = "Remove Shape Key"
    bl_description = "Remove the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return obj is not None and obj.mode != "EDIT"

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        sync_shape_key_assignment_names(mesh)
        key = obj.active_shape_key
        if not key:
            return {"CANCELLED"}
        # The basis key goes too, exactly like Blender's own operator: the next key
        # becomes the basis and is baked into the mesh. It is never listed, so the
        # visibility filter cannot be applied to it - but every other key still has
        # to be visible, which is what keeps a filtered-out key from being deleted
        # by accident.
        if not sko_is_basis(mesh, key) and not sko_is_shape_key_visible(mesh, key.name):
            return {"CANCELLED"}

        obj.active_shape_key_index = sko_key_index(mesh, key)
        obj.shape_key_remove(key)
        sko_clean_missing_shape_keys(mesh)
        sync_shape_key_assignment_names(mesh)
        return {"FINISHED"}


class SKO_OT_move_shape_key(Operator):
    bl_idname = "sko.move_shape_key"
    bl_label = "Move Shape Key"
    bl_description = "Move the active shape key up or down"
    bl_options = {"REGISTER", "UNDO"}

    direction: StringProperty(default="UP")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        key = sko_get_active_visible_key(obj)
        if not key:
            return {"CANCELLED"}
        if sko_is_basis(mesh, key):
            return {"CANCELLED"}

        obj.active_shape_key_index = sko_key_index(mesh, key)
        bpy.ops.object.shape_key_move(type=self.direction)
        return {"FINISHED"}


class SKO_OT_scroll_to_active_key(Operator):
    bl_idname = "sko.scroll_to_active_key"
    bl_label = "Scroll to Active Key"
    bl_description = "Bring the active shape key into view in the list"
    bl_options = {"REGISTER"}

    def execute(self, context):
        obj = get_active_object(context)
        mesh = obj.data if obj is not None else None
        if mesh is None or mesh.shape_keys is None:
            return {"CANCELLED"}
        if obj.active_shape_key is None:
            return {"CANCELLED"}

        # Nothing is written to the object: the list scrolls itself, on the next draw, by showing one
        # row less for that frame. See apply_scroll_request for why that is what it takes. The list is
        # drawn for the key collection, so that is what the request is filed under.
        request_list_scroll(mesh.shape_keys.as_pointer())
        return {"FINISHED"}


class SKO_OT_activate_pair_key(Operator):
    bl_idname = "sko.activate_pair_key"
    bl_label = "Activate Shape Key"
    bl_description = "Make this shape key active"
    bl_options = {"REGISTER", "UNDO"}

    key_name: StringProperty()

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        sync_shape_key_assignment_names(mesh)
        key = sko_get_key_by_name(mesh, self.key_name)
        if not key:
            return {"CANCELLED"}

        obj.active_shape_key_index = sko_key_index(mesh, key)
        return {"FINISHED"}


class SKO_OT_toggle_basis_flag(Operator):
    """Mute or lock the basis key from the row that shows it above the list.

    The basis row draws mute and lock as operators instead of ``prop`` widgets so
    the whole row can carry the "pressed" highlight while the basis is the active
    key: ``UILayout.prop`` has no ``depress``, so a property button would stay
    flat beside a highlighted name button. The icon still shows the state.
    """

    bl_idname = "sko.toggle_basis_flag"
    bl_label = "Toggle Basis Key Flag"
    bl_description = "Mute or lock the basis shape key"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="MUTE")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.type != "MESH" or not obj.data.shape_keys:
            return {"CANCELLED"}

        basis = obj.data.shape_keys.key_blocks[0]
        if self.action == "LOCK":
            if not hasattr(basis, "lock_shape"):
                return {"CANCELLED"}
            basis.lock_shape = not basis.lock_shape
        else:
            basis.mute = not basis.mute
        return {"FINISHED"}


class SKO_OT_lock_filtered_keys(Operator):
    bl_idname = "sko.lock_filtered_keys"
    bl_label = "Lock Filtered Shape Keys"
    bl_description = "Change lock state only for currently filtered shape keys"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="LOCK")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        keys = sko_get_visible_shape_keys(obj.data)
        updated = 0
        for key in keys:
            if not hasattr(key, "lock_shape"):
                continue
            if self.action == "LOCK":
                key.lock_shape = True
            elif self.action == "UNLOCK":
                key.lock_shape = False
            elif self.action == "INVERT":
                key.lock_shape = not key.lock_shape
            updated += 1

        self.report({"INFO"}, iface_("Updated {} filtered shape keys.").format(updated))
        return {"FINISHED"}


class SKO_OT_mute_filtered_keys(Operator):
    bl_idname = "sko.mute_filtered_keys"
    bl_label = "Mute Filtered Shape Keys"
    bl_description = "Change mute state only for currently filtered shape keys"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="MUTE")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        keys = sko_get_visible_shape_keys(obj.data)
        for key in keys:
            if self.action == "MUTE":
                key.mute = True
            elif self.action == "UNMUTE":
                key.mute = False
            elif self.action == "INVERT":
                key.mute = not key.mute

        self.report({"INFO"}, iface_("Updated {} filtered shape keys.").format(len(keys)))
        return {"FINISHED"}


class SKO_OT_delete_filtered_keys(Operator):
    bl_idname = "sko.delete_filtered_keys"
    bl_label = "Delete Filtered Shape Keys"
    bl_description = "Delete only currently filtered shape keys"
    bl_options = {"REGISTER", "UNDO"}

    only_unlocked: BoolProperty(default=False)

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        keys = list(sko_get_visible_shape_keys(mesh))
        removed = 0
        for key in keys:
            current = sko_get_key_by_name(mesh, key.name)
            if not current:
                continue
            if sko_is_basis(mesh, current):
                continue
            if self.only_unlocked and hasattr(current, "lock_shape") and current.lock_shape:
                continue
            obj.shape_key_remove(current)
            removed += 1

        sko_clean_missing_shape_keys(mesh)
        sync_shape_key_assignment_names(mesh)
        self.report({"INFO"}, iface_("Deleted {} filtered shape keys.").format(removed))
        return {"FINISHED"}


# The offsets copied by sko.copy_selected_offsets, kept for the session: a scratch pad
# for one edit rather than part of the file. Living in the module also means it survives
# undo, the way a clipboard should.
_OFFSET_CLIPBOARD = []


def sko_offset_context(context):
    """What the two offset-clipboard operators need, or None when they cannot run.

    Edit mode, an active key that is not the basis, and the key the offsets are measured
    against - the same three things in the same order for the copy and the paste, so both
    polls and both bodies ask once.
    """
    obj = get_active_object(context)
    if obj is None or obj.mode != "EDIT" or obj.data.shape_keys is None:
        return None
    key = obj.active_shape_key
    if key is None or sko_is_basis(obj.data, key):
        return None
    reference = sko_get_reference_key(obj.data, key)
    if reference is None:
        return None
    return obj, obj.data, key, reference


class SKO_OT_select_offset_vertices(Operator):
    bl_idname = "sko.select_offset_vertices"
    bl_label = "Select Offset Vertices"
    bl_description = "Select vertices that are moved by the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    threshold: FloatProperty(
        name="Min Move Threshold",
        description="Minimum movement required to count as an offset",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        precision=4,
    )

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.mode == "EDIT"
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.mode != "EDIT":
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        selected = 0
        for vert in bm.verts:
            index = vert.index
            offset = (vert.co - reference.data[index].co).length
            select = offset > self.threshold
            vert.select = select
            if select:
                selected += 1

        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Selected {} offset vertices.").format(selected))
        return {"FINISHED"}


class SKO_OT_remove_selected_offsets(Operator):
    bl_idname = "sko.remove_selected_offsets"
    bl_label = "Remove Selected Offsets"
    bl_description = "Reset the offset of selected vertices in the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.mode == "EDIT"
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.mode != "EDIT":
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        moved = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            vert.co = reference.data[vert.index].co
            moved += 1

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Removed offsets from {} vertices.").format(moved))
        return {"FINISHED"}


class SKO_OT_copy_selected_offsets(Operator):
    bl_idname = "sko.copy_selected_offsets"
    bl_label = "Copy Offsets from Selected Points' Shape Key"
    bl_description = "Copy the offsets the selected vertices have in the active shape key, scaled by its value so the copy matches what is on screen"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return sko_offset_context(context) is not None

    def execute(self, context):
        found = sko_offset_context(context)
        if found is None:
            return {"CANCELLED"}
        _obj, mesh, key, reference = found

        # A relative key's value scales what it does to the mesh, so the copy carries it:
        # pasting into another key at another value then reproduces this offset on screen
        # instead of the raw one. Absolute keys have no value to take into account.
        scale = float(key.value) if mesh.shape_keys.use_relative else 1.0

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        offsets = []
        for vert in bm.verts:
            if not vert.select:
                continue
            base = reference.data[vert.index].co
            offset = (vert.co - base) * scale
            offsets.append((vert.index, offset.x, offset.y, offset.z))

        if not offsets:
            self.report({"WARNING"}, iface_("Select vertices in edit mode first."))
            return {"CANCELLED"}

        _OFFSET_CLIPBOARD[:] = offsets
        self.report({"INFO"}, iface_("Copied the offsets of {} vertices.").format(len(offsets)))
        return {"FINISHED"}


class SKO_OT_paste_selected_offsets(Operator):
    bl_idname = "sko.paste_selected_offsets"
    bl_label = "Paste Offsets to Selected Points' Shape Key"
    bl_description = "Apply the stored offsets to the selected vertices in the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_OFFSET_CLIPBOARD) and sko_offset_context(context) is not None

    def execute(self, context):
        found = sko_offset_context(context)
        if found is None:
            return {"CANCELLED"}
        _obj, mesh, key, reference = found
        if not _OFFSET_CLIPBOARD:
            self.report({"WARNING"}, iface_("Nothing has been copied yet."))
            return {"CANCELLED"}

        # The inverse of the copy: the clipboard holds what was on screen, so undo the
        # value scaling of the key being pasted into and the same offset lands again. A
        # key sitting at zero shows nothing either way, so it cannot divide.
        scale = float(key.value) if mesh.shape_keys.use_relative else 1.0
        divisor = scale if scale else 1.0
        stored = {index: (dx, dy, dz) for index, dx, dy, dz in _OFFSET_CLIPBOARD}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        applied = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            offset = stored.get(vert.index)
            if offset is None:
                continue
            base = reference.data[vert.index].co
            vert.co = (
                base.x + offset[0] / divisor,
                base.y + offset[1] / divisor,
                base.z + offset[2] / divisor,
            )
            applied += 1

        if not applied:
            self.report(
                {"WARNING"},
                iface_("None of the selected vertices has a stored offset."),
            )
            return {"CANCELLED"}

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Pasted offsets to {} vertices.").format(applied))
        return {"FINISHED"}


class SKO_OT_apply_stored_offsets(Operator):
    bl_idname = "sko.apply_stored_offsets"
    bl_label = "Apply Offsets to Selected Points"
    bl_description = "Move the selected vertices by the stored offsets in the active shape key, without taking its value into account"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            bool(_OFFSET_CLIPBOARD)
            and obj is not None
            and obj.mode == "EDIT"
            and obj.data.shape_keys is not None
        )

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or obj.mode != "EDIT" or obj.data.shape_keys is None:
            return {"CANCELLED"}
        if not _OFFSET_CLIPBOARD:
            self.report({"WARNING"}, iface_("Nothing has been copied yet."))
            return {"CANCELLED"}

        mesh = obj.data
        stored = {index: (dx, dy, dz) for index, dx, dy, dz in _OFFSET_CLIPBOARD}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        applied = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            offset = stored.get(vert.index)
            if offset is None:
                continue
            # Edit mode writes the active key and nothing else, which is exactly what this
            # entry wants: the offset lands there like a plain vertex move, with the key's
            # value left out of it.
            vert.co = (vert.co.x + offset[0], vert.co.y + offset[1], vert.co.z + offset[2])
            applied += 1

        if not applied:
            self.report(
                {"WARNING"},
                iface_("None of the selected vertices has a stored offset."),
            )
            return {"CANCELLED"}

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Applied the offsets to {} vertices.").format(applied))
        return {"FINISHED"}


def sko_get_vertex_group(obj, name):
    for group in obj.vertex_groups:
        if group.name == name:
            return group
    return None


class SKO_OT_create_offset_vertex_group(Operator):
    # The idname keeps the old "offset" wording so existing shortcuts and scripts
    # keep working; only the labels moved to the "blend" vocabulary.
    bl_idname = "sko.create_offset_vertex_group"
    bl_label = "Auto Create Blend Vertex Group"
    bl_description = "Create a blend vertex group from the vertices the active shape key moves"
    bl_options = {"REGISTER", "UNDO"}

    threshold: FloatProperty(
        name="Min Move Threshold",
        description="Minimum movement required to count as an offset",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        precision=4,
    )
    vertex_group_name: StringProperty(name="Vertex Group")

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def invoke(self, context, event):
        obj = get_active_object(context)
        if obj and obj.active_shape_key and not self.vertex_group_name:
            self.vertex_group_name = "shapeblend_" + obj.active_shape_key.name
        if context.window is None:  # background / scripted runs have no dialog
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        key = obj.active_shape_key if obj else None
        if key is not None and key.vertex_group:
            layout.label(text=iface_("Replaces the shape key's current vertex group:"), icon="ERROR")
            layout.label(text=key.vertex_group)
        layout.prop(self, "vertex_group_name")
        layout.prop(self, "threshold")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or not obj.data.shape_keys:
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        if not key or sko_is_basis(mesh, key):
            return {"CANCELLED"}

        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        if obj.mode == "EDIT":
            import bmesh

            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            indices = [
                vert.index
                for vert in bm.verts
                if (vert.co - reference.data[vert.index].co).length > self.threshold
            ]
        else:
            indices = [
                vertex.index
                for vertex in mesh.vertices
                if (key.data[vertex.index].co - reference.data[vertex.index].co).length > self.threshold
            ]

        name = (self.vertex_group_name or "").strip() or ("shapeblend_" + key.name)
        replaced = key.vertex_group
        group = obj.vertex_groups.new(name=name)
        if obj.mode == "EDIT":
            deform = bm.verts.layers.deform.verify()
            for index in indices:
                bm.verts[index][deform][group.index] = 1.0
            bmesh.update_edit_mesh(mesh)
        else:
            group.add(indices, 1.0, "REPLACE")
        key.vertex_group = group.name

        self.report({"INFO"}, iface_("Created vertex group {} with {} vertices.").format(group.name, len(indices)))
        if replaced and replaced != group.name:
            self.report({"WARNING"}, iface_("Replaced the shape key's vertex group {}.").format(replaced))
        return {"FINISHED"}


class SKO_OT_create_blend_group(Operator):
    """The same group as the automatic one, but from the edit-mode selection."""

    bl_idname = "sko.create_blend_group"
    bl_label = "Create Blend Vertex Group"
    bl_description = "Create a blend vertex group from the vertices selected in edit mode"
    bl_options = {"REGISTER", "UNDO"}

    vertex_group_name: StringProperty(name="Vertex Group")

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.mode == "EDIT"  # the selection only exists in edit mode
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def invoke(self, context, event):
        obj = get_active_object(context)
        if obj and obj.active_shape_key and not self.vertex_group_name:
            self.vertex_group_name = "shapeblend_" + obj.active_shape_key.name
        if context.window is None:  # background / scripted runs have no dialog
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        key = obj.active_shape_key if obj else None
        if key is not None and key.vertex_group:
            layout.label(text=iface_("Replaces the shape key's current vertex group:"), icon="ERROR")
            layout.label(text=key.vertex_group)
        layout.prop(self, "vertex_group_name")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.mode != "EDIT" or not obj.data.shape_keys:
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        if not key or sko_is_basis(mesh, key):
            return {"CANCELLED"}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        selection = [vert.index for vert in bm.verts if vert.select]
        if not selection:
            self.report({"WARNING"}, iface_("Select vertices in edit mode first."))
            return {"CANCELLED"}

        name = (self.vertex_group_name or "").strip() or ("shapeblend_" + key.name)
        replaced = key.vertex_group
        group = obj.vertex_groups.new(name=name)
        deform = bm.verts.layers.deform.verify()
        for index in selection:
            bm.verts[index][deform][group.index] = 1.0
        bmesh.update_edit_mesh(mesh)
        key.vertex_group = group.name

        self.report({"INFO"}, iface_("Created vertex group {} with {} vertices.").format(group.name, len(selection)))
        if replaced and replaced != group.name:
            self.report({"WARNING"}, iface_("Replaced the shape key's vertex group {}.").format(replaced))
        return {"FINISHED"}


class SKO_OT_apply_offset_vertex_group(Operator):
    bl_idname = "sko.apply_offset_vertex_group"
    bl_label = "Apply Blend Vertex Group"
    bl_description = "Apply the active shape key's vertex group weights and clear the vertex group"
    bl_options = {"REGISTER", "UNDO"}

    delete_group: BoolProperty(
        name="Delete Vertex Group",
        description="Delete the vertex group after applying it",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        if obj is None or obj.data.shape_keys is None:
            return False
        key = obj.active_shape_key
        if key is None or not key.vertex_group:
            return False
        return sko_get_vertex_group(obj, key.vertex_group) is not None

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or not obj.data.shape_keys:
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        if not key or not key.vertex_group:
            return {"CANCELLED"}

        group = sko_get_vertex_group(obj, key.vertex_group)
        if group is None:
            return {"CANCELLED"}

        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        if obj.mode == "EDIT":
            import bmesh

            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            for vert in bm.verts:
                index = vert.index
                try:
                    weight = group.weight(index)
                except RuntimeError:
                    weight = 0.0
                ref_co = reference.data[index].co
                vert.co = ref_co + (vert.co - ref_co) * weight
            bmesh.update_edit_mesh(mesh)
        else:
            for vertex in mesh.vertices:
                index = vertex.index
                try:
                    weight = group.weight(index)
                except RuntimeError:
                    weight = 0.0
                ref_co = reference.data[index].co
                key.data[index].co = ref_co + (key.data[index].co - ref_co) * weight

        name = group.name
        key.vertex_group = ""
        if self.delete_group:
            obj.vertex_groups.remove(group)

        self.report({"INFO"}, iface_("Applied vertex group {} to {}.").format(name, key.name))
        return {"FINISHED"}


class SKO_OT_toggle_group_by_folder(GroupByFolderOperator, Operator):
    bl_idname = "sko.toggle_group_by_folder"
    bl_label = "Folder Order in List"
    bl_description = "Show the list grouped by folder without reordering the keys"
    kind = KIND


class SKO_OT_reset_filtered_keys(Operator):
    bl_idname = "sko.reset_filtered_keys"
    bl_label = "Reset Filtered Shape Keys"
    bl_description = "Set the value of currently filtered shape keys to 0"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        keys = sko_get_visible_shape_keys(obj.data)
        for key in keys:
            key.value = 0.0

        self.report({"INFO"}, iface_("Reset {} filtered shape keys.").format(len(keys)))
        return {"FINISHED"}
