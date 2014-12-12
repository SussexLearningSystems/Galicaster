import calendar
import alsaaudio
import cStringIO
import os
import requests
import socket
import subprocess
from threading import Event, Thread
import time

import gobject
from MeteorClient import MeteorClient
import pyscreenshot as ImageGrab

from galicaster.core import context


conf = context.get_conf()
dispatcher = context.get_dispatcher()
logger = context.get_logger()


def init():
  ddp = DDP()
  ddp.start()

class DDP(Thread):
  def __init__(self):
    Thread.__init__(self)
    self.meteor = conf.get('ddp', 'meteor')

    self.client = MeteorClient(self.meteor, debug=False)
    self.client.on('added', self.on_added)
    self.client.on('changed', self.on_changed)
    self.client.on('subscribed', self.on_subscribed)
    self.client.on('connected', self.on_connected)
    self.client.on('reconnected', self.on_connected)
    self.client.on('closed', self.on_closed)

    self.displayName = conf.get('sussexlogin', 'room_name')
    self.vu_min = -70
    self.vu_range = 40
    self.do_vu = 0
    self.ip = socket.gethostbyname(socket.gethostname())
    self.id = conf.get('ingest', 'hostname')
    self._user = conf.get('ddp', 'user')
    self._password = conf.get('ddp', 'password')
    self._http_host = conf.get('ddp', 'http_host')
    self.paused = False
    self.recording = False
    self.has_disconnected = False

    cam_available = conf.get('sussexlogin', 'cam_available') or cam_available
    if cam_available in ('True', 'true', True, '1', 1):
      self.cam_available = 1
    elif cam_available in ('False', 'false', False, '0', 0):
      self.cam_available = 0
    else:
      self.cam_available = int(cam_available)

    self.audiofaders = []
    self.mixers = {}
    faders = conf.get('ddp', 'audiofaders').split()
    for fader in faders:
        audiofader = {}
        fader = 'audiofader-' + fader
        audiofader['name'] = conf.get(fader, 'name')
        audiofader['display'] = conf.get(fader, 'display')
        audiofader['min'] = conf.get_int(fader, 'min')
        audiofader['max'] = conf.get_int(fader, 'max')
        audiofader['type'] = conf.get(fader, 'type')
        audiofader['setrec'] = conf.get_boolean(fader, 'setrec')
        audiofader['mute'] = conf.get_boolean(fader, 'mute')
        audiofader['unmute'] = conf.get_boolean(fader, 'unmute')
        audiofader['setlevel'] = conf.get_int(fader, 'setlevel')
        mixer = {}
        mixer['control'] = alsaaudio.Mixer(control=audiofader['name'])
        mixer['watchid'] = None
        self.mixers[audiofader['name']] = mixer
        self.audiofaders.append(audiofader)

    dispatcher.connect('galicaster-init', self.on_init)
    dispatcher.connect('update-rec-vumeter', self.vumeter)
    dispatcher.connect('galicaster-notify-timer-short', self.heartbeat)
    dispatcher.connect('start-before', self.on_start_recording)
    dispatcher.connect('restart-preview', self.on_stop_recording)
    dispatcher.connect('update-rec-status', self.on_rec_status_update)

  def run(self):
    self.connect()

  def connect(self):
    if not self.has_disconnected:
        try:
          self.client.connect()
          self.client.subscribe('GalicasterControl', params=[self.id], callback=self.subscription_callback)
        except Exception:
          logger.warn('DDP connection failed')

  def update(self, collection, query, update):
    if self.client.connected:
      try:
        self.client.update(collection, query, update, callback=self.update_callback)
      except Exception:
        logger.warn("Error updating document {collection: %s, query: %s, update: %s}" % (collection, query, update))

  def insert(self, collection, document):
    if self.client.connected:
      try:
        self.client.insert(collection, document, callback=self.insert_callback)
      except Exception:
        logger.warn("Error inserting document {collection: %s, document: %s}" % (collection, document))

  def heartbeat(self, element):
    if self.client.connected:
        self.update_screenshots()
        self.update('rooms', {'_id': self.id},
          {'$set': {'heartbeat': int(time.time())}}
        )
    else:
      self.connect()

  def on_start_recording(self, sender, id):
    media_package = self.media_package_metadata(id)
    profile = context.get_state().profile.name
    self.update('rooms', {'_id': self.id},
        {'$set': {'currentMediaPackage': media_package, 'recording': True, 'currentProfile': profile}}
    )

  def on_stop_recording(self, sender=None):
    self.update('rooms', {'_id': self.id},
      {'$unset': {'currentMediaPackage': ''}, '$set': {'recording': False}}
    )
    self.update_screenshots(1.5)

  def on_init(self, data):
    self.update_screenshots(1.5)

  def update_screenshots(self, delay=0):
    worker = Thread(target=self._update_screenshots, args=(delay,))
    worker.start()

  def _update_screenshots(self, delay):
    time.sleep(delay)
    images = [
      {
        'type': 'presentation',
        'filename': 'presentation.jpg',
        'file': '/tmp/SCREEN.avi.jpg'
      },
      {
        'type': 'presenter',
        'filename': 'camera.jpg',
        'file': '/tmp/CAMERA.avi.jpg'
      }
    ]
    files = {}
    for image in images:
      try:
        if(os.path.getctime(image['file']) > time.time() - 3):
          files[image['type']] = (image['filename'], open(image['file'], 'rb'), 'image/jpeg')
      except Exception:
        pass
    im = ImageGrab.grab(bbox=(10, 10, 1280, 720), backend='imagemagick')
    im.thumbnail((640, 360))
    output = cStringIO.StringIO()
    if im.mode != "RGB":
      im = im.convert("RGB")
    im.save(output, format="JPEG")
    files['screen'] = ('screen.jpg', output.getvalue(), 'image/jpeg')
    try:
      # add verify=False for testing self signed certs
      requests.post("%s/image/%s" % (self._http_host, self.id), files=files, auth=(self._user, self._password))
    except Exception:
      logger.warn('Unable to post images')

  def mixer_changed(self, source=None, condition=None, reopen=True):
    if reopen:
      for audiofader in self.audiofaders:
        mixer = {}
        mixer['control'] = alsaaudio.Mixer(control=audiofader['name'])
        mixer['watchid'] = None
        self.mixers[audiofader['name']] = mixer
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
      self.update('rooms', {'_id': self.id}, {'$set': update})
    self.do_vu = (self.do_vu + 1) % 4

  def on_rec_status_update(self, element, data):
    is_paused = data == 'Paused'
    if is_paused:
      self.update_screenshots(.75)
    if self.paused != is_paused:
      self.update('rooms', {'_id': self.id}, {'$set': {'paused': is_paused}})
      self.paused = is_paused
    if data == '  Recording  ':
      subprocess.call(['killall', 'maliit-server'])
      self.update_screenshots(.75)

  def media_package_metadata(self, id):
    mp = context.get_repository().get(id)
    line = mp.metadata_episode.copy()
    duration = mp.getDuration()
    line["duration"] = long(duration/1000) if duration else None
    # Does series_title need sanitising as well as duration?
    created = mp.getDate()
    line["created"] = calendar.timegm(created.utctimetuple())
    for key,value in mp.metadata_series.iteritems():
        line["series_"+key] = value
    for key,value in line.iteritems():
        if value in [None,[]]:
            line[key]=''
    return line

  def subscription_callback(self, error):
    if error:
        logger.warn("Subscription callback returned error: %s" % error)

  def insert_callback(self, error, data):
    if error:
        logger.warn("Insert callback returned error: %s" % error)

  def update_callback(self, error, data):
    if error:
        logger.warn("Update callback returned error: %s" % error)

  def on_subscribed(self, subscription):
    me = self.client.find_one('rooms')
    if me:
      self.update('rooms', {'_id': self.id}, {
        '$set': {
          'displayName': self.displayName,
          'ip': self.ip,
          'paused': False,
          'recording': False,
          'heartbeat': int(time.time()),
          'camAvailable': self.cam_available
        }
      })
    else:
      audio = self.read_audio_settings()
      self.insert('rooms', {
        '_id': self.id,
        'displayName': self.displayName,
        'audio': audio,
        'ip': self.ip,
        'paused': False,
        'recording': False,
        'heartbeat': int(time.time()),
        'camAvailable': self.cam_available
      })

  def set_audio(self, fields):
    faders = fields.get('audio')
    if faders:
      for fader in faders:
        level = fader.get('level')
        if fader['name'] in self.mixers:
            mixer = self.mixers[fader['name']]['control']
            l, r = mixer.getvolume(fader['type'])
            if level >= 0 and l != level:
              mixer.setvolume(level, 0, fader['type'])
              mixer.setvolume(level, 1, fader['type'])

  def on_added(self, collection, id, fields):
    self.set_audio(fields)
    self.update_audio()

  def on_changed(self, collection, id, fields, cleared):
    self.set_audio(fields)
    me = self.client.find_one('rooms')
    if self.paused != me['paused']:
      self.set_paused(me['paused'])
    if context.get_state().is_recording != me['recording']:
      self.set_recording(me)

  def set_paused(self, new_status):
    self.paused = new_status
    dispatcher.emit("toggle-pause-rec")

  def set_recording(self, me):
    self.recording = me['recording']
    if self.recording:
      meta = me.get('currentMediaPackage', {}) or {}
      profile = me.get('currentProfile', 'nocam')
      series = (meta.get('series_title', ''), meta.get('isPartOf', ''))
      user = {'user_name': meta.get('creator', ''),
              'user_id': meta.get('rightsHolder', '')}
      title = meta.get('title', 'Unknown')
      dispatcher.emit('sussexlogin-record',
                      (user, title, series, profile))
    else:
      dispatcher.emit("stop-record", '')

  def on_connected(self):
    logger.info('Connected to Meteor')
    self.client.login(self._user, self._password)
    for key, mixer in self.mixers.iteritems():
      if not mixer['watchid']:
        fd, eventmask = mixer['control'].polldescriptors()[0]
        mixer['watchid'] = gobject.io_add_watch(fd, eventmask, self.mixer_changed)

  def on_closed(self, code, reason):
    self.has_disconnected = True
    logger.error('Disconnected from Meteor: err %d - %s' % (code, reason))

  def update_audio(self):
    me = self.client.find_one('rooms')
    audio = self.read_audio_settings()
    if me:
      mAudio = me.get('audio')
      update = False
      for key, fader in enumerate(audio):
        if not key in mAudio or mAudio[key].get('level') != fader.get('level'):
          update = True
      if update:
        self.update('rooms', {'_id': self.id}, {'$set': {'audio': audio}})

  def read_audio_settings(self):
    audio_settings = []
    for audiofader in self.audiofaders:
      mixer = self.mixers[audiofader['name']]['control']
      if audiofader['display']:
        audio_settings.append(
          self.control_values(
            mixer, audiofader
          )
        )
      #ensure fixed values
      if audiofader['setrec']:
        mixer.setrec(1)
      if audiofader['mute']:
        mixer.setmute(1)
      if audiofader['unmute']:
        mixer.setmute(0)
      if audiofader['setlevel'] >= 0:
        mixer.setvolume(audiofader['setlevel'], 0, audiofader['type'])
        mixer.setvolume(audiofader['setlevel'], 1, audiofader['type'])
    return audio_settings

  def control_values(self, mixer, audiofader):
    controls = {}
    left, right = mixer.getvolume(audiofader['type'])
    controls['min'] = audiofader['min']
    controls['max'] = audiofader['max']
    controls['level'] = left
    controls['type'] = audiofader['type']
    controls['name'] = audiofader['name']
    controls['display'] = audiofader['display']
    return controls
