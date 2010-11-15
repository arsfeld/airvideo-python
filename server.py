#!/usr/bin/env python
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer  
from avmap import to_avmap, from_avmap, AVDict
import os

ROOT = "/home/arosenfeld/"

class air(object):
    pass

class video(air):
    pass

class DiskRootFolder(video):
    pass

class Services():
    class browseService(object):
        def getPathItems(self):
            files = os.listdir(ROOT)
            items = []
            for f in files:
                if os.path.isdir(f):
                    items.append(AVDict("air.video.Folder",
                        {'itemId': "ID"}))
                else:
                    items.append(AVDict("air.video.VideoItem",
                        {'itemId': 'ID'}))
            return AVDict("Items", {'items': items})

class Server(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200, 'OK')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write( "<html><h1>hello</h1>world</html>" )
        
    def do_POST(self):
        request = from_avmap(self.rfile)
        print "Request: %s" % request
        response = AVDict("response")
        try:
            service = getattr(Services, request['serviceName'])()
            method = getattr(service, request['methodName'])
        except AttributeError:
            self.send_response(404, "Service not found")
            return
        response['result'] = method()
        self.send_response(200, 'OK')
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
    Server.serve_forever(45631)
