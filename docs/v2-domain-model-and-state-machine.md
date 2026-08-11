# JobMailDesk v2 – Domain Model & Application State Machine

Status: draft v1  
Depends on: `docs/v2-feature-audit.md`

## 1. Scope and invariants

JobMailDesk v2 Core converts recruitment mail into an auditable application
lifecycle. It is connector-neutral and does not depend on Feishu, Obsidian,
Markdown, a desktop UI, or an LLM.

The first implementation must preserve these invariants:

1. Mail ingestion is read-only and idempotent.
2. An Event is an immutable fact. A later Event may supersede it but never
   overwrite it.
3. Application state is derived by a deterministic reducer.
4. A Task is a projection of current actionable state, not a copy of a mail.
5. A reminder does not advance stage or create a second Task.
6. A reschedule retains both the previous and current schedule.
7. A terminal application cannot be reactivated by a generic or older mail.
8. A confirmed user correction cannot be reversed by replaying the same mail.
9. Connector failure cannot roll back local ingestion or domain state.
10. Full mail content remains local unless the user selects an explicit export
    policy. Connector payloads are allowlisted.

## 2. Core flow

```text
Mail Intake
  → deterministic normalization and deduplication
  → recruitment classification
  → structured extraction
  → Company / Project / Application resolution
  → Event detection
  → append Event + Evidence + Resolution Decision
  → State Reducer
  → Task Projector
  → local transaction commit
  → connector outbox
```

LLM assistance, when enabled in a later version, may propose extraction or
resolution candidates. It cannot directly mutate Application state or Tasks.

## 3. Domain entities

### 3.1 Mail

`Mail` represents one provider message and exists only in the local Core.

Required fields:

```text
mail_id                 internal stable ID
account_id              local mailbox account
source_provider         qq / netease / gmail / outlook / generic_imap
provider_uid            provider-local UID
message_id              raw provider Message-ID, local only
thread_id               optional provider thread reference
sender                  local only
recipients              local only
subject                 local only
received_at
content_hash            internal deduplication key
body_local_ref          encrypted/local content reference
attachment_refs         local references only
processing_status       new / classified / processed / review / failed
parser_version
created_at
updated_at
```

Privacy rules:

- Full body, HTML, headers, attachments, addresses and raw identifiers never
  enter a connector payload by default.
- v2 stores complete recruitment mail locally by default to support replay and
  audit. Storage must be private to the OS user, encrypted at rest where the
  platform permits, and governed by a configurable retention policy.
- The compatibility migration must not claim that v0.6 historical bodies can
  be reconstructed; they were intentionally not persisted.

### 3.2 Company

```text
company_id
canonical_name
display_name
parent_company_id       optional
aliases[]
sender_domains[]
recruitment_domains[]
confidence
source                   built_in / user / extracted
created_at
updated_at
```

`canonical_name` is used for identity. `display_name` preserves the meaningful
brand or business-unit name shown to the user. Parent groups and business
units are not silently collapsed.

### 3.3 RecruitmentProject

```text
project_id
company_id
project_name
project_type             campus / internship / graduate_program / experienced
graduation_year
season                   spring / autumn / early / rolling / unknown
aliases[]
external_project_id      optional
created_at
updated_at
```

Project is part of Application identity. The same company and role in a summer
internship and a campus graduate programme are different applications.

### 3.4 Application

One Application represents one user application to one role in one recruitment
project.

```text
application_id
display_id               human-readable short label
company_id
project_id               optional until resolved
role_name
role_canonical
role_id_external         optional job code
business_unit            optional
location                 optional
applied_at               optional
current_stage            reducer output
current_status           reducer output
current_deadline         reducer output
next_action              projector summary
confidence               identity confidence
identity_locked          confirmed user identity guard
created_at
updated_at
```

`current_*` fields are materialized projections for query performance. Events,
not these fields, are authoritative.

### 3.5 Event

