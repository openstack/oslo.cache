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

from oslo_config import cfg


_DEFAULT_BACKEND = 'dogpile.cache.null'

FILE_OPTIONS = {
    'cache': [
        cfg.StrOpt('config_prefix', default='cache.oslo',
                   help='Prefix for building the configuration dictionary '
                        'for the cache region. This should not need to be '
                        'changed unless there is another dogpile.cache '
                        'region with the same configuration name.'),
        cfg.IntOpt('expiration_time', default=600,
                   min=1,
                   help='Default TTL, in seconds, for any cached item in '
                        'the dogpile.cache region. This applies to any '
                        'cached method that doesn\'t have an explicit '
                        'cache expiration time defined for it.'),
        cfg.IntOpt('backend_expiration_time',
                   min=1,
                   help='Expiration time in cache backend to purge '
                        'expired records automatically. This should be '
                        'greater than expiration_time and all cache_time '
                        'options'),
        # NOTE(morganfainberg): It is recommended that either Redis or
        # Memcached are used as the dogpile backend for real workloads. To
        # prevent issues with the memory cache ending up in "production"
        # unintentionally, we register a no-op as the default caching backend.
        cfg.StrOpt('backend', default=_DEFAULT_BACKEND,
                   choices=['oslo_cache.memcache_pool',
                            'oslo_cache.dict',
                            'oslo_cache.mongo',
                            'oslo_cache.etcd3gw',
                            'dogpile.cache.pymemcache',
                            'dogpile.cache.memcached',
                            'dogpile.cache.pylibmc',
                            'dogpile.cache.bmemcached',
                            'dogpile.cache.dbm',
                            'dogpile.cache.redis',
                            'dogpile.cache.redis_sentinel',
                            'dogpile.cache.memory',
                            'dogpile.cache.memory_pickle',
                            'dogpile.cache.null'],
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
                    help='Memcache servers in the format of "host:port". '
                         'This is used by backends dependent on Memcached.'
                         'If ``dogpile.cache.memcached`` or '
                         '``oslo_cache.memcache_pool`` is used and a given '
                         'host refer to an IPv6 or a given domain refer to '
                         'IPv6 then you should prefix the given address with '
                         'the address family (``inet6``) '
                         '(e.g ``inet6[::1]:11211``, '
                         '``inet6:[fd12:3456:789a:1::1]:11211``, '
                         '``inet6:[controller-0.internalapi]:11211``). '
                         'If the address family is not given then these '
                         'backends will use the default ``inet`` address '
                         'family which corresponds to IPv4'),
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
        cfg.BoolOpt('memcache_pool_flush_on_reconnect',
                    default=False,
                    help='Global toggle if memcache will be flushed'
                    ' on reconnect.'
                    ' (oslo_cache.memcache_pool backend only).'),
        cfg.BoolOpt('memcache_sasl_enabled',
                    default=False,
                    help='Enable the SASL(Simple Authentication and Security'
                         'Layer) if the SASL_enable is true, else disable.'),
        cfg.StrOpt('memcache_username',
                   help='the user name for the memcached which SASL enabled'),
        cfg.StrOpt('memcache_password',
                   secret=True,
                   help='the password for the memcached which SASL enabled'),
        cfg.StrOpt('redis_server',
                   default='localhost:6379',
                   help='Redis server in the format of "host:port"'),
        cfg.IntOpt('redis_db',
                   default=0,
                   min=0,
                   help='Database id in Redis server'),
        cfg.StrOpt('redis_username',
                   help='the user name for redis'),
        cfg.StrOpt('redis_password',
                   secret=True,
                   help='the password for redis'),
        cfg.ListOpt('redis_sentinels',
                    default=['localhost:26379'],
                    help='Redis sentinel servers in the format of '
                         '"host:port"'),
        cfg.FloatOpt('redis_socket_timeout',
                     default=1.0,
                     help='Timeout in seconds for every call to a server.'
                     ' (dogpile.cache.redis and dogpile.cache.redis_sentinel '
                     'backends only).'),
        cfg.StrOpt('redis_sentinel_service_name',
                   default='mymaster',
                   help='Service name of the redis sentinel cluster.'),
        cfg.BoolOpt('tls_enabled',
                    default=False,
                    help='Global toggle for TLS usage when communicating with'
                    ' the caching servers. Currently supported by '
                    '``dogpile.cache.bmemcache``, '
                    '``dogpile.cache.pymemcache``, '
                    '``oslo_cache.memcache_pool``, '
                    '``dogpile.cache.redis`` and '
                    '``dogpile.cache.redis_sentinel``.'),
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
                   ' private key in. Otherwise the private key will be taken'
                   ' from the file specified in tls_certfile. If tls_enabled'
                   ' is False, this option is ignored.'),
        cfg.StrOpt('tls_allowed_ciphers',
                   default=None,
                   help='Set the available ciphers for sockets created with'
                   ' the TLS context. It should be a string in the OpenSSL'
                   ' cipher list format. If not specified, all OpenSSL enabled'
                   ' ciphers will be available. Currently supported by '
                   '``dogpile.cache.bmemcache``, '
                   '``dogpile.cache.pymemcache`` and '
                   '``oslo_cache.memcache_pool``.'),
        cfg.BoolOpt(
            'enable_socket_keepalive',
            default=False,
            help="Global toggle for the socket keepalive of "
            "dogpile's pymemcache backend"),
        cfg.IntOpt(
            'socket_keepalive_idle',
            default=1,
            min=0,
            help='The time (in seconds) the connection needs to '
            'remain idle before TCP starts sending keepalive probes. '
            'Should be a positive integer most greater than zero.'),
        cfg.IntOpt(
            'socket_keepalive_interval',
            default=1,
            min=0,
            help='The time (in seconds) between individual keepalive '
            'probes. Should be a positive integer greater '
            'than zero.'),
        cfg.IntOpt(
            'socket_keepalive_count',
            default=1,
            min=0,
            help='The maximum number of keepalive probes TCP should '
            'send before dropping the connection. Should be a '
            'positive integer greater than zero.'),
        cfg.BoolOpt(
            'enable_retry_client',
            default=False,
            help='Enable retry client mechanisms to handle failure. '
            'Those mechanisms can be used to wrap all kind of pymemcache '
            'clients. The wrapper allows you to define how many attempts '
            'to make and how long to wait between attemots.'),
        cfg.IntOpt(
            'retry_attempts',
            min=1,
            default=2,
            help='Number of times to attempt an action before failing.'),
        cfg.FloatOpt(
            'retry_delay',
            default=0,
            help='Number of seconds to sleep between each attempt.'),
        cfg.IntOpt(
            'hashclient_retry_attempts',
            min=1,
            default=2,
            help='Amount of times a client should be tried '
            'before it is marked dead and removed from the pool in '
            'the HashClient\'s internal mechanisms.'),
        cfg.FloatOpt(
            'hashclient_retry_delay',
            default=1,
            help='Time in seconds that should pass between '
            'retry attempts in the HashClient\'s internal mechanisms.'),
        cfg.FloatOpt(
            'dead_timeout',
            default=60,
            help='Time in seconds before attempting to add a node '
            'back in the pool in the HashClient\'s internal mechanisms.'),
        cfg.BoolOpt('enforce_fips_mode',
                    default=False,
                    help='Global toggle for enforcing the OpenSSL FIPS mode. '
                    'This feature requires Python support. '
                    'This is available in Python 3.9 in all '
                    'environments and may have been backported to older '
                    'Python versions on select environments. If the Python '
                    'executable used does not support OpenSSL FIPS mode, '
                    'an exception will be raised. Currently supported by '
                    '``dogpile.cache.bmemcache``, '
                    '``dogpile.cache.pymemcache`` and '
                    '``oslo_cache.memcache_pool``.'),
    ],
}


def configure(conf):
    for section in FILE_OPTIONS:
        for option in FILE_OPTIONS[section]:
            conf.register_opt(option, group=section)


def set_defaults(conf, memcache_pool_flush_on_reconnect=False):
    """Set defaults for configuration variables.

    Overrides default options values.

    :param conf: Configuration object, managed by the caller.
    :type conf: oslo.config.cfg.ConfigOpts

    :param memcache_pool_flush_on_reconnect: The default state for the
        ``flush_on_reconnect`` flag. By default deactivated
    :type memcache_pool_flush_on_reconnect: bool
    """
    conf.register_opt(FILE_OPTIONS, group='cache')

    cfg.set_defaults(
        FILE_OPTIONS,
        memcache_pool_flush_on_reconnect=memcache_pool_flush_on_reconnect)


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
