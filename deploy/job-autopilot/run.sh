#!/usr/bin/env bash
set -eu
RUNNER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${JOBHUNT_ROOT:-$(cd -- "$RUNNER_DIR/../.." && pwd)}"
export JOBHUNT_RUNNER="${JOBHUNT_RUNNER:-$RUNNER_DIR}"
cd "$PROJECT_DIR"
exec "${JOBHUNT_PYTHON:-python3}" "$PROJECT_DIR/scripts/external_batch.py"
