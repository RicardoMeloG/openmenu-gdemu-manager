# OpenMenu GDEMU Manager v2

Version `2.0.0.dev7`; illustrated preparation work is on
`feature/setup-design-direction`, based on `develop`.
This is a real PySide6 application over the original services. It is not the
HTML mockup or a simulation, and is not yet a hardware-validated public release.

## Purpose and design

The collection answers which games are present and which need a cover. It uses
compact rows, small uncropped thumbnails, disc ID, region and pending states.
It has no page title: the title bar names the app and the destination card heads
the window, so the game list keeps that height. The card adds a short GDEMU.ini
status; the full configuration note gets its own line only when the file needs
attention, and its details action sits beside the guidance banner. A
«Solo sin carátula (n)» checkbox filters games without a cover, and the save
button counts pending changes and breathes an orange halo while they exist.
The cover workspace helps fans find a design, inspect its scan and choose it.
It starts with six alternatives per page, across every available region. While a
web search runs and no alternative is shown yet, the gallery shows the app's
spinning disc and «Buscando imágenes en la web» instead of an empty result; the
disc stops when results arrive, the search fails or the window closes, and a new
search keeps the alternatives already shown. Click
an image to enlarge it; compare two distinct images side by side or by alternation,
with zoom and synchronized pan. `100 %` draws one image pixel per physical
screen pixel whatever the Windows display scaling, and the fitted view states
its real percentage, so the two are not confused on scaled displays. The
OpenMenu preview uses the project's actual
Pillow normalizer. The original scan is not color-corrected or cropped.

Shared tokens, action semantics, Tabler SVG icons and Qt atoms live in
`ui/v2/design.py` and `resources/v2/`. Command icons remain consistent; artwork has a separate decorative role.
The accepted [setup art direction](design/SETUP_DESIGN_DIRECTION.md) adds an
illustrated state card and grouped destination/backup layout. Its native Qt adaptation
and matching backup flow are implemented; independent evidence is tracked in
[setup design validation](SETUP_DESIGN_VALIDATION.md). Human acceptance remains separate.
There is no Tailwind/browser dependency. The original template registry still
supports palettes, backgrounds and music. V2 gives the default formal template
the approved warm orange palette; explicitly selected external/arcade palettes
are translated to the same semantic tokens. Templates cannot change action semantics.

SD preparation now uses `ui/v2/setup.py`: compact destination selection, a clear
status and next action, technical diagnostics on demand, and an explicit
installation success state before entering the collection. Invalid edits revoke
the old destination approval. An unrelated working directory is not presented
as the user's SD at first run. Original diagnosis, installation and backup
services remain authoritative. `ui/v2/backup.py` now presents selection, explicit
skip scope, real file-count progress, persistent success and error/retry over the
original copy worker. The footer remains outside scrolling content and decoration
hides first in compact windows. `retained_dialogs.py` registers upgrade,
review, providers/credentials, language, About and bulk progress presentation;
standard messages and template inputs share command icons and translated labels.
Native file pickers remain OS-owned. See [screen coverage and visual review](V2_DIALOG_DESIGN_AUDIT.md).

## Original functionality retained

