#!/usr/bin/env bash
# One-shot, idempotent setup for cadstudio on macOS (Apple silicon).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_MIN=22

ASSUME_YES=0
WANT_PRUSA=1
WORKSPACES=()

usage() {
  cat <<'EOF'
Usage: ./setup.sh [options]

Sets up cadstudio: Python env (uv), UI and VS Code extension builds, and the
extension install. Safe to re-run.

Options:
  --workspace DIR    Also wire up a projects repo at DIR (repeatable): link the
                     engine's agent skills into it and run `uv sync` there.
  --no-prusaslicer   Do not offer to install PrusaSlicer.
  --yes, -y          Answer yes to every prompt.
  --help, -h         Show this help.
EOF
}

say() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Ask a yes/no question; --yes accepts, a non-interactive shell declines.
confirm() {
  if [ "$ASSUME_YES" -eq 1 ]; then return 0; fi
  if [ ! -t 0 ]; then return 1; fi
  local reply
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy] ]]
}

while [ $# -gt 0 ]; do
  case "$1" in
    --workspace)
      [ $# -ge 2 ] || die "--workspace needs a directory"
      WORKSPACES+=("$2"); shift 2 ;;
    --workspace=*) WORKSPACES+=("${1#*=}"); shift ;;
    --no-prusaslicer) WANT_PRUSA=0; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

# --- Platform and Homebrew ---------------------------------------------------

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] \
  || die "cadstudio supports macOS on Apple silicon only (found $(uname -s) $(uname -m))."

if ! have brew; then
  cat >&2 <<'EOF'
error: Homebrew is required but was not found. Install it, then re-run:
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
EOF
  exit 1
fi

# --- uv and node -------------------------------------------------------------

missing=()
have uv || missing+=(uv)
have node || missing+=(node)
if [ "${#missing[@]}" -gt 0 ]; then
  say "Installing with Homebrew: ${missing[*]}"
  brew install "${missing[@]}"
else
  say "uv and node already installed"
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" -lt "$NODE_MIN" ]; then
  die "node $(node -v) is too old; cadstudio needs node >= $NODE_MIN. Run: brew upgrade node"
fi

# --- PrusaSlicer (optional) --------------------------------------------------

prusa_app=/Applications/PrusaSlicer.app
prusa_bin="$prusa_app/Contents/MacOS/PrusaSlicer"

if [ "$WANT_PRUSA" -eq 1 ]; then
  if [ ! -d "$prusa_app" ] && ! have prusa-slicer; then
    if confirm "PrusaSlicer is not installed (print_plate.py needs it). Install with Homebrew?"; then
      brew install --cask prusaslicer
    else
      say "Skipping PrusaSlicer"
    fi
  fi
  if [ -x "$prusa_bin" ] && ! have prusa-slicer; then
    if confirm "Link a prusa-slicer command into ~/.local/bin?"; then
      mkdir -p "$HOME/.local/bin"
      ln -sfn "$prusa_bin" "$HOME/.local/bin/prusa-slicer"
      say "Linked ~/.local/bin/prusa-slicer"
      case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) warn "$HOME/.local/bin is not on your PATH; add it to your shell profile." ;;
      esac
    fi
  elif have prusa-slicer; then
    say "prusa-slicer already available"
  fi
fi

# --- Python environment ------------------------------------------------------

uv_sync() {
  # Frozen when a lock exists; otherwise let uv create one.
  if [ -f "$1/uv.lock" ]; then
    (cd "$1" && uv sync --frozen --extra physics)
  else
    (cd "$1" && uv sync --extra physics)
  fi
}

say "Syncing the Python environment"
uv_sync "$ROOT"

# --- UI and VS Code extension ------------------------------------------------

say "Building the UI"
(cd "$ROOT/ui" && npm ci && npm run build)

# The extension build copies ui/dist into its media, so the UI goes first.
say "Building and packaging the VS Code extension"
(cd "$ROOT/editor/vscode" && npm ci && npm run build && npm run package)

vsix="$ROOT/editor/vscode/cadstudio.vsix"
[ -f "$vsix" ] || die "expected $vsix after packaging"

if have code; then
  say "Installing the extension into VS Code"
  code --install-extension "$vsix" --force
else
  warn "the 'code' command is not on PATH, so the extension was not installed."
  echo "    In VS Code, run 'Shell Command: Install \"code\" command in PATH' from the" >&2
  echo "    Command Palette, then re-run ./setup.sh (or: code --install-extension $vsix)." >&2
fi

# --- Projects workspaces -----------------------------------------------------

# Create or refresh a symlink; never replace a real file or directory.
link() {
  local target="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    warn "$dest exists and is not a symlink; leaving it alone"
    return
  fi
  ln -sfn "$target" "$dest"
  say "Linked $dest -> $target"
}

for ws in ${WORKSPACES[@]+"${WORKSPACES[@]}"}; do
  [ -d "$ws" ] || die "workspace not found: $ws"
  ws="$(cd "$ws" && pwd)"
  say "Wiring workspace $ws"
  link "$ROOT/.claude/skills/cadstudio" "$ws/.claude/skills/cadstudio"
  link "$ROOT/.claude/skills/connect-ide" "$ws/.claude/skills/connect-ide"
  link "$ROOT/.agents/skills/cadstudio" "$ws/.agents/skills/cadstudio"
  if [ -f "$ws/pyproject.toml" ]; then
    uv_sync "$ws"
  else
    warn "$ws has no pyproject.toml; skipped uv sync"
  fi
done

# --- Verify ------------------------------------------------------------------

say "Running cad doctor"
(cd "$ROOT" && uv run --frozen cad doctor) || warn "cad doctor reported problems (see above)"

cat <<EOF

Setup finished. Next steps:
  1. Open this folder in VS Code:      code $ROOT
  2. Build the example with a scene:   uv run cad build starter/box --check --scene
  3. Show it in the CADStudio panel:   uv run cad gui open starter/box
EOF