```text
event_id
application_id           nullable only while in Review Queue
source_mail_id           nullable for user/system events
type
occurred_at              event time when stated
received_at              mail/user input time
start_at
end_at
deadline_at
previous_start_at
previous_end_at
previous_deadline_at
round
location
online_url_local_ref     local only
evidence_ids[]
confidence
supersedes_event_id      optional
source                   mail / user / migration / system
rule_version
created_at
```

Events are append-only. A correction or parser improvement appends a new Event
and records which previous interpretation it supersedes.

### 3.6 Evidence

```text
evidence_id
mail_id                  local relation
field                    company / role / project / event / time / application
snippet_local
snippet_sync_safe        redacted and length-limited
source_span              local offsets when available
extractor
confidence
created_at
```

Evidence sync policy:

```text
none
minimal_snippet          default
full_recruitment_mail    explicit opt-in only
```

### 3.7 Task

Task is a current-action projection.

```text
task_id
application_id
origin_event_id
action_kind
title
start_at
deadline_at
status                   open / done / cancelled / expired
priority
completed_at
projection_key           idempotency key
updated_at
```

The projection key is based on Application + action kind + occurrence, not the
source mail. Multiple reminder mails update evidence/urgency on the same Task.

### 3.8 ReviewItem

```text
review_id
mail_id
suggested_application_id
suggested_event_type
alternative_application_ids[]
reason
evidence_ids[]
confidence
status                   pending / confirmed / corrected / ignored
corrected_application_id
corrected_event_type
created_at
resolved_at
```

Suggested default policy:

- confidence `>= 0.90`: accept automatically;
- confidence `0.65–0.90`: apply provisionally and create ReviewItem;
- confidence `< 0.65`: do not mutate Application projections; create ReviewItem.

Thresholds are configuration and must be calibrated against the golden
dataset, not treated as permanent constants.

### 3.9 Correction

```text
correction_id
review_id
mail_id
original_output
corrected_output
context
created_at
```

Corrections are audit data and regression inputs. v2 does not automatically
train a model from a single correction.

### 3.10 ConnectorOutbox

```text
outbox_id
aggregate_type
aggregate_id
projection_version
connector_name
operation                upsert / append / close
payload_safe
status                   pending / delivered / retry / dead_letter
attempt_count
next_attempt_at
created_at
delivered_at
```

Outbox payloads are sanitized before commit. Connector code cannot query raw
mail bodies as part of normal projection delivery.

## 4. Event taxonomy v1

The initial taxonomy intentionally stays small.

| Event type | Stage effect | Task effect | Notes |
|---|---|---|---|
| `APPLICATION_RECEIVED` | at least APPLIED | none | acknowledgement or manually confirmed application |
| `APPLICATION_UPDATED` | none | optional profile/update action | application detail changed |
| `PROFILE_COMPLETION_REQUESTED` | none | upsert profile task | deadline may be actionable |
| `SCREENING_STARTED` | SCREENING | none | no invented deadline |
| `ASSESSMENT_INVITED` | ASSESSMENT | upsert assessment task | assessment distinct from written exam |
| `ASSESSMENT_REMINDER` | none | update existing assessment task | never creates a duplicate occurrence |
| `ASSESSMENT_RESCHEDULED` | none | reschedule existing task | retains previous schedule |
| `ASSESSMENT_CANCELLED` | none | cancel occurrence task | application may remain active |
| `ASSESSMENT_COMPLETED` | none | complete assessment task | usually user/manual event |
| `WRITTEN_EXAM_INVITED` | WRITTEN_EXAM | upsert exam task | actionable schedule/deadline |
| `WRITTEN_EXAM_REMINDER` | none | update existing exam task | no stage advance |
| `WRITTEN_EXAM_RESCHEDULED` | none | reschedule exam task | retains previous schedule |
| `WRITTEN_EXAM_CANCELLED` | none | cancel exam task | does not imply rejection |
| `WRITTEN_EXAM_COMPLETED` | none | complete exam task | waits for later result |
| `INTERVIEW_INVITED` | INTERVIEW | upsert interview task | round is an event attribute |
| `INTERVIEW_RESCHEDULED` | none | reschedule interview task | links to occurrence |
| `INTERVIEW_CANCELLED` | none | cancel interview task | application may remain active |
| `INTERVIEW_COMPLETED` | none | complete interview task | does not invent pass/fail |
| `NEXT_ROUND_PASSED` | INTERVIEW | none | round progression without schedule |
| `OFFER_INTENT` | OFFER | optional follow-up task | not equivalent to signed Offer |
| `OFFER_RECEIVED` | OFFER | upsert response task if needed | records reply deadline |
| `REJECTED` | CLOSED | close open tasks | terminal unless corrected |
| `APPLICATION_CLOSED` | CLOSED | close open tasks | withdrawal/ended/explicit closure |
| `GENERAL_NOTICE` | none | none by default | attach to timeline only |
| `UNKNOWN_RECRUITMENT_EVENT` | none | none | Review Queue unless safely ignorable |

