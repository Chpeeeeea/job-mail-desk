# JobMailDesk v2 Feature Audit

Status: reviewed architecture freeze  
Scope: v0.6.0 Core and the current local worktree  
Decision vocabulary: `KEEP` / `REBUILD` / `FEISHU` / `DELETE`

## Product boundary

JobMailDesk v2 is a local Candidate-side ATS engine. It reads recruitment
mail, resolves each message to an application, records immutable recruitment
events, derives the current application state and next action, then publishes
sanitized projections through connectors.

Core must not depend on Feishu, Obsidian, a desktop calendar, or an LLM.
Presentation and notification belong to workspace connectors. Recruitment
intelligence belongs to Core.

The North Star is:

> JobMailDesk should remove the need to maintain job-search records, not become
> another job-search tool that users must maintain.

## Decision rules

- `KEEP`: directly improves mail intake, recruitment understanding, identity,
  privacy, or reliability and already has reusable implementation.
- `REBUILD`: solves a Core problem, but the current representation conflates
  mail, event, application, state, or task.
- `FEISHU`: a presentation, task-management, notification, mobile, or
  analytics capability already provided better by Feishu.
- `DELETE`: has no place in v2 Core and should be removed after compatibility
  and migration gates pass.

No item marked `FEISHU` or `DELETE` is removed during the architecture phase.
The v0.6 desktop and Obsidian paths remain a compatibility surface until the
new projections pass shadow and dual-write validation.

## Feature audit

| Feature | Current implementation | User value | Competitive advantage | Decision | Migration notes |
|---|---|---:|---:|---|---|
| QQ/163/generic IMAP read-only intake | `mail_reader.py`, provider presets, `BODY.PEEK`, readonly mailbox | High | High for Chinese student mailboxes | KEEP | Move behind provider interfaces; preserve unread/UID invariants |
| Gmail/Outlook IMAP intake | Generic presets and credentials | High | Medium | KEEP | Keep provider-neutral Core; Feishu Outlook trigger is an alternative, not a dependency |
| Credential storage | OS keyring through `credentials.py` | High | Medium | KEEP | Add account IDs and multiple accounts without exposing secrets to connectors |
| Mail deduplication | Message fingerprint in `state.db` | High | Medium | KEEP + REBUILD | Dedup must guard immutable mail/event ingestion, not point directly to a mutable task |
| Recruitment classification | Keyword and rule classifier in `parser.py` | High | Medium | KEEP + REBUILD | Split classifier from structured extraction; measure precision separately |
| Company extraction | Subject/sender rules plus normalization dictionaries | High | High when domain-specific | REBUILD | Resolve to `Company`, preserve display name, aliases, parent and domains |
| Role extraction | Regex, normalization and role dictionary | High | High when combined with identity | REBUILD | Separate raw role evidence, canonical role and external job code |
| Recruitment project extraction | Cycle/program rules in parser and identity pipeline | High | High | REBUILD | Introduce `RecruitmentProject`; do not bury project inside role/application strings |
| Deadline extraction | Deterministic date/time parser | Critical | High | KEEP + REBUILD | Preserve parser assets; output evidence and temporal semantics; evaluate separately |
| Application resolution | Registry, resolver, batch context and legacy IDs | Critical | Very high | REBUILD (P0) | Make a standalone staged resolver with hard keys, company, project, role, time and optional semantic assistance |
| Application chain | `ApplicationRecord` plus mutable `JobTask` grouping | Critical | Very high | REBUILD (P0) | One application becomes a derived aggregate over immutable events |
| Recruitment events | `ParsedEvent` exists only as transient scan output | Critical | Very high | REBUILD (P0) | Persist append-only events; never overwrite history on reschedule or correction |
| Current stage/status | Stored directly on applications/tasks | Critical | Very high | REBUILD (P0) | Derive through a deterministic reducer; AI may propose events but cannot write stage directly |
| Reschedule/cancel/reminder/duplicate | `change_type` and task merge rules | Critical | Very high | REBUILD (P0) | Use distinct event types, supersession links and idempotent projectors |
| Next action | `action_summary` stored on each task | Critical | High | REBUILD | Derive Task projections from application state and actionable events |
| Evidence/confidence | Short requirements/evidence and one confidence number | High | High | REBUILD | Make evidence, provenance and confidence first-class per extracted field and resolution |
| Review queue | Markdown unresolved records, direct resolve/ignore | High | High | REBUILD | Unified review items and correction events; confirmed corrections must survive rescans |
| Manual correction | Direct task/application edits | High | High | REBUILD | Append correction events; projections update from reducer instead of mutating facts |
| Local privacy/redaction | In-memory body parsing and redaction helpers | Critical | High | KEEP + strengthen | Connector receives allowlisted structured fields and optional evidence snippets only |
| Markdown task fact layer | One Markdown file per mutable task | Medium | Low | REBUILD | Replace as authoritative source with a local event store; Markdown becomes a connector projection |
| Obsidian synchronization | `progress.py`, `exporter.py`, managed blocks | Medium | Low | REBUILD as Connector | Preserve export and optional corrections during dual-write; later read-only archive/export |
| Research queue | `research.py`, `ResearchRequest` on Core tasks | Optional | Not v2 Core | DELETE from Core | Move to a future optional research plugin after v2 state is stable |
| Desktop task cards and manual task editor | pywebview bridge and custom task UI | Medium | Low | FEISHU | Keep only compatibility until Feishu workspace is accepted |
| Week/month calendar | Custom UI projections | Medium | None | FEISHU | Use Base calendar/Feishu calendar |
| Company progress page and Kanban | `dashboard.py`, `progress.py`, UI assets | Medium | None | FEISHU | Applications and Events views replace it |
| Dashboard/statistics | Desktop payload and UI | Low | None | FEISHU | Base Dashboard/application mode owns presentation |
| Task manager, reminders and digest | task UI, notifier, scheduled digest | Medium | None | FEISHU | Core emits Tasks; Feishu handles reminders, overdue styling and digest workflows |
| Mobile and collaboration | Not native; previously delegated to Obsidian/mobile | High | None | FEISHU | Do not build a mobile client in v2 |
| Paper/note/image features | `image_store.py` and PaperTodo-inspired UI paths | Low for Candidate-side ATS | None | DELETE | Remove after data/export compatibility check |
| Theme, capsule and complex window behavior | `preferences.py`, `ui_app.py`, `ui/*` | Low | None | DELETE / minimal shell | Retain only setup, health, scan and review launcher if needed |
| Update notification and packaging | `updates.py`, PyInstaller/py2app | Medium | Low | KEEP minimal | Still needed for a local Core service; remove UI-specific packaging dependencies later |
| Doctor, logs and scheduler | environment checks, scan jobs and health | High | Medium | KEEP + REBUILD | Scheduler triggers one Core pipeline; connectors run after a successful local transaction |
| CLI | mixed Core, UI, Obsidian and research commands | High for maintenance | Medium | REBUILD | Split Core commands, connector commands, migration commands and diagnostics |
| Tests | good parser/identity/UI coverage but no event reducer suite | Critical | High as engineering asset | KEEP + expand | Add golden dataset, state/reducer/projector and connector contract tests |

