"""The shape key panel, its sub-panel, and the menus they open.

Split out of the organizer's model module. This is the drawing half: the panel's class list ties every
module together for registration.
"""

from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Menu, Panel

from .. import folders
import bpy
from ..common import get_active_object, scroll_stage

# The list classes live in the list module; this panel's class list registers them from here.
from .list import (
    SKO_OT_clear_key_pins,
    SKO_OT_toggle_deforming_filter,
    SKO_UL_deforming_keys,
    SKO_UL_folders,
    SKO_UL_visible_keys,
)
from .ops import (
    SKO_OT_activate_pair_key,
    SKO_OT_add_folder,
    SKO_OT_add_shape_key,
    SKO_OT_apply_offset_vertex_group,
    SKO_OT_apply_stored_offsets,
    SKO_OT_assign_to_folder,
    SKO_OT_clear_solo,
    SKO_OT_copy_folders_to_selected,
    SKO_OT_copy_selected_offsets,
    SKO_OT_create_blend_group,
    SKO_OT_create_offset_vertex_group,
    SKO_OT_delete_filtered_keys,
    SKO_OT_isolate_folder,
    SKO_OT_lock_filtered_keys,
    SKO_OT_move_filtered_to_selected_folder,
    SKO_OT_move_folder,
    SKO_OT_move_shape_key,
    SKO_OT_mute_filtered_keys,
    SKO_OT_paste_selected_offsets,
    SKO_OT_remove_folder,
    SKO_OT_remove_from_folder,
    SKO_OT_remove_selected_offsets,
    SKO_OT_remove_shape_key,
    SKO_OT_reset_filtered_keys,
    SKO_OT_scroll_to_active_key,
    SKO_OT_select_offset_vertices,
    SKO_OT_set_folder_tag,
    SKO_OT_toggle_organizing,
    SKO_OT_move_picked_to_selected_folder,
    SKO_OT_remove_picked_from_selected_folder,
    SKO_OT_invert_picked,
    SKO_OT_clear_picked,
    SKO_OT_toggle_basis_flag,
    SKO_OT_toggle_filed,
    SKO_OT_toggle_folder_visibility,
    SKO_OT_toggle_group_by_folder,
    SKO_OT_toggle_unfiled,
    SKO_OT_unhide_all_folders,
    SKO_PT_folder_tag_popup,
)
from .model import SKO_SyncSettings, draw_shape_key_sync

# Taken from the model module at import time: the package imports that one first, so it has run to the end.
from .model import (
    DEFORMING_ROWS,
    FOLDER_ROWS,
    KEY_ROWS,
    KIND,
    MEMBER_BUTTON_COLUMN_UNITS,
    NATIVE_MENU,
    SKO_Assignment,
    SKO_Folder,
    SKO_KeyFlag,
    SKO_PlaceholderKey,
    SKO_Settings,
    sko_get_active_key_pair,
    sko_get_deforming_keys,
    sko_get_pinned_keys,
    sko_get_visible_shape_keys,
)


def draw_shape_key_specials(self, context):
    """Our entries, appended to Blender's own shape key specials menu.

    Only entries that make sense next to Blender's own go here. The actions that
    work on whatever the search/folder filter shows live in their own menu
    (``SKO_MT_filter_menu``), otherwise this one grows past the screen.
    """
    layout = self.layout
    layout.separator()
    edit_col = layout.column()
    edit_col.enabled = context.object is not None and context.object.mode == "EDIT"
    edit_col.operator("sko.select_offset_vertices", icon="VERTEXSEL", text=iface_("Select Offset Vertices"))
    edit_col.operator("sko.remove_selected_offsets", icon="X", text=iface_("Remove Selected Offsets"))
    layout.separator()
    layout.operator("sko.create_offset_vertex_group", icon="GROUP_VERTEX", text=iface_("Auto Create Blend Vertex Group"))
    # Its poll already needs edit mode, so the entry greys itself out elsewhere.
    layout.operator("sko.create_blend_group", icon="GROUP_VERTEX", text=iface_("Create Blend Vertex Group"))
    layout.operator("sko.apply_offset_vertex_group", icon="GROUP_VERTEX", text=iface_("Apply Blend Vertex Group"))
    # Both are edit-mode only; their polls grey them out everywhere else, so no wrapper
    # column is needed here.
    layout.separator()
    layout.operator(
        "sko.copy_selected_offsets",
        icon="COPYDOWN",
        text=iface_("Copy Offsets from Selected Points' Shape Key"),
    )
    layout.operator(
        "sko.paste_selected_offsets",
        icon="PASTEDOWN",
        text=iface_("Paste Offsets to Selected Points' Shape Key"),
    )
    layout.operator(
        "sko.apply_stored_offsets",
        icon="ARROW_LEFTRIGHT",
        text=iface_("Apply Offsets to Selected Points"),
    )
    layout.separator()
    layout.operator(
        "sko.copy_folders_to_selected",
        icon="DUPLICATE",
        text=iface_("Copy Folders to Selected Objects"),
    )


