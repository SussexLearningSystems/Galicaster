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

import dbus
import subprocess
import time

from galicaster.core import context

logger = context.get_logger()
dispatcher = context.get_dispatcher()
conf = context.get_conf()

cookie = None
idle_delay = 20
hourly_wake = False
hourly_wake_from = 8
hourly_wake_to = 17
hourly_wake_minute = 50

# set up dbus stuff
dbus_session = dbus.SessionBus()
bus_name = "org.mate.ScreenSaver"
object_path = "/org/mate/ScreenSaver"
screen_saver = dbus_session.get_object(bus_name, object_path)
ss_inhibit = screen_saver.get_dbus_method('Inhibit')
ss_uninhibit = screen_saver.get_dbus_method('UnInhibit')

def init():
    global idle_delay, hourly_wake, hourly_wake_from, hourly_wake_to, hourly_wake_minute
    idle_delay = conf.get_int('sussexscreensaver', 'idle_delay') or 20
    logger.debug('idle_delay set to %i', idle_delay)

    hourly_wake = conf.get_boolean('sussexscreensaver', 'hourly_wake') or False
    logger.debug('hourly_wake set to %s', hourly_wake)

    hourly_wake_from = conf.get_int('sussexscreensaver', 'hourly_wake_from') or 8
    logger.debug('hourly_wake_from set to %i', hourly_wake_from)

    hourly_wake_to = conf.get_int('sussexscreensaver', 'hourly_wake_to') or 17
    logger.debug('hourly_wake_to set to %i', hourly_wake_to)

    hourly_wake_minute = conf.get_int('sussexscreensaver', 'hourly_wake_minute') or 50
    logger.debug('hourly_wake_minute set to %i', hourly_wake_minute)

    subprocess.call(['dconf', 'write', '/org/mate/desktop/session/idle-delay', '%i' % idle_delay]) 
    wake_screen()
    dispatcher.connect('starting-record', inhibit)
    dispatcher.connect('restart-preview', uninhibit)
    dispatcher.connect('galicaster-notify-quit', uninhibit)
    dispatcher.connect('galicaster-quit', uninhibit)
    dispatcher.connect('galicaster-notify-timer-long', pre_lecture_wake)

def inhibit(signal=None):
    global cookie
    if cookie is None:
        logger.debug('Inhibiting screensaver')
        cookie = ss_inhibit('Galicaster', 'Recording')

def uninhibit(signal=None):
    global cookie
    if cookie is not None:
        logger.debug('Un-inhibiting screensaver')
        ss_uninhibit(cookie)
        cookie = None

def pre_lecture_wake(signal=None):
    now = time.localtime()
    if (hourly_wake and now.tm_hour >= hourly_wake_from 
                    and now.tm_hour <= hourly_wake_to 
                    and now.tm_min == hourly_wake_minute):
        wake_screen()

def wake_screen(signal=None):
    logger.debug('waking!')
    # bodge as nothing sensible seems to work
    subprocess.call(['xdotool', 'keydown',  'control',  'keyup', 'control'])