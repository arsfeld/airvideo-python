import threading
import sys
import os
import gobject
import gtk

from Queue import Queue

import pygst
pygst.require('0.10')
import gst
from gst.extend import discoverer

import utils

gobject.threads_init()

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
        
def generate_thumbnail(filename):
    print "Getting thumb for %s" % (filename)
    CAPS = "video/x-raw-rgb,pixel-aspect-ratio=1/1,bpp=(int)24,"\
           "depth=(int)24,endianness=(int)4321,red_mask=(int)0xff0000,"\
           "green_mask=(int)0x00ff00, blue_mask=(int)0x0000ff"
    pipeline_desc = "uridecodebin uri=\"file://%s\" ! ffmpegcolorspace ! videoscale !"\
      " appsink name=sink caps=\"%s\"" % (filename, CAPS)
    print pipeline_desc
    pipeline = gst.parse_launch(pipeline_desc)
    sink = pipeline.get_by_name("sink")

    ret = pipeline.set_state(gst.STATE_PAUSED)
    if ret == gst.STATE_CHANGE_FAILURE:
        print "failed to play the file"
        return None
    elif ret == gst.STATE_CHANGE_NO_PREROLL:
        # for live sources, we need to set the pipeline to PLAYING before we can
        # receive a buffer. We don't do that yet 
        print "live sources not supported yet"
        return None
    print gst.SECOND
    ret = pipeline.get_state (5 * gst.SECOND)
    
    # get the duration
    duration = pipeline.query_duration(gst.FORMAT_TIME)[0]

    if duration != -1:
        # we have a duration, seek to 5% 
        position = duration * 5 / 100.0;
    else:
        # no duration, seek to 1 second, this could EOS 
        position = 1 * gst.SECOND;

    # seek to the a position in the file. Most files have a black first frame so
    # by seeking to somewhere else we have a bigger chance of getting something
    # more interesting. An optimisation would be to detect black images and then
    # seek a little more 
    pipeline.seek_simple(gst.FORMAT_TIME, gst.SEEK_FLAG_FLUSH, position);

    # get the preroll buffer from appsink, this block untils appsink really
    # prerolls */
    buf = sink.emit("pull-preroll")
    
    # if we have a buffer now, convert it to a pixbuf. It's possible that we
    # don't have a buffer because we went EOS right away or had an error. */
    if buf:
        # get the snapshot buffer format now. We set the caps on the appsink so
        # that it can only be an rgb buffer. The only thing we have not specified
        # on the caps is the height, which is dependant on the pixel-aspect-ratio
        # of the source material
        caps = buf.get_caps();
        if not caps:
            print "could not get snapshot format"
            return None
        s = caps[0];

        # we need to get the final caps on the buffer to get the size 
        width = s["width"];
        height = s["height"];

        # create pixmap from buffer and save, gstreamer video buffers have a stride
        # that is rounded up to the nearest multiple of 4 
        #print width * 3
        #print width * 3 + (4 - (width * 3) % 4)
        pixbuf = gtk.gdk.pixbuf_new_from_data(buf.data,
            gtk.gdk.COLORSPACE_RGB, False, 8, width, height,
            width * 3)
        data = StringIO.StringIO()
        pixbuf.save_to_callback(data.write, "jpeg", {"quality":"90"})
        return data.get_value()
        # save the pixbuf 
        #pixbuf.save("snapshot.png", "png")
    else:
        print "could not make snapshot"
        return None
        
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
    gobject.idle_add(generate_thumbnail)
    
    
    #from gstmanager.gstmanager import PipelineManager
    #pipeline = PipelineManager(pipeline_desc)
    #pipeline.pause()
    #print pipeline.get_duration()
    
    #pipeline = server(sys.argv[1]) 
    # The MainLoop
    mainloop = gobject.MainLoop()
    # And off we go!
    #pipeline.set_state(gst.STATE_PLAYING)
    mainloop.run()
    
