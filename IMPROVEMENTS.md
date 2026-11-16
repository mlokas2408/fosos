# FosOS UI improvements plan

Follow-on polish after the Phase 7–14 desktop in [PLAN.md](PLAN.md).
These phases tighten FosOS Desktop toward Windows 10/11 habits without
copying Windows chrome or abandoning Openbox + `fosos-shell`.

Work happens in `packages/fosos-desktop` (`fosdesk/panel.py`, settings,
shortcuts). The `mockup/` tree stays a visual reference only.

---

## Phase 1 — taskbar: virtual desktops like Windows

**Goal:** stop using numbered desktop buttons on the taskbar. Desktop
switching should match Windows: Task View for overview, shortcuts for
quick flips, no pager strip of `1 2 3 4`.

### How Windows handles this

Windows does **not** put numbered virtual-desktop buttons on the taskbar.

| Windows control | Behavior |
| --- | --- |
| Task View button (optional) | Opens the desktop/window overview (Win+Tab) |
| Win+Tab | Task View: create/switch desktops, pick a window |
| Ctrl+Win+← / → | Switch to previous / next virtual desktop |
| Win+Ctrl+D / F4 | Create / close a desktop (Win11) |
| Far-right taskbar edge | Show Desktop (peek / toggle) |
| Win+D | Show Desktop |

Desktop identity lives in Task View (thumbnails + names), not as permanent
taskbar chrome. The taskbar stays Start → (Search) → Task View → apps →
tray → clock → Show Desktop.

### Current FosOS gap

Today the primary panel builds a **workspace pager** of buttons labeled
`1`–`4` (`panel.py` → `rebuild_workspaces`), with Settings → Taskbar →
“Show desktop switcher (1–4)”. Task View already exists (Win+Tab /
`TaskView`), but there is no Task View button on the bar, and there is no
Show Desktop strip on the far right.

That pager is the main visual mismatch with Windows.

### Required changes

1. **Remove the numbered desktop buttons** from the taskbar
   (`workspace_box` / `rebuild_workspaces` UI).
2. **Do not leave a hole:** either hide the old box entirely or replace it
   with a single **Task View** control (see proposals below).
3. **Update Settings → Taskbar:** drop “Show desktop switcher (1–4)”; if a
   Task View button ships, expose “Show Task View button” instead.
4. **Keep desktop switching elsewhere:**
   - Win+Tab Task View (already)
   - Super+1…Super+4 (already; keep for power users)
   - Taskbar / Task View “Move to Desktop N” (already)
5. **Docs / tests:** refresh [docs/DESKTOP.md](docs/DESKTOP.md) and
   [docs/TESTING.md](docs/TESTING.md) so checklists no longer expect the
   pager strip.

**Exit condition:** a default session has no `1`–`4` buttons on the
taskbar; users switch desktops via Task View and keyboard shortcuts; Task
View and Move-to-Desktop still work.

### Proposed further taskbar alignments (same phase or immediate follow-ups)

Ordered by how much they close the Windows gap for daily use:

1. **Task View button next to Start**
   Icon-only control after Start (where Windows puts Task View). Click
   toggles the existing `TaskView`. Prefer this over keeping any pager UI.
   Settings toggle: show / hide the button (default: on).

2. **Ctrl+Win+Left / Ctrl+Win+Right**
   Switch previous / next workspace, matching Windows. Keep Super+1…4 as
   absolute jumps. Wire in Openbox `rc.xml` or shell keybinds.

3. **Show Desktop on the far-right edge**
   Thin hit target at the end of the panel that runs the same action as
   Win+D (`ToggleShowDesktop`). Optional hover peek later; click toggle is
   enough for Phase 1.

4. **Tighter left cluster**
   Layout: Start → Task View → pinned/running apps (separator only where
   Windows would put one). Remove the extra separator that today frames the
   old pager.

5. **Right-click empty taskbar → Taskbar settings**
   Open Settings on the Taskbar page (Windows habit). Complements the
   existing app Pin/Unpin menu on icons.

6. **Hover previews for grouped windows (stretch)**
   On hover over a running task button, show small window thumbnails /
   titles and activate on click—closer to Windows taskbar peek. Defer if
   Wnck/GTK cost is high; not required to close Phase 1.

7. **Search entry on the taskbar (optional, later)**
   Compact Search next to Start that focuses Start search (Win+S style).
   Only if Start search is already fast enough; otherwise skip.

8. **Out of Phase 1 on purpose**
   - Centered taskbar icons (Win11 default): keep left-aligned FosOS layout
     unless a Settings option is requested later.
   - Widgets board, Copilot, News/weather: not in scope.
   - Full StatusNotifier / legacy tray hosting: separate phase if needed.

### Implementation notes

