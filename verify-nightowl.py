#!/usr/bin/env python3
import concurrent.futures, json, pathlib, subprocess
from urllib.parse import quote

base = pathlib.Path(__file__).resolve().parent
cfg = json.loads((base / 'mediamtx.yml').read_text())
reader = next(u for u in cfg['authInternalUsers'] if u['user'] == 'protect')
def probe(path):
    uri = f'rtsp://protect:{quote(reader["pass"], safe="")}@127.0.0.1:8555/{path}'
    try:
        result = subprocess.run([
            '/usr/bin/ffprobe', '-v', 'error', '-rtsp_transport', 'tcp',
            '-rw_timeout', '5000000', '-analyzeduration', '1000000', '-probesize', '1000000',
            '-read_intervals', '%+4', '-count_frames', '-select_streams', 'v:0', '-show_entries',
            'stream=codec_name,width,height,r_frame_rate,profile,nb_read_frames:frame=best_effort_timestamp_time', '-of', 'json', uri,
        ], capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout or '{}')
        stream = data.get('streams', [])
        times = [float(f['best_effort_timestamp_time']) for f in data.get('frames', []) if 'best_effort_timestamp_time' in f]
        span = max(times)-min(times) if len(times)>1 else 0
        return {'path': path, 'ok': bool(stream), 'streams': stream, 'decodedTimeSpanSeconds':round(span,3)}
    except (ValueError, subprocess.TimeoutExpired):
        return {'path': path, 'ok': False}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(probe, [f'camera{ch}{suffix}' for ch in range(1, 8) for suffix in ('', '-low')]))
print(json.dumps(results, indent=2))
assert all(r['ok'] and r['streams'][0]['codec_name'] == 'h264' and int(r['streams'][0].get('nb_read_frames', 0)) >= 8 and r['decodedTimeSpanSeconds'] >= 1 for r in results), 'Missing live H.264 stream'
