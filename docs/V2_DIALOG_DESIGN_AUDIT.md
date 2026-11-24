# V2 dialog design coverage

Development checkpoint: `2.0.0.dev4`. This review closes the missed visual
integration of the original SD wizard. The dev2 audit remains historical
functional/transaction evidence; its approval did not certify all screens.

## Contract and ownership

- V2 tokens define color, typography, spacing, controls and icon size. Commands
  use the shared Tabler outline family. Bitmap covers and brand logos retain
  their purposes. Command icons stay outline; decorative setup artwork follows
  the accepted [setup direction](design/SETUP_DESIGN_DIRECTION.md). The old
  blanket replacement of diagnostic illustrations is superseded for setup.
- One clear primary next action; a compact state/reason; secondary navigation
  and expandable technical information. Neutral/not-applicable information
  must not be presented as a successful SD check.
- Original services, counts, permissions, backup decisions, cancellation signals,
  recovery options and defaults are retained. Native file pickers remain OS UI.
- Setup is a dedicated view over original services. Other retained dialogs have
  an explicit presentation registry, not a blanket claim that inherited UI is
  approved. The adapter translates roles without reconnecting action signals.

## Screen inventory

| Screen / state | Treatment and verification |
| --- | --- |
| No destination chosen | Compact V2 setup, empty route, Select SD as primary; no startup alarm about the executable directory. |
| Empty compatible destination | Install OpenMenu as primary; confirmation remains required; outcome remains visible until Continue. |
| Ready / read-only / blocked destination | Original diagnostic remains authoritative; use/install hidden when unavailable; choose another destination is primary for a blocked path. |
| Collection configuration details | A visible info+label action beside the guidance banner opens an actual read-only dialog, including for valid configuration. Current configuration is re-read without changing other storage findings; bulk mode exits. Scroll and a translated Close footer use shared V2 atoms. |
| Configuration inspection | Optional missing file is neutral, independent from game integrity and write permission; nonconfirmed/invalid content directs users to technical details. Settings, line numbers and documented bounds are localized and escaped. Long inputs have a bounded view with omitted counts. |
| Edited destination | Prior approval invalidated; current path diagnosed again before installation/acceptance. |
| Diagnostic details | Expandable scroll area with all diagnostic categories and original path/classification/menu/permission values; local filesystem N/A is plain neutral text. |
| Backup in setup | Dedicated BackupPromptV2 over original worker/service/registry; parent route and close blocked until child exits. Recommendation only for actual content/access. |
| Backup prompt / required | Illustrated native header, adjacent destination chooser, inspectable source/target strips, optional reminder checkbox. All three choices remain in compact footer; required backup omits Skip. |
| Skip / remembered preference confirmation | Compact Confirmation with safe Back default; skip once does not persist; checking reminder persists only after explicit confirmation. |
| Backup preparing / copying | Actual original worker; file-count progress and measured elapsed time; no byte ETA or fake cancel. Cancel/window close cannot abandon worker cleanup. |
| Backup failure / retry | Inline persistent error and scrollable technical details; destination chooser and retry remain accessible. Partial copies never display success. |
| Backup success | Persistent result with location, Open folder and explicit Continue; completed copy manifest/registry retain original semantics. |
| Old-menu upgrade | Shared hierarchy/roles/icons; backup-first, update and cancel preserved. |
| Manual and batch save review | All five counts retained: covers, additions, deletion, slot moves and ID corrections; transactional explanation and destination preserved. Shared hierarchy/file icons replace missing-icon warnings. |
| Provider settings | All seven columns retained and scrollable; buttons and priority controls fit cells; current statuses, signup, testing and credentials remain available. |
| Nested provider credentials | Field names localized in English/Spanish; original field identities, ranges, password modes and acceptance values preserved. |
| First-run language | V2 theme/adapter installed before main window construction; brand allowed, Use/Cancel roles and icons. |
| About | Brand, actual shared version and repository/contact/data directory preserved; shared title and Close action. |
| Bulk progress | Consistent cancel icon and label; original cancellation signal/reject behavior preserved. |
| Other busy progress | Token-based panel, spinner colors and content-height calculation instead of fixed clipping height. |
| Recovery / repair / generic confirmation | Standard and authored QMessageBox roles/defaults/conditional branches preserved; icons and translated standard buttons. |
| Template URL / music volume | QInputDialog buttons receive V2 icons and translated labels; OS controls and values preserved. |
| Exports / template ZIP / image and game pickers | OS-owned file dialogs; parent busy/result/error UI uses V2 treatment. |
| Game / image information | Replaced V2 card (`ui/v2/game_info.py`) opened by the info action in the collection and the cover window: header with cover, name and chips, consistency warnings, titled sections with small labels and interpreted values, and a footer with Remove/Undo removal, Undo name (only when renamed), Open folder (only when the game has an SD folder) and Close. Review status, saved-cover history and source opening are retained. Height fits the content without scrolling at normal sizes in Spanish and English; the scroll area remains only as a fallback and uses the surface background in both themes. Workflow tests cover saved, new pending and renamed SLOT games and the image card at scales 1 and 2.5. Visual approval is pending. |
| Collection / cover details / import | Existing dedicated V2 views retained and still exercised by workflow tests. CandidateDialog, CoverPreviewDialog, AddGameDialog and original SetupWizardDialog/BackupPromptDialog are explicitly replaced in V2; legacy UI remains available. |

