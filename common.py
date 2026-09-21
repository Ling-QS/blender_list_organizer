import difflib
import uuid

from bpy.app.translations import pgettext_iface as iface_


ROOT_FOLDER_ID = "__ROOT__"


def get_active_object(context):
    obj = context.object
    if obj and obj.type == "MESH":
        return obj
    return None


_SCROLL_REQUESTS = set()


def request_list_scroll(key):
    """Ask the list drawn for ``key`` to bring its active row into view on the next draw."""
    _SCROLL_REQUESTS.add(key)


def apply_scroll_request(key, flags, order, active_row, rows):
    """Take one row out of ``flags`` so that Blender scrolls the list to its active row.

    A ``template_list`` scrolls to its active row on two conditions only: the number of rows it shows
    changed, or its grip was dragged. The second is out of reach from Python, and the first is why
    re-writing the active index does nothing - the row is already the active one, so nothing about the
    list changed. Shrinking the list by one row for a single frame does reach it, and the next frame puts
    the row back, which triggers the same scroll again and lands in the same place.

    The row taken out is the last one in display order that is not the active row, and the request is
    only acted on when the list is longer than it can show, so the missing row is off screen for the
    frame it is gone. The active row is never the one taken out: a list whose active row is filtered
    away scrolls to the top instead of to the row, which is the opposite of what was asked for.
    """
    if key not in _SCROLL_REQUESTS:
        return False
    _SCROLL_REQUESTS.discard(key)

    if sum(1 for flag in flags if flag) <= rows:
        # The whole list fits, active row included: there is nothing to scroll to.
        return False

    for index in sorted(range(len(order)), key=lambda item: order[item], reverse=True):
        if flags[index] and index != active_row:
            flags[index] = 0
            return True
    return False


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
