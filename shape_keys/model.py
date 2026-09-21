import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from .. import folders

# The sync subsystem lives in sync.py. Its names are re-exported here because
# __init__.py, the panel and the tests all address them through this module.
from ..sync import (  # noqa: F401  (re-exported names)
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


def update_folder_tag(folder, context):
    """Repaint as soon as a tag changes.

    The tag is written from a popup, and the lists that draw it are elsewhere on screen: without this the new
    icon only appeared once something else happened to redraw the editor.
    """
    folders.tag_redraw()


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
    tag: EnumProperty(
        name="Label",
        description="Icon that tags this folder and the keys filed in it",
        items=folders.folder_tag_items(),
        default="NONE",
        update=update_folder_tag,
    )


class SKO_Assignment(PropertyGroup):
    shape_key_name: StringProperty(name="Shape Key")
    folder_uids: StringProperty(name="Folder IDs", description="Folders this key is filed in")


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
    # Which row the member list counts as active while *Scroll to Active Key* runs; see
    # ``common.request_list_scroll`` for why the list is handed stand-in rows for a few draws.
    scroll_index: IntProperty(options={"SKIP_SAVE"})
