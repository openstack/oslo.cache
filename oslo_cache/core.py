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

"""Caching Layer Implementation.

To use this library:

You must call :func:`configure`.

Inside your application code, decorate the methods that you want the results
to be cached with a memoization decorator created with
:func:`get_memoization_decorator`. This function takes a group name from the
config. Register [`group`] ``caching`` and [`group`] ``cache_time`` options
for the groups that your decorators use so that caching can be configured.

This library's configuration options must be registered in your application's
:class:`oslo_config.cfg.ConfigOpts` instance. Do this by passing the ConfigOpts
instance to :func:`configure`.

The library has special public value for nonexistent or expired keys called
:data:`NO_VALUE`. To use this value you should import it from oslo_cache.core::

    from oslo_cache import core
    NO_VALUE = core.NO_VALUE
"""
import re
import ssl
import urllib.parse

import dogpile.cache
from dogpile.cache import api
from dogpile.cache import proxy
from dogpile.cache import util
from oslo_log import log
from oslo_utils import importutils

from oslo_cache._i18n import _
from oslo_cache import _opts
from oslo_cache import exception


__all__ = [
    'configure',
    'configure_cache_region',
    'create_region',
    'get_memoization_decorator',
    'NO_VALUE',
]

NO_VALUE = api.NO_VALUE
"""Value returned for nonexistent or expired keys."""

_LOG = log.getLogger(__name__)


class _DebugProxy(proxy.ProxyBackend):
    """Extra Logging ProxyBackend."""
    # NOTE(morganfainberg): Pass all key/values through repr to ensure we have
    # a clean description of the information.  Without use of repr, it might
    # be possible to run into encode/decode error(s). For logging/debugging
    # purposes encode/decode is irrelevant and we should be looking at the
    # data exactly as it stands.

    def get(self, key):
        value = self.proxied.get(key)
        _LOG.debug('CACHE_GET: Key: "%(key)r" Value: "%(value)r"',
                   {'key': key, 'value': value})
        return value

    def get_multi(self, keys):
        values = self.proxied.get_multi(keys)
        _LOG.debug('CACHE_GET_MULTI: "%(keys)r" Values: "%(values)r"',
                   {'keys': keys, 'values': values})
        return values

    def set(self, key, value):
        _LOG.debug('CACHE_SET: Key: "%(key)r" Value: "%(value)r"',
                   {'key': key, 'value': value})
        return self.proxied.set(key, value)

    def set_multi(self, keys):
        _LOG.debug('CACHE_SET_MULTI: "%r"', keys)
        self.proxied.set_multi(keys)

    def delete(self, key):
        self.proxied.delete(key)
        _LOG.debug('CACHE_DELETE: "%r"', key)

    def delete_multi(self, keys):
        _LOG.debug('CACHE_DELETE_MULTI: "%r"', keys)
        self.proxied.delete_multi(keys)


def _parse_sentinel(sentinel):
    # IPv6 (eg. [::1]:6379 )
    match = re.search(r'^\[(\S+)\]:(\d+)$', sentinel)
    if match:
        return (match[1], int(match[2]))
    # IPv4 or hostname (eg. 127.0.0.1:6379 or localhost:6379)
    match = re.search(r'^(\S+):(\d+)$', sentinel)
    if match:
        return (match[1], int(match[2]))
    raise exception.ConfigurationError('Malformed sentinel server format')


