import subprocess
from pathlib import Path

from breezy_trace.git import branch_intelligence


def run(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def configure(path: Path) -> None:
    run(path, "config", "user.email", "trace@example.test")
    run(path, "config", "user.name", "Trace Test")


def commit(path: Path, filename: str, message: str) -> None:
    (path / filename).write_text(message + "\\n", encoding="utf-8")
    run(path, "add", filename)
    run(path, "commit", "-m", message)


def test_branch_intelligence_reports_local_branches_without_upstream(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    configure(repo)
    commit(repo, "one.txt", "Initial commit")
    run(repo, "branch", "feature/example")

    details = branch_intelligence(repo)

    assert details["current_branch"] == "main"
    assert details["upstream"] is None
    assert details["ahead"] is None
    assert details["behind"] is None
    assert {item["name"] for item in details["local_branches"]} == {"main", "feature/example"}
    assert details["remote_branches"] == []
    assert details["unpushed_commits"] == []
    assert details["upstream_only_commits"] == []


def test_branch_intelligence_separates_ahead_and_behind_commits(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    local.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(local)], check=True, capture_output=True)
    configure(local)
    commit(local, "base.txt", "Base commit")
    run(local, "remote", "add", "origin", str(remote))
    run(local, "push", "-u", "origin", "main")
    subprocess.run(
        ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True
    )

    subprocess.run(["git", "clone", str(remote), str(peer)], check=True, capture_output=True)
    configure(peer)
    commit(peer, "remote.txt", "Remote-only commit")
    run(peer, "push", "origin", "main")

    commit(local, "local.txt", "Local-only commit")
    run(local, "fetch", "origin")

    details = branch_intelligence(local)

    assert details["upstream"] == "origin/main"
    assert details["ahead"] == 1
    assert details["behind"] == 1
    assert [item["subject"] for item in details["unpushed_commits"]] == ["Local-only commit"]
    assert [item["subject"] for item in details["upstream_only_commits"]] == ["Remote-only commit"]
    assert any(item["name"] == "origin/main" for item in details["remote_branches"])
