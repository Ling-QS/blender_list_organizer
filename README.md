# List Organizer

Organize **vertex groups** and **shape keys** into custom folders with search filtering, right inside
Blender's Object Data properties. Requires **Blender 5.1 or newer**.

## Features

**Vertex groups** (stored per object, panel `Vertex Group Organizer`)

- Custom folders with stable ids: create, rename inline in the list, reorder with the up/down buttons,
  and delete — deleting keeps the groups and returns them to *Unfiled*.
- A group can be filed into **several folders at once**; *Active out of …* takes the active group back
  out of the selected folder.
- *Filed* and *Unfiled* are two independent switches: each one shows or hides its half of the list, either
  or both can be on, and neither of them touches a folder switch. Per-folder hide and *isolate* (solo) mode
  decide which filed members show — any number of folders can be soloed at once and the list is then their
  union, a soloed folder ignores its own hide switch, and a member listed in two folders stays visible while
  either of them is switched on. Solo is the narrowest and most temporary of the three, so it overrides both
  switches while it lasts: a soloed list is the soloed folders and nothing else, the unfiled pile included —
  that pile is usually the largest and least organized half, and exactly what soloing a folder is meant to get
  out of the way. Clear the solo and both switches take over again, exactly as they were left. While a folder
  is soloed the *Unfiled* switch is dimmed, so it is clear that the unfiled pile is being held back rather  than being empty. Creating a group or a key turns *Unfiled* on and clears every solo before it hands the new
  row back as the active one: a new member belongs to no folder, so with Unfiled off — or a folder soloed — the
  row would be filtered straight back out and the button would look like it had done nothing. Nothing else
  about the view is touched, so a search box that still filters the new name out is what the scroll button is
  for. The two bulk switches that undo a whole column of hide and solo presses at once —
  *unhide all folders* (`HIDE_OFF`) and *clear all solo* (`SOLO_OFF`) — sit right-aligned above the folder
  list. They are folder controls, so that is where they belong, and the row above the list is the only one
  with room for them; the button row below keeps to the per-folder buttons and can therefore size to them
  instead of splitting its width, which used to squeeze them as the panel narrowed. Turning the last switch
  of the two off hands the view to the other half instead, so the list is never left empty. A new folder is
  made **right below the selected one** rather than at the end: a folder list reads as a plan, and the new
  entry belongs next to the folder it was thought of beside. With the last folder selected that is the end of
  the list, as it always was, and the new folder is the one left selected so it can be renamed at once. The
  list is a property collection, which can only append, so an insert rewrites it from a snapshot - the same
  route the move buttons take, and the one that carries each folder's uid, so assignments are untouched. The
  *Filed* /
  *Unfiled* switches, by contrast, sit over the **member** list: they decide which members show, which is
  that list's business rather than the folder list's.
- Search box drives a filtered list — a button next to it inverts the search (show what it hides) while a
  search is typed. It sits under the member list, where Blender puts the filter of a list of its own. The box
  matches the way that one does too: a plain word matches anywhere in the name, and `*` and `?` work as
  wildcards. The actions that work on the filtered set (lock / unlock / invert, clear, delete
  unlocked, delete, delete empty with an *ignore zero weights* option, remove selected vertices) live in
  their own menu under the panel's menu button, so Blender's own menu stays short.
- The upper menu button opens Blender's own *Vertex Group Specials* menu (see "The side menus are split"),
  which the add-on adds *Delete Empty Vertex Groups* (every empty group, whether or not the filter shows it),
  *Archive Deform Bone Groups* and *Copy Folders to Selected Objects* to — the last one merges this object's
  folders into the other selected meshes (matched by folder id, so nothing is duplicated or overwritten) and
  files every group they also have by name into the folders it came from. One click sets a second object up
  the same way. The folder-order view is a switch, so it is a button under the move buttons rather than a
  menu entry.
