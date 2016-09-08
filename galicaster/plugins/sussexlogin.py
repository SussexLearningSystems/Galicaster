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
import re
import requests
import time
import xml.etree.ElementTree as ET
from galicaster.core import context
from galicaster.classui import get_ui_path, get_image_path
from galicaster.classui.elements.message_header import Header
from galicaster.mediapackage.mediapackage import Mediapackage
from operator import itemgetter
from mav.mav import MAV

#defaults
cam_available = 0
cam_profile = 'cam'
nocam_profile = 'nocam'
camonly_profile = 'camonly'
twocams_profile = 'twocams'
fsize = 50
matrix_ip = ''
matrix_port = 2006
matrix_retries = 5
matrix_outs = [2, 3]
matrix_cam_labels = ['Judges', 'Left', 'Right']

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


mav = None
flash_messages = {
    'empty_username': "Please enter a username",
    'user_not_found': "Username does not exist\nPlease enter a valid username",
    'webservice_unavailable': "Unable to verify user.\nPlease contact IT Services"
}

def init():
    global timeout
    global cam_available, cam_profile, nocam_profile, camonly_profile, twocams_profile
    global matrix_ip, matrix_port, matrix_retries, matrix_outs, matrix_cam_labels
    global fsize, mav
    try:
        dispatcher.connect('galicaster-status', event_change_mode)
        dispatcher.connect('restart-preview', show_login)
        dispatcher.connect('update-pipeline-status', on_update_pipeline)

    except ValueError:
        pass

    cam_available = conf.get('sussexlogin', 'cam_available') or cam_available
    if cam_available in ('True', 'true', True, '1', 1):
      cam_available = 1
    elif cam_available in ('False', 'false', False, '0', 0):
      cam_available = 0
    else:
      cam_available = int(cam_available)
    logger.info("cam_available set to: %d", cam_available)

    cam_profile = conf.get('sussexlogin', 'cam_profile') or cam_profile
    logger.info("cam_profile set to: %s", cam_profile)

    nocam_profile = conf.get('sussexlogin', 'nocam_profile') or nocam_profile
    logger.info("nocam_profile set to: %s", nocam_profile)

    fsize = conf.get('sussexlogin', 'font_size') or fsize
    fsize = int(fsize)
    logger.info("font_size set to: %s", fsize)

    dispatcher.add_new_signal('sussexlogin-record', True)
    dispatcher.connect('sussexlogin-record', start_recording)

    if cam_available > 1:
      camonly_profile = conf.get('sussexlogin', 'camonly_profile') or camonly_profile
      logger.info("camonly_profile set to: %s", camonly_profile)

      twocams_profile = conf.get('sussexlogin', 'twocams_profile') or twocams_profile
      logger.info("twocams_profile set to: %s", twocams_profile)

      outs = conf.get('sussexlogin', 'matrix_outs')
      if outs:
        matrix_outs = outs.split(',')
        matrix_outs = [int(x) for x in matrix_outs]
      matrix_outs_str = ', '.join("%d" % m for m in matrix_outs)
      logger.info("matrix_outs set to: [%s]", matrix_outs_str)

      labels = conf.get('sussexlogin', 'matrix_cam_labels')
      if labels:
        matrix_cam_labels = [l.strip() for l in labels.split(',')]
      logger.info("matrix_cam_labels set to: [%s]", ', '.join(matrix_cam_labels))

      matrix_ip = conf.get('sussexlogin', 'matrix_ip') or matrix_ip
      if matrix_ip:
        logger.info("matrix_ip set to: %s", matrix_ip)

      matrix_port = conf.get_int('sussexlogin', 'matrix_port') or matrix_port
      logger.info("matrix_port set to: %d", matrix_port)

      matrix_retries = conf.get_int('sussexlogin', 'matrix_retries') or matrix_retries
      logger.info("matrix_retries set to: %d", matrix_retries)

      mav = MAV(matrix_ip, matrix_port, matrix_retries)


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


def show_login(element=None, flash=None):
    """
    Called up when switching to record mode or recording ended, shows the dialog if necessary
    """
    global sussex_login_dialog
    global waiting_for_details
    if (not context.get_state().is_recording and
        not waiting_for_details and
        context.get_state().area == 0 and
        context.get_state().status == 'Preview'):
        sussex_login_dialog = LoginDialog(flash)
        waiting_for_details = True
        recorder_ui = context.get_mainwindow().nbox.get_nth_page(0).gui
        recorder_ui.get_object('recording1').set_text('Not recording')
        recorder_ui.get_object('recording3').set_text('')
        if cam_available:
            switch_profile(cam_profile, 1)
        elif (profile == cam_profile) or not cam_available:
            switch_profile(nocam_profile)
        sussex_login_dialog.show()
    return True