class SKO_MT_filter_menu(Menu):
    """Bulk actions that only touch what the filter shows."""

    bl_label = "Shape Key Filter Operations"
    bl_idname = "SKO_MT_filter_menu"
    bl_description = folders.FILTER_MENU_DESCRIPTION

    def draw(self, context):
        layout = self.layout
        layout.operator("sko.reset_filtered_keys", text=iface_("Reset Filtered Values"))
        layout.operator("sko.delete_filtered_keys", text=iface_("Delete Filtered Unlocked Keys")).only_unlocked = True
        layout.operator("sko.delete_filtered_keys", text=iface_("Delete Filtered Keys")).only_unlocked = False
        layout.separator()
        # Filing the whole filtered list at once. Organize mode's "Selected to ..." does the same for a
        # picked subset, which is the more general tool; a plain filter is what a search gives you.
        layout.operator(KIND.move_filtered_op, icon="FILE_FOLDER", text=iface_("Filtered to Folder"))
        layout.separator()
        layout.operator("sko.lock_filtered_keys", icon="LOCKED", text=iface_("Lock Filtered")).action = "LOCK"
        layout.operator("sko.lock_filtered_keys", icon="UNLOCKED", text=iface_("Unlock Filtered")).action = "UNLOCK"
        layout.operator("sko.lock_filtered_keys", text=iface_("Invert Filtered Locks")).action = "INVERT"
        layout.separator()
        layout.operator("sko.mute_filtered_keys", icon="HIDE_ON", text=iface_("Mute Filtered")).action = "MUTE"
        layout.operator("sko.mute_filtered_keys", icon="HIDE_OFF", text=iface_("Unmute Filtered")).action = "UNMUTE"
        layout.operator("sko.mute_filtered_keys", text=iface_("Invert Filtered Mutes")).action = "INVERT"


def sko_draw_shape_key_properties(context, layout, obj):
    mesh = obj.data
    key = mesh.shape_keys
    kb = obj.active_shape_key
    if key is None or kb is None:
        return

    enable_edit = obj.mode != "EDIT"
    enable_edit_value = False
    if enable_edit or (obj.use_shape_key_edit_mode and obj.type == "MESH"):
        if not obj.show_only_shape_key:
            enable_edit_value = True

    # Left-aligned, and only the range fields keep a label: the value slider, the vertex group and the
    # relative key all show what they hold, while two bare number fields would not say which is which.
    layout.use_property_split = False
    layout.use_property_decorate = False

    if key.use_relative:
        if obj.active_shape_key_index != 0:
            row = layout.row()
            row.active = enable_edit_value
            row.prop(kb, "value", text="")

            col = layout.column()
            sub = col.column(align=True)
            sub.active = enable_edit_value
            sub.prop(kb, "slider_min", text="Range Min")
            sub.prop(kb, "slider_max", text="Max")

            col.prop_search(kb, "vertex_group", obj, "vertex_groups", text="")
            col.prop_search(kb, "relative_key", key, "key_blocks", text="")
    else:
        layout.prop(kb, "interpolation")
        row = layout.column()
        row.active = enable_edit_value
        row.prop(key, "eval_time")


