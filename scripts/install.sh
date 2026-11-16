#!/bin/sh
# Install Breezy Trace as a uv tool on macOS or Linux.
set -eu

UV_INSTALL_URL="https://astral.sh/uv/install.sh"
PACKAGE="breezy-trace"
version="${BREEZY_TRACE_VERSION:-}"
with_code=0

usage() {
    cat <<'EOF'
Install Breezy Trace as a uv tool.

Usage:
  sh scripts/install.sh [--version VERSION] [--with-code]

Environment:
  BREEZY_TRACE_VERSION     Install a specific version (for example 0.1.0).
  BREEZY_TRACE_WITH_CODE   Set to 1 to install optional multi-language support.
EOF
}

case "${BREEZY_TRACE_WITH_CODE:-0}" in
    1|true|TRUE|yes|YES) with_code=1 ;;
    0|false|FALSE|no|NO|"") with_code=0 ;;
    *)
        printf 'error: BREEZY_TRACE_WITH_CODE must be 1/0, true/false, or yes/no.\n' >&2
        exit 1
        ;;
esac

while [ "$#" -gt 0 ]; do
    case "$1" in
        --version)
            if [ "$#" -lt 2 ]; then
                printf 'error: --version requires a value.\n' >&2
                exit 1
            fi
            version=$2
            shift 2
            ;;
        --version=*)
            version=${1#*=}
            shift
            ;;
        --with-code)
            with_code=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'error: unrecognized argument: %s\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

step() {
    printf '==> %s\n' "$1"
}

fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

uv_bin=""
if command -v uv >/dev/null 2>&1; then
    uv_bin=$(command -v uv)
else
    command -v curl >/dev/null 2>&1 || fail "curl is required to install uv."
    step "Installing uv..."
    uv_installer=$(mktemp) || fail "Could not create a temporary file."
    if ! curl -LsSf "$UV_INSTALL_URL" -o "$uv_installer"; then
        rm -f "$uv_installer"
        fail "Could not download uv from $UV_INSTALL_URL."
    fi
    if ! sh "$uv_installer"; then
        rm -f "$uv_installer"
        fail "The uv installer failed."
    fi
    rm -f "$uv_installer"

    for dir in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin"; do
        if [ -n "$dir" ] && [ -d "$dir" ]; then
            PATH="$dir:$PATH"
        fi
    done
    export PATH
    command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on PATH. Open a new terminal and run this installer again."
    uv_bin=$(command -v uv)
fi

package="$PACKAGE"
if [ "$with_code" -eq 1 ]; then
    package="breezy-trace[code]"
fi
if [ -n "$version" ]; then
    package="$package==$version"
fi

step "Installing $package..."
if ! "$uv_bin" tool install --upgrade "$package"; then
    fail "uv could not install Breezy Trace."
fi

tool_bin=""
if tool_bin_output=$("$uv_bin" tool dir --bin 2>/dev/null); then
    tool_bin=$tool_bin_output
fi
if [ -z "$tool_bin" ]; then
    if [ -n "${UV_TOOL_BIN_DIR:-}" ]; then
        tool_bin=$UV_TOOL_BIN_DIR
    else
        tool_bin="$HOME/.local/bin"
    fi
fi

if [ -n "$tool_bin" ]; then
    PATH="$tool_bin:$PATH"
    export PATH
fi

case "${UV_NO_MODIFY_PATH:-}" in
    ""|0|false|FALSE)
        step "Adding the Breezy Trace command to your PATH..."
        if ! "$uv_bin" tool update-shell; then
            printf 'warning: uv could not update your shell PATH automatically.\n' >&2
            printf 'Add %s to your PATH, or run: %s tool update-shell\n' "$tool_bin" "$uv_bin" >&2
        fi
        ;;
    *)
        printf 'Skipping shell PATH update because UV_NO_MODIFY_PATH is set.\n'
        ;;
esac

exe="$tool_bin/breezy-trace"
if [ ! -x "$exe" ]; then
    if command -v breezy-trace >/dev/null 2>&1; then
        exe=$(command -v breezy-trace)
    else
        fail "Breezy Trace was installed, but $tool_bin/breezy-trace was not found."
    fi
fi

step "Verifying the install..."
if ! version_output=$("$exe" --version); then
    fail "breezy-trace --version failed. Open a new terminal and run: breezy-trace --version"
fi
printf '%s\n' "$version_output"

printf '\nBreezy Trace is ready.\n'
printf 'Next steps:\n'
printf '  1. Restart your terminal (or open a new terminal window) so the breezy-trace command is available.\n'
printf '  2. Run: breezy-trace\n'
printf '  3. Later, check for updates with: breezy-trace update --check\n'
printf '     and upgrade with: breezy-trace update\n'
if [ "$with_code" -eq 1 ]; then
    printf 'Optional multi-language indexing is installed.\n'
else
    printf 'Optional multi-language indexing: run this installer again with --with-code.\n'
fi
