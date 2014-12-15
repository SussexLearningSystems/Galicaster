from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
import subprocess
from threading import Thread

from galicaster.core import context

dispatcher = context.get_dispatcher()


def init():
    audiostream = AudioStream()
    audiostream.start()

class AudioStream(Thread):
    def __init__(self):
        Thread.__init__(self)

        serveraddr = ('', 1234)
        server = ThreadedHTTPServer(serveraddr, AudioStreamer)
        server.allow_reuse_address = True
        server.timeout = 30
        self.server = server

        dispatcher.connect('galicaster-notify-quit', self.shutdown)

    def run(self):
        self.server.serve_forever()

    def shutdown(self, whatever):
        self.server.shutdown()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


class AudioStreamer(BaseHTTPRequestHandler):
    def _writeheaders(self):
        self.send_response(200) # 200 OK http response
        self.send_header('Content-type', 'audio/mpeg')
        self.end_headers()

    def do_HEAD(self):
        self._writeheaders()

    def do_GET(self):
        try:
            self._writeheaders()

            DataChunkSize = 10000

            command = 'gst-launch-0.10 alsasrc ! lamemp3enc target=1 bitrate=32 cbr=true ! filesink location=/dev/stdout'
            p = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=-1, shell=True)

            while(p.poll() is None):
                stdoutdata = p.stdout.read(DataChunkSize)
                self.wfile.write(stdoutdata)

            stdoutdata = p.stdout.read(DataChunkSize)
            self.wfile.write(stdoutdata)
        except Exception:
            pass

        p.kill()

        try:
            self.wfile.flush()
            self.wfile.close()
        except:
            pass

    def handle_one_request(self):
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except:
            self.close_connection = 1
            self.rfile = None
            self.wfile = None

    def finish(self):
        try:
            BaseHTTPRequestHandler.finish(self)
        except:
            pass