## Evidence and approval boundaries

`scripts/validate_v2.py` executes dialog coverage alongside production flows at
offscreen scales 1, 1.25, 1.5 and native Windows system DPI. It regenerates
`docs/V2_VALIDATION.md` and saves snapshots in
`build/v2-validation/visual-<backend>-<scale>/`. Coverage includes setup states,
disclosure, install cancel/failure/success, stale paths, all retained classes,
button reachability, provider-cell scrolling, standard labels and original-UI
fallback. A new exported original dialog fails the explicit disposition test.

An independent reviewer, without conversation history, inspected reachable
paths and rendered setup, backup, upgrade, review, providers/credentials,
language, About, progress, messages, template input and busy overlay through
native Windows at DPR 2.5 in English/Spanish. It found active-backup closure,
untranslated Qt buttons, clipped provider priority and missing metric icons.
These received corrections. Its actual backup-worker runs used generated files,
including failure and retry; they did not write to a physical SD.

The same reviewer caught a destination handoff defect: changing the path before
asking to discard pending changes could leave old games approved for the new
destination. Setup now checks abandonment before opening, clears destination-owned
views and revokes old permissions when switching. Diagnostic-driven setup/backup/
recovery dialogs wait for the diagnostic thread to finish. Regression tests cover
declined abandonment, active jobs, accepted switching and deferred handoff.

Visual/behavior approval is scoped to the reviewed local development screens.
It does not certify every external template, pathological screen/window size,
OS-owned file picker appearance, provider network availability or hardware.
Clean Windows, physical SD and Dreamcast gates remain in OPENMENU_V2.md.
Final independent status is recorded in V2_INDEPENDENT_AUDIT.md after closure.


## Configuration follow-up

Read-only GDEMU.ini diagnosis is also exposed in the collection without replacing
cover guidance or introducing a configuration editor. A missing or valid file is
summarized in the destination card; the full note takes its own line only for
invalid, unreadable or unconfirmed content. A visible action beside the guidance
banner opens a dedicated read-only dialog, even for a file with valid supported settings. Changing destination through
the folder picker or setup invalidates the prior diagnosis, games, drafts and
write permission before scanning. Cancelling the picker preserves that context.
Self-tests supply an explicit local destination, so startup evidence cannot
silently discover physical cards. The full-suite source digest now includes every
regression test, including configuration and optional provider tests.

Independent review caught stale destination context and excessive RichText rows
from a bounded but repetitive file. Both gained reproductions and corrections;
final reviewer disposition is recorded in V2_INDEPENDENT_AUDIT.md.


## CDI import follow-up

CDI import still uses the existing V2 file/folder picker and selection table.
Supported structural checks now show a localized checked status and scope
in the status tooltip. Confirmed failures and unsupported layouts remain
unselectable with distinct localized explanations. Native captures and
regressions exercise checked/invalid/unsupported in EN/ES through InspectWorker;
no preview, pagination or action layout is replaced. The CLI/MCP architecture
is separate from these desktop screens.

## Setup art direction — 10 October 2026

The [illustrated preparation/backup contract](design/SETUP_DESIGN_DIRECTION.md)
supersedes the compact setup direction. Shared native components, state badges,
artwork and outline command icons have distinct roles. Tests in
test_v2_preparation.py exercise actual generated-file copy, error and retry,
compact sizes, EN/ES, both themes and persistent results. The source-bound visual
gate in SETUP_DESIGN_VALIDATION.md records the new independent review; historical
approval and functional PASS do not approve this direction automatically.


Illustrated dev7 scope adds source-bound evidence for all 18 preparation/backup
states. The independent review requested reproductions for read-only registry,
incompatible installation, folder switching after installation, contextual notices,
failed preference persistence, keyboard checkbox visibility and action accessibility.
Those regressions now have generated-file/native Qt tests. Slow install/check calls
keep Qt events active through a protected service thread. New approval is recorded
in SETUP_DESIGN_VALIDATION.md separately from previous compact-screen acceptance.

Legacy menu handoff: the setup action now says Review update for migratable old/unknown menus, matching the original backup/update review. It does not promise collection inspection before an upgrade. Generic read-only presentation is tested with simulated permissions; it is not reported as a new end-to-end legacy inspection flow. Cancelling review preserves source files.

Compact confirmation text has its own regression: its wrapped label must reserve heightForWidth at the actual width, and the final preference paragraph must be visible after keyboard scrolling. Button reachability alone did not establish that text was readable. The skip message distinguishes Save and old-menu Update, instead of promising an exclusively read-only next step.
