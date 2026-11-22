#!/usr/bin/env python3
import json, pathlib, shutil, signal, subprocess, time

base = pathlib.Path(__file__).resolve().parent
running, child = True, None
def addresses():
    result = {}
    state = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show']))
    for ch in range(1, 8):
        name = f'onvifcam{ch}'
        nic = next((n for n in state if n['ifname'] == name), {})
        ip = next((a['local'] for a in nic.get('addr_info', []) if a['family'] == 'inet' and a.get('scope') == 'global'), None)
        if ip:
            result[ch] = ip
    return result
def stop(*_):
    global running
    running = False
    if child and child.poll() is None:
        child.terminate()
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while running:
    state = addresses()
    if len(state) != 7:
        time.sleep(2)
        continue
    (base / 'runtime' / 'camera-addresses.json').write_text(json.dumps(state, indent=2) + '\n')
    print(f'Starting ONVIF endpoints: {state}', flush=True)
    child = subprocess.Popen([shutil.which('node') or 'node', 'main.js', 'config.yaml'], cwd=base)
    while running and child.poll() is None:
        time.sleep(2)
        if addresses() != state:
            print('Camera DHCP address changed; restarting ONVIF endpoints.', flush=True)
            child.terminate()
            break
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
    if running:
        time.sleep(3)
