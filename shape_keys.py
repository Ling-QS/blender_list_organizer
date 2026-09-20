import bpy

from bpy.app.translations import pgettext_iface as iface_
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Menu, Operator, Panel, PropertyGroup, UIList

from . import folders
from .common import get_active_object
from .folders import (
    FolderAddOperator,
    FolderAssignOperator,
    FolderClearSoloOperator,
    FolderColorOperator,
    FolderCopyToSelectedOperator,
    FolderIsolateOperator,
    FolderMoveFilteredOperator,
    FolderMoveOperator,
    FolderRemoveMemberOperator,
    FolderRemoveOperator,
    FolderToggleVisibilityOperator,
    FolderUnhideAllOperator,
    FolderViewSwitchOperator,
    GroupByFolderOperator,
)

# The sync subsystem lives in sync.py. Its names are re-exported here because
# __init__.py, the panel and the tests all address them through this module.
from .sync import (  # noqa: F401  (re-exported names)
    SKO_SyncSettings,
    _SYNCED_VALUES,
    _SYNC_OBJECT_NAMES,
    _syncing_objects,
    collect_syncing_objects,
    draw_shape_key_sync,
    push_shape_key_values,
    request_sync_registry_rebuild,
    sync_shape_key_values,
)

KIND = folders.SHAPE_KEYS
# Blender's own specials menu for shape keys: our entries are appended to it and
# the panel's menu button opens it, so foreign items added there show up too.
NATIVE_MENU = "MESH_MT_shape_key_context_menu"
# Starting height of the two lists in the panel, in rows.
FOLDER_ROWS = 5
KEY_ROWS = 16
# The deforming-key list is a short read-out rather than the main list, so it starts at
# the folder list's height.
DEFORMING_ROWS = 5

# Width of the icon button column next to the member list, in UI units. The
# basis box above the list is padded by this much so the two line up.
MEMBER_BUTTON_COLUMN_UNITS = 1.0


# The folder, assignment and visibility machinery is shared with the vertex
# group organizer (see folders.py); the wrappers below keep the shape key
# vocabulary that the panels and operators use.


def sko_get_visible_shape_keys(mesh):
    return folders.get_visible_members(mesh, KIND)


def sko_get_visibility_context(mesh):
    return folders.get_visibility_context(mesh, KIND)


def sko_is_shape_key_visible(mesh, key_name, vis=None):
    return folders.is_member_visible(mesh, KIND, key_name, vis=vis)


def sko_get_shape_key_folder_uids(mesh, key_name):
    return folders.get_member_folder_uids(mesh, KIND, key_name)


def sko_get_active_visible_key(obj):
    return folders.get_active_visible_member(obj.data, KIND, obj)


def sko_get_active_key_pair(obj):
    return folders.get_active_member_pair(obj.data, KIND, obj)


def sko_get_deforming_keys(mesh):
    """The keys the mesh is actually showing: unmuted and not sitting at zero.

    Not to be confused with Blender's own "active shape key", which is the one being
    edited: these are the keys deforming the mesh right now. The basis is skipped - it is
    the reference the others are measured against, never an edit of its own.
    """
    if not mesh.shape_keys:
        return []
    return [key for key in mesh.shape_keys.key_blocks[1:] if not key.mute and key.value != 0.0]


def sko_sync_key_flags(mesh):
    """Keep one flag entry per shape key.

    A list row needs a property of its own to draw: pressing a button and dragging it across
    rows is something a ``prop`` widget does and an operator does not, so pinning lives on a
    flag entry rather than on the key. Entries follow renames the same way the assignments do
    - the pairing is planned first, so a renamed key keeps its pin instead of losing it and
    handing it to whichever key took its name. The call is idempotent and does nothing once
    the two lists agree.
    """
    settings = mesh.sko_settings
    if mesh.shape_keys is None or settings is None:
        return

    names = [key.name for key in mesh.shape_keys.key_blocks]
    flags = settings.key_flags

    renames = dict(folders.plan_assignment_renames([flag.shape_key_name for flag in flags], names))
    for flag in flags:
        renamed = renames.get(flag.shape_key_name)
        if renamed is not None:
            flag.shape_key_name = renamed

    wanted = set(names)
    index = 0
    while index < len(flags):
        if flags[index].shape_key_name in wanted:
            wanted.discard(flags[index].shape_key_name)
            index += 1
        else:
            flags.remove(index)
    for name in names:
        if name in wanted:
            wanted.discard(name)
            flags.add().shape_key_name = name


def sko_get_key_flag(mesh, name):
    """The flag entry of one shape key, or None when there is not one yet."""
    settings = mesh.sko_settings
    if settings is None:
        return None
    for flag in settings.key_flags:
        if flag.shape_key_name == name:
            return flag
    return None


def sko_get_pinned_keys(mesh):
    """The key names pinned into the deforming list."""
    settings = mesh.sko_settings
    if settings is None:
        return []
    return [flag.shape_key_name for flag in settings.key_flags if flag.pinned]


def sko_is_key_pinned(mesh, name):
    flag = sko_get_key_flag(mesh, name)
    return flag is not None and flag.pinned


def sync_shape_key_assignment_names(mesh):
    result = folders.sync_assignment_names(mesh, KIND)
    # A renamed key moves its assignment, and its flag entry has to move with it, so the two
    # stay in step wherever this runs. It deliberately does not run from a draw callback:
    # Blender draws in a read-only context, where writing raises "Writing to ID classes in
    # this context is not allowed" and takes the whole list down with it.
    sko_sync_key_flags(mesh)
    return result


def sko_clean_missing_shape_keys(mesh):
    folders.clean_missing_assignments(mesh, KIND)


_KEYS_OWNER = {}


def sko_mesh_of_keys(keys):
    """The mesh a ``Key`` datablock belongs to.

    The list classes cannot ask the context for the object: Blender calls them while
    drawing, and there ``context.object`` turned out to be empty - which silently disabled
    both the filtering and the pin widget. A Key does not point back at its mesh either
    (``id_data`` is the Key itself), so the mesh is looked up instead, and the answer is
    cached the way ``mesh_member_owner`` caches its own.
    """
    cached = bpy.data.meshes.get(_KEYS_OWNER.get(keys.name, ""))
    if cached is not None and cached.shape_keys is keys:
        return cached

    for mesh in bpy.data.meshes:
        if mesh.shape_keys is keys:
            _KEYS_OWNER[keys.name] = mesh.name
            return mesh
    return None


def sko_get_key_by_name(mesh, name):
    if not mesh.shape_keys:
        return None
    return mesh.shape_keys.key_blocks.get(name)


def sko_key_index(mesh, key):
    if not mesh.shape_keys or key is None:
        return -1
    return mesh.shape_keys.key_blocks.find(key.name)


def sko_is_basis(mesh, key):
    if not mesh.shape_keys or key is None:
        return False
    return key == mesh.shape_keys.key_blocks[0]


def sko_get_reference_key(mesh, key):
    if not mesh.shape_keys or key is None:
        return None
    if mesh.shape_keys.use_relative:
        reference = getattr(key, "relative_key", None)
        if reference is not None:
            return reference
    blocks = mesh.shape_keys.key_blocks
    return blocks[0] if len(blocks) else None


