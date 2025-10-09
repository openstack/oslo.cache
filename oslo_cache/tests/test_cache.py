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

from oslo_config import fixture as config_fixture
from oslotest import base


class BaseTestCase(base.BaseTestCase):
    def setUp(self):
        super().setUp()
        self.config_fixture = self.useFixture(config_fixture.Config())
        self.config_fixture.config(
            # TODO(morganfainberg): Make Cache Testing a separate test case
            # in tempest, and move it out of the base unit tests.
            group='cache',
            backend='dogpile.cache.memory',
            enabled=True,
            proxies=['oslo_cache.testing.CacheIsolatingProxy'],
        )
