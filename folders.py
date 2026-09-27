"""Shared folder machinery for the vertex group and shape key organizers.

Both organizers are the same idea twice: a list of names (vertex groups, shape
keys) that the user files into folders, filters by name, isolates and bulk-edits.
The generic half lives here; :data:`VERTEX_GROUPS` and :data:`SHAPE_KEYS` describe
how to reach each list, and ``vertex_groups.py`` / ``shape_keys.py`` are thin
wrappers around them.

Two words are used throughout:

``obj``
    the mesh object the panel is showing.
``data``
    the ID that owns ``*_folders`` / ``*_assignments`` / ``*_settings``: the
    object itself for vertex groups, the mesh for shape keys, because that is
    where Blender keeps shape keys.
"""

import bpy

from typing import NamedTuple
from bpy.app.translations import pgettext_iface as iface_

import fnmatch

from .common import (
    ROOT_FOLDER_ID,
    make_folder_uid_in,
    make_unique_folder_name_in,
    mirror_name,
    plan_assignment_renames,
)


# The list-kind adapters live in kinds.py and the folder drawing helpers in
# folder_ui.py. Their names are re-exported here because vertex_groups.py,
# shape_keys.py and tests/smoke_test.py all address them through this module.
from .folder_ui import (  # noqa: F401  (re-exported names)
    draw_active_header,
    draw_folder_controls,
    draw_folder_item,
    draw_folder_list_header,
    draw_folder_tag_popup,
    draw_member_list_header,
    draw_organize_actions,
)
from .kinds import (  # noqa: F401  (re-exported names)
    FILTER_MENU_DESCRIPTION,
    LIST_MAX_ROWS,
    SHAPE_KEYS,
    VERTEX_GROUPS,
    ShapeKeyKind,
    VertexGroupKind,
    _MESH_MEMBER_OWNER,
    is_editable,
    mesh_member_owner,
)


# --------------------------------------------------------------------- folders


def get_folder_by_name(folders, name):
    for folder in folders:
        if folder.name == name:
            return folder
    return None


def get_folder_by_uid(folders, folder_uid):
    for folder in folders:
        if folder.uid == folder_uid:
            return folder
    return None


def get_or_create_folder(data, kind, name):
    folders = kind.folders(data)
    name = (name or "").strip()
    if name:
        folder = get_folder_by_name(folders, name)
        if folder:
            return folder

    unique_name = make_unique_folder_name_in(folders, name)
    folder = folders.add()
    folder.name = unique_name
    folder.uid = make_folder_uid_in(folders)
    kind.set_folder_index(data, len(folders) - 1)
    return folder


def focus_folder(data, kind, folder):
    for index, item in enumerate(kind.folders(data)):
        if item.uid == folder.uid:
            kind.set_folder_index(data, index)
            return


def get_selected_folder(data, kind):
    folders = kind.folders(data)
    if not folders:
        return None
    index = max(0, min(kind.folder_index(data), len(folders) - 1))
    return folders[index]


def ensure_folder(data, kind, folder_uid):
    if folder_uid == ROOT_FOLDER_ID:
        return True
    return any(folder.uid == folder_uid for folder in kind.folders(data))


def reveal_new_member(data, kind):
    """Turn *Unfiled* on and clear every solo, so a member that was just created can be seen.

    A new member has no folder yet, so with Unfiled off it is invisible the moment it is made, and a folder
    that is soloed hides everything outside it. Neither switch was turned off by this action, so nothing else
    about the view is touched: the search box and the hidden folders stay as they are, and a member the search
    still filters out is what the scroll button is for.
    """
    settings = kind.settings(data)
    if settings is not None:
        settings.show_unfiled = True
    for folder in kind.folders(data):
        if folder.isolate:
            folder.isolate = False


def tag_redraw():
    """Ask every window to redraw the UI.

    ``bpy_prop_collection.move()`` shuffles the folder list without emitting the
    notification Blender would repaint a panel on, so a reordered folder list
    stayed exactly as it was drawn until something unrelated redrew it. Tagging
    the areas from the operator that did the move fixes that.
    """
    window_manager = getattr(bpy.context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()):
        for area in window.screen.areas:
            area.tag_redraw()


