import argparse, json, pathlib, socket, urllib.request, xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description='Check virtual ONVIF camera endpoints.')
parser.add_argument('addresses', nargs='*', help='Camera addresses in channel order')
parser.add_argument('--addresses-file', type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parents[1] / 'runtime' / 'camera-addresses.json',
                    help='JSON channel-to-address map (defaults to local runtime state)')
args = parser.parse_args()
if args.addresses:
    targets = list(enumerate(args.addresses, 1))
else:
    try:
        targets = sorted((int(ch), address) for ch, address in json.loads(args.addresses_file.read_text()).items())
    except (OSError, ValueError, AttributeError) as error:
        parser.error('Supply camera addresses or an existing --addresses-file: ' + str(error))
if not targets:
    parser.error('No camera addresses were supplied.')


def soap(ip, service, body):
    data = ('<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:d="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:m="http://www.onvif.org/ver10/media/wsdl"><s:Body>' + body + '</s:Body></s:Envelope>').encode()
    req = urllib.request.Request(f'http://{ip}:8081/onvif/{service}_service', data=data,
                                 headers={'Content-Type': 'application/soap+xml; charset=utf-8'})
    return ET.fromstring(urllib.request.urlopen(req, timeout=5).read())

rows = []
for ch, ip in targets:
    info = soap(ip, 'device', '<d:GetDeviceInformation/>')
    profiles = soap(ip, 'media', '<m:GetProfiles/>')
    uris = []
    for token in ('main_stream', 'sub_stream'):
        stream = soap(ip, 'media', '<m:GetStreamUri><m:StreamSetup><m:Stream>RTP-Unicast</m:Stream>'
                      '<m:Transport><m:Protocol>RTSP</m:Protocol></m:Transport></m:StreamSetup>'
                      f'<m:ProfileToken>{token}</m:ProfileToken></m:GetStreamUri>')
        uris.append(next(e.text for e in stream.iter() if e.tag.endswith('}Uri')))
    with urllib.request.urlopen(f'http://{ip}:8081/snapshot.jpg', timeout=5) as response:
        image = response.read()
        assert response.headers.get('Content-Type') == 'image/jpeg' and image[:2] == b'\xff\xd8'
    with socket.create_connection((ip, 8554), timeout=5) as s:
        s.sendall(f'DESCRIBE rtsp://{ip}:8554/camera{ch} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n'.encode())
        rtsp = s.recv(4096).decode()
        assert '401 Unauthorized' in rtsp, rtsp
    rows.append({'channel': ch, 'ip': ip, 'uris': uris, 'profiles': len([e for e in profiles.iter() if e.tag.endswith('}Profiles')]),
                 'snapshot_bytes': len(image), 'rtsp_requires_auth': True,
                 'serial': next(e.text for e in info.iter() if e.tag.endswith('}SerialNumber'))})
    assert uris == [f'rtsp://{ip}:8554/camera{ch}', f'rtsp://{ip}:8554/camera{ch}-low']
    assert rows[-1]['profiles'] == 2
print(json.dumps(rows, indent=2))
