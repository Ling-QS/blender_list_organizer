"""The shape key lists: the two UILists, their shared row, and the list-wide switches.

Split out of the organizer's model module. Everything here draws or filters a list and reads the model
module for what to show.
"""

from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Operator, UIList

from .. import folders
import bpy
from ..common import get_active_object

# Taken from the model module at import time: the package imports that one first, so it has run to the end.
from .model import (
    KIND,
    sko_get_deforming_keys,
    sko_get_key_flag,
    sko_get_pinned_keys,
    sko_get_visibility_context,
    sko_is_shape_key_visible,
    sko_mesh_of_keys,
)


class SKO_UL_folders(UIList):
    def filter_items(self, context, data, propname):
        # Nothing is filtered out, but this is the one hook that runs before the rows: the two sets the rows
        # share are built here rather than once per row.
        items = getattr(data, propname)
        obj = KIND.object_of(data, context)
        active = KIND.active_member(data, obj) if obj is not None else None
        self._held = folders.get_member_folder_uids(data, KIND, active.name) if active else []
        self._used = folders.used_folder_uids(data, KIND)
        return [self.bitflag_filter_item] * len(items), list(range(len(items)))

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
        folders.draw_folder_item(
            layout,
            context,
            data,
            KIND,
            item,
            held=getattr(self, "_held", None),
            used=getattr(self, "_used", None),
        )


class SKO_OT_toggle_deforming_filter(Operator):
    bl_idname = "sko.toggle_deforming_filter"
    bl_label = "Filter the Deforming List"
    bl_description = "Let the folder filter narrow the deforming list as well"
    bl_options = {"REGISTER"}

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or obj.data.sko_settings is None:
            return {"CANCELLED"}

        settings = obj.data.sko_settings
        settings.filter_deforming = not settings.filter_deforming
        return {"FINISHED"}


class SKO_OT_clear_key_pins(Operator):
    bl_idname = "sko.clear_key_pins"
    bl_label = "Clear All Pins"
    bl_description = "Unpin every shape key at once"
    bl_options = {"REGISTER"}

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or obj.data.sko_settings is None:
            return {"CANCELLED"}

        cleared = 0
        for flag in obj.data.sko_settings.key_flags:
            if flag.pinned:
                flag.pinned = False
                cleared += 1
        self.report({"INFO"}, iface_("Cleared {} pins.").format(cleared))
        return {"FINISHED"}


def sko_draw_key_row(layout, item, data, mesh, with_pin=False, vis=None, with_pick=False):
    """One shape key row, shared by the organizer list and the deforming list.

    The value slider is the flexible widget, so it stretches right up to the mute and lock
    buttons, which stay flush against the right edge; a split with a fixed factor would
    leave a gap between the two. Absolute keys are placed on the timeline instead of being
    mixed, and Blender's own panel shows their frame there, so that column follows the
    mode. The deforming list adds a pin button after them - pinning is what keeps a key in
    *that* list, so it has no business in the organizer.

    The name and the value get a row of their own so that a muted key can dim them without dimming the
    buttons beside them. Those buttons still work on a muted key, and a greyed-out button reads as a
    disabled one.
    """
    row = layout.row(align=True)
    text_row = row.row(align=True)
    key_icon = "SHAPEKEY_DATA"
    # The tag replaces the key icon here: a member row is tight, and the folder's tag is the more
    # useful thing to see. The folder list itself shows both side by side.
    if mesh is not None:
        tag = folders.get_member_tag_folder(mesh, KIND, item.name, vis=vis)
        if tag is not None:
            key_icon = folders.folder_tag_icon(tag) or key_icon
    text_row.prop(item, "name", text="", emboss=False, icon=key_icon, translate=False)
    if getattr(data, "use_relative", True):
        text_row.prop(item, "value", text="", slider=True)
    else:
        text_row.prop(item, "frame", text="")
    if item.mute:
        text_row.active = False
    icons = row.row(align=True)
    icons.use_property_decorate = False
    icons.prop(item, "mute", text="", emboss=False)
    organizing = (
        with_pick and mesh is not None and mesh.sko_settings is not None and mesh.sko_settings.organizing
    )
    if organizing:
        # Organize mode puts the pick button where the lock sits: a row has room for one of the two, and
        # while a list is being filed the pick is the one in use. It is a real property, so it presses and
        # drags across rows exactly like the lock button does. The deforming list asks for no pick button:
        # it is a view of the same keys, not the list that organize mode files.
        assignment = folders.get_assignment(mesh, KIND, item.name)
        if assignment is not None:
            icons.prop(
                assignment,
                "picked",
                text="",
                icon="RADIOBUT_ON" if assignment.picked else "RADIOBUT_OFF",
                emboss=False,
            )
    elif hasattr(item, "lock_shape"):
        icons.prop(item, "lock_shape", text="", emboss=False)
    if with_pin:
        # A prop rather than an operator: pressing it and dragging across rows toggles a run
        # of keys at once, which is how the mute and lock buttons next to it already behave.
        flag = sko_get_key_flag(mesh, item.name) if mesh is not None else None
        if flag is not None:
            icons.prop(
                flag,
                "pinned",
                text="",
                icon="PINNED" if flag.pinned else "UNPINNED",
                emboss=False,
            )