## 5. Application stages and lifecycle status

Stage answers “where is the application in the recruitment funnel?”

```text
UNKNOWN
APPLIED
SCREENING
ASSESSMENT
WRITTEN_EXAM
INTERVIEW
OFFER
CLOSED
```

Status answers “what is the user/application condition now?”

```text
ACTIVE
ACTION_REQUIRED
WAITING
TERMINAL_REJECTED
TERMINAL_CLOSED
ARCHIVED
```

Stage and status are deliberately separate. Completing an assessment changes
status from `ACTION_REQUIRED` to `WAITING`; it does not invent a later stage.

## 6. State reducer

### 6.1 Ordering

For one Application, active Events are reduced in this stable order:

1. `occurred_at` when explicit, otherwise `received_at`;
2. `received_at`;
3. local append sequence.

Superseded interpretations are excluded from the active reduction but remain
queryable in history.

### 6.2 Stage progression

- Stage advances only for stage-bearing Events.
- Reminder, reschedule, cancellation-of-occurrence and completion Events do not
  advance stage by themselves.
- Lower-rank or older Events do not move the stage backward.
- A user Correction Event may explicitly replace an incorrect stage.
- `REJECTED` and `APPLICATION_CLOSED` produce a terminal stage/status.
- A terminal aggregate can reopen only through an explicit confirmed
  Correction or a future `APPLICATION_REOPENED` taxonomy addition; a generic
  new mail cannot reopen it.

### 6.3 Schedule and deadline

- Invitation sets the schedule for a specific occurrence.
- Reschedule must identify an occurrence or enter Review Queue.
- Reschedule appends previous and new values and supersedes the active schedule
  Event; it never edits the earlier Event.
- Cancellation closes the occurrence Task but does not automatically close the
  Application.
- The current Application deadline is the nearest active actionable Task
  deadline, not simply the latest date found in mail.

### 6.4 Duplicate and reminder handling

- Exact provider/message/content duplicates create no second Mail/Event.
- Semantic duplicate Events may attach new Evidence to an existing occurrence.
- Reminder Events update urgency/evidence on the current Task and never create
  a second Task.
- A reminder received after the action is completed remains timeline evidence
  and cannot reopen the Task without explicit new action content.

## 7. Task projector

The projector consumes reduced Application state and active actionable Events.

Rules:

1. Invitation/profile request/Offer reply produces or updates one occurrence
   Task.
2. Reminder finds the existing projection key and updates urgency/evidence.
3. Reschedule updates the projected schedule and preserves history in Events.
4. Cancellation marks the occurrence Task cancelled.
5. Completion marks it done and records completion time.
6. Rejection/application closure closes all open Tasks for the Application.
7. Past events do not become new Tasks during migration unless an explicit
   incomplete action is still valid.
8. No explicit action or reliable time means timeline/review, not a fabricated
   Task.

## 8. Application resolver v1

Resolution is staged and conservative.

### Hard identity

Highest-confidence signals:

- provider/ATS application ID;
- external job code;
- explicit project ID;
- provider thread tied to an already confirmed application;
- a user-locked Application identity.

A different explicit job code must not merge into an existing Application.

### Company identity

Use sender/recruitment domains, company aliases, parent/business-unit
relationships, sender names and extracted body evidence. Parent and child
companies remain distinct unless the dictionary defines the relationship.

