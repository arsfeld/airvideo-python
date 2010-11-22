import threading
import dbus
import dbus.service
import gobject
from dbus.mainloop.glib import DBusGMainLoop

import server

DBusGMainLoop(set_as_default=True)

mainloop = gobject.MainLoop()
gobject.threads_init()

class AirVideoServer(dbus.service.Object):
    def __init__(self):
        dbus.service.Object.__init__(self, dbus.SessionBus(), "/Server")
        self.config = server.Config()
        
    def run(self):
        server_thread = server.run()
        try:
            mainloop.run()
        except KeyboardInterrupt:
            server_thread.kill()

    @dbus.service.method(dbus_interface='com.airvideo.Server',
                         in_signature='s', out_signature='v')
    def getConfig(self, name):
        return self.config.get(name)
    
    @dbus.service.method(dbus_interface='com.airvideo.Server',
                         in_signature='sv', out_signature='')
    def setConfig(self, name, value):
        return self.config.set(name, value)

def main():
    session_bus = dbus.SessionBus()
    name = dbus.service.BusName("com.airvideo.Server", session_bus)
    
    AirVideoServer().run()
        
if __name__ == "__main__":
    main()
