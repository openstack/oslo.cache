# Copyright 2014 Mirantis Inc
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

"""dogpile.cache backend that uses Memcached connection pool"""

import functools

from dogpile.cache.backends import memcached as memcached_backend

try:
    from oslo_cache import _bmemcache_pool
except ImportError as e:
    if str(e) == "No module named 'bmemcached'":
        _bmemcache_pool = None
    else:
        raise
from oslo_cache import _memcache_pool
from oslo_cache import exception


# Helper to ease backend refactoring
class ClientProxy(object):
    def __init__(self, client_pool):
        self.client_pool = client_pool

    def _run_method(self, __name, *args, **kwargs):
        with self.client_pool.acquire() as client:
            return getattr(client, __name)(*args, **kwargs)

    def __getattr__(self, name):
        return functools.partial(self._run_method, name)


class PooledMemcachedBackend(memcached_backend.MemcachedBackend):
    """Memcached backend that does connection pooling.

    This memcached backend only allows for reuse of a client object,
    prevents too many client object from being instantiated, and maintains
    proper tracking of dead servers so as to limit delays when a server
    (or all servers) become unavailable.

    This backend doesn't allow to load balance things between servers.

    Memcached isn't HA. Values aren't automatically replicated between servers
    unless the client went out and wrote the value multiple time.

    The memcache server to use is determined by `python-memcached` itself by
    picking the host to use (from the given server list) based on a key hash.
    """

    # Composed from GenericMemcachedBackend's and MemcacheArgs's __init__
    def __init__(self, arguments):
        super(PooledMemcachedBackend, self).__init__(arguments)
        if (arguments.get('tls_enabled', False) or
                arguments.get('sasl_enabled', False)):
            if (arguments.get('sasl_enabled', False) and
                (arguments.get('username') is None or
                    arguments.get('password') is None)):
                raise exception.ConfigurationError(
                    'username and password should be configured to use SASL '
                    'authentication.')
            if not _bmemcache_pool:
                raise ImportError("python-binary-memcached package is missing")
            self.client_pool = _bmemcache_pool.BMemcacheClientPool(
                self.url,
                arguments,
                maxsize=arguments.get('pool_maxsize', 10),
                unused_timeout=arguments.get('pool_unused_timeout', 60),
                conn_get_timeout=arguments.get('pool_connection_get_timeout',
                                               10),
            )
        else:
            self.client_pool = _memcache_pool.MemcacheClientPool(
                self.url,
                arguments,
                maxsize=arguments.get('pool_maxsize', 10),
                unused_timeout=arguments.get('pool_unused_timeout', 60),
                conn_get_timeout=arguments.get('pool_connection_get_timeout',
                                               10),
            )

    # Since all methods in backend just call one of methods of client, this
    # lets us avoid need to hack it too much
    @property
    def client(self):
        return ClientProxy(self.client_pool)
