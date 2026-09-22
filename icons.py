"""The add-on's own icons, and the preview collection they are loaded into.

``icon`` only takes one of Blender's own icon names, so an image of our own goes through ``icon_value`` and a
preview collection instead. The icons are SVGs, which the preview system rasterises at the size the interface
draws them.

One thing it asks of them: the root element has to declare a definite pixel size - ``width="1600"
height="1500"`` here rather than ``width="100%"``, which is what an exporter tends to write. Without one the
preview system reports a size and hands back no pixels, so every button drawn with the icon comes out blank.
The drawing's own coordinates also have to land inside that size, which they do as long as the width and height
match the viewBox. Keep both in mind when re-exporting these.

The collection is built on first use rather than when the add-on registers. A preview built that early, before
any file has been read and before there is a window to draw into, comes back with nothing to draw either, which
is what left a project opened straight from the command line with blank icon buttons. Building it again later
is no cure: a collection made after another one has been removed behaves the same way, so there is no removing
and rebuilding here at all - the first draw asks for the icons, and that is the only build there is.

The ids are looked up here rather than kept anywhere, because an ``icon_id`` is new every session and is 0 in a
``--background`` run, where there is nothing to draw into. ``icon_kwargs()`` turns that into what a button
needs either way, so a caller that cannot have the icon still gets one of Blender's own.
"""

import pathlib

import bpy
import bpy.utils.previews

ICON_FOLDER = pathlib.Path(__file__).parent / "icons"

# The name each icon is loaded under, and the file it comes from.
FILE_NAMES = {
    "move_in": "folder_move_in.svg",
    "move_out": "folder_move_out.svg",
    "folder_tag": "folder_tag.svg",
}

# Built on first use; None means it has not been asked for yet.
_icons = None
_build_queued = [False]


def build():
    """Load the icons into a collection of their own, now."""
    global _icons
    if _icons is None:
        _icons = bpy.utils.previews.new()
    for name, file_name in FILE_NAMES.items():
        path = ICON_FOLDER / file_name
        if path.is_file() and name not in _icons:
            _icons.load(name, str(path), "IMAGE")
    return _icons


def _build_later():
    _build_queued[0] = False
    build()
    # The panel that asked has already been drawn without them, so it is told to draw again.
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            area.tag_redraw()
    return None


def ensure():
    """Ask for the icons, and say whether they are there yet.

    The first call comes from a panel being drawn, which is late enough for the previews to work and is far
    too early to be loading images in - so the building itself is put on a timer, and the draw that asked
    falls back to one of Blender's own icons for that one frame.
    """
    if _icons is not None:
        return True
    if not _build_queued[0]:
        _build_queued[0] = True
        bpy.app.timers.register(_build_later, first_interval=0.0)
    return False


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
    ensure()
    preview = icon_id(name)
    return {"icon_value": preview} if preview else {"icon": fallback}
