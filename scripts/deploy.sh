#!/usr/bin/env bash
# Deploy Foundry on the VPS (Passenger + a2wsgi).
# Run from the app checkout on the server, e.g.:
#   cd ~/foundry && ./scripts/deploy.sh
#
# Env overrides:
#   FOUNDRY_DEPLOY_BRANCH   default: main
#   FOUNDRY_SKIP_PULL=1     skip git pull
#   FOUNDRY_SKIP_DEPS=1     skip pip install
#   FOUNDRY_SYSTEMD_UNIT    if set (e.g. foundry), restart via systemctl instead of Passenger
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${FOUNDRY_DEPLOY_BRANCH:-main}"
REMOTE="${FOUNDRY_DEPLOY_REMOTE:-origin}"

echo "==> Foundry deploy"
echo "    root:   $ROOT"
echo "    branch: $REMOTE/$BRANCH"

if [ "${FOUNDRY_SKIP_PULL:-0}" != "1" ]; then
  echo "==> git fetch / pull"
  git fetch "$REMOTE" "$BRANCH"
  BEFORE="$(git rev-parse --short HEAD)"
  git pull --ff-only "$REMOTE" "$BRANCH"
  AFTER="$(git rev-parse --short HEAD)"
  echo "    $BEFORE → $AFTER"
else
  echo "==> skip pull (FOUNDRY_SKIP_PULL=1)"
  AFTER="$(git rev-parse --short HEAD)"
fi

if [ "${FOUNDRY_SKIP_DEPS:-0}" != "1" ]; then
  echo "==> dependencies"
  if [ -x "$ROOT/venv/bin/pip" ]; then
    "$ROOT/venv/bin/pip" install -r backend/requirements.txt
  elif command -v pip3 >/dev/null 2>&1; then
    pip3 install -r backend/requirements.txt
  else
    echo "    warning: no venv/bin/pip or pip3; skipping dependency install" >&2
  fi
else
  echo "==> skip deps (FOUNDRY_SKIP_DEPS=1)"
fi

echo "==> restart app"
if [ -n "${FOUNDRY_SYSTEMD_UNIT:-}" ]; then
  sudo systemctl restart "$FOUNDRY_SYSTEMD_UNIT"
  sudo systemctl --no-pager --full status "$FOUNDRY_SYSTEMD_UNIT" | head -n 12 || true
elif [ -d "$ROOT/tmp" ] || mkdir -p "$ROOT/tmp"; then
  # Phusion Passenger: touching tmp/restart.txt reloads the app
  touch "$ROOT/tmp/restart.txt"
  echo "    touched $ROOT/tmp/restart.txt (Passenger)"
else
  echo "    error: could not create $ROOT/tmp for Passenger restart" >&2
  exit 1
fi

echo "==> done"
echo "    commit: $(git rev-parse --short HEAD) $(git log -1 --pretty=%s)"
echo "    tip:    migrations run automatically on next app start"
echo "    check:  https://foundry.perrinresearch.com/"