def _build_cache_config(conf):
    """Build the cache region dictionary configuration.

    :returns: dict
    """
    prefix = conf.cache.config_prefix
    conf_dict = {}
    conf_dict['%s.backend' % prefix] = _opts._DEFAULT_BACKEND
    if conf.cache.enabled is True:
        conf_dict['%s.backend' % prefix] = conf.cache.backend
    conf_dict['%s.expiration_time' % prefix] = conf.cache.expiration_time
    for argument in conf.cache.backend_argument:
        try:
            (argname, argvalue) = argument.split(':', 1)
        except ValueError:
            msg = ('Unable to build cache config-key. Expected format '
                   '"<argname>:<value>". Skipping unknown format: %s')
            _LOG.error(msg, argument)
            continue

        arg_key = '.'.join([prefix, 'arguments', argname])
        # NOTE(morgan): The handling of the URL data in memcache is bad and
        # only takes cases where the values are a list. This explicitly
        # checks for the base dogpile.cache.memcached backend and does the
        # split if needed. Other backends such as redis get the same
        # previous behavior. Overall the fact that the backends opaquely
        # take data and do not handle processing/validation as expected
        # directly makes for odd behaviors when wrapping dogpile.cache in
        # a library like oslo.cache
        if (conf.cache.backend
                in ('dogpile.cache.memcached', 'oslo_cache.memcache_pool') and
                argname == 'url'):
            argvalue = argvalue.split(',')
        conf_dict[arg_key] = argvalue

        _LOG.debug('Oslo Cache Config: %s', conf_dict)

    if conf.cache.backend == 'dogpile.cache.redis':
        if conf.cache.redis_password is None:
            netloc = conf.cache.redis_server
        else:
            if conf.cache.redis_username:
                netloc = '%s:%s@%s' % (conf.cache.redis_username,
                                       conf.cache.redis_password,
                                       conf.cache.redis_server)
            else:
                netloc = ':%s@%s' % (conf.cache.redis_password,
                                     conf.cache.redis_server)

        parts = urllib.parse.ParseResult(
            scheme=('rediss' if conf.cache.tls_enabled else 'redis'),
            netloc=netloc, path='', params='', query='', fragment='')

        conf_dict.setdefault(
            '%s.arguments.url' % prefix,
            urllib.parse.urlunparse(parts)
        )
        for arg in ('socket_timeout',):
            value = getattr(conf.cache, 'redis_' + arg)
            conf_dict['%s.arguments.%s' % (prefix, arg)] = value
    elif conf.cache.backend == 'dogpile.cache.redis_sentinel':
        for arg in ('password', 'socket_timeout'):
            value = getattr(conf.cache, 'redis_' + arg)
            conf_dict['%s.arguments.%s' % (prefix, arg)] = value
        if conf.cache.redis_username:
            # TODO(tkajinam): Update dogpile.cache to add username argument,
            # similarly to password.
            conf_dict['%s.arguments.connection_kwargs' % prefix] = \
                {'username': conf.cache.redis_username}
            conf_dict['%s.arguments.sentinel_kwargs' % prefix] = \
                {'username': conf.cache.redis_username}
        conf_dict['%s.arguments.service_name' % prefix] = \
            conf.cache.redis_sentinel_service_name
        if conf.cache.redis_sentinels:
            conf_dict['%s.arguments.sentinels' % prefix] = [
                _parse_sentinel(s) for s in conf.cache.redis_sentinels]
    else:
        # NOTE(yorik-sar): these arguments will be used for memcache-related
        # backends. Use setdefault for url to support old-style setting through
        # backend_argument=url:127.0.0.1:11211
        #
        # NOTE(morgan): If requested by config, 'flush_on_reconnect' will be
        # set for pooled connections. This can ensure that stale data is never
        # consumed from a server that pops in/out due to a network partition
        # or disconnect.
        #
        # See the help from python-memcached:
        #
        # param flush_on_reconnect: optional flag which prevents a
        #        scenario that can cause stale data to be read: If there's more
        #        than one memcached server and the connection to one is
        #        interrupted, keys that mapped to that server will get
        #        reassigned to another. If the first server comes back, those
        #        keys will map to it again. If it still has its data, get()s
        #        can read stale data that was overwritten on another
        #        server. This flag is off by default for backwards
        #        compatibility.
        #
        # The normal non-pooled clients connect explicitly on each use and
        # does not need the explicit flush_on_reconnect
        conf_dict.setdefault('%s.arguments.url' % prefix,
                             conf.cache.memcache_servers)

        for arg in ('dead_retry', 'socket_timeout', 'pool_maxsize',
                    'pool_unused_timeout', 'pool_connection_get_timeout',
                    'pool_flush_on_reconnect', 'sasl_enabled', 'username',
                    'password'):
            value = getattr(conf.cache, 'memcache_' + arg)
            conf_dict['%s.arguments.%s' % (prefix, arg)] = value

    if conf.cache.tls_enabled:
        if conf.cache.backend in ('dogpile.cache.bmemcache',
                                  'dogpile.cache.pymemcache',
                                  'oslo_cache.memcache_pool'):
            _LOG.debug('Oslo Cache TLS - CA: %s', conf.cache.tls_cafile)
            tls_context = ssl.create_default_context(
                cafile=conf.cache.tls_cafile)

            if conf.cache.enforce_fips_mode:
                if hasattr(ssl, 'FIPS_mode'):
                    _LOG.info("Enforcing the use of the OpenSSL FIPS mode")
                    ssl.FIPS_mode_set(1)
                else:
                    raise exception.ConfigurationError(
                        "OpenSSL FIPS mode is not supported by your Python "
                        "version. You must either change the Python "
                        "executable used to a version with FIPS mode support "
                        "or disable FIPS mode by setting "
                        "the '[cache] enforce_fips_mode' configuration option "
                        "to 'False'.")

            if conf.cache.tls_certfile is not None:
                _LOG.debug('Oslo Cache TLS - cert: %s',
                           conf.cache.tls_certfile)
                _LOG.debug('Oslo Cache TLS - key: %s', conf.cache.tls_keyfile)
                tls_context.load_cert_chain(
                    conf.cache.tls_certfile,
                    conf.cache.tls_keyfile,
                )

            if conf.cache.tls_allowed_ciphers is not None:
                _LOG.debug(
                    'Oslo Cache TLS - ciphers: %s',
                    conf.cache.tls_allowed_ciphers,
                )
                tls_context.set_ciphers(conf.cache.tls_allowed_ciphers)

            conf_dict['%s.arguments.tls_context' % prefix] = tls_context

            # pass the value of tls_enabled to the backend
            conf_dict['%s.arguments.tls_enabled' % prefix] = \
                conf.cache.tls_enabled
        elif conf.cache.backend in ('dogpile.cache.redis',
                                    'dogpile.cache.redis_sentinel'):
            if conf.cache.tls_allowed_ciphers is not None:
                raise exception.ConfigurationError(
                    "Limiting allowed ciphers is not supported by "
                    "the %s backend" % conf.cache.backend)
            if conf.cache.enforce_fips_mode:
                raise exception.ConfigurationError(
                    "FIPS mode is not supported by the %s backend" %
                    conf.cache.backend)

            conn_kwargs = {}
            if conf.cache.tls_cafile is not None:
                _LOG.debug('Oslo Cache TLS - CA: %s', conf.cache.tls_cafile)
                conn_kwargs['ssl_ca_certs'] = conf.cache.tls_cafile
            if conf.cache.tls_certfile is not None:
                _LOG.debug('Oslo Cache TLS - cert: %s',
                           conf.cache.tls_certfile)
                _LOG.debug('Oslo Cache TLS - key: %s', conf.cache.tls_keyfile)
                conn_kwargs.update({
                    'ssl_certfile': conf.cache.tls_certfile,
                    'ssl_keyfile': conf.cache.tls_keyfile
                })
            if conf.cache.backend == 'dogpile.cache.redis_sentinel':
                conn_kwargs.update({'ssl': True})
                conf_dict.setdefault(
                    '%s.arguments.connection_kwargs' % prefix,
                    {}).update(conn_kwargs)
                conf_dict.setdefault(
                    '%s.arguments.sentinel_kwargs' % prefix,
                    {}).update(conn_kwargs)
            else:
                conf_dict.setdefault(
                    '%s.arguments.connection_kwargs' % prefix,
                    {}).update(conn_kwargs)
        else:
            raise exception.ConfigurationError(
                "TLS setting via [cache] tls_enabled is not supported by the "
                "%s backend. Set [cache] tls_enabled=False or use a different "
                "backend." % conf.cache.backend
            )

    # NOTE(hberaud): Pymemcache support socket keepalive, If it is enable in
    # our config then configure it to enable this feature.
    # The socket keepalive feature means that pymemcache will be able to check
    # your connected socket and determine whether the connection is still up
    # and running or if it has broken.
    # This could be used by users who want to handle fine grained failures.
    if conf.cache.enable_socket_keepalive:
        if conf.cache.backend != 'dogpile.cache.pymemcache':
            msg = _(
                "Socket keepalive is only supported by the "
                "'dogpile.cache.pymemcache' backend."
            )
            raise exception.ConfigurationError(msg)
        import pymemcache
        socket_keepalive = pymemcache.KeepaliveOpts(
            idle=conf.cache.socket_keepalive_idle,
            intvl=conf.cache.socket_keepalive_interval,
            cnt=conf.cache.socket_keepalive_count)
        # As with the TLS context above, the config dict below will be
        # consumed by dogpile.cache that will be used as a proxy between
        # oslo.cache and pymemcache.
        conf_dict['%s.arguments.socket_keepalive' % prefix] = socket_keepalive

    # NOTE(hberaud): The pymemcache library comes with retry mechanisms that
    # can be used to wrap all kind of pymemcache clients. The retry wrapper
    # allow you to define how many attempts to make and how long to wait
    # between attempts. The section below will pass our config
    # to dogpile.cache to setup the pymemcache retry client wrapper.
    if conf.cache.enable_retry_client:
        if conf.cache.backend != 'dogpile.cache.pymemcache':
            msg = _(
                "Retry client is only supported by the "
                "'dogpile.cache.pymemcache' backend."
            )
            raise exception.ConfigurationError(msg)
        import pymemcache
        conf_dict['%s.arguments.enable_retry_client' % prefix] = True
        conf_dict['%s.arguments.retry_attempts' % prefix] = \
            conf.cache.retry_attempts
        conf_dict['%s.arguments.retry_delay' % prefix] = \
            conf.cache.retry_delay
        conf_dict['%s.arguments.hashclient_retry_attempts' % prefix] = \
            conf.cache.hashclient_retry_attempts
        conf_dict['%s.arguments.hashclient_retry_delay' % prefix] = \
            conf.cache.hashclient_retry_delay
        conf_dict['%s.arguments.dead_timeout' % prefix] = \
            conf.cache.dead_timeout

    return conf_dict