class SKO_Folder(PropertyGroup):
    uid: StringProperty(name="Folder ID")
    name: StringProperty(name="Name", default="")
    visible: BoolProperty(
        name="Visible",
        description="Show this folder's shape keys; a soloed folder ignores it",
        default=True,
    )
    isolate: BoolProperty(
        name="Isolate",
        description="Show only this folder; click again to leave solo",
        default=False,
    )
    color: EnumProperty(
        name="Color",
        description="Colour that tags this folder and the keys filed in it",
        items=folders.folder_color_items(),
        default="NONE",
    )


class SKO_Assignment(PropertyGroup):
    shape_key_name: StringProperty(name="Shape Key")
    folder_uids: StringProperty(name="Folder IDs", description="Folders this key is filed in")
    folder_uid: StringProperty(name="Folder ID (legacy)", options={"HIDDEN"})


class SKO_PlaceholderKey(PropertyGroup):
    """Stands in for a key block so the list has a collection to point at.

    ``mesh.shape_keys`` does not exist until the first key is added, and a
    ``template_list`` needs a collection on a real data-block. An always-empty
    collection of these lets the panel draw the same empty list Blender draws for
    the vertex groups instead of a hand-made placeholder.
    """

    name: StringProperty()


class SKO_KeyFlag(PropertyGroup):
    """Per-key state the organizer keeps beside the mesh's own key blocks.

    It exists so that a list row has a real property to draw: pressing a button and
    dragging it across rows is what a ``prop`` widget does and an operator does not, and
    pinning is exactly that kind of switch.
    """

    shape_key_name: StringProperty()
    pinned: BoolProperty(
        name="Pinned",
        description="Keep this shape key in the deforming list even when it is muted or at zero",
        default=False,
    )


class SKO_Settings(PropertyGroup):
    search: StringProperty(name="Search", description="Filter shape keys by name")
    invert_filter: BoolProperty(
        name="Invert Filter",
        description="Show the keys the search hides, and hide the ones it matches",
        default=False,
    )
    shape_key_name_snapshot: StringProperty(name="Shape Key Snapshot", default="", options={"HIDDEN"})
    # Never filled: the list points at this while the mesh has no shape keys, so the
    # empty state is a real UIList at its usual height.
    placeholder_keys: CollectionProperty(type=SKO_PlaceholderKey)
    placeholder_index: IntProperty()
    group_by_folder: BoolProperty(
        name="Folder Order",
        description="Show the list grouped by folder without reordering the keys",
        default=False,
    )
    show_filed: BoolProperty(
        name="Filed",
        description="Show the shape keys that are filed in at least one folder",
        default=True,
    )
    show_unfiled: BoolProperty(
        name="Unfiled",
        description="Show the shape keys that are in no folder",
        default=True,
    )
    key_flags: CollectionProperty(type=SKO_KeyFlag)
    filter_deforming: BoolProperty(
        name="Filter Deforming Keys",
        description="Let the folder filter narrow the deforming list too; the search box never does",
        default=False,
    )



class SKO_UL_folders(UIList):
    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        folders.draw_folder_item(layout, context, data, KIND, item)


class SKO_OT_toggle_deforming_filter(Operator):
    bl_idname = "sko.toggle_deforming_filter"
    bl_label = "Filter the Deforming List"
    bl_description = "Let the folder filter narrow the deforming list as well"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or obj.data.sko_settings is None:
            return {"CANCELLED"}

        settings = obj.data.sko_settings
        settings.filter_deforming = not settings.filter_deforming
        return {"FINISHED"}


class SKO_OT_clear_key_pins(Operator):
    bl_idname = "sko.clear_key_pins"
    bl_label = "Clear All Pins"
    bl_description = "Unpin every shape key at once"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or obj.data.sko_settings is None:
            return {"CANCELLED"}

        cleared = 0
        for flag in obj.data.sko_settings.key_flags:
            if flag.pinned:
                flag.pinned = False
                cleared += 1
        self.report({"INFO"}, iface_("Cleared {} pins.").format(cleared))
        return {"FINISHED"}


def sko_draw_key_row(layout, item, data, mesh, with_pin=False):
    """One shape key row, shared by the organizer list and the deforming list.

    The value slider is the flexible widget, so it stretches right up to the mute and lock
    buttons, which stay flush against the right edge; a split with a fixed factor would
    leave a gap between the two. Absolute keys are placed on the timeline instead of being
    mixed, and Blender's own panel shows their frame there, so that column follows the
    mode. The deforming list adds a pin button after them - pinning is what keeps a key in
    *that* list, so it has no business in the organizer.
    """
    row = layout.row(align=True)
    key_icon = "SHAPEKEY_DATA"
    # The colour sits *beside* the key's own icon rather than replacing it: one icon costs a fixed
    # sliver of the row, which is affordable, and the key icon stays where it was.
    if mesh is not None:
        tag = folders.get_member_color_folder(mesh, KIND, item.name)
        color_icon = folders.folder_color_icon(tag) if tag is not None else None
        if color_icon:
            row.label(text="", icon=color_icon)
    row.prop(item, "name", text="", emboss=False, icon=key_icon, translate=False)
    if getattr(data, "use_relative", True):
        row.prop(item, "value", text="", slider=True)
    else:
        row.prop(item, "frame", text="")
    icons = row.row(align=True)
    icons.use_property_decorate = False
    icons.prop(item, "mute", text="", emboss=False)
    if hasattr(item, "lock_shape"):
        icons.prop(item, "lock_shape", text="", emboss=False)
    if with_pin:
        # A prop rather than an operator: pressing it and dragging across rows toggles a run
        # of keys at once, which is how the mute and lock buttons next to it already behave.
        flag = sko_get_key_flag(mesh, item.name) if mesh is not None else None
        if flag is not None:
            icons.prop(
                flag,
                "pinned",
                text="",
                icon="PINNED" if flag.pinned else "UNPINNED",
                emboss=False,
            )
    if item.mute:
        row.active = False


