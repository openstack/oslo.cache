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

import dogpile

from oslo_config import cfg


_DEFAULT_BACKEND = 'dogpile.cache.null'

_backend_choices = [
    'oslo_cache.memcache_pool',
    'oslo_cache.dict',
    'oslo_cache.mongo',
    'oslo_cache.etcd3gw',
    'dogpile.cache.memcached',
    'dogpile.cache.pylibmc',
    'dogpile.cache.bmemcached',
    'dogpile.cache.dbm',
    'dogpile.cache.redis',
    'dogpile.cache.memory',
    'dogpile.cache.memory_pickle',
    'dogpile.cache.null'
]

# NOTE(moguimar): dogpile.cache.pymemcache is currently the best
# driver for using Memcached with TLS. This backport is intent for
# security purposes.
if dogpile.__version__ >= '1.1.2':
    _backend_choices.append('dogpile.cache.pymemcache')

FILE_OPTIONS = {
    'cache': [
        cfg.StrOpt('config_prefix', default='cache.oslo',
                   help='Prefix for building the configuration dictionary '
                        'for the cache region. This should not need to be '
                        'changed unless there is another dogpile.cache '
                        'region with the same configuration name.'),
        cfg.IntOpt('expiration_time', default=600,
                   help='Default TTL, in seconds, for any cached item in '
                        'the dogpile.cache region. This applies to any '
                        'cached method that doesn\'t have an explicit '
                        'cache expiration time defined for it.'),
        # NOTE(morganfainberg): It is recommended that either Redis or
        # Memcached are used as the dogpile backend for real workloads. To
        # prevent issues with the memory cache ending up in "production"
        # unintentionally, we register a no-op as the default caching backend.
        cfg.StrOpt('backend', default=_DEFAULT_BACKEND,
                   choices=_backend_choices,
                   help='Cache backend module. For eventlet-based or '
                   'environments with hundreds of threaded servers, Memcache '
                   'with pooling (oslo_cache.memcache_pool) is recommended. '
                   'For environments with less than 100 threaded servers, '
                   'Memcached (dogpile.cache.memcached) or Redis '
                   '(dogpile.cache.redis) is recommended. Test environments '
                   'with a single instance of the server can use the '
                   'dogpile.cache.memory backend.'),
        cfg.MultiStrOpt('backend_argument', default=[], secret=True,
                        help='Arguments supplied to the backend module. '
                             'Specify this option once per argument to be '
                             'passed to the dogpile.cache backend. Example '
                             'format: "<argname>:<value>".'),
        cfg.ListOpt('proxies', default=[],
                    help='Proxy classes to import that will affect the way '
                         'the dogpile.cache backend functions. See the '
                         'dogpile.cache documentation on '
                         'changing-backend-behavior.'),
        cfg.BoolOpt('enabled', default=False,
                    help='Global toggle for caching.'),
        cfg.BoolOpt('debug_cache_backend', default=False,
                    help='Extra debugging from the cache backend (cache '
                         'keys, get/set/delete/etc calls). This is only '
                         'really useful if you need to see the specific '
                         'cache-backend get/set/delete calls with the '
                         'keys/values.  Typically this should be left set '
                         'to false.'),
        cfg.ListOpt('memcache_servers', default=['localhost:11211'],
                    help='Memcache servers in the format of "host:port".'
                    ' (dogpile.cache.memcache and oslo_cache.memcache_pool'
                    ' backends only).'),
        cfg.IntOpt('memcache_dead_retry',
                   default=5 * 60,
                   help='Number of seconds memcached server is considered dead'
                   ' before it is tried again. (dogpile.cache.memcache and'
                   ' oslo_cache.memcache_pool backends only).'),
        cfg.FloatOpt('memcache_socket_timeout',
                     default=1.0,
                     help='Timeout in seconds for every call to a server.'
                     ' (dogpile.cache.memcache and oslo_cache.memcache_pool'
                     ' backends only).'),
        cfg.IntOpt('memcache_pool_maxsize',
                   default=10,
                   help='Max total number of open connections to every'
                   ' memcached server. (oslo_cache.memcache_pool backend'
                   ' only).'),
        cfg.IntOpt('memcache_pool_unused_timeout',
                   default=60,
                   help='Number of seconds a connection to memcached is held'
                   ' unused in the pool before it is closed.'
                   ' (oslo_cache.memcache_pool backend only).'),
        cfg.IntOpt('memcache_pool_connection_get_timeout',
                   default=10,
                   help='Number of seconds that an operation will wait to get '
                        'a memcache client connection.'),
        cfg.BoolOpt('tls_enabled',
                    default=False,
                    help='Global toggle for TLS usage when comunicating with'
                    ' the caching servers.'),
        cfg.StrOpt('tls_cafile',
                   default=None,
                   help='Path to a file of concatenated CA certificates in PEM'
                   ' format necessary to establish the caching servers\''
                   ' authenticity. If tls_enabled is False, this option is'
                   ' ignored.'),
        cfg.StrOpt('tls_certfile',
                   default=None,
                   help='Path to a single file in PEM format containing the'
                   ' client\'s certificate as well as any number of CA'
                   ' certificates needed to establish the certificate\'s'
                   ' authenticity. This file is only required when client side'
                   ' authentication is necessary. If tls_enabled is False,'
                   ' this option is ignored.'),
        cfg.StrOpt('tls_keyfile',
                   default=None,
                   help='Path to a single file containing the client\'s'
                   ' private key in. Otherwhise the private key will be taken'
                   ' from the file specified in tls_certfile. If tls_enabled'
                   ' is False, this option is ignored.'),
        cfg.StrOpt('tls_allowed_ciphers',
                   default=None,
                   help='Set the available ciphers for sockets created with'
                   ' the TLS context. It should be a string in the OpenSSL'
                   ' cipher list format. If not specified, all OpenSSL enabled'
                   ' ciphers will be available.'),
    ],
}


def configure(conf):
    for section in FILE_OPTIONS:
        for option in FILE_OPTIONS[section]:
            conf.register_opt(option, group=section)


def list_opts():
    """Return a list of oslo_config options.

    The returned list includes all oslo_config options which are registered as
    the "FILE_OPTIONS".

    Each object in the list is a two element tuple. The first element of
    each tuple is the name of the group under which the list of options in the
    second element will be registered. A group name of None corresponds to the
    [DEFAULT] group in config files.

    This function is also discoverable via the 'oslo_config.opts' entry point
    under the 'oslo_cache.config.opts' namespace.

    The purpose of this is to allow tools like the Oslo sample config file
    generator to discover the options exposed to users by this library.

    :returns: a list of (group_name, opts) tuples
    """
    return list(FILE_OPTIONS.items())
