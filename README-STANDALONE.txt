Breezy Trace Standalone Binary Guide

This document describes how to use Breezy Trace when installed as a
standalone (frozen/PyInstaller) binary.

------------------------------------------------------------
1. What is a standalone install?
------------------------------------------------------------
A standalone binary is a single executable that bundles the Python
interpreter and all dependencies. It is created using PyInstaller and
distributed as official releases.

Standalone installs have the following characteristics:
- No code signing (Windows SmartScreen may warn; macOS may need
  right-click > Open to launch)
- The ``breezy-trace update`` command refuses to modify a standalone
  install — it will print a message suggesting you download the new
  version instead
- Self-update is not supported; you must download the latest release
  manually

------------------------------------------------------------
2. Running the binary
------------------------------------------------------------

Windows
  • Double-click breezy-trace.exe, or run it from a PowerShell prompt:
    .\breezy-trace.exe
  • First run may trigger SmartScreen — click "More info" → "Run
    anyway"
  • To add to PATH (PowerShell):
    [Environment]::SetEnvironmentVariable("PATH",
        [Environment]::GetEnvironmentVariable("PATH", "User") +
        ";C:\Program Files\Breezy-trace", "User")

macOS
  • Run from a terminal: ./breezy-trace
  • First run may require Right-click (Control-click) → Open
  • To add to PATH:
    export PATH="$PATH:/opt/breezy-trace"

Linux
  • Run from a terminal: ./breezy-trace
  • To add to PATH:
    export PATH="$PATH:/opt/breezy-trace"

------------------------------------------------------------
3. Updating a standalone install
------------------------------------------------------------
The ``breezy-trace update`` command will refuse to modify a standalone
install with the following message:

  Breezy Trace is installed as a standalone (frozen) application.
  Self-update is not supported. Download the new version from the
  website or re-run the installer to get the latest release.

To update:
1. Download the latest release archive for your platform from the
   GitHub Release page.
2. Extract the archive.
3. Replace the old binary with the new one, or run the new binary
   directly.

Do NOT run ``breezy-trace update`` — it will refuse and instruct you
to download the new version manually.

------------------------------------------------------------
4. Verifying the install
------------------------------------------------------------
After downloading a release, verify the archive integrity:

  # Windows PowerShell
  Get-FileHash .\breezy-trace-0.2.0-windows-x64.zip

  # macOS / Linux
  sha256sum breezy-trace-0.2.0-windows-x64.zip

The SHA-256 checksums are published on the GitHub Release page
alongside each asset.

------------------------------------------------------------
5. CLI options
------------------------------------------------------------
--version   Print the version and exit
--self-test Boot the real TUI interface with a temporary data directory
            and exit 0 if successful. Used inside CI/frozen builds.
--no-intro  Skip the animated boot sequence