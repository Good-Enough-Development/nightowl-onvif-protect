import json, socket, time, uuid, xml.etree.ElementTree as ET
ident = str(uuid.uuid4())
probe = f'''<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><s:Header><a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action><a:MessageID>uuid:{ident}</a:MessageID><a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To></s:Header><s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body></s:Envelope>'''.encode()
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    s.bind(('', 0))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    found = {}
    for _ in range(2):
        s.sendto(probe, ('239.255.255.250', 3702))
        until = time.monotonic() + 3
        while time.monotonic() < until:
            try:
                data, addr = s.recvfrom(65535)
                root = ET.fromstring(data)
                xaddr = root.find('.//{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs')
                endpoint = root.find('.//{http://schemas.xmlsoap.org/ws/2004/08/addressing}Address')
                if xaddr is not None:
                    found[xaddr.text.strip()] = {'source': addr[0], 'uuid': endpoint.text if endpoint is not None else None}
            except (socket.timeout, ET.ParseError):
                pass
print(json.dumps(found, indent=2))
