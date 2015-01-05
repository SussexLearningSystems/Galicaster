from galicaster.core import context

logger = context.get_logger()
dispatcher = context.get_dispatcher()
conf = context.get_conf()

reload_every = 30
last_reload = 0
def init():
    global reload_every
    reload_every = conf.get_int('reloadpipeline', 'reload_every') or 30
    logger.debug('reload_every set to %i', reload_every)

    dispatcher.connect('galicaster-notify-timer-long', timer)

def timer(signal=None):
    global last_reload
    last_reload += 1
    if last_reload == reload_every:
        if not context.get_state().is_recording:
            last_reload = 0
            dispatcher.emit('reload-profile')
            logger.info('reload profile')

