#!/usr/bin/env python
import os
import threading
import tempfile
import subprocess
import socket
import hashlib
import re
import random
import json

cherrypy_available = False
try:
    import cherrypy
    cherrypy_available = True
except:
    pass
from gzip import GzipFile
from wsgiref.simple_server import make_server
#from flup.server.fcgi import WSGIServer
#from threading import Thread
#from socket import socket
#from select import select

import avmap
import utils
import media

import pygst
pygst.require('0.10')
import gst

import SocketServer
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from ConfigParser import SafeConfigParser
from avmap import AVDict, AVObject

try:
    import cStringIO as StringIO
except:
    import StringIO

random.seed()

class Item(AVObject):
    def __init__(self, filename, root = None, parent = None):
        self._filename = filename
        self._parent = parent
        self._children = None
        self._loading = False
        self.folder = os.path.isdir(filename)
        self.detail = None
        self.detailLoaded = False
        self.converted = False
        self.name = os.path.basename(filename)
        if root is not None:
            self.itemId=root.itemId+filename[len(root._filename):]
            self._root = root
        else:
            self.itemId = utils.filename_id(filename)            
                    
    def loadDetails(self, wait = False):
        raise NotImplementedError()
    
    def getItems(self):
        raise NotImplementedError()
    
class MediaInfo(AVObject):
    class AudioStream(AVObject):
        __namespace__='.'.join([AVObject.__namespace__,'MediaInfo'])
        
    class VideoStream(AVObject):
        __namespace__='.'.join([AVObject.__namespace__,'MediaInfo'])

class VideoItem(Item):

    def loadDetails(self, wait = False):
        if not self._loading:
            self._loading = True
            media.loader().load(self._filename, self.loadCallback)
            if wait:
                media.loader().wait(self._filename)

    def getThumbnail(self):
        filename_md5 = hashlib.md5(os.path.abspath(self._filename)).hexdigest()
        thumbs_dir = os.path.join(os.path.expanduser("~"), '.cache', 'airvideo-python', 'thumbs')
        if not os.path.exists(thumbs_dir):
            os.makedirs(thumbs_dir)
        thumb_filename = os.path.join(thumbs_dir, filename_md5)
        if not os.path.exists(thumb_filename):
            subprocess.call(["/usr/bin/totem-video-thumbnailer", "-s", "256","--jpeg", self._filename, thumb_filename])
        thumb_data = StringIO.StringIO()
        if os.path.exists(thumb_filename):
            thumb_file = open(thumb_filename, "r")    
            thumb_data.write(thumb_file.read())
            thumb_data.seek(0)
            thumb_file.close()
        return thumb_data

    def findConverted(self):
        basename, ext = os.path.splitext(os.path.basename(self._filename))
        folders = [os.path.dirname(self._filename)] + config().get("convert_folders")
        for folder in folders:
            if not os.path.isabs(folder):
                folder = os.path.join(os.path.dirname(self._filename), folder)
            filenames = [os.path.join(folder, basename + '.m4v'),
                         os.path.join(folder, basename + '.mp4'),
                         os.path.join(folder, basename + ' - airvideo.m4v'),
                         os.path.join(folder, basename + ' - airvideo.mp4')]
            for filename in filenames:
                if os.path.exists(filename):
                    return filename
        return False

    def loadCallback(self, d, is_media):
        print "Details load callback!!"
        self.detailLoaded = True
        if not is_media:
            self.playable = False
        else:
            self.converted =  (self.findConverted() != False)
            self.playable = self.converted or os.path.splitext(self._filename) in ['.mp4', '.m4v']
            streams = []
            if d.is_audio:
                streams.append(MediaInfo.AudioStream(
                    index = len(streams),
                    streamType = 1,
                    codec = "audio",
                    language = "eng"
                ))
            if d.is_video:
                streams.append(MediaInfo.VideoStream(
                    index = len(streams),
                    streamType = 0,
                    codec = "video",
                    language = "eng",
                    width = int(d.videowidth),
                    height = int(d.videoheight)
                ))
            self.detail = MediaInfo(
                fileSize = os.path.getsize(self._filename),
                subtitles = [],
                duration = float(d.videolength/gst.SECOND),
                bitrate = 0,
                streams = streams,
                videoThumbnail = self.getThumbnail(),
            )
        self._loading = False
    
    
