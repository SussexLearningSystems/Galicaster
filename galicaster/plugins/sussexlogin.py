# sussexlogin galicaster plugin
#
# Copyright 2013 University of Sussex
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

"""

import gst
import gtk
import pango
import requests
import time
import xml.etree.ElementTree as ET
from galicaster.core import context
from galicaster.classui import get_ui_path, get_image_path
from galicaster.classui.elements.message_header import Header
from galicaster.mediapackage.mediapackage import Mediapackage
from operator import itemgetter

sussex_login_dialog = None
hidden_time = 0
waiting_for_details = False
trigger_recording = None

#defaults 
timeout = 300 #5 mins
cam_profile = 'cam'
nocam_profile = 'nocam'

logger = context.get_logger()
conf = context.get_conf()

def init():
    global timeout
    global cam_profile
    global nocam_profile
    try:
        dispatcher = context.get_dispatcher()
        dispatcher.connect('galicaster-status', event_change_mode)
        dispatcher.connect('stop-record', show_login)
        dispatcher.connect('restart-preview', show_login)
        dispatcher.connect('galicaster-notify-timer-short', check_timeout)
        dispatcher.connect('update-pipeline-status', on_update_pipeline)
        
    except ValueError:
        pass
    
    timeout = int(conf.get('sussexlogin', 'timeout')) or timeout
    logger.info("timeout set to: %d", timeout)
    
    cam_profile = conf.get('sussexlogin', 'cam_profile') or cam_profile
    logger.info("cam_profile set to: %s", cam_profile)
        
    nocam_profile = conf.get('sussexlogin', 'nocam_profile') or nocam_profile
    logger.info("nocam_profile set to: %s", nocam_profile)
    
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
    if not context.get_state().is_recording and not waiting_for_details:
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
        liststore = liststore = gtk.ListStore(str,str)
        liststore.append(['', ''])
        if u:
            presenter = gui.get_object('xpresent')
            presenter.set_text(u['user_name'])
            
            if u['pic']:
                photo = gui.get_object('xphoto')
                photo.set_from_pixbuf(u['pic'])
            
            if u['modules']:
                #sort modules by name before adding to liststore
                for series_id, series_name in sorted(u['modules'].items(), key=itemgetter(1)):
                    liststore.append([series_name, series_id])
    
        cell = gtk.CellRendererText()
        
        self.module = gtk.ComboBox(liststore)
        self.module.pack_start(cell, True)
        self.module.add_attribute(cell, 'text', 0)

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
            mod = None
            iter = self.module.get_active_iter()
            if iter:
                mod = liststore.get(iter, 0, 1)
            name = gui.get_object('xtitle').get_text()
            cam = gui.get_object('xcamera').get_active()
            profile = cam_profile if cam else nocam_profile
            start_recording(u, name, mod, profile)

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
                u['modules'][mod_fullcode] = row_temp['module']
            
        except Exception as e:
             logger.error('Looks like the web service XML is broken (or user name is invalid)')

        return u
        
def start_recording(user, title, module, profile):
    """
    start a recording by adding a mediapackage to the repo with the correct metadata
    then emitting a 'start-before' signal.
    """
    global trigger_recording
    repo = context.get_repository()
    if user:
        pres = user['user_name']
        user_id = user['user_id']
    else:
        pres = ''
        user_id = ''
    mp = Mediapackage(title=title, presenter=pres)
    mp.setMetadataByName('rightsHolder', user_id)
    if module:
        series = {'title': module[0], 'identifier': module[1]}
        pub = conf.get('sussexlogin', 'publisher')
        series['publisher'] = pub
        mp.setSeries(series)
    room = conf.get('sussexlogin', 'room_name')
    mp.setMetadataByName('spatial', room)
    repo.add(mp)

    conf.change_current_profile(profile)
    conf.update()
    dispatcher = context.get_dispatcher()
    dispatcher.emit('reload-profile')
    trigger_recording = mp.getIdentifier()
    
def on_update_pipeline(source, old, new):
    global trigger_recording
    if trigger_recording and (old, new) == (gst.STATE_PAUSED, gst.STATE_PLAYING):
        context.get_dispatcher().emit('start-before', trigger_recording)
        trigger_recording = None
