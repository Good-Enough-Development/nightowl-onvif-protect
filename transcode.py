#!/usr/bin/env python3
import json, pathlib, re, signal, subprocess, sys, threading
from urllib.parse import quote
from motion_detector import MotionDetector

base = pathlib.Path(__file__).resolve().parent
ch = int(sys.argv[1])
assert 1 <= ch <= 7
cfg = json.loads((base / 'mediamtx.yml').read_text())
worker = next(u for u in cfg['authInternalUsers'] if u['user'] == 'transcoder')
url = f'rtsp://transcoder:{quote(worker["pass"], safe="")}@127.0.0.1:8555/'
cam = json.loads((base / 'config.yaml').read_text())['onvif'][ch - 1]
fps = cam['highQuality']['framerate']
args = ['/usr/bin/ffmpeg', '-y', '-nostdin', '-hide_banner', '-loglevel', 'warning',
        '-rtsp_transport', 'tcp', '-timeout', '15000000', '-threads', '2',
        '-i', url + f'source{ch}', '-filter_threads', '1']
for low in (False, True):
    args += ['-map', '0:v:0', '-an']
    if low:
        args += ['-vf', 'scale=640:360']
    if low:
        args += ['-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
                 '-keyint_min', str(2 * fps), '-sc_threshold', '0', '-threads', '1']
    else:
        args += ['-c:v', 'h264_nvenc', '-preset', 'p4', '-tune', 'll', '-rc', 'vbr', '-bf', '0']
    args += ['-pix_fmt', 'yuv420p', '-profile:v', 'main', '-r', str(fps),
             '-g', str(2 * fps), '-b:v', '400k' if low else '2500k',
             '-maxrate', '500k' if low else '3000k', '-bufsize', '800k' if low else '5000k',
             '-f', 'rtsp', '-rtsp_transport', 'tcp', url + f'camera{ch}' + ('-low' if low else '')]
args += ['-map', '0:v:0', '-an', '-vf', 'scale=640:360,fps=1/5', '-threads', '1',
         '-q:v', '5', '-update', '1', '-atomic_writing', '1', '-f', 'image2',
         str(base / 'runtime' / f'camera{ch}.jpg')]
args += ['-map','0:v:0','-an','-vf','scale=320:180,fps=3,format=gray',
         '-c:v','rawvideo','-pix_fmt','gray','-threads','1','-f','rawvideo','pipe:1']
p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
signal.signal(signal.SIGTERM, lambda *_: p.terminate())
signal.signal(signal.SIGINT, lambda *_: p.terminate())
def errors():
    for raw in p.stderr:
        # Never write URI credentials into the journal.
        line=raw.decode(errors='replace').rstrip()
        print(re.sub(r'rtsp://[^\s]+', 'rtsp://[redacted]', line), flush=True)
threading.Thread(target=errors,daemon=True).start()
motion=cam.get('motion',{})
detector=MotionDetector(ch, motion.get('stateFile',base/'runtime'/f'motion-camera{ch}.json'), options=motion)
frame_size=MotionDetector.WIDTH*MotionDetector.HEIGHT
try:
    while True:
        frame=bytearray()
        while len(frame)<frame_size:
            data=p.stdout.read(frame_size-len(frame))
            if not data:
                break
            frame.extend(data)
        if len(frame)!=frame_size:
            break
        detector.feed(frame)
finally:
    detector.stopped()
    if p.poll() is None:
        p.terminate()
raise SystemExit(p.wait())
