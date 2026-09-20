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
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, StringProperty

from .common import (
    ROOT_FOLDER_ID,
    get_active_object,
    make_folder_uid_in,
    make_unique_folder_name_in,
    mirror_name,
    plan_assignment_renames,
)


# The list-kind adapters live in kinds.py and the folder drawing helpers in
# folder_ui.py. Their names are re-exported here because vertex_groups.py,
# shape_keys.py and tests/smoke_test.py all address them through this module.
from .folder_ui import (  # noqa: F401  (re-exported names)
    draw_folder_actions,
    draw_folder_controls,
    draw_folder_item,
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
    """Everything a folder carries, in list order."""
    return [
        (folder.name, folder.uid, folder.visible, folder.isolate)
        for folder in folders
    ]


def write_folder_state(folders, state):
    """Replace the folder list with ``state`` (clear + add again)."""
    folders.clear()
    for name, uid, visible, isolate in state:
        folder = folders.add()
        folder.name = name
        folder.uid = uid
        folder.visible = visible
        folder.isolate = isolate


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

    settings = kind.settings(data)
    active_folder_uid = settings.active_folder_uid
    show_all_folders = settings.show_all_folders

    state = folder_state(folders)
    state.insert(target, state.pop(index))
    write_folder_state(folders, state)

    # Writing the flags above fires the folder update callbacks, so put the view
    # state back where the user had it.
    kind.set_folder_index(data, target)
    settings.active_folder_uid = active_folder_uid
    settings.show_all_folders = show_all_folders
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


def get_member_folder_uids(data, kind, member_name):
    """The folders this member is filed in; empty means unfiled."""
    assignment = get_assignment(data, kind, member_name)
    if assignment is None:
        return []
    # One pass over the folders instead of one per recorded uid: the folder list is
    # RNA, and re-entering it for every uid is both slower and more chances to walk a
    # collection while something else is looking at it.
    known = {folder.uid for folder in kind.folders(data)}
    known.add(ROOT_FOLDER_ID)
    return [uid for uid in parse_member_folders(assignment) if uid in known]


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


def apply_assignment_renames(data, kind, remaps):
    for old_name, new_name in remaps:
        assignment = get_assignment(data, kind, old_name)
        if assignment and not get_assignment(data, kind, new_name):
            setattr(assignment, kind.member_name_attr, new_name)


def clean_missing_assignments(data, kind):
    """Drop assignments for gone members, and stale or empty memberships."""
    names = set(kind.member_names(data))
    valid_uids = {folder.uid for folder in kind.folders(data)}
    assignments = kind.assignments(data)
    index = len(assignments) - 1
    while index >= 0:
        assignment = assignments[index]
        uids = parse_member_folders(assignment)
        kept = [uid for uid in uids if uid in valid_uids]
        if getattr(assignment, kind.member_name_attr) not in names or not kept:
            assignments.remove(index)
        elif len(kept) != len(uids):
            write_member_folders(assignment, kept)
        index -= 1


def migrate_legacy_memberships(data, kind):
    """Fold the pre-multi-folder single ``folder_uid`` into the uid set."""
    changed = False
    for assignment in kind.assignments(data):
        legacy = assignment.folder_uid
        if legacy:
            if legacy != ROOT_FOLDER_ID:
                uids = parse_member_folders(assignment)
                if legacy not in uids:
                    write_member_folders(assignment, [*uids, legacy])
            assignment.folder_uid = ""
            changed = True
    return changed


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

    changed = migrate_legacy_memberships(data, kind)
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


def get_visibility_context(data, kind):
    settings = kind.settings(data)
    if settings is None:
        # Linked meshes can come without the settings container; show everything
        # rather than failing every draw that asks what is visible.
        return ("", ROOT_FOLDER_ID, True, set(), False)
    active_folder_uid = settings.active_folder_uid
    if active_folder_uid != ROOT_FOLDER_ID and not ensure_folder(data, kind, active_folder_uid):
        active_folder_uid = ROOT_FOLDER_ID

    isolated_folder_uids = {folder.uid for folder in kind.folders(data) if folder.isolate}
    return (
        settings.search.strip().lower(),
        active_folder_uid,
        settings.show_all_folders,
        isolated_folder_uids,
        settings.invert_filter,
    )


def is_folder_visible_in_all_mode(data, kind, folder_uid):
    if folder_uid == ROOT_FOLDER_ID:
        return True
    folder = get_folder_by_uid(kind.folders(data), folder_uid)
    return folder is None or folder.visible


def is_member_visible(data, kind, member_name, vis=None):
    if not kind.is_listable(data, member_name):
        return False

    if vis is None:
        vis = get_visibility_context(data, kind)
    search, active_folder_uid, show_all, isolated_folder_uids, invert = vis

    # The invert button flips the search only, and only while a search is typed:
    # flipping it with an empty box would otherwise hide the whole list.
    if search and (search in member_name.lower()) == invert:
        return False

    uids = get_member_folder_uids(data, kind, member_name)

    # "Unfiled" is a solo filter of its own: while it is the view it overrides folder
    # solo mode, and it does so without touching the isolate flags - leave "Unfiled"
    # and the folders that were soloed take over again.
    if not show_all and active_folder_uid == ROOT_FOLDER_ID:
        return not uids

    if isolated_folder_uids:
        return bool(set(uids) & isolated_folder_uids)
    if not show_all:
        return active_folder_uid in uids
    # All mode: unfiled members always show, a filed one shows when any of its
    # folders is visible.
    return not uids or any(is_folder_visible_in_all_mode(data, kind, uid) for uid in uids)


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


def ordered_member_names(data, kind):
    """Member names grouped by folder list position, unfiled members last.

    The sort is stable, so members that share a folder keep the order they had;
    sorting the members by name first therefore leaves a folder then name order.
    A member filed in several folders is grouped under its first folder.
    """
    ranks = member_folder_ranks(data, kind)
    return sorted(kind.member_names(data), key=lambda name: ranks[name])


def member_folder_ranks(data, kind):
    """Folder list position of every member; unfiled members come after them all."""
    folder_ranks = {folder.uid: index for index, folder in enumerate(kind.folders(data))}
    unfiled_rank = len(folder_ranks)

    def rank(name):
        uids = get_member_folder_uids(data, kind, name)
        return min((folder_ranks[uid] for uid in uids), default=unfiled_rank)

    return {name: rank(name) for name in kind.member_names(data)}


def member_display_order(data, kind, items):
    """The UIList order array that shows ``items`` grouped by folder.

    Blender's ``filter_items`` wants a mapping **original index -> new
    position** (see the UI template: "the new indices of the items"), so the
    result is indexed like ``items`` and holds each item's display slot.
    """
    position = {name: slot for slot, name in enumerate(ordered_member_names(data, kind))}
    return [position.get(item.name, index) for index, item in enumerate(items)]


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


# --------------------------------------------------- property update callbacks


def update_folder_visible(folder, context, kind):
    """``visible`` changed: with nothing isolated, show every folder again."""
    data = folder.id_data
    if any(item.isolate for item in kind.folders(data)):
        return
    kind.settings(data).show_all_folders = True


# --------------------------------------------------------------- operator half


class FolderOperator:
    """Common plumbing for the folder operators; subclasses set ``kind``.

    The per-module classes only carry ``bl_idname`` / ``bl_label`` /
    ``bl_description`` and the kind, so the behaviour lives in one place.
    """

    kind = None
    bl_options = {"REGISTER", "UNDO"}

    def target(self, context):
        obj = get_active_object(context)
        if obj is None:
            return None, None
        data = self.kind.data_of(obj)
        if not is_editable(data):
            # Every folder operator writes, so a linked mesh gets none of them.
            return None, None
        return obj, data


class GroupByFolderOperator(FolderOperator):
    """Toggles the display only folder order of the member list."""

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}
        settings = self.kind.settings(data)
        settings.group_by_folder = not settings.group_by_folder
        tag_redraw()
        return {"FINISHED"}


