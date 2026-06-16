#!/bin/sh
set -eu

PREFIX="${PREFIX:-$HOME/.local}"
REMOVE_SKILL=0

usage() {
  cat <<'EOF'
Usage: ./uninstall.sh [--prefix PATH] [--skill]

Removes the apple-triage wrapper. Pass --skill to also remove the installed Codex skill.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      [ "$#" -ge 2 ] || { echo "--prefix requires a path" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    --skill)
      REMOVE_SKILL=1
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

rm -f "$PREFIX/bin/apple-triage"
echo "Removed $PREFIX/bin/apple-triage"

if [ "$REMOVE_SKILL" -eq 1 ]; then
  CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
  rm -rf "$CODEX_HOME_DIR/skills/apple-triage"
  echo "Removed $CODEX_HOME_DIR/skills/apple-triage"
fi
