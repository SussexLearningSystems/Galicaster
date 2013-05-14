# -*- coding:utf-8 -*-
# Galicaster, Multistream Recorder and Player
#
#       galicaster/plugins/sussexlogin
#
# Copyright (c) 2013, Teltek Video Research <galicaster@teltek.es>
#
# This work is licensed under the Creative Commons Attribution-
# NonCommercial-ShareAlike 3.0 Unported License. To view a copy of 
# this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/ 
# or send a letter to Creative Commons, 171 Second Street, Suite 300, 
# San Francisco, California, 94105, USA.

"""

"""

import gtk
import pango
import time
from galicaster.core import context
from galicaster.classui import get_ui_path, get_image_path
from galicaster.classui.elements.message_header import Header

sussex_login_dialog = None
hidden_time = 0

#default 5 mins
timeout = 300

logger = context.get_logger()

def init():
    try:
        dispatcher = context.get_dispatcher()
        dispatcher.connect('galicaster-status', event_change_mode)
        dispatcher.connect('stop-record', show_login)
        dispatcher.connect('restart-preview', show_login)
        dispatcher.connect('galicaster-notify-timer-short', check_timeout)
        
    except ValueError:
        pass
    
    try:
        global timeout
        conf = context.get_conf()
        timeout = int(conf.get('sussexlogin', 'timeout'))
    except ValueError:
        #use default
        pass
    logger.info("timeout set to: %d", timeout)
    
def check_timeout(dispatcher):
    """
    Pop up login dialog if timeout has elapsed and no recording is in progress
    """ 
    now = int(time.time())
    status = context.get_state()
    if now - hidden_time >= timeout and status.area == 0 and not status.is_recording:
        show_login()


def event_change_mode(orig, old_state, new_state):
    """
    On changing mode, if the new area is right, shows dialog if necessary
    """
    global sussex_login_dialog
    global hidden_time
    status = context.get_state().get_all()
    
    if new_state == 0: 
        if not status['is-recording']:
            show_login()

    if old_state == 0:
        hidden_time = int(time.time())
        sussex_login_dialog.hide()

def show_login(element=None):
    """
    Called up when switching to record mode or recording ended, shows the dialog if necessary
    """
    global sussex_login_dialog
    if sussex_login_dialog:
        pass
    else:
        sussex_login_dialog = create_ui()
    sussex_login_dialog.show() 
    return True

def do_login(button):
    """
    Called when you press the login button
    """
    global hidden_time
    hidden_time = int(time.time())
    sussex_login_dialog.hide()

def create_ui():
    """
    Creates the No Audio Dialog interface
    """
    parent =  context.get_mainwindow().get_toplevel()
    ui = gtk.Dialog("Warning", parent)

    #Properties
    ui.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_TOOLBAR)
    ui.set_skip_taskbar_hint(True)
    ui.set_modal(True)
    ui.set_accept_focus(True)
    ui.set_destroy_with_parent(True)


    size = parent.get_size()
    ui.set_property('width-request',int(size[0]/3)) 
    if size[0] < 1300:
        ui.set_property('width-request',int(size[0]/2.3)) 
    wprop = size[0]/1920.0
    hprop = size[1]/1080.0
    ui.set_position(gtk.WIN_POS_CENTER_ON_PARENT)
    ui.action_area.set_layout(gtk.BUTTONBOX_SPREAD)

    #Buttons
    conf = context.get_conf()
    login_button = ui.add_button("Log In",2)
    login_button.connect("clicked", do_login)
    for child in ui.action_area.get_children():
        child.set_property("width-request", int(wprop*170) )
        child.set_property("height-request", int(hprop*70) )
        child.set_can_focus(False)

    #Taskbar with logo
    strip = Header(size=size, title="Log In")
    ui.vbox.pack_start(strip, False, True, 0)
    strip.show()

    #Labels
    label1 = gtk.Label("Username:")
    login = gtk.Entry()
    login.set_editable(gtk.TRUE)
    login.set_can_focus(gtk.TRUE)
    login.set_activates_default(gtk.TRUE)
    login.activate()
    desc1 = "bold " + str(int(hprop*32))+"px"
    font1=pango.FontDescription(desc1)
    label1.modify_font(font1)
    label1.set_alignment(0.5,0.5)
    # Warning icon
    box = gtk.HBox(spacing=0) # between image and text
    box.pack_start(label1,True,True,0)  
    box.pack_start(login,True,True,0)  
    box.show()
    ui.action_area.set_property('spacing',int(hprop*20))
    ui.vbox.pack_start(box, True, False, 0)
    #ui.vbox.pack_start(label2, True, False, 0)
    resize_buttons(ui.action_area,int(wprop*25),True)
    ui.vbox.set_child_packing(ui.action_area, True, True, int(hprop*25), gtk.PACK_END)
    login.show()
    label1.show()
    return ui

def set_font(description):
        """Asign a font description to a text"""
        alist = pango.AttrList()
        font=pango.FontDescription(description)
        attr=pango.AttrFontDesc(font,0,-1)
        alist.insert(attr)
        return alist

def resize_buttons(area, fsize, equal = False):    
        """Adapts buttons to the dialog size"""
        font = set_font("bold "+str(fsize)+"px")
        for button in area.get_children():
            for element in button.get_children():
                if type(element) == gtk.Label:
                    element.set_attributes(font)
                    if equal:
                        element.set_padding(-1,int(fsize/2.6))

def notify(*args, **kwargs):
    print args, kwargs
    print context.get_state().get_all()
    