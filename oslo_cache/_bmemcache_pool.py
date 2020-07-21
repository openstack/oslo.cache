# Copyright 2022 Inspur
# All Rights Reserved.
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

"""Thread-safe connection pool for python-binary-memcached."""
try:
    import eventlet
except ImportError:
    eventlet = None
import bmemcached
from oslo_cache._memcache_pool import MemcacheClientPool
from oslo_log import log

LOG = log.getLogger(__name__)


class _BMemcacheClient(bmemcached.Client):
    """Thread global memcache client

    As client is inherited from threading.local we have to restore object
    methods overloaded by threading.local so we can reuse clients in
    different threads
    """
    __delattr__ = object.__delattr__
    __getattribute__ = object.__getattribute__
    __setattr__ = object.__setattr__

    # Hack for lp 1812935
    if eventlet and eventlet.patcher.is_monkey_patched('thread'):
        # NOTE(bnemec): I'm not entirely sure why this works in a
        # monkey-patched environment and not with vanilla stdlib, but it does.
        def __new__(cls, *args, **kwargs):
            return object.__new__(cls)
    else:
        __new__ = object.__new__

    def __del__(self):
        pass


class BMemcacheClientPool(MemcacheClientPool):
    def __init__(self, urls, arguments, **kwargs):
        MemcacheClientPool.__init__(self, urls, arguments, **kwargs)
        self._arguments = {
            'username': arguments.get('username', None),
            'password': arguments.get('password', None),
            'tls_context': arguments.get('tls_context', None),
        }

    def _create_connection(self):
        return _BMemcacheClient(self.urls, **self._arguments)
