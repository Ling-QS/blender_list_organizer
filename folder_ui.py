"""The drawing half of the folder machinery: the folder list row and the two
button rows that sit under it.

Split out of ``folders.py``. These are the only folder functions that touch a
layout, and they are pure presentation - they read the kind and the folder data and
emit buttons - so they can be read on their own. ``folders.py`` re-exports them,
which is how both panels draw them (``folders.draw_folder_item(...)``).
"""

from bpy.app.translations import pgettext_iface as iface_

from .common import get_active_object

# Imported as a module rather than as names: ``folders`` imports these functions at
# the top of its own module, so the two are a cycle. Going through the module object
# defers the lookup to call time, when ``folders`` has finished loading and the two
# helpers below are defined.
from . import folders
from . import icons


def draw_folder_item(layout, context, data, kind, item):
    """One row of the folder list (shared by both UILists).

    The two sets the row needs - the active member's folders, and the folders holding anyone - are worked out
    by ``folders.folder_row_sets``, which keeps them for the draw so that the rows share one pass.
    """
    obj = kind.object_of(data, context)
    active = kind.active_member(data, obj)
    held, used = folders.folder_row_sets(data, kind, active.name if active else "")
    belongs = item.uid in held

    row = layout.row(align=True)
    # The tag replaces the plain folder icon. Membership of the active member gets a narrow icon *after* the
    # name instead of brackets around it: brackets have to wrap the whole name field, which swallows the tag
    # and costs far more width than one icon.
    icon = folders.folder_tag_icon(item) or "FILE_FOLDER"
    row.prop(item, "name", text="", emboss=False, icon=icon)
    if belongs:
        row.label(text="", **icons.icon_kwargs("folder_holds", "FOLDER_REDIRECT"))
    elif item.uid not in used:
        # The same slot, for the folder that holds nothing: one place on the row says what this folder is to
        # the active member, or that it is empty.
        row.label(text="", **icons.icon_kwargs("folder_empty", "CHECKBOX_DEHLT"))

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
    """Add / remove, the label button, and the move buttons - one row, sized to its contents.

    One row and no split: a split hands its halves a fixed share of the width, which squeezed the
    fixed-size icon buttons here as soon as the panel got narrow. The two bulk switches are not in this row
    either - they sit at the top of the folder list, against its right edge.
    """
    folders_ = kind.folders(data)
    index = kind.folder_index(data)

    row = layout.row(align=True)
    row.operator(kind.add_op, text="", **icons.icon_kwargs("folder_add", "NEWFOLDER"))
    row.operator(kind.remove_op, text="", **icons.icon_kwargs("folder_remove", "TRASH"))
    row.separator()
    # The palette opens as a popup panel: a menu's content is a column, so it could never lay out a grid.
    palette = row.operator("wm.call_panel", text="", **icons.icon_kwargs("folder_tag", "COLOR"))
    palette.name = kind.tag_panel
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


def draw_folder_tag_popup(layout, kind, context):
    """The tag palette, laid out as a real grid of icon buttons.

    A popup *panel* rather than a menu: a menu's content is a column, so every way of expanding an enum inside
    one came out a single entry per line, while a panel lays out rows freely. The popup's width comes from
    ``bl_ui_units_x`` on the panel class.
    """
    obj = get_active_object(context)
    data = kind.data_of(obj) if obj is not None else None
    if data is None:
        return

    folder = folders.get_selected_folder(data, kind)
    if folder is None:
        return

    layout.label(text=iface_("Label for {}").format(folder.name), icon="COLOR")

    per_row = 10
    for start in range(0, len(folders.FOLDER_TAG_IDS), per_row):
        row = layout.row(align=True)
        for tag in folders.FOLDER_TAG_IDS[start : start + per_row]:
            icon = "X" if tag == "NONE" else tag
            # Borderless: the entries are icons, and a button frame around each one only adds width.
            op = row.operator(kind.tag_op, text="", icon=icon, emboss=False)
            op.tag = tag


def draw_folder_actions(layout, data, kind):
    """The organize switch and the folder move buttons: one row, plus two in organize mode.

    The ordinary mode is a single row - the mode switch, a gap, then the two icon buttons that file and
    unfile the active member. Organize mode adds two rows underneath that work on the picked rows instead;
    that is where a large tidy-up happens, so those two carry their text rather than an icon alone.
    """
    settings = kind.settings(data)
    selected = folders.get_selected_folder(data, kind)
    organizing = settings is not None and settings.organizing
    folder_uid = selected.uid if selected is not None else ""

    row = layout.row(align=True)
    # Left rather than the row's default expand: an expanding row (what ``align=True`` asks for) hands
    # the first button whatever width is left over, which stretched the switch across the panel. Aligned
    # left, every button here keeps the width of its label - and the two icon buttons follow it directly.
    row.alignment = "LEFT"
    row.operator(kind.organize_op, text=iface_("Organize"), depress=organizing)
    row.separator()

    active_row = row.row(align=True)
    active_row.enabled = selected is not None
    active_row.operator(
        kind.assign_op, text="", **icons.icon_kwargs("move_in", "SORT_DESC")
    ).folder_uid = folder_uid
    active_row.operator(
        kind.remove_member_op, text="", **icons.icon_kwargs("move_out", "SORT_ASC")
    ).folder_uid = folder_uid

    if not organizing:
        return

    name = selected.name if selected is not None else iface_("Folder")
    bulk = layout.column(align=True)
    bulk.enabled = selected is not None
    bulk.operator(
        kind.move_picked_op,
        text=iface_("Move ● to {}").format(name),
        **icons.icon_kwargs("move_in", "SORT_DESC"),
    ).folder_uid = folder_uid
    bulk.operator(
        kind.remove_picked_op,
        text=iface_("Remove ● from {}").format(name),
        **icons.icon_kwargs("move_out", "SORT_ASC"),
    ).folder_uid = folder_uid
