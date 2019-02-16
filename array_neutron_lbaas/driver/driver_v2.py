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
#
#

from array_neutron_lbaas.device_driver import device_driver
from neutron_lbaas.drivers import driver_base
import threading
import logging
import traceback

LOG = logging.getLogger(__name__)

class ArrayLoadBalancerDriver(driver_base.LoadBalancerBaseDriver):

    def __init__(self, plugin):
        super(ArrayLoadBalancerDriver, self).__init__(plugin)
        self.load_balancer = ArrayLoadBalancerManager(self)
        self.listener = ArrayListenerManager(self)
        self.pool = ArrayPoolManager(self)
        self.member = ArrayMemberManager(self)
        self.health_monitor = ArrayHealthMonitorManager(self)
        self.device_driver = device_driver.ArrayDeviceDriverV2(plugin)


class ArrayLoadBalancerManager(driver_base.BaseLoadBalancerManager):
    def create(self, context, obj):
        thread = threading.Thread(target=self._create, args=(context, obj))
        thread.start()

    def _create(self, context, obj):
        try:
            self.driver.device_driver.create_loadbalancer(context, obj)
            self.successful_completion(context, obj)
        except Exception as e:
            LOG.debug("trace is below: %s", traceback.format_exc())
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_loadbalancer(context, obj, old_obj)
            self.successful_completion(context, obj)
        except Exception as e:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_loadbalancer(context, obj)
        except Exception:
            pass
        self.successful_completion(context, obj, delete=True)

    def refresh(self, context, lb_obj):
        self.driver.device_driver.refresh(context, lb_obj)

    def stats(self, context, lb_obj):
        return self.driver.device_driver.stats(context, lb_obj)


class ArrayListenerManager(driver_base.BaseListenerManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_listener(context, obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_listener(context, obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_listener(context, obj)
        except Exception:
            pass
        self.successful_completion(context, obj, delete=True)


class ArrayPoolManager(driver_base.BasePoolManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_pool(context, obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_pool(context, obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_pool(context, obj)
        except Exception:
            pass
        self.successful_completion(context, obj, delete=True)


class ArrayMemberManager(driver_base.BaseMemberManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_member(context, obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_member(context, obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_member(context, obj)
        except Exception:
            pass
        self.successful_completion(context, obj, delete=True)

    def get(self, context, obj):
        try:
            status = self.driver.device_driver.get_member_health(context, obj)
        except Exception:
            status = "UNKNOWN"
        return status


class ArrayHealthMonitorManager(driver_base.BaseHealthMonitorManager):
    def create(self, context, obj):
        try:
            self.driver.device_driver.create_healthmonitor(context, obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def update(self, context, old_obj, obj):
        try:
            self.driver.device_driver.update_healthmonitor(context, obj, old_obj)
            self.successful_completion(context, obj)
        except Exception:
            self.failed_completion(context, obj)

    def delete(self, context, obj):
        try:
            self.driver.device_driver.delete_healthmonitor(context, obj)
        except Exception:
            pass
        self.successful_completion(context, obj, delete=True)