class SKO_PT_shape_key_organizer(Panel):
    bl_label = "Shape Key Organizer"
    bl_idname = "SKO_PT_shape_key_organizer"
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
        settings = mesh.sko_settings
        # Linked data cannot be written to. Say so instead of drawing buttons that quietly do
        # nothing, and keep drawing the rest: the folders are still worth looking at.
        if not folders.is_editable(mesh) or settings is None:
            layout.label(
                text=iface_("Linked data: folders are read-only."),
                icon="LIBRARY_DATA_DIRECTORY",
            )
        if settings is None:
            return
        visible = sko_get_visible_shape_keys(mesh)

        split = layout.split(factor=0.36)
        left = split.column()
        right = split.column()

        # A folder icon introduces the list below it, and the two bulk switches sit against the right edge of
        # the same row: they undo a whole column of hide and solo presses, which is the folder list's own
        # business. The button row under the list keeps to the per-folder buttons and sizes to them.
        switches = left.row(align=True)
        switches.label(text="", icon="FILE_FOLDER")
        bulk_switches = switches.row(align=True)
        bulk_switches.alignment = "RIGHT"
        bulk_switches.operator(KIND.unhide_all_op, text="", icon="HIDE_OFF")
        bulk_switches.operator(KIND.clear_solo_op, text="", icon="SOLO_OFF")

        left.template_list(
            "SKO_UL_folders",
            "",
            mesh,
            "sko_folders",
            mesh,
            "sko_folder_index",
            rows=FOLDER_ROWS,
            maxrows=folders.LIST_MAX_ROWS,
        )

        folders.draw_folder_controls(left, mesh, KIND)

        folders.draw_folder_actions(left, mesh, KIND)

        # The title goes inside the aligned column: an aligned column packs its
        # items tight, so the entries sit right under the title.
        pair_box = left.box()
        pair_col = pair_box.column(align=True)
        # The title row carries the scroll button against its right edge: it acts on the list below, so it
        # belongs on the heading rather than among the per-member buttons.
        pair_split = pair_col.split(factor=0.6)
        pair_split.column(align=True).label(text=iface_("Active Key"))
        pair_scroll = pair_split.row(align=True)
        pair_scroll.alignment = "RIGHT"
        pair_scroll.operator("sko.scroll_to_active_key", text="", icon="RESTRICT_SELECT_OFF")
        pair_keys = sko_get_active_key_pair(obj)
        if pair_keys:
            for key in pair_keys:
                row = pair_col.row(align=True)
                icon = "SHAPEKEY_DATA" if key == obj.active_shape_key else "ARROW_LEFTRIGHT"
                op = row.operator(
                    "sko.activate_pair_key",
                    text=key.name,
                    icon=icon,
                    emboss=False,
                    depress=(key == obj.active_shape_key),
                    translate=False,
                )
                op.key_name = key.name
                row.prop(key, "mute", text="", emboss=False)
                if hasattr(key, "lock_shape"):
                    row.prop(key, "lock_shape", text="", emboss=False)

        active_key = obj.active_shape_key
        if mesh.shape_keys and active_key:
            sko_draw_shape_key_properties(context, left, obj)

        if mesh.shape_keys:
            basis = mesh.shape_keys.key_blocks[0]
            basis_active = obj.active_shape_key_index == 0
            # Pad the basis box with an invisible button so its right edge lines
            # up with the list below, which is narrowed by its button column.
            basis_outer = right.row()
            basis_box = basis_outer.box()
            basis_spacer = basis_outer.column()
            basis_spacer.ui_units_x = MEMBER_BUTTON_COLUMN_UNITS
            basis_spacer.label(text="", icon="BLANK1")
            basis_col = basis_box.column(align=True)
            basis_row = basis_col.row(align=True)
            op = basis_row.operator(
                "sko.activate_pair_key",
                text=basis.name,
                icon="SHAPEKEY_DATA",
                # Embossed while it is the active key: a flat row cannot show
                # "pressed", so the basis would look the same either way.
                emboss=basis_active,
                depress=basis_active,
                translate=False,
            )
            op.key_name = basis.name
            # Mute and lock are operators as well, so the pressed background runs
            # across the whole row instead of stopping after the name; the icons
            # keep showing the state.
            mute_op = basis_row.operator(
                "sko.toggle_basis_flag",
                text="",
                # ShapeKey.mute declares ICON_CHECKBOX_HLT with icon_on=-1, so the
                # widget the other rows use shows the checked box while the key is
                # *not* muted and swaps in the empty box once it is. Keep the same
                # way round here, or the basis row contradicts the list.
                icon="CHECKBOX_HLT" if not basis.mute else "CHECKBOX_DEHLT",
                emboss=basis_active,
                depress=basis_active,
            )
            mute_op.action = "MUTE"
            if hasattr(basis, "lock_shape"):
                lock_op = basis_row.operator(
                    "sko.toggle_basis_flag",
                    text="",
                    icon="LOCKED" if basis.lock_shape else "UNLOCKED",
                    emboss=basis_active,
                    depress=basis_active,
                )
                lock_op.action = "LOCK"
            if basis.mute:
                basis_row.active = False

        # The member list is introduced by its own bare icon, then the two view switches and the count close
        # the row. An aligned row hands every item the same share of its width - the count label included - so
        # the two switches would each take a third and come out far wider than their labels ask for. Splitting
        # the rest of the row in half gives the pair a quarter each and the count the other half.
        switchers = right.row(align=True)
        switchers.label(text="", icon="SHAPEKEY_DATA")
        switchers.separator()
        halves = switchers.split(factor=0.5)
        switch_pair = halves.row(align=True)
        switch_pair.operator(KIND.filed_op, text=iface_("Filed"), depress=settings.show_filed)
        switch_pair.operator(KIND.unfiled_op, text=iface_("Unfiled"), depress=settings.show_unfiled)
        count_row = halves.row(align=True)
        count_row.separator()
        if settings.organizing:
            # What organize mode works on: the picked rows that are visible. Hidden rows keep their own mark
            # but take no part, so the count and the bulk actions describe the same set.
            picked = folders.picked_member_names(mesh, KIND)
            count_row.label(text=iface_("● {} / {}").format(len(picked), len(visible)))
        else:
            count_row.label(text=iface_("{} shown").format(len(visible)))

        # The list and the search row share an aligned column, so the search box sits tight under the list
        # instead of being pushed away by the usual gap between rows.
        list_column = right.column(align=True)
        list_row = list_column.row()
        if mesh.shape_keys:
            # While a scroll request is running, the list is told about a stand-in active row instead of
            # the real one: that is the whole mechanism, and it is handed back on the third draw.
            if scroll_stage(mesh.shape_keys.as_pointer()):
                active_data, active_prop = mesh.sko_settings, "scroll_index"
            else:
                active_data, active_prop = obj, "active_shape_key_index"
            list_row.template_list(
                "SKO_UL_visible_keys",
                "",
                mesh.shape_keys,
                "key_blocks",
                active_data,
                active_prop,
                rows=KEY_ROWS,
                maxrows=folders.LIST_MAX_ROWS,
            )
        else:
            # No shape keys yet: draw a real (empty) list rather than a placeholder,
            # by pointing it at a collection that is always empty. It then matches
            # what the vertex group panel shows, height and drag handle included.
            list_row.template_list(
                "SKO_UL_visible_keys",
                "",
                settings,
                "placeholder_keys",
                settings,
                "placeholder_index",
                rows=KEY_ROWS,
                maxrows=folders.LIST_MAX_ROWS,
            )

        buttons = list_row.column(align=True)
        buttons.operator("sko.add_shape_key", text="", icon="ADD").from_mix = False
        buttons.operator("sko.remove_shape_key", text="", icon="REMOVE")
        buttons.separator()
        # Blender's own menu, with our entries appended: one list, shared with
        # whatever other add-ons put in it. The filter actions sit below it in
        # their own menu so neither list grows past the screen.
        buttons.menu(NATIVE_MENU, text="", icon="DOWNARROW_HLT")
        buttons.menu("SKO_MT_filter_menu", text="", icon="FILTER")
        buttons.separator()
        buttons.operator("sko.move_shape_key", text="", icon="TRIA_UP").direction = "UP"
        buttons.operator("sko.move_shape_key", text="", icon="TRIA_DOWN").direction = "DOWN"
        buttons.separator()
        # The folder-order view is a switch, not an action, so it lives here as a
        # button that stays pressed while it is on instead of in the menu.
        buttons.operator(
            "sko.toggle_group_by_folder",
            text="",
            icon="APPEND_BLEND",
            depress=settings.group_by_folder,
        )
        if settings.organizing:
            buttons.separator()
            buttons.operator(KIND.invert_picked_op, text="", icon="ARROW_LEFTRIGHT")
            buttons.operator(KIND.clear_picked_op, text="", icon="X")

        # The search box sits under the list it filters, where Blender puts the filter of a list of its own.
        # It brings its own magnifier icon, so the bare icon that introduces the list stayed up with the
        # switches and the count. The outer row is a plain row, not an aligned one: an aligned row sizes every
        # item to its contents, which squeezed the spacer below to an icon's width. The two widgets go in an
        # aligned row of their own so no gap opens between them.
        header = list_column.row()
        search_row = header.row(align=True)
        search_row.prop(settings, "search", text="", icon="VIEWZOOM")
        search_row.prop(
            settings,
            "invert_filter",
            text="",
            icon="ARROW_LEFTRIGHT",
            toggle=True,
        )
        # Pad the row with an invisible button, the way the basis box is padded: the list above is narrowed
        # by its button column, and without this the search box would run past the list it filters.
        header_spacer = header.column()
        header_spacer.ui_units_x = MEMBER_BUTTON_COLUMN_UNITS
        header_spacer.label(text="", icon="BLANK1")

        if mesh.shape_keys and len(mesh.shape_keys.key_blocks) > 1 and not visible:
            right.label(text=iface_("No shape keys match the current filter."), icon="INFO")
            if settings.search:
                right.label(text=iface_("The basis key is never listed."), icon="INFO")

        # The rest position, the relative/absolute choice and the pin are about the whole mesh rather than
        # either column, so this row is drawn across both of them, directly above the sync section.
        has_rest = obj.type == "MESH" and hasattr(obj, "add_rest_position_attribute")
        if mesh.shape_keys and active_key:
            row = layout.row(align=True)
            row.use_property_split = False
            if has_rest:
                row.prop(obj, "add_rest_position_attribute")

            # The relative/absolute switch changes what the whole list shows, so it
            # belongs with the rest position and the pin rather than under the basis.
            row.prop(mesh.shape_keys, "use_relative")

            sub = row.row(align=True)
            sub.alignment = "RIGHT"
            subsub = sub.row(align=True)
            enable_pin = (obj.mode != "EDIT") or (obj.use_shape_key_edit_mode and obj.type == "MESH")
            subsub.active = enable_pin
            subsub.prop(obj, "show_only_shape_key", text="")
            if obj.type == "MESH":
                sub.prop(obj, "use_shape_key_edit_mode", text="")
            sub.separator()
            if mesh.shape_keys.use_relative:
                sub.operator("object.shape_key_clear", icon="X", text="")
            else:
                sub.operator("object.shape_key_retime", icon="RECOVER_LAST", text="")
        elif has_rest:
            rest_row = layout.row(align=True)
            rest_row.use_property_split = False
            rest_row.alignment = "LEFT"
            rest_row.prop(obj, "add_rest_position_attribute")

        draw_shape_key_sync(layout, obj)