def cmp_filename(filename1, filename2):
    '''
    Auxiliar function to compare filenames grouping numbers.
    
    This function recognizes that, for instance, filename1 is less then 
    filename10 and so on, by grouping numbers together.
    '''
    def try_int(value):
        try:
            value = int(value)
        except:
            pass
        return value
    if not (filename1 and filename2):
        return cmp(filename1, filename2)
    regex = re.compile("(\d+|\D+)")
    groups1 = map(try_int, regex.findall(filename1))
    groups2 = map(try_int, regex.findall(filename2))
    return cmp(groups1, groups2)
    
def cmp_items(x, y):
    if type(x) == type(y):
        return cmp_filename(x._filename.lower(), y._filename.lower())
    else:
        if isinstance(x, VideoItem):
            return 1
        elif isinstance(y, VideoItem):
            return -1
        else:
            return 0
    
class Folder(Item):
    class Detail(AVObject):
        __namespace__='.'.join([AVObject.__namespace__,'Folder'])
        
    def loadDetails(self, wait = False):
        self.detailLoaded = True
        self.detail = Folder.Detail(childrenCount = len(self.getItems()))
    
    def getItems(self):
        if not self._children:
            self._children = []
            for f in os.listdir(self._filename):
                if f.startswith('.'):
                    continue
                filename = os.path.join(self._filename, f)
                if os.path.isdir(filename):
                    item = Folder(filename, root = self._root, parent = self)
                else:
                    item = VideoItem(filename, root = self._root, parent = self)
                self._children.append(item)
            self._children = sorted(self._children, cmp=cmp_items)
        return self._children
        
class DiskRootFolder(Folder):
    pass
    
class FolderContent(AVObject):
    pass
    
class PathItem(AVObject):
    pass
    
class ConversionFolder(AVObject):
    pass
    
@utils.singleton
class Config(object):
    def __init__(self):
        self.config_parser = SafeConfigParser()
        self.config_file = os.path.expanduser('~/.config/airvideo.cfg')
        self.load()
        
    def load(self):
        self.config = {
            "folders":[os.path.expanduser("~/Videos")],
            "convert_folders":['.converted_videos'],
        }
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as config_file:
                self.config.update(json.load(config_file))

    def save(self):
        with open(self.config_file, 'wb') as config_file:
            json.dump(self.config, config_file, sort_keys=True, indent=4)
            
    def get(self, name):
        return self.config[name]
        
    def set(self, name, value):
        self.config[name] = value
        self.save()
            
    def get_folders(self):
        return self.get('folders')
        
    def add_folder(self, path):
        self.get('folders').append(path)
        self.save()
        
    def remove_folder(self, path):
        if path in self.get('folders'):
            del self.get('folders')[path]
            self.save()
            
def config():
    return Config()

@utils.singleton
class browseService(object):
    def __init__(self):
        self.roots = {}
        self.items = {}

    def getItems(self, browseRequest = None):
        if not browseRequest['folderId']:
            for root in config().get('folders'):
                root = os.path.expanduser(root)
                if root not in self.roots:
                    root_folder = DiskRootFolder(filename=root)
                    root_folder._root = root_folder
                    self.items[root_folder.itemId] = root_folder
                    self.roots[root] = root_folder
            items = self.roots.values()
        else:
            folder = self.items[browseRequest['folderId']]
            items = folder.getItems()
            for item in items:
                self.items[item.itemId] = item
        return FolderContent(
            items = items,
            name = "tauron",
            serverVersion = 204.03,
            invalidPassword = False,
            folderId = None,
        )
        
    def getItemsWithDetail(self, items_id):
        items = []
        for items_id in items_id:
            item = self.items[items_id]
            item.loadDetails(wait = True)
            items.append(item)
        return items
        
    def getNestedItem(self, item_id):
        return self.items[item_id]
        
    def getPathItems(self, item_id):
        items = []
        root = PathItem(itemId=None, type_=0, name=socket.gethostname())
        if item_id:
            item = self.items[item_id]
            items = []
            while item:
                items.append(PathItem(itemId=item.itemId, 
                                       type_=int(not item.folder),
                                       name=item.name))
                item = item._parent
            items.append(root)
        else:
            items.append(root)
        return list(reversed(items))
        
    def initPlayback(self, items):
        pass
        