class SKO_UL_visible_keys(UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        mesh = sko_mesh_of_keys(data) if isinstance(data, bpy.types.Key) else None
        if mesh is None or not hasattr(mesh, "sko_settings"):
            return [self.bitflag_filter_item] * len(items), list(range(len(items)))

        vis = sko_get_visibility_context(mesh)
        flags = [
            self.bitflag_filter_item if sko_is_shape_key_visible(mesh, item.name, vis=vis) else 0
            for item in items
        ]
        if mesh.sko_settings.group_by_folder:
            order = folders.member_display_order(mesh, KIND, items)
        else:
            order = list(range(len(items)))

        return flags, order

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        sko_draw_key_row(layout, item, data, sko_mesh_of_keys(data))


class SKO_UL_deforming_keys(UIList):
    """The organizer's list, filtered down to the keys deforming the mesh right now.

    Deforming means unmuted and off zero. The basis is filtered out with the rest: it is
    the reference the others are measured against, never an edit of its own. A pinned key
    stays in the list whether or not it is deforming, which is what pinning is for.
    """

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        mesh = sko_mesh_of_keys(data)
        if mesh is None or mesh.shape_keys is None:
            return [self.bitflag_filter_item] * len(items), list(range(len(items)))

        # Read-only on purpose: writing from a draw callback raises "Writing to ID classes in
        # this context is not allowed", and that exception takes the whole filter result with
        # it - which is how every key, basis included, once ended up in this list.
        shown = {key.name for key in sko_get_deforming_keys(mesh)}
        shown.update(sko_get_pinned_keys(mesh))

        if mesh.sko_settings.filter_deforming:
            # Only the folder half of the filter, and only when asked for. The search box is
            # deliberately left out: it is shared with the organizer above, so typing in it
            # must not empty this list while the user is looking at something else.
            _search, show_filed, show_unfiled, isolated, _invert = folders.get_visibility_context(
                mesh, KIND
            )
            folder_vis = ("", show_filed, show_unfiled, isolated, False)
            shown = {
                name
                for name in shown
                if folders.is_member_visible(mesh, KIND, name, vis=folder_vis)
            }

        return (
            [self.bitflag_filter_item if item.name in shown else 0 for item in items],
            list(range(len(items))),
        )

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        sko_draw_key_row(layout, item, data, sko_mesh_of_keys(data), with_pin=True)


class SKO_OT_add_folder(FolderAddOperator, Operator):
    bl_idname = "sko.add_folder"
    bl_label = "Add Shape Key Folder"
    bl_description = "Create a folder for organizing shape keys"
    kind = KIND


class SKO_OT_remove_folder(FolderRemoveOperator, Operator):
    bl_idname = "sko.remove_folder"
    bl_label = "Remove Shape Key Folder"
    bl_description = "Remove the selected folder; shape keys stay on the mesh"
    kind = KIND


class SKO_OT_move_folder(FolderMoveOperator, Operator):
    bl_idname = "sko.move_folder"
    bl_label = "Move Shape Key Folder"
    bl_description = "Move the selected folder up or down in the folder list"
    kind = KIND


class SKO_OT_remove_from_folder(FolderRemoveMemberOperator, Operator):
    bl_idname = "sko.remove_from_folder"
    bl_label = "Remove Shape Key from Folder"
    bl_description = "Take the active shape key out of the selected folder"
    kind = KIND


class SKO_OT_toggle_filed(FolderViewSwitchOperator, Operator):
    bl_idname = "sko.toggle_filed"
    bl_label = "Show Filed Shape Keys"
    bl_description = "Show or hide the shape keys filed in at least one folder"
    kind = KIND
    attr = "show_filed"
    other_attr = "show_unfiled"


class SKO_OT_toggle_unfiled(FolderViewSwitchOperator, Operator):
    bl_idname = "sko.toggle_unfiled"
    bl_label = "Show Unfiled Shape Keys"
    bl_description = "Show or hide the shape keys that are in no folder"
    kind = KIND
    attr = "show_unfiled"
    other_attr = "show_filed"


class SKO_OT_unhide_all_folders(FolderUnhideAllOperator, Operator):
    bl_idname = "sko.unhide_all_folders"
    bl_label = "Unhide All Folders"
    bl_description = "Turn the hide switch of every folder back on"
    kind = KIND


class SKO_OT_clear_solo(FolderClearSoloOperator, Operator):
    bl_idname = "sko.clear_solo"
    bl_label = "Clear All Solo"
    bl_description = "Drop solo from every folder"
    kind = KIND


class SKO_OT_set_folder_color(FolderColorOperator, Operator):
    bl_idname = "sko.set_folder_color"
    bl_label = "Set Folder Color"
    bl_description = "Tag the selected folder with a colour"
    kind = KIND


class SKO_OT_copy_folders_to_selected(FolderCopyToSelectedOperator, Operator):
    bl_idname = "sko.copy_folders_to_selected"
    bl_label = "Copy Folders to Selected Objects"
    kind = KIND


class SKO_OT_toggle_folder_visibility(FolderToggleVisibilityOperator, Operator):
    bl_idname = "sko.toggle_folder_visibility"
    bl_label = "Toggle Folder Visibility"
    bl_description = "Show or hide this folder's shape keys"
    kind = KIND


class SKO_OT_isolate_folder(FolderIsolateOperator, Operator):
    bl_idname = "sko.isolate_folder"
    bl_label = "Isolate Folder"
    bl_description = "Show only this folder; click again to leave solo"
    kind = KIND


class SKO_OT_assign_to_folder(FolderAssignOperator, Operator):
    bl_idname = "sko.assign_to_folder"
    bl_label = "Move Shape Key to Folder"
    bl_description = "Assign the active shape key to the selected folder"
    kind = KIND


class SKO_OT_move_filtered_to_selected_folder(FolderMoveFilteredOperator, Operator):
    bl_idname = "sko.move_filtered_to_selected_folder"
    bl_label = "Move Filtered to Selected Folder"
    bl_description = "Move all currently filtered shape keys to the selected folder"
    kind = KIND


class SKO_OT_add_shape_key(Operator):
    bl_idname = "sko.add_shape_key"
    bl_label = "Add Shape Key"
    bl_description = "Create a shape key"
    bl_options = {"REGISTER", "UNDO"}

    from_mix: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return obj is not None and obj.mode != "EDIT"

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        sync_shape_key_assignment_names(mesh)
        # Blender's own operator names the keys the way its Shape Keys panel does
        # ("Basis" first, then "Key 1", "Key 2", ...); the Object API would fall
        # back to its "Key" default and produce "Key", "Key.001", ...
        if bpy.ops.object.shape_key_add(from_mix=self.from_mix) != {"FINISHED"}:
            return {"CANCELLED"}
        if not mesh.shape_keys or not mesh.shape_keys.key_blocks:
            return {"CANCELLED"}
        key = mesh.shape_keys.key_blocks[-1]

        obj.active_shape_key_index = sko_key_index(mesh, key)
        sync_shape_key_assignment_names(mesh)
        return {"FINISHED"}


class SKO_OT_remove_shape_key(Operator):
    bl_idname = "sko.remove_shape_key"
    bl_label = "Remove Shape Key"
    bl_description = "Remove the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return obj is not None and obj.mode != "EDIT"

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        sync_shape_key_assignment_names(mesh)
        key = obj.active_shape_key
        if not key:
            return {"CANCELLED"}
        # The basis key goes too, exactly like Blender's own operator: the next key
        # becomes the basis and is baked into the mesh. It is never listed, so the
        # visibility filter cannot be applied to it - but every other key still has
        # to be visible, which is what keeps a filtered-out key from being deleted
        # by accident.
        if not sko_is_basis(mesh, key) and not sko_is_shape_key_visible(mesh, key.name):
            return {"CANCELLED"}

        obj.active_shape_key_index = sko_key_index(mesh, key)
        obj.shape_key_remove(key)
        sko_clean_missing_shape_keys(mesh)
        sync_shape_key_assignment_names(mesh)
        return {"FINISHED"}


class SKO_OT_move_shape_key(Operator):
    bl_idname = "sko.move_shape_key"
    bl_label = "Move Shape Key"
    bl_description = "Move the active shape key up or down"
    bl_options = {"REGISTER", "UNDO"}

    direction: StringProperty(default="UP")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        key = sko_get_active_visible_key(obj)
        if not key:
            return {"CANCELLED"}
        if sko_is_basis(mesh, key):
            return {"CANCELLED"}

        obj.active_shape_key_index = sko_key_index(mesh, key)
        bpy.ops.object.shape_key_move(type=self.direction)
        return {"FINISHED"}


class SKO_OT_activate_pair_key(Operator):
    bl_idname = "sko.activate_pair_key"
    bl_label = "Activate Shape Key"
    bl_description = "Make this shape key active"
    bl_options = {"REGISTER", "UNDO"}

    key_name: StringProperty()

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        sync_shape_key_assignment_names(mesh)
        key = sko_get_key_by_name(mesh, self.key_name)
        if not key:
            return {"CANCELLED"}

        obj.active_shape_key_index = sko_key_index(mesh, key)
        return {"FINISHED"}


class SKO_OT_toggle_basis_flag(Operator):
    """Mute or lock the basis key from the row that shows it above the list.

    The basis row draws mute and lock as operators instead of ``prop`` widgets so
    the whole row can carry the "pressed" highlight while the basis is the active
    key: ``UILayout.prop`` has no ``depress``, so a property button would stay
    flat beside a highlighted name button. The icon still shows the state.
    """

    bl_idname = "sko.toggle_basis_flag"
    bl_label = "Toggle Basis Key Flag"
    bl_description = "Mute or lock the basis shape key"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="MUTE")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.type != "MESH" or not obj.data.shape_keys:
            return {"CANCELLED"}

        basis = obj.data.shape_keys.key_blocks[0]
        if self.action == "LOCK":
            if not hasattr(basis, "lock_shape"):
                return {"CANCELLED"}
            basis.lock_shape = not basis.lock_shape
        else:
            basis.mute = not basis.mute
        return {"FINISHED"}


