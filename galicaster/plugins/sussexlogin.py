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

#defaults 
cam_available = True
cam_profile = 'cam'
nocam_profile = 'nocam'
fsize = 50

sussex_login_dialog = None
waiting_for_details = False
trigger_recording = None
switching_profile = False
profile = nocam_profile
ed = None

logger = context.get_logger()
conf = context.get_conf()
dispatcher = context.get_dispatcher()
is_admin = conf.is_admin_blocked()

def init():
    global timeout
    global cam_available, cam_profile, nocam_profile
    global fsize
    try:
        dispatcher.connect('galicaster-status', event_change_mode)
        dispatcher.connect('restart-preview', show_login)
        dispatcher.connect('update-pipeline-status', on_update_pipeline)
        
    except ValueError:
        pass

    cam_available = conf.get('sussexlogin', 'cam_available') or cam_available
    cam_available = True if cam_available in ('True', 'true', True) else False
    logger.info("cam_available set to: %r", cam_available)
        
    cam_profile = conf.get('sussexlogin', 'cam_profile') or cam_profile
    logger.info("cam_profile set to: %s", cam_profile)

    nocam_profile = conf.get('sussexlogin', 'nocam_profile') or nocam_profile
    logger.info("nocam_profile set to: %s", nocam_profile)

    fsize = conf.get('sussexlogin', 'font_size') or fsize
    fsize = int(fsize)
    logger.info("font_size set to: %s", fsize)


def event_change_mode(orig, old_state, new_state):
    """
    On changing mode, if the new area is right, shows dialog if necessary
    """
    global sussex_login_dialog
    
    if new_state == 0: 
        if not context.get_state().is_recording:
            show_login()

    if old_state == 0:
        sussex_login_dialog.hide()


def show_login(element=None):
    """
    Called up when switching to record mode or recording ended, shows the dialog if necessary
    """
    global sussex_login_dialog
    global waiting_for_details
    if (not context.get_state().is_recording and 
        not waiting_for_details and
        context.get_state().area == 0 and
        context.get_state().status == 'Preview'):
        if sussex_login_dialog:
            pass
        else:
            sussex_login_dialog = LoginDialog()
        waiting_for_details = True
        recorder_ui = context.get_mainwindow().nbox.get_nth_page(0).gui
        recorder_ui.get_object('recording1').set_text('Not recording')
        recorder_ui.get_object('recording3').set_text('')
        if cam_available:
            switch_profile(cam_profile)
        elif (profile == cam_profile) or not cam_available:
            switch_profile(nocam_profile)
        sussex_login_dialog.login.set_text('')
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
    
        font = "%dpx" % (hprop * fsize)
        fdesc = pango.FontDescription(font)
        attr = set_font(font)

        #Buttons
        login_button = self.add_button("Log In",2)
        login_button.child.set_attributes(attr)
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
        label1.modify_font(fdesc)
        label1.set_alignment(0.5,0.5)

        login = gtk.Entry()
        login.set_editable(gtk.TRUE)
        login.set_can_focus(gtk.TRUE)
        login.set_activates_default(gtk.TRUE)
        login.set_text('')
        login.activate()
        login.modify_font(fdesc)
        self.login = login
        
        # Warning icon
        box = gtk.HBox(spacing=0) # between image and text
        box.pack_start(label1, True, True, 0)  
        box.pack_start(self.login, True, True, 0)  
        box.show()

        self.action_area.set_property('spacing',int(hprop*20))
        self.vbox.pack_start(box, True, False, 0)

        self.vbox.set_child_packing(self.action_area, True, True, int(hprop*25), gtk.PACK_END)
        self.login.show()
        label1.show()

        # listen for key presses
        self.add_events(gtk.gdk.KEY_PRESS_MASK)
        self.connect('key-press-event', self.eat_escape)

    def do_login(self, button):
        """
        Called when you press the login button
        """
        global ed
        self.hide()
        ed = EnterDetails(self.login.get_text())

    # ignore escape presses
    def eat_escape(self, widget, event):
        return event.keyval == 65307

def set_font(description):
        """Asign a font description to a text"""
        alist = pango.AttrList()
        font=pango.FontDescription(description)
        attr=pango.AttrFontDesc(font,0,-1)
        alist.insert(attr)
        return alist