class FolderAddOperator(FolderOperator):
    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        sync_assignment_names(data, self.kind)
        folder = get_or_create_folder(data, self.kind, "")
        # Focus the new row so it can be renamed right away, but leave the view
        # alone. Switching to the new (empty) folder emptied the list and left
        # neither "All" nor "Unfiled" pressed, which reads as a broken filter.
        focus_folder(data, self.kind, folder)
        return {"FINISHED"}


class FolderRemoveOperator(FolderOperator):
    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        folders = self.kind.folders(data)
        if not folders:
            return {"CANCELLED"}

        index = max(0, min(self.kind.folder_index(data), len(folders) - 1))
        folder = folders[index]
        folder_uid = folder.uid
        # Read the flag before the folder goes away: removing it frees the group.
        was_isolated = folder.isolate
        for assignment in self.kind.assignments(data):
            uids = parse_member_folders(assignment)
            if folder_uid in uids:
                write_member_folders(assignment, [uid for uid in uids if uid != folder_uid])

        folders.remove(index)
        clean_missing_assignments(data, self.kind)
        self.kind.set_folder_index(data, min(index, max(0, len(folders) - 1)))

        settings = self.kind.settings(data)
        if was_isolated:
            # Any number of folders can be isolated at once, so deleting one only
            # drops it from that set: follow whatever is still isolated (the view is
            # their union) and fall back to "All" only once none is left. Turning
            # "All" on while another folder is isolated would show both states at once.
            remaining = next((item for item in folders if item.isolate), None)
            settings.active_folder_uid = remaining.uid if remaining else ROOT_FOLDER_ID
            settings.show_all_folders = remaining is None
        elif settings.active_folder_uid == folder_uid:
            # The view pointed at the folder that just went away, so it has to move;
            # in every other case the view is left exactly as the user had it.
            settings.active_folder_uid = ROOT_FOLDER_ID
            settings.show_all_folders = True
        return {"FINISHED"}


