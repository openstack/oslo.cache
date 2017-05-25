# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
from oslo_utils import uuidutils
import urllib3

from oslo_cache import core
from oslo_cache.tests import test_cache


NO_VALUE = core.NO_VALUE


class Etcd3gwCache(test_cache.BaseTestCase):
    arguments = {
        'host': '127.0.0.1',
        'port': 2379,
    }

    def setUp(self):
        test_cache.BaseTestCase.setUp(self)
        try:
            urllib3.PoolManager().request(
                'GET',
                '%s:%d' % (self.arguments['host'], self.arguments['port'])
            )
            return True
        except urllib3.exceptions.HTTPError:
            self.skipTest("skipping this test")

    def test_typical_configuration(self):

        dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )
        self.assertTrue(True)  # reached here means no initialization error

    def test_backend_get_missing_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )

        random_key = uuidutils.generate_uuid(dashed=False)
        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, region.get(random_key))

    def test_backend_set_data(self):
        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )

        random_key = uuidutils.generate_uuid(dashed=False)
        region.set(random_key, "dummyValue")
        self.assertEqual("dummyValue", region.get(random_key))

    def test_backend_set_none_as_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )

        random_key = uuidutils.generate_uuid(dashed=False)
        region.set(random_key, None)
        self.assertIsNone(region.get(random_key))

    def test_backend_set_blank_as_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )

        random_key = uuidutils.generate_uuid(dashed=False)
        region.set(random_key, "")
        self.assertEqual("", region.get(random_key))

    def test_backend_set_same_key_multiple_times(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )

        random_key = uuidutils.generate_uuid(dashed=False)
        region.set(random_key, "dummyValue")
        self.assertEqual("dummyValue", region.get(random_key))

        dict_value = {'key1': 'value1'}
        region.set(random_key, dict_value)
        self.assertEqual(dict_value, region.get(random_key))

        region.set(random_key, "dummyValue2")
        self.assertEqual("dummyValue2", region.get(random_key))

    def test_backend_multi_set_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )
        random_key = uuidutils.generate_uuid(dashed=False)
        random_key1 = uuidutils.generate_uuid(dashed=False)
        random_key2 = uuidutils.generate_uuid(dashed=False)
        random_key3 = uuidutils.generate_uuid(dashed=False)
        mapping = {random_key1: 'dummyValue1',
                   random_key2: 'dummyValue2',
                   random_key3: 'dummyValue3'}
        region.set_multi(mapping)
        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, region.get(random_key))
        self.assertFalse(region.get(random_key))
        self.assertEqual("dummyValue1", region.get(random_key1))
        self.assertEqual("dummyValue2", region.get(random_key2))
        self.assertEqual("dummyValue3", region.get(random_key3))

    def test_backend_multi_get_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )
        random_key = uuidutils.generate_uuid(dashed=False)
        random_key1 = uuidutils.generate_uuid(dashed=False)
        random_key2 = uuidutils.generate_uuid(dashed=False)
        random_key3 = uuidutils.generate_uuid(dashed=False)
        mapping = {random_key1: 'dummyValue1',
                   random_key2: '',
                   random_key3: 'dummyValue3'}
        region.set_multi(mapping)

        keys = [random_key, random_key1, random_key2, random_key3]
        results = region.get_multi(keys)
        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, results[0])
        self.assertEqual("dummyValue1", results[1])
        self.assertEqual("", results[2])
        self.assertEqual("dummyValue3", results[3])

    def test_backend_multi_set_should_update_existing(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )
        random_key = uuidutils.generate_uuid(dashed=False)
        random_key1 = uuidutils.generate_uuid(dashed=False)
        random_key2 = uuidutils.generate_uuid(dashed=False)
        random_key3 = uuidutils.generate_uuid(dashed=False)
        mapping = {random_key1: 'dummyValue1',
                   random_key2: 'dummyValue2',
                   random_key3: 'dummyValue3'}
        region.set_multi(mapping)
        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, region.get(random_key))
        self.assertEqual("dummyValue1", region.get(random_key1))
        self.assertEqual("dummyValue2", region.get(random_key2))
        self.assertEqual("dummyValue3", region.get(random_key3))

        mapping = {random_key1: 'dummyValue4',
                   random_key2: 'dummyValue5'}
        region.set_multi(mapping)
        self.assertEqual(NO_VALUE, region.get(random_key))
        self.assertEqual("dummyValue4", region.get(random_key1))
        self.assertEqual("dummyValue5", region.get(random_key2))
        self.assertEqual("dummyValue3", region.get(random_key3))

    def test_backend_multi_set_get_with_blanks_none(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )
        random_key = uuidutils.generate_uuid(dashed=False)
        random_key1 = uuidutils.generate_uuid(dashed=False)
        random_key2 = uuidutils.generate_uuid(dashed=False)
        random_key3 = uuidutils.generate_uuid(dashed=False)
        random_key4 = uuidutils.generate_uuid(dashed=False)
        mapping = {random_key1: 'dummyValue1',
                   random_key2: None,
                   random_key3: '',
                   random_key4: 'dummyValue4'}
        region.set_multi(mapping)
        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, region.get(random_key))
        self.assertEqual("dummyValue1", region.get(random_key1))
        self.assertIsNone(region.get(random_key2))
        self.assertEqual("", region.get(random_key3))
        self.assertEqual("dummyValue4", region.get(random_key4))

        keys = [random_key, random_key1, random_key2, random_key3, random_key4]
        results = region.get_multi(keys)

        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, results[0])
        self.assertEqual("dummyValue1", results[1])
        self.assertIsNone(results[2])
        self.assertEqual("", results[3])
        self.assertEqual("dummyValue4", results[4])

        mapping = {random_key1: 'dummyValue5',
                   random_key2: 'dummyValue6'}
        region.set_multi(mapping)
        self.assertEqual(NO_VALUE, region.get(random_key))
        self.assertEqual("dummyValue5", region.get(random_key1))
        self.assertEqual("dummyValue6", region.get(random_key2))
        self.assertEqual("", region.get(random_key3))

    def test_backend_delete_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )

        random_key = uuidutils.generate_uuid(dashed=False)
        region.set(random_key, "dummyValue")
        self.assertEqual("dummyValue", region.get(random_key))

        region.delete(random_key)
        # should return NO_VALUE as key no longer exists in cache
        self.assertEqual(NO_VALUE, region.get(random_key))

    def test_backend_multi_delete_data(self):

        region = dp_region.make_region().configure(
            'oslo_cache.etcd3gw',
            arguments=self.arguments
        )
        random_key = uuidutils.generate_uuid(dashed=False)
        random_key1 = uuidutils.generate_uuid(dashed=False)
        random_key2 = uuidutils.generate_uuid(dashed=False)
        random_key3 = uuidutils.generate_uuid(dashed=False)
        mapping = {random_key1: 'dummyValue1',
                   random_key2: 'dummyValue2',
                   random_key3: 'dummyValue3'}
        region.set_multi(mapping)
        # should return NO_VALUE as key does not exist in cache
        self.assertEqual(NO_VALUE, region.get(random_key))
        self.assertEqual("dummyValue1", region.get(random_key1))
        self.assertEqual("dummyValue2", region.get(random_key2))
        self.assertEqual("dummyValue3", region.get(random_key3))
        self.assertEqual(NO_VALUE, region.get("InvalidKey"))

        keys = mapping.keys()

        region.delete_multi(keys)

        self.assertEqual(NO_VALUE, region.get("InvalidKey"))
        # should return NO_VALUE as keys no longer exist in cache
        self.assertEqual(NO_VALUE, region.get(random_key1))
        self.assertEqual(NO_VALUE, region.get(random_key2))
        self.assertEqual(NO_VALUE, region.get(random_key3))