class SKO_UL_visible_keys(UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        mesh = sko_mesh_of_keys(data) if isinstance(data, bpy.types.Key) else None
        if mesh is None or not hasattr(mesh, "sko_settings"):
            return [self.bitflag_filter_item] * len(items), list(range(len(items)))

        vis = sko_get_visibility_context(mesh)
        # Kept for the rows that follow: draw_item runs once per row, and building the context again there
        # would rebuild the assignment table for every one of them - quadratic in the size of the list.
        self._vis = vis
        flags = [
            self.bitflag_filter_item if sko_is_shape_key_visible(mesh, item.name, vis=vis) else 0
            for item in items
        ]
        if mesh.sko_settings.group_by_folder:
            order = folders.member_display_order(mesh, KIND, items, vis=vis)
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
        sko_draw_key_row(
            layout, item, data, sko_mesh_of_keys(data), vis=getattr(self, "_vis", None), with_pick=True
        )


class SKO_UL_deforming_keys(UIList):
    """The organizer's list, filtered down to the keys deforming the mesh right now.

    Deforming means unmuted and off zero. The basis is filtered out with the rest: it is
    the reference the others are measured against, never an edit of its own. A pinned key
    stays in the list whether or not it is deforming, which is what pinning is for.
    """

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        mesh = sko_mesh_of_keys(data)
        if mesh is None or mesh.shape_keys is None:
            return [self.bitflag_filter_item] * len(items), list(range(len(items)))

        # Read-only on purpose: writing from a draw callback raises "Writing to ID classes in
        # this context is not allowed", and that exception takes the whole filter result with
        # it - which is how every key, basis included, once ended up in this list.
        shown = {key.name for key in sko_get_deforming_keys(mesh)}
        shown.update(sko_get_pinned_keys(mesh))

        vis = folders.get_visibility_context(mesh, KIND)
        self._vis = vis
        if mesh.sko_settings.filter_deforming:
            # Only the folder half of the filter, and only when asked for. The search box is
            # deliberately left out: it is shared with the organizer above, so typing in it
            # must not empty this list while the user is looking at something else.
            folder_vis = vis._replace(search="", invert=False)
            shown = {
                name
                for name in shown
                if folders.is_member_visible(mesh, KIND, name, vis=folder_vis)
            }

        shown_flags = [self.bitflag_filter_item if item.name in shown else 0 for item in items]

        # Pinned keys lead the list. A pin is what keeps a key here when it is not deforming, so the rows put
        # there by hand come first and the ones deforming right now follow. ``flt_neworder`` maps a source
        # index to the position it should be displayed at.
        pinned = set(sko_get_pinned_keys(mesh))
        leading = [
            index for index, item in enumerate(items) if shown_flags[index] and item.name in pinned
        ]
        following = [
            index for index, item in enumerate(items) if shown_flags[index] and item.name not in pinned
        ]
        rest = [index for index in range(len(items)) if not shown_flags[index]]
        neworder = [0] * len(items)
        for position, index in enumerate(leading + following + rest):
            neworder[index] = position

        return shown_flags, neworder

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
        sko_draw_key_row(
            layout, item, data, sko_mesh_of_keys(data), with_pin=True, vis=getattr(self, "_vis", None)
        )
