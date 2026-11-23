#!/usr/bin/env bash
# Kept for compatibility: the portal is started from the repo root (one process, one port).
exec "$(cd "$(dirname "$0")/../.." && pwd)/start-portal.sh" "$@"