class SKO_PT_deforming_keys(Panel):
    """A live list of the keys the mesh is showing, folded away by default.

    It mirrors the mesh instead of organizing it, so it hangs under the organizer as a
    sub-panel and starts collapsed: the organizer stays what the panel opens on, and this
    is there for the other question - what is deforming the mesh right now. The name keeps
    clear of Blender's own "active shape key", which is the key being edited.
    """

    bl_label = "Deforming Shape Keys"
    bl_idname = "SKO_PT_deforming_keys"
    bl_parent_id = "SKO_PT_shape_key_organizer"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.data.shape_keys is not None
            and obj.data.sko_settings is not None
        )

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        mesh = obj.data
        if not sko_get_deforming_keys(mesh) and not sko_get_pinned_keys(mesh):
            layout.label(text=iface_("No shape key is deforming the mesh."), icon="INFO")
            return

        # The organizer's own list with a different filter - plus the pin button that keeps a key
        # here - so there is nothing new to learn. The button column to its right holds the two
        # list-wide switches, with a gap between them so one press cannot mean both.
        row = layout.row()
        row.template_list(
            "SKO_UL_deforming_keys",
            "",
            mesh.shape_keys,
            "key_blocks",
            obj,
            "active_shape_key_index",
            rows=DEFORMING_ROWS,
            maxrows=folders.LIST_MAX_ROWS,
        )
        buttons = row.column(align=True)
        buttons.operator("sko.clear_key_pins", text="", icon="UNPINNED")
        buttons.separator()
        buttons.operator(
            "sko.toggle_deforming_filter",
            text="",
            icon="FILTER",
            depress=mesh.sko_settings.filter_deforming,
        )