def folder_state(folders):
    """Everything a folder carries, in list order.

    Read off the RNA rather than from a hand-written list of field names: a list like that is what let the
    tag palette be silently dropped every time a folder was moved up or down.
    """
    return [
        {
            prop.identifier: getattr(folder, prop.identifier)
            for prop in folder.bl_rna.properties
            if prop.identifier != "rna_type"
            and not prop.is_readonly
            and prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}
        }
        for folder in folders
    ]


def write_folder_state(folders, state):
    """Replace the folder list with ``state`` (clear + add again).

    Only fields that differ from what the fresh entry starts with are written, so an update callback (the tag
    palette has one, to repaint the panels) does not fire for folders whose value did not really change.
    """
    folders.clear()
    for fields in state:
        folder = folders.add()
        for name, value in fields.items():
            if getattr(folder, name) != value:
                setattr(folder, name, value)


def move_folder(data, kind, direction, folder_uid=""):
    """Move the selected folder one slot up or down; False at the ends.

    The list is rewritten from a snapshot rather than shuffled with
    ``bpy_prop_collection.move()``. A raw move only permutes the property array
    and tells the UI nothing, so the folder list kept drawing the old order;
    clearing and adding again goes through the same notifications as the add and
    remove buttons, which the panels do repaint for. Folder uids travel with the
    snapshot, so assignments and the active folder survive untouched.
    """
    folders = kind.folders(data)
    count = len(folders)
    if count < 2:
        return False

    index = kind.folder_index(data)
    if folder_uid:
        for position, folder in enumerate(folders):
            if folder.uid == folder_uid:
                index = position
                break
    index = max(0, min(index, count - 1))
    target = index - 1 if direction == "UP" else index + 1
    if not 0 <= target < count:
        return False

    state = folder_state(folders)
    state.insert(target, state.pop(index))
    write_folder_state(folders, state)

    kind.set_folder_index(data, target)
    # An Object lives in the Object Data tab but is not mesh data, so hint at the
    # refresh kind that makes that editor repaint. Only objects accept the
    # refresh argument, meshes reject it ("not compatible with refresh options").
    if isinstance(data, bpy.types.Object):
        data.update_tag(refresh={"OBJECT"})
    else:
        data.update_tag()
    tag_redraw()
    return True


# ------------------------------------------------------- membership and names
#
# A member can be filed in any number of folders, so an assignment stores a set
# of folder uids. An empty set means *Unfiled*, which is why memberships are
# pruned instead of pointing at a root folder.

MEMBERSHIP_SEPARATOR = "\n"


def parse_member_folders(assignment):
    """Folder uids stored on one assignment, in insertion order."""
    return [uid for uid in (assignment.folder_uids or "").split(MEMBERSHIP_SEPARATOR) if uid]


def write_member_folders(assignment, uids):
    assignment.folder_uids = MEMBERSHIP_SEPARATOR.join(dict.fromkeys(uids))


def get_assignment(data, kind, member_name, create=False):
    assignments = kind.assignments(data)
    attribute = kind.member_name_attr
    for item in assignments:
        if getattr(item, attribute) == member_name:
            return item

    if create:
        if not assignments:
            # First tracked member on this ID: remember today's names as the
            # baseline. The sync fast-path skips IDs without assignments, so
            # without this a rename could never be recognised on them.
            setattr(kind.settings(data), kind.snapshot_attr, "\n".join(kind.member_names(data)))
        item = assignments.add()
        setattr(item, attribute, member_name)
        return item

    return None


def get_member_folder_uids(data, kind, member_name, vis=None):
    """The folders this member is filed in; empty means unfiled."""
    if vis is None:
        vis = get_visibility_context(data, kind)
    return [uid for uid in vis.assignment_folders.get(member_name, ()) if uid in vis.folder_uids]


def add_member_to_folder(data, kind, member_name, folder_uid):
    """File a member into a folder, keeping its other folders."""
    if folder_uid == ROOT_FOLDER_ID or not ensure_folder(data, kind, folder_uid):
        return None
    assignment = get_assignment(data, kind, member_name, create=True)
    uids = parse_member_folders(assignment)
    if folder_uid not in uids:
        write_member_folders(assignment, [*uids, folder_uid])
    return assignment