class SKO_OT_lock_filtered_keys(Operator):
    bl_idname = "sko.lock_filtered_keys"
    bl_label = "Lock Filtered Shape Keys"
    bl_description = "Change lock state only for currently filtered shape keys"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="LOCK")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        keys = sko_get_visible_shape_keys(obj.data)
        updated = 0
        for key in keys:
            if not hasattr(key, "lock_shape"):
                continue
            if self.action == "LOCK":
                key.lock_shape = True
            elif self.action == "UNLOCK":
                key.lock_shape = False
            elif self.action == "INVERT":
                key.lock_shape = not key.lock_shape
            updated += 1

        self.report({"INFO"}, iface_("Updated {} filtered shape keys.").format(updated))
        return {"FINISHED"}


class SKO_OT_mute_filtered_keys(Operator):
    bl_idname = "sko.mute_filtered_keys"
    bl_label = "Mute Filtered Shape Keys"
    bl_description = "Change mute state only for currently filtered shape keys"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty(default="MUTE")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        keys = sko_get_visible_shape_keys(obj.data)
        for key in keys:
            if self.action == "MUTE":
                key.mute = True
            elif self.action == "UNMUTE":
                key.mute = False
            elif self.action == "INVERT":
                key.mute = not key.mute

        self.report({"INFO"}, iface_("Updated {} filtered shape keys.").format(len(keys)))
        return {"FINISHED"}


class SKO_OT_delete_filtered_keys(Operator):
    bl_idname = "sko.delete_filtered_keys"
    bl_label = "Delete Filtered Shape Keys"
    bl_description = "Delete only currently filtered shape keys"
    bl_options = {"REGISTER", "UNDO"}

    only_unlocked: BoolProperty(default=False)

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        mesh = obj.data
        keys = list(sko_get_visible_shape_keys(mesh))
        removed = 0
        for key in keys:
            current = sko_get_key_by_name(mesh, key.name)
            if not current:
                continue
            if sko_is_basis(mesh, current):
                continue
            if self.only_unlocked and hasattr(current, "lock_shape") and current.lock_shape:
                continue
            obj.shape_key_remove(current)
            removed += 1

        sko_clean_missing_shape_keys(mesh)
        sync_shape_key_assignment_names(mesh)
        self.report({"INFO"}, iface_("Deleted {} filtered shape keys.").format(removed))
        return {"FINISHED"}


# The offsets copied by sko.copy_selected_offsets, kept for the session: a scratch pad
# for one edit rather than part of the file. Living in the module also means it survives
# undo, the way a clipboard should.
_OFFSET_CLIPBOARD = []


def sko_offset_context(context):
    """What the two offset-clipboard operators need, or None when they cannot run.

    Edit mode, an active key that is not the basis, and the key the offsets are measured
    against - the same three things in the same order for the copy and the paste, so both
    polls and both bodies ask once.
    """
    obj = get_active_object(context)
    if obj is None or obj.mode != "EDIT" or obj.data.shape_keys is None:
        return None
    key = obj.active_shape_key
    if key is None or sko_is_basis(obj.data, key):
        return None
    reference = sko_get_reference_key(obj.data, key)
    if reference is None:
        return None
    return obj, obj.data, key, reference


class SKO_OT_select_offset_vertices(Operator):
    bl_idname = "sko.select_offset_vertices"
    bl_label = "Select Offset Vertices"
    bl_description = "Select vertices that are moved by the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    threshold: FloatProperty(
        name="Min Move Threshold",
        description="Minimum movement required to count as an offset",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        precision=4,
    )

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.mode == "EDIT"
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.mode != "EDIT":
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        selected = 0
        for vert in bm.verts:
            index = vert.index
            offset = (vert.co - reference.data[index].co).length
            select = offset > self.threshold
            vert.select = select
            if select:
                selected += 1

        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Selected {} offset vertices.").format(selected))
        return {"FINISHED"}


class SKO_OT_remove_selected_offsets(Operator):
    bl_idname = "sko.remove_selected_offsets"
    bl_label = "Remove Selected Offsets"
    bl_description = "Reset the offset of selected vertices in the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.mode == "EDIT"
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.mode != "EDIT":
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        moved = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            vert.co = reference.data[vert.index].co
            moved += 1

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Removed offsets from {} vertices.").format(moved))
        return {"FINISHED"}


class SKO_OT_copy_selected_offsets(Operator):
    bl_idname = "sko.copy_selected_offsets"
    bl_label = "Copy Offsets from Selected Points' Shape Key"
    bl_description = "Copy the offsets the selected vertices have in the active shape key, scaled by its value so the copy matches what is on screen"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return sko_offset_context(context) is not None

    def execute(self, context):
        found = sko_offset_context(context)
        if found is None:
            return {"CANCELLED"}
        _obj, mesh, key, reference = found

        # A relative key's value scales what it does to the mesh, so the copy carries it:
        # pasting into another key at another value then reproduces this offset on screen
        # instead of the raw one. Absolute keys have no value to take into account.
        scale = float(key.value) if mesh.shape_keys.use_relative else 1.0

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        offsets = []
        for vert in bm.verts:
            if not vert.select:
                continue
            base = reference.data[vert.index].co
            offset = (vert.co - base) * scale
            offsets.append((vert.index, offset.x, offset.y, offset.z))

        if not offsets:
            self.report({"WARNING"}, iface_("Select vertices in edit mode first."))
            return {"CANCELLED"}

        _OFFSET_CLIPBOARD[:] = offsets
        self.report({"INFO"}, iface_("Copied the offsets of {} vertices.").format(len(offsets)))
        return {"FINISHED"}


