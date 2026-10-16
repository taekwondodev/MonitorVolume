#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
    test | check | ipa) exec /usr/bin/python3 "$SCRIPT_DIR/app_tool.py" "ios-$1" ;;
    *) echo "usage: $0 test|check|ipa" >&2; exit 64 ;;
esac