| Function | V2 integration |
| --- | --- |
| SD / backup folder diagnosis, FAT32 and write permission | Original diagnostic worker and safeguards; destination summary and reason visible. |
| Empty SD setup, menu installation and old-menu upgrade | Illustrated native V2 setup and adapted original upgrade, preserving backup decisions and OpenMenu assets. |
| Read games, names, IDs, regions and menu inconsistencies | Original scanner/models; compact table and a game information card (cover, name, position/region/pending chips, consistency warnings, then «En OpenMenu», «Del disco» and «Archivos» sections). Values are interpreted for reading only: region names, VGA yes/no, a readable date or «Sin fecha» for 00000000, disc «n de m»; a SLOT reference is never shown as the disc ID. GameItem fields are not rewritten. |
| GDI/CDI file or recursive folder import | Real source inspection in a worker; explicit selection, Todos, a text filter (name, game folder or format) that only hides rows and never changes the selection; while it is active, Todos becomes «Todos los visibles (n)» and acts only on the shown games, hidden selections are kept and the counter states the total; the selection's size, the destination's free space and free positions are shown, and Preparar stays enabled: when the selection does not fit it shows a warning with the checked games' size, a margin for covers and the menu, the total needed and the destination's free space (the save repeats the space check before touching the SD), picked files start checked and a picked folder's games start unchecked (a folder is a catalogue to choose from), duplicates initially unchecked, «Todos los visibles» and the capacity warning say how many checked games the filter hides, game folders run from 02 to 999 (the former 127 cap had no documented GDEMU/openMenu reason; more than 126 games on real hardware is still pending verification), invalid GDI/CDI blocked with reason; unsupported CDI profiles distinguished. |
| Add, remove, compact slots, write names and rebuild 01 | Original workers/slot transactions/rebuilder; changes remain pending until confirmed. The «Aplicar cambios en SD» confirmation shows every count (zeros dimmed) and the menu rebuild; a new game's cover is counted with the games to copy, not again as a cover change. Cancel is the default. |
| Search providers, matching thresholds and caching | Original search services/settings; remote image preparation stays outside the UI thread. |
| Automatic bulk proposals and batch approval | Original bulk workers/quality rules; proposals do not automatically become a manual Save. The collection previews each pending proposal inside a dashed accent frame, never as a saved cover, and its status says it awaits review, new games included. Explicit batch Save retains the original review/confirmation. |
| Current cover, quality, dimensions, source and previous covers | Game/image information cards (the image card uses the same header and «Imagen»/«Origen de la imagen» sections) and persistent original cover library. Full metadata remains on GameItem. |
| Import local covers and web search templates | Original file picker/providers and configured web templates, disc-ID search, source opening, originals folder. |
| Backup, transaction recovery and internal trash | Original copy/recovery/trash services; native V2 backup presentation, retained recovery dialogs. A slot transaction stays incomplete (`slots_published`) until menu 01 is rebuilt for its folders; if the rebuild fails, recovery offers to revert to the layout the current menu describes, and offers completion only when 01 already lists the new layout. A slot pending deletion is not reused by an addition in the same save. |
| Spanish/English, language packages | Original language registry; V2 strings/actions use its catalogs. |
| Install templates, backgrounds and music | Original template registry/menu/audio controller. |
| JSON/TSV export, logs and updates | Original menus/services. The displayed version comes from the current code. |

## State and interaction contract

1. Selecting a destination diagnoses it before any write. Migratable old or
   unknown menus open the original backup/update review before collection access;
   the setup action names that review. The generic read-only presentation does
   not promise a new inspection path for those menus.
2. Source import is separate from SD contents. Preparing games adds pending
   rows; it does not copy files. Invalid sources show a reason. Supported CDI
   descriptors and declared track bounds are checked; unknown layouts require
   review. No structural check guarantees payload integrity or game boot.
3. Entering bulk mode checks only games without covers. Todos affects the entire
   collection, independent of filters. Clicking a row or its checkbox toggles
   once. Search selected keeps the mode; individual search/info/remove, import,
   scan, destination, save and other menu actions leave it first.
4. The search text is temporary. Only Guardar nombre adopts it for OpenMenu.
   IDs, internal name, disc, VGA, version/date and aliases remain unchanged.
5. Choosing a cover creates a draft. Searching, inspecting, comparing and opening
   the web do not choose it or write to the SD. Keeping the current image does
   not prepare a replacement. Exact image duplicates are merged; different
   scans/tones remain alternatives under the original deduplication rules.
   The cover window footer offers Listo/Done, which closes the window like
   Mi colección and keeps the draft; it never saves. The main window's
   Guardar cambios/Save changes saves every pending change together.
6. Save changes validates the intentional choices and confirms the storage
   plan before materializing them through the original cover service and
   starting the transactional worker. Cancelling leaves drafts and local cover
   state untouched; Discard/Keep can remove the choice without a hidden save.
   Successful save rescans
   after its thread finishes. Unchosen bulk proposals are excluded from manual Save.