def _draw_edit_mesh_vertex_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sko.select_offset_vertices", icon="VERTEXSEL")
    layout.operator("sko.remove_selected_offsets", icon="X")


def _draw_edit_mesh_select_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sko.select_offset_vertices", icon="VERTEXSEL")


def _draw_paint_weight_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sko.create_offset_vertex_group", icon="GROUP_VERTEX")
    layout.operator("sko.apply_offset_vertex_group", icon="GROUP_VERTEX")


def register_menus():
    bpy.types.VIEW3D_MT_edit_mesh_vertices.append(_draw_edit_mesh_vertex_menu)
    bpy.types.VIEW3D_MT_select_edit_mesh.append(_draw_edit_mesh_select_menu)
    bpy.types.VIEW3D_MT_paint_weight.append(_draw_paint_weight_menu)
    if hasattr(bpy.types, NATIVE_MENU):
        getattr(bpy.types, NATIVE_MENU).append(draw_shape_key_specials)


def unregister_menus():
    bpy.types.VIEW3D_MT_edit_mesh_vertices.remove(_draw_edit_mesh_vertex_menu)
    bpy.types.VIEW3D_MT_select_edit_mesh.remove(_draw_edit_mesh_select_menu)
    bpy.types.VIEW3D_MT_paint_weight.remove(_draw_paint_weight_menu)
    if hasattr(bpy.types, NATIVE_MENU):
        getattr(bpy.types, NATIVE_MENU).remove(draw_shape_key_specials)