| Area | Likely touch |
| --- | --- |
| Panel UI | `packages/fosos-desktop/.../fosdesk/panel.py` |
| Task View toggle | `shell.py` → `toggle_task_view` |
| Prefs | `settings_pages.py` → `build_taskbar` + `taskbar` kv |
| Shortcuts | `openbox/rc.xml` and/or shell key handling |
| Verify | Hyper-V soak items in `docs/TESTING.md` |

Default preference after this phase: no numbered pager; Task View button
visible unless the user turns it off.

**Status:** planned (not implemented).

---

## Phase 2 — Start menu and search polish *(placeholder)*

**Goal:** Start feels closer to Windows for find-and-launch without redesigning
the whole launcher.

Candidates: stronger Search affordance, pinned vs recommended clarity,
keyboard focus order, All apps scrolling, power/account placement.

**Status:** not started.

---

## Phase 3 — window chrome and snap feedback *(placeholder)*

**Goal:** maximize / snap / restore cues match user expectations from
Windows (layouts already in Phase 13).

Candidates: clearer snap zones, restore-from-snap, titlebar context menu
parity, Alt+Tab preview polish.

**Status:** not started.

---

## Phase 4 — notifications and Quick Settings depth *(placeholder)*

**Goal:** hubs from Phase 10 feel complete for everyday controls.

Candidates: per-app notification toggles, Quick Settings tiles layout,
Focus assist naming, toast stacking.

**Status:** not started.

---

## Phase 5 — desktop icons: grid align, no overlap

**Goal:** desktop icons behave like Windows Explorer’s desktop: they sit on
an invisible grid, and one icon cannot sit on top of another.

### How Windows handles this

| Windows rule | Behavior |
| --- | --- |
| Align icons to grid (default on) | Drop snaps to the nearest cell; free-pixel placement is not used |
| Occupied cells | Dropping on a taken cell moves the icon to the nearest free cell (icons do not stack) |
| Auto arrange icons (optional) | Packs icons into a column/row order and keeps them packed |
| View → Large / Medium / Small | Changes cell size; grid still applies |

Users can rearrange icons, but the desktop never leaves two icons sharing
the same slot.

### Current FosOS gap

`desktop.py` stores absolute pixel positions (`desktop-icons` config) and
`move_icon` only clamps to the primary monitor bounds. There is no snap to
`ICON_W` / `ICON_H` / `ICON_GAP` cells, and nothing prevents two icons from
sharing the same coordinates after a drag. Default layout stacks a column,
but after drag, overlap is allowed. “Reset icon positions” re-stacks; it
does not enforce a live grid.

### Required changes

1. **Define a desktop grid** from the existing icon metrics (`ICON_W`,
   `ICON_H`, `ICON_GAP`, `DEFAULT_MARGIN`) and the usable area above the
   taskbar.
2. **On drag end, snap** the dropped icon to the nearest free cell (not
   free pixels).
3. **Reject overlap:** if the target cell is occupied, place on the nearest
   empty cell (Windows-style), never leave two icons at the same slot.
4. **Persist cell positions** (or snapped pixel origins) so restart keeps
   the grid layout.
5. **Migrate existing free positions** once: on first load after the change,
   snap saved coordinates onto the grid and resolve collisions.
6. **Update tests/docs** for drag, overlap attempt, reset, and Refresh/F5.

**Exit condition:** dragging an icon always lands on a grid cell; dropping
onto another icon never stacks them; reset still produces a clean column
on the grid.

### Proposed further alignments (same phase or follow-ups)

1. **Align to grid always (default)** — match Windows default; no Settings
   toggle required for v1 unless users ask for free placement later.
2. **Auto arrange** — desktop right-click (or Personalize) option that
   packs icons into the default column/flow and re-packs after reset.
3. **Live snap while dragging** — optional visual snap during motion, not
   only on release (nicer feedback; not required for exit).
4. **Icon size presets** — Small / Medium / Large that scale cell size and
   reflow without allowing overlap.
5. **Keep out of this phase unless needed** — multi-select marquee move,
   align-to-grid off mode, Recycle Bin special casing beyond current open.

### Implementation notes

| Area | Likely touch |
| --- | --- |
| Grid + collision | `packages/fosos-desktop/.../fosdesk/desktop.py` (`move_icon`, `place`, drag release) |
| Prefs / reset | `settings_pages.py` Personalize + `save_icon_positions` |
| Context menu | desktop right-click in `desktop.py` if Auto arrange ships |
| Verify | `docs/TESTING.md` Phase 12 / new Phase 5 checklist |

**Status:** planned (not implemented).

---

## Phase 6 — Files Explorer: Windows-like browsing

**Goal:** `fosos-files` behaves like File Explorer for everyday browsing:
search works while typing, context menus match what you clicked (item vs
empty folder background), and common Win habits work without surprises.
Phase 11 shipped clipboard/trash basics; this phase closes the remaining
parity gaps.

