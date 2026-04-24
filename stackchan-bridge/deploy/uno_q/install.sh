#!/usr/bin/env bash
set -euo pipefail

PREFIX="/opt/stackchan-bridge"
SERVICE_USER="stackchan"
INSTALL_APT=false
WITH_SYSTEMD=false
ENABLE_SERVICES=false
START_SERVICES=false
ROVER_SERIAL_DEVICE=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

usage() {
  cat <<'EOF'
Install stackchan-bridge on Arduino UNO Q Linux / Debian.

Usage:
  sudo ./deploy/uno_q/install.sh [options]

Options:
  --prefix PATH              Install location. Default: /opt/stackchan-bridge
  --user NAME                Service user. Default: stackchan
  --install-apt              Install Debian apt prerequisites
  --with-systemd             Install systemd service units
  --enable-services          Enable installed services at boot
  --start-services           Start installed services after install
  --serial-device PATH       Set ROVER_SERIAL_DEVICE in the rover env file
  -h, --help                 Show this help

Notes:
  - This installer expects to run from an extracted stackchan-bridge bundle.
  - Python dependencies are installed into a venv under the prefix.
  - The default UNO Q router path is /var/run/arduino-router.sock.
EOF
}

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "error: this operation needs root; rerun with sudo" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      PREFIX="$2"
      shift 2
      ;;
    --user)
      SERVICE_USER="$2"
      shift 2
      ;;
    --install-apt)
      INSTALL_APT=true
      shift
      ;;
    --with-systemd)
      WITH_SYSTEMD=true
      shift
      ;;
    --enable-services)
      ENABLE_SERVICES=true
      WITH_SYSTEMD=true
      shift
      ;;
    --start-services)
      START_SERVICES=true
      WITH_SYSTEMD=true
      shift
      ;;
    --serial-device)
      ROVER_SERIAL_DEVICE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_root

APP_DIR="${PREFIX}/app"
VENV_DIR="${PREFIX}/venv"
ENV_DIR="/etc/stackchan-bridge"
SYSTEMD_DIR="/etc/systemd/system"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "debian" && "${ID_LIKE:-}" != *"debian"* ]]; then
    echo "warning: expected Debian-like OS, found ${PRETTY_NAME:-unknown}" >&2
  fi
  if [[ "${VERSION_CODENAME:-}" != "trixie" ]]; then
    echo "warning: expected Debian trixie; found codename '${VERSION_CODENAME:-unknown}'" >&2
  fi
fi

if [[ ! -f "${SOURCE_ROOT}/pyproject.toml" ]]; then
  echo "error: ${SOURCE_ROOT} does not look like the stackchan-bridge project root" >&2
  exit 1
fi

if [[ "${INSTALL_APT}" == "true" ]]; then
  apt-get update
  apt-get install -y \
    ca-certificates \
    build-essential \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${PREFIX}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

for group in dialout tty; do
  if getent group "${group}" >/dev/null 2>&1; then
    usermod -aG "${group}" "${SERVICE_USER}"
  fi
done

install -d -m 0755 "${PREFIX}"
rm -rf "${APP_DIR}"
install -d -m 0755 "${APP_DIR}"

tar \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude="__pycache__" \
  --exclude=".pytest_cache" \
  --exclude=".ruff_cache" \
  --exclude="dist" \
  --exclude="*.pyc" \
  -C "${SOURCE_ROOT}" \
  -cf - . | tar -C "${APP_DIR}" -xf -

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel
"${VENV_DIR}/bin/python" -m pip install "${APP_DIR}"

install -d -m 0755 "${ENV_DIR}"
install_env() {
  local src="$1"
  local dest="$2"
  if [[ -f "${dest}" ]]; then
    echo "keeping existing env file: ${dest}"
  else
    install -m 0644 "${src}" "${dest}"
  fi
}

install_env "${APP_DIR}/deploy/uno_q/env/stackchan-bridge.env" "${ENV_DIR}/stackchan-bridge.env"
install_env "${APP_DIR}/deploy/uno_q/env/stackchan-rover.env" "${ENV_DIR}/stackchan-rover.env"

set_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "${file}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${file}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${file}"
  fi
}

if [[ -n "${ROVER_SERIAL_DEVICE}" ]]; then
  set_env_key "${ENV_DIR}/stackchan-rover.env" "ROVER_SERIAL_DEVICE" "${ROVER_SERIAL_DEVICE}"
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${PREFIX}"

if [[ "${WITH_SYSTEMD}" == "true" ]]; then
  install -m 0644 "${APP_DIR}/deploy/uno_q/systemd/stackchan-bridge.service" "${SYSTEMD_DIR}/stackchan-bridge.service"
  install -m 0644 "${APP_DIR}/deploy/uno_q/systemd/stackchan-rover.service" "${SYSTEMD_DIR}/stackchan-rover.service"
  systemctl daemon-reload

  if [[ "${ENABLE_SERVICES}" == "true" ]]; then
    systemctl enable stackchan-bridge.service
    systemctl enable stackchan-rover.service
  fi

  if [[ "${START_SERVICES}" == "true" ]]; then
    systemctl start stackchan-bridge.service
    systemctl start stackchan-rover.service
  fi
fi

cat <<EOF
Installed stackchan-bridge:
  app:   ${APP_DIR}
  venv:  ${VENV_DIR}
  env:   ${ENV_DIR}

Useful checks:
  ${VENV_DIR}/bin/stackchan-rover-service --help
  ${VENV_DIR}/bin/python -c "from stackchan_bridge.server.app import create_app; print(create_app().title)"

Rover env:
  ${ENV_DIR}/stackchan-rover.env

Start manually:
  sudo systemctl start stackchan-rover.service
  sudo systemctl start stackchan-bridge.service
EOF
