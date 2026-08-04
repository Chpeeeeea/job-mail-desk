# Identity dictionaries

JobMailDesk Core ships with a reviewed base dictionary containing 520
companies, 129 recruiting programs, 2825 role names, and verified mail
templates. They normalize names but never prove that a user applied for a job.

## Sources and precedence

Built-in files are packaged under `job_mail_desk/identity_data/`:

- `companies.yml`
- `programs.yml`
- `roles.yml`
- `mail_templates.yml`

Optional user dictionaries live in `%LOCALAPPDATA%\JobMailDesk\dictionaries`
on Windows. Precedence is fixed:

1. bundled base dictionary;
2. `imported/`, generated from the Settings page;
3. legacy YAML files in the dictionary root;
4. `manual/`, for explicit user-maintained overrides.

An item replaces only an item with the same stable `id`. Manual rules therefore
remain stronger than spreadsheet imports.

The user's application/progress ledger remains the source of truth for which
positions were actually applied to. A company or role dictionary entry is not
evidence that an application exists.

## Safety rules

- Unknown fields fail validation.
- Duplicate IDs fail validation.
- Alias collisions fail validation.
- Programs and mail templates cannot reference an unknown company.
- A generic application receipt has `creates_application: false` and cannot
  create a new application chain by itself.
- Company name alone is insufficient for automatic application assignment.
- Conflicting job codes, recruiting programs, years, or business units block
  automatic assignment.

## Check dictionaries

```powershell
jobmaildesk dictionary-check
```

To inspect a separate override directory without changing local data:

```powershell
jobmaildesk dictionary-check --user-dir D:\path\to\dictionaries
```

The command is read-only. It prints item counts and every loaded source file.

## Compile a personal spreadsheet dictionary

The Settings page can select an XLSX recruiting sheet, choose its worksheet,
compile it locally, validate it, and activate it without restarting. The source
path is not written to configuration and the workbook is not copied.

The same operation is available from the CLI:

```powershell
jobmaildesk dictionary-compile `
  --xlsx "D:\path\to\recruiting.xlsx" `
  --output "$env:LOCALAPPDATA\JobMailDesk\dictionaries\imported"

jobmaildesk dictionary-check `
  --user-dir "$env:LOCALAPPDATA\JobMailDesk\dictionaries"
```

The compiler uses the XLSX format directly and requires no Excel installation.
It does not copy application links, annotations, contact information, cities,
education requirements, or source rows. It writes a source hash and aggregate
counts to `compilation-report.json` for local auditing.

The compiler has workbook-size, expanded-size, and row-count limits. It writes
only normalized company, explicit project-label, and role fields plus a local
audit report; links, annotations, contact details, cities, education
requirements, and source rows are not copied.

## Preview mailbox identity resolution

To inspect identity resolution without writes, replay a bounded mailbox window:

```powershell
jobmaildesk scan --identity-preview --days 3 `
  --preview-output "$env:LOCALAPPDATA\JobMailDesk\identity-preview.md"
```

Identity preview deliberately does not:

- create or update task Markdown;
- change `state.db` or processed-message markers;
- import Obsidian checkbox changes;
- create Application Registry or unresolved records;
- export email bodies, sender addresses, private links, or authentication data.

Normal scans now use the same resolver and write either a canonical application
task or a privacy-safe unresolved record. Use `unresolved-list`,
`unresolved-resolve`, and `unresolved-ignore` for the local review loop.
