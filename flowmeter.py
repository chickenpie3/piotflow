import RPi.GPIO as GPIO
import sys

class FlowMeter:
    
    def __init__(self, pin):
        self.pin = pin
        self.count = 0
        self.end_timeout_ms = 1000
        self.gpio_edge_event = GPIO.FALLING
        self.update_interval = 50
        self.monitoring = False
        self.flow_started = False
    
    def monitor(self, start, update, end):
        self.monitoring = True;
        self.count = 0
        self.flow_started = False
        while (self.monitoring):
            edge = GPIO.wait_for_edge(self.pin, self.gpio_edge_event, timeout=self.end_timeout_ms)
            if edge:
                self.count+=1
                if not self.flow_started:
                    self.flow_started = True
                    if start:
                        start(self) #signal start event
                elif update and self.count % self.update_interval == 0:
                    update(self)
            elif self.flow_started:
                self.flow_started = False
                if end:
                    end(self)
                self.count = 0
        
    def stop(self):
        self.flow_started = False
        self.monitoring = False

    def flowing(self):
        return self.flow_started
    
        
