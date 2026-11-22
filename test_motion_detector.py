import unittest
import numpy as np
from motion_detector import MotionDetector

class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.now=0.0
        self.d=MotionDetector(1,clock=lambda:self.now,options={'warmupSeconds':1,'holdSeconds':2})
        self.frame=np.full((180,320),70,dtype=np.uint8)
    def feed(self,frame):
        self.now+=1/3
        return self.d.feed(frame.tobytes())
    def test_static_noise_and_clock_overlay_do_not_trigger(self):
        rng=np.random.default_rng(7)
        for _ in range(45):
            frame=np.clip(self.frame.astype(int)+rng.integers(-4,5,self.frame.shape),0,255).astype(np.uint8)
            frame[0:15,0:180]=rng.integers(0,255,(15,180),dtype=np.uint8)
            self.assertFalse(self.feed(frame))
    def test_moving_object_starts_and_idle_clears(self):
        for _ in range(6):self.feed(self.frame)
        for x in range(40,120,10):
            frame=self.frame.copy();frame[60:110,x:x+30]=180
            active=self.feed(frame)
        self.assertTrue(active)
        for _ in range(12):active=self.feed(self.frame)
        self.assertFalse(active)
    def test_global_light_change_does_not_trigger(self):
        for _ in range(9):self.feed(self.frame)
        for _ in range(12):self.assertFalse(self.feed(np.full_like(self.frame,130)))

if __name__=='__main__':unittest.main()
