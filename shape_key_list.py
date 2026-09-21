"""The shape key lists: the two UILists, their shared row, and the list-wide switches.

Split out of ``shape_keys.py``. Everything here draws or filters a list and reads the model module for
what to show.
"""

from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Operator, UIList

from . import folders
import bpy
from .common import get_active_object

# Taken from the model module at import time: ``shape_keys`` imports these back at the end of its own
# file, so the cycle resolves there.
from .shape_keys import (
    KIND,
    sko_get_deforming_keys,
    sko_get_key_flag,
    sko_get_pinned_keys,
    sko_get_visibility_context,
    sko_is_shape_key_visible,
    sko_mesh_of_keys,
)


class SKO_UL_folders(UIList):
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


class SKO_OT_toggle_deforming_filter(Operator):
    bl_idname = "sko.toggle_deforming_filter"
    bl_label = "Filter the Deforming List"
    bl_description = "Let the folder filter narrow the deforming list as well"
    bl_options = {"REGISTER", "UNDO"}

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
    bl_options = {"REGISTER", "UNDO"}

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


def sko_draw_key_row(layout, item, data, mesh, with_pin=False):
    """One shape key row, shared by the organizer list and the deforming list.

    The value slider is the flexible widget, so it stretches right up to the mute and lock
    buttons, which stay flush against the right edge; a split with a fixed factor would
    leave a gap between the two. Absolute keys are placed on the timeline instead of being
    mixed, and Blender's own panel shows their frame there, so that column follows the
    mode. The deforming list adds a pin button after them - pinning is what keeps a key in
    *that* list, so it has no business in the organizer.
    """
    row = layout.row(align=True)
    key_icon = "SHAPEKEY_DATA"
    # The tag replaces the key icon here: a member row is tight, and the folder's tag is the more
    # useful thing to see. The folder list itself shows both side by side.
    if mesh is not None:
        tag = folders.get_member_tag_folder(mesh, KIND, item.name)
        if tag is not None:
            key_icon = folders.folder_tag_icon(tag) or key_icon
    row.prop(item, "name", text="", emboss=False, icon=key_icon, translate=False)
    if getattr(data, "use_relative", True):
        row.prop(item, "value", text="", slider=True)
    else:
        row.prop(item, "frame", text="")
    icons = row.row(align=True)
    icons.use_property_decorate = False
    icons.prop(item, "mute", text="", emboss=False)
    if hasattr(item, "lock_shape"):
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
    if item.mute:
        row.active = False


class SKO_UL_visible_keys(UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        mesh = sko_mesh_of_keys(data) if isinstance(data, bpy.types.Key) else None
        if mesh is None or not hasattr(mesh, "sko_settings"):
            return [self.bitflag_filter_item] * len(items), list(range(len(items)))

        vis = sko_get_visibility_context(mesh)
        flags = [
            self.bitflag_filter_item if sko_is_shape_key_visible(mesh, item.name, vis=vis) else 0
            for item in items
        ]
        if mesh.sko_settings.group_by_folder:
            order = folders.member_display_order(mesh, KIND, items)
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
        sko_draw_key_row(layout, item, data, sko_mesh_of_keys(data))


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

        if mesh.sko_settings.filter_deforming:
            # Only the folder half of the filter, and only when asked for. The search box is
            # deliberately left out: it is shared with the organizer above, so typing in it
            # must not empty this list while the user is looking at something else.
            vis = folders.get_visibility_context(mesh, KIND)
            # Only the folder half of the filter, and only when asked for. The search box is
            # deliberately left out: it is shared with the organizer above, so typing in it
            # must not empty this list while the user is looking at something else.
            folder_vis = vis._replace(search="", invert=False)
            shown = {
                name
                for name in shown
                if folders.is_member_visible(mesh, KIND, name, vis=folder_vis)
            }

        return (
            [self.bitflag_filter_item if item.name in shown else 0 for item in items],
            list(range(len(items))),
        )

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
        sko_draw_key_row(layout, item, data, sko_mesh_of_keys(data), with_pin=True)
