#!/usr/bin/env bash
set -euo pipefail
base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
stage="$base/deployment"
test "$(id -u)" = 0 || { echo 'Run with sudo.'; exit 1; }
test -s "$base/mediamtx.yml"
test -s "$base/config.yaml"
service_user=${NIGHTOWL_SERVICE_USER:-nightowl}
service_group=$(id -gn "$service_user")
test "$service_user" != root || { echo 'Choose an unprivileged service account.'; exit 1; }
settings="$stage/network.env"
test -s "$settings" || { echo 'Copy deployment/network.example.env to deployment/network.env and configure it first.'; exit 1; }
set -a
# This is a trusted, administrator-reviewed shell environment file.
source "$settings"
set +a
python3 - "$base" "$service_user" "$service_group" <<'PY'
import ipaddress, os, re, sys
if not re.fullmatch(r'/[A-Za-z0-9_./-]+', sys.argv[1]):
    raise SystemExit('Use an installation directory without spaces or shell metacharacters.')
for account in sys.argv[2:]:
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', account):
        raise SystemExit('Unsupported service account or group name.')
parent = os.environ.get('NIGHTOWL_PARENT_INTERFACE', '')
if not re.fullmatch(r'[A-Za-z0-9_.-]{1,15}', parent):
    raise SystemExit('Set NIGHTOWL_PARENT_INTERFACE to the LAN interface name.')
gateway = ipaddress.IPv4Address(os.environ['NIGHTOWL_GATEWAY'])
lan = ipaddress.IPv4Network(os.environ['NIGHTOWL_LAN_CIDR'], strict=True)
if gateway not in lan:
    raise SystemExit('The gateway must belong to NIGHTOWL_LAN_CIDR.')
if gateway in ipaddress.IPv4Network('192.0.2.0/24'):
    raise SystemExit('Replace the documentation-only network settings before installing.')
PY
ip link show "$NIGHTOWL_PARENT_INTERFACE" >/dev/null
test -s "$base/bin/mediamtx"
install -d -o "$service_user" -g "$service_group" -m 700 "$base/runtime"
if test ! -e /etc/nightowl-onvif-installed; then
  for ch in {1..7}; do
    if ip link show "onvifcam$ch" >/dev/null 2>&1; then echo "Interface onvifcam$ch already exists; refusing to replace it"; exit 1; fi
    if ip rule show | awk -v p="$((1000+ch)):" '$1==p {found=1} END {exit !found}'; then echo 'Routing priority already used'; exit 1; fi
    if test -n "$(ip route show table "$((10000+ch))" 2>/dev/null || true)"; then echo 'Routing table already used'; exit 1; fi
  done
  for name in nightowl-onvif-network nightowl-onvif nightowl-mediamtx 'nightowl-transcode@'; do
    test ! -e "/etc/systemd/system/$name.service" || { echo "Unit $name already exists"; exit 1; }
  done
fi
install -d -m 755 /usr/local/libexec
install -m 755 "$stage/network-service.py" /usr/local/libexec/nightowl-onvif-network.py
install -m 755 "$base/bin/mediamtx" /usr/local/bin/nightowl-mediamtx
for ch in {1..7}; do
  cat > "/etc/systemd/network/20-nightowl-onvif-$ch.network" <<EOF
[Match]
Name=onvifcam$ch
[Link]
RequiredForOnline=no
[Network]
DHCP=ipv4
LinkLocalAddressing=no
IPv6AcceptRA=no
LLMNR=no
MulticastDNS=no
[DHCPv4]
ClientIdentifier=mac
Hostname=nightowl-camera-$ch
UseRoutes=no
UseGateway=no
UseDNS=no
UseNTP=no
UseHostname=no
EOF
done
install -m 600 "$settings" /etc/nightowl-onvif.env
python3 - "$stage" "$base" "$service_user" "$service_group" <<'PY'
import pathlib, sys
stage, base, user, group = sys.argv[1:]
for template in pathlib.Path(stage).glob('*.service'):
    text = template.read_text().replace('/opt/nightowl-onvif', base)
    text = text.replace('User=nightowl', 'User=' + user).replace('Group=nightowl', 'Group=' + group)
    destination = pathlib.Path('/etc/systemd/system') / template.name
    destination.write_text(text)
    destination.chmod(0o644)
PY
if command -v ufw >/dev/null && ufw status | head -1 | grep -q 'Status: active'; then
  for ch in {1..7}; do
    ufw allow in on "onvifcam$ch" proto tcp from "$NIGHTOWL_LAN_CIDR" to any port 8081,8554 comment 'NightOwl ONVIF bridge'
    ufw allow in on "onvifcam$ch" proto udp from "$NIGHTOWL_LAN_CIDR" to any port 3702 comment 'NightOwl discovery'
  done
fi
touch /etc/nightowl-onvif-installed
systemctl daemon-reload
systemctl enable --now nightowl-onvif-network.service nightowl-mediamtx.service
for ch in {1..7}; do systemctl enable --now "nightowl-transcode@$ch.service"; done
systemctl enable --now nightowl-onvif.service
echo 'Service installation complete. Waiting for DHCP leases and video startup...'
sleep 12
systemctl --no-pager --plain is-active nightowl-onvif-network.service nightowl-mediamtx.service nightowl-onvif.service
ip -br -4 addr show | grep onvifcam || true
