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

"""dogpile.cache backend that uses etcd 3.x for storage"""
from dogpile.cache import api

from oslo_cache import core
from oslo_serialization import jsonutils

__all__ = [
    'Etcd3gwCacheBackend'
]

_NO_VALUE = core.NO_VALUE


class Etcd3gwCacheBackend(api.CacheBackend):
    #: Default socket/lock/member/leader timeout used when none is provided.
    DEFAULT_TIMEOUT = 30

    #: Default hostname used when none is provided.
    DEFAULT_HOST = "localhost"

    #: Default port used if none provided (4001 or 2379 are the common ones).
    DEFAULT_PORT = 2379

    def __init__(self, arguments):
        self.host = arguments.get('host', self.DEFAULT_HOST)
        self.port = arguments.get('port', self.DEFAULT_PORT)
        self.timeout = int(arguments.get('timeout', self.DEFAULT_TIMEOUT))
        # module etcd3gw is only required when etcd3gw backend is used
        import etcd3gw
        self._client = etcd3gw.client(host=self.host,
                                      port=self.port,
                                      timeout=self.timeout)

    def get(self, key):
        values = self._client.get(key, False)
        if not values:
            return core.NO_VALUE
        value, metadata = jsonutils.loads(values[0])
        return api.CachedValue(value, metadata)

    def get_multi(self, keys):
        """Retrieves the value for a list of keys."""
        return [self.get(key) for key in keys]

    def set(self, key, value):
        self.set_multi({key: value})

    def set_multi(self, mapping):
        lease = None
        if self.timeout:
            lease = self._client.lease(ttl=self.timeout)
        for key, value in mapping.items():
            self._client.put(key, jsonutils.dumps(value), lease)

    def delete(self, key):
        self._client.delete(key)

    def delete_multi(self, keys):
        for key in keys:
            self._client.delete(key)