class SKO_OT_paste_selected_offsets(Operator):
    bl_idname = "sko.paste_selected_offsets"
    bl_label = "Paste Offsets to Selected Points' Shape Key"
    bl_description = "Apply the stored offsets to the selected vertices in the active shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_OFFSET_CLIPBOARD) and sko_offset_context(context) is not None

    def execute(self, context):
        found = sko_offset_context(context)
        if found is None:
            return {"CANCELLED"}
        _obj, mesh, key, reference = found
        if not _OFFSET_CLIPBOARD:
            self.report({"WARNING"}, iface_("Nothing has been copied yet."))
            return {"CANCELLED"}

        # The inverse of the copy: the clipboard holds what was on screen, so undo the
        # value scaling of the key being pasted into and the same offset lands again. A
        # key sitting at zero shows nothing either way, so it cannot divide.
        scale = float(key.value) if mesh.shape_keys.use_relative else 1.0
        divisor = scale if scale else 1.0
        stored = {index: (dx, dy, dz) for index, dx, dy, dz in _OFFSET_CLIPBOARD}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        applied = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            offset = stored.get(vert.index)
            if offset is None:
                continue
            base = reference.data[vert.index].co
            vert.co = (
                base.x + offset[0] / divisor,
                base.y + offset[1] / divisor,
                base.z + offset[2] / divisor,
            )
            applied += 1

        if not applied:
            self.report(
                {"WARNING"},
                iface_("None of the selected vertices has a stored offset."),
            )
            return {"CANCELLED"}

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Pasted offsets to {} vertices.").format(applied))
        return {"FINISHED"}


class SKO_OT_apply_stored_offsets(Operator):
    bl_idname = "sko.apply_stored_offsets"
    bl_label = "Apply Offsets to Selected Points"
    bl_description = "Move the selected vertices by the stored offsets in the active shape key, without taking its value into account"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            bool(_OFFSET_CLIPBOARD)
            and obj is not None
            and obj.mode == "EDIT"
            and obj.data.shape_keys is not None
        )

    def execute(self, context):
        obj = get_active_object(context)
        if obj is None or obj.mode != "EDIT" or obj.data.shape_keys is None:
            return {"CANCELLED"}
        if not _OFFSET_CLIPBOARD:
            self.report({"WARNING"}, iface_("Nothing has been copied yet."))
            return {"CANCELLED"}

        mesh = obj.data
        stored = {index: (dx, dy, dz) for index, dx, dy, dz in _OFFSET_CLIPBOARD}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()

        applied = 0
        for vert in bm.verts:
            if not vert.select:
                continue
            offset = stored.get(vert.index)
            if offset is None:
                continue
            # Edit mode writes the active key and nothing else, which is exactly what this
            # entry wants: the offset lands there like a plain vertex move, with the key's
            # value left out of it.
            vert.co = (vert.co.x + offset[0], vert.co.y + offset[1], vert.co.z + offset[2])
            applied += 1

        if not applied:
            self.report(
                {"WARNING"},
                iface_("None of the selected vertices has a stored offset."),
            )
            return {"CANCELLED"}

        bmesh.update_edit_mesh(mesh)
        self.report({"INFO"}, iface_("Applied the offsets to {} vertices.").format(applied))
        return {"FINISHED"}


def sko_get_vertex_group(obj, name):
    for group in obj.vertex_groups:
        if group.name == name:
            return group
    return None


class SKO_OT_create_offset_vertex_group(Operator):
    # The idname keeps the old "offset" wording so existing shortcuts and scripts
    # keep working; only the labels moved to the "blend" vocabulary.
    bl_idname = "sko.create_offset_vertex_group"
    bl_label = "Auto Create Blend Vertex Group"
    bl_description = "Create a blend vertex group from the vertices the active shape key moves"
    bl_options = {"REGISTER", "UNDO"}

    threshold: FloatProperty(
        name="Min Move Threshold",
        description="Minimum movement required to count as an offset",
        default=0.0,
        min=0.0,
        soft_max=1.0,
        precision=4,
    )
    vertex_group_name: StringProperty(name="Vertex Group")

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def invoke(self, context, event):
        obj = get_active_object(context)
        if obj and obj.active_shape_key and not self.vertex_group_name:
            self.vertex_group_name = "shapeblend_" + obj.active_shape_key.name
        if context.window is None:  # background / scripted runs have no dialog
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        key = obj.active_shape_key if obj else None
        if key is not None and key.vertex_group:
            layout.label(text=iface_("Replaces the shape key's current vertex group:"), icon="ERROR")
            layout.label(text=key.vertex_group)
        layout.prop(self, "vertex_group_name")
        layout.prop(self, "threshold")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or not obj.data.shape_keys:
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        if not key or sko_is_basis(mesh, key):
            return {"CANCELLED"}

        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        if obj.mode == "EDIT":
            import bmesh

            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            indices = [
                vert.index
                for vert in bm.verts
                if (vert.co - reference.data[vert.index].co).length > self.threshold
            ]
        else:
            indices = [
                vertex.index
                for vertex in mesh.vertices
                if (key.data[vertex.index].co - reference.data[vertex.index].co).length > self.threshold
            ]

        name = (self.vertex_group_name or "").strip() or ("shapeblend_" + key.name)
        replaced = key.vertex_group
        group = obj.vertex_groups.new(name=name)
        if obj.mode == "EDIT":
            deform = bm.verts.layers.deform.verify()
            for index in indices:
                bm.verts[index][deform][group.index] = 1.0
            bmesh.update_edit_mesh(mesh)
        else:
            group.add(indices, 1.0, "REPLACE")
        key.vertex_group = group.name

        self.report({"INFO"}, iface_("Created vertex group {} with {} vertices.").format(group.name, len(indices)))
        if replaced and replaced != group.name:
            self.report({"WARNING"}, iface_("Replaced the shape key's vertex group {}.").format(replaced))
        return {"FINISHED"}


class SKO_OT_create_blend_group(Operator):
    """The same group as the automatic one, but from the edit-mode selection."""

    bl_idname = "sko.create_blend_group"
    bl_label = "Create Blend Vertex Group"
    bl_description = "Create a blend vertex group from the vertices selected in edit mode"
    bl_options = {"REGISTER", "UNDO"}

    vertex_group_name: StringProperty(name="Vertex Group")

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.mode == "EDIT"  # the selection only exists in edit mode
            and obj.data.shape_keys is not None
            and obj.active_shape_key is not None
            and not sko_is_basis(obj.data, obj.active_shape_key)
        )

    def invoke(self, context, event):
        obj = get_active_object(context)
        if obj and obj.active_shape_key and not self.vertex_group_name:
            self.vertex_group_name = "shapeblend_" + obj.active_shape_key.name
        if context.window is None:  # background / scripted runs have no dialog
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        key = obj.active_shape_key if obj else None
        if key is not None and key.vertex_group:
            layout.label(text=iface_("Replaces the shape key's current vertex group:"), icon="ERROR")
            layout.label(text=key.vertex_group)
        layout.prop(self, "vertex_group_name")

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or obj.mode != "EDIT" or not obj.data.shape_keys:
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        if not key or sko_is_basis(mesh, key):
            return {"CANCELLED"}

        import bmesh

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        selection = [vert.index for vert in bm.verts if vert.select]
        if not selection:
            self.report({"WARNING"}, iface_("Select vertices in edit mode first."))
            return {"CANCELLED"}

        name = (self.vertex_group_name or "").strip() or ("shapeblend_" + key.name)
        replaced = key.vertex_group
        group = obj.vertex_groups.new(name=name)
        deform = bm.verts.layers.deform.verify()
        for index in selection:
            bm.verts[index][deform][group.index] = 1.0
        bmesh.update_edit_mesh(mesh)
        key.vertex_group = group.name

        self.report({"INFO"}, iface_("Created vertex group {} with {} vertices.").format(group.name, len(selection)))
        if replaced and replaced != group.name:
            self.report({"WARNING"}, iface_("Replaced the shape key's vertex group {}.").format(replaced))
        return {"FINISHED"}