## Source module disposition

| Current module | Primary decision | v2 destination / note |
|---|---|---|
| `launcher.py` | REBUILD | Minimal Core/service launcher instead of a task-workspace launcher |
| `packaging/macos/setup.py` | REBUILD | Package the local Core and minimal shell; remove display dependencies after cutover |
| `__init__.py` | KEEP | Package/version metadata only; no workspace dependency |
| `__main__.py` | REBUILD | Entry remains, but targets the separated Core CLI |
| `config.py` | REBUILD | Keep provider values but split Core, connector and presentation configuration |
| `credentials.py` | KEEP | Local credential adapter; expand to multiple account IDs |
| `mail_reader.py` | KEEP | `providers/imap` base and QQ/163/Gmail/Outlook adapters |
| `privacy.py` | KEEP | Strengthen local redaction with a connector allowlist policy |
| `normalization.py` | KEEP + REBUILD | Extraction normalization plus domain identity values |
| `parser.py` | REBUILD (assets KEEP) | Split classifier, company/role/project/deadline extractors and event detector |
| `identity_data/*` | KEEP | Versioned built-in domain dictionaries |
| `identity_dictionaries.py` | REBUILD | Keep schema/data assets while introducing explicit Company/Project/Role registries |
| `dictionary_compiler.py` | KEEP | User-extensible dictionary compiler outside runtime pipeline |
| `identity_resolver.py` | REBUILD (P0) | Staged application resolver with explicit scoring/evidence |
| `identity_pipeline.py` | REBUILD (P0) | Orchestrator only; remove application creation side effects |
| `identity_preview.py` | REBUILD | Privacy-safe Resolver/ReviewItem preview without side effects |
| `application_registry.py` | REBUILD (P0) | Application repository and projections over event facts |
| `models.py` | REBUILD (P0) | Separate Mail, Company, Project, Application, Event, Task, Review, Correction models |
| `task_service.py` | REBUILD (P0) | Event reducer plus Task Projector; eliminate task-as-event merging |
| `state.py` | REBUILD | Local transactional event store, ingestion state, projections and scan health |
| `scanner.py` | REBUILD | Thin pipeline: intake → classify → extract → resolve → append event → reduce → project → connectors |
| `unresolved_store.py` | REBUILD | Review Queue repository and correction event writer |
| `markdown_store.py` | REBUILD as compatibility/connector | Markdown is no longer the Core fact source |
| `progress.py` | REBUILD as Obsidian Connector | Dual-write compatibility, then archive/export only |
| `exporter.py` | REBUILD as Obsidian Connector | Connector projection and controlled correction import |
| `agent_bridge.py` | REBUILD | Workspace/query bridge over domain services, not task Markdown |
| `research.py` | DELETE from Core | Future optional plugin |
| `dashboard.py` | FEISHU | Remove after Feishu projection acceptance |
| `digest.py` | FEISHU | Replace with Base/Task workflow |
| `notifier.py` | FEISHU | Replace with Feishu reminder/notification |
| `scheduler.py` | KEEP + REBUILD | Keep local scans; remove display/digest responsibilities |
| `doctor.py` | KEEP + expand | Add connector health and privacy diagnostics |
| `logging_setup.py` | KEEP | Structured local logs with redaction |
| `updates.py` | KEEP minimal | Local Core update notice only |
| `preferences.py` | DELETE / minimal shell | Remove presentation preferences; retain operational settings elsewhere |
| `image_store.py` | DELETE | Out of Candidate-side ATS scope |
| `ui_app.py` | REBUILD | Remove workspace behavior; retain setup, health, scan and review handoff |
| `ui/index.html` | REBUILD | Minimal setup/health/review shell only |
| `ui/app.js` | REBUILD | Remove task manager, calendar, dashboard and capsule behavior |
| `ui/style.css` | REBUILD | Remove workspace styles and keep a minimal operational shell |
| `cli.py` | REBUILD | Domain, connector, migration and diagnostic command groups |
| packaging and launchers | KEEP + simplify | Ship local Core service and first-run setup, not a second task application |