def _sha1_mangle_key(key):
    """Wrapper for dogpile's sha1_mangle_key.

    dogpile's sha1_mangle_key function expects an encoded string, so we
    should take steps to properly handle multiple inputs before passing
    the key through.
    """
    try:
        key = key.encode('utf-8', errors='xmlcharrefreplace')
    except (UnicodeError, AttributeError):
        # NOTE(stevemar): if encoding fails just continue anyway.
        pass
    return util.sha1_mangle_key(key)


def _key_generate_to_str(s):
    # NOTE(morganfainberg): Since we need to stringify all arguments, attempt
    # to stringify and handle the Unicode error explicitly as needed.
    try:
        return str(s)
    except UnicodeEncodeError:
        return s.encode('utf-8')


def function_key_generator(namespace, fn, to_str=_key_generate_to_str):
    # NOTE(morganfainberg): This wraps dogpile.cache's default
    # function_key_generator to change the default to_str mechanism.
    return util.function_key_generator(namespace, fn, to_str=to_str)


def kwarg_function_key_generator(namespace, fn, to_str=_key_generate_to_str):
    # NOTE(ralonsoh): This wraps dogpile.cache's default
    # kwarg_function_key_generator to change the default to_str mechanism.
    return util.kwarg_function_key_generator(namespace, fn, to_str=to_str)