class SKO_OT_apply_offset_vertex_group(Operator):
    bl_idname = "sko.apply_offset_vertex_group"
    bl_label = "Apply Blend Vertex Group"
    bl_description = "Apply the active shape key's vertex group weights and clear the vertex group"
    bl_options = {"REGISTER", "UNDO"}

    delete_group: BoolProperty(
        name="Delete Vertex Group",
        description="Delete the vertex group after applying it",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        if obj is None or obj.data.shape_keys is None:
            return False
        key = obj.active_shape_key
        if key is None or not key.vertex_group:
            return False
        return sko_get_vertex_group(obj, key.vertex_group) is not None

    def execute(self, context):
        obj = get_active_object(context)
        if not obj or not obj.data.shape_keys:
            return {"CANCELLED"}

        mesh = obj.data
        key = obj.active_shape_key
        if not key or not key.vertex_group:
            return {"CANCELLED"}

        group = sko_get_vertex_group(obj, key.vertex_group)
        if group is None:
            return {"CANCELLED"}

        reference = sko_get_reference_key(mesh, key)
        if reference is None:
            return {"CANCELLED"}

        if obj.mode == "EDIT":
            import bmesh

            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            for vert in bm.verts:
                index = vert.index
                try:
                    weight = group.weight(index)
                except RuntimeError:
                    weight = 0.0
                ref_co = reference.data[index].co
                vert.co = ref_co + (vert.co - ref_co) * weight
            bmesh.update_edit_mesh(mesh)
        else:
            for vertex in mesh.vertices:
                index = vertex.index
                try:
                    weight = group.weight(index)
                except RuntimeError:
                    weight = 0.0
                ref_co = reference.data[index].co
                key.data[index].co = ref_co + (key.data[index].co - ref_co) * weight

        name = group.name
        key.vertex_group = ""
        if self.delete_group:
            obj.vertex_groups.remove(group)

        self.report({"INFO"}, iface_("Applied vertex group {} to {}.").format(name, key.name))
        return {"FINISHED"}


class SKO_OT_toggle_group_by_folder(GroupByFolderOperator, Operator):
    bl_idname = "sko.toggle_group_by_folder"
    bl_label = "Folder Order in List"
    bl_description = "Show the list grouped by folder without reordering the keys"
    kind = KIND


class SKO_OT_reset_filtered_keys(Operator):
    bl_idname = "sko.reset_filtered_keys"
    bl_label = "Reset Filtered Shape Keys"
    bl_description = "Set the value of currently filtered shape keys to 0"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = get_active_object(context)
        if not obj:
            return {"CANCELLED"}

        keys = sko_get_visible_shape_keys(obj.data)
        for key in keys:
            key.value = 0.0

        self.report({"INFO"}, iface_("Reset {} filtered shape keys.").format(len(keys)))
        return {"FINISHED"}


def draw_shape_key_specials(self, context):
    """Our entries, appended to Blender's own shape key specials menu.

    Only entries that make sense next to Blender's own go here. The actions that
    work on whatever the search/folder filter shows live in their own menu
    (``SKO_MT_filter_menu``), otherwise this one grows past the screen.
    """
    layout = self.layout
    layout.separator()
    edit_col = layout.column()
    edit_col.enabled = context.object is not None and context.object.mode == "EDIT"
    edit_col.operator("sko.select_offset_vertices", icon="VERTEXSEL", text=iface_("Select Offset Vertices"))
    edit_col.operator("sko.remove_selected_offsets", icon="X", text=iface_("Remove Selected Offsets"))
    layout.separator()
    layout.operator("sko.create_offset_vertex_group", icon="GROUP_VERTEX", text=iface_("Auto Create Blend Vertex Group"))
    # Its poll already needs edit mode, so the entry greys itself out elsewhere.
    layout.operator("sko.create_blend_group", icon="GROUP_VERTEX", text=iface_("Create Blend Vertex Group"))
    layout.operator("sko.apply_offset_vertex_group", icon="GROUP_VERTEX", text=iface_("Apply Blend Vertex Group"))
    # Both are edit-mode only; their polls grey them out everywhere else, so no wrapper
    # column is needed here.
    layout.separator()
    layout.operator(
        "sko.copy_selected_offsets",
        icon="COPYDOWN",
        text=iface_("Copy Offsets from Selected Points' Shape Key"),
    )
    layout.operator(
        "sko.paste_selected_offsets",
        icon="PASTEDOWN",
        text=iface_("Paste Offsets to Selected Points' Shape Key"),
    )
    layout.operator(
        "sko.apply_stored_offsets",
        icon="ARROW_LEFTRIGHT",
        text=iface_("Apply Offsets to Selected Points"),
    )
    layout.separator()
    layout.operator(
        "sko.copy_folders_to_selected",
        icon="DUPLICATE",
        text=iface_("Copy Folders to Selected Objects"),
    )


class SKO_MT_filter_menu(Menu):
    """Bulk actions that only touch what the filter shows."""

    bl_label = "Shape Key Filter Operations"
    bl_idname = "SKO_MT_filter_menu"
    bl_description = folders.FILTER_MENU_DESCRIPTION

    def draw(self, context):
        layout = self.layout
        layout.operator("sko.reset_filtered_keys", text=iface_("Reset Filtered Values"))
        layout.operator("sko.delete_filtered_keys", text=iface_("Delete Filtered Unlocked Keys")).only_unlocked = True
        layout.operator("sko.delete_filtered_keys", text=iface_("Delete Filtered Keys")).only_unlocked = False
        layout.separator()
        layout.operator("sko.lock_filtered_keys", icon="LOCKED", text=iface_("Lock Filtered")).action = "LOCK"
        layout.operator("sko.lock_filtered_keys", icon="UNLOCKED", text=iface_("Unlock Filtered")).action = "UNLOCK"
        layout.operator("sko.lock_filtered_keys", text=iface_("Invert Filtered Locks")).action = "INVERT"
        layout.separator()
        layout.operator("sko.mute_filtered_keys", icon="HIDE_ON", text=iface_("Mute Filtered")).action = "MUTE"
        layout.operator("sko.mute_filtered_keys", icon="HIDE_OFF", text=iface_("Unmute Filtered")).action = "UNMUTE"
        layout.operator("sko.mute_filtered_keys", text=iface_("Invert Filtered Mutes")).action = "INVERT"


def sko_draw_shape_key_properties(context, layout, obj):
    mesh = obj.data
    key = mesh.shape_keys
    kb = obj.active_shape_key
    if key is None or kb is None:
        return

    enable_edit = obj.mode != "EDIT"
    enable_edit_value = False
    if enable_edit or (obj.use_shape_key_edit_mode and obj.type == "MESH"):
        if not obj.show_only_shape_key:
            enable_edit_value = True

    layout.use_property_split = True
    layout.use_property_decorate = False

    if key.use_relative:
        if obj.active_shape_key_index != 0:
            row = layout.row()
            row.active = enable_edit_value
            row.prop(kb, "value")

            col = layout.column()
            sub = col.column(align=True)
            sub.active = enable_edit_value
            sub.prop(kb, "slider_min", text="Range Min")
            sub.prop(kb, "slider_max", text="Max")

            col.prop_search(kb, "vertex_group", obj, "vertex_groups", text="Vertex Group")
            col.prop_search(kb, "relative_key", key, "key_blocks", text="Relative To")
    else:
        layout.prop(kb, "interpolation")
        row = layout.column()
        row.active = enable_edit_value
        row.prop(key, "eval_time")


class SKO_PT_shape_key_organizer(Panel):
    bl_label = "Shape Key Organizer"
    bl_idname = "SKO_PT_shape_key_organizer"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return get_active_object(context) is not None

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        mesh = obj.data
        settings = mesh.sko_settings
        # Linked data cannot be written to. Say so instead of drawing buttons that quietly do
        # nothing, and keep drawing the rest: the folders are still worth looking at.
        if not folders.is_editable(mesh) or settings is None:
            layout.label(
                text=iface_("Linked data: folders are read-only."),
                icon="LIBRARY_DATA_DIRECTORY",
            )
        if settings is None:
            return
        visible = sko_get_visible_shape_keys(mesh)

        split = layout.split(factor=0.36)
        left = split.column()
        right = split.column()

        row = left.row(align=True)
        row.operator(KIND.filed_op, text=iface_("Filed"), depress=settings.show_filed)
        # Solo hides the unfiled members, so the switch that normally shows them is dimmed
        # for as long as it cannot have any effect.
        unfiled_row = row.row(align=True)
        unfiled_row.enabled = not folders.has_isolated_folder(mesh, KIND)
        unfiled_row.operator(KIND.unfiled_op, text=iface_("Unfiled"), depress=settings.show_unfiled)

        left.template_list(
            "SKO_UL_folders",
            "",
            mesh,
            "sko_folders",
            mesh,
            "sko_folder_index",
            rows=FOLDER_ROWS,
            maxrows=folders.LIST_MAX_ROWS,
        )

        folders.draw_folder_controls(left, mesh, KIND)

        folders.draw_folder_actions(left, mesh, KIND)

        # The title goes inside the aligned column: an aligned column packs its
        # items tight, so the entries sit right under the title.
        pair_box = left.box()
        pair_col = pair_box.column(align=True)
        pair_col.label(text=iface_("Active Key"))
        pair_keys = sko_get_active_key_pair(obj)
        if pair_keys:
            for key in pair_keys:
                row = pair_col.row(align=True)
                icon = "SHAPEKEY_DATA" if key == obj.active_shape_key else "ARROW_LEFTRIGHT"
                op = row.operator(
                    "sko.activate_pair_key",
                    text=key.name,
                    icon=icon,
                    emboss=False,
                    depress=(key == obj.active_shape_key),
                    translate=False,
                )
                op.key_name = key.name
                row.prop(key, "mute", text="", emboss=False)
                if hasattr(key, "lock_shape"):
                    row.prop(key, "lock_shape", text="", emboss=False)

        active_key = obj.active_shape_key
        if mesh.shape_keys and active_key:
            sko_draw_shape_key_properties(context, left, obj)

        if mesh.shape_keys:
            basis = mesh.shape_keys.key_blocks[0]
            basis_active = obj.active_shape_key_index == 0
            # Pad the basis box with an invisible button so its right edge lines
            # up with the list below, which is narrowed by its button column.
            basis_outer = right.row()
            basis_box = basis_outer.box()
            basis_spacer = basis_outer.column()
            basis_spacer.ui_units_x = MEMBER_BUTTON_COLUMN_UNITS
            basis_spacer.label(text="", icon="BLANK1")
            basis_col = basis_box.column(align=True)
            basis_row = basis_col.row(align=True)
            op = basis_row.operator(
                "sko.activate_pair_key",
                text=basis.name,
                icon="SHAPEKEY_DATA",
                # Embossed while it is the active key: a flat row cannot show
                # "pressed", so the basis would look the same either way.
                emboss=basis_active,
                depress=basis_active,
                translate=False,
            )
            op.key_name = basis.name
            # Mute and lock are operators as well, so the pressed background runs
            # across the whole row instead of stopping after the name; the icons
            # keep showing the state.
            mute_op = basis_row.operator(
                "sko.toggle_basis_flag",
                text="",
                # ShapeKey.mute declares ICON_CHECKBOX_HLT with icon_on=-1, so the
                # widget the other rows use shows the checked box while the key is
                # *not* muted and swaps in the empty box once it is. Keep the same
                # way round here, or the basis row contradicts the list.
                icon="CHECKBOX_HLT" if not basis.mute else "CHECKBOX_DEHLT",
                emboss=basis_active,
                depress=basis_active,
            )
            mute_op.action = "MUTE"
            if hasattr(basis, "lock_shape"):
                lock_op = basis_row.operator(
                    "sko.toggle_basis_flag",
                    text="",
                    icon="LOCKED" if basis.lock_shape else "UNLOCKED",
                    emboss=basis_active,
                    depress=basis_active,
                )
                lock_op.action = "LOCK"
            if basis.mute:
                basis_row.active = False

        header = right.row(align=True)
        header.prop(settings, "search", text="", icon="VIEWZOOM")
        header.prop(
            settings,
            "invert_filter",
            text="",
            icon="ARROW_LEFTRIGHT",
            toggle=True,
        )
        header.label(text=iface_("{} shown").format(len(visible)))
        list_row = right.row()
        if mesh.shape_keys:
            list_row.template_list(
                "SKO_UL_visible_keys",
                "",
                mesh.shape_keys,
                "key_blocks",
                obj,
                "active_shape_key_index",
                rows=KEY_ROWS,
                maxrows=folders.LIST_MAX_ROWS,
            )
        else:
            # No shape keys yet: draw a real (empty) list rather than a placeholder,
            # by pointing it at a collection that is always empty. It then matches
            # what the vertex group panel shows, height and drag handle included.
            list_row.template_list(
                "SKO_UL_visible_keys",
                "",
                settings,
                "placeholder_keys",
                settings,
                "placeholder_index",
                rows=KEY_ROWS,
                maxrows=folders.LIST_MAX_ROWS,
            )

        buttons = list_row.column(align=True)
        buttons.operator("sko.add_shape_key", text="", icon="ADD").from_mix = False
        buttons.operator("sko.remove_shape_key", text="", icon="REMOVE")
        buttons.separator()
        # Blender's own menu, with our entries appended: one list, shared with
        # whatever other add-ons put in it. The filter actions sit below it in
        # their own menu so neither list grows past the screen.
        buttons.menu(NATIVE_MENU, text="", icon="DOWNARROW_HLT")
        buttons.menu("SKO_MT_filter_menu", text="", icon="FILTER")
        buttons.separator()
        buttons.operator("sko.move_shape_key", text="", icon="TRIA_UP").direction = "UP"
        buttons.operator("sko.move_shape_key", text="", icon="TRIA_DOWN").direction = "DOWN"
        buttons.separator()
        # The folder-order view is a switch, not an action, so it lives here as a
        # button that stays pressed while it is on instead of in the menu.
        buttons.operator(
            "sko.toggle_group_by_folder",
            text="",
            icon="APPEND_BLEND",
            depress=settings.group_by_folder,
        )

        if mesh.shape_keys and len(mesh.shape_keys.key_blocks) > 1 and not visible:
            right.label(text=iface_("No shape keys match the current filter."), icon="INFO")
            if settings.search:
                right.label(text=iface_("The basis key is never listed."), icon="INFO")

        has_rest = obj.type == "MESH" and hasattr(obj, "add_rest_position_attribute")
        if mesh.shape_keys and active_key:
            row = right.row(align=True)
            row.use_property_split = False
            if has_rest:
                row.prop(obj, "add_rest_position_attribute")

            # The relative/absolute switch changes what the whole list shows, so it
            # belongs with the rest position and the pin rather than under the basis.
            row.prop(mesh.shape_keys, "use_relative")

            sub = row.row(align=True)
            sub.alignment = "RIGHT"
            subsub = sub.row(align=True)
            enable_pin = (obj.mode != "EDIT") or (obj.use_shape_key_edit_mode and obj.type == "MESH")
            subsub.active = enable_pin
            subsub.prop(obj, "show_only_shape_key", text="")
            if obj.type == "MESH":
                sub.prop(obj, "use_shape_key_edit_mode", text="")
            sub.separator()
            if mesh.shape_keys.use_relative:
                sub.operator("object.shape_key_clear", icon="X", text="")
            else:
                sub.operator("object.shape_key_retime", icon="RECOVER_LAST", text="")
        elif has_rest:
            rest_row = right.row(align=True)
            rest_row.use_property_split = False
            rest_row.alignment = "LEFT"
            rest_row.prop(obj, "add_rest_position_attribute")

        draw_shape_key_sync(layout, obj)


class SKO_PT_deforming_keys(Panel):
    """A live list of the keys the mesh is showing, folded away by default.

    It mirrors the mesh instead of organizing it, so it hangs under the organizer as a
    sub-panel and starts collapsed: the organizer stays what the panel opens on, and this
    is there for the other question - what is deforming the mesh right now. The name keeps
    clear of Blender's own "active shape key", which is the key being edited.
    """

    bl_label = "Deforming Shape Keys"
    bl_idname = "SKO_PT_deforming_keys"
    bl_parent_id = "SKO_PT_shape_key_organizer"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        obj = get_active_object(context)
        return (
            obj is not None
            and obj.data.shape_keys is not None
            and obj.data.sko_settings is not None
        )

    def draw(self, context):
        layout = self.layout
        obj = get_active_object(context)
        mesh = obj.data
        if not sko_get_deforming_keys(mesh) and not sko_get_pinned_keys(mesh):
            layout.label(text=iface_("No shape key is deforming the mesh."), icon="INFO")
            return

        # The organizer's own list with a different filter - plus the pin button that keeps a key
        # here - so there is nothing new to learn. The button column to its right holds the two
        # list-wide switches, with a gap between them so one press cannot mean both.
        row = layout.row()
        row.template_list(
            "SKO_UL_deforming_keys",
            "",
            mesh.shape_keys,
            "key_blocks",
            obj,
            "active_shape_key_index",
            rows=DEFORMING_ROWS,
            maxrows=folders.LIST_MAX_ROWS,
        )
        buttons = row.column(align=True)
        buttons.operator("sko.clear_key_pins", text="", icon="UNPINNED")
        buttons.separator()
        buttons.operator(
            "sko.toggle_deforming_filter",
            text="",
            icon="FILTER",
            depress=mesh.sko_settings.filter_deforming,
        )


def _draw_edit_mesh_vertex_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sko.select_offset_vertices", icon="VERTEXSEL")
    layout.operator("sko.remove_selected_offsets", icon="X")


def _draw_edit_mesh_select_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sko.select_offset_vertices", icon="VERTEXSEL")


def _draw_paint_weight_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sko.create_offset_vertex_group", icon="GROUP_VERTEX")
    layout.operator("sko.apply_offset_vertex_group", icon="GROUP_VERTEX")


def register_menus():
    bpy.types.VIEW3D_MT_edit_mesh_vertices.append(_draw_edit_mesh_vertex_menu)
    bpy.types.VIEW3D_MT_select_edit_mesh.append(_draw_edit_mesh_select_menu)
    bpy.types.VIEW3D_MT_paint_weight.append(_draw_paint_weight_menu)
    if hasattr(bpy.types, NATIVE_MENU):
        getattr(bpy.types, NATIVE_MENU).append(draw_shape_key_specials)


def unregister_menus():
    bpy.types.VIEW3D_MT_edit_mesh_vertices.remove(_draw_edit_mesh_vertex_menu)
    bpy.types.VIEW3D_MT_select_edit_mesh.remove(_draw_edit_mesh_select_menu)
    bpy.types.VIEW3D_MT_paint_weight.remove(_draw_paint_weight_menu)
    if hasattr(bpy.types, NATIVE_MENU):
        getattr(bpy.types, NATIVE_MENU).remove(draw_shape_key_specials)


classes = (
    SKO_Folder,
    SKO_Assignment,
    SKO_KeyFlag,
    SKO_PlaceholderKey,
    SKO_Settings,
    SKO_SyncSettings,
    SKO_UL_folders,
    SKO_UL_visible_keys,
    SKO_UL_deforming_keys,
    SKO_OT_add_folder,
    SKO_OT_remove_folder,
    SKO_OT_move_folder,
    SKO_OT_toggle_filed,
    SKO_OT_toggle_unfiled,
    SKO_OT_unhide_all_folders,
    SKO_OT_clear_solo,
    SKO_OT_set_folder_color,
    SKO_OT_copy_folders_to_selected,
    SKO_OT_toggle_folder_visibility,
    SKO_OT_isolate_folder,
    SKO_OT_assign_to_folder,
    SKO_OT_remove_from_folder,
    SKO_OT_move_filtered_to_selected_folder,
    SKO_OT_add_shape_key,
    SKO_OT_remove_shape_key,
    SKO_OT_move_shape_key,
    SKO_OT_activate_pair_key,
    SKO_OT_toggle_basis_flag,
    SKO_OT_lock_filtered_keys,
    SKO_OT_mute_filtered_keys,
    SKO_OT_delete_filtered_keys,
    SKO_OT_select_offset_vertices,
    SKO_OT_remove_selected_offsets,
    SKO_OT_copy_selected_offsets,
    SKO_OT_paste_selected_offsets,
    SKO_OT_apply_stored_offsets,
    SKO_OT_toggle_deforming_filter,
    SKO_OT_clear_key_pins,
    SKO_OT_create_offset_vertex_group,
    SKO_OT_create_blend_group,
    SKO_OT_apply_offset_vertex_group,
    SKO_OT_reset_filtered_keys,
    SKO_OT_toggle_group_by_folder,
    SKO_MT_filter_menu,
    SKO_PT_shape_key_organizer,
    SKO_PT_deforming_keys,
)
