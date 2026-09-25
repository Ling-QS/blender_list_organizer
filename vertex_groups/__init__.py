"""The vertex group organizer as one package: model, list, operators and panel.

The four modules import each other in one direction only - this file imports them in that order, and each
of them imports names back from ``model`` at import time, by which point ``model`` has run to the end. Every
name the add-on, the shared folder machinery and the tests address is re-exported here, so
``list_organizer.vertex_groups.VGO_Settings`` and the like keep working.
"""

from .model import *  # noqa: F401,F403  (the model's own names)
from .list import (  # noqa: F401  (re-exported names)
    VGO_UL_folders,
    VGO_UL_visible_groups,
)
from .ops import (  # noqa: F401  (re-exported names)
    _WEIGHT_CLIPBOARD,
    VGO_OT_add_folder,
    VGO_OT_remove_folder,
    VGO_OT_move_folder,
    VGO_OT_remove_from_folder,
    VGO_OT_toggle_filed,
    VGO_OT_toggle_unfiled,
    VGO_OT_unhide_all_folders,
    VGO_OT_clear_solo,
    VGO_OT_set_folder_tag,
    VGO_PT_folder_tag_popup,
    VGO_OT_copy_folders_to_selected,
    VGO_OT_copy_selected_weights,
    VGO_OT_paste_selected_weights,
    VGO_OT_assign_to_folder,
    VGO_OT_move_filtered_to_selected_folder,
    VGO_OT_toggle_group_by_folder,
    VGO_OT_add_vertex_group,
    VGO_OT_remove_vertex_group,
    VGO_OT_move_vertex_group,
    VGO_OT_activate_pair_group,
    VGO_OT_scroll_to_active_group,
    VGO_OT_lock_filtered_groups,
    VGO_OT_delete_filtered_groups,
    VGO_OT_delete_filtered_empty_groups,
    VGO_OT_delete_empty_groups,
    VGO_OT_clear_filtered_groups,
    VGO_OT_remove_selected_from_filtered_groups,
    VGO_OT_archive_deform_groups,
    vgo_weight_context,
    vgo_deform_layer,
)
from .panel import (  # noqa: F401  (re-exported names)
    VGO_MT_filter_menu,
    VGO_PT_vertex_group_organizer,
    draw_vertex_group_specials,
    register_menus,
    unregister_menus,
    classes,
)