### How Windows handles this

| Windows control | Behavior |
| --- | --- |
| Search box | Filters / finds in the current location; focus stays in the box while typing; Esc clears |
| Ctrl+F / F3 | Focuses search |
| Right-click empty area in a folder | Folder background menu: View, Sort, New, Paste, Properties, Refresh — not an item menu |
| Right-click a selected folder/file | Item menu: Open, Cut/Copy, Rename, Delete, Properties, Open in Terminal, etc. |
| Right-click with multi-select | Acts on the selection |
| Address / breadcrumbs | Navigate; Ctrl+L edits the path |
| Back / Forward / Up | History and parent folder |
| Details / list / icons | Sortable columns in Details; remembered view per folder optional |

### Current FosOS gap

`fosdesk/files.py` has a Search entry that filters **names in the current
folder only** (`_entries`). On every `changed` it calls `refresh()`, which
rebuilds the whole listing and commonly **steals focus** from the search
field — search feels broken even when the filter logic exists.

Context menus are wired only on **items** (`_wire_item` →
`_on_item_press`). There is **no empty-listing / folder-background**
right-click menu. Right-click paths also call `refresh()` before the menu
(`_select_and_menu`), which can disrupt selection and menu targeting
(especially for a selected folder). New folder / Paste live mainly on the
item menu, not as a true “inside this folder” background menu.

Other Windows-alignment gaps likely to hit users next: Ctrl+F to focus
search, Esc to clear search, recursive “search in folder” depth, Details
column sort headers, New item types, and Refresh/Select none on empty
space click.

### Required changes

1. **Fix Search so it works while typing**
   - Keep keyboard focus in the search entry across filter updates.
   - Do not destroy/rebuild the search widget on refresh; prefer updating
     the listing only, or restore focus/cursor after refresh.
   - Esc clears the query and restores the full listing; Ctrl+F / F3
     focuses Search.
2. **Folder-background context menu**
   - Right-click empty space in the current folder (scrolled listing, not
     an item) shows a Windows-style background menu: Paste (when
     clipboard), New folder, Open Terminal here, Refresh, Properties of
     the current folder.
   - Distinct from the item menu when right-clicking a file or folder tile.
3. **Stable item context menu**
   - Right-click a selected folder/file must open the item menu for that
     selection without clearing selection or navigating away.
   - Avoid a full `refresh()` before popup when only selection/menu is
     needed.
4. **Docs / tests**
   - Extend [docs/TESTING.md](docs/TESTING.md) Phase 11 (or a Phase 6
     checklist): type in Search without losing focus; empty-area vs item
     right-click; Paste/New from background menu.

**Exit condition:** typing in Search filters the current folder without
losing the caret; right-click empty folder area and right-click a selected
item each show the correct Windows-like menu; Paste/New folder work from
the background menu.

### Proposed further alignments (same phase or follow-ups)

1. **Search depth** — optional “This folder” vs “All subfolders” (Windows
   search expands scope); start with reliable current-folder filter, then
   add recursive name search with a cancelable progress state.
2. **Clear (×) on the search entry** — clickable clear icon like Win11.
3. **Click empty space** — clears selection (Windows habit).
4. **Details view column headers** — click Name / Date / Size to sort;
   show sort direction.
5. **New ▸** submenu — Folder (have), empty text file, shortcut later if
   needed.
6. **Keyboard parity** — Ctrl+N new window/folder where it fits; Delete /
   Shift+Delete already partly there; ensure menu accelerators match.
7. **Status bar** — item count + selection size (partially present; show
   total size of selection when cheap).
8. **Out of scope for this phase** — full Windows Explorer ribbon, OneDrive,
   Home “Quick access” cloud, thumbnail preview pane, ZIP-as-folder depth
   beyond current open-with.

### Implementation notes

| Area | Likely touch |
| --- | --- |
| Search focus + filter | `packages/fosos-desktop/.../fosdesk/files.py` (`refresh`, `_entries`, search `changed`) |
| Empty-area menu | listing / `ScrolledWindow` button-press; new `_popup_background_menu` |
| Item menu | `_popup_menu`, `_select_and_menu`, `_on_item_press` |
| Shortcuts | `_on_key` (Ctrl+F, F3, Esc) |
| Verify | `docs/TESTING.md` Files checklist |

**Status:** planned (not implemented).

---

## Working rules

- Prefer Windows *behavior* over Windows *pixels*; keep FosOS palette,
  square corners, Dawn Aperture, Inter.
- One composition change per phase; ship behind Settings toggles when
  removing a control users may still want.
- Update `docs/TESTING.md` checklists in the same change set as the UI.
- Do not import or build `mockup/`.

