#!/usr/bin/env python3
"""Own only the seven named camera interfaces and their source routing tables."""
import ipaddress, json, os, pathlib, signal, subprocess, time

PARENT = os.environ['NIGHTOWL_PARENT_INTERFACE']
GATEWAY = str(ipaddress.IPv4Address(os.environ['NIGHTOWL_GATEWAY']))
running = True
def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)
def interfaces():
    links = {r['ifname']: r for r in json.loads(run('ip', '-j', 'link', 'show').stdout)}
    for r in json.loads(run('ip', '-j', '-4', 'addr', 'show').stdout):
        links[r['ifname']].update(r)
    return links
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
saved = {}
for key, value in [('arp_ignore', '1'), ('arp_announce', '2')]:
    path = pathlib.Path(f'/proc/sys/net/ipv4/conf/{PARENT}/{key}')
    saved[path] = path.read_text()
    path.write_text(value)
current = {}
try:
    for ch in range(1, 8):
        name, mac = f'onvifcam{ch}', f'02:00:00:00:01:{ch:02x}'
        old = interfaces().get(name)
        if old and old.get('address', '').lower() != mac:
            raise RuntimeError(f'{name} already belongs to another device')
        if not old:
            run('ip', 'link', 'add', name, 'link', PARENT, 'address', mac, 'type', 'macvlan', 'mode', 'bridge')
        # A camera interface must answer ARP only for its own address.
        for key, value in [('arp_ignore', '1'), ('arp_announce', '2')]:
            pathlib.Path(f'/proc/sys/net/ipv4/conf/{name}/{key}').write_text(value)
        run('ip', 'link', 'set', name, 'up')
    run('networkctl', 'reload')
    while running:
        state = interfaces()
        for ch in range(1, 8):
            name, table, pref = f'onvifcam{ch}', str(10000 + ch), str(1000 + ch)
            addresses = state.get(name, {}).get('addr_info', [])
            a = next((a for a in addresses if a['family'] == 'inet' and a.get('scope') == 'global'), None)
            ip = a['local'] if a else None
            if current.get(ch) == ip:
                continue
            if ch in current:
                run('ip', 'rule', 'del', 'pref', pref, check=False)
                run('ip', 'route', 'flush', 'table', table, check=False)
            current[ch] = ip
            if ip:
                subnet = str(ipaddress.ip_network(f'{ip}/{a["prefixlen"]}', strict=False))
                run('ip', 'route', 'replace', 'table', table, subnet, 'dev', name, 'src', ip)
                run('ip', 'route', 'replace', 'table', table, 'default', 'via', GATEWAY, 'dev', name)
                run('ip', 'rule', 'add', 'pref', pref, 'from', ip + '/32', 'table', table)
                print(f'{name} {ip} MAC 02:00:00:00:01:{ch:02x}', flush=True)
        time.sleep(2)
finally:
    for ch in range(1, 8):
        run('ip', 'rule', 'del', 'pref', str(1000 + ch), check=False)
        run('ip', 'route', 'flush', 'table', str(10000 + ch), check=False)
        name = f'onvifcam{ch}'
        entry = interfaces().get(name)
        if entry and entry.get('address', '').lower() == f'02:00:00:00:01:{ch:02x}':
            run('ip', 'link', 'del', name, check=False)
    for path, value in saved.items():
        path.write_text(value)