def create_region(function=function_key_generator):
    """Create a region.

    This is just dogpile.cache.make_region, but the key generator has a
    different to_str mechanism.

    .. note::

        You must call :func:`configure_cache_region` with this region before
        a memoized method is called.

    :param function: function used to generate a unique key depending on the
                     arguments of the decorated function
    :type function: function
    :returns: The new region.
    :rtype: :class:`dogpile.cache.region.CacheRegion`

    """

    return dogpile.cache.make_region(function_key_generator=function)


def configure_cache_region(conf, region):
    """Configure a cache region.

    If the cache region is already configured, this function does nothing.
    Otherwise, the region is configured.

    :param conf: config object, must have had :func:`configure` called on it.
    :type conf: oslo_config.cfg.ConfigOpts
    :param region: Cache region to configure (see :func:`create_region`).
    :type region: dogpile.cache.region.CacheRegion
    :raises oslo_cache.exception.ConfigurationError: If the region parameter is
        not a dogpile.cache.CacheRegion.
    :returns: The region.
    :rtype: :class:`dogpile.cache.region.CacheRegion`
    """
    if not isinstance(region, dogpile.cache.CacheRegion):
        raise exception.ConfigurationError(
            _('region not type dogpile.cache.CacheRegion'))

    if not region.is_configured:
        # NOTE(morganfainberg): this is how you tell if a region is configured.
        # There is a request logged with dogpile.cache upstream to make this
        # easier / less ugly.

        config_dict = _build_cache_config(conf)
        region.configure_from_config(config_dict,
                                     '%s.' % conf.cache.config_prefix)

        if conf.cache.debug_cache_backend:
            region.wrap(_DebugProxy)

        # NOTE(morganfainberg): if the backend requests the use of a
        # key_mangler, we should respect that key_mangler function.  If a
        # key_mangler is not defined by the backend, use the sha1_mangle_key
        # mangler provided by dogpile.cache. This ensures we always use a fixed
        # size cache-key.
        if region.key_mangler is None:
            region.key_mangler = _sha1_mangle_key

        for class_path in conf.cache.proxies:
            # NOTE(morganfainberg): if we have any proxy wrappers, we should
            # ensure they are added to the cache region's backend.  Since
            # configure_from_config doesn't handle the wrap argument, we need
            # to manually add the Proxies. For information on how the
            # ProxyBackends work, see the dogpile.cache documents on
            # "changing-backend-behavior"
            cls = importutils.import_class(class_path)
            _LOG.debug("Adding cache-proxy '%s' to backend.", class_path)
            region.wrap(cls)

    return region


