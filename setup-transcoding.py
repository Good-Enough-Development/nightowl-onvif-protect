#!/usr/bin/env python3
import argparse, getpass, json, os, pathlib, re, secrets, uuid
from fractions import Fraction
from urllib.parse import quote

base = pathlib.Path(__file__).resolve().parent
os.umask(0o077)
parser = argparse.ArgumentParser(description='Configure NightOwl recorder streams.')
parser.add_argument('--host', help='Recorder hostname or address; prompted if omitted')
args = parser.parse_args()
host = args.host or input('NightOwl recorder hostname or address: ').strip()
if not host or not re.fullmatch(r'[A-Za-z0-9.-]+', host):
    parser.error('Enter a valid IPv4 address or DNS hostname.')
user = input('NightOwl NVR username [admin]: ').strip() or 'admin'
password = getpass.getpass('NightOwl NVR password (stored in a mode-600 service config): ')
print('Choose a NEW bridge password. Use username protect and this password when adopting the seven cameras.')
while True:
    protect_password = getpass.getpass('New Protect bridge password (at least 12 characters): ')
    again = getpass.getpass('Confirm bridge password: ')
    if len(protect_password) >= 12 and protect_password == again:
        break
    print('Passwords must match and contain at least 12 characters.')
worker = secrets.token_urlsafe(24)
existing_motion_by_mac = {}
if (base / 'config.yaml').exists():
    existing_motion_by_mac = {c['mac']: c.get('motion') for c in json.loads((base / 'config.yaml').read_text())['onvif']}
config = {
    'logLevel': 'warn', 'logDestinations': ['stdout'],
    'rtsp': True, 'rtspAddress': '127.0.0.1:8555', 'rtspTransports': ['tcp'],
    'rtspAuthMethods': ['basic', 'digest'],
    'rtmp': False, 'hls': False, 'webrtc': False, 'srt': False, 'moq': False,
    'api': False, 'metrics': False, 'pprof': False, 'playback': False,
    'authMethod': 'internal',
    'authInternalUsers': [
        {'user': 'protect', 'pass': protect_password, 'ips': [], 'permissions': [
            {'action': 'read', 'path': '~^camera[1-7](-low)?$'}]},
        {'user': 'transcoder', 'pass': worker, 'ips': ['127.0.0.1'], 'permissions': [
            {'action': 'read', 'path': '~^source[1-7]$'},
            {'action': 'publish', 'path': '~^camera[1-7](-low)?$'}]},
    ], 'paths': {},
}
onvif = {'onvif': []}
probes = json.loads((base / 'probe-results.json').read_text())
for ch in range(1, 8):
    source = f'rtsp://{quote(user, safe="")}:{quote(password, safe="")}@{host}:554/cam/realmonitor?channel={ch}&subtype=0'
    config['paths'][f'source{ch}'] = {'source': source, 'rtspTransport': 'tcp', 'sourceOnDemand': False}
    config['paths'][f'camera{ch}'] = {'source': 'publisher'}
    config['paths'][f'camera{ch}-low'] = {'source': 'publisher'}
    original = next(r for r in probes if r['channel'] == ch and r['subtype'] == 0)
    fps = max(1, round(float(Fraction(original['r_frame_rate']))))
    onvif['onvif'].append({
        'mac': f'02:00:00:00:01:{ch:02x}', 'ports': {'server': 8081, 'rtsp': 8554},
        'name': f'NightOwl Camera {ch}',
        'uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, f'rtsp://{host}/nightowl/channel/{ch}')),
        'highQuality': {'rtsp': f'/camera{ch}', 'width': original['width'], 'height': original['height'],
                        'framerate': fps, 'bitrate': 2500, 'quality': 4},
        'lowQuality': {'rtsp': f'/camera{ch}-low', 'width': 640, 'height': 360,
                       'framerate': fps, 'bitrate': 400, 'quality': 1},
        'snapshotFile': str(base / 'runtime' / f'camera{ch}.jpg'),
        'target': {'hostname': '127.0.0.1', 'ports': {'rtsp': 8555}},
    })
    if (base / 'motion_detector.py').exists():
        onvif['onvif'][-1]['motion'] = existing_motion_by_mac.get(onvif['onvif'][-1]['mac']) or {
            'channel': ch, 'stateFile': str(base/'runtime'/f'motion-camera{ch}.json'),
            'pixelThreshold': 20, 'minChangedPercent': 0.25, 'holdSeconds': 8, 'warmupSeconds': 10,
        }
for name, data in [('mediamtx.yml', config), ('config.yaml', onvif)]:
    path = base / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
(base / 'runtime').mkdir(mode=0o700, exist_ok=True)
print('Private service configuration saved. Adoption username: protect. Use the NEW bridge password you just chose.')