- *Copy Weights from Selected Points* / *Paste Weights to Selected Points* (edit mode only, same specials
  menu): copy what the selected vertices weigh in the active group, then paste it into the active group of the
  same or another object, matched by vertex index. In edit mode weights live in the session's deform layer, so
  the paste writes there — writing through `vertex_groups` would land behind the edit session and be lost.
- Linked meshes are read-only. Both panels say so instead of drawing buttons that only ever cancel, and every
  folder operator reports the same reason when one is pressed anyway.
- Follows renames: rename a group (here or in Blender's own list) and its folder membership follows;
  deletions are pruned automatically. The pairing is deliberately conservative — a rename is only
  recognised when exactly one name vanished and one appeared *and* the two still look alike. Everything
  else (a delete plus an add, a swap of two names) is left alone, because a wrong pair would hand one
  member's folders to another.
- Folders carry a **label**: one of Blender's icons, colours included, chosen from a `COLOR` button in the
  folder controls row (between the delete button and the move buttons, with a gap on either side). The button
  opens the palette as a **floating popup panel** (`wm.call_panel`) — a `COLOR` button between the delete button
  and the move buttons, with a gap on either side. The panel is registered with `bl_options = {"INSTANCED"}`, which
  is what keeps it floating: without it Blender also lists it permanently in the Properties editor. It is a panel
  rather than a menu on purpose: a menu's content is a *column*, so every way of expanding an enum inside one came
  out a single entry per line (a hand-built grid, `prop(expand=True)`, `prop_enum` and `operator_enum` were all
  tried), while a panel lays out rows freely. The palette is therefore a real grid of **borderless** icon
  buttons, ten to a row, each exactly icon-wide; the popup has no fixed width, so it hugs the grid instead of
  leaving a band on the right. The tag property carries an `update` callback that repaints the panels, so a new
  label shows up while the popup is still open rather than when it closes. Both the folder row and a member row
  show the label **in place of** their usual icon. A member takes the label of the first folder that would show
  it (solo and hide respected), and *Archive Deform Bone Groups* tags the folder it creates with `BONE_DATA`. A
  folder holding the **active** member is marked by a trailing `FOLDER_REDIRECT` icon — not brackets around the
  name, which would wrap the tag icon too and cost far more width. The member list is introduced by its own
  bare icon, in front of the search box.
- The *Active Group* title above the list carries the two buttons that **file the active member** (`>` into the
  selected folder, `<` back out of it) and ends in a small `RESTRICT_SELECT_OFF` button that scrolls the
  active group to the **sixth row** — five rows below the top edge — rather than to whichever edge it happens
  to be next to. Blender scrolls a list to its active row only when that row changes, and always by the
  *smallest* step that brings it back into view, so no position can be asked for directly. Which row a list
  counts as active is whatever property the panel hands `template_list`, though, so the button hands it
  stand-in rows instead, both of them taken from the rows the list is actually showing — a stand-in it cannot
  find leaves it with no active row at all, which clamps the scroll to the top: first the last *visible* row,
  which parks the list at its end whatever it showed before, and then one five rows above the active row
  among the visible ones. A list scrolled below that row is brought up exactly to it, which drops the active
  row five rows below the top edge — and no list height enters that sum, which is why this landing row was
  chosen over the middle: the middle would need the height, and a `UIList` exposes neither that nor its
  scroll position. A further draw hands the list its real active row back. The last visible row is approached
  in two steps — the row before it, then itself — because a list does not scroll for a row it already counts
  as active, and one row short of the end the stand-in after it would scroll to the wrong place. An active
  row with too few rows below it to reach the landing row lands as near the top as the scroll range allows,
  which for the last rows means the bottom of the list: a list of *n* rows showing *R* of them can only
  scroll *n − R* rows, so the last rows simply cannot be brought any higher. Nothing is written to the
  object and no row is hidden — only which property the list reads its active row from.
- If the active group is **hidden** — by the search box, a hidden folder, a solo, or the *Filed* / *Unfiled*
  switch that covers its half — the button undoes that first, by the smallest change that does it: the search
  is cleared, a list with a solo running takes the member's own folder into the solo, otherwise the hidden
  folder it is in is shown, and the switch is turned on. The smallest change matters: with a solo running the
  solo is *not* dropped, so whatever else was soloed stays soloed. What was changed is reported. A member
  with no folder at all is the one case that drops the solo instead, there being nothing else that would let
  it through. The basis key is not in the list to begin with, so scrolling to it is refused with a word about
  why.
- **Organize mode** — the *Organize* switch on the folder list's own row, next to the icon that introduces that
  list. Filing a long, irregularly named
  list one member at a time costs two clicks each with a focus switch in between, and a search can only batch
  what it can match, which is nothing when the names follow no pattern. Organize mode puts a **pick mark** on
  every row, **beside the lock button rather than in its place**: every member starts picked, so the work is
  deselecting the few that belong elsewhere, and a press-and-drag across rows marks a run at once, exactly as
  the lock button does. The lock keeps its slot because Blender's own weight edits skip a locked group, so
  unlocking one is exactly what a bulk filing session runs into — with the pick in that slot the button sat
  behind a mode switch. The row is one icon wider for it. Two
  rows then appear under the folder controls and file or unfile **every picked row** in one go; *select all*,
  *invert* and *clear* live under the folder-order switch. Only rows that are both **visible and picked** take part — a
  member the search box or a folder hides keeps its mark but is left alone — so the count above the list and
  the bulk actions always describe the same set, and one *invert* after a *clear* picks everything in view
  again. The mark is stored on the assignment record, because a vertex group and a shape key carry no
  properties of their own, so entering the mode first gives every visible member a record for the button to
  write to. The mode is a way of working rather than file content, which is why its switches are drawn as
  operators with `REGISTER` only: an operator button takes no undo step. Measured on 5.2 that is *not* the same
  as keeping it out of the file — a `PropertyGroup` on a mesh is written into the `.blend` whatever its
  `SKIP_SAVE` flags say, so the mode does come back with the file it was left on.
- Left/right pair shortcuts (`.L`/`.R`, `_L`/`_R`, `left`/`right`, `左`/`右`, ...) for the active group.
- *Archive Deform Bone Groups*: file every group whose name matches a deform bone of a selected armature into
  a folder called *Bone Deform* (the name is translated like every other label).

**Shape keys** (stored per mesh, panel `Shape Key Organizer`)

- The same folder, search (with the same invert button), isolate and bulk toolkit (lock, mute, reset
  values, delete filtered), and the same scroll-to-active button on the *Active Key* title.
- The basis key is shown separately, as a one-row list of its own above the organizer: only the first key is
  let through, so it is always that one row and never a row of the folder list — it can therefore not be filed
  by accident. Being a list row rather than a button, its name is a real text field: a click makes the basis
  the active key, a double-click renames it, and the list shows the active row by itself. Its mute and lock are
  the same property buttons the keys in the list carry. The remove button does delete the basis, exactly like
  Blender's own operator: the next key becomes the basis and is baked into the mesh, and removing the last key
  drops the shape keys entirely.
- A muted key dims its **name and value** only. The buttons beside them keep their normal contrast because
  they still work on a muted key, and a greyed-out button reads as a disabled one.
- The upper menu button opens Blender's own *Shape Key Specials* menu with the add-on's *Folder Order in
  List*, offset selection, blend group entries and *Copy Folders to Selected Objects* appended; the filter
  actions sit in the menu button below it (see "The side menus are split").
- *Deforming Shape Keys*: a sub-panel under the organizer holding a second list of the keys actually deforming
  the mesh — unmuted and off zero, basis excluded. It is the organizer's own list with a different filter, so
  its rows carry the same name, value slider, mute and lock buttons, plus a **pin** that keeps a key in this
  list even while it is muted or sitting at zero — the pin is a real property, so it presses and drags across
  rows exactly like the buttons next to it. Its right-hand button column carries two list-wide switches, kept
  apart by a gap: *unpin everything*, and a *filter* toggle — off by default — that lets the folder filter
  narrow this list as well. The search box never narrows it: search is shared with the organizer above, so
  typing there must not empty this list while it is being read. The name keeps clear of Blender's own *Active
  Shape Key*, which is the one being edited. It hangs off the organizer and starts collapsed.
- Blend group workflow: *Select Offset Vertices*, *Remove Selected Offsets*, *Auto Create Blend Vertex
  Group* (every vertex the active key moves), *Create Blend Vertex Group* (the vertices selected in edit
  mode, edit mode only) and *Apply Blend Vertex Group* to mask or bake the part of the mesh a key moves.
- *Copy Offsets from Selected Points' Shape Key* / *Paste Offsets to Selected Points' Shape Key* (edit mode
  only, same specials menu): copy how far the selected vertices are displaced in the active key and paste it
  back, either into another key or onto another object with the same topology. A relative key's value scales
  what it does to the mesh, so the copy is taken at the value the key has right now and the paste undoes the
  target key's own value — what lands is the offset you saw on screen, not the raw one. *Apply Offsets to
  Selected Points* leaves the value out instead: the stored offset is added to the vertices of the active key
  exactly as it stands, which is a plain vertex displacement. The clipboard lives for the session.
- *Folder Order in List* groups the list by folder instantly, without touching the data
  (see "Folder order is a view" below).
- **Key sync** (a box at the bottom of the panel): switch *Sync Keys* on for an object and every
  shape key value you edit **on that object** is copied to the same-named keys of the objects in its
  target collection. Only objects with the switch on act as sources, only edited keys are pushed, and
  the switch is off by default. The *Animated Sync* switch right after it — also off by default — decides
  whether values moved by an **action or a driver** count as edits: with it off, only manual edits
  mirror, so a synced object does not quietly become a live mirror of somebody's animation. A key is
  counted as animated when its `value` has an fcurve in the object's action (layered actions included)
  or a driver. The mirror **stands down while a render runs**, and comes back when the render ends however
  it ended: writing values into the original data cannot reach the frame already evaluated from it — so
  mirroring during a render would only make the result depend on the order the frames were asked for. A
  render plays what the file holds.

## Installation

1. Download or build `list_organizer.zip`.
2. Blender: `Edit > Preferences > Add-ons > Install from Disk…` and pick the zip.
3. Enable **List Organizer**.
4. Open `Properties > Object Data` on a mesh: the two organizer panels are at the bottom.

The zip is a standard Blender extension package (`blender_manifest.toml` at the package root), so the
same file also works with `Edit > Preferences > Get Extensions > Install from Disk`.
For a legacy `scripts/addons` install, copy the `list_organizer/` folder there instead.

## Where your folders are stored

| | Property | Stored on |
|---|---|---|
| Vertex group folders | `vgo_folders`, `vgo_assignments`, `vgo_settings` | `Mesh` |
| Shape key folders | `sko_folders`, `sko_assignments`, `sko_settings` | `Mesh` |

Folder membership is a `(name, set of folder uids)` pair, so it survives renames, allows several
folders per group or key, and the whole thing lives in the `.blend` file — no external data, no side
files. The one piece of data the add-on still tolerates from an older layout is the `__ROOT__` sentinel:
early versions recorded "unfiled" as that uid instead of an empty set, and dropping it as an unknown uid
would silently unfile those members. The shape key sync switch and its target collection are per object
(`object.sko_sync`), so they travel with the file too.

Both trees sit on the mesh because that is where the things they organize live. Shape keys are mesh
data outright; vertex groups are *reached* through `Object.vertex_groups` but their names and weights
are stored on the mesh (Blender 3.0 moved them there), so a brand new object built on an existing mesh
already has that mesh's groups. Objects that share a mesh therefore share one folder tree, which is
what linked duplicates (Alt+D) expect.

## Development

```
list_organizer/
    __init__.py          registration, throttled rename-following scan
    common.py            shared helpers: folder ids, rename pairing, mirroring, scroll requests
    folders.py           the data layer: folders, memberships, visibility, ordering
    folder_ops.py        the shared folder operators, one per user action
    folder_tags.py       the tag palette: the icons, and the lookups that use them
    folder_ui.py         the list row, the button rows and the member list header both panels draw
    kinds.py             the list-kind adapters (`VertexGroupKind` / `ShapeKeyKind`)
    scan.py              the rename-following scan, and the timer the panels arm it with
    icons.py             the add-on's own icons, and the preview collection they live in
    icons/               those icons as SVG: folder add/remove, holds, empty, move in/out, tag
    sync.py              shape key value mirroring: the sync box and the pass behind it
    translations.py      zh_HANS / zh_HANT table
    blender_manifest.toml
    vertex_groups/       the vertex group organizer
        __init__.py      re-exports every name the add-on, the shared half and the tests address
        model.py         model: helpers and the property groups
        list.py          the two vertex group UILists
        ops.py           the vertex group operators
        panel.py         the vertex group panel and its menus
    shape_keys/          the shape key organizer
        __init__.py      the same re-exports for this package
        model.py         model: helpers, flags and the property groups
        list.py          the four shape key UILists: folders, basis, visible keys, deforming
        ops.py           the shape key operators, offsets included
        panel.py         the shape key panel, its sub-panel and its menus
tests/smoke_test.py      headless end-to-end checks
tools/build.py           version bump, smoke test, zip build, extension validation
tools/svg_icons.py       normalises the icon files' declared sizes before a build
tools/health_check.py    a hand-run report on the add-on's own state
```

The shared half lives at the top: `folders.py` reads and writes folders and memberships and knows
nothing about operators, `folder_ops.py` drives that data one user action at a time, `folder_tags.py` holds the
palette, and `kinds.py` is the small per-kind adapter (`VertexGroupKind` / `ShapeKeyKind`) they all speak
through. `folder_ui.py` is the folder drawing half. Each organizer is then a package of the same four
modules: a model, a list, an operator module and a panel module.

Those four import each other in one direction only — the package's `__init__.py` imports them in that
order, and each of the others imports names back from `model` at import time, by which point `model` has run
to the end. The `__init__.py` re-exports everything they hold, which is why
`vertex_groups.VGO_Settings` and the like still resolve, and why nothing outside the package has to know
which of the four a name lives in. The zip keeps the two package folders, so it mirrors the source tree.

Visibility is resolved once per draw and handed to every member as a `VisibilityContext` (a named tuple of the
search term, the two view switches, the soloed and switched-on folder sets, and a name → assignment table).
Deriving any of it per member is what turns a linear pass over the list into a quadratic one. The context also
holds each assignment's folder uids already parsed and the folder of the tag that marks a member, so both of
those questions are a dict lookup instead of a re-split of a membership string per member per folder. Each
list builds the context once in `filter_items` and keeps it on the list instance, so the draw pass that
follows reuses it instead of building one per row.

Run the checks and build a release package with any Python 3.11+:

```bash
python tools/build.py --check                 # metadata consistency only
python tools/build.py --test                  # headless smoke test
python tools/build.py --version 1.3.0         # bump, test, build, validate
python tools/build.py --no-test --no-validate # just rebuild the zip
python tools/build.py --install               # ... and install into the user repository
python tools/build.py --install-dir PATH      # ... or copy into PATH/list_organizer
```

`--install` runs `blender --command extension install-file -r user_default`, so pass the Blender whose
repository you want to refresh (`--blender PATH`); it keeps that repository's metadata in sync instead
of just dropping files in. This checkout is mirrored into
`C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\list_organizer`,
so a release round is:

```bash
python tools/build.py --version 1.7.1 --install --blender "F:\Blender Foundation\Blender 5.2\blender.exe"
```

Blender reads an extension when it starts, so reload it in the running session (`Edit > Preferences >
Get Extensions`, disable then enable, or restart Blender) after syncing.

### Publishing the add-on on its own

`https://github.com/Ling-QS/blender_list_organizer` holds **only** what is inside `list_organizer/`, with the
package at the repository root so Blender's own tooling finds `blender_manifest.toml` where it expects it. It is
a *subtree* of this checkout, not a second copy of it: `git subtree split` rewrites the history down to that one
path, and the branch it writes is what gets pushed.

```bash
git branch -D ext_publish                                    # the split wants to create the branch
git subtree split --prefix=list_organizer -b ext_publish
git push https://github.com/Ling-QS/blender_list_organizer ext_publish:main
```

`tools/`, `tests/`, the README and the other repository files stay here: `git subtree split` drops everything
outside the prefix, so the published tree is 29 files - the package, its icons and its licence.

`tools/build.py` finds Blender via `--blender PATH`, `$BLENDER_BIN`, `blender` on `PATH`, or a
default install location. To run the smoke test by hand:

```bash
blender --background --factory-startup --python tests/smoke_test.py
```

`list_organizer/blender_manifest.toml` is the single source of truth for the version, and the build
script reads it back to check the shape of it. The zip is written with fixed timestamps so identical
sources produce identical artifacts.

Implementation notes worth knowing before changing things:

- The rename-following scan runs from a one-shot timer that the **panels arm as they draw**
  (`list_organizer/scan.py`), not from a depsgraph handler: a stale record only shows up in a list, and a
  draw is also the moment the user is looking. The timer is throttled to `scan.SCAN_INTERVAL`, so drawing
  several times a second costs one scan, not one per draw. Operators that need a fresh mapping call the sync
  functions directly.
- The sync functions return early for IDs without assignments, so scenes that never use the add-on
  cost nothing. The first tracked item records a name snapshot baseline, which is what makes rename
  detection work after that early-out.
- Folder membership is stored per name with a stable folder uid, so renames follow and reordering
  folders never touches the groups; `bpy_prop_collection.move()` only permutes the folder list.
- Shape key mirroring runs from a repeating timer that only exists while at least one object has the switch
  on (`list_organizer/sync.py`): it registers when the switch goes on or a file is loaded with one already on,
  and unregisters when the last one goes off. It looks at the objects in the registry only — they are tracked
  in a set maintained by the toggle's update callback and rebuilt from `load_post` — and compares each source
  against its previous values, so nothing is written unless a key really changed. It copies values outside of
  any operator, which means undo does not take the mirrored values back.
- The panels are drawn headlessly in the tests against a recording fake layout, because Blender
  cannot draw a real panel without a window. Keep draw code limited to layout calls the fake covers
  (see `_FakeLayout` in `tests/smoke_test.py`).
- The smoke test checks that every key in `translations.py` still appears as a string literal in the
  add-on source, so entries cannot outlive the button they translate (Blender translates its own menus,
  ours are appended to them - see "The side menus are split").

### Folder order is a view, not a reorder

*Folder Order in List* (a per-object/mesh switch, the folder button under the move buttons in each panel)
is display only: the UIList's `filter_items` returns a custom `order`, so the list is shown grouped by
folder (unfiled last, stable inside a folder) while the datablocks, the undo stack and Blender's own
lists stay exactly as they were. It is instant for any number of entries and can be switched off again.

Grouping physically was tried and removed in 1.7.0. Blender moves one slot per operator call
(`vertex_groups` and `key_blocks` have no `move()`), so grouping N entries needs one call per slot a
member travels — the number of pairs sitting in the wrong order — which grows with the square of the
list. Measured on a four folder worst case (reverse order):

| entries | moves | vertex groups | shape keys |
|---|---|---|---|
| 100 | 1 950 | 0.5 s | 1.0 s |
| 200 | 7 650 | 3.3 s | 7.6 s |
| 400 | 30 300 | 31 s | 55 s |

Beside being slow it was dangerous: each of those `bpy.ops` calls takes an undo step, and an undo step is a
snapshot of the whole file, so a few thousand moves piled up thousands of snapshots, which made big sorts hang
and eventually crash. The step-wise name sort that grew out of this lesson is gone: Blender's own operators and
the folder-order view cover the same ground without walking the list slot by slot.

Folder *storage* order is real data, so the up/down buttons move the folders themselves. Two things can
still make a move look like it did nothing:

- Blender's own list sort, in the filter row the little triangle at the list's bottom-left opens. With *Sort by
  Name* on there, the rows are shown in name order, so reordering folders (which the arrows do correctly)
  cannot be seen. Turn it off to see and change the real order; the add-on never enables it.
- A list shorter than its content. The two move buttons sit on the *Active Group* / *Active Key* heading and act
  on the folder **selected in the folder list**, so a selection scrolled out of view looks like a dead pair —
  select the row you want to move first. Each
  list starts at its own height (vertex groups: 5 rows of folders, 16 groups; shape keys: 5 rows of
  folders, 16 keys) and can be dragged taller up to `folders.LIST_MAX_ROWS` (20): `rows` is the default
  height, `maxrows` the maximum it may be dragged to.

### Why the move buttons are icon-only

They sit on the *Active Group* / *Active Key* heading, right-aligned, with a gap before the scroll button. They
are icon-only because Blender sizes a button by the button, not by the layout: a button with a label stretches
to the width it was given, one without a label keeps its own. Measured in a probe panel:

| button | measured width |
|---|---|
| icon only | 25–31 px |
| icon only, inside an aligned row | 31–33 px |
| `text=" "` (or a zero-width space) plus icon | 25 px |
| `text=">"` plus icon | 31 px |
| `text="In"` plus icon | 35–39 px |
| `text="Organize"` (a labelled switch, for scale) | 88 px ≈ its half |

That is also why the heading gives the three buttons the right end rather than a share of a split: a split
hands out width, and an icon button ignores it. Labelling the two move buttons did fill the shares a split
gave them, but it also put a word beside two icons that already say in and out, so they stay icon-only and
packed together.

### The two list headings

Each list is introduced by its own row, and the two rows that used to share one are now apart, on the side each
belongs to. The folder list's row is its icon, the *Organize* switch and the two bulk switches; the switch
takes the left half of a `split(factor=0.5)` because that is the shape a view switch takes on the member side,
and the two bulk switches keep the right edge. The active member's row is its title, the two buttons that file
it and the scroll button. Nothing is drawn under the folder list in the ordinary mode: the two rows that file
and unfile every picked member appear there only while organize mode is on.

The entries under that heading go in a **plain** column, not an aligned one. An aligned column hands every row
the width of its widest one, so a long member name reaches the heading row above it and takes the gap before the
scroll button with it — and, in a narrow panel, the width it asks for is what pushes the member list's own
button column off the edge. A plain column keeps each row to the box's own width; the entries then sit a hair
further apart, which is the trade. The heading itself is left exactly as it was: rewriting how its label and its
three buttons share that row is what broke the panel the last time it was tried.

### The side menus are split

The upper menu button in each panel opens Blender's own specials menu
(`MESH_MT_vertex_group_context_menu`, `MESH_MT_shape_key_context_menu`); the add-on *appends* its own
entries to it (`vertex_groups.draw_vertex_group_specials`, `shape_keys.draw_shape_key_specials`). One menu
then holds Blender's entries, ours and anything another add-on appended, so a foreign item cannot be
missed. Earlier versions kept a menu of their own and hand-copied Blender's entries into it, which drifts
with every release and can never show a foreign item; the idname is looked up when registering, so a
Blender without that menu simply gets the entries nowhere rather than an error.

Only entries that make sense beside Blender's own go there. Everything that acts on *what the search and
folder filter show* lives in a second menu under it (`VGO_MT_filter_menu`, `SKO_MT_filter_menu`, the
funnel button) — a list of nine filtered actions would push Blender's own menu off the screen. Because
those actions read the same `filter_items` result the panel lists, they always act on exactly the rows the
user sees, inverted search included.

### Why there is no depsgraph handler

Earlier versions ran shape key mirroring inline from `bpy.app.handlers.depsgraph_update_post`, and used the
same handler to arm the rename-following scan. It is gone, for two reasons: a hook on that path fires on
every weight paint stroke, sculpt dab and playback frame even in a file that never switches sync on, and the
Extensions platform review asks hard questions about exactly that kind of hook.

What replaced it:

1. **Mirroring** runs from a repeating timer (`sync.MIRROR_INTERVAL`, one frame at 60 Hz) that exists only
   while at least one object has *Sync Keys* on. A dragged slider is therefore mirrored within a frame, and a
   file with nothing switched on has no timer at all.
2. **The rename-following scan** is armed by the panels as they draw, throttled to `scan.SCAN_INTERVAL`, and
   fires once. A stale record is only visible in a list, so a draw is the right moment to look for one.

Measured on a 201 object × 50 vertex-group scene, the old handler cost 0.22 µs per update when nothing synced
(0.013 ms per second at 60 Hz) and 14 µs per update with one object mirroring 21 keys; the scan cost 0.15 ms.
The numbers were small, but the point of removing it is not the microseconds: it is that the add-on now
touches no hot path at all, and its cost is zero unless the user asks for the feature.

Alternatives that were probed:

| Option | Why it was not taken |
|---|---|
| `bpy.msgbus.subscribe_rna()` | Delivers no notifications in a headless run, not even for `Object.location`, so the tests could not cover it. Drivers and animation drive values through evaluation rather than RNA writes, so a notification would also miss exactly the changes the mirror has to catch. |
| A stable id per group/key instead of name tracking | `VertexGroup` and `ShapeKey` are not ID types; registering a custom property on them fails with "attribute is read-only", so membership has to stay name based — which is why rename following exists at all. |
| Keeping the depsgraph handler | It works and it is cheap, but it is a hook on the busiest path in Blender, and the review treats such a hook as a red flag. |
| Pull only (panel draw + own operators) | Enough for folder renames, not for value mirroring: editing keys in Blender's own Shape Keys panel or through a driver never draws our panel. |

Note that msgbus and timers both need the GUI main loop, so neither fires in a `--background` run; the tests
call the functions and check the registrations directly instead.

### Shape key sync with several sources

Any number of objects in the same target collection may have *Sync Keys* switched on. The pass is built
so that they cannot ping-pong:

- Each source remembers the values it had at the previous pass and pushes only keys that really
  changed, so an edit propagates once and the next pass finds nothing to do.
- Values copied by the pass itself are recorded while pushing, and the caches of the objects that were
  written to are refreshed at the end. A source therefore never pushes our own write back: without
  this, the second syncing object in a collection handed the value it had just been given back to
  everybody on the next update, overwriting whatever the dragged object had moved on to — which is
  what made a slider snap backwards while being dragged.
- Each source's remembered values are keyed by the object's own pointer (`as_pointer()`), not by its name.
  Two objects may carry the same name in different scenes, and a rename between two passes used to hand one
  object's remembered values to another, which showed up as a slider jumping on the next pass. The registry
  of *which* objects sync is still keyed by name, because it is rebuilt from the scene when a file is loaded.
- Sources are visited in name order. When two of them genuinely change in the same pass (drivers,
  animation, scripts) the outcome is then at least reproducible, instead of depending on `set`
  iteration order, which differs between Blender sessions.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).

The icon files in `list_organizer/icons/` are released as CC0 (public domain), which is what the Blender
Extensions platform requires of an extension's images: see its
[Terms of Service](https://extensions.blender.org/terms-of-service/) §1.2. Everything else in the extension is
covered by the GPL above, and no third-party code, fonts or images are bundled.
