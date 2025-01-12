#    Copyright 2020 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from oslo_cache.tests.functional import test_base


ETCD_PORT = os.getenv("OSLO_CACHE_TEST_ETCD_PORT", "2379")


class TestEtcdCacheBackend(test_base.BaseTestCaseCacheBackend):
    def setUp(self):
        self.config_fixture.config(
            group='cache',
            backend='oslo_cache.etcd3gw',
            backend_argument=['host:127.0.0.1', f'port:{ETCD_PORT}']
        )

        # NOTE(hberaud): super must be called after all to ensure that
        # config fixture is properly initialized with value related to
        # the current backend in use.
        super().setUp()
