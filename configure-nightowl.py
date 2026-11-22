#!/usr/bin/env python3
import argparse
import re
import concurrent.futures
import getpass
import json
import pathlib
import subprocess
import uuid
from fractions import Fraction
from urllib.parse import quote

base = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Configure NightOwl recorder streams.')
parser.add_argument('--host', help='Recorder hostname or address; prompted if omitted')
args = parser.parse_args()
host = args.host or input('NightOwl recorder hostname or address: ').strip()
if not host or not re.fullmatch(r'[A-Za-z0-9.-]+', host):
    parser.error('Enter a valid IPv4 address or DNS hostname.')
user = input('NightOwl NVR username [admin]: ').strip() or 'admin'
password = getpass.getpass('NightOwl NVR password (hidden, never saved): ')

def probe(channel, subtype):
    path = f'/cam/realmonitor?channel={channel}&subtype={subtype}'
    uri = f'rtsp://{quote(user, safe="")}:{quote(password, safe="")}@{host}:554{path}'
    try:
        p = subprocess.run([
            '/usr/bin/ffprobe', '-v', 'error', '-rtsp_transport', 'tcp',
            '-rw_timeout', '5000000', '-analyzeduration', '2000000',
            '-probesize', '2000000', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,width,height,r_frame_rate,bit_rate',
            '-of', 'json', uri,
        ], capture_output=True, text=True, timeout=18)
        streams = json.loads(p.stdout or '{}').get('streams', [])
        if not streams:
            # Do not save ffprobe errors: they can contain the credential-bearing URL.
            print(f'Channel {channel}, subtype {subtype}: no video returned (exit {p.returncode})', flush=True)
            return {'channel': channel, 'subtype': subtype, 'ok': False}
        stream = streams[0]
        print(f'Channel {channel}, subtype {subtype}: {stream}', flush=True)
        return {'channel': channel, 'subtype': subtype, 'ok': True, **stream}
    except (subprocess.TimeoutExpired, ValueError):
        print(f'Channel {channel}, subtype {subtype}: probe timed out or returned invalid metadata', flush=True)
        return {'channel': channel, 'subtype': subtype, 'ok': False}

results = []
# Limit to two sessions to avoid overwhelming the NVR.
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    jobs = [pool.submit(probe, ch, sub) for ch in range(1, 8) for sub in (0, 1)]
    for job in jobs:
        results.append(job.result())
password = None
(base / 'probe-results.json').write_text(json.dumps(results, indent=2) + '\n')
by_key = {(r['channel'], r['subtype']): r for r in results}
bad = [r for r in results if r['subtype'] == 0 and (not r['ok'] or r.get('codec_name') != 'h264')]
if bad:
    print('Some main streams are unavailable or are not H.264. Results saved without credentials; review them before configuring transcoding.')
    raise SystemExit(2)

def quality(ch, sub, r):
    try:
        fps = round(float(Fraction(r.get('r_frame_rate', '15/1'))))
    except (ValueError, ZeroDivisionError):
        fps = 15
    return {
        'rtsp': f'/cam/realmonitor?channel={ch}&subtype={sub}',
        'width': r['width'], 'height': r['height'], 'framerate': max(fps, 1),
        'bitrate': max(int(r.get('bit_rate', 0)) // 1000, 1) if r.get('bit_rate') else (4096 if sub == 0 else 512),
        'quality': 4 if sub == 0 else 1,
    }

config = {'onvif': []}
for ch in range(1, 8):
    hi = by_key[ch, 0]
    lo = by_key[ch, 1]
    low_sub = 1 if lo['ok'] and lo.get('codec_name') == 'h264' else 0
    config['onvif'].append({
        'mac': f'02:00:00:00:01:{ch:02x}',
        'ports': {'server': 8081, 'rtsp': 8554},
        'name': f'NightOwl Camera {ch}',
        'uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, f'rtsp://{host}/nightowl/channel/{ch}')),
        'highQuality': quality(ch, 0, hi),
        'lowQuality': quality(ch, low_sub, lo if low_sub == 1 else hi),
        'target': {'hostname': host, 'ports': {'rtsp': 554}},
    })
(base / 'config.yaml').write_text(json.dumps(config, indent=2) + '\n')
print('Seven-camera config.yaml created. No passwords were saved.')
