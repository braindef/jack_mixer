#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# This file is part of jack_mixer
#
# Copyright (C) 2006-2009 Nedko Arnaudov <nedko@arnaudov.name>
# Copyright (C) 2009 Frederic Peters <fpeters@0d.be>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.

from optparse import OptionParser

import gtk
import gobject
import sys
import os

try:
    import lash
except:
    lash = None
    print >> sys.stderr, "Cannot load LASH python bindings, you want them unless you enjoy manual jack plumbing each time you use this app"

# temporary change Python modules lookup path to look into installation
# directory ($prefix/share/jack_mixer/)
old_path = sys.path
sys.path.insert(0, os.path.join(os.path.dirname(sys.argv[0]), '..', 'share', 'jack_mixer'))

import jack_mixer_c
import scale
from channel import *

import gui
from preferences import PreferencesDialog

from serialization_xml import XmlSerialization
from serialization import SerializedObject, Serializator

# restore Python modules lookup path
sys.path = old_path

class JackMixer(SerializedObject):

    # scales suitable as meter scales
    meter_scales = [scale.IEC268(), scale.Linear70dB(), scale.IEC268Minimalistic()]

    # scales suitable as volume slider scales
    slider_scales = [scale.Linear30dB(), scale.Linear70dB()]

    # name of settngs file that is currently open
    current_filename = None

    def __init__(self, name, lash_client):
        self.mixer = jack_mixer_c.Mixer(name, self.newchannel_callback)
        if not self.mixer:
            return
        self.monitor_channel = self.mixer.add_output_channel("Monitor", True, True)

        if lash_client:
            # Send our client name to server
            lash_event = lash.lash_event_new_with_type(lash.LASH_Client_Name)
            lash.lash_event_set_string(lash_event, name)
            lash.lash_send_event(lash_client, lash_event)

            lash.lash_jack_client_name(lash_client, name)

        gtk.window_set_default_icon_name('jack_mixer')

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title(name)

        self.gui_factory = gui.Factory(self.window, self.meter_scales, self.slider_scales)

        self.vbox_top = gtk.VBox()
        self.window.add(self.vbox_top)

        self.menubar = gtk.MenuBar()
        self.vbox_top.pack_start(self.menubar, False)

        mixer_menu_item = gtk.MenuItem("_Mixer")
        self.menubar.append(mixer_menu_item)
        edit_menu_item = gtk.MenuItem('_Edit')
        self.menubar.append(edit_menu_item)
        help_menu_item = gtk.MenuItem('_Help')
        self.menubar.append(help_menu_item)

        self.window.set_default_size(120, 300)

        mixer_menu = gtk.Menu()
        mixer_menu_item.set_submenu(mixer_menu)

        add_input_channel = gtk.ImageMenuItem('New _Input Channel')
        mixer_menu.append(add_input_channel)
        add_input_channel.connect("activate", self.on_add_input_channel)

        add_output_channel = gtk.ImageMenuItem('New _Output Channel')
        mixer_menu.append(add_output_channel)
        add_output_channel.connect("activate", self.on_add_output_channel)

        mixer_menu.append(gtk.SeparatorMenuItem())
        open = gtk.ImageMenuItem(gtk.STOCK_OPEN)
        mixer_menu.append(open)
        open.connect('activate', self.on_open_cb)
        save = gtk.ImageMenuItem(gtk.STOCK_SAVE)
        mixer_menu.append(save)
        save.connect('activate', self.on_save_cb)
        save_as = gtk.ImageMenuItem(gtk.STOCK_SAVE_AS)
        mixer_menu.append(save_as)
        save_as.connect('activate', self.on_save_as_cb)

        mixer_menu.append(gtk.SeparatorMenuItem())

        quit = gtk.ImageMenuItem(gtk.STOCK_QUIT)
        mixer_menu.append(quit)
        quit.connect('activate', self.on_quit_cb)

        edit_menu = gtk.Menu()
        edit_menu_item.set_submenu(edit_menu)

        self.channel_edit_input_menu_item = gtk.MenuItem('_Edit Input Channel')
        edit_menu.append(self.channel_edit_input_menu_item)
        self.channel_edit_input_menu = gtk.Menu()
        self.channel_edit_input_menu_item.set_submenu(self.channel_edit_input_menu)

        self.channel_edit_output_menu_item = gtk.MenuItem('Edit _Output Channel')
        edit_menu.append(self.channel_edit_output_menu_item)
        self.channel_edit_output_menu = gtk.Menu()
        self.channel_edit_output_menu_item.set_submenu(self.channel_edit_output_menu)

        self.channel_remove_input_menu_item = gtk.MenuItem('Remove _Input Channel')
        edit_menu.append(self.channel_remove_input_menu_item)
        self.channel_remove_input_menu = gtk.Menu()
        self.channel_remove_input_menu_item.set_submenu(self.channel_remove_input_menu)

        self.channel_remove_output_menu_item = gtk.MenuItem('_Remove Output Channel')
        edit_menu.append(self.channel_remove_output_menu_item)
        self.channel_remove_output_menu = gtk.Menu()
        self.channel_remove_output_menu_item.set_submenu(self.channel_remove_output_menu)

        channel_remove_all_menu_item = gtk.ImageMenuItem(gtk.STOCK_CLEAR)
        edit_menu.append(channel_remove_all_menu_item)
        channel_remove_all_menu_item.connect("activate", self.on_channels_clear)

        edit_menu.append(gtk.SeparatorMenuItem())

        preferences = gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
        preferences.connect('activate', self.on_preferences_cb)
        edit_menu.append(preferences)

        help_menu = gtk.Menu()
        help_menu_item.set_submenu(help_menu)

        about = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
        help_menu.append(about)
        about.connect("activate", self.on_about)

        self.hbox_top = gtk.HBox()
        self.vbox_top.pack_start(self.hbox_top, True)

        self.scrolled_window = gtk.ScrolledWindow()
        self.hbox_top.pack_start(self.scrolled_window, True)

        self.hbox_inputs = gtk.HBox()
        self.hbox_inputs.set_spacing(0)
        self.hbox_inputs.set_border_width(0)
        self.hbox_top.set_spacing(0)
        self.hbox_top.set_border_width(0)
        self.channels = []
        self.output_channels = []

        self.scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.scrolled_window.add_with_viewport(self.hbox_inputs)

        self.main_mix = MainMixChannel(self)
        self.hbox_outputs = gtk.HBox()
        self.hbox_outputs.set_spacing(0)
        self.hbox_outputs.set_border_width(0)
        frame = gtk.Frame()
        frame.add(self.main_mix)
        self.hbox_outputs.pack_start(frame, False)
        self.hbox_top.pack_start(self.hbox_outputs, False)

        self.window.connect("destroy", gtk.main_quit)

        gobject.timeout_add(80, self.read_meters)
        self.lash_client = lash_client

        if lash_client:
            gobject.timeout_add(1000, self.lash_check_events)

    def cleanup(self):
        print "Cleaning jack_mixer"
        if not self.mixer:
            return

        for channel in self.channels:
            channel.unrealize()

    def on_open_cb(self, *args):
        dlg = gtk.FileChooserDialog(title='Open', parent=self.window,
                        action=gtk.FILE_CHOOSER_ACTION_OPEN,
                        buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                 gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        dlg.set_default_response(gtk.RESPONSE_OK)
        if dlg.run() == gtk.RESPONSE_OK:
            filename = dlg.get_filename()
            try:
                f = file(filename, 'r')
                self.load_from_xml(f)
            except:
                err = gtk.MessageDialog(self.window,
                            gtk.DIALOG_MODAL,
                            gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_OK,
                            "Failed loading settings.")
                err.run()
                err.destroy()
            else:
                self.current_filename = filename
            finally:
                f.close()
        dlg.destroy()

    def on_save_cb(self, *args):
        if not self.current_filename:
            return self.on_save_as_cb()
        f = file(self.current_filename, 'w')
        self.save_to_xml(f)
        f.close()

    def on_save_as_cb(self, *args):
        dlg = gtk.FileChooserDialog(title='Save', parent=self.window,
                        action=gtk.FILE_CHOOSER_ACTION_SAVE,
                        buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                 gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        dlg.set_default_response(gtk.RESPONSE_OK)
        if dlg.run() == gtk.RESPONSE_OK:
            self.current_filename = dlg.get_filename()
            self.on_save_cb()
        dlg.destroy()

    def on_quit_cb(self, *args):
        gtk.main_quit()

    preferences_dialog = None
    def on_preferences_cb(self, widget):
        if not self.preferences_dialog:
            self.preferences_dialog = PreferencesDialog(self)
        self.preferences_dialog.show()
        self.preferences_dialog.present()

    def on_add_input_channel(self, widget):
        dialog = NewChannelDialog(app=self)
        dialog.set_transient_for(self.window)
        dialog.show()
        ret = dialog.run()
        dialog.hide()

        if ret == gtk.RESPONSE_OK:
            result = dialog.get_result()
            channel = self.add_channel(**result)
            self.window.show_all()

    def on_add_output_channel(self, widget):
        dialog = NewOutputChannelDialog(app=self)
        dialog.set_transient_for(self.window)
        dialog.show()
        ret = dialog.run()
        dialog.hide()

        if ret == gtk.RESPONSE_OK:
            result = dialog.get_result()
            channel = self.add_output_channel(**result)
            self.window.show_all()

    def on_edit_input_channel(self, widget, channel):
        print 'Editing channel "%s"' % channel.channel_name
        channel.on_channel_properties()

    def remove_channel_edit_input_menuitem_by_label(self, widget, label):
        if (widget.get_label() == label):
            self.channel_edit_input_menu.remove(widget)

    def on_remove_input_channel(self, widget, channel):
        print 'Removing channel "%s"' % channel.channel_name
        self.channel_remove_input_menu.remove(widget)
        self.channel_edit_input_menu.foreach(
            self.remove_channel_edit_input_menuitem_by_label, 
            channel.channel_name);
        if self.monitored_channel is channel:
            channel.monitor_button.set_active(False)
        for i in range(len(self.channels)):
            if self.channels[i] is channel:
                channel.unrealize()
                del self.channels[i]
                self.hbox_inputs.remove(channel.parent)
                break
        if len(self.channels) == 0:
            self.channel_remove_input_menu_item.set_sensitive(False)

    def on_edit_output_channel(self, widget, channel):
        print 'Editing channel "%s"' % channel.channel_name
        channel.on_channel_properties()

    def remove_channel_edit_output_menuitem_by_label(self, widget, label):
        if (widget.get_label() == label):
            self.channel_edit_output_menu.remove(widget)

    def on_remove_output_channel(self, widget, channel):
        print 'Removing channel "%s"' % channel.channel_name
        self.channel_remove_output_menu.remove(widget)
        self.channel_edit_output_menu.foreach(
            self.remove_channel_edit_output_menuitem_by_label, 
            channel.channel_name);
        if self.monitored_channel is channel:
            channel.monitor_button.set_active(False)
        for i in range(len(self.channels)):
            if self.output_channels[i] is channel:
                channel.unrealize()
                del self.output_channels[i]
                self.hbox_outputs.remove(channel.parent)
                break
        if len(self.output_channels) == 0:
            self.channel_remove_output_menu_item.set_sensitive(False)

    def rename_channels(self, container, parameters):
        if (container.get_label() == parameters['oldname']):
            container.set_label(parameters['newname']) 

    def on_channel_rename(self, oldname, newname):
        rename_parameters = { 'oldname' : oldname, 'newname' : newname }
        self.channel_edit_input_menu.foreach(self.rename_channels, 
            rename_parameters)
        self.channel_edit_output_menu.foreach(self.rename_channels, 
            rename_parameters)
        self.channel_remove_input_menu.foreach(self.rename_channels, 
            rename_parameters)
        self.channel_remove_output_menu.foreach(self.rename_channels, 
            rename_parameters)
        print "Renaming channel from %s to %s\n" % (oldname, newname)


    def on_channels_clear(self, widget):
        for channel in self.output_channels:
            channel.unrealize()
            self.hbox_outputs.remove(channel.parent)
        for channel in self.channels:
            channel.unrealize()
            self.hbox_inputs.remove(channel.parent)
        self.channels = []
        self.output_channels = []
        self.channel_edit_input_menu = gtk.Menu()
        self.channel_edit_input_menu_item.set_submenu(self.channel_edit_input_menu)
        self.channel_edit_input_menu_item.set_sensitive(False)
        self.channel_remove_input_menu = gtk.Menu()
        self.channel_remove_input_menu_item.set_submenu(self.channel_remove_input_menu)
        self.channel_remove_input_menu_item.set_sensitive(False)
        self.channel_edit_output_menu = gtk.Menu()
        self.channel_edit_output_menu_item.set_submenu(self.channel_edit_output_menu)
        self.channel_edit_output_menu_item.set_sensitive(False)
        self.channel_remove_output_menu = gtk.Menu()
        self.channel_remove_output_menu_item.set_submenu(self.channel_remove_output_menu)
        self.channel_remove_output_menu_item.set_sensitive(False)

    def add_channel(self, name, stereo, volume_cc, balance_cc):
        try:
            channel = InputChannel(self, name, stereo)
            self.add_channel_precreated(channel)
        except Exception:
            err = gtk.MessageDialog(self.window,
                            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                            gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_OK,
                            "Channel creation failed")
            err.run()
            err.destroy()
            return
        if volume_cc:
            channel.channel.volume_midi_cc = int(volume_cc)
        if balance_cc:
            channel.channel.balance_midi_cc = int(balance_cc)
        if not (volume_cc or balance_cc):
            channel.channel.autoset_midi_cc()

        return channel

    def add_channel_and_refresh(self, name, stereo, volume_cc, balance_cc):
        self.add_channel(name, stereo, volume_cc, balance_cc)
        self.window.show_all()
        # must return None, because otherwise gobject.idle_add will keep calling
        # this message
        return None;
    
    def newchannel_callback(self, *args):
        gobject.idle_add(self.add_channel_and_refresh, args[0], 0, 0, 0);

    def add_channel_precreated(self, channel):
        frame = gtk.Frame()
        frame.add(channel)
        self.hbox_inputs.pack_start(frame, False)
        channel.realize()

        channel_edit_menu_item = gtk.MenuItem(channel.channel_name)
        self.channel_edit_input_menu.append(channel_edit_menu_item)
        channel_edit_menu_item.connect("activate", self.on_edit_input_channel, channel)
        self.channel_edit_input_menu_item.set_sensitive(True)

        channel_remove_menu_item = gtk.MenuItem(channel.channel_name)
        self.channel_remove_input_menu.append(channel_remove_menu_item)
        channel_remove_menu_item.connect("activate", self.on_remove_input_channel, channel)
        self.channel_remove_input_menu_item.set_sensitive(True)

        self.channels.append(channel)

        for outputchannel in self.output_channels:
            channel.add_control_group(outputchannel)

        # create post fader output channel matching the input channel
        channel.post_fader_output_channel = self.mixer.add_output_channel(
                        channel.channel.name + ' Out', channel.channel.is_stereo, True)
        channel.post_fader_output_channel.volume = 0
        channel.post_fader_output_channel.set_solo(channel.channel, True)

    def read_meters(self):
        for channel in self.channels:
            channel.read_meter()
        self.main_mix.read_meter()
        for channel in self.output_channels:
            channel.read_meter()
        return True

    def add_output_channel(self, name, stereo, volume_cc, balance_cc, display_solo_buttons):
        try:
            channel = OutputChannel(self, name, stereo)
            channel.display_solo_buttons = display_solo_buttons
            self.add_output_channel_precreated(channel)
        except Exception:
            err = gtk.MessageDialog(self.window,
                            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                            gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_OK,
                            "Channel creation failed")
            err.run()
            err.destroy()
            return
        if volume_cc:
            channel.channel.volume_midi_cc = int(volume_cc)
        if balance_cc:
            channel.channel.balance_midi_cc = int(balance_cc)
        return channel

    def add_output_channel_precreated(self, channel):
        frame = gtk.Frame()
        frame.add(channel)
        self.hbox_outputs.pack_start(frame, False)
        channel.realize()

        channel_edit_menu_item = gtk.MenuItem(channel.channel_name)
        self.channel_edit_output_menu.append(channel_edit_menu_item)
        channel_edit_menu_item.connect("activate", self.on_edit_output_channel, channel)
        self.channel_edit_output_menu_item.set_sensitive(True)

        channel_remove_menu_item = gtk.MenuItem(channel.channel_name)
        self.channel_remove_output_menu.append(channel_remove_menu_item)
        channel_remove_menu_item.connect("activate", self.on_remove_output_channel, channel)
        self.channel_remove_output_menu_item.set_sensitive(True)

        self.output_channels.append(channel)

    _monitored_channel = None
    def get_monitored_channel(self):
        return self._monitored_channel

    def set_monitored_channel(self, channel):
        if self._monitored_channel:
            if channel.channel.name == self._monitored_channel.channel.name:
                return
        self._monitored_channel = channel
        if type(channel) is InputChannel:
            # reset all solo/mute settings
            for in_channel in self.channels:
                self.monitor_channel.set_solo(in_channel.channel, False)
                self.monitor_channel.set_muted(in_channel.channel, False)
            self.monitor_channel.set_solo(channel.channel, True)
            self.monitor_channel.prefader = True
        else:
            self.monitor_channel.prefader = False
        self.update_monitor(channel)
    monitored_channel = property(get_monitored_channel, set_monitored_channel)

    def update_monitor(self, channel):
        if self.monitored_channel is not channel:
            return
        self.monitor_channel.volume = channel.channel.volume
        self.monitor_channel.balance = channel.channel.balance
        if type(self.monitored_channel) is OutputChannel:
            # sync solo/muted channels
            for input_channel in self.channels:
                self.monitor_channel.set_solo(input_channel.channel,
                                channel.channel.is_solo(input_channel.channel))
                self.monitor_channel.set_muted(input_channel.channel,
                                channel.channel.is_muted(input_channel.channel))
        elif type(self.monitored_channel) is MainMixChannel:
            # sync solo/muted channels
            for input_channel in self.channels:
                self.monitor_channel.set_solo(input_channel.channel,
                                input_channel.channel.solo)
                self.monitor_channel.set_muted(input_channel.channel,
                                input_channel.channel.mute)

    def get_input_channel_by_name(self, name):
        for input_channel in self.channels:
            if input_channel.channel.name == name:
                return input_channel
        return None

    def on_about(self, *args):
        about = gtk.AboutDialog()
        about.set_name('jack_mixer')
        about.set_copyright('Copyright © 2006-2009\nNedko Arnaudov, Frederic Peters')
        about.set_license('''\
jack_mixer is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 2 of the License, or (at your
option) any later version.

jack_mixer is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License along
with jack_mixer; if not, write to the Free Software Foundation, Inc., 51
Franklin Street, Fifth Floor, Boston, MA 02110-130159 USA''')
        about.set_authors(['Nedko Arnaudov <nedko@arnaudov.name>',
                           'Frederic Peters <fpeters@0d.be>'])
        about.set_logo_icon_name('jack_mixer')
        about.set_website('http://home.gna.org/jackmixer/')

        about.run()
        about.destroy()

    def lash_check_events(self):
        while lash.lash_get_pending_event_count(self.lash_client):
            event = lash.lash_get_event(self.lash_client)

            #print repr(event)

            event_type = lash.lash_event_get_type(event)
            if event_type == lash.LASH_Quit:
                print "jack_mixer: LASH ordered quit."
                gtk.main_quit()
                return False
            elif event_type == lash.LASH_Save_File:
                directory = lash.lash_event_get_string(event)
                print "jack_mixer: LASH ordered to save data in directory %s" % directory
                filename = directory + os.sep + "jack_mixer.xml"
                f = file(filename, "w")
                self.save_to_xml(f)
                f.close()
                lash.lash_send_event(self.lash_client, event) # we crash with double free
            elif event_type == lash.LASH_Restore_File:
                directory = lash.lash_event_get_string(event)
                print "jack_mixer: LASH ordered to restore data from directory %s" % directory
                filename = directory + os.sep + "jack_mixer.xml"
                f = file(filename, "r")
                self.load_from_xml(f, silence_errors=True)
                f.close()
                lash.lash_send_event(self.lash_client, event)
            else:
                print "jack_mixer: Got unhandled LASH event, type " + str(event_type)
                return True

            #lash.lash_event_destroy(event)

        return True

    def save_to_xml(self, file):
        #print "Saving to XML..."
        b = XmlSerialization()
        s = Serializator()
        s.serialize(self, b)
        b.save(file)

    def load_from_xml(self, file, silence_errors=False):
        #print "Loading from XML..."
        self.on_channels_clear(None)
        self.unserialized_channels = []
        b = XmlSerialization()
        try:
            b.load(file)
        except:
            if silence_errors:
                return
            raise
        s = Serializator()
        s.unserialize(self, b)
        for channel in self.unserialized_channels:
            if isinstance(channel, InputChannel):
                self.add_channel_precreated(channel)
        for channel in self.unserialized_channels:
            if isinstance(channel, OutputChannel):
                self.add_output_channel_precreated(channel)
        del self.unserialized_channels
        self.window.show_all()

    def serialize(self, object_backend):
        object_backend.add_property('geometry',
                        '%sx%s' % (self.window.allocation.width, self.window.allocation.height))

    def unserialize_property(self, name, value):
        if name == 'geometry':
            width, height = value.split('x')
            self.window.resize(int(width), int(height))
            return True

    def unserialize_child(self, name):
        if name == MainMixChannel.serialization_name():
            return self.main_mix

        if name == InputChannel.serialization_name():
            channel = InputChannel(self, "", True)
            self.unserialized_channels.append(channel)
            return channel

        if name == OutputChannel.serialization_name():
            channel = OutputChannel(self, "", True)
            self.unserialized_channels.append(channel)
            return channel

    def serialization_get_childs(self):
        '''Get child objects tha required and support serialization'''
        childs = self.channels[:] + self.output_channels[:]
        childs.append(self.main_mix)
        return childs

    def serialization_name(self):
        return "jack_mixer"

    def main(self):
        self.main_mix.realize()
        self.main_mix.set_monitored()

        if not self.mixer:
            return

        self.window.show_all()

        gtk.main()

        #f = file("/dev/stdout", "w")
        #self.save_to_xml(f)
        #f.close

def help():
    print "Usage: %s [mixer_name]" % sys.argv[0]

def main():
    # Connect to LASH if Python bindings are available, and the user did not
    # pass --no-lash
    if lash and not '--no-lash' in sys.argv:
        # sys.argv is modified by this call
        lash_client = lash.init(sys.argv, "jack_mixer", lash.LASH_Config_File)
    else:
        lash_client = None

    parser = OptionParser()
    parser.add_option('-c', '--config', dest='config',
                      help='use a non default configuration file')
    # --no-lash here is not acted upon, it is specified for completeness when
    # --help is passed.
    parser.add_option('--no-lash', dest='nolash', action='store_true',
                      help='do not connect to LASH')
    options, args = parser.parse_args()

    # Yeah , this sounds stupid, we connected earlier, but we dont want to show this if we got --help option
    # This issue should be fixed in pylash, there is a reason for having two functions for initialization after all
    if lash_client:
        print "Successfully connected to LASH server at " +  lash.lash_get_server_name(lash_client)

    if len(args) == 1:
        name = args[0]
    else:
        name = None

    if not name:
        name = "jack_mixer"

    gtk.gdk.threads_init()
    try:
        mixer = JackMixer(name, lash_client)
    except Exception, e:
        err = gtk.MessageDialog(None,
                            gtk.DIALOG_MODAL,
                            gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_OK,
                            "Mixer creation failed (%s)" % str(e))
        err.run()
        err.destroy()
        sys.exit(1)

    if options.config:
        f = file(options.config)
        mixer.current_filename = options.config
        try:
            mixer.load_from_xml(f)
        except:
            err = gtk.MessageDialog(mixer.window,
                            gtk.DIALOG_MODAL,
                            gtk.MESSAGE_ERROR,
                            gtk.BUTTONS_OK,
                            "Failed loading settings.")
            err.run()
            err.destroy()
        mixer.window.set_default_size(60*(1+len(mixer.channels)+len(mixer.output_channels)), 300)
        f.close()

    mixer.main()

    mixer.cleanup()

if __name__ == "__main__":
    main()
