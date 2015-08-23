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

from dogpile.cache import region as dp_region

from oslo_cache import core
from oslo_cache.tests import test_cache
from oslo_config import fixture as config_fixture
from oslo_utils import fixture as time_fixture


NO_VALUE = core.NO_VALUE
KEY = 'test_key'
VALUE = 'test_value'


class CacheDictBackendTest(test_cache.BaseTestCase):

    def setUp(self):
        super(CacheDictBackendTest, self).setUp()
        self.config_fixture = self.useFixture(config_fixture.Config())
        self.config_fixture.config(group='cache', backend='oslo_cache.dict')
        self.time_fixture = self.useFixture(time_fixture.TimeFixture())
        self.region = dp_region.make_region()
        self.region.configure(
            'oslo_cache.dict', arguments={'expiration_time': 0.5})

    def test_dict_backend(self):
        self.assertIs(NO_VALUE, self.region.get(KEY))

        self.region.set(KEY, VALUE)
        self.assertEqual(VALUE, self.region.get(KEY))

        self.region.delete(KEY)
        self.assertIs(NO_VALUE, self.region.get(KEY))

    def test_dict_backend_expiration_time(self):
        self.region.set(KEY, VALUE)
        self.assertEqual(VALUE, self.region.get(KEY))

        self.time_fixture.advance_time_seconds(1)
        self.assertIs(NO_VALUE, self.region.get(KEY))

    def test_dict_backend_clear_cache(self):
        self.region.set(KEY, VALUE)

        self.time_fixture.advance_time_seconds(1)

        self.assertEqual(1, len(self.region.backend.cache))
        self.region.backend._clear()
        self.assertEqual(0, len(self.region.backend.cache))

    def test_dict_backend_zero_expiration_time(self):
        self.region = dp_region.make_region()
        self.region.configure(
            'oslo_cache.dict', arguments={'expiration_time': 0})

        self.region.set(KEY, VALUE)
        self.time_fixture.advance_time_seconds(1)

        self.assertEqual(VALUE, self.region.get(KEY))
        self.assertEqual(1, len(self.region.backend.cache))

        self.region.backend._clear()

        self.assertEqual(VALUE, self.region.get(KEY))
        self.assertEqual(1, len(self.region.backend.cache))

    def test_dict_backend_multi_keys(self):
        self.region.set('key1', 'value1')
        self.region.set('key2', 'value2')
        self.time_fixture.advance_time_seconds(1)
        self.region.set('key3', 'value3')

        self.assertEqual(1, len(self.region.backend.cache))
        self.assertIs(NO_VALUE, self.region.get('key1'))
        self.assertIs(NO_VALUE, self.region.get('key2'))
        self.assertEqual('value3', self.region.get('key3'))

    def test_dict_backend_multi_keys_in_one_call(self):
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

    def test_dict_backend_rewrite_value(self):
        self.region.set(KEY, 'value1')
        self.region.set(KEY, 'value2')
        self.assertEqual('value2', self.region.get(KEY))
