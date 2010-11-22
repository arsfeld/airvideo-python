import threading
import sys
import os
import gobject

from Queue import Queue

import pygst
pygst.require('0.10')
import gst
from gst.extend import discoverer

import utils

# Avoid importing gst in server.py
SECOND = gst.SECOND

def loader():
    return Loader()

@utils.singleton
class Loader(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.queue = Queue(5)
        self.killed = False
        self.lock = threading.Lock()
        self.locks = {}

    def load(self, filename, callback):
        self.locks[filename] = threading.Condition()
        self.queue.put((filename, callback, self.locks[filename]))
        
    def full(self):
        return self.queue.full()
        
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
        if self.queue.full():
            return
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
        
STREAM_PORT = 9990

def server(filename):
    #filesrc name=file location=SOURCE ! decodebin name=demux { mpegtsmux name=mux ! tcpserversink port=PORT }     
    #{ demux. ! queue ! audioconvert ! faac profile=2 ! queue ! mux. } 
    #{ demux. ! queue ! videorate ! x264enc bitrate=50 ! mux. }
    
    print "playing %s" % filename
    pipeline = gst.Pipeline("streamer")
    
    def on_new_decoded_pad(element, pad, last):
        print pad.get_caps()
        print pad.get_caps().to_string().startswith("video/")
        #print pad.get_target().get_property("template")
        #print dir(pad)
        #print pad.get_pad_template()
        #if pad.get_property("template").name_template == "video_%02d":
        if pad.get_caps().to_string().startswith("video/"):
            qv_pad = pipeline.get_by_name("video_queue").get_pad("sink")
            pad.link(qv_pad)
            print pad.get_caps()
        #elif pad.get_property("template").name_template == "audio_%02d":
        elif pad.get_caps().to_string().startswith("audio/"):
            qa_pad = pipeline.get_by_name("audio_queue").get_pad("sink")
            pad.link(qa_pad)
    
    def on_eos(bus, msg):
        print 'on_eos'
        #mainloop.quit()


    def on_tag(bus, msg):
        taglist = msg.parse_tag()
        print 'on_tag:'
        for key in taglist.keys():
            print '\t%s = %s' % (key, taglist[key])


    def on_error(bus, msg):
        error = msg.parse_error()
        print 'on_error:', error[1]
        #self.mainloop.quit()
    
    # Create bus and connect several handlers
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect('message::eos', on_eos)
    bus.connect('message::tag', on_tag)
    bus.connect('message::error', on_error)

    
    source = gst.element_factory_make("filesrc", "file")
    source.set_property("location", filename)
    decode = gst.element_factory_make("decodebin", "demux")
    decode.connect('new-decoded-pad', on_new_decoded_pad)
    pipeline.add(source, decode)
    gst.element_link_many(source, decode)

    audio_queue = gst.element_factory_make("queue", "audio_queue")
    audio_convert = gst.element_factory_make("audioconvert", "audio_convert")
    audio_faac = gst.element_factory_make("faac", "audio_faac")
    audio_faac.set_property("profile", 2)
    audio_queue2 = gst.element_factory_make("queue", "audio_queue2")
    pipeline.add(audio_queue, audio_convert, audio_faac, audio_queue2)
    gst.element_link_many(audio_queue, audio_convert, audio_faac, audio_queue2)
    
    video_queue = gst.element_factory_make("queue", "video_queue")
    video_rate = gst.element_factory_make("videorate", "video_rate")
    video_scale = gst.element_factory_make("videoscale", "video_scale")
    caps = gst.Caps("video/x-raw-yuv,width=256,height=256")
    video_capsfilter = gst.element_factory_make("capsfilter", "video_capsfilter")
    video_capsfilter.props.caps = caps
    video_x264enc = gst.element_factory_make("x264enc", "video_x264enc")
    video_x264enc.set_property("bitrate", 150)
    pipeline.add(video_queue, video_rate, video_scale, video_capsfilter, video_x264enc)
    gst.element_link_many(video_queue, video_scale, video_capsfilter, video_rate, video_x264enc)
    
    mpegtsmux = gst.element_factory_make("mpegtsmux", "mux")
    tcpserversink = gst.element_factory_make("tcpserversink", "tcpserversink")
    tcpserversink.set_property("port", STREAM_PORT)
    pipeline.add(mpegtsmux, tcpserversink)
    gst.element_link_many(mpegtsmux, tcpserversink)
    
    gst.element_link_many(video_x264enc, mpegtsmux)
    gst.element_link_many(audio_queue2, mpegtsmux)
    
    return pipeline

if __name__ == "__main__":
    pipeline = server(sys.argv[1])
    
    # The MainLoop
    mainloop = gobject.MainLoop()

    # And off we go!
    pipeline.set_state(gst.STATE_PLAYING)
    mainloop.run()
    