class EnterDetails(gtk.Window):
    """
    Handle enter details dialog
    """
    __gtype_name__ = 'EnterDetails'

    def __init__(self, user=''):
        gtk.Window.__init__(self)
        global waiting_for_details

        parent = context.get_mainwindow()
            
        self.par = parent
        width, height = parent.get_size()
        self.wprop = width / 1920.0                                      
        self.hprop = height / 1080.0
        
        font = '%dpx' % (self.wprop * fsize)
        fdesc = pango.FontDescription(font)
        attr = set_font(font)

        self.set_property("width-request", width)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_TOOLBAR)
        self.set_keep_above(True)
        self.set_position(gtk.WIN_POS_NONE)
        self.set_modal(True)

        vbox = gtk.VBox()
        vbox2 = gtk.VBox()
        hbox = gtk.HBox()
        hbox2 = gtk.HBox()
        hbox3 = gtk.HBox()

        liststore = liststore = gtk.ListStore(str,str)
        self.liststore = liststore
        liststore.append(['Choose a Module...', ''])
        presenter = "Enter Details"
        photo = gtk.Image()
        
        self.u = None 
        u = get_user_details(user)
        if u:
            self.u = u
            presenter = u['user_name']
             
            if u['pic']:
                photo.set_from_pixbuf(u['pic'])
             
            if u['modules']:
                #sort modules by name before adding to liststore
                for series_id, series_name in sorted(u['modules'].items(), key=itemgetter(1)):
                    liststore.append([series_name, series_id])
 
        strip = Header(size=(width, height), title=presenter)
        vbox.pack_start(strip, True, True, 0)

        cell = gtk.CellRendererText()
        cell.set_property('font-desc', fdesc)
        self.module = gtk.ComboBox(liststore)
        self.module.pack_start(cell, True)
        self.module.add_attribute(cell, 'text', 0)
        self.module.set_active(0)

        title = PlaceholderEntry(placeholder='Enter a title here...')
        title.modify_font(fdesc)
        self.t = title

        if cam_available:
            cam = gtk.CheckButton(label='Camera')
            cam.connect('clicked', self._toggled)
            cam.child.set_attributes(attr)
            self.cam = cam
        
        rec_image = gtk.Image()
        icon = gtk.icon_theme_get_default().load_icon('media-record', 
                                                      int(fsize * 1.5), 
                                                      gtk.ICON_LOOKUP_FORCE_SVG)
        rec_image.set_from_pixbuf(icon)
        rec_image.set_alignment(1.0, 0.5)
        rec_image.show()
        rec_label = gtk.Label('Record')
        rec_label.set_alignment(0, 0.5)
        rec_label.set_attributes(attr)
        rec_hbox = gtk.HBox()
        rec_hbox.pack_start(rec_image)
        rec_hbox.pack_start(rec_label)
        
        record = gtk.Button()
        record.connect('clicked', self.do_record)
        record.add(rec_hbox)
        
        cancel = gtk.Button(label='Cancel')
        cancel.connect('clicked', self.do_cancel)
        cancel.child.set_attributes(attr)
        cancel.child.set_padding(-1, int(fsize / 2.5))

        hbox2.pack_start(title)
        if cam_available:
            hbox2.pack_start(cam, False, False, 5)
        hbox3.pack_start(record, padding=5)
        hbox3.pack_start(cancel, padding=5)
        if u and u['modules']:
            vbox2.pack_start(self.module)
        vbox2.pack_start(hbox2, padding=5)
        vbox2.pack_start(hbox3, padding=5)
        hbox.pack_start(photo, False, False, 5)
        hbox.pack_start(vbox2)
        
        vbox.add(hbox)
        self.add(vbox)
        self.set_transient_for(parent)
        self.show_all()
        if cam_available:
            switch_profile(nocam_profile)

    def _toggled(self, widget):
        use_cam = widget.get_active()
        profile = cam_profile if use_cam else nocam_profile
        switch_profile(profile)
        
    def do_record(self, button):
        global waiting_for_details
        mod = None
        iter = self.module.get_active_iter()
        if iter:
            mod = self.liststore.get(iter, 0, 1)
            # If no module selected, set module title to nothing.
            if mod[1] == '':
              mod = ('', '')
        name = self.t.get_text() or 'Unknown'
        cam = self.cam.get_active() if cam_available else False
        profile = cam_profile if cam else nocam_profile
        start_recording(self.u, name, mod, profile)

        waiting_for_details = False
        self.destroy()

    def do_cancel(self, button):
        global waiting_for_details
        waiting_for_details = False
        self.destroy()
        if not is_admin:
            show_login()


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
    switch_profile(profile)
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

    if switching_profile:
        trigger_recording = mp.getIdentifier()
    else:
        dispatcher.emit('start-before', mp.getIdentifier())

def switch_profile(profile):
    global switching_profile
    if not switching_profile:
        switching_profile = True
        conf.change_current_profile(profile)
        conf.update()
        dispatcher.emit('reload-profile')

def on_update_pipeline(source, old, new):
    global trigger_recording, switching_profile, profile
    playing = (old, new) == (gst.STATE_PAUSED, gst.STATE_PLAYING)
    if playing:
        if trigger_recording:
            dispatcher.emit('start-before', trigger_recording)
            trigger_recording = None
        time.sleep(0.5)
        
        profile = conf.get('basic','profile')
        if ed and cam_available:
            ed.cam.set_active(profile == cam_profile)
        if not waiting_for_details:
            show_login()
        switching_profile = False

class PlaceholderEntry(gtk.Entry):

    placeholder = 'Username'
    _default = True

    def __init__(self, *args, **kwargs):
        self.placeholder = kwargs['placeholder']
        del kwargs['placeholder'] 
        gtk.Entry.__init__(self, *args, **kwargs)
        self.connect('focus-in-event', self._focus_in_event)
        self.connect('focus-out-event', self._focus_out_event)
        self._focus_out_event(self, None)

    def _focus_in_event(self, widget, event):
        if self._default:
            self.set_text('')
            self.modify_text(gtk.STATE_NORMAL, gtk.gdk.color_parse('black'))

    def _focus_out_event(self, widget, event):
        if gtk.Entry.get_text(self) == '':
            self.set_text(self.placeholder)
            self.modify_text(gtk.STATE_NORMAL, gtk.gdk.color_parse('gray'))
            self._default = True
        else:
            self._default = False

    def get_text(self):
        if self._default:
            return ''
        return gtk.Entry.get_text(self)