def _get_should_cache_fn(conf, group):
    """Build a function that returns a config group's caching status.

    For any given object that has caching capabilities, a boolean config option
    for that object's group should exist and default to ``True``. This
    function will use that value to tell the caching decorator if caching for
    that object is enabled. To properly use this with the decorator, pass this
    function the configuration group and assign the result to a variable.
    Pass the new variable to the caching decorator as the named argument
    ``should_cache_fn``.

    :param conf: config object, must have had :func:`configure` called on it.
    :type conf: oslo_config.cfg.ConfigOpts
    :param group: name of the configuration group to examine
    :type group: string
    :returns: function reference
    """
    def should_cache(value):
        if not conf.cache.enabled:
            return False
        conf_group = getattr(conf, group)
        return getattr(conf_group, 'caching', True)
    return should_cache


def _get_expiration_time_fn(conf, group):
    """Build a function that returns a config group's expiration time status.

    For any given object that has caching capabilities, an int config option
    called ``cache_time`` for that driver's group should exist and typically
    default to ``None``. This function will use that value to tell the caching
    decorator of the TTL override for caching the resulting objects. If the
    value of the config option is ``None`` the default value provided in the
    ``[cache] expiration_time`` option will be used by the decorator. The
    default may be set to something other than ``None`` in cases where the
    caching TTL should not be tied to the global default(s).

    To properly use this with the decorator, pass this function the
    configuration group and assign the result to a variable. Pass the new
    variable to the caching decorator as the named argument
    ``expiration_time``.

    :param group: name of the configuration group to examine
    :type group: string
    :rtype: function reference
    """
    def get_expiration_time():
        conf_group = getattr(conf, group)
        return getattr(conf_group, 'cache_time', None)
    return get_expiration_time


def get_memoization_decorator(conf, region, group, expiration_group=None):
    """Build a function based on the `cache_on_arguments` decorator.

    The memoization decorator that gets created by this function is a
    :meth:`dogpile.cache.region.CacheRegion.cache_on_arguments` decorator,
    where

    * The ``should_cache_fn`` is set to a function that returns True if both
      the ``[cache] enabled`` option is true and [`group`] ``caching`` is
      True.

    * The ``expiration_time`` is set from the
      [`expiration_group`] ``cache_time`` option if ``expiration_group``
      is passed in and the value is set, or [`group`] ``cache_time`` if
      ``expiration_group`` is not passed in and the value is set, or
      ``[cache] expiration_time`` otherwise.

    Example usage::

        import oslo_cache.core

        MEMOIZE = oslo_cache.core.get_memoization_decorator(
            conf, region, group='group1')

        @MEMOIZE
        def function(arg1, arg2):
            ...


        ALTERNATE_MEMOIZE = oslo_cache.core.get_memoization_decorator(
            conf, region, group='group2', expiration_group='group3')

        @ALTERNATE_MEMOIZE
        def function2(arg1, arg2):
            ...

    :param conf: config object, must have had :func:`configure` called on it.
    :type conf: oslo_config.cfg.ConfigOpts
    :param region: region as created by :func:`create_region`.
    :type region: dogpile.cache.region.CacheRegion
    :param group: name of the configuration group to examine
    :type group: string
    :param expiration_group: name of the configuration group to examine
                             for the expiration option. This will fall back to
                             using ``group`` if the value is unspecified or
                             ``None``
    :type expiration_group: string
    :rtype: function reference
    """
    if expiration_group is None:
        expiration_group = group
    should_cache = _get_should_cache_fn(conf, group)
    expiration_time = _get_expiration_time_fn(conf, expiration_group)

    memoize = region.cache_on_arguments(should_cache_fn=should_cache,
                                        expiration_time=expiration_time)

    # Make sure the actual "should_cache" and "expiration_time" methods are
    # available. This is potentially interesting/useful to pre-seed cache
    # values.
    memoize.should_cache = should_cache
    memoize.get_expiration_time = expiration_time

    return memoize


def configure(conf):
    """Configure the library.

    Register the required oslo.cache config options into an oslo.config CONF
    object.

    This must be called before :py:func:`configure_cache_region`.

    :param conf: The configuration object.
    :type conf: oslo_config.cfg.ConfigOpts
    """
    _opts.configure(conf)