## Test module disposition

| Current test module | Primary decision | Migration note |
|---|---|---|
| `test_agent_bridge.py` | REBUILD | Domain query, Correction and outbox contract |
| `test_application_registry.py` | REBUILD | Application repository/projection and legacy migration |
| `test_config.py` | REBUILD | Provider/Core defaults separated from connectors |
| `test_dashboard.py` | FEISHU | Retire desktop assertions after projection contract coverage |
| `test_dictionary_compiler.py` | KEEP | Reuse offline compiler behavior |
| `test_exporter.py` | REBUILD | Obsidian Connector idempotency and compatibility |
| `test_identity_dictionaries.py` | REBUILD | New domain registry schema and override order |
| `test_identity_pipeline.py` | REBUILD | Preserve current cases as Resolver/golden regression assets |
| `test_identity_preview.py` | REBUILD | ReviewItem allowlist and side-effect-free preview |
| `test_identity_resolver.py` | REBUILD | Evidence-rich staged resolver decisions |
| `test_imap_readonly.py` | KEEP | Provider contract baseline |
| `test_manual_tasks.py` | REBUILD | Correction Events; ordinary personal tasks leave Core |
| `test_parser.py` | REBUILD | Keep all cases and split classifier/extractor/deadline/event assertions |
| `test_privacy_and_storage.py` | REBUILD | New local content store and connector allowlist |
| `test_progress.py` | REBUILD | Legacy migration plus Obsidian Connector |
| `test_scanner_policy.py` | REBUILD | Local transaction, isolation, replay and outbox |
| `test_state.py` | REBUILD | Mail/Event/attempt/projection/outbox persistence |
| `test_ui_helpers.py` | REBUILD | Minimal shell only |
| `test_updates.py` | KEEP | Existing safe update-notice behavior |

## Findings that require architectural change

### 1. The current fact source is the wrong abstraction

`JobTask` contains application identity, event type, current stage, deadline,
completion state, research state and source evidence. A later mail is merged
into that mutable record. This loses the distinction between what happened and
what the user currently needs to do.

v2 must use an append-only local Event store as the fact source. Applications,
Tasks, Markdown and Feishu records are projections.

### 2. Reschedule currently overwrites history