def remove_member_from_folder(data, kind, member_name, folder_uid):
    """Take a member out of one folder; False when it was not in it."""
    assignment = get_assignment(data, kind, member_name)
    if assignment is None:
        return False
    uids = parse_member_folders(assignment)
    if folder_uid not in uids:
        return False
    write_member_folders(assignment, [uid for uid in uids if uid != folder_uid])
    return True


def copy_folders_to_data(source_data, target_data, kind):
    """Merge one ID's folders into another and file its same-named members.

    Folders are matched by uid, so running this twice duplicates nothing: a folder the
    target already has is left exactly as it is - its hide and solo switches stay the
    user's - and only a missing one is added, carrying the source's name and flags.
    A member is filed only when the target has one of that name, and nothing on the
    target is ever removed. Returns how many folders were added.
    """
    added = 0
    for folder in kind.folders(source_data):
        target_folders = kind.folders(target_data)
        if get_folder_by_uid(target_folders, folder.uid) is not None:
            continue
        moved = target_folders.add()
        # Every field copies over; the name is made unique in the target first. Read off the RNA, the way the
        # move snapshot is: a hand-written list of fields is what used to drop the tag palette here too.
        for field, value in folder_state([folder])[0].items():
            if field == "name":
                value = make_unique_folder_name_in(target_folders, value)
            if getattr(moved, field) != value:
                setattr(moved, field, value)
        added += 1

    for assignment in kind.assignments(source_data):
        name = getattr(assignment, kind.member_name_attr)
        if kind.member_by_name(target_data, name) is None:
            continue
        for folder_uid in parse_member_folders(assignment):
            add_member_to_folder(target_data, kind, name, folder_uid)
    return added


def apply_assignment_renames(data, kind, remaps):
    for old_name, new_name in remaps:
        assignment = get_assignment(data, kind, old_name)
        if assignment and not get_assignment(data, kind, new_name):
            setattr(assignment, kind.member_name_attr, new_name)


def folder_row_sets(data, kind, member_name):
    """The folders ``member_name`` is in, and every folder that holds anyone at all.

    Both come out of one pass over the assignments, which is what the membership arrow alone used to cost.
    They cannot be kept between rows: Blender calls each UIList hook on a fresh instance, so nothing a row
    sets on itself is there for the row after it - and a module-level cache is no use either, because
    ``filter_items`` runs between the rows and would have to drop it every time.
    """
    held = set()
    used = set()
    for assignment in kind.assignments(data):
        uids = parse_member_folders(assignment)
        used.update(uids)
        if getattr(assignment, kind.member_name_attr) == member_name:
            held.update(uids)
    return held, used


def clean_missing_assignments(data, kind):
    """Drop assignments for gone members, and the ones that hold nothing at all.

    A record with no folder is only empty while its pick mark is the default. A member unpicked in organize
    mode keeps its record for that mark alone, and dropping it would quietly pick the member again - which
    is exactly what a pass over the list would then do to it.
    """
    names = set(kind.member_names(data))
    valid_uids = {folder.uid for folder in kind.folders(data)}
    assignments = kind.assignments(data)
    index = len(assignments) - 1
    while index >= 0:
        assignment = assignments[index]
        uids = parse_member_folders(assignment)
        kept = [uid for uid in uids if uid in valid_uids]
        if getattr(assignment, kind.member_name_attr) not in names:
            assignments.remove(index)
        elif not kept and assignment.picked:
            assignments.remove(index)
        elif len(kept) != len(uids):
            write_member_folders(assignment, kept)
        index -= 1


