"""The vertex group lists: the two UILists.

Split out of ``vertex_groups.py``. They only draw and filter; the model module says what to show.
"""

from bpy.types import UIList

from . import folders
from .common import apply_scroll_request

# Taken from the model module at import time: ``vertex_groups`` imports these back at the end of its
# own file, so the cycle resolves there.
from .vertex_groups import (
    KIND,
    get_visibility_context,
    is_vertex_group_visible,
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
        # Kept for the rows that follow: draw_item runs once per row, and building the context again there
        # would rebuild the assignment table for every one of them - quadratic in the size of the list.
        self._vis = vis
        items = getattr(data, propname)
        flags = [
            self.bitflag_filter_item if is_vertex_group_visible(obj, item.name, vis=vis) else 0
            for item in items
        ]
        if obj.data.vgo_settings.group_by_folder:
            order = folders.member_display_order(KIND.data_of(obj), KIND, items)
        else:
            order = list(range(len(items)))

        # Serving a scroll request means changing how many rows the list shows for one frame; the
        # helper explains why that is the only lever there is.
        apply_scroll_request(
            data.as_pointer(),
            flags,
            order,
            obj.vertex_groups.active_index,
            folders.LIST_MAX_ROWS,
        )

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
        row.prop(
            item,
            "lock_weight",
            text="",
            icon="LOCKED" if item.lock_weight else "UNLOCKED",
            emboss=False,
        )
