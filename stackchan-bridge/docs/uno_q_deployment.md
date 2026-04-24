# UNO Q Debian Deployment

This packages `stackchan-bridge` for transfer to the Arduino UNO Q Linux side.

The target assumption is Debian/Trixie or a close Debian-like image on the UNO Q. The installer uses a normal Python virtual environment under `/opt/stackchan-bridge` and optional systemd units.

## Build The Transfer Bundle

On your Mac or development machine:

```bash
cd /Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge
./scripts/build_uno_q_bundle.sh
```

The script writes a tarball under `dist/`, for example:

```text
dist/stackchan-bridge-unoq-YYYYMMDD-HHMMSS.tar.gz
dist/stackchan-bridge-unoq-latest.tar.gz
```

Transfer it to the UNO Q:

```bash
scp dist/stackchan-bridge-unoq-latest.tar.gz arduino@<uno-q-host>:/tmp/stackchan-bridge-unoq.tar.gz
```

## Install On The UNO Q

SSH into the UNO Q:

```bash
ssh arduino@<uno-q-host>
cd /tmp
tar -xzf stackchan-bridge-unoq.tar.gz
cd stackchan-bridge
sudo ./deploy/uno_q/install.sh --install-apt --with-systemd
```

If your StackChan UART appears somewhere other than `/dev/ttyS0`, pass it during install:

```bash
sudo ./deploy/uno_q/install.sh \
  --install-apt \
  --with-systemd \
  --serial-device /dev/ttyAMA0
```

The installer writes:

- app files: `/opt/stackchan-bridge/app`
- Python venv: `/opt/stackchan-bridge/venv`
- env files: `/etc/stackchan-bridge`
- optional units: `/etc/systemd/system/stackchan-bridge.service` and `/etc/systemd/system/stackchan-rover.service`

## Configure

Rover UART service config:

```bash
sudo nano /etc/stackchan-bridge/stackchan-rover.env
```

Important values:

```bash
ROVER_SERIAL_DEVICE=/dev/ttyS0
ROVER_BAUDRATE=115200
ROVER_RPC_SOCKET_PATH=/var/run/arduino-router.sock
ROVER_ADMIN_SOCKET=/run/stackchan-bridge/rover-admin.sock
```

Bridge API config:

```bash
sudo nano /etc/stackchan-bridge/stackchan-bridge.env
```

For hardware bring-up, keep cloud and model integrations disabled or pointed at local services. The rover service can be tested independently from the FastAPI bridge.

## Start Services

Start only the rover UART service first:

```bash
sudo systemctl start stackchan-rover.service
sudo systemctl status stackchan-rover.service --no-pager
```

Follow logs:

```bash
journalctl -u stackchan-rover.service -f
```

Enable services after the serial path and router socket are confirmed:

```bash
sudo systemctl enable stackchan-rover.service
sudo systemctl enable stackchan-bridge.service
```

Start the FastAPI bridge when you want websocket and agent tooling on the UNO Q:

```bash
sudo systemctl start stackchan-bridge.service
curl http://127.0.0.1:8000/healthz
```

## Manual Run Without Systemd

This is useful while finding the correct UART path:

```bash
sudo /opt/stackchan-bridge/venv/bin/stackchan-rover-service serve \
  --serial-device /dev/ttyS0 \
  --baudrate 115200 \
  --rpc-socket /var/run/arduino-router.sock
```

Send admin commands to a running service:

```bash
/opt/stackchan-bridge/venv/bin/stackchan-rover-service admin loop-status \
  --admin-socket /run/stackchan-bridge/rover-admin.sock
```

## First Checks

1. Confirm the Arduino router socket exists:

```bash
ls -l /var/run/arduino-router.sock
```

2. Confirm the StackChan UART device exists:

```bash
ls -l /dev/ttyS* /dev/ttyAMA* /dev/ttyUSB* 2>/dev/null
```

3. Keep motor power disconnected for the first service start.

4. Start the rover service and watch logs.

5. Send `PING` and `STATUS` from StackChan or a serial terminal before any motion command.

## Notes

- If the router socket is not ready when the service starts, the rover service will fail and systemd will retry according to the unit restart policy.
- The default service user is `stackchan`, added to `dialout` and `tty` if those groups exist.
- If the router socket is not readable by that user on your image, either adjust socket permissions/groups or temporarily run the service manually with `sudo` while debugging.
- The L298N motor rail should stay separate from the UNO Q power path, with common ground shared.