def sync_assignment_names(data, kind):
    """Follow renames and removals; True when assignments changed.

    IDs without assignments have nothing to follow, clean up or snapshot, so
    they bail out before touching any names: that early return is what keeps the
    depsgraph handler affordable, since most IDs in a scene never use this
    add-on.
    """
    if data is None or not kind.assignments(data):
        return False
    if not is_editable(data):
        # Linked data cannot be re-filed, and its snapshot is not ours to write.
        return False

    changed = False
    settings = kind.settings(data)
    names = kind.member_names(data)
    snapshot = "\n".join(names)
    previous = getattr(settings, kind.snapshot_attr)
    if previous != snapshot:
        apply_assignment_renames(data, kind, plan_assignment_renames(previous.split("\n") if previous else [], names))
        clean_missing_assignments(data, kind)
        setattr(settings, kind.snapshot_attr, snapshot)
        changed = True
    return changed


# ------------------------------------------------------------------ visibility


class VisibilityContext(NamedTuple):
    """Everything one pass over a list needs in order to decide what to show.

    Built once per draw and handed to every member. Deriving it per member instead is what turned a linear
    pass quadratic: the folder uid set was rebuilt for every name, and each name's assignment was found by
    scanning the whole assignment collection.
    """

    search: str
    show_filed: bool
    show_unfiled: bool
    isolated: frozenset
    invert: bool
    folder_uids: frozenset
    shown_folders: frozenset
    assignment_folders: dict


def get_visibility_context(data, kind):
    settings = kind.settings(data)
    if settings is None:
        # Linked meshes can come without the settings container; show everything
        # rather than failing every draw that asks what is visible.
        return VisibilityContext("", True, True, frozenset(), False, frozenset(), frozenset(), {})

    folders_ = kind.folders(data)
    isolated = frozenset(folder.uid for folder in folders_ if folder.isolate)
    shown_folders = frozenset(folder.uid for folder in folders_ if folder.visible)
    # Keyed by member name so a lookup replaces a scan; ROOT_FOLDER_ID is kept because assignments written
    # before folders lived on the mesh may still point at it, and dropping it would silently unfiled them.
    assignment_folders = {
        getattr(item, kind.member_name_attr): parse_member_folders(item)
        for item in kind.assignments(data)
    }
    return VisibilityContext(
        settings.search.strip().lower(),
        settings.show_filed,
        settings.show_unfiled,
        isolated,
        settings.invert_filter,
        frozenset(folder.uid for folder in folders_) | {ROOT_FOLDER_ID},
        shown_folders,
        assignment_folders,
    )


def has_isolated_folder(data, kind):
    """Whether any folder is soloed.

    Solo overrides both view switches while it lasts, so this doubles as the answer to "is
    the Unfiled switch doing anything right now?" - the panels dim it while it is not.
    """
    return any(folder.isolate for folder in kind.folders(data))


def name_matches_search(search, member_name):
    """Whether a name matches the search box, the way Blender's own list filter does.

    The pattern is wrapped in stars, so a plain word still matches anywhere in the name - which is what the
    box did before - and ``*`` and ``?`` work as well, exactly like the search box Blender draws under a
    list of its own. Both sides are lowercased already, so the match is case-insensitive.
    """
    return fnmatch.fnmatchcase(member_name.lower(), f"*{search}*")


def is_member_visible(data, kind, member_name, vis=None):
    if not kind.is_listable(data, member_name):
        return False

    if vis is None:
        vis = get_visibility_context(data, kind)

    # The invert button flips the search only, and only while a search is typed:
    # flipping it with an empty box would otherwise hide the whole list.
    if vis.search and name_matches_search(vis.search, member_name) == vis.invert:
        return False

    uids = set(get_member_folder_uids(data, kind, member_name, vis=vis))

    # A soloed folder is the narrowest and most temporary condition there is, so it overrides
    # both view switches: while it lasts the list is the soloed folders and nothing else.
    # Unfiled members go with the rest - a folder is soloed to look at what is *in* it, and
    # the unfiled pile is usually the largest, least organized half of the list.
    if vis.isolated:
        return bool(uids & vis.isolated)

    # Unfiled members answer to the "Unfiled" switch and to nothing else - no folder is
    # involved in showing them, so neither hide nor solo takes part.
    if not uids:
        return vis.show_unfiled
    if not vis.show_filed:
        return False
    return bool(uids & vis.shown_folders)


