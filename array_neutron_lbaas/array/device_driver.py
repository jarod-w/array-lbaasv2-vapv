# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from oslo_log import log as logging

from array_neutron_lbaas.array.apv_driver import ArrayAPVAPIDriver

LOG = logging.getLogger(__name__)


class ArrayADCDriver(object):
    """ The implementation on host to push config to
        APV/AVX instance via RESTful API
    """
    def __init__(self):
        pass

    def create_loadbalancer(self, lb, vapv, network_config):
        """
        Used to allocate the VIP to loadbalancer
        """
        LOG.debug("Create a loadbalancer on Array ADC device(%s)", lb)
        argu = {}

        if 'data_netmask' not in network_config.keys():
            LOG.error("Exit because data_netmask is none")
            return

        if 'pri_data_ip' in network_config.keys():
            argu['vip_address'] = network_config['pri_data_ip']
            argu['netmask'] = network_config['data_netmask']
            management_ip = [vapv['pri_mgmt_address'],]
            driver = ArrayAPVAPIDriver(management_ip)
            driver.create_loadbalancer(argu)
            driver.configure_cluster(vapv['cluster_id'], 100)
            driver.write_memory(argu)

        if 'sec_data_ip' in network_config.keys():
            argu['vip_address'] = network_config['pri_data_ip']
            argu['netmask'] = network_config['data_netmask']
            management_ip = [vapv['sec_mgmt_address'],]
            driver = ArrayAPVAPIDriver(management_ip)
            driver.create_loadbalancer(argu)
            driver.configure_cluster(vapv['cluster_id'], 99)
            driver.write_memory(argu)


    def update_loadbalancer(self, obj, old_obj):
        # see: https://wiki.openstack.org/wiki/Neutron/LBaaS/API_2.0#Update_a_Load_Balancer
        LOG.debug("Nothing to do at LB updating")


    def delete_loadbalancer(self, vapv):
        LOG.debug("Delete a loadbalancer on Array ADC device")
        argu = {}

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.delete_loadbalancer(argu)
        driver.write_memory(argu)


    def get_stats(self, instance):
        pass


    def create_listener(self, lb, listener, vapv):
        argu = {}

        argu['connection_limit'] = listener.connection_limit
        argu['protocol'] = listener.protocol
        argu['protocol_port'] = listener.protocol_port
        argu['listener_id'] = listener.id
        argu['vip_id'] = listener.loadbalancer_id
        argu['vip_address'] = lb.vip_address

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.create_listener(argu)
        driver.write_memory(argu)


    def update_listener(self, lb, listener, old, vapv):
        # see: https://wiki.openstack.org/wiki/Neutron/LBaaS/API_2.0#Update_a_Listener
        # handle the change of "connection_limit" only
        if listener.connection_limit != old.connection_limit:
            # firstly delete this listener, it will cause policy is deleted as well
            self.delete_listener(lb, listener)

            # re-create listener and policy
            self.create_listener(lb, listener)


    def delete_listener(self, listener, vapv):
        argu = {}

        argu['listener_id'] = listener.id
        argu['protocol'] = listener.protocol
        argu['vip_id'] = listener.loadbalancer_id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.delete_listener(argu)
        driver.write_memory(argu)


    def create_pool(self, pool, vapv):
        argu = {}

        sp_type = None
        ck_name = None
        listener = pool.listener
        if pool.session_persistence:
            sp_type = pool.session_persistence.type
            ck_name = pool.session_persistence.cookie_name
        argu['pool_id'] = pool.id
        argu['listener_id'] = listener.id
        argu['session_persistence_type'] = sp_type
        argu['cookie_name'] = ck_name
        argu['lb_algorithm'] = pool.lb_algorithm
        argu['vip_id'] = listener.loadbalancer_id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.create_pool(argu)
        driver.write_memory(argu)


    def update_pool(self, obj, old_obj, vapv):
        # see: https://wiki.openstack.org/wiki/Neutron/LBaaS/API_2.0#Update_a_Pool
        need_recreate = False
        if ((obj.lb_algorithm != old_obj.lb_algorithm) or
            (obj.session_persistence != old_obj.session_persistence)):
            need_recreate = True

        if need_recreate:
            LOG.debug("Need to recreate the pool....")

            # firstly delete old group
            self.delete_pool(old_obj, vapv)

            # re-create group
            self.create_pool(obj, vapv)

            # re-create members
            for member in obj.members:
                self.create_member(member, vapv)

            # re-create healthmonitor
            if obj.healthmonitor:
                # FIXME: should directly update the hm
                self.update_health_monitor(obj.healthmonitor, old_obj.healthmonitor, vapv)

    def delete_pool(self, pool, vapv):
        argu = {}

        sp_type = None
        ck_name = None
        if pool.session_persistence:
            sp_type = pool.session_persistence.type
            ck_name = pool.session_persistence.cookie_name

        argu['pool_id'] = pool.id
        argu['listener_id'] = pool.listener.id
        argu['session_persistence_type'] = sp_type
        argu['cookie_name'] = ck_name
        argu['lb_algorithm'] = pool.lb_algorithm
        argu['vip_id'] = pool.listener.loadbalancer_id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.delete_pool(argu)
        driver.write_memory(argu)

    def create_member(self, member, vapv):
        argu = {}

        pool = member.pool
        lb = pool.root_loadbalancer
        argu['member_id'] = member.id
        argu['member_address'] = member.address
        argu['member_port'] = member.protocol_port
        argu['member_weight'] = member.weight
        argu['protocol'] = pool.protocol
        argu['pool_id'] = pool.id
        argu['vip_id'] = lb.id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.create_member(argu)
        driver.write_memory(argu)

    def update_member(self, member, old, vapv):
        # see: https://wiki.openstack.org/wiki/Neutron/LBaaS/API_2.0#Update_a_Member_of_a_Pool
        if member.weight != old.weight:
            self.delete_member(old, vapv)
            self.create_member(member, vapv)

    def delete_member(self, member, vapv):
        argu = {}

        pool = member.pool
        lb = pool.root_loadbalancer
        argu['member_id'] = member.id
        argu['protocol'] = pool.protocol
        argu['vip_id'] = lb.id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.delete_member(argu)
        driver.write_memory(argu)

    def create_health_monitor(self, hm, vapv):
        argu = {}

        pool = hm.pool
        lb = hm.root_loadbalancer
        argu['hm_id'] = hm.id
        argu['hm_type'] = hm.type
        argu['hm_delay'] = hm.delay
        argu['hm_max_retries'] = hm.max_retries
        argu['hm_timeout'] = hm.timeout
        argu['hm_http_method'] = hm.http_method
        argu['hm_url'] = hm.url_path
        argu['hm_expected_codes'] = hm.expected_codes
        argu['pool_id'] = pool.id
        argu['vip_id'] = lb.id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.create_health_monitor(argu)
        driver.write_memory(argu)

    def update_health_monitor(self, hm, old, vapv):

        need_recreate = False
        hm_dict = hm.to_dict()
        old_dict = old.to_dict()
        for changed in ('delay', 'timeout', 'max_retries', 'http_method', 'url_path', 'expected_codes'):
            if hm_dict[changed] != old_dict[changed]:
                need_recreate = True

        if need_recreate:
            self.delete_health_monitor(old, vapv)
            self.create_health_monitor(hm, vapv)


    def delete_health_monitor(self, hm, vapv):
        argu = {}

        pool = hm.pool
        lb = hm.root_loadbalancer
        argu['hm_id'] = hm.id
        argu['pool_id'] = pool.id
        argu['vip_id'] = lb.id

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.delete_health_monitor(argu)
        driver.write_memory(argu)

