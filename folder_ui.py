"""The drawing half of the folder machinery: the folder list row and the two
button rows that sit under it.

Split out of ``folders.py``. These are the only folder functions that touch a
layout, and they are pure presentation - they read the kind and the folder data and
emit buttons - so they can be read on their own. ``folders.py`` re-exports them,
which is how both panels draw them (``folders.draw_folder_item(...)``).
"""

from bpy.app.translations import pgettext_iface as iface_

# Imported as a module rather than as names: ``folders`` imports these functions at
# the top of its own module, so the two are a cycle. Going through the module object
# defers the lookup to call time, when ``folders`` has finished loading and the two
# helpers below are defined.
from . import folders


def draw_folder_item(layout, context, data, kind, item):
    """One row of the folder list (shared by both UILists)."""
    obj = kind.object_of(data, context)
    active = kind.active_member(data, obj)
    active_folder_uids = folders.get_member_folder_uids(data, kind, active.name) if active else []
    folder_icon = "FOLDER_REDIRECT" if item.uid in active_folder_uids else "FILE_FOLDER"

    row = layout.row(align=True)
    row.prop(item, "name", text="", emboss=False, icon=folder_icon)

    has_isolate = any(folder.isolate for folder in kind.folders(data))
    visibility_row = row.row(align=True)
    visibility_row.enabled = not has_isolate
    visibility_op = visibility_row.operator(
        kind.visibility_op,
        text="",
        icon="HIDE_OFF" if item.visible else "HIDE_ON",
        emboss=False,
        depress=not item.visible,
    )
    visibility_op.folder_uid = item.uid

    isolate_op = row.operator(
        kind.isolate_op,
        text="",
        icon="SOLO_ON" if item.isolate else "SOLO_OFF",
        emboss=False,
        depress=item.isolate,
    )
    isolate_op.folder_uid = item.uid


def draw_folder_controls(layout, data, kind):
    """Add / remove buttons, a gap, then the move up / move down buttons."""
    folders_ = kind.folders(data)
    index = kind.folder_index(data)

    row = layout.row(align=True)
    row.operator(kind.add_op, text="", icon="NEWFOLDER")
    row.operator(kind.remove_op, text="", icon="TRASH")
    row.separator()

    move_up = row.row(align=True)
    move_up.enabled = bool(folders_) and index > 0
    up_op = move_up.operator(kind.move_op, text="", icon="TRIA_UP")
    up_op.direction = "UP"
    up_op.folder_uid = folders_[index].uid if folders_ else ""

    move_down = row.row(align=True)
    move_down.enabled = bool(folders_) and index < len(folders_) - 1
    down_op = move_down.operator(kind.move_op, text="", icon="TRIA_DOWN")
    down_op.direction = "DOWN"
    down_op.folder_uid = folders_[index].uid if folders_ else ""


def draw_folder_actions(layout, data, kind):
    """Filtered-to / active-to / active-out-of buttons for the selected folder."""
    selected = folders.get_selected_folder(data, kind)
    column = layout.column(align=True)
    column.enabled = selected is not None

    if selected is None:
        column.operator(kind.move_filtered_op, text=iface_("Filtered to Folder"), icon="FILTER")
        column.operator(kind.assign_op, text=iface_("Active to Folder"), icon="FILE_FOLDER")
        column.operator(kind.remove_member_op, text=iface_("Active out of Folder"), icon="X")
        return

    column.operator(
        kind.move_filtered_op,
        text=iface_("Filtered to {}").format(selected.name),
        icon="FILTER",
    )
    column.operator(
        kind.assign_op,
        text=iface_("Active to {}").format(selected.name),
        icon="FILE_FOLDER",
    ).folder_uid = selected.uid
    column.operator(
        kind.remove_member_op,
        text=iface_("Active out of {}").format(selected.name),
        icon="X",
    ).folder_uid = selected.uid
