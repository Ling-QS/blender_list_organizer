"""The shape key organizer as one package: model, list, operators and panel.

The four modules import each other in one direction only - this file imports them in that order, and each
of them imports names back from ``model`` at import time, by which point ``model`` has run to the end. Every
name the add-on, the shared folder machinery and the tests address is re-exported here, so
``list_organizer.shape_keys.SKO_Settings`` and the like keep working.
"""

from .model import *  # noqa: F401,F403  (the model's own names, the sync names included)
from .model import (  # noqa: F401  (the sync names, which a star import would skip)
    _SYNCED_VALUES,
    _SYNC_OBJECT_NAMES,
    _syncing_objects,
)
from .list import (  # noqa: F401  (re-exported names)
    SKO_OT_clear_key_pins,
    SKO_OT_toggle_deforming_filter,
    SKO_UL_basis_key,
    SKO_UL_deforming_keys,
    SKO_UL_folders,
    SKO_UL_visible_keys,
    sko_draw_key_row,
)
from .ops import (  # noqa: F401  (re-exported names)
    _OFFSET_CLIPBOARD,
    SKO_OT_add_folder,
    SKO_OT_add_shape_key,
    SKO_OT_activate_pair_key,
    SKO_OT_apply_offset_vertex_group,
    SKO_OT_apply_stored_offsets,
    SKO_OT_assign_to_folder,
    SKO_OT_clear_solo,
    SKO_OT_copy_folders_to_selected,
    SKO_OT_copy_selected_offsets,
    SKO_OT_create_blend_group,
    SKO_OT_create_offset_vertex_group,
    SKO_OT_delete_filtered_keys,
    SKO_OT_isolate_folder,
    SKO_OT_lock_filtered_keys,
    SKO_OT_move_filtered_to_selected_folder,
    SKO_OT_move_folder,
    SKO_OT_move_shape_key,
    SKO_OT_mute_filtered_keys,
    SKO_OT_paste_selected_offsets,
    SKO_OT_remove_folder,
    SKO_OT_remove_from_folder,
    SKO_OT_remove_selected_offsets,
    SKO_OT_remove_shape_key,
    SKO_OT_reset_filtered_keys,
    SKO_OT_scroll_to_active_key,
    SKO_OT_select_offset_vertices,
    SKO_OT_set_folder_tag,
    SKO_OT_toggle_filed,
    SKO_OT_toggle_folder_visibility,
    SKO_OT_toggle_group_by_folder,
    SKO_OT_toggle_sync,
    SKO_OT_toggle_unfiled,
    SKO_OT_unhide_all_folders,
    SKO_PT_folder_tag_popup,
    sko_offset_context,
)
from .panel import (  # noqa: F401  (re-exported names)
    SKO_MT_filter_menu,
    SKO_PT_deforming_keys,
    SKO_PT_shape_key_organizer,
    classes,
    draw_shape_key_specials,
    register_menus,
    unregister_menus,
)
