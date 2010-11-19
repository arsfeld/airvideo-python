#!/usr/bin/env python
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer  
from avmap import to_avmap, from_avmap, AVDict, AVObject
import os
import random
from ConfigParser import SafeConfigParser

import json

import threading
import dbus
import dbus.service
import gobject

mainloop = gobject.MainLoop()
gobject.threads_init()

from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop(set_as_default=True)

random.seed()

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
        self.config_parser = SafeConfigParser()
        self.config_file = os.path.expanduser('~/.config/airvideo.cfg')
        self.load()
        
    def load(self):
        self.config = {"folders":[os.path.expanduser("~/Videos")]}
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

class browseService(object):
    def __init__(self, config):
        self.config = config
        self.roots = {}
        self.items = {}

    def getItems(self, browseRequest = None):
        if not browseRequest['folderId']:
            for root in self.config.get('folders'):
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
        files = os.listdir(self.config.get_config('folders'))
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

class Server(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(404, 'What are you doing here?')
        
    def do_POST(self):
        request = from_avmap(self.rfile)
        print "Request: %s" % request
        response = AVDict("air.connect.Response")
        try:
            service = self.services[request['serviceName']]
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

class ServerThread(threading.Thread):
    def __init__(self, config, services):
        threading.Thread.__init__(self)
        self.config = config
        self.services = services

    def run(self):
        try:
            self.server = HTTPServer(('', 45632), Server)
            self.server.config = self.config
            self.server.services = self.services
            self.server.serve_forever()
        except KeyboardInterrupt:
            self.kill()
    
    def kill(self):
        print "Shutting down server..."
        self.server.shutdown()
        
class AirVideoServer(dbus.service.Object):
    def __init__(self, config):
        dbus.service.Object.__init__(self, dbus.SessionBus(), "/Server")
        self.config = config

    @dbus.service.method(dbus_interface='com.airvideo.ServerInterface',
                         in_signature='s', out_signature='v')
    def getConfig(self, name):
        return self.config.get(name)
    
    @dbus.service.method(dbus_interface='com.airvideo.ServerInterface',
                         in_signature='sv', out_signature='')
    def setConfig(self, name, value):
        return self.config.set(name, value)

if __name__ == "__main__":
    config = Config()
    services = {'browseService': browseService(config)}
    
    session_bus = dbus.SessionBus()
    name = dbus.service.BusName("com.airvideo.Server", session_bus)
    
    AirVideoServer(config)
    
    server = ServerThread(config, services)
    server.start()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        server.kill()
