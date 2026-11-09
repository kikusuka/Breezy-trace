"""Windows Explorer integration: right-click a folder -> "Open with Breezy Trace".

Writes two per-user (HKCU) registry keys, so no administrator rights are needed and
nothing outside your account changes. ``uninstall`` removes exactly what ``install``
wrote. The registry module is passed in so this can be tested on any platform.
"""

import sys

LABEL = "Open with Breezy Trace"
FOLDER_KEY = r"Software\Classes\Directory\shell\BreezyTrace"
BACKGROUND_KEY = r"Software\Classes\Directory\Background\shell\BreezyTrace"
# %1 is the folder you right-clicked; %V is the folder you are inside (empty-space click).
TARGETS = ((FOLDER_KEY, "%1"), (BACKGROUND_KEY, "%V"))


def launch_command(python: str, placeholder: str) -> str:
    return f'"{python}" -m breezy_trace open "{placeholder}"'


def install(winreg, python: str | None = None) -> list[str]:
    """Create the menu entries; returns the commands that were registered."""
    python = python or sys.executable
    registered: list[str] = []
    for key, placeholder in TARGETS:
        command = launch_command(python, placeholder)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as menu:
            winreg.SetValueEx(menu, "", 0, winreg.REG_SZ, LABEL)
            winreg.SetValueEx(menu, "Icon", 0, winreg.REG_SZ, f'"{python}"')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as entry:
            winreg.SetValueEx(entry, "", 0, winreg.REG_SZ, command)
        registered.append(command)
    return registered


def uninstall(winreg) -> int:
    """Remove the menu entries; returns how many keys were deleted."""
    removed = 0
    for key, _placeholder in TARGETS:
        for name in (key + r"\command", key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, name)
            except FileNotFoundError:
                continue
            removed += 1
    return removed


def installed_command(winreg) -> str | None:
    """The command currently registered for folders, or ``None``."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FOLDER_KEY + r"\command") as entry:
            return winreg.QueryValueEx(entry, "")[0]
    except FileNotFoundError:
        return None
