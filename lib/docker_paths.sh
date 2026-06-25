#!/usr/bin/env bash
# Shared helpers: repo is bind-mounted at /workspace in docker-compose.arepair.
# Usage (after cd to repo root):
#   # shellcheck disable=SC1091
#   source "$REPO_ROOT/scripts/lib/docker_paths.sh"

# If path is under repo root, return path relative to repo; else return unchanged.
repo_relpath() {
  local root="${1:?repo root}"
  local p="${2:?path}"
  case "$p" in
    "$root"/*) printf '%s\n' "${p#"$root"/}" ;;
    *) printf '%s\n' "$p" ;;
  esac
}

# Host path -> /workspace/<rel> for docker-compose -e REPAIR_INFO_JSON / OUTPUT_DIR.
host_to_workspace() {
  local root="${1:?repo root}"
  local p="${2:?path}"
  case "$p" in
    "$root"/*) printf '/workspace/%s\n' "${p#"$root"/}" ;;
    /*)
      echo "ERROR: path outside repo root: $p" >&2
      return 1
      ;;
    *) printf '/workspace/%s\n' "$p" ;;
  esac
}

# In-container: normalize OUT_ROOT / INFO_ROOT from argv (reject bare host absolutes).
# Usage: docker_normalize_repo_rel OUT_ROOT
docker_normalize_repo_rel() {
  local var_name="${1:?}"
  local o
  eval "o=\${$var_name:-}"
  [[ -z "$o" ]] && return 0
  case "$o" in
    /workspace/*)
      eval "$var_name=\"\${o#/workspace/}\""
      ;;
    /*)
      echo "ERROR: --out-root must be repo-relative (e.g. result/...) or /workspace/result/..., not host path: $o" >&2
      return 1
      ;;
  esac
}
