# Copyright 2012 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import logging as log

from oslo_config import cfg
from oslo_utils import encodeutils
import six

from oslo_cache._i18n import _, _LW


CONF = cfg.CONF
LOG = log.getLogger(__name__)

# Tests use this to make exception message format errors fatal
_FATAL_EXCEPTION_FORMAT_ERRORS = False


class Error(Exception):
    """Base error class.

    Child classes should define an HTTP status code, title, and a
    message_format.

    """
    code = None
    title = None
    message_format = None

    def __init__(self, message=None, **kwargs):
        try:
            message = self._build_message(message, **kwargs)
        except KeyError:
            # if you see this warning in your logs, please raise a bug report
            if _FATAL_EXCEPTION_FORMAT_ERRORS:
                raise
            else:
                LOG.warning(_LW('missing exception kwargs (programmer error)'))
                message = self.message_format

        super(Error, self).__init__(message)

    def _build_message(self, message, **kwargs):
        """Builds and returns an exception message.

        :raises: KeyError given insufficient kwargs

        """
        if not message:
            try:
                message = self.message_format % kwargs
            except UnicodeDecodeError:
                try:
                    kwargs = {k: encodeutils.safe_decode(v)
                              for k, v in six.iteritems(kwargs)}
                except UnicodeDecodeError:
                    # NOTE(jamielennox): This is the complete failure case
                    # at least by showing the template we have some idea
                    # of where the error is coming from
                    message = self.message_format
                else:
                    message = self.message_format % kwargs

        return message


class ValidationError(Error):
    message_format = _("Expecting to find %(attribute)s in %(target)s -"
                       " the server could not comply with the request"
                       " since it is either malformed or otherwise"
                       " incorrect. The client is assumed to be in error.")
    code = 400
    title = 'Bad Request'


class NotImplemented(Error):
    message_format = _("The action you have requested has not"
                       " been implemented.")
    code = 501
    title = 'Not Implemented'
