import telnetlib
import time
import socket
import re

import galicaster
from galicaster.core import context

logger = context.get_logger()


class MAV:
    def __init__(self, host, port, retries=5):
        """
        Extron MAV 44 AV class for switching and reading input / output ties
        via telnet (using Direct Port Access of an Extron Controller).

        :param host: ``string`` telnet host.
        :param port: ``int`` telnet port.
        :param retries: ``int`` maximum connection errors or read / write
        failures.
        """
        self.host = host
        self.port = port
        self.retries = retries
        self.conn = telnetlib.Telnet()

    def _connect(self):
        """
        Connect to host:port
        """
        logger.info('Connecting')
        self.conn.open(self.host, self.port)

    def _write(self, data, expect):
        """
        Attempt to write data to telnet socket and match the response against
        expect parameter.

        :param data: ``string`` to write to telnet socket.
        :param expect: ``string`` regex string to match response against.
        """
        logger.info('Starting write data')
        logger.info("Data to write: %s" % data)
        logger.info("Expected response: %s" % expect)
        error = Exception('Failed to read expected reply.')
        attempts = 0
        while attempts < self.retries:
            logger.info("Attempt: %d of %d" % (attempts, self.retries))
            try:
                if not isinstance(self.conn.get_socket(), socket.socket):
                    logger.info('No telnet connection, need to connect')
                    self._connect()
                # drain read buffer
                logger.info('Draining read buffer')
                while self.conn.read_until("\n", .1):
                    pass
                logger.info('Writing data')
                self.conn.write(data)
                logger.info('Reading response data')
                read = self.conn.read_until("\n", 1)
                if re.match(expect, read):
                    logger.info("Read data matched expected response")
                else:
                    logger.info("Read data did not match expected response: %s"
                                % read)
                return read
            except Exception as e:
                logger.error("Error occurred: %s" % str(e))
                logger.info('Closing telnet connection')
                self.conn.close()
                self._connect()
                error = e
                time.sleep(.5)
            finally:
                attempts += 1
        raise error

    def tie(self, i, o):
        """
        Create tie between input and output.

        :param i: ``int`` input (1-4)
        :param o: ``int`` output (1-4)
        """
        logger.info("Creating tie between In%d and Out%d" % (i, o))
        self._write("%d*%d%%\n" % (i, o), r"^Out%d In%d Vid\r\n$" % (o, i))
        return True

    def read_tie(self, o):
        """
        Read which input is tied to output.

        :param o: ``int`` output (1-4)
        """
        return self._write("%d%%\n" % o, "^\d\r\n$")

if __name__ == '__main__':
    host = '139.184.190.166'
    port = 2006

    m = MAV(host, port)
    print m.tie(3, 2)
    print m.read_tie(2)
    print m.tie(2, 2)
    print m.read_tie(2)
    print m.tie(1, 2)
    print m.read_tie(2)
    time.sleep(320)
    print m.tie(3, 2)
    print m.read_tie(2)
    print m.tie(2, 2)
    print m.read_tie(2)
    print m.tie(1, 2)
    print m.read_tie(2)