@utils.singleton
class conversionService(object):
    def getConversionLocations(self):
        return [ConversionFolder(folderId = utils.filename_id(folder),
                                 location = folder,
                                 name = os.path.basename(folder)) 
                for folder in config().get("convert_folders")]

@utils.singleton
class playbackService(object):
    def initPlayback(self, items):
        pass

browse_service = browseService()
conversion_service = conversionService()
playbackService = playbackService()

services = {'browseService': browse_service,
            'conversionService': conversion_service,
            'playbackService': playbackService}

def process_request(request, outfile = None):
    '''Generic request handler for /service
    
    request: avmap structure (from avmap.load)
    outfile: file-like object to write the response (if None, a string will be
        the return value with the response) 
    '''
    fakefile = outfile is None
    if fakefile:
        outfile = StringIO.StringIO()
    print "Request:"
    utils.pprint(request)
    response = AVDict("air.connect.Response")
    try:
        service = services[request['serviceName']]
        method = getattr(service, request['methodName'])
    except AttributeError:
        raise Exception()
    response['errorMessage'] = None
    response['errorReport'] = None
    response['state'] = 0
    try:
        response['result'] = method(*request['parameters'])
    except Exception as exp:
        #Error is not working
        #response['errorMessage'] = "%s: %s" % (type(exp), exp)
        #response['errorReport'] = True
        raise
    print "Response:"
    utils.pprint(avmap.loads(avmap.dumps(response)))
    avmap.dump(response, outfile)
    if fakefile:
        return outfile.getvalue()

class Server(BaseHTTPRequestHandler):
    '''Request handler from the generic HTTPServer'''
    def do_GET(self):
        self.send_response(404, 'What are you doing here?')
        
    def do_POST(self):
        request = avmap.load(self.rfile)
        self.send_response(200, 'OK')
        self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        outfile = GzipFile(fileobj=self.wfile, compresslevel=7)
        process_request(request, outfile)
        outfile.close()

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, HTTPServer):
    '''Generic HTTPServer handler (does not use wsgi or anything)'''
    @classmethod
    def run(cls):
        cls.server = ThreadedHTTPServer(('', 45632), Server)
        cls.server.serve_forever()
        
    @classmethod
    def shutdown(cls):
        cls.server.shutdown()

class WsgiServer:
    '''Server using the wsgi handler (will be used if cherrypy is not available'''
    def serve(self, environ, start_response):
        start_response('200 OK', [('Content-type', 'avmap')])
        request = avmap.load(environ['wsgi.input'])
        return process_request(request)
        
    @classmethod
    def run(cls):
        app = WsgiServer()
        cls.server = make_server('', 45632, app.serve)
        cls.server.serve_forever()
        
    @classmethod
    def shutdown(cls):
        cls.server.shutdown()

if cherrypy_available:
    class CherryPyServer:
        '''CherryPy based server'''
        @cherrypy.expose
        def service(self, data):
            request = avmap.load(data)
            return process_request(request)
            
        @classmethod
        def run(cls):
            cherrypy.server.socket_port = 45632
            cherrypy.server.socket_host = '0.0.0.0'
            cherrypy.quickstart(CherryPyServer())
        
        @classmethod
        def shutdown(cls):
            pass
        
class ServerThread(threading.Thread):
    '''Runs a web server in a thread.
    
    Chooses from an available server and calls the static run method'''
    def run(self):
        try:
            media.loader().start()
            if cherrypy_available:
                self.server = CherryPyServer
            else:
                self.server = WsgiServer
            #self.server = ThreadedHTTPServer
            self.server.run()
        except KeyboardInterrupt:
            self.kill()
    
    def kill(self):
        print "Shutting down server..."
        self.server.shutdown()
        media.loader().kill()
        
def run():
    '''Create and run a server thread'''
    server_thread = ServerThread()
    server_thread.setDaemon(True)
    server_thread.start()
    return server_thread
    
if __name__ == "__main__":
    try:
        server = run()
        while server.is_alive():
            server.join(1.0)
    except KeyboardInterrupt:
        server.kill()
