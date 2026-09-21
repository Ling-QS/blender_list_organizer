"""The folder operators, split out of ``folders.py``.

Each one is a thin subclass of :class:`FolderOperator`, which holds the shared plumbing: finding the target
data block, refusing linked data, and speaking to both list kinds. They live apart from the data layer on
purpose - ``folders.py`` reads and writes folders and memberships and knows nothing about operators, while
this module drives it.

``folders.py`` imports these names back, so the organizers and the tests keep importing them from there.
"""

from bpy.app.translations import pgettext_iface as iface_
from bpy.props import EnumProperty, StringProperty

from .common import get_active_object

# Imported from ``folders`` rather than the other way round: ``folders`` imports this module at the very end
# of its own file, by which point every name below already exists, so the cycle resolves at import time.
from .folders import (
    _FOLDER_TAG_ICON_SET,
    add_member_to_folder,
    clean_missing_assignments,
    copy_folders_to_data,
    focus_folder,
    folder_tag_items,
    get_folder_by_uid,
    get_or_create_folder,
    get_selected_folder,
    get_visible_members,
    is_editable,
    move_folder,
    parse_member_folders,
    remove_member_from_folder,
    sync_assignment_names,
    tag_redraw,
    write_member_folders,
)


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
            # Every folder operator writes, so a linked mesh gets none of them - and it says
            # why, because a button that only ever cancels looks broken.
            self.report({"WARNING"}, iface_("Linked data: folders are read-only."))
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
        folder_uid = folders[index].uid
        for assignment in self.kind.assignments(data):
            uids = parse_member_folders(assignment)
            if folder_uid in uids:
                write_member_folders(assignment, [uid for uid in uids if uid != folder_uid])

        folders.remove(index)
        clean_missing_assignments(data, self.kind)
        self.kind.set_folder_index(data, min(index, max(0, len(folders) - 1)))
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


class FolderViewSwitchOperator(FolderOperator):
    """One of the two view switches: it flips its own flag and nothing else.

    "Filed" and "Unfiled" are independent - either or both can be on - and neither of
    them touches a folder switch, so hiding or soloing a folder is a separate decision
    that survives any number of view changes. Turning the last switch off would leave
    an empty list, which is never what a click on a view switch means, so the view is
    handed to the other half instead: switching "Filed" off while "Unfiled" is already
    off turns "Unfiled" on.
    """

    attr = ""
    other_attr = ""

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        settings = self.kind.settings(data)
        value = not getattr(settings, self.attr)
        setattr(settings, self.attr, value)
        if not value and not getattr(settings, self.other_attr):
            setattr(settings, self.other_attr, True)
        return {"FINISHED"}


class FolderUnhideAllOperator(FolderOperator):
    """Turn the hide switch of every folder back on."""

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        for folder in self.kind.folders(data):
            folder.visible = True
        return {"FINISHED"}


class FolderClearSoloOperator(FolderOperator):
    """Drop solo from every folder."""

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        for folder in self.kind.folders(data):
            folder.isolate = False
        return {"FINISHED"}


class FolderTagOperator(FolderOperator):
    """Tag the selected folder with one of the palette icons.

    Drawn as a row of icon buttons in the panel rather than in a menu: a menu entry is sized by its
    operator's label and an expanded enum follows the menu's column, so neither gave a compact grid.
    A plain button in a panel is exactly as wide as its icon.
    """

    tag: EnumProperty(items=folder_tag_items())

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        if obj is None:
            return False
        data = cls.kind.data_of(obj)
        return is_editable(data) and get_selected_folder(data, cls.kind) is not None

    def execute(self, context):
        _obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        folder = get_selected_folder(data, self.kind)
        if folder is None:
            return {"CANCELLED"}

        folder.tag = self.tag if self.tag in _FOLDER_TAG_ICON_SET else "NONE"
        return {"FINISHED"}


class FolderCopyToSelectedOperator(FolderOperator):
    """Copy this object's folders onto the other selected mesh objects.

    The point is to set a second object up the same way: the folders come over with
    their flags, and every member the target also has by name lands in the folders the
    source filed it into.
    """

    bl_description = (
        "Copy this object's folders to the other selected objects and file their same-named members"
    )

    @classmethod
    def poll(cls, context):
        # Two objects are the minimum that makes sense, so the menu entry greys itself
        # out instead of failing after the click.
        return len([item for item in context.selected_objects if item.type == "MESH"]) > 1

    def execute(self, context):
        obj, data = self.target(context)
        if data is None:
            return {"CANCELLED"}

        targets = []
        for item in context.selected_objects:
            if item is obj or item.type != "MESH":
                continue
            target_data = self.kind.data_of(item)
            if target_data is None or target_data is data or not is_editable(target_data):
                continue
            targets.append(target_data)
        if not targets:
            self.report(
                {"WARNING"},
                iface_("Select at least one other mesh object to copy the folders to."),
            )
            return {"CANCELLED"}

        added = sum(copy_folders_to_data(data, target_data, self.kind) for target_data in targets)
        self.report(
            {"INFO"},
            iface_("Copied {} folders to {} objects.").format(added, len(targets)),
        )
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

        self.report({"INFO"}, iface_(self.kind.moved_message).format(len(members), folder.name))
        return {"FINISHED"}
