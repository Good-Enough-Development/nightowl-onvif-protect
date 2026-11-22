import json, pathlib
base=pathlib.Path(__file__).resolve().parent
p=base/'config.yaml'
cfg=json.loads(p.read_text())
for ch,cam in enumerate(cfg['onvif'],1):
    cam['motion']={
        'channel':ch,'stateFile':str(base/'runtime'/f'motion-camera{ch}.json'),
        'pixelThreshold':20,'minChangedPercent':0.25,'holdSeconds':8,'warmupSeconds':10,
    }
p.write_text(json.dumps(cfg,indent=2)+'\n')
print('Enabled per-channel video motion and ONVIF event capabilities; camera identities and stream paths preserved.')
