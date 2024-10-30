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

import copy
import socket
import ssl
import time
from unittest import mock

from dogpile.cache import proxy
from oslo_config import cfg
from oslo_utils import uuidutils
from pymemcache import KeepaliveOpts

from oslo_cache import _opts
from oslo_cache import core as cache
from oslo_cache import exception
from oslo_cache.tests import test_cache


NO_VALUE = cache.NO_VALUE
TEST_GROUP = uuidutils.generate_uuid(dashed=False)
TEST_GROUP2 = uuidutils.generate_uuid(dashed=False)


def _copy_value(value):
    if value is not NO_VALUE:
        value = copy.deepcopy(value)
    return value


class TestProxy(proxy.ProxyBackend):
    def get(self, key):
        value = _copy_value(self.proxied.get(key))
        if value is not NO_VALUE:
            if isinstance(value[0], TestProxyValue):
                value[0].cached = True
        return value


class TestProxyValue:
    def __init__(self, value):
        self.value = value
        self.cached = False


class CacheRegionTest(test_cache.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.region = cache.create_region()
        cache.configure_cache_region(self.config_fixture.conf, self.region)
        self.region.wrap(TestProxy)
        self.region_kwargs = cache.create_region(
            function=cache.kwarg_function_key_generator)
        cache.configure_cache_region(self.config_fixture.conf,
                                     self.region_kwargs)
        self.region_kwargs.wrap(TestProxy)
        self.test_value = TestProxyValue('Decorator Test')

    def _add_test_caching_option(self):
        self.config_fixture.register_opt(
            cfg.BoolOpt('caching', default=True), group='cache')

    def _add_dummy_config_group(self):
        self.config_fixture.register_opt(
            cfg.IntOpt('cache_time'), group=TEST_GROUP)
        self.config_fixture.register_opt(
            cfg.IntOpt('cache_time'), group=TEST_GROUP2)

    def _get_cacheable_function(self, region=None):
        region = region if region else self.region
        memoize = cache.get_memoization_decorator(
            self.config_fixture.conf, region, group='cache')

        @memoize
        def cacheable_function(value=0, **kw):
            return value

        return cacheable_function

    def test_region_built_with_proxy_direct_cache_test(self):
        # Verify cache regions are properly built with proxies.
        test_value = TestProxyValue('Direct Cache Test')
        self.region.set('cache_test', test_value)
        cached_value = self.region.get('cache_test')
        self.assertTrue(cached_value.cached)

    def test_cache_region_no_error_multiple_config(self):
        # Verify configuring the CacheRegion again doesn't error.
        cache.configure_cache_region(self.config_fixture.conf, self.region)
        cache.configure_cache_region(self.config_fixture.conf, self.region)

    def _get_cache_fallthrough_fn(self, cache_time):
        memoize = cache.get_memoization_decorator(
            self.config_fixture.conf,
            self.region,
            group='cache',
            expiration_group=TEST_GROUP2)

        class _test_obj:
            def __init__(self, value):
                self.test_value = value

            @memoize
            def get_test_value(self):
                return self.test_value

        def _do_test(value):

            test_obj = _test_obj(value)

            # Ensure the value has been cached
            test_obj.get_test_value()
            # Get the now cached value
            cached_value = test_obj.get_test_value()
            self.assertTrue(cached_value.cached)
            self.assertEqual(value.value, cached_value.value)
            self.assertEqual(cached_value.value, test_obj.test_value.value)
            # Change the underlying value on the test object.
            test_obj.test_value = TestProxyValue(
                uuidutils.generate_uuid(dashed=False))
            self.assertEqual(cached_value.value,
                             test_obj.get_test_value().value)
            # override the system time to ensure the non-cached new value
            # is returned
            new_time = time.time() + (cache_time * 2)
            with mock.patch.object(time, 'time',
                                   return_value=new_time):
                overriden_cache_value = test_obj.get_test_value()
                self.assertNotEqual(cached_value.value,
                                    overriden_cache_value.value)
                self.assertEqual(test_obj.test_value.value,
                                 overriden_cache_value.value)

        return _do_test

    def test_cache_no_fallthrough_expiration_time_fn(self):
        self._add_dummy_config_group()
        # Since we do not re-configure the cache region, for ease of testing
        # this value is set the same as the expiration_time default in the
        # [cache] group
        cache_time = 600
        expiration_time = cache._get_expiration_time_fn(
            self.config_fixture.conf, TEST_GROUP)
        do_test = self._get_cache_fallthrough_fn(cache_time)
        # Run the test with the dummy group cache_time value
        self.config_fixture.config(cache_time=cache_time,
                                   group=TEST_GROUP)
        test_value = TestProxyValue(uuidutils.generate_uuid(dashed=False))
        self.assertEqual(cache_time, expiration_time())
        do_test(value=test_value)

    def test_cache_fallthrough_expiration_time_fn(self):
        self._add_dummy_config_group()
        # Since we do not re-configure the cache region, for ease of testing
        # this value is set the same as the expiration_time default in the
        # [cache] group
        cache_time = 599
        expiration_time = cache._get_expiration_time_fn(
            self.config_fixture.conf, TEST_GROUP)
        do_test = self._get_cache_fallthrough_fn(cache_time)
        # Run the test with the dummy group cache_time value set to None and
        # the global value set.
        self.config_fixture.config(cache_time=None, group=TEST_GROUP)
        test_value = TestProxyValue(
            uuidutils.generate_uuid(dashed=False))
        self.assertIsNone(expiration_time())
        do_test(value=test_value)

    def test_should_cache_fn_global_cache_enabled(self):
        # Verify should_cache_fn generates a sane function for subsystem and
        # functions as expected with caching globally enabled.
        cacheable_function = self._get_cacheable_function()

        self.config_fixture.config(group='cache', enabled=True)
        cacheable_function(self.test_value)
        cached_value = cacheable_function(self.test_value)
        self.assertTrue(cached_value.cached)

    def test_should_cache_fn_global_cache_disabled(self):
        # Verify should_cache_fn generates a sane function for subsystem and
        # functions as expected with caching globally disabled.
        cacheable_function = self._get_cacheable_function()

        self.config_fixture.config(group='cache', enabled=False)
        cacheable_function(self.test_value)
        cached_value = cacheable_function(self.test_value)
        self.assertFalse(cached_value.cached)

    def test_should_cache_fn_global_cache_disabled_group_cache_enabled(self):
        # Verify should_cache_fn generates a sane function for subsystem and
        # functions as expected with caching globally disabled and the specific
        # group caching enabled.
        cacheable_function = self._get_cacheable_function()

        self._add_test_caching_option()
        self.config_fixture.config(group='cache', enabled=False)
        self.config_fixture.config(group='cache', caching=True)

        cacheable_function(self.test_value)
        cached_value = cacheable_function(self.test_value)
        self.assertFalse(cached_value.cached)

    def test_should_cache_fn_global_cache_enabled_group_cache_disabled(self):
        # Verify should_cache_fn generates a sane function for subsystem and
        # functions as expected with caching globally enabled and the specific
        # group caching disabled.
        cacheable_function = self._get_cacheable_function()

        self._add_test_caching_option()
        self.config_fixture.config(group='cache', enabled=True)
        self.config_fixture.config(group='cache', caching=False)

        cacheable_function(self.test_value)
        cached_value = cacheable_function(self.test_value)
        self.assertFalse(cached_value.cached)

    def test_should_cache_fn_global_cache_enabled_group_cache_enabled(self):
        # Verify should_cache_fn generates a sane function for subsystem and
        # functions as expected with caching globally enabled and the specific
        # group caching enabled.
        cacheable_function = self._get_cacheable_function()

        self._add_test_caching_option()
        self.config_fixture.config(group='cache', enabled=True)
        self.config_fixture.config(group='cache', caching=True)

        cacheable_function(self.test_value)
        cached_value = cacheable_function(self.test_value)
        self.assertTrue(cached_value.cached)

    def test_cache_config_builder(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict',
                                   expiration_time=86400,
                                   backend_argument=['arg1:test',
                                                     'arg2:test:test',
                                                     'arg3.invalid'])

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            self.config_fixture.conf.cache.backend,
            config_dict['test_prefix.backend'])
        self.assertEqual(
            self.config_fixture.conf.cache.expiration_time,
            config_dict['test_prefix.expiration_time'])
        self.assertEqual('test', config_dict['test_prefix.arguments.arg1'])
        self.assertEqual('test:test',
                         config_dict['test_prefix.arguments.arg2'])
        self.assertNotIn('test_prefix.arguments.arg3', config_dict)

    def test_cache_config_builder_global_disabled(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=False,
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict')

        self.assertFalse(self.config_fixture.conf.cache.enabled)
        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            _opts._DEFAULT_BACKEND,
            config_dict['test_prefix.backend'])

    def test_cache_config_builder_tls_disabled(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   tls_cafile='path_to_ca_file',
                                   tls_keyfile='path_to_key_file',
                                   tls_certfile='path_to_cert_file',
                                   tls_allowed_ciphers='allowed_ciphers')

        with mock.patch.object(ssl, 'create_default_context'):
            config_dict = cache._build_cache_config(self.config_fixture.conf)

            self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
            ssl.create_default_context.assert_not_called()
            self.assertNotIn('test_prefix.arguments.tls_context', config_dict)

    def test_cache_config_builder_tls_disabled_redis(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   tls_cafile='path_to_ca_file',
                                   tls_keyfile='path_to_key_file',
                                   tls_certfile='path_to_cert_file',
                                   tls_allowed_ciphers='allowed_ciphers')

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://localhost:6379/0',
            config_dict['test_prefix.arguments.url'])
        self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
        self.assertNotIn('test_prefix.arguments.connection_kwargs',
                         config_dict)

    def test_cache_config_builder_tls_disabled_redis_sentinel(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis_sentinel',
                                   tls_cafile='path_to_ca_file',
                                   tls_keyfile='path_to_key_file',
                                   tls_certfile='path_to_cert_file')

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
        self.assertNotIn('test_prefix.arguments.connection_kwargs',
                         config_dict)
        self.assertNotIn('test_prefix.arguments.sentinel_kwargs',
                         config_dict)

    def test_cache_config_builder_tls_enabled(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   tls_enabled=True)

        fake_context = mock.Mock()
        with mock.patch.object(ssl, 'create_default_context',
                               return_value=fake_context):
            config_dict = cache._build_cache_config(self.config_fixture.conf)

            self.assertTrue(self.config_fixture.conf.cache.tls_enabled)

            ssl.create_default_context.assert_called_with(cafile=None)
            fake_context.load_cert_chain.assert_not_called()
            fake_context.set_ciphers.assert_not_called()

            self.assertEqual(
                fake_context,
                config_dict['test_prefix.arguments.tls_context'],
            )

    def test_cache_config_builder_tls_enabled_redis(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   tls_enabled=True,
                                   tls_cafile='path_to_ca_file',
                                   tls_keyfile='path_to_key_file',
                                   tls_certfile='path_to_cert_file')

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(self.config_fixture.conf.cache.tls_enabled)
        self.assertIn('test_prefix.arguments.connection_kwargs',
                      config_dict)
        self.assertEqual(
            'rediss://localhost:6379/0',
            config_dict['test_prefix.arguments.url'])
        self.assertEqual(
            {
                'ssl_ca_certs': 'path_to_ca_file',
                'ssl_keyfile': 'path_to_key_file',
                'ssl_certfile': 'path_to_cert_file'
            },
            config_dict['test_prefix.arguments.connection_kwargs'])
        self.assertNotIn('test_prefix.arguments.sentinel_kwargs', config_dict)

    def test_cache_config_builder_tls_enabled_redis_sentinel(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis_sentinel',
                                   tls_enabled=True,
                                   tls_cafile='path_to_ca_file',
                                   tls_keyfile='path_to_key_file',
                                   tls_certfile='path_to_cert_file')

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(self.config_fixture.conf.cache.tls_enabled)
        self.assertIn('test_prefix.arguments.connection_kwargs',
                      config_dict)
        self.assertEqual(
            {
                'ssl': True,
                'ssl_ca_certs': 'path_to_ca_file',
                'ssl_keyfile': 'path_to_key_file',
                'ssl_certfile': 'path_to_cert_file'
            },
            config_dict['test_prefix.arguments.connection_kwargs'])
        self.assertIn('test_prefix.arguments.sentinel_kwargs',
                      config_dict)
        self.assertEqual(
            {
                'ssl': True,
                'ssl_ca_certs': 'path_to_ca_file',
                'ssl_keyfile': 'path_to_key_file',
                'ssl_certfile': 'path_to_cert_file'
            },
            config_dict['test_prefix.arguments.sentinel_kwargs'])

    @mock.patch('oslo_cache.core._LOG')
    def test_cache_config_builder_fips_mode_supported(self, log):
        """Validate the FIPS mode is supported."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   tls_enabled=True,
                                   enforce_fips_mode=True)

        # Ensure that we emulate FIPS_mode even if it doesn't exist
        with mock.patch.object(ssl, 'FIPS_mode',
                               create=True, return_value=True):
            # Ensure that we are able to set FIPS_mode
            with mock.patch.object(ssl, 'FIPS_mode_set', create=True):

                cache._build_cache_config(self.config_fixture.conf)
                log.info.assert_called_once_with(
                    "Enforcing the use of the OpenSSL FIPS mode")

    @mock.patch('oslo_cache.core._LOG')
    def test_cache_config_builder_fips_mode_unsupported(self, log):
        """Validate the FIPS mode is not supported."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   tls_enabled=True,
                                   enforce_fips_mode=True)

        with mock.patch.object(cache, 'ssl') as ssl_:
            del ssl_.FIPS_mode

            # We do this test only if FIPS mode is not supported to
            # ensure that we hard fail.
            self.assertRaises(exception.ConfigurationError,
                              cache._build_cache_config,
                              self.config_fixture.conf)

    def test_cache_config_builder_fips_mode_unsupported_redis(self):
        """Validate the FIPS mode is not supported."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   tls_enabled=True,
                                   enforce_fips_mode=True)

        self.assertRaises(exception.ConfigurationError,
                          cache._build_cache_config,
                          self.config_fixture.conf)

    def test_cache_config_builder_tls_enabled_unsupported(self):
        """Validate the tls_enabled opiton is not supported.."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict',
                                   tls_enabled=True)

        with mock.patch.object(ssl, 'create_default_context'):
            self.assertRaises(exception.ConfigurationError,
                              cache._build_cache_config,
                              self.config_fixture.conf)
            ssl.create_default_context.assert_not_called()

    def test_cache_config_builder_tls_enabled_with_config(self):
        """Validate the backend is reset to default if caching is disabled."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   tls_enabled=True,
                                   tls_cafile='path_to_ca_file',
                                   tls_keyfile='path_to_key_file',
                                   tls_certfile='path_to_cert_file',
                                   tls_allowed_ciphers='allowed_ciphers')

        fake_context = mock.Mock()
        with mock.patch.object(ssl, 'create_default_context',
                               return_value=fake_context):
            config_dict = cache._build_cache_config(self.config_fixture.conf)

            self.assertTrue(self.config_fixture.conf.cache.tls_enabled)

            ssl.create_default_context.assert_called_with(
                cafile='path_to_ca_file',
            )
            fake_context.load_cert_chain.assert_called_with(
                'path_to_cert_file',
                'path_to_key_file',
            )
            fake_context.set_ciphers.assert_called_with(
                'allowed_ciphers'
            )

            self.assertEqual(
                fake_context,
                config_dict['test_prefix.arguments.tls_context'],
            )

    def test_cache_pymemcache_socket_kalive_enabled_with_wrong_backend(self):
        """Validate we build a config without the retry option when retry
        is disabled.
        """
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict',
                                   enable_socket_keepalive=True)

        self.assertRaises(
            exception.ConfigurationError,
            cache._build_cache_config,
            self.config_fixture.conf
        )

    def test_cache_pymemcache_socket_keepalive_disabled(self):
        """Validate we build a dogpile.cache dict config without keepalive."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   socket_keepalive_idle=2,
                                   socket_keepalive_interval=2,
                                   socket_keepalive_count=2)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(
            self.config_fixture.conf.cache.enable_socket_keepalive)
        self.assertNotIn(
            'test_prefix.arguments.socket_keepalive', config_dict)

    def test_cache_pymemcache_socket_keepalive_enabled(self):
        """Validate we build a dogpile.cache dict config with keepalive."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   enable_socket_keepalive=True)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(
            self.config_fixture.conf.cache.enable_socket_keepalive)

        self.assertIsInstance(
            config_dict['test_prefix.arguments.socket_keepalive'],
            KeepaliveOpts
        )

    def test_cache_pymemcache_socket_keepalive_with_config(self):
        """Validate we build a socket keepalive with the right config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   enable_socket_keepalive=True,
                                   socket_keepalive_idle=12,
                                   socket_keepalive_interval=38,
                                   socket_keepalive_count=42)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(
            self.config_fixture.conf.cache.enable_socket_keepalive)

        self.assertTrue(
            config_dict['test_prefix.arguments.socket_keepalive'],
            KeepaliveOpts
        )
        self.assertEqual(
            12,
            config_dict['test_prefix.arguments.socket_keepalive'].idle
        )
        self.assertEqual(
            38,
            config_dict['test_prefix.arguments.socket_keepalive'].intvl
        )
        self.assertEqual(
            42,
            config_dict['test_prefix.arguments.socket_keepalive'].cnt
        )

    def test_cache_pymemcache_retry_enabled_with_wrong_backend(self):
        """Validate we build a config without the retry option when retry
        is disabled.
        """
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict',
                                   enable_retry_client=True,
                                   retry_attempts=2,
                                   retry_delay=2)

        self.assertRaises(
            exception.ConfigurationError,
            cache._build_cache_config,
            self.config_fixture.conf
        )

    def test_cache_pymemcache_retry_disabled(self):
        """Validate we build a config without the retry option when retry
        is disabled.
        """
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   retry_attempts=2,
                                   retry_delay=2)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        opts = ['enable_retry_client', 'retry_attempts', 'retry_delay']

        for el in opts:
            self.assertNotIn('test_prefix.arguments.{}'.format(el),
                             config_dict)

    def test_cache_pymemcache_retry_enabled(self):
        """Validate we build a dogpile.cache dict config with retry."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   enable_retry_client=True)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        opts = ['enable_retry_client', 'retry_attempts', 'retry_delay']

        for el in opts:
            self.assertIn('test_prefix.arguments.{}'.format(el), config_dict)

    def test_cache_pymemcache_retry_with_opts(self):
        """Validate we build a valid config for the retry client."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   enable_retry_client=True,
                                   retry_attempts=42,
                                   retry_delay=42)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(
            self.config_fixture.conf.cache.enable_retry_client)

        self.assertEqual(
            config_dict['test_prefix.arguments.retry_attempts'],
            42
        )

        self.assertEqual(
            config_dict['test_prefix.arguments.retry_delay'],
            42
        )

    def test_cache_pymemcache_retry_with_extra_opts(self):
        """Validate we build a valid config for the retry client."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.pymemcache',
                                   enable_retry_client=True,
                                   retry_attempts=42,
                                   retry_delay=42,
                                   hashclient_retry_attempts=100,
                                   hashclient_retry_delay=100,
                                   dead_timeout=100)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(
            self.config_fixture.conf.cache.enable_retry_client)

        self.assertEqual(
            config_dict['test_prefix.arguments.retry_attempts'],
            42
        )

        self.assertEqual(
            config_dict['test_prefix.arguments.retry_delay'],
            42
        )

        self.assertEqual(
            config_dict['test_prefix.arguments.hashclient_retry_attempts'],
            100
        )

        self.assertEqual(
            config_dict['test_prefix.arguments.hashclient_retry_delay'],
            100
        )

        self.assertEqual(
            config_dict['test_prefix.arguments.dead_timeout'],
            100
        )

    def test_cache_config_builder_flush_on_reconnect_enabled(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict',
                                   memcache_pool_flush_on_reconnect=True)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertTrue(self.config_fixture.conf.cache.
                        memcache_pool_flush_on_reconnect)
        self.assertTrue(config_dict['test_prefix.arguments'
                                    '.pool_flush_on_reconnect'])

    def test_cache_config_builder_flush_on_reconnect_disabled(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='oslo_cache.dict',
                                   memcache_pool_flush_on_reconnect=False)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(self.config_fixture.conf.cache.
                         memcache_pool_flush_on_reconnect)
        self.assertFalse(config_dict['test_prefix.arguments'
                                     '.pool_flush_on_reconnect'])

    def test_cache_config_builder_redis(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379')

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://[::1]:6379/0',
            config_dict['test_prefix.arguments.url'])
        self.assertEqual(
            1.0, config_dict['test_prefix.arguments.socket_timeout'])

    def test_cache_config_builder_redis_with_db(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379',
                                   redis_db=1)

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://[::1]:6379/1',
            config_dict['test_prefix.arguments.url'])
        self.assertEqual(
            1.0, config_dict['test_prefix.arguments.socket_timeout'])

    def test_cache_config_builder_redis_with_sock_to(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379',
                                   redis_socket_timeout=10.0)

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://[::1]:6379/0',
            config_dict['test_prefix.arguments.url'])
        self.assertEqual(
            10.0, config_dict['test_prefix.arguments.socket_timeout'])

    def test_cache_config_builder_redis_with_keepalive(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379',
                                   enable_socket_keepalive=True)

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://[::1]:6379/0',
            config_dict['test_prefix.arguments.url'])
        self.assertEqual(
            1.0, config_dict['test_prefix.arguments.socket_timeout'])
        self.assertEqual({
            'socket_keepalive': True,
            'socket_keepalive_options': {
                socket.TCP_KEEPIDLE: 1,
                socket.TCP_KEEPINTVL: 1,
                socket.TCP_KEEPCNT: 1,
            }}, config_dict['test_prefix.arguments.connection_kwargs'])

    def test_cache_config_builder_redis_with_keepalive_params(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379',
                                   enable_socket_keepalive=True,
                                   socket_keepalive_idle=2,
                                   socket_keepalive_interval=3,
                                   socket_keepalive_count=4)

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://[::1]:6379/0',
            config_dict['test_prefix.arguments.url'])
        self.assertEqual(
            1.0, config_dict['test_prefix.arguments.socket_timeout'])
        self.assertEqual({
            'socket_keepalive': True,
            'socket_keepalive_options': {
                socket.TCP_KEEPIDLE: 2,
                socket.TCP_KEEPINTVL: 3,
                socket.TCP_KEEPCNT: 4,
            }}, config_dict['test_prefix.arguments.connection_kwargs'])

    def test_cache_config_builder_redis_with_auth(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379',
                                   redis_password='secrete')

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://:secrete@[::1]:6379/0',
            config_dict['test_prefix.arguments.url'])

    def test_cache_config_builder_redis_with_auth_and_user(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   redis_server='[::1]:6379',
                                   redis_username='user',
                                   redis_password='secrete')

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            'redis://user:secrete@[::1]:6379/0',
            config_dict['test_prefix.arguments.url'])

    def test_cache_config_builder_redis_sentinel(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis_sentinel')

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
        self.assertEqual(
            0, config_dict['test_prefix.arguments.db'])
        self.assertEqual(
            'mymaster', config_dict['test_prefix.arguments.service_name'])
        self.assertEqual([
            ('localhost', 26379)
        ], config_dict['test_prefix.arguments.sentinels'])
        self.assertEqual(
            1.0, config_dict['test_prefix.arguments.socket_timeout'])
        self.assertNotIn('test_prefix.arguments.connection_kwargs',
                         config_dict)
        self.assertNotIn('test_prefix.arguments.sentinel_kwargs',
                         config_dict)

    def test_cache_config_builder_redis_sentinel_with_db(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis_sentinel',
                                   redis_db=1)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
        self.assertEqual(
            1, config_dict['test_prefix.arguments.db'])
        self.assertEqual(
            'mymaster', config_dict['test_prefix.arguments.service_name'])
        self.assertEqual([
            ('localhost', 26379)
        ], config_dict['test_prefix.arguments.sentinels'])
        self.assertEqual(
            1.0, config_dict['test_prefix.arguments.socket_timeout'])
        self.assertNotIn('test_prefix.arguments.connection_kwargs',
                         config_dict)
        self.assertNotIn('test_prefix.arguments.sentinel_kwargs',
                         config_dict)

    def test_cache_config_builder_redis_sentinel_with_sock_to(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis_sentinel',
                                   redis_socket_timeout=10.0)

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
        self.assertEqual(
            0, config_dict['test_prefix.arguments.db'])
        self.assertEqual(
            'mymaster', config_dict['test_prefix.arguments.service_name'])
        self.assertEqual([
            ('localhost', 26379)
        ], config_dict['test_prefix.arguments.sentinels'])
        self.assertEqual(
            10.0, config_dict['test_prefix.arguments.socket_timeout'])
        self.assertNotIn('test_prefix.arguments.connection_kwargs',
                         config_dict)
        self.assertNotIn('test_prefix.arguments.sentinel_kwargs',
                         config_dict)

    def test_cache_config_builder_redis_sentinel_with_auth(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   enabled=True,
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis_sentinel',
                                   redis_username='user',
                                   redis_password='secrete',
                                   redis_db=1,
                                   redis_sentinels=[
                                       '127.0.0.1:26379',
                                       '[::1]:26379',
                                       'localhost:26379'
                                   ],
                                   redis_sentinel_service_name='cluster')

        config_dict = cache._build_cache_config(self.config_fixture.conf)

        self.assertFalse(self.config_fixture.conf.cache.tls_enabled)
        self.assertEqual(
            1, config_dict['test_prefix.arguments.db'])
        self.assertEqual(
            'cluster', config_dict['test_prefix.arguments.service_name'])
        self.assertEqual([
            ('127.0.0.1', 26379),
            ('::1', 26379),
            ('localhost', 26379),
        ], config_dict['test_prefix.arguments.sentinels'])
        self.assertEqual(
            'user', config_dict['test_prefix.arguments.username'])
        self.assertEqual(
            'secrete', config_dict['test_prefix.arguments.password'])

    def test_cache_config_builder_with_backend_expiration(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.memcached',
                                   backend_expiration_time=600)

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            600, config_dict['test_prefix.expiration_time'])
        self.assertEqual(
            600, config_dict['test_prefix.arguments.memcached_expire_time'])

    def test_cache_config_builder_with_redis_backend_expiration(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.redis',
                                   backend_expiration_time=600)

        config_dict = cache._build_cache_config(self.config_fixture.conf)
        self.assertEqual(
            600, config_dict['test_prefix.expiration_time'])
        self.assertEqual(
            600, config_dict['test_prefix.arguments.redis_expiration_time'])

    def test_cache_config_builder_with_backend_expiration_too_small(self):
        """Validate we build a sane dogpile.cache dictionary config."""
        self.config_fixture.config(group='cache',
                                   config_prefix='test_prefix',
                                   backend='dogpile.cache.memcached',
                                   backend_expiration_time=599)

        self.assertRaises(exception.ConfigurationError,
                          cache._build_cache_config, self.config_fixture.conf)

    def test_cache_debug_proxy(self):
        single_value = 'Test Value'
        single_key = 'testkey'
        multi_values = {'key1': 1, 'key2': 2, 'key3': 3}

        self.region.set(single_key, single_value)
        self.assertEqual(single_value, self.region.get(single_key))

        self.region.delete(single_key)
        self.assertEqual(NO_VALUE, self.region.get(single_key))

        self.region.set_multi(multi_values)
        cached_values = self.region.get_multi(multi_values.keys())
        for value in multi_values.values():
            self.assertIn(value, cached_values)
        self.assertEqual(len(multi_values.values()), len(cached_values))

        self.region.delete_multi(multi_values.keys())
        for value in self.region.get_multi(multi_values.keys()):
            self.assertEqual(NO_VALUE, value)

    def test_configure_non_region_object_raises_error(self):
        self.assertRaises(exception.ConfigurationError,
                          cache.configure_cache_region,
                          self.config_fixture.conf,
                          "bogus")

    def test_kwarg_function_key_generator_no_kwargs(self):
        cacheable_function = self._get_cacheable_function(
            region=self.region_kwargs)

        self.config_fixture.config(group='cache', enabled=True)
        cacheable_function(self.test_value)
        cached_value = cacheable_function(self.test_value)
        self.assertTrue(cached_value.cached)

    def test_kwarg_function_key_generator_with_kwargs(self):
        cacheable_function = self._get_cacheable_function(
            region=self.region_kwargs)

        self.config_fixture.config(group='cache', enabled=True)
        cacheable_function(value=self.test_value)
        cached_value = cacheable_function(value=self.test_value)
        self.assertTrue(cached_value.cached)


class UTF8KeyManglerTests(test_cache.BaseTestCase):

    def test_key_is_utf8_encoded(self):
        key = 'fäké1'
        encoded = cache._sha1_mangle_key(key)
        self.assertIsNotNone(encoded)

    def test_key_is_bytestring(self):
        key = b'\xcf\x84o\xcf\x81\xce\xbdo\xcf\x82'
        encoded = cache._sha1_mangle_key(key)
        self.assertIsNotNone(encoded)

    def test_key_is_string(self):
        key = 'fake'
        encoded = cache._sha1_mangle_key(key)
        self.assertIsNotNone(encoded)
