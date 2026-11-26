#!/usr/bin/env bash
# Run Clearbuy's checks before saying a task is done (M1-10).
#
# The same checks as CI (.github/workflows/ci.yml), in CI's order:
#   The checks job:
#     1. uv lock --check
#     2. uv sync --locked
#     3. Ruff format (check only)
#     4. Ruff check
#     5. mypy
#     6. Export the locked dependencies, then pip-audit them
#     7. gitleaks over the whole history (the same image and digest as CI)
#   The arm-image job:
#     8. The tests through Docker Compose (the tests service, M1-17)
#     9. docker compose down, always
#
# Differences on the laptop, on purpose: the image is built for the laptop's
# own processor, so CI's ARM build and ARM check are left out; the tests get
# APP_ENV=local from compose.yaml (CI adds -e APP_ENV=ci); the laptop's own
# .env (with its role passwords) is used instead of CI's random ones.
#
# CI keeps its own steps. A change to this script or to ci.yml changes both
# in the same pull request (AGENTS.md).

set -euo pipefail

cd "$(dirname "$0")/.."

audit_file="$(mktemp)"

finish() {
  status=$?
  docker compose down || true
  rm -f "$audit_file"
  if [ "$status" -eq 0 ]; then
    echo "ALL CHECKS PASSED"
  else
    echo "CHECKS FAILED"
  fi
  exit "$status"
}
trap finish EXIT

uv lock --check
uv sync --locked
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy
uv export --frozen --format requirements-txt --no-emit-project -o "$audit_file"
uv run --frozen pip-audit --disable-pip -r "$audit_file"
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo" \
  ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  git --redact --verbose /repo
docker compose run --build --rm -e COVERAGE_FILE=/tmp/.coverage tests pytest
