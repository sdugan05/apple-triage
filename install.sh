#!/bin/sh
set -eu

PREFIX="${PREFIX:-$HOME/.local}"
INSTALL_SKILL=1

usage() {
  cat <<'EOF'
Usage: ./install.sh [--prefix PATH] [--no-skill]

Installs apple-triage to PATH and, by default, installs the companion Codex skill.

Options:
  --prefix PATH   Install wrapper under PATH/bin. Default: ~/.local
  --no-skill      Do not copy .codex/skills/apple-triage into CODEX_HOME.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      [ "$#" -ge 2 ] || { echo "--prefix requires a path" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    --no-skill)
      INSTALL_SKILL=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$(uname -s)" != "Darwin" ]; then
  echo "apple-triage requires macOS because it reads Apple Mail and Calendar via osascript." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install Xcode Command Line Tools or Homebrew Python." >&2
  exit 1
fi

if ! command -v osascript >/dev/null 2>&1; then
  echo "osascript is required and should be present on macOS." >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN_DIR="$PREFIX/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/apple-triage" <<EOF
#!/bin/sh
exec python3 "$SCRIPT_DIR/apple_triage/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/apple-triage"

echo "Installed $BIN_DIR/apple-triage"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "Note: add $BIN_DIR to PATH if 'apple-triage' is not found by your shell."
    echo "For zsh: echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc"
    ;;
esac

if [ "$INSTALL_SKILL" -eq 1 ]; then
  CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
  SRC_SKILL="$SCRIPT_DIR/.codex/skills/apple-triage"
  DST_SKILL="$CODEX_HOME_DIR/skills/apple-triage"
  if [ -f "$SRC_SKILL/SKILL.md" ]; then
    mkdir -p "$(dirname "$DST_SKILL")"
    rm -rf "$DST_SKILL"
    cp -R "$SRC_SKILL" "$DST_SKILL"
    echo "Installed Codex skill $DST_SKILL"
  else
    echo "Skipped Codex skill install: $SRC_SKILL/SKILL.md not found" >&2
  fi
fi

"$BIN_DIR/apple-triage" --json doctor