### Project and role identity

Compare project cycle/type/year, canonical role, external role ID, business
unit and location. Same company + same role is insufficient when project or
year differs.

### Temporal/context evidence

Time proximity and batch context can rank candidates but cannot override a
hard conflict. A company-only acknowledgement attaches only when there is one
unambiguous candidate; otherwise it enters Review Queue and must not create a
placeholder Application.

### Optional semantic/LLM assistance

The optional resolver returns a proposal, confidence, explanation and
alternatives. Core applies the same thresholds and hard-conflict guards as for
deterministic candidates.

## 9. Connector contract

Core exposes domain projections only:

```python
class WorkspaceConnector:
    def upsert_company(self, company): ...
    def upsert_application(self, application): ...
    def append_event(self, event): ...
    def upsert_task(self, task): ...
    def create_review_item(self, item): ...
    def resolve_review_item(self, item): ...
```

Implementations must be idempotent by stable domain ID and projection version.
Feishu, Obsidian and future connectors live outside Core domain packages.

## 10. Persistence model

v2 uses local SQLite as the transactional event and projection store:

```text
mail_accounts
mails
companies
recruitment_projects
applications
events
evidence
tasks
review_items
corrections
connector_outbox
processing_attempts
```

Markdown and Feishu are projections, not authoritative facts. Raw mail content
uses a separate local content store referenced from `mails` so connector
queries cannot accidentally select it.

## 11. Golden dataset and metrics

The evaluation corpus uses sanitized or synthetic fixtures derived from real
recruitment patterns. Raw private mail never enters the repository.

Each case labels:

```text
is_recruitment
company
project
role
application_label
event_type
expected_stage
deadline
should_create_task
evidence
```

Required metrics:

- Recruitment Classification Precision;
- Company Resolution Accuracy;
- Role Resolution Accuracy;
- Application Linking Accuracy;
- Event Classification Accuracy;
- Deadline Accuracy;
- State Transition Accuracy;
- Duplicate Task Rate;
- False Task Creation Rate.

The release gate prioritizes Application Linking Accuracy and False Task
Creation Rate over a single aggregate model score.

## 12. Error severity

### P0

- missed or incorrect actionable deadline;
- new time replaced by an older time;
- two distinct applications incorrectly merged;
- cancelled occurrence still produces an active reminder;
- terminal/completed item reactivated by replay;
- false actionable Task.

### P1

- wrong company/application attribution without a hard merge;
- wrong stage or interview round;
- a resolvable item remains in Review Queue.

### P2

- display name, evidence length, label or cosmetic metadata issue.

## 13. Implementation slices

1. Add domain dataclasses/enums and pure reducer/projector tests without
   changing the v0.6 scan path.
2. Add v2 SQLite schema and repositories behind a disabled feature flag.
3. Append v2 Events in shadow mode while v0.6 remains authoritative.
4. Compare applications/tasks from both projections using anonymous fixtures.
5. Refactor Application Resolver and Review/Correction flow.
6. Establish the golden dataset and P0 metric gates.
7. Implement Connector contract and Obsidian compatibility adapter.
8. Implement Feishu Connector and six-table schema (Companies, Applications,
   Events, Tasks, Reviews and optional safe Evidence projections) only after the domain
   model passes shadow validation.

No Feishu API call, Base creation, old UI deletion or primary-workspace switch
is permitted before slices 1–6 pass.

## 14. Design acceptance cases

The reducer/projector contract is incomplete until these tests exist:

- invitation → reminder produces one Task;
- invitation → reschedule preserves old and new time and updates one Task;
- invitation → cancellation cancels only the occurrence;
- completion → reminder does not reopen Task;
- rejection → generic notice does not reopen Application;
- two roles with different job codes remain two Applications;
- same role in two recruitment projects remains two Applications;
- company-only receipt with two candidates enters Review Queue;
- manual correction survives parser replay;
- connector delivery failure leaves local Event/Application/Task committed;
- connector payload contains no raw body, address, private URL or credential.
