import argparse, json, pathlib, urllib.request, xml.etree.ElementTree as ET

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


def soap(ip,service,operation,args='',query=''):
    ns='http://www.onvif.org/ver10/'+('events' if service=='events' else 'device')+'/wsdl'
    body=f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:t="{ns}"><s:Header/><s:Body><t:{operation}>{args}</t:{operation}></s:Body></s:Envelope>'
    request=urllib.request.Request(f'http://{ip}:8081/onvif/{service}_service{query}',data=body.encode(),headers={'Content-Type':'application/soap+xml'})
    return ET.fromstring(urllib.request.urlopen(request,timeout=5).read())

results=[]
for ch, ip in targets:
    cap=soap(ip,'device','GetCapabilities','<t:Category>All</t:Category>')
    event_cap=next(e for e in cap.iter() if e.tag.endswith('}Events'))
    assert any(e.tag.endswith('}XAddr') and e.text==f'http://{ip}:8081/onvif/events_service' for e in event_cap.iter())
    assert any(e.tag.endswith('}WSPullPointSupport') and e.text=='true' for e in event_cap.iter())
    properties=soap(ip,'events','GetEventProperties')
    assert any(e.attrib.get('Name')=='IsMotion' and e.attrib.get('Type')=='xs:boolean' for e in properties.iter())
    created=soap(ip,'events','CreatePullPointSubscription','<t:InitialTerminationTime>PT1M</t:InitialTerminationTime>')
    address=next(e.text for e in created.iter() if e.tag.endswith('}Address'))
    query=address[address.index('?'):]
    try:
        initial=soap(ip,'events','PullMessages','<t:Timeout>PT0S</t:Timeout><t:MessageLimit>10</t:MessageLimit>',query)
        source=[e.attrib for e in initial.iter() if e.attrib.get('Name')=='VideoSourceConfigurationToken']
        assert source[0]['Value']=='video_src_config_token'
        state=next(e.attrib['Value'] for e in initial.iter() if e.attrib.get('Name')=='IsMotion')
        results.append({'channel':ch,'eventsAdvertised':True,'motionProperty':True,'subscriptionWorks':True,'currentMotion':state})
    finally:
        soap(ip,'events','Unsubscribe','',query)
print(json.dumps(results,indent=2))
