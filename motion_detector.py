"""Low-resolution, per-camera motion state for the existing FFmpeg decoder."""
import datetime, json, os, pathlib, time
import numpy as np

class MotionDetector:
    WIDTH, HEIGHT, FPS = 320, 180, 3
    def __init__(self, channel, output=None, clock=time.monotonic, options=None):
        self.channel, self.output, self.clock = channel, pathlib.Path(output) if output else None, clock
        options = options or {}
        self.threshold = float(options.get('pixelThreshold', 20))
        self.min_percent = float(options.get('minChangedPercent', 0.25))
        self.hold = float(options.get('holdSeconds', 8))
        self.warmup = float(options.get('warmupSeconds', 10))
        self.started, self.last_motion = clock(), float('-inf')
        self.background, self.previous = None, None
        self.active, self.consecutive, self.frames = False, 0, 0
        self.score = 0.0
        self.changed_at = self.utc()

    @staticmethod
    def utc():
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')

    @staticmethod
    def denoise(mask):
        # A 3x3 majority suppresses isolated codec noise and single-pixel flicker.
        padded = np.pad(mask.astype(np.uint8), 1)
        total = sum(padded[y:y+mask.shape[0],x:x+mask.shape[1]] for y in range(3) for x in range(3))
        return total >= 5

    def feed(self, raw):
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.HEIGHT,self.WIDTH).astype(np.float32)
        # Exclude the top/bottom overlays where recorder clocks and titles change.
        frame = frame[22:166,8:312]
        now = self.clock()
        if self.background is None:
            self.background, self.previous = frame.copy(), frame.copy()
        global_shift = float(np.median(frame-self.previous))
        temporal = np.abs(frame-self.previous-global_shift)
        background_shift = float(np.median(frame-self.background))
        foreground = np.abs(frame-self.background-background_shift)
        moved = self.denoise(temporal > self.threshold)
        self.score = float(np.mean(moved)*100)
        foreground_percent = float(np.mean(self.denoise(foreground > self.threshold))*100)
        scene_change = abs(global_shift)>18 or self.score>45
        if scene_change:
            self.background = frame.copy()
            self.consecutive = 0
            candidate = False
        else:
            candidate = self.score >= self.min_percent and foreground_percent >= self.min_percent
            self.consecutive = self.consecutive+1 if candidate else 0
            if now-self.started >= self.warmup and self.consecutive >= 2:
                self.last_motion = now
            self.background += 0.025*(frame-self.background)
        self.previous = frame
        active = now-self.started >= self.warmup and now-self.last_motion < self.hold
        if active != self.active:
            self.active, self.changed_at = active, self.utc()
            print(f'[MOTION] channel={self.channel} active={active} changedPixels={self.score:.3f}%',flush=True)
        self.frames += 1
        self.write('warming-up' if now-self.started<self.warmup else 'running')
        return self.active

    def write(self, status):
        if not self.output:
            return
        payload = {'channel':self.channel,'active':self.active,'updatedAt':self.utc(),
                   'transitionAt':self.changed_at,'status':status,'source':'video',
                   'changedPercent':round(self.score,4),'frames':self.frames}
        tmp = self.output.with_suffix('.tmp')
        with tmp.open('w') as f:
            json.dump(payload,f)
        os.replace(tmp,self.output)

    def stopped(self):
        self.active, self.changed_at = False, self.utc()
        self.write('stopped')
