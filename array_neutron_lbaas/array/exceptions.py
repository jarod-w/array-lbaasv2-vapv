#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import errno
import inspect
import logging
try:
    from neutron_lib import exceptions as q_exception
except Exception:
    from neutron.common import exceptions as q_exception

import syslog
import traceback


class ArrayAgentException(Exception):
    pass


class ArrayMissingDependencies(ArrayAgentException):
    default_msg = "array_lbaas_agent cannot start due to missing dependency"
    message_format = "(%d) %s: %s [%s; line:%s]"
    default_errno = errno.ENOSYS
    default_project = 'neutron'
    default_name = 'array_lbaas_agent'

    def __init__(self, *args, **kargs):
        self.__set_message(args, kargs)
        super(ArrayMissingDependencies, self).__init__(self.message)
        self.__logger()
        self.__log_error()

    def __logger(self):
        try:
            self._logger = logging.getLogger(self.default_name)
            fh = \
                logging.FileHandler("/var/log/%s/%s.log" %
                                    (self.default_project, self.default_name))
            fh.setLevel(logging.DEBUG)
            self._logger.addHandler(fh)
        except IOError:
            self._logger = None

    def __log_error(self):
        if self._logger:
            self._logger.fatal(self.message)
        else:
            syslog.syslog(syslog.LOG_CRIT, self.message)
        traceback.print_exc()

    def __set_message(self, args, kargs):
        details = ', '.join(map(str, args))
        errno = kargs['errno'] if 'errno' in kargs and kargs['errno'] else \
            self.default_errno
        self.errno = errno
        message = kargs['message'] if 'message' in kargs and kargs['message'] \
            else self.default_msg
        exception = ''
        if 'frame' in kargs and kargs['frame']:
            frame = kargs['frame']
        else:
            my_frames = inspect.getouterframes(inspect.currentframe())[2]
            frame = inspect.getframeinfo(my_frames[0])
        if 'exception' in kargs and kargs['exception']:
            message = kargs['exception']
        elif details:
            exception = details
        self.frame = frame
        self.message = self.message_format % (errno, message, exception,
                                              frame.filename, frame.lineno)


UNKNOWN_ERROR = 100

class ArrayADCException(q_exception.NeutronException):

    # override class property
    message = "Errno: %(errno)d, reason: %(errstr)s"

    def __init__(self, errstr = "Unknown exception in ArrayNetworks LBaaS provider",
                 errno = UNKNOWN_ERROR):
        super(ArrayADCException, self).__init__(errstr = errstr, errno = errno)
        self.errno = errno

class TimeOutException(ArrayADCException):

    message = "Timeout exception."
