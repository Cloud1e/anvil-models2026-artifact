#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODEL="${1:-gemini-3.1-pro-preview}"
TASK="${2:-both}"
OUTPUT_ROOT="$REPO_ROOT/RQ1_Generation/outputs"

cd "$REPO_ROOT"

case "$TASK" in
  english|e2a)
    mvn -q compile exec:java \
      -Dexec.mainClass=Example \
      -Dexec.args="rq1-process-english RQ1_Generation/outputs/E2A/$MODEL"
    ;;
  alloy|a2a)
    mvn -q compile exec:java \
      -Dexec.mainClass=Example \
      -Dexec.args="rq1-process-alloy RQ1_Generation/outputs/A2A/$MODEL"
    ;;
  both)
    mvn -q compile exec:java \
      -Dexec.mainClass=Example \
      -Dexec.args="rq1-process-english RQ1_Generation/outputs/E2A/$MODEL"
    mvn -q compile exec:java \
      -Dexec.mainClass=Example \
      -Dexec.args="rq1-process-alloy RQ1_Generation/outputs/A2A/$MODEL"
    ;;
  *)
    echo "Usage: $0 [gemini-model] [english|alloy|both]" >&2
    echo "Available outputs are under: $OUTPUT_ROOT/{E2A,A2A}/" >&2
    exit 2
    ;;
esac
