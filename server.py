#!/usr/bin/env python
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer  
from avmap import to_avmap, from_avmap, AVDict, AVObject
import os
import random

random.seed()

ROOT = ["/home/arosenfeld/Videos", "/home/arosenfeld/Packages"]

class Item(AVObject):
    def __init__(self, filename):
        self._filename = filename
        self._children = None
        self.folder = os.path.isdir(filename)
        self.detail = None
        self.detailLoaded = False
        self.converted = False
        self.name = os.path.basename(filename)
        self.itemId="%016x" % random.getrandbits(128)
        
    def loadDetails(self):
        raise NotImplementedError()
    
    def getItems(self):
        raise NotImplementedError()
    
class MediaInfo(AVObject):
    pass
    
class VideoItem(Item):
        
    def loadDetails(self):
        self.detailLoaded = True
        self.detail = MediaInfo(
            fileSize = os.path.getsize(self._filename),
            subtitles = [],
            duration = 0.0,
            bitrate = 0,
            streams = [],
        )
        self.playable = True
        self.converted = False
    
def cmp_items(x, y):
    if type(x) == type(y):
        return cmp(x._filename.lower(), y._filename.lower())
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
        
    def loadDetails(self):
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
                    item = Folder(filename)
                else:
                    item = VideoItem(filename)
                self._children.append(item)
            self._children = sorted(self._children, cmp=cmp_items)
        return self._children
        
class DiskRootFolder(Folder):
    pass
    
class FolderContent(AVObject):
    pass
    
class PathItem(AVObject):
    def __init__(self, itemId, type_, name):
        AVObject(itemId=itemId, type_=type_,name=name)
    
class Config(object):
    def __init__(self):
        self.root = ROOT

class browseService(object):
    def __init__(self, config):
        self.config = config
        self.roots = {}
        self.items = {}

    def getItems(self, browseRequest = None):
        if not browseRequest['folderId']:
            for root in self.config.root:
                if root not in self.roots:
                    root_folder = DiskRootFolder(filename=root)
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
        
    def getItemsWithDetail(self, folders):
        items = []
        for folder_id in folders:
            folder = self.items[folder_id]
            folder.loadDetails()
            items.append(folder)
        return items

    def getItems2(self, params):
        files = os.listdir(self.config.root)
        items = []
        for f in files:
            if os.path.isdir(f):
                items.append(Folder(itemId=None))
            else:
                items.append(VideoItem(itemId=None))
        return items
        
    def getPathItems(self, params):
        items = [PathItem(itemId=None, type_=0, name='tauron')]
        return items
        
config = Config()
services = {'browseService': browseService(config)}

class Server(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404, 'What are you doing here?')
        
    def do_POST(self):
        request = from_avmap(self.rfile)
        print "Request: %s" % request
        response = AVDict("air.connect.Response")
        try:
            service = services[request['serviceName']]
            method = getattr(service, request['methodName'])
        except AttributeError:
            self.send_response(404, "Service not found")
            return
        response['errorMessage'] = None
        response['errorReport'] = None
        response['state'] = 0
        try:
            response['result'] = method(*request['parameters'])
            self.send_response(200, 'OK')
        except Exception as exp:
            response['errorMessage'] = "%s: %s" % (type(exp), exp)
            response['errorReport'] = True
            self.send_response(500, 'Error')
            raise
        print "Response: %s" % response
        self.end_headers()
        self.wfile.write(to_avmap(response))

    @staticmethod
    def serve_forever(port):
        try:
            server = HTTPServer(('', port), Server)
            server.serve_forever()
        except KeyboardInterrupt:
            print "Shutting down..."
            server.shutdown()

if __name__ == "__main__":
    Server.serve_forever(45632)