7. Closing/changing destination/rescanning asks before abandoning pending work.
   Discard restores local edited state and clears session changes; archived
   original-cover history is preserved. An active storage job prevents closing.
   Search completion after closing its dialog is ignored; its thread stays alive
   until cleanup so Qt cannot destroy a running worker.

## Source integrity added in v2

The v1 baseline has byte-total copy verification. V2 additionally validates GDI
track count/order, quoted filenames, path containment, offsets, missing/empty
tracks, incomplete sectors and provable ISO9660 volume truncation before an
addition can mutate the SD. It validates the staged destination again before
publishing a slot. A failed copy remains recoverable through original transaction
metadata. Existing GDEMU.ini is preserved. The runtime diagnosis separately reports its
optional absence, unreadable content, unsupported sections/keys, duplicate known
keys and invalid documented values. Root settings and line numbers appear in
expandable technical details with allowed ranges. No timings or other values
are inferred, repaired or written, and configuration findings do not certify
image integrity or change storage permissions. The view bounds the number of
rendered rows and reports omitted counts; the original file remains complete.
Recovery revalidates source and staging, records ownership of published additions
and retains it after late failures. Pending transactions block new writes from
both the worker and service until completed/reverted. Reversal evacuates owned
published moves before restoring originals, including slot reorder cycles.

These checks are structural. Supported CDI footer/track layouts now receive
bounded descriptor and extent validation before import, before any addition
mutates storage, after staging and during recovery. Unsupported layouts are
reported for review separately from confirmed structural failures. Deeper disc
checksum/filesystem-extents audits remain separate work; a structurally checked
CDI is not certified intact or bootable. See [CDI contract](CDI_VALIDATION.md). A GDI with
no supported filesystem size evidence can still be truncated on a whole sector
boundary without this validator proving it. Bootability requires hardware evidence.
See [launch protocol](VALIDATION_GAME_LAUNCH.md).

## Run, validate and package

```powershell
python -m pip install -e ".[dev,build]"
python -m openmenu_gdemu_manager
python -m openmenu_gdemu_manager --legacy-ui
python scripts/validate_v2.py
python scripts/validate_v2.py --check-docs
./scripts/build_portable.ps1 -Version "2.0.0-dev6"
./dist/OpenMenuGDEMUManager-Portable/OpenMenuGDEMUManager.exe --self-test report.json
```

The harness regenerates [validation evidence](V2_VALIDATION.md). Re-run it after
V2 code/resource/test changes; `--check-docs` rejects stale source evidence.
On Windows it also tests UI flows with the native Qt backend at the system DPI,
because offscreen measurements alone can miss native layout changes.
See the [independent audit and corrections](V2_INDEPENDENT_AUDIT.md).
The self-test verifies native startup and packaged icons without SD/network work.
Generated artifacts, caches, ROMs, real library inventories and mockup sample
covers must not be committed. No new third-party dependency was introduced.

Use a reviewed topic branch from develop for corrections, then integrate its PR
into develop. Main receives only a validated release. Every commit uses Conventional Commits and
the repository's existing commit-msg/pre-push hooks.

## Remaining release checks

- Portable launch in a clean Windows VM, beyond this development PC; use
  [the acceptance protocol](V2_EXTERNAL_ACCEPTANCE.md).
- Private/credentialed provider checks as configured by the user. Public OpenMenu,
  Libretro and Cover API search/download/decoding passed the opt-in tests; see
  [provider evidence](V2_PROVIDER_VALIDATION.md). Offline suites still skip network calls.
- Real-world CDI variants outside the supported structural profiles, deeper
  checksums/filesystem extents and unusual GDI layouts.
- A disposable backed-up SD and Dreamcast/GDEMU test: setup, add GDI/CDI, rename,
  change covers, remove/compact, then actually launch each game.

The original v1 remains available through `--legacy-ui`. Its existing checkout
and portable installation are not replaced by creating this branch/build.

## Agent access