class LoginDialog(gtk.Dialog):
    def __init__(self, flash_str):
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

        #Taskbar with logo
        strip = Header(size=size, title="Log In")
        self.vbox.pack_start(strip, False, True, 0)
        strip.show()

        #Labels
        label = gtk.Label("Username:")
        label.modify_font(fdesc)
        label.show()

        self.entry = gtk.Entry()
        self.entry.connect('activate', self.do_login)
        self.entry.modify_font(fdesc)
        self.entry.connect('focus-in-event', self._focus_in_event)
        self.entry.show()

        login_button = gtk.Button('Log In')
        login_button.connect('clicked', self.do_login)
        login_button.modify_font(fdesc)
        login_button.child.set_attributes(attr)
        login_button.show()

        flash_label = gtk.Label(flash_str)
        flash_label.modify_font(fdesc)
        flash_label.set_alignment(0, 0)
        flash_label.set_line_wrap(True)
        flash_label.modify_fg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#a94442'))
        flash_label.show()

        flash_bg = gtk.EventBox()
        flash_bg.add(flash_label)
        flash_bg.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#ebccd1'))
        flash_bg.show()

        spacer = gtk.HBox()
        spacer.pack_start(flash_bg, False, False, 10)
        spacer.show()

        self.continuous_bg = gtk.EventBox()
        self.continuous_bg.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#ebccd1'))
        self.continuous_bg.add(spacer)
        self.continuous_bg.show()

        table = gtk.Table(2, 2, False)
        table.set_row_spacings(5)
        table.attach(label, 0, 1, 0, 1, xoptions=gtk.SHRINK)
        table.attach(self.entry, 1, 2, 0, 1, xoptions=gtk.EXPAND|gtk.FILL)
        table.attach(login_button, 1, 2, 1, 2, xoptions=gtk.EXPAND|gtk.FILL)
        table.show()

        self.table_box = gtk.HBox()
        self.table_box.pack_start(table, True, True, 10)
        self.table_box.show()

        vbox = gtk.VBox()
        if flash_str:
            vbox.pack_start(self.continuous_bg, False, False, 10)
        vbox.pack_start(self.table_box, False, False, 0)
        vbox.show()

        self.vbox.add(vbox)

        # listen for key presses
        self.add_events(gtk.gdk.KEY_PRESS_MASK)
        self.connect('key-press-event', self.eat_escape)

        # Move dialog to 50px above top of maliit keyboard display on screen
        available_headroom = size[1] - 264
        dialog_size = self.get_size()
        posx, posy = self.get_position()
        self.move(posx, available_headroom - (dialog_size[1] + 50))

    def _focus_in_event(self, widget, event):
        self.continuous_bg.hide()

    def do_login(self, button):
        """
        Called when you press the login button
        """
        global ed, flash_messages, waiting_for_details
        self.hide()
        username = self.entry.get_text()

        force_login = conf.get_boolean('sussexlogin', 'force_login') or False
        if force_login:
            if not username:
                waiting_for_details = False
                show_login(flash=flash_messages['empty_username'])
            else:
                try:
                    user = get_user_details(username)
                    if user:
                        ed = EnterDetails(user)
                    else:
                        waiting_for_details = False
                        show_login(flash=flash_messages['user_not_found'].format(username))
                except Exception as e:
                    if e.message is flash_messages['webservice_unavailable']:
                        user = {}
                        logger.warn('Allowing anonymous recording as web service unavailable')
                        ed = EnterDetails(user)
        else:
            try:
                user = get_user_details(username)
            except Exception as e:
                if e.message is flash_messages['webservice_unavailable']:
                    user = {}
                    logger.warn('Allowing anonymous recording as web service unavailable')
            finally:
                ed = EnterDetails(user)

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

    def __init__(self, user=None):
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

        self.module_liststore = gtk.ListStore(str,str)
        self.module_liststore.append(['Choose a Module...', ''])
        presenter = "Enter Details"
        photo = gtk.Image()

        self.u = None
        u = user
        if u:
            self.u = u
            presenter = u['user_name']

            if u['pic']:
                photo.set_from_pixbuf(u['pic'])

            if u['modules']:
                #sort modules by name before adding to liststore
                for series_id, series_name in sorted(u['modules'].items(), key=itemgetter(1)):
                    self.module_liststore.append([series_name + ' (' + series_id.split('__')[0] + ')', series_id])

        strip = Header(size=(width, height), title=presenter)
        vbox.pack_start(strip, True, True, 0)

        cell = gtk.CellRendererText()
        cell.set_property('font-desc', fdesc)
        self.module = gtk.ComboBox(self.module_liststore)
        self.module.pack_start(cell, True)
        self.module.add_attribute(cell, 'text', 0)
        self.module.set_active(0)

        title = PlaceholderEntry(placeholder='Enter a title here...')
        title.modify_font(fdesc)
        self.t = title

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
        if cam_available == 1:
            cam = gtk.CheckButton(label='Camera')
            cam.connect('clicked', self._toggled)
            cam.child.set_attributes(attr)
            self.cam = cam
            hbox2.pack_start(cam, False, False, 5)
        elif cam_available == 2:
            self.cam1_liststore = gtk.ListStore(str,int)
            self.cam1_liststore.append(['Presentation', -1])
            for output, cam in enumerate(matrix_cam_labels):
                self.cam1_liststore.append([cam, output + 1])
            self.cam1 = gtk.ComboBox(self.cam1_liststore)
            self.cam1.pack_start(cell, True)
            self.cam1.add_attribute(cell, 'text', 0)
            self.cam1.set_active(0)
            self.cam1.set_wrap_width(1)
            hbox2.pack_start(self.cam1, False, False, 5)
            self.cam1.connect('changed', self._toggled)

            self.cam2_liststore = gtk.ListStore(str,int)
            self.cam2_liststore.append(['', -1])
            for output, cam in enumerate(matrix_cam_labels):
                self.cam2_liststore.append([cam, output + 1])
            self.cam2 = gtk.ComboBox(self.cam2_liststore)
            self.cam2.pack_start(cell, True)
            self.cam2.add_attribute(cell, 'text', 0)
            self.cam2.set_active(0)
            self.cam2.set_wrap_width(1)
            hbox2.pack_start(self.cam2, False, False, 5)
            self.cam2.connect('changed', self._toggled)


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
        profile, cam1, cam2 = self.which_profile()
        switch_profile(profile, cam1, cam2)

    def which_profile(self):
        profile = nocam_profile
        if cam_available == 1:
          profile = cam_profile if self.cam.get_active() else nocam_profile

        if cam_available > 1:
          cam1 = None
          cam1_iter = self.cam1.get_active_iter()
          if cam1_iter:
            cam1 = self.cam1_liststore.get(cam1_iter, 0, 1)

          cam2 = None
          cam2_iter = self.cam2.get_active_iter()
          if cam2_iter:
            cam2 = self.cam2_liststore.get(cam2_iter, 0, 1)

          if cam1[1] == -1:
            profile = nocam_profile if cam2[1] == -1 else cam_profile
          elif cam2[1] == -1:
            profile = camonly_profile
            cam2 = cam1
          else:
            profile = twocams_profile

        if 0 <= cam_available <= 1:
          return profile, None, None

        return profile, cam1[1], cam2[1]

    def do_record(self, button):
        global waiting_for_details
        mod = None
        iter = self.module.get_active_iter()
        if iter:
            mod = self.module_liststore.get(iter, 0, 1)
            # If no module selected, set module title to nothing.
            if mod[1] == '':
              mod = ('', '')
            else:
              code = mod[1].split('__')[0]
              m = re.match('(.+) \(' + code + '\)$', mod[0])
              if m:
                  mod = (m.group(1), mod[1])
        name = self.t.get_text() or 'Unknown'
        profile = self.which_profile()
        dispatcher.emit('sussexlogin-record', (self.u, name, mod, profile))

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
    global flash_messages
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
            ws_timeout = int(conf.get('sussexlogin', 'ws_timeout'))
        except:
            ws_timeout = 5
            logger.error('No value or invalid timeout specified for web service request, defaulting to {}'.format(ws_timeout))

        try:
            r = requests.get(url, timeout=ws_timeout)
        except requests.exceptions.RequestException:
            logger.error('Error getting data from web service')
            raise Exception(flash_messages['webservice_unavailable'])

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

def start_recording(orig, metadata):
    """
    start a recording by adding a mediapackage to the repo with the correct metadata
    then emitting a 'start-before' signal.
    """
    global trigger_recording, waiting_for_details, ed

    waiting_for_details = False

    user, title, module, profile = metadata

    if sussex_login_dialog:
      sussex_login_dialog.hide()

    if ed:
      ed.hide()

    if isinstance(profile, basestring):
        switch_profile(profile)
    else:
        switch_profile(profile[0], profile[1], profile[2])

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

def switch_profile(profile, cam1=None, cam2=None):
    global switching_profile
    if not switching_profile:
        switching_profile = True
        conf.change_current_profile(profile)
        conf.update()
        if mav:
          if cam1 > 0:
            try:
              mav.tie(cam1, matrix_outs[0])
            except:
              pass
          if cam2 > 0:
            try:
              mav.tie(cam2, matrix_outs[1])
            except:
              pass

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
        if ed and cam_available == 1:
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
