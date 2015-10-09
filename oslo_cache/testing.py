# Copyright 2013 Metacloud
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

"""Items useful for external testing."""


import copy

from dogpile.cache import proxy

from oslo_cache import core as cache


__all__ = [
    'CacheIsolatingProxy',
]


NO_VALUE = cache.NO_VALUE


def _copy_value(value):
    if value is not NO_VALUE:
        value = copy.deepcopy(value)
    return value


# NOTE(morganfainberg): WARNING - It is not recommended to use the Memory
# backend for dogpile.cache in a real deployment under any circumstances. The
# backend does no cleanup of expired values and therefore will leak memory. The
# backend is not implemented in a way to share data across processes (e.g.
# Keystone in HTTPD.  This proxy is a hack to get around the lack of isolation
# of values in memory.  Currently it blindly stores and retrieves the values
# from the cache, and modifications to dicts/lists/etc returned can result in
# changes to the cached values.  In short, do not use the dogpile.cache.memory
# backend unless you are running tests or expecting odd/strange results.
class CacheIsolatingProxy(proxy.ProxyBackend):
    """Proxy that forces a memory copy of stored values.

    The default in-memory cache-region does not perform a copy on values it
    is meant to cache.  Therefore if the value is modified after set or after
    get, the cached value also is modified.  This proxy does a copy as the last
    thing before storing data.

    In your application's tests, you'll want to set this as a proxy for the
    in-memory cache, like this::

        self.config_fixture.config(
            group='cache',
            backend='dogpile.cache.memory',
            enabled=True,
            proxies=['oslo_cache.testing.CacheIsolatingProxy'])

    """
    def get(self, key):
        return _copy_value(self.proxied.get(key))

    def set(self, key, value):
        self.proxied.set(key, _copy_value(value))
