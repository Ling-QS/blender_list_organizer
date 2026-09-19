"""List-kind adapters: what each organizer's list is, plus two shared constants.

Split out of ``folders.py``. ``VertexGroupKind`` / ``ShapeKeyKind`` are the whole
reason one folder machinery can serve both organizers, and they are self-contained:
they only read ``bpy.data`` and the properties the kind describes, with nothing in
``folders.py`` behind them, so they can be read on their own. ``folders.py`` imports
them from here and re-exports the names for the modules that address them through
it (``vertex_groups.py``, ``shape_keys.py``, the smoke test).
"""

import bpy


_MESH_MEMBER_OWNER = {}


def mesh_member_owner(mesh):
    """An object using ``mesh``.

    Vertex group names and weights live on the mesh datablock (Blender 3.0 moved
    them there), but the RNA collection that exposes them hangs off an object, and
    every object sharing the mesh reports the same groups - so any of them can
    answer questions about the members. The answer is cached per mesh name.
    """
    cached = bpy.data.objects.get(_MESH_MEMBER_OWNER.get(mesh.name, ""))
    if cached is not None and cached.data is mesh:
        return cached

    for obj in bpy.data.objects:
        if obj.data is mesh:
            _MESH_MEMBER_OWNER[mesh.name] = obj.name
            return obj
    return None


def is_editable(id_block):
    """Whether the add-on may write to this ID: linked data is read-only.

    The add-on writes from places that run on their own - the legacy migration, the
    rename scan, the folder operators - so they all ask first instead of raising
    once per handler tick on a mesh that came from a library.
    """
    return id_block is not None and id_block.library is None


class VertexGroupKind:
    """Vertex groups: names and weights live on the mesh, so folders do too."""

    add_op = "vgo.add_folder"
    remove_op = "vgo.remove_folder"
    move_op = "vgo.move_folder"
    visibility_op = "vgo.toggle_folder_visibility"
    isolate_op = "vgo.isolate_folder"
    assign_op = "vgo.assign_to_folder"
    remove_member_op = "vgo.remove_from_folder"
    move_filtered_op = "vgo.move_filtered_to_selected_folder"
    moved_message = "Moved {} vertex groups to {}."
    member_name_attr = "vertex_group_name"
    snapshot_attr = "vertex_group_name_snapshot"

    @staticmethod
    def data_of(obj):
        return obj.data

    @staticmethod
    def object_of(data, context):
        obj = getattr(context, "object", None)
        if obj is not None and obj.data is data:
            return obj
        return None

    @staticmethod
    def folders(data):
        return data.vgo_folders

    @staticmethod
    def assignments(data):
        return data.vgo_assignments

    @staticmethod
    def settings(data):
        return data.vgo_settings

    @staticmethod
    def folder_index(data):
        return data.vgo_folder_index

    @staticmethod
    def set_folder_index(data, index):
        data.vgo_folder_index = index

    @staticmethod
    def members(data):
        owner = mesh_member_owner(data)
        return owner.vertex_groups if owner is not None else ()

    @staticmethod
    def member_names(data):
        owner = mesh_member_owner(data)
        return [group.name for group in owner.vertex_groups] if owner is not None else []

    @staticmethod
    def member_by_name(data, name):
        owner = mesh_member_owner(data)
        return owner.vertex_groups.get(name) if owner is not None else None

    @staticmethod
    def active_member(data, obj):
        if obj is None or obj.data is not data or not obj.vertex_groups:
            return None
        return obj.vertex_groups.active

    @staticmethod
    def focus_member(data, obj, member):
        if obj is None or obj.data is not data:
            return
        obj.vertex_groups.active_index = member.index

    @staticmethod
    def is_listable(data, member_name):
        return True


class ShapeKeyKind:
    """Shape keys: folders live on the mesh, and the basis never enters the list."""

    add_op = "sko.add_folder"
    remove_op = "sko.remove_folder"
    move_op = "sko.move_folder"
    visibility_op = "sko.toggle_folder_visibility"
    isolate_op = "sko.isolate_folder"
    assign_op = "sko.assign_to_folder"
    remove_member_op = "sko.remove_from_folder"
    move_filtered_op = "sko.move_filtered_to_selected_folder"
    moved_message = "Moved {} shape keys to {}."
    member_name_attr = "shape_key_name"
    snapshot_attr = "shape_key_name_snapshot"

    @staticmethod
    def data_of(obj):
        return obj.data

    @staticmethod
    def object_of(data, context):
        obj = getattr(context, "object", None)
        if obj is not None and obj.data is data:
            return obj
        return None

    @staticmethod
    def folders(data):
        return data.sko_folders

    @staticmethod
    def assignments(data):
        return data.sko_assignments

    @staticmethod
    def settings(data):
        return data.sko_settings

    @staticmethod
    def folder_index(data):
        return data.sko_folder_index

    @staticmethod
    def set_folder_index(data, index):
        data.sko_folder_index = index

    @staticmethod
    def members(data):
        return data.shape_keys.key_blocks if data.shape_keys else ()

    @staticmethod
    def member_names(data):
        return [key.name for key in data.shape_keys.key_blocks] if data.shape_keys else []

    @staticmethod
    def member_by_name(data, name):
        if not data.shape_keys:
            return None
        return data.shape_keys.key_blocks.get(name)

    @staticmethod
    def active_member(data, obj):
        if obj is None or obj.data is not data:
            return None
        return obj.active_shape_key

    @staticmethod
    def focus_member(data, obj, member):
        if obj is None or obj.data is not data or not data.shape_keys:
            return
        obj.active_shape_key_index = data.shape_keys.key_blocks.find(member.name)

    @staticmethod
    def is_listable(data, member_name):
        blocks = data.shape_keys.key_blocks if data.shape_keys else ()
        return not blocks or member_name != blocks[0].name


VERTEX_GROUPS = VertexGroupKind()
SHAPE_KEYS = ShapeKeyKind()


# Every list is drawn at its own height (the panels define theirs) and can be
# dragged taller up to this many rows. ``rows`` is the default *and minimum* number
# of rows and ``maxrows`` the maximum: while the two are equal the height is pinned
# and no drag handle appears, so the cap stays above every starting height.
LIST_MAX_ROWS = 20

# Tooltip of the two filter menus. A menu button drawn with no text of its own is
# described by its menu, so the menu needs a description of its own for the hover
# text to say anything - and to have anything to translate.
FILTER_MENU_DESCRIPTION = (
    "Bulk actions that act only on the rows the search and folder filter show"
)