classes = (
    SKO_Folder,
    SKO_Assignment,
    SKO_KeyFlag,
    SKO_PlaceholderKey,
    SKO_Settings,
    SKO_SyncSettings,
    SKO_UL_folders,
    SKO_UL_visible_keys,
    SKO_UL_deforming_keys,
    SKO_OT_add_folder,
    SKO_OT_remove_folder,
    SKO_OT_move_folder,
    SKO_OT_toggle_filed,
    SKO_OT_toggle_unfiled,
    SKO_OT_unhide_all_folders,
    SKO_OT_clear_solo,
    SKO_OT_set_folder_tag,
    SKO_OT_copy_folders_to_selected,
    SKO_OT_toggle_folder_visibility,
    SKO_OT_isolate_folder,
    SKO_OT_assign_to_folder,
    SKO_OT_remove_from_folder,
    SKO_OT_move_filtered_to_selected_folder,
    SKO_OT_add_shape_key,
    SKO_OT_remove_shape_key,
    SKO_OT_move_shape_key,
    SKO_OT_activate_pair_key,
    SKO_OT_scroll_to_active_key,
    SKO_OT_toggle_organizing,
    SKO_OT_move_picked_to_selected_folder,
    SKO_OT_remove_picked_from_selected_folder,
    SKO_OT_invert_picked,
    SKO_OT_clear_picked,
    SKO_OT_toggle_basis_flag,
    SKO_OT_lock_filtered_keys,
    SKO_OT_mute_filtered_keys,
    SKO_OT_delete_filtered_keys,
    SKO_OT_select_offset_vertices,
    SKO_OT_remove_selected_offsets,
    SKO_OT_copy_selected_offsets,
    SKO_OT_paste_selected_offsets,
    SKO_OT_apply_stored_offsets,
    SKO_OT_toggle_deforming_filter,
    SKO_OT_clear_key_pins,
    SKO_OT_create_offset_vertex_group,
    SKO_OT_create_blend_group,
    SKO_OT_apply_offset_vertex_group,
    SKO_OT_reset_filtered_keys,
    SKO_OT_toggle_group_by_folder,
    SKO_MT_filter_menu,
    SKO_PT_folder_tag_popup,
    SKO_PT_shape_key_organizer,
    SKO_PT_deforming_keys,
)
