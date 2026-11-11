"""Where a local repository lives on the web (GitHub, GitLab, ...), read from ``.git/config``.

Entirely offline and read-only: it parses the remote URLs Git already stores. Any
credentials embedded in a URL (``https://user:token@host/...``) are discarded and are
never shown, stored or logged.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from breezy_trace.git import run_git

_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_SCP_LIKE = re.compile(r"^(?:[\w.~-]+@)?(?P<host>[\w.-]+):(?P<path>(?!/)[^\s]+)$")

KNOWN_HOSTS = {
    "github.com": "GitHub",
    "gitlab.com": "GitLab",
    "bitbucket.org": "Bitbucket",
    "codeberg.org": "Codeberg",
}


@dataclass(frozen=True)
class Remote:
    name: str
    host: str
    slug: str  # owner/repo, or group/subgroup/repo
    provider: str  # GitHub, GitLab, Bitbucket, Codeberg or Git
    web_url: str

    @property
    def label(self) -> str:
        return f"{self.provider} · {self.slug}"


def provider_for(host: str) -> str:
    host = host.lower()
    if host in KNOWN_HOSTS:
        return KNOWN_HOSTS[host]
    if "gitlab" in host:
        return "GitLab"  # self-hosted
    if "github" in host:
        return "GitHub"  # GitHub Enterprise
    return "Git"


def parse_remote_url(name: str, raw: str) -> Remote | None:
    """Parse a remote URL; ``None`` for local paths and anything without a host."""
    raw = raw.strip()
    if not raw or _WINDOWS_PATH.match(raw) or raw.startswith((".", "/", "~")):
        return None
    host = path = ""
    if "://" in raw:
        parts = urlsplit(raw)
        if parts.scheme in ("file", "") or not parts.hostname:
            return None
        host, path = parts.hostname, parts.path
    else:
        match = _SCP_LIKE.match(raw)
        if match is None:
            return None
        host, path = match["host"], match["path"]
    slug = path.strip("/").removesuffix(".git")
    if not host or not slug:
        return None
    host = host.lower()
    return Remote(
        name=name,
        host=host,
        slug=slug,
        provider=provider_for(host),
        web_url=f"https://{host}/{slug}",
    )


def list_remotes(path: Path) -> list[Remote]:
    """Remotes configured for the repository, ``origin`` first."""
    command = run_git(path, "config", "--get-regexp", r"^remote\..*\.url$")
    if command is None or command.returncode != 0:
        return []
    remotes: list[Remote] = []
    for line in command.stdout.splitlines():
        key, _, url = line.partition(" ")
        name = key.removeprefix("remote.").removesuffix(".url")
        remote = parse_remote_url(name, url)
        if remote is not None:
            remotes.append(remote)
    return sorted(remotes, key=lambda remote: remote.name != "origin")


def primary_remote(remotes: list[Remote]) -> Remote | None:
    return remotes[0] if remotes else None