class FolderMoveOperator(FolderOperator):
    direction: StringProperty(default="UP")
    folder_uid: StringProperty()

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}
        if not move_folder(data, self.kind, self.direction, self.folder_uid):
            return {"CANCELLED"}
        return {"FINISHED"}


class FolderSelectOperator(FolderOperator):
    folder_uid: StringProperty()
    show_all: BoolProperty(default=False)

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        settings = self.kind.settings(data)
        # "All" and picking a single folder leave solo mode - while a folder is
        # isolated the view is that folder's, so they would otherwise do nothing at
        # all. "Unfiled" deliberately does not touch it: as a solo filter of its own it
        # overrides the isolated folders for as long as it is the view, and the folders
        # that were soloed take over again once "Unfiled" is left.
        isolated = any(folder.isolate for folder in self.kind.folders(data))
        # "All" only counts as "already showing" while nothing is isolated, so its first
        # press during solo is still the one that drops solo.
        already_all = settings.show_all_folders and not isolated
        already_unfiled = (
            not settings.show_all_folders
            and settings.active_folder_uid == ROOT_FOLDER_ID
        )

        if self.show_all:
            for folder in self.kind.folders(data):
                folder.isolate = False
            # "All" leaves the per-folder hide switches alone; pressing it again while
            # it is already the view is what turns every folder back on, so the two
            # steps stay separate.
            if already_all:
                for folder in self.kind.folders(data):
                    folder.visible = True
            settings.active_folder_uid = self.folder_uid
            settings.show_all_folders = True
            return {"FINISHED"}

        if self.folder_uid == ROOT_FOLDER_ID:
            # Isolating "Unfiled" only writes the condition, never the isolate flags:
            # they stay exactly as they were and take the list back the moment this
            # view is left.
            if already_unfiled:
                # Pressing it again while it is already the view returns to "All" -
                # with any solo that was on still on, and driving the list again.
                settings.show_all_folders = True
                return {"FINISHED"}
            settings.active_folder_uid = ROOT_FOLDER_ID
            settings.show_all_folders = False
            return {"FINISHED"}

        for folder in self.kind.folders(data):
            folder.isolate = False
        settings.active_folder_uid = self.folder_uid
        settings.show_all_folders = False
        return {"FINISHED"}


class FolderToggleVisibilityOperator(FolderOperator):
    folder_uid: StringProperty()

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        folder = get_folder_by_uid(self.kind.folders(data), self.folder_uid)
        if not folder:
            return {"CANCELLED"}

        folder.visible = not folder.visible
        return {"FINISHED"}


class FolderIsolateOperator(FolderOperator):
    folder_uid: StringProperty()

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        folder = get_folder_by_uid(self.kind.folders(data), self.folder_uid)
        if not folder:
            return {"CANCELLED"}

        folder.isolate = not folder.isolate
        return {"FINISHED"}


class FolderAssignOperator(FolderOperator):
    """File the active member into a folder, keeping its other folders."""

    folder_uid: StringProperty()

    def execute(self, context):
        obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        sync_assignment_names(data, self.kind)
        member = self.kind.active_member(data, obj)
        if member is None or not self.kind.is_listable(data, member.name):
            return {"CANCELLED"}
        if add_member_to_folder(data, self.kind, member.name, self.folder_uid) is None:
            return {"CANCELLED"}

        self.kind.focus_member(data, obj, member)
        return {"FINISHED"}


class FolderRemoveMemberOperator(FolderOperator):
    """Take the active member out of one folder."""

    folder_uid: StringProperty()

    def execute(self, context):
        obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        sync_assignment_names(data, self.kind)
        member = self.kind.active_member(data, obj)
        if member is None or not self.kind.is_listable(data, member.name):
            return {"CANCELLED"}
        if not remove_member_from_folder(data, self.kind, member.name, self.folder_uid):
            return {"CANCELLED"}

        clean_missing_assignments(data, self.kind)
        self.kind.focus_member(data, obj, member)
        return {"FINISHED"}


class FolderMoveFilteredOperator(FolderOperator):
    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        folders = self.kind.folders(data)
        if not folders:
            return {"CANCELLED"}

        sync_assignment_names(data, self.kind)
        index = max(0, min(self.kind.folder_index(data), len(folders) - 1))
        folder = folders[index]
        members = get_visible_members(data, self.kind)
        for member in members:
            add_member_to_folder(data, self.kind, member.name, folder.uid)

        for item in folders:
            item.isolate = False
        settings = self.kind.settings(data)
        settings.active_folder_uid = folder.uid
        settings.show_all_folders = False
        self.report({"INFO"}, iface_(self.kind.moved_message).format(len(members), folder.name))
        return {"FINISHED"}
