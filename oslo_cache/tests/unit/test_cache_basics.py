# -*- coding: utf-8 -*-
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
import time
from unittest import mock

from dogpile.cache import proxy
from oslo_config import cfg
from oslo_utils import uuidutils

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


class TestProxyValue(object):
    def __init__(self, value):
        self.value = value
        self.cached = False


class CacheRegionTest(test_cache.BaseTestCase):

    def setUp(self):
        super(CacheRegionTest, self).setUp()
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

        class _test_obj(object):
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

    def test_cache_dictionary_config_builder(self):
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

    def test_cache_dictionary_config_builder_global_disabled(self):
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
        key = u'fäké1'
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
