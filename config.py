import os
import sys
import dbus
import gtk

from dbus.mainloop.glib import DBusGMainLoop
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

class MainWindow:
    def __init__(self):
        self.builder = gtk.Builder()
        #self.builder.set_translation_domain(domain)
        self.builder.add_from_file("config.ui")
        self.builder.connect_signals(self)
        for o in self.builder.get_objects():
            if issubclass(type(o), gtk.Buildable):
                name = gtk.Buildable.get_name(o)
                setattr(self, name, o)
            else:
                print >> sys.stderr, "WARNING: can not get name for '%s'" % o
        
        self.bus = dbus.SessionBus()
        
        dbus_obj = self.bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
        dbus_obj.connect_to_signal('NameOwnerChanged', self.name_owner_changed)
        
        self.update_server()
        
        self.config_box = self.builder.get_object("config_box")
        self.status_bar = self.builder.get_object("status_bar")
        main_window = self.builder.get_object("main_window")
        main_window.set_default_size(400, 300)
        main_window.show_all()
        
    def name_owner_changed(self, name, old_owner, new_owner):
        print (name, old_owner, new_owner)
        if name == "com.airvideo.Server":
            self.update_server()
        
    def update_server(self):
        try:
            server_obj = self.bus.get_object('com.airvideo.Server',
                                             '/Server')
            self.server = dbus.Interface(server_obj,
                dbus_interface='com.airvideo.Server')
            
            self.folders_model = self.builder.get_object("folders_model")
            self.update_folders()
            self.config_box.set_sensitive(True)
            self.status_bar.push(0, "Status: Connected")
        except dbus.DBusException:
            self.server = None
            self.folders_model.clear()
            self.config_box.set_sensitive(False)
            self.status_bar.push(1, "Status: Disconnected")

    def update_folders(self):
        self.folders_model.clear()
        for folder in self.server.getConfig("folders"):
            print str(folder)
            icon = gtk.icon_factory_lookup_default(gtk.STOCK_DIRECTORY)
            pixbuf = icon.render_icon(gtk.Style(), gtk.TEXT_DIR_NONE, gtk.STATE_NORMAL, gtk.ICON_SIZE_MENU, None, None)
            
            self.folders_model.append((str(folder),pixbuf))

    def run(self):
        """
        Starts the main loop of processing events checking for Control-C.

        The default implementation checks wheter a Control-C is pressed,
        then calls on_keyboard_interrupt().

        Use this method for starting programs.
        """
        try:
            gtk.main()
        except KeyboardInterrupt:
            sys.exit()

if __name__ == "__main__":
    MainWindow().run()
