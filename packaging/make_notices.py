#!/usr/bin/env python3
"""Generate THIRD_PARTY_NOTICES.txt for the standalone binaries.

The wheel metadata is the source of truth: the script walks the installed
dependency tree from Breezy Trace's runtime dependencies, reads each
package's licence name and licence files, and refuses to write the notices
if a package cannot be identified or is not on the allow-list below.
"""

from __future__ import annotations

import argparse
import platform
import sys
from collections import deque
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

ALLOWED_LICENCES = frozenset({"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "PSF"})

ROOT_PACKAGES = ("breezy-trace", "textual", "rich", "platformdirs")

_CLASSIFIER_LICENCES = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: BSD 2-Clause License": "BSD-2-Clause",
    "License :: OSI Approved :: BSD 3-Clause License": "BSD-3-Clause",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF",
}

_LICENCE_ALIASES = {
    "mit": "MIT",
    "mit license": "MIT",
    "expat": "MIT",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "apache-2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "isc": "ISC",
    "isc license": "ISC",
    "psf": "PSF",
    "psf-2.0": "PSF",
    "python software foundation license": "PSF",
    "python-2.0": "PSF",
}

_LICENCE_FILE_STEMS = {"license", "licence", "copying", "notice"}

_DIVIDER = "=" * 78
_SECTION = "-" * 78


@dataclass(frozen=True)
class Package:
    """One bundled distribution and its licence information."""

    name: str
    version: str
    licence: str
    text: str


def normalize_licence(value: str | None) -> str | None:
    """Return a canonical allow-list name, or ``None`` if unrecognised."""

    if not value:
        return None
    text = " ".join(value.strip().split())
    if not text:
        return None
    if any(operator in text.upper() for operator in (" OR ", " AND ", " WITH ")):
        return None
    return _LICENCE_ALIASES.get(text.lower())


def validate_licence(package: str, licence: str | None) -> str:
    """Fail the build unless ``licence`` is identifiable and allowed."""

    if licence is None:
        raise SystemExit(
            f"error: no identifiable licence for {package}. "
            "Add it to the allow-list only after checking its licence."
        )
    if licence not in ALLOWED_LICENCES:
        raise SystemExit(
            f"error: {package} is licensed under {licence}, which is not on the "
            f"allow-list: {', '.join(sorted(ALLOWED_LICENCES))}."
        )
    return licence


def _requirement_applies(requirement: Requirement, extras: set[str]) -> bool:
    if requirement.marker is None:
        return True
    return any(requirement.marker.evaluate({"extra": extra}) for extra in {"", *extras})


def _distributions() -> dict[str, set[str]]:
    """Walk the installed runtime dependency tree.

    Returns each canonical distribution name with the set of extras that were
    requested for it. Markers are evaluated for the current interpreter, and
    optional extras of Breezy Trace itself are never requested.
    """

    found: dict[str, set[str]] = {}
    queue: deque[tuple[str, frozenset[str]]] = deque(
        (canonicalize_name(name), frozenset()) for name in ROOT_PACKAGES
    )

    while queue:
        name, extras = queue.popleft()
        known = found.get(name)
        if known is not None and known.issuperset(extras):
            continue

        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError as error:
            raise SystemExit(
                f"error: {name} is required by the bundle but is not installed."
            ) from error

        found.setdefault(name, set()).update(extras)
        for raw in distribution.requires or []:
            try:
                requirement = Requirement(raw)
            except InvalidRequirement as error:
                raise SystemExit(f"error: {name} has an invalid requirement: {raw!r}") from error
            if not _requirement_applies(requirement, extras):
                continue
            queue.append(
                (
                    canonicalize_name(requirement.name),
                    frozenset(requirement.extras),
                )
            )

    return found


def _licence_from_metadata(distribution: metadata.Distribution) -> str | None:
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return normalize_licence(expression)

    declared = distribution.metadata.get("License")
    if declared:
        normalized = normalize_licence(declared)
        if normalized is not None:
            return normalized

    classifiers = {
        _CLASSIFIER_LICENCES.get(classifier)
        for classifier in distribution.metadata.get_all("Classifier") or []
        if classifier.startswith("License ::")
    }
    classifiers.discard(None)
    if len(classifiers) == 1:
        return classifiers.pop()
    return None


def _licence_files(distribution: metadata.Distribution) -> list[Path]:
    files: list[Path] = []
    for entry in distribution.files or []:
        stem = Path(str(entry)).name.lower().split(".", 1)[0]
        if stem not in _LICENCE_FILE_STEMS:
            continue
        path = Path(distribution.locate_file(entry))
        if path.is_file():
            files.append(path)
    return files


def _read_licence_texts(distribution: metadata.Distribution, package: str) -> str:
    texts: list[str] = []
    for path in _licence_files(distribution):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text and text not in texts:
            texts.append(text)
    if texts:
        return "\n\n".join(texts)

    declared = (distribution.metadata.get("License") or "").strip()
    if len(declared) > 200:
        return declared
    raise SystemExit(f"error: no licence file or full licence text found for {package}.")


def collect_packages() -> list[Package]:
    """Read the licence name and text for every package in the bundle."""

    packages: list[Package] = []
    for name in sorted(_distributions()):
        distribution = metadata.distribution(name)
        shown_name = distribution.metadata.get("Name") or name
        licence = validate_licence(shown_name, _licence_from_metadata(distribution))
        packages.append(
            Package(
                name=shown_name,
                version=distribution.version,
                licence=licence,
                text=_read_licence_texts(distribution, shown_name),
            )
        )
    return packages


def _python_runtime() -> Package:
    candidates = [
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
        Path(sys.executable).parent / "LICENSE.txt",
    ]
    for path in candidates:
        if path.is_file():
            return Package(
                name="Python runtime",
                version=platform.python_version(),
                licence="PSF",
                text=path.read_text(encoding="utf-8", errors="replace").strip(),
            )
    raise SystemExit("error: could not find the Python runtime licence file.")


def _pyinstaller_bootloader() -> Package:
    try:
        distribution = metadata.distribution("pyinstaller")
    except metadata.PackageNotFoundError as error:
        raise SystemExit(
            "error: PyInstaller is not installed, so its bootloader licence cannot be included."
        ) from error
    texts = [
        path.read_text(encoding="utf-8", errors="replace").strip()
        for path in _licence_files(distribution)
    ]
    if not texts:
        raise SystemExit(
            "error: PyInstaller does not ship its licence file; cannot include "
            "the bootloader notice."
        )
    return Package(
        name="PyInstaller bootloader",
        version=distribution.version,
        licence="GPL-2.0 with PyInstaller bootloader exception",
        text="\n\n".join(dict.fromkeys(texts)),
    )


def render_notices(packages: list[Package]) -> str:
    """Render the notices file from collected packages."""

    chunks = [
        "THIRD-PARTY NOTICES",
        _DIVIDER,
        "",
        "Breezy Trace includes the following third-party software.",
        "Each entry lists the package, its version, its licence, and the full",
        "licence text. This file is generated by packaging/make_notices.py.",
        "",
    ]
    for package in packages:
        chunks.extend(
            [
                _SECTION,
                f"{package.name} {package.version}",
                f"Licence: {package.licence}",
                _SECTION,
                "",
                package.text,
                "",
            ]
        )

    chunks.extend(
        [
            _SECTION,
            "FIXED COMPONENTS",
            _SECTION,
            "",
        ]
    )
    for package in (_python_runtime(), _pyinstaller_bootloader()):
        chunks.extend(
            [
                _SECTION,
                f"{package.name} {package.version}",
                f"Licence: {package.licence}",
                _SECTION,
                "",
                package.text,
                "",
            ]
        )
    return "\n".join(chunks).rstrip() + "\n"


def write_notices(output: Path) -> None:
    """Collect, validate and write the notices file."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_notices(collect_packages()), encoding="utf-8")
    print(f"Wrote {output}")


def main(argv: list[str] | None = None) -> int:
    default = Path(__file__).resolve().parent.parent / "THIRD_PARTY_NOTICES.txt"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default)
    args = parser.parse_args(argv)
    write_notices(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
