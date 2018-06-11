import RPIO
import sys
import threading

class FlowMeter:
    
    def __init__(self, pin):
        self.pin = pin
        self.count = 0
        self.end_timeout_ms = 1000
        self.gpio_edge_event = 'falling'
        self.update_interval = 20
        self.monitoring = False
        self.flow_started = False
        self.start_event = None
        self.update_event = None
        self.end_event = None
        self.end_timer = threading.Timer(self.end_timeout_ms/1000, self.timer_callback)
        self.flow_lock = threading.Lock()

    def gpio_callback(self, gpio_id, value):
        self.flow_lock.acquire()
        try:
            self.count+=1
            if not self.flow_started:
                self.flow_started = True
                if self.start_event:
                    self.start_event(self)
            elif self.update_event and self.count % self.update_interval == 0:
                self.update_event(self)
            #reset timer
            self.end_timer.cancel()
            self.end_timer = threading.Timer(self.end_timeout_ms/1000, self.timer_callback)
            self.end_timer.start()
        finally:
            self.flow_lock.release()

    def timer_callback(self):
        self.flow_lock.acquire()
        try:
            self.flow_started = False
            if self.end_event:
                self.end_event(self)
            self.count = 0
        finally:
            self.flow_lock.release()
    
    def monitor(self, start, update, end):
        self.monitoring = True;
        self.count = 0
        self.flow_started = False
        self.start_event = start
        self.update_event = update
        self.end_event = end
        RPIO.add_interrupt_callback(self.pin,
                                    self.gpio_callback,
                                    edge=self.gpio_edge_event,
                                    threaded_callback=True)
        RPIO.wait_for_interrupts()
                
    def stop(self):
        RPIO.stop_waiting_for_interrupts()
        self.flow_started = False
        self.monitoring = False

    def flowing(self):
        return self.flow_started
    
        
