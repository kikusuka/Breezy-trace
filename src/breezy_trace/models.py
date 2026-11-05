"""Small domain models shared by the application."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    path: str
    registered_at: str
    last_opened_at: str | None = None

    @property
    def display_path(self) -> str:
        return self.path


@dataclass(frozen=True, slots=True)
class GitStatus:
    branch: str
    staged: int
    modified: int
    untracked: int
    ahead: int
    behind: int
    clean: bool
    summary: str

    @classmethod
    def unavailable(cls, reason: str) -> "GitStatus":
        return cls(
            branch="unknown",
            staged=0,
            modified=0,
            untracked=0,
            ahead=0,
            behind=0,
            clean=False,
            summary=reason,
        )
