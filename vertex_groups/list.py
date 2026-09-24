"""The vertex group lists: the two UILists.

Split out of the organizer's model module. They only draw and filter; the model says what to show.
"""

from bpy.types import UIList

from .. import folders

# Taken from the model module at import time: the package imports that one first, so it has run to the end.
from .model import (
    KIND,
    get_visibility_context,
    is_vertex_group_visible,
)


class VGO_UL_folders(UIList):
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



class VGO_UL_visible_groups(UIList):
    def filter_items(self, context, data, propname):
        obj = data
        vis = get_visibility_context(obj)
        # Kept for the rows that follow: draw_item runs once per row, and building the context again there
        # would rebuild the assignment table for every one of them - quadratic in the size of the list.
        self._vis = vis
        items = getattr(data, propname)
        flags = [
            self.bitflag_filter_item if is_vertex_group_visible(obj, item.name, vis=vis) else 0
            for item in items
        ]
        if obj.data.vgo_settings.group_by_folder:
            order = folders.member_display_order(KIND.data_of(obj), KIND, items, vis=vis)
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
        tag = folders.get_member_tag_folder(obj.data, KIND, item.name, vis=getattr(self, "_vis", None))
        if tag is not None:
            group_icon = folders.folder_tag_icon(tag) or group_icon
        row.prop(item, "name", text="", emboss=False, icon=group_icon, translate=False)
        if obj.data.vgo_settings.organizing:
            # Organize mode puts the pick button where the lock sits: a row has room for one of the two, and
            # while a list is being filed the pick is the one in use. It is a real property, so it presses
            # and drags across rows exactly like the lock button does.
            assignment = folders.get_assignment(obj.data, KIND, item.name)
            if assignment is not None:
                row.prop(
                    assignment,
                    "picked",
                    text="",
                    icon="RADIOBUT_ON" if assignment.picked else "RADIOBUT_OFF",
                    emboss=False,
                )
        else:
            row.prop(
                item,
                "lock_weight",
                text="",
                icon="LOCKED" if item.lock_weight else "UNLOCKED",
                emboss=False,
            )
