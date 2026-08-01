# Security

## Supported version

Security fixes are applied to the latest `0.4.x` preview release.

## Secrets

Never put email passwords, authorization codes, cookies, browser tokens,
private notification links, or real recruiting passcodes in issues, fixtures,
logs, screenshots, commits, or Markdown.

## Updates

- Version notifications accept only Release pages from
  `Chpeeeeea/job-mail-desk` and require both the current platform ZIP and its
  companion `.sha256` to exist before showing a version as available.
- The application does not automatically download, extract, execute, or
  install Release assets.
- Users should verify the published `.sha256`, exit JobMailDesk, and manually
  replace only the executable or app bundle. Local data and credentials are
  outside that boundary.

## Reporting

Before a public repository exists, report security concerns directly to the
project owner. Do not open a public issue containing private data.