def get_visible_members(data, kind):
    vis = get_visibility_context(data, kind)
    # Filter against a snapshot of the names first: is_member_visible() reads several
    # RNA collections of its own, and feeding it members straight out of an iterator
    # over another collection means walking a list that something else is touching.
    visible = set()
    for name in kind.member_names(data):
        if is_member_visible(data, kind, name, vis=vis):
            visible.add(name)
    return [member for member in kind.members(data) if member.name in visible]


def get_visible_member_names(data, kind):
    return [member.name for member in get_visible_members(data, kind)]


def listable_member_names(data, kind):
    """Every member the list could show, before any filter: the half a count is measured against.

    The basis of a shape key list is not listable, so it stays out of both halves of the count - the same
    reason it is never a row of the list.
    """
    return [name for name in kind.member_names(data) if kind.is_listable(data, name)]


def ordered_member_names(data, kind, vis=None):
    """Member names grouped by folder list position, unfiled members last.

    The sort is stable, so members that share a folder keep the order they had;
    sorting the members by name first therefore leaves a folder then name order.
    A member filed in several folders is grouped under its first folder.
    """
    ranks = member_folder_ranks(data, kind, vis=vis)
    return sorted(kind.member_names(data), key=lambda name: ranks[name])


def member_folder_ranks(data, kind, vis=None):
    """Folder list position of every member; unfiled members come after them all.

    A uid the folder list does not know counts as unfiled rather than raising. An assignment written before
    folders lived on the mesh can still name the root sentinel - ``get_member_folder_uids`` keeps it, because
    dropping it would silently unfile the member - and looking that uid up in the rank table threw a KeyError
    from the middle of a draw.

    The visibility context is taken once and handed down: rebuilding it per member is what turned grouping
    the list by folder into a quadratic pass.
    """
    if vis is None:
        vis = get_visibility_context(data, kind)

    folder_ranks = {folder.uid: index for index, folder in enumerate(kind.folders(data))}
    unfiled_rank = len(folder_ranks)

    def rank(name):
        uids = get_member_folder_uids(data, kind, name, vis=vis)
        return min((folder_ranks[uid] for uid in uids if uid in folder_ranks), default=unfiled_rank)

    return {name: rank(name) for name in kind.member_names(data)}


def member_display_order(data, kind, items, vis=None):
    """The UIList order array that shows ``items`` grouped by folder.

    Blender's ``filter_items`` wants a mapping **original index -> new
    position** (see the UI template: "the new indices of the items"), so the
    result is indexed like ``items`` and holds each item's display slot.
    """
    position = {name: slot for slot, name in enumerate(ordered_member_names(data, kind, vis=vis))}
    return [position.get(item.name, index) for index, item in enumerate(items)]


def visible_row_indices(data, kind):
    """The visible members' indices, in the order the list shows them.

    The scroll buttons hand the list stand-in rows, and those rows have to be ones the list can actually
    see: Blender matches a stand-in against the rows it is showing, and a number it cannot find leaves the
    list with no active row at all - which clamps the scroll to the top, the opposite of what was asked.
    """
    names = kind.member_names(data)
    index_of = {name: position for position, name in enumerate(names)}
    vis = get_visibility_context(data, kind)
    return [
        index_of[name]
        for name in ordered_member_names(data, kind, vis=vis)
        if name in index_of and is_member_visible(data, kind, name, vis=vis)
    ]


