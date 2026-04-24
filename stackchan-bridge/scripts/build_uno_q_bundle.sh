#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_NAME="stackchan-bridge-unoq-${STAMP}.tar.gz"
ARCHIVE_PATH="${DIST_DIR}/${ARCHIVE_NAME}"
LATEST_PATH="${DIST_DIR}/stackchan-bridge-unoq-latest.tar.gz"

mkdir -p "${DIST_DIR}"

tar \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude="__pycache__" \
  --exclude=".pytest_cache" \
  --exclude=".ruff_cache" \
  --exclude="dist" \
  --exclude="*.pyc" \
  -czf "${ARCHIVE_PATH}" \
  -C "$(dirname "${PROJECT_ROOT}")" \
  "$(basename "${PROJECT_ROOT}")"

ln -sf "${ARCHIVE_NAME}" "${LATEST_PATH}"

cat <<EOF
Built UNO Q deployment bundle:
  ${ARCHIVE_PATH}
  ${LATEST_PATH}

Transfer example:
  scp "${LATEST_PATH}" arduino@<uno-q-host>:/tmp/stackchan-bridge-unoq.tar.gz

Install example on the UNO Q:
  ssh arduino@<uno-q-host>
  cd /tmp
  tar -xzf stackchan-bridge-unoq.tar.gz
  cd stackchan-bridge
  sudo ./deploy/uno_q/install.sh --install-apt --with-systemd
EOF
