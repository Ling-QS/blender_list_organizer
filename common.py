import difflib
import uuid

import bpy
from bpy.app.translations import pgettext_iface as iface_


ROOT_FOLDER_ID = "__ROOT__"


def get_active_object(context):
    obj = context.object
    if obj and obj.type == "MESH":
        return obj
    return None


_SCROLL_REQUESTS = {}

# How many rows below the top edge the active row is put by *Scroll to Active Group* / *Active Key*.
SCROLL_LANDING_ROW = 5


def scroll_targets(active_index, count):
    """The two stand-in active rows the scroll is taken through, in the order they are used.

    The first is the last row there is. A row at the end is always further down than the list is scrolled,
    so Blender's step brings the list to its end whatever it showed before - which is what the second one
    needs: a list scrolled *below* the landing row is moved by a stand-in above the active row, and the
    step it then takes is "bring that row into view", i.e. exactly to the top edge. Putting the stand-in
    ``SCROLL_LANDING_ROW`` rows above the active row therefore drops the active row that far below the
    top edge, and no list height enters into it. An active row too close to the end for the list to scroll
    that far simply lands as near the top as its scroll range allows.
    """
    return count - 1, max(active_index - SCROLL_LANDING_ROW, 0)


def request_list_scroll(key, area, settings, park, landing):
    """Ask the list drawn for ``key`` to scroll its active row to the landing row.

    Which row a list counts as active is not fixed: it is whatever property the panel hands
    ``template_list`` says, and the list scrolls when that row changes. So the scroll is done by the list
    itself, on stand-in rows, with nothing written to the object and no rows hidden - the trick is only
    which row the list is told about.

    It takes two of them, because the landing row can only be reached by a list that is scrolled below it:
    the first stand-in parks the list at its end, the second lands the active row on the landing row, and
    a third draw hands the list its real active row back. If the list already sits below the landing row
    the park leaves it where it is, and if it is too short to scroll the landing row into place it stays
    as near the top as it can get. The draws are asked for by timer, since nothing else would make them.
    """
    _SCROLL_REQUESTS[key] = 1
    settings.scroll_index = park
    if area is None:
        return

    def redraw():
        more = advance_scroll_request(key, settings, landing)
        _tag_redraw(area)
        return 0.02 if more else None

    bpy.app.timers.register(redraw, first_interval=0.02)


def advance_scroll_request(key, settings, landing):
    """Move a pending request on to its next draw, and say whether another one is still to come."""
    if _SCROLL_REQUESTS.get(key) != 1:
        _SCROLL_REQUESTS.pop(key, None)
        return False
    _SCROLL_REQUESTS[key] = 2
    settings.scroll_index = landing
    return True


def scroll_stage(key):
    """Which stand-in active row a pending scroll request is on, or None for the real one."""
    return _SCROLL_REQUESTS.get(key)


def _tag_redraw(area):
    try:
        area.tag_redraw()
    except ReferenceError:  # the region went away before the timer ran
        pass


def make_unique_folder_name_in(folders, base_name):
    base_name = (base_name or "").strip() or iface_("Folder")
    used = {folder.name for folder in folders}
    if base_name not in used:
        return base_name

    index = 2
    while f"{base_name} {index}" in used:
        index += 1
    return f"{base_name} {index}"


def make_folder_uid_in(folders):
    used = {folder.uid for folder in folders}
    for _ in range(8):
        uid = f"folder_{uuid.uuid4().hex}"
        if uid not in used:
            return uid
    return f"folder_{uuid.uuid4().hex}_{len(used)}"


RENAME_SIMILARITY = 0.5


def names_look_like_rename(old_name, new_name):
    if not old_name or not new_name:
        return False
    return difflib.SequenceMatcher(a=old_name, b=new_name, autojunk=False).ratio() >= RENAME_SIMILARITY


def plan_assignment_renames(old_names, new_names):
    """Pair a renamed member with its new name - and only when that is unambiguous.

    Membership is stored by name and Blender reports no rename, so a rename can only be seen
    as one name disappearing while another appears, which is exactly what a delete plus an add
    looks like too. Only the one-out-one-in shape can be told apart, and only while the two
    names still look alike. Everything else is a guess, and a wrong guess hands one member's
    folders to another, so it is left alone: the two members simply start out unfiled.
    """
    if not old_names or old_names == new_names:
        return []

    old_set = set(old_names)
    new_set = set(new_names)
    disappeared = [name for name in old_names if name not in new_set]
    appeared = [name for name in new_names if name not in old_set]
    if len(disappeared) != 1 or len(appeared) != 1:
        return []

    old_name, new_name = disappeared[0], appeared[0]
    if not names_look_like_rename(old_name, new_name):
        return []
    return [(old_name, new_name)]


MIRROR_SUFFIX_PAIRS = (
    (".L", ".R"),
    (".l", ".r"),
    ("_L", "_R"),
    ("_l", "_r"),
    ("-L", "-R"),
    ("-l", "-r"),
    (" Left", " Right"),
    (" left", " right"),
    ("Left", "Right"),
    ("left", "right"),
    ("左", "右"),
)


def _suffix_starts_a_word(name, start):
    """True when a bare-word match at ``start`` really begins a new word.

    Separator suffixes (``.L``, ``_L``, `` Left``) carry their own boundary and
    never reach this check; it only guards the bare words, so that ``HandLeft``
    and ``Hand.Left`` still mirror while ``Notleft`` does not.
    """
    if start == 0:
        return True
    previous = name[start - 1]
    if previous.isascii() and not previous.isalnum():
        return True
    if previous.islower() and name[start].isupper():
        return True
    return not previous.isascii()


def mirror_name(name):
    """Return the left/right counterpart of ``name``, or "" when it has none."""
    if not name:
        return ""
    for left, right in MIRROR_SUFFIX_PAIRS:
        for suffix, counterpart in ((left, right), (right, left)):
            if not name.endswith(suffix):
                continue
            if suffix[0].isalnum() and not _suffix_starts_a_word(name, len(name) - len(suffix)):
                continue
            return name[: -len(suffix)] + counterpart
    return ""
