# Privacy

JobMailDesk is local-first.

- Email is opened through IMAP in read-only mode.
- The scanner uses `BODY.PEEK` and does not intentionally mark messages read.
- It has no send, reply, delete, move, or mailbox-settings feature.
- Passwords and authorization codes are stored only in the operating-system
  credential store.
- Full email bodies are parsed in memory and are not persisted.
- Markdown stores structured job facts and redacted evidence only.
- Public research requests contain company, role, recruiting project, year,
  and stage. They exclude email addresses, phone numbers, passcodes, message
  identifiers, private links, and email body text.
- Obsidian export is optional. Sender and private-link export are disabled by
  default because a chosen vault may sync to a cloud provider.
- Optional update checks send one unauthenticated HTTPS request to the public
  GitHub Releases API at most once every 24 hours. GitHub can observe the
  request IP address and JobMailDesk version in the User-Agent. No email,
  task, credential, local path, or Obsidian content is included.
- The application displays release notes and opens this project's public
  GitHub Release page. It does not automatically download or install updates.
  Disabling automatic checks does not affect email scanning or local tasks.
