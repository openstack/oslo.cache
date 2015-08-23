# Copyright 2015 Mirantis Inc
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

"""dogpile.cache backend that uses dictionary for storage"""

from dogpile.cache import api
from oslo_cache import core
from oslo_utils import timeutils

__all__ = [
    'DictCacheBackend'
]

_NO_VALUE = core.NO_VALUE


class DictCacheBackend(api.CacheBackend):
    """A DictCacheBackend based on dictionary.

    Arguments accepted in the arguments dictionary:

    :param expiration_time: interval in seconds to indicate maximum
        time-to-live value for each key in DictCacheBackend.
        Default expiration_time value is 0, that means that all keys have
        infinite time-to-live value.
    :type expiration_time: real
    """

    def __init__(self, arguments):
        self.expiration_time = arguments.get('expiration_time', 0)
        self.cache = {}

    def get(self, key):
        """Retrieves the value for a key.

        :param key: dictionary key
        :returns: value for a key or :data:`oslo_cache.core.NO_VALUE`
            for nonexistent or expired keys.
        """
        (value, timeout) = self.cache.get(key, (_NO_VALUE, 0))
        if self.expiration_time > 0 and timeutils.utcnow_ts() >= timeout:
            self.cache.pop(key, None)
            return _NO_VALUE

        return value

    def get_multi(self, keys):
        """Retrieves the value for a list of keys."""
        return [self.get(key) for key in keys]

    def set(self, key, value):
        """Sets the value for a key.

        Expunges expired keys during each set.

        :param key: dictionary key
        :param value: value associated with the key
        """
        self.set_multi({key: value})

    def set_multi(self, mapping):
        """Set multiple values in the cache.
        Expunges expired keys during each set.

        :param mapping: dictionary with key/value pairs
        """
        self._clear()
        timeout = 0
        if self.expiration_time > 0:
            timeout = timeutils.utcnow_ts() + self.expiration_time
        for key, value in mapping.items():
            self.cache[key] = (value, timeout)

    def delete(self, key):
        """Deletes the value associated with the key if it exists.

        :param key: dictionary key
        """
        self.cache.pop(key, None)

    def delete_multi(self, keys):
        """Deletes the value associated with each key in list if it exists.

        :param keys: list of dictionary keys
        """
        for key in keys:
            self.cache.pop(key, None)

    def _clear(self):
        """Expunges expired keys."""
        now = timeutils.utcnow_ts()
        for k in list(self.cache):
            (_value, timeout) = self.cache[k]
            if timeout > 0 and now >= timeout:
                del self.cache[k]
