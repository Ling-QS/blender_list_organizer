"""The vertex group panel and the menus it opens.

Split out of the organizer's model module. This is the drawing half, plus the class list that ties every
module together for registration.
"""

from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Menu, Panel

from .. import folders
import bpy
from ..common import get_active_object, scroll_stage

# Taken from the model module at import time: the package imports that one first, so it has run to the end.
from .model import (
    FOLDER_ROWS,
    GROUP_ROWS,
    KIND,
    NATIVE_MENU,
    VGO_Assignment,
    VGO_Folder,
    VGO_Settings,
    get_active_group_pair,
    get_visible_vertex_groups,
)

# The classes this panel's list has to register live in the two modules beside it.
from .list import VGO_UL_folders, VGO_UL_visible_groups
from .ops import (
    VGO_OT_activate_pair_group,
    VGO_OT_add_folder,
    VGO_OT_add_vertex_group,
    VGO_OT_archive_deform_groups,
    VGO_OT_assign_to_folder,
    VGO_OT_clear_filtered_groups,
    VGO_OT_clear_solo,
    VGO_OT_copy_folders_to_selected,
    VGO_OT_copy_selected_weights,
    VGO_OT_delete_empty_groups,
    VGO_OT_delete_filtered_empty_groups,
    VGO_OT_delete_filtered_groups,
    VGO_OT_isolate_folder,
    VGO_OT_lock_filtered_groups,
    VGO_OT_move_filtered_to_selected_folder,
    VGO_OT_move_folder,
    VGO_OT_move_vertex_group,
    VGO_OT_paste_selected_weights,
    VGO_OT_remove_folder,
    VGO_OT_remove_from_folder,
    VGO_OT_remove_selected_from_filtered_groups,
    VGO_OT_remove_vertex_group,
    VGO_OT_scroll_to_active_group,
    VGO_OT_set_folder_tag,
    VGO_OT_toggle_organizing,
    VGO_OT_move_picked_to_selected_folder,
    VGO_OT_remove_picked_from_selected_folder,
    VGO_OT_invert_picked,
    VGO_OT_clear_picked,
    VGO_OT_toggle_filed,
    VGO_OT_toggle_folder_visibility,
    VGO_OT_toggle_group_by_folder,
    VGO_OT_toggle_unfiled,
    VGO_OT_unhide_all_folders,
    VGO_PT_folder_tag_popup,
)


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
        # Filing the whole filtered list at once. Organize mode's "Selected to ..." does the same for a
        # picked subset, which is the more general tool; a plain filter is what a search gives you.
        layout.operator(KIND.move_filtered_op, icon="FILE_FOLDER", text=iface_("Filtered to Folder"))
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
        # A folder icon introduces the list below it; it is a label, so it carries no button frame. The gap
        # keeps it from reading as part of the buttons next to it.
        row.label(text="", icon="FILE_FOLDER")
        row.separator()
        row.operator(KIND.filed_op, text=iface_("Filed"), depress=settings.show_filed)
        # Solo hides the unfiled members, so the switch that normally shows them is dimmed
        # for as long as it cannot have any effect.
        unfiled_row = row.row(align=True)
        unfiled_row.enabled = not folders.has_isolated_folder(mesh, KIND)
        unfiled_row.operator(KIND.unfiled_op, text=iface_("Unfiled"), depress=settings.show_unfiled)
        # The two bulk switches belong beside the switches they undo: one column of hide presses, one of
        # solo presses. They used to share the folder control row below, which had to split its width to
        # reach the right edge - and that split squeezed the fixed-size buttons next to it.
        row.separator()
        row.operator(KIND.unhide_all_op, text="", icon="HIDE_OFF")
        row.operator(KIND.clear_solo_op, text="", icon="SOLO_OFF")

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
        # The title row carries the scroll button against its right edge: it acts on the list below, so it
        # belongs on the heading rather than among the per-member buttons.
        pair_split = pair_col.split(factor=0.6)
        pair_split.column(align=True).label(text=iface_("Active Group"))
        pair_scroll = pair_split.row(align=True)
        pair_scroll.alignment = "RIGHT"
        pair_scroll.operator("vgo.scroll_to_active_group", text="", icon="RESTRICT_SELECT_OFF")
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
        # A bare icon introduces the list below it, so what the search box filters is never in doubt.
        header.label(text="", icon="GROUP_VERTEX")
        header.separator()
        header.prop(settings, "search", text="", icon="VIEWZOOM")
        header.prop(
            settings,
            "invert_filter",
            text="",
            icon="ARROW_LEFTRIGHT",
            toggle=True,
        )
        if settings.organizing:
            # What organize mode works on: the picked rows that are visible. Hidden rows keep their own mark
            # but take no part, so the count and the bulk actions describe the same set.
            picked = folders.picked_member_names(mesh, KIND)
            header.label(text=iface_("{} of {} selected").format(len(picked), len(visible)))
        else:
            header.label(text=iface_("{} shown").format(len(visible)))
        list_row = right.row()
        # While a scroll request is running, the list is told about a stand-in active row instead of the
        # real one: that is the whole mechanism, and it is handed back on the third draw.
        if scroll_stage(obj.as_pointer()):
            active_data, active_prop = obj.data.vgo_settings, "scroll_index"
        else:
            active_data, active_prop = obj.vertex_groups, "active_index"
        list_row.template_list(
            "VGO_UL_visible_groups",
            "",
            obj,
            "vertex_groups",
            active_data,
            active_prop,
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
        if settings.organizing:
            buttons.separator()
            buttons.operator(KIND.invert_picked_op, text="", icon="ARROW_LEFTRIGHT")
            buttons.operator(KIND.clear_picked_op, text="", icon="X")

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
    VGO_OT_toggle_organizing,
    VGO_OT_move_picked_to_selected_folder,
    VGO_OT_remove_picked_from_selected_folder,
    VGO_OT_invert_picked,
    VGO_OT_clear_picked,
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
    VGO_OT_scroll_to_active_group,
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
