"""The add-on's own icons, and the preview collection they are loaded into.

``icon`` only takes one of Blender's own icon names, so an image of our own goes through ``icon_value`` and a
preview collection instead. ``previews.load()`` rasterises an SVG at the preview size, which is why the icons
ship as SVG rather than as bitmaps - and why they stay sharp at any interface scale.

The collection is built on register and released on unregister, and the ids are looked up here rather than
kept anywhere: an ``icon_id`` is new every session, and is 0 in a ``--background`` run, where there is nothing
to draw into. ``icon_kwargs()`` turns that into what a button needs either way, so a caller that cannot have
the icon still gets one of Blender's own.
"""

import pathlib

import bpy
import bpy.utils.previews

ICON_FOLDER = pathlib.Path(__file__).parent / "icons_svg"

# The name each icon is loaded under, and the file it comes from.
FILE_NAMES = {
    "move_in": "folder_move_in.svg",
    "move_out": "folder_move_out.svg",
    "folder_tag": "folder_tag.svg",
}

# Built by ``register()``; None means the icons are not available at all.
_icons = None


def register():
    """Load the icons into a collection of their own."""
    global _icons
    _icons = bpy.utils.previews.new()
    for name, file_name in FILE_NAMES.items():
        path = ICON_FOLDER / file_name
        if path.is_file():
            _icons.load(name, str(path), "IMAGE")


def unregister():
    """Release the collection; the icons go with it."""
    global _icons
    if _icons is not None:
        bpy.utils.previews.remove(_icons)
    _icons = None


def icon_id(name):
    """The preview id of one of the icons, or 0 when it is not loaded."""
    if _icons is None or name not in _icons:
        return 0
    return _icons[name].icon_id


def icon_kwargs(name, fallback):
    """What to hand a button for one of these icons, falling back to a built-in one.

    A button takes either ``icon`` or ``icon_value``, never both, and the custom one is not always there -
    so this decides which to pass rather than leaving every call site to work it out.
    """
    preview = icon_id(name)
    return {"icon_value": preview} if preview else {"icon": fallback}