The current merge path assigns new start/end/deadline values to an existing
task. Even when the resulting user view is correct, the original schedule and
the reason for change are not first-class facts.

v2 appends a `*_RESCHEDULED` Event with previous and new schedule values and a
link to the superseded Event. The reducer computes the current deadline.

### 3. Manual correction is mutable, not auditable

Current editing changes task fields in place. v2 writes a Correction Event
containing the proposed output, corrected output, evidence and timestamp. A
subsequent mail replay cannot silently reverse a confirmed correction.

### 4. Processed mail points to a task

`processed_messages` currently stores a task reference. In v2 it must point to
an immutable Mail ingestion record and the Event(s) produced from it. Replaying
a parser version creates a new processing attempt or corrected Event, not a
duplicate Task.

### 5. Application identity is split across four layers

Application identity currently lives across parser strings, task grouping,
the registry and Obsidian progress import. v2 gives Company, Project and
Application explicit repositories and makes the resolver the only service
allowed to select or create an Application candidate.

### 6. Core orchestration is coupled to all outputs

The current scanner imports Obsidian state, parses mail, reconciles identity,
updates Markdown tasks, updates research, expires tasks and exports multiple
views in one function. One connector failure can affect the scan transaction.

v2 commits local Mail/Event/Application projections first. Connectors consume
an outbox afterward and may retry independently.

### 7. Parser replay currently destroys ingestion history

Changing the parser version clears `processed_messages`. This cannot distinguish
a Mail, a processing attempt and a corrected interpretation. v2 stores
versioned processing attempts and superseding Events.

### 8. Terminal state has multiple writers

Rejection, cancellation, expiration, ignored state, ledger completion and
checkbox completion are interpreted in parser, task service, scanner, progress
and exporters. v2 gives terminal semantics exclusively to the reducer, while
task completion remains a separate projection fact.

### 9. Current identity fixes are valuable migration inputs

The local worktree contains uncommitted improvements for job-code extraction,
distinct same-company applications and unresolved reconciliation. They must be
preserved as anonymized Resolver regression cases before structural code is
moved. The v2 work must not overwrite or silently discard them.

### 10. Compatibility Markdown has several different authorities

Task files, Application files, unresolved files, the progress ledger and the
Obsidian managed block all use Markdown but do not have equal authority. The
migration must identify facts, corrections and projections explicitly rather
than importing every Markdown field as an authoritative Event.

## Freeze boundary

Effective immediately for the v2 branch:

- no new desktop calendar, Kanban, dashboard, note, capsule or task-manager
  features;
- no new Research behavior in Core;
- no Feishu-specific types inside Core domain models;
- no deletion of the v0.6 compatibility surface before shadow validation;
- bug fixes for mail loss, wrong application linking, wrong deadline, wrong
  terminal state and false tasks remain allowed;
- current uncommitted identity/scanner fixes must be preserved and evaluated as
  resolver inputs, not overwritten by the refactor.

## Implementation order after this audit

1. Freeze product boundaries and approve this audit.
2. Define Domain Model v1 and the first 15–25 Event types.
3. Specify the State Reducer and Task Projector as pure deterministic services.
4. Add a local event store and outbox behind a disabled v2 feature flag.
5. Run the old and new projections in shadow mode on anonymized fixtures.
6. Refactor Application Resolver to emit scored decisions and review items.
7. Add Evidence, Confidence and Correction records.
8. Build a sanitized golden dataset and metrics, emphasizing Application
   Linking Accuracy and False Task Creation Rate.
9. Define connector contracts, then implement Obsidian compatibility and
   Feishu output independently.
10. Enable dual-write, replay real mail locally, fix P0 errors, and only then
    deprecate the old display layer.

## Completion criteria for the audit phase

- every current source module has one primary disposition;
- no v2 Core model mentions Feishu, Base, Obsidian, Markdown or desktop UI;
- event history is authoritative; stage and Tasks are deterministic projections;
- Connector failure cannot roll back or block successful local mail ingestion;
- user corrections are persistent, auditable and protected from replay;
- no current display or export module is deleted before compatibility evidence
  exists.

## Verification evidence

- The version-controlled source/UI inventory was compared against the source
  and test disposition tables.
- `uv run pytest --collect-only -q -p no:cacheprovider` collected 153 tests
  without scanning mail, exporting data, calling connectors or modifying the
  local task store.
- `git status --short` and `git diff --stat` confirm that the existing local
  identity/scanner/unresolved changes remain present and unmodified by this
  documentation phase.