def reveal_member(data, kind, member_name):
    """Undo what keeps ``member_name`` out of the list, by the smallest change that does it.

    Returns one note per change, in the order they were made, and an empty list when the member was visible
    already. The changes are the folder view state, the two switches and the search box - nothing about the
    member itself.

    Solo is the one case with no folder to open: it shows only the folders it names and hides the unfiled
    pile outright, so the member's own folder is soloed - or, for a member with no folder at all, the solo
    is dropped, there being nothing else that would let it through.
    """
    notes = []
    settings = kind.settings(data)
    if settings is None:
        return notes

    vis = get_visibility_context(data, kind)
    if is_member_visible(data, kind, member_name, vis=vis):
        return notes

    if vis.search:
        settings.search = ""
        notes.append(iface_("cleared the search"))
        vis = get_visibility_context(data, kind)
        if is_member_visible(data, kind, member_name, vis=vis):
            return notes

    uids = get_member_folder_uids(data, kind, member_name, vis=vis)
    member_folders = [folder for folder in kind.folders(data) if folder.uid in uids]

    if has_isolated_folder(data, kind):
        if member_folders:
            candidate = member_folders[0]
            if not candidate.isolate:
                candidate.isolate = True
                notes.append(iface_("soloed {}").format(candidate.name))
        else:
            for folder in kind.folders(data):
                folder.isolate = False
            notes.append(iface_("cleared the solo"))
    elif member_folders:
        hidden = [folder for folder in member_folders if not folder.visible]
        if hidden:
            hidden[0].visible = True
            notes.append(iface_("showed {}").format(hidden[0].name))

    if uids and not settings.show_filed:
        settings.show_filed = True
        notes.append(iface_("turned Filed on"))
    if not uids and not settings.show_unfiled:
        settings.show_unfiled = True
        notes.append(iface_("turned Unfiled on"))

    return notes


def is_member_picked(data, kind, member_name):
    """Whether a member is picked; one with no record yet counts as picked."""
    assignment = get_assignment(data, kind, member_name)
    return True if assignment is None else assignment.picked


def ensure_picked_records(data, kind):
    """Give every visible member an assignment record, so its pick button has something to write to.

    The mark cannot live on the member itself - a vertex group and a shape key carry no properties of their
    own - and a row button has to be a real property to be pressed and dragged across rows. Members without
    a record already read as picked, so this only makes that state drawable, and only on entering organize
    mode rather than on every draw.
    """
    for name in get_visible_member_names(data, kind):
        get_assignment(data, kind, name, create=True)


def picked_member_names(data, kind):
    """The picked members that are visible too - what the bulk actions work on.

    Visibility takes part on purpose: a member the search box or a folder hides is not on screen, so it is
    not part of what is being worked on. Its own mark is left untouched, so it takes part again as soon as it
    is back in view.
    """
    marks = {getattr(item, kind.member_name_attr): item.picked for item in kind.assignments(data)}
    vis = get_visibility_context(data, kind)
    return [
        name
        for name in ordered_member_names(data, kind, vis=vis)
        if marks.get(name, True) and is_member_visible(data, kind, name, vis=vis)
    ]


def set_picked(data, kind, names, picked):
    """Set the pick mark of the given members."""
    for name in names:
        get_assignment(data, kind, name, create=True).picked = picked


def get_active_visible_member(data, kind, obj):
    active = kind.active_member(data, obj)
    if not active or not is_member_visible(data, kind, active.name):
        return None
    return active


def get_active_member_pair(data, kind, obj):
    """The active member plus its left/right counterpart, when it has one."""
    active = kind.active_member(data, obj)
    if not active:
        return []

    members = [active]
    mirrored = mirror_name(active.name)
    if mirrored:
        partner = kind.member_by_name(data, mirrored)
        if partner is not None and partner != active:
            members.append(partner)
    return members


# Tag first: ``folder_ops`` imports four names from this module, two of which arrive with the tag module
# below, so the tag re-export has to run before the operator one.
from .folder_tags import (  # noqa: F401  (re-exported names)
    _FOLDER_TAG_ICON_SET,
    FOLDER_TAG_GROUPS,
    FOLDER_TAG_ICONS,
    FOLDER_TAG_IDS,
    folder_tag_icon,
    folder_tag_items,
    get_member_tag_folder,
)
from .folder_ops import (  # noqa: F401  (re-exported names)
    GroupByFolderOperator,
    FolderAddOperator,
    FolderRemoveOperator,
    FolderMoveOperator,
    FolderViewSwitchOperator,
    FolderUnhideAllOperator,
    FolderClearSoloOperator,
    FolderTagOperator,
    FolderCopyToSelectedOperator,
    FolderToggleVisibilityOperator,
    FolderIsolateOperator,
    FolderAssignOperator,
    FolderRemoveMemberOperator,
    FolderMoveFilteredOperator,
    OrganizeOperator,
    MovePickedOperator,
    RemovePickedOperator,
    InvertPickedOperator,
    PickAllOperator,
    ClearPickedOperator,
)
