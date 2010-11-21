import threading

from Queue import Queue

import pygst
pygst.require('0.10')
import gst
from gst.extend import discoverer

import utils

def loader():
    return Loader()

@utils.singleton
class Loader(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.queue = Queue()
        self.killed = False
        self.lock = threading.Lock()
        self.locks = {}

    def load(self, filename, callback):
        self.locks[filename] = threading.Condition()
        self.queue.put((filename, callback, self.locks[filename]))
        
    def get_lock(self, filename):
        self.lock.acquire()
        try:
            return self.locks[filename]
        finally:
            self.lock.release()

    def run(self):
        while not self.killed:
            filename, callback, lock = self.queue.get()
            lock.acquire()
            def discovered(d, is_media):
                callback(d, is_media)
                lock.acquire()
                lock.notifyAll()
                lock.release()
            d = discoverer.Discoverer(filename)
            d.connect('discovered', discovered)
            d.discover()
            lock.wait()
            lock.release()
            self.lock.acquire()
            del self.locks[filename]
            self.lock.release()
            
            
    def wait(self, filename):
        '''Wait for metadata to finish loading'''
        self.lock.acquire()
        if filename not in self.locks:
            self.lock.release()
            return
        condition = self.locks[filename]
        self.lock.release()
        condition.acquire()
        condition.wait()
        condition.release()
            
    def kill(self):
        self.killed = True

