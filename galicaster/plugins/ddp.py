import alsaaudio
import base64
import cStringIO
import socket
from threading import Thread, Timer
import time

import gobject
from MeteorClient import MeteorClient
import pyscreenshot as ImageGrab

from galicaster.core import context


conf = context.get_conf()
dispatcher = context.get_dispatcher()

ddp = None


def init():
  ddp = DDP()
  ddp.start()


class DDP(Thread):
  def __init__(self):
    Thread.__init__(self)
    self.meteor = conf.get('ddp', 'meteor')
    self.displayName = conf.get('sussexlogin', 'room_name')
    self.vu_min = -70
    self.vu_range = 40
    self.do_vu = 0
    self.ip = socket.gethostbyname(socket.gethostname())
    self.id = conf.get('ingest', 'hostname')
    self.capture_mixer = alsaaudio.Mixer(control='Capture')
    self.boost_mixer = alsaaudio.Mixer(control='Rear Mic Boost')
    dispatcher.connect('update-rec-vumeter', self.vumeter)

  def run(self):
    self.client = MeteorClient(self.meteor, debug=False)
    self.client.connect()
    self.client.subscribe('GalicasterControl', params=[self.id], callback=self.subscription_callback)
    self.client.on('changed', self.changed)
    self.client.on('subscribed', self.subscribed)
    fd, eventmask = self.capture_mixer.polldescriptors()[0]
    self.capture_watchid = gobject.io_add_watch(fd, eventmask, self.mixer_changed)
    fd, eventmask = self.boost_mixer.polldescriptors()[0]
    self.boost_watchid = gobject.io_add_watch(fd, eventmask, self.mixer_changed)
    self.update_screenshots()

  def is_recording(self):
    me = self.client.find_one('rooms')
    is_recording = context.get_state().is_recording
    result = {}
    if not 'recording' in me or is_recording != me['recording']:
      result = {'recording': is_recording}
    return result

  def update_screenshots(self):
    start = time.time()
    im = ImageGrab.grab(bbox=(10, 10, 1280, 720), backend='imagemagick')
    im.thumbnail((640, 360))
    output = cStringIO.StringIO()
    if im.mode != "RGB":
      im = im.convert("RGB")
    im.save(output, format="JPEG")
    screen = base64.b64encode(output.getvalue())

    with open('/tmp/SCREEN.avi.jpg', mode='rb') as file:
      presentationVideo = base64.b64encode(file.read())

    with open('/tmp/CAMERA.avi.jpg', mode='rb') as file:
      presenterVideo = base64.b64encode(file.read())

    self.client.update('rooms', {'_id': self.id},
                       {'$set': {'screen': 'data:image/jpeg;base64,' + screen,
                                 'presentationVideo': 'data:image/jpeg;base64,' + presentationVideo,
                                 'presenterVideo': 'data:image/jpeg;base64,' + presenterVideo}})
    exec_time = time.time() - start
    Timer(1 - exec_time, self.update_screenshots).start()

  def mixer_changed(self, source=None, condition=None, reopen=True):
    if reopen:
      del self.capture_mixer
      self.capture_mixer = alsaaudio.Mixer(control='Capture')
      del self.boost_mixer
      self.boost_mixer = alsaaudio.Mixer(control='Rear Mic Boost')
    self.update_audio()
    return True

  def vumeter(self, element, data):
    if self.do_vu == 0:
      data_aux = data
      minimum = float(self.vu_min)

      if data == "Inf":
        valor = 0
      else:
        if data < -self.vu_range:
          data = -self.vu_range
        elif data > 0:
          data = 0
      data = int(((data + self.vu_range) / float(self.vu_range)) * 100)
      update = {'vumeter': data}
      update.update(self.is_recording())
      self.client.update('rooms', {'_id': self.id}, {'$set': update})

    self.do_vu = (self.do_vu + 1) % 4

  def subscription_callback(self, error):
    if error:
      print '*** ERROR: ' + error

  def update_callback(self, error, data):
    if error:
      print '*** ERROR: ' + error
      return
    print '*** DATA: ', data

  def subscribed(self, subscription):
    me = self.client.find_one('rooms')
    audio = self.read_audio_settings()
    if me:
      self.client.update('rooms', {'_id': self.id}, {'displayName': self.displayName, 'audio': audio, 'ip': self.ip},
                         callback=self.update_callback)
    else:
      self.client.insert('rooms', {'_id': self.id, 'displayName': self.displayName, 'audio': audio, 'ip': self.ip})

  def changed(self, collection, id, fields, cleared):
    me = self.client.find_one('rooms')
    level = int((float(me['audio']['capture']['value']['left']) / float(me['audio']['capture']['limits']['max'])) * 100)
    self.capture_mixer.setvolume(level, 0, 'capture')
    self.capture_mixer.setvolume(level, 1, 'capture')
    level = int(
      (float(me['audio']['rearMicBoost']['value']['left']) / float(me['audio']['rearMicBoost']['limits']['max'])) * 100)
    self.boost_mixer.setvolume(level, 0, 'capture')
    self.boost_mixer.setvolume(level, 1, 'capture')

  def update_audio(self):
    me = self.client.find_one('rooms')
    audio = self.read_audio_settings()
    if ((int(me['audio']['capture']['value']['left']) != int(audio['capture']['value']['left'])) or
          (int(me['audio']['rearMicBoost']['value']['left']) != int(audio['rearMicBoost']['value']['left']))):
      self.client.update('rooms', {'_id': self.id}, {'$set': {'audio': audio}})

  def read_audio_settings(self):
    audio_settings = {}
    audio_settings['capture'] = self.control_values(self.capture_mixer)
    audio_settings['rearMicBoost'] = self.control_values(self.boost_mixer)
    return audio_settings

  def control_values(self, mixer):
    controls = {}
    minimum, maximum = mixer.getrange('capture')
    controls['limits'] = {'min': minimum, 'max': maximum}
    left, right = mixer.getvolume('capture')
    controls['value'] = {'left': int(round((float(left) / 100) * maximum)),
                         'right': int(round((float(right) / 100) * maximum))}
    return controls
  