A read-only headless CLI now shares validation/diagnostic services with the
application. `python -m openmenu_gdemu_manager.cli --language es validate-image
"path/to/disc.cdi"` returns schema-versioned JSON and a categorized exit code.
`diagnose-storage "path/to/destination"` requires an explicit path and performs no
automatic drive discovery. It does not authorize or execute writes.
[MCP evaluation](MCP_EVALUACION.md) recommends an optional local stdio adapter
using the official SDK. No MCP server or remote API is activated in this phase.
The source installation provides the CLI entry point; the GUI portable does not
include a separate console executable.

## Error diagnostics (dev6)

The native application initializes diagnostics before runtime migration and Qt/UI
imports. Startup/DLL failures, uncaught Python and worker-thread exceptions and Qt
warnings/errors can therefore be retained when the logger itself can initialize.
V2 game inspection, local cover imports, image preparation and retries log their
originating errors without changing the existing user-facing workflows. Saves use
the same operation ID in the application log and transaction recovery journal.

The application log records UTC time, module, level, session/operation IDs and
thread, plus app/Python/platform and loaded Qt versions at startup. Each session
uses a separate
`openmenu_gdemu_manager.<session-id>.log` file, rotating at a 2 MiB threshold
with four backups. Five recent sessions are retained, plus any older still-active
sessions protected by OS file leases; transaction/search/recovery files on
storage are not rotated or changed by this policy. The normal log is under the
runtime data folder (portable: `data/openmenu_gdemu_manager.<session-id>.log`). If
it is not writable, a temporary `OpenMenu GDEMU Manager` folder is tried and the existing
Open log action opens the active path. Failure of both locations or a native
crash before Python starts remains outside this guarantee.

Known URL password/token/API-key fields, URL userinfo and bearer/basic headers
are masked in formatted diagnostics. This is not complete anonymization: paths,
game names, hosts and other user data can remain. Review logs before sharing;
do not commit them to this public repository. Independent application processes
rotate separate files; history cleanup skips
active sessions. These are application diagnostics, not a cross-process collector.

The headless CLI returns a `request_id` in its existing schema-versioned JSON and
retains error tracebacks on stderr with the matching ID. It creates no diagnostic
file, imports no Qt and does not migrate runtime data or mutate the inspected
source/destination. Normal invalid/unsupported image findings remain categorized
JSON results; unexpected/access failures also retain a technical diagnostic.
This prepares diagnostics for agent use; no MCP server is activated.

Regression coverage is in `tests/test_logging_diagnostics.py`; generated full/DPI
evidence remains in [V2 validation](V2_VALIDATION.md). The old dev5 portable does
not include these changes. The dev6 local packaging/startup checks passed; see
[V2 portable evidence](V2_PORTABLE_VALIDATION.md). Existing clean-Windows/hardware
gates still apply.


## Illustrated preparation and backup (dev7)

Native Qt shared Header/PathStrip/StatusCard/Confirmation/footer components replace
only setup and backup presentation. Artwork is a custom decorative SVG; commands
remain Tabler outline. Compact layouts hide decoration first; fixed footers and
focus-aware scrolling keep buttons, path fields and reminder checkboxes reachable.
Diagnostic and install services run outside the GUI thread with protected busy
states. Enter inside the destination field only checks it. Editing/picking a new
destination clears its old installation approval and contextual notices.

A copy must complete before success appears. Completed backups retain the original
manifest/copy service. PC metadata and optional source registry failures are shown
separately from copy failure; read-only/blocked sources are not mutated to register
a backup. V2 also recognizes a PC backup decision with a matching complete manifest
and existing recorded files/sizes, preserving the old-menu upgrade handoff without
requiring that registry write. This is copy evidence, not a payload/hash/hardware
certification. Remembered omissions are persisted only after confirmation; a failed
settings write preserves the previous decision and keeps the reminder available.

Installation success requires compatible OpenMenu and permitted scan/write in the
final diagnostic. An incompatible copied template remains inspectable with its
actual diagnostic; it is never reported as ready to add games. No automatic repair,
formatting or deletion is added. Human acceptance and hardware gates remain open.

Legacy menu handoff: the setup action now says Review update for migratable old/unknown menus, matching the original backup/update review. It does not promise collection inspection before an upgrade. Generic read-only presentation is tested with simulated permissions; it is not reported as a new end-to-end legacy inspection flow. Cancelling review preserves source files.
