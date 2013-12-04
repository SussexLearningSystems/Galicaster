# -*- coding:utf-8 -*-
# Galicaster, Multistream Recorder and Player
#
#       galicaster/plugins/screensaver
#
# Copyright (c) 2012, Teltek Video Research <galicaster@teltek.es>
#
# This work is licensed under the Creative Commons Attribution-
# NonCommercial-ShareAlike 3.0 Unported License. To view a copy of 
# this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/ 
# or send a letter to Creative Commons, 171 Second Street, Suite 300, 
# San Francisco, California, 94105, USA.

"""
inhibit mate-screensaver when recording.

power management should still be turned off manually for now.
"""

import os
import dbus
from dbus.mainloop.glib import DBusGMainLoop
#from gi.repository import Gio
from galicaster.core import context

logger = context.get_logger()
dispatcher = context.get_dispatcher()

cookie = None
idle_delay = 5

def init():
    idle_delay = context.get_conf().get('sussexscreensaver', 'idle_delay')

    #dconf_session = Gio.Settings.new("org.mate.session")
    #dconf_session.set_int('idle-delay', idle_delay)

    os.system('dconf write /org/mate/desktop/session/idle-delay ' + idle_delay) 
    dispatcher.connect('upcoming-recording', inhibit_and_poke)
    dispatcher.connect('starting-record', inhibit)
    dispatcher.connect('restart-preview', uninhibit)
    dispatcher.connect('galicaster-notify-quit', uninhibit)
    dispatcher.connect('galicaster-quit', uninhibit)

def get_screensaver_method(method):
    dbus_loop = DBusGMainLoop()
    session = dbus.SessionBus(mainloop=dbus_loop)
    bus_name = "org.mate.ScreenSaver"
    object_path = "/org/mate/ScreenSaver"
    screen_saver = session.get_object(bus_name, object_path)
    return screen_saver.get_dbus_method(method)

def inhibit(signal=None):
    global cookie
    if cookie is None:
        logger.debug('Inhibiting screensaver')
        ss_inhibit = get_screensaver_method('Inhibit')
        cookie = ss_inhibit('Galicaster', 'Recording')

def uninhibit(signal=None):
    global cookie
    if cookie is not None:
        logger.debug('Un-inhibiting screensaver')
        ss_uninhibit = get_screensaver_method('UnInhibit')
        ss_uninhibit(cookie)
        cookie = None

def poke_screen(signal=None):
    poke = get_screensaver_method('SimulateUserActivity')
    a = poke() 


def inhibit_and_poke(signal=None):
    inhibit()
    poke_screen()