"""The folder tag palette: the icons a folder can be marked with.

Split out of ``folders.py``. Nothing here writes folder data - it only reads it - so the module is the
palette itself, the helper that turns it into a property definition, and the two lookups the panels and the
popup need.

``folders.py`` imports these names back, so the organizers and the tests keep importing them from there.
"""

# Imported from ``folders`` rather than the other way round: ``folders`` imports this module at the end of its
# own file, by which point both names already exist, so the cycle resolves at import time.
from .folders import get_member_folder_uids, get_visibility_context


# The tag palette, grouped. Colours come first, then Blender's own object and data icons, so a folder can
# be recognised by a shape as well as by a colour. Icons are the only way to show either inside a list row:
# a colour widget takes a fixed slice of the row's width, which the list cannot spare.
#
# The groups exist because a menu sizes itself to its widest entry and stretches any grid inside it to that
# width - with forty entries in one flat grid, most of the menu was empty band. Plain lists in short
# sub-menus have no band to stretch, and stay on screen.
FOLDER_TAG_GROUPS = (
    (
        "colors",
        "Colors",
        (
            "STRIP_COLOR_01",
            "STRIP_COLOR_02",
            "STRIP_COLOR_03",
            "STRIP_COLOR_04",
            "STRIP_COLOR_05",
            "STRIP_COLOR_06",
            "STRIP_COLOR_07",
            "STRIP_COLOR_08",
            "STRIP_COLOR_09",
            "COLLECTION_COLOR_01",
            "COLLECTION_COLOR_02",
            "COLLECTION_COLOR_03",
            "COLLECTION_COLOR_04",
            "COLLECTION_COLOR_05",
            "COLLECTION_COLOR_06",
            "COLLECTION_COLOR_07",
            "COLLECTION_COLOR_08",
        ),
    ),
    (
        "objects",
        "Objects",
        (
            "FUND",
            "ORPHAN_DATA",
            "SHADING_RENDERED",
            "SHADING_SOLID",
            "OUTLINER_OB_ARMATURE",
            "OUTLINER_OB_LATTICE",
            "BONE_DATA",
            "GEOMETRY_SET",
            "GHOST_ENABLED",
            "SNAP_FACE",
            "SHAPEKEY_DATA",
            "PREFERENCES",
            "UGLYPACKAGE",
        ),
    ),
    (
        "modifiers",
        "Modifiers",
        (
            "MODIFIER_ON",
            "MOD_MASK",
            "MOD_PHYSICS",
            "MOD_FLUIDSIM",
            "MOD_CLOTH",
            "MOD_SOFT",
            "RIGID_BODY",
        ),
    ),
    (
        "nodes",
        "Nodes",
        (
            "NODE_SOCKET_BOOLEAN",
            "NODE_SOCKET_BUNDLE",
            "NODE_SOCKET_CLOSURE",
            "NODE_SOCKET_COLLECTION",
            "NODE_SOCKET_FLOAT",
            "NODE_SOCKET_FONT",
            "NODE_SOCKET_GEOMETRY",
            "NODE_SOCKET_IMAGE",
            "NODE_SOCKET_INT",
            "NODE_SOCKET_INT_VECTOR",
            "NODE_SOCKET_MATERIAL",
            "NODE_SOCKET_MATRIX",
            "NODE_SOCKET_MENU",
            "NODE_SOCKET_OBJECT",
            "NODE_SOCKET_RGBA",
            "NODE_SOCKET_ROTATION",
            "NODE_SOCKET_SHADER",
            "NODE_SOCKET_STRING",
            "NODE_SOCKET_VECTOR",
        ),
    ),
    (
        "more",
        "More",
        (
            "KEYTYPE_BREAKDOWN_VEC",
            "KEYTYPE_EXTREME_VEC",
            "KEYTYPE_GENERATED_VEC",
            "KEYTYPE_JITTER_VEC",
            "KEYTYPE_KEYFRAME_VEC",
            "KEYTYPE_MOVING_HOLD_VEC",
            "PHYSICS",
            "GROUP_BONE",
            "GROUP",
            "MATERIAL",
            "NODE_TEXTURE",
            "TEXTURE",
        ),
    ),
)

FOLDER_TAG_ICONS = tuple(icon for _slug, _label, icons in FOLDER_TAG_GROUPS for icon in icons)

# The clear choice first, then the palette, in the order the menu draws them.
FOLDER_TAG_IDS = ("NONE", *FOLDER_TAG_ICONS)

_FOLDER_TAG_ICON_SET = frozenset(FOLDER_TAG_ICONS)


def folder_tag_items():
    """The tag choices: one per palette icon, plus clearing the tag.

    Every name is empty on purpose. The property is drawn with ``expand=True``, which lays the choices
    out as a row of buttons that wraps - and a name here would widen every button in that row. All-icon
    entries make each button exactly icon-wide, which is the whole point.
    """
    items = [("NONE", "", "Clear the label", "X", 0)]
    for number, icon in enumerate(FOLDER_TAG_ICONS, start=1):
        items.append((icon, "", "", icon, number))
    return items


def folder_tag_icon(folder):
    """The icon that tags a folder, or None when it carries no tag."""
    tag = folder.tag
    return tag if tag in _FOLDER_TAG_ICON_SET else None


def get_member_tag_folder(data, kind, member_name, vis=None):
    """The folder whose tag marks a member: the first one that would show it.

    A member can be filed in several folders and their tags can differ, so the list needs one
    answer. The first folder in folder order that is switched on gives it - the same order the
    folder list itself uses - and solo is respected the way the visibility rules are.
    Returns None for an unfiled member, or for one whose every folder is hidden.
    """
    if vis is None:
        vis = get_visibility_context(data, kind)

    uids = get_member_folder_uids(data, kind, member_name, vis=vis)
    if not uids:
        return None

    wanted = set(uids) & (vis.isolated if vis.isolated else vis.shown_folders)
    for folder in kind.folders(data):
        if folder.uid in wanted:
            return folder
    return None