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
import requests
import time
import xml.etree.ElementTree as ET
from galicaster.core import context
from galicaster.classui import get_ui_path, get_image_path
from galicaster.classui.elements.message_header import Header
from galicaster.classui.metadata import ComboBoxEntryExt

sussex_login_dialog = None
hidden_time = 0
waiting_for_details = False

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
    global waiting_for_details
    now = int(time.time())
    status = context.get_state()
    if (now - hidden_time >= timeout and status.area == 0 
        and not waiting_for_details and not status.is_recording):
        waiting_for_details = True
        show_login()


def event_change_mode(orig, old_state, new_state):
    """
    On changing mode, if the new area is right, shows dialog if necessary
    """
    global sussex_login_dialog
    status = context.get_state().get_all()
    
    if new_state == 0: 
        if not status['is-recording']:
            show_login()

    if old_state == 0:
        sussex_login_dialog.hide()


def show_login(element=None):
    """
    Called up when switching to record mode or recording ended, shows the dialog if necessary
    """
    global sussex_login_dialog
    global waiting_for_details
    if sussex_login_dialog:
        pass
    else:
        sussex_login_dialog = LoginDialog()
    waiting_for_details = True
    sussex_login_dialog.show() 
    return True

   
class LoginDialog(gtk.Dialog):
    def __init__(self):
        """
        Creates the Sussex Login interface
        """
        parent = context.get_mainwindow().get_toplevel()
        super(LoginDialog, self).__init__("Log In", parent)
        
    
        #Properties
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_TOOLBAR)
        self.set_skip_taskbar_hint(True)
        self.set_modal(True)
        self.set_accept_focus(True)
        self.set_destroy_with_parent(True)
    
    
        size = parent.get_size()
        self.set_property('width-request',int(size[0]/3)) 
        if size[0] < 1300:
            self.set_property('width-request',int(size[0]/2.3)) 
        wprop = size[0]/1920.0
        hprop = size[1]/1080.0
        self.set_position(gtk.WIN_POS_CENTER_ON_PARENT)
        self.action_area.set_layout(gtk.BUTTONBOX_SPREAD)
    
        #Buttons
        login_button = self.add_button("Log In",2)
        login_button.connect("clicked", self.do_login)
        for child in self.action_area.get_children():
            child.set_property("width-request", int(wprop*170) )
            child.set_property("height-request", int(hprop*70) )
            child.set_can_focus(False)
    
        #Taskbar with logo
        strip = Header(size=size, title="Log In")
        self.vbox.pack_start(strip, False, True, 0)
        strip.show()
    
        #Labels
        label1 = gtk.Label("Username:")
        self.login = gtk.Entry()
        self.login.set_editable(gtk.TRUE)
        self.login.set_can_focus(gtk.TRUE)
        self.login.set_activates_default(gtk.TRUE)
        self.login.activate()
        desc1 = str(int(hprop*32))+"px"
        font1=pango.FontDescription(desc1)
        label1.modify_font(font1)
        label1.set_alignment(0.5,0.5)
        # Warning icon
        box = gtk.HBox(spacing=0) # between image and text
        box.pack_start(label1,True,True,0)  
        box.pack_start(self.login,True,True,0)  
        box.show()
        self.action_area.set_property('spacing',int(hprop*20))
        self.vbox.pack_start(box, True, False, 0)
        #ui.vbox.pack_start(label2, True, False, 0)
        resize_buttons(self.action_area,int(wprop*25),True)
        self.vbox.set_child_packing(self.action_area, True, True, int(hprop*25), gtk.PACK_END)
        self.login.show()
        label1.show()

    def do_login(self, button):
        """
        Called when you press the login button
        """
        self.hide()
        EnterDetails(self.login.get_text())
        

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

class EnterDetails(gtk.Widget):
    """
    Handle enter details dialog
    """
    __gtype_name__ = 'EnterDetails'

    def __init__(self, user=""):
        global hidden_time
        global waiting_for_details

        parent = context.get_mainwindow()
        size = parent.get_size()
            
        self.par = parent
        altura = size[1]
        anchura = size[0]        
        k1 = anchura / 1920.0                                      
        k2 = altura / 1080.0
        self.wprop = k1
        self.hprop = k2

        gui = gtk.Builder()
        gui.add_from_file(get_ui_path('enterdetails.glade'))

        dialog = gui.get_object("enterdetailsdialog")
        dialog.set_property("width-request",int(anchura/2.2))
        dialog.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_TOOLBAR)
        dialog.set_keep_above(True)

        #NEW HEADER
        strip = Header(size=size, title="Edit Metadata")
        dialog.vbox.pack_start(strip, True, True, 0)
        dialog.vbox.reorder_child(strip,0)


        if parent != None:
            dialog.set_transient_for(parent.get_toplevel())

        u = get_user_details(user)
        
        presenter = gui.get_object('xpresent')
        presenter.set_text(u['user_name'])
        
        if u['pic']:
            photo = gui.get_object('xphoto')
            photo.set_from_pixbuf(u['pic'])
        
        self.module = ComboBoxEntryExt(self.par, u['modules'], '')
        table = gui.get_object('infobox')
        table.attach(self.module,1,2,2,3,gtk.EXPAND|gtk.FILL,False,0,0)

        dialog.vbox.set_child_packing(table, True, True, int(self.hprop*25), gtk.PACK_END)    
        title = gui.get_object('title')
        talign = gui.get_object('table_align')

        modification = "bold "+str(int(k2*25))+"px"        
        title.modify_font(pango.FontDescription(modification))
        title.hide()
        talign.set_padding(int(k2*40),int(k2*40),0,0)
        mod2 = str(int(k1*35))+"px"        


        talign.set_padding(int(self.hprop*25), int(self.hprop*10), int(self.hprop*25), int(self.hprop*25))
        dialog.vbox.set_child_packing(dialog.action_area, True, True, int(self.hprop*25), gtk.PACK_END)   
        
        dialog.show_all()

        return_value = dialog.run()
        if return_value == -8:
            pass
            #self.update_metadata(table,package)

        hidden_time = int(time.time())
        waiting_for_details = False
        dialog.destroy()

def get_user_details(user=None):
    """
    look up user info/courses in web service
    """
    if user:
        u = {}
        try:
            conf = context.get_conf()
            ws = conf.get('sussexlogin', 'ws')
            pic_urls = conf.get('sussexlogin', 'pic_urls').split('|')
            url = ws % user
            logger.debug(url)
        except:
            logger.error('No web service url specified in config')

        try:
            r = requests.get(url)
        except requests.exceptions.RequestException:
            logger.error('Error getting data from web service')
        
        try:
            xml = ET.fromstring(r.text)
            sub = xml.find('subtitle').text.split('/')
            u['user_id'] = user
            u['user_name'] = sub[0].strip()
            u['person_id'] = sub[1].strip()
            u['pic_flag'] = int(sub[2].strip())
            u['pic'] = None

            if not u['pic_flag']:
                for pic_url in pic_urls:
                    logger.debug(pic_url % u['person_id'])
                    r = requests.get(pic_url % u['person_id'])
                    if r.status_code == 200:
                        loader = gtk.gdk.PixbufLoader()
                        loader.write(r.content)
                        loader.close()
                        u['pic'] = loader.get_pixbuf()
                        break
        
            u['modules'] = {}
            for row in xml.findall('row'):
                row_temp = {}
                for field in row.findall('field'):
                    row_temp[field.find('name').text] = field.find('value').text
                mod_fullcode = row_temp['course_code'] + '__' + row_temp['occurrence_code']
                u['modules'][mod_fullcode] = {'title': row_temp['module']}
            
        except Exception as e:
             logger.error('Looks like the web service XML is broken (or user name is invalid)')

        return u
        

def notify(*args, **kwargs):
    print args, kwargs
    print context.get_state().get_all()