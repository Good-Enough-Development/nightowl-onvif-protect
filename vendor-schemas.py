#!/usr/bin/env python3
"""Cache official WSDL/XSD imports and replace only import/include locations."""
import hashlib, json, os, pathlib, re, urllib.parse, urllib.request
base = pathlib.Path(__file__).resolve().parent / 'wsdl'
cache = base / 'vendor'
cache.mkdir(exist_ok=True)
seen = {}
manifest = []
tag_pattern = re.compile(r'<(?:[\w.-]+:)?(?:import|include|redefine)\b[^>]*>', re.I)
attr_pattern = re.compile(r'(\b(?:schemaLocation|location)\s*=\s*)([\'\"])(.*?)(\2)', re.I)

def fetch(url):
    # The official schema servers also support HTTPS for older HTTP references.
    url = re.sub(r'^http:', 'https:', url)
    if url in seen:
        return seen[url]
    parsed = urllib.parse.urlparse(url)
    assert parsed.hostname in ('www.onvif.org', 'onvif.org', 'www.w3.org', 'schemas.xmlsoap.org', 'docs.oasis-open.org'), url
    dest = cache / (hashlib.sha256(url.encode()).hexdigest()[:16] + pathlib.PurePosixPath(parsed.path).suffix)
    seen[url] = dest
    request = urllib.request.Request(url, headers={'User-Agent': 'ONVIF-local-schema-cache/1.0'})
    raw = urllib.request.urlopen(request, timeout=30).read()
    text = raw.decode('utf-8-sig')
    assert '<' in text and ('schema' in text or 'definitions' in text), url
    def tag_repl(match):
        def attr_repl(a):
            target = urllib.parse.urljoin(url, a.group(3))
            local = fetch(target)
            return a.group(1) + a.group(2) + pathlib.Path(os.path.relpath(local, dest.parent)).as_posix() + a.group(2)
        return attr_pattern.sub(attr_repl, match.group(0))
    text = tag_pattern.sub(tag_repl, text)
    dest.write_text(text)
    manifest.append({'url': url, 'file': dest.name, 'download_sha256': hashlib.sha256(raw).hexdigest()})
    print('Cached official schema:', url, flush=True)
    return dest

for filename in ('device_service.wsdl', 'media_service.wsdl'):
    p = base / filename
    text = p.read_text(encoding='utf-8-sig')
    # A second run can safely leave already local locations unchanged.
    def root_tag(match):
        def root_attr(a):
            target = a.group(3)
            if not target.startswith(('http://', 'https://')):
                return a.group(0)
            return a.group(1) + a.group(2) + pathlib.Path(os.path.relpath(fetch(target), p.parent)).as_posix() + a.group(2)
        return attr_pattern.sub(root_attr, match.group(0))
    p.write_text(tag_pattern.sub(root_tag, text))
(cache / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('All ONVIF imports are local.')
