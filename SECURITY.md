# Security Policy

## Supported versions

Security fixes are provided for the latest `0.1.x` release.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private vulnerability reporting for this repository if it is available:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Include the affected version, operating system, Python version, reproduction steps, and the impact you observed.

If private reporting is not available, contact the maintainer through the repository profile and ask for a private channel. Do not include exploit details in a public issue.

## Scope

Breezy Trace runs locally and reads Git state. Areas that deserve security review include:

- SQLite database handling and restore validation
- Git subprocess arguments and repository path handling
- Clone URL handling and credential redaction
- Editor, terminal, and file-manager launching
- Optional Tree-sitter grammar downloads

## What to expect

We will review the report, confirm the affected versions, and prepare a fix and disclosure plan. Please give us reasonable time to address the issue before publishing details.
