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
from array_neutron_lbaas.array.apv_driver import get_vlinks_by_policy

LOG = logging.getLogger(__name__)


class ArrayADCDriver(object):
    """ The implementation on host to push config to
        APV/AVX instance via RESTful API
    """
    def __init__(self):
        pass

    def create_loadbalancer(self, lb, vapv, network_config, only_cluster = False):
        """
        Used to allocate the VIP to loadbalancer
        """
        LOG.debug("Create a loadbalancer on Array ADC device(%s)", lb)
        argu = {}

        if 'data_netmask' not in network_config.keys() and not only_cluster:
            LOG.error("Exit because data_netmask is none")
            return

        if 'pri_data_ip' in network_config.keys():
            argu['vip_address'] = network_config['pri_data_ip']
            argu['netmask'] = network_config['data_netmask']
            management_ip = [vapv['pri_mgmt_address'],]
            driver = ArrayAPVAPIDriver(management_ip)
            if not only_cluster:
                driver.create_loadbalancer(argu)
            driver.configure_cluster(vapv['cluster_id'], 100, lb.vip_address)
            driver.write_memory(argu)

        if 'sec_data_ip' in network_config.keys():
            argu['vip_address'] = network_config['sec_data_ip']
            argu['netmask'] = network_config['data_netmask']
            management_ip = [vapv['sec_mgmt_address'],]
            driver = ArrayAPVAPIDriver(management_ip)
            if not only_cluster:
                driver.create_loadbalancer(argu)
            driver.configure_cluster(vapv['cluster_id'], 99, lb.vip_address)
            driver.write_memory(argu)


    def update_loadbalancer(self, obj, old_obj):
        # see: https://wiki.openstack.org/wiki/Neutron/LBaaS/API_2.0#Update_a_Load_Balancer
        LOG.debug("Nothing to do at LB updating")


    def delete_loadbalancer(self, lb, vapv):
        LOG.debug("Delete a loadbalancer on Array ADC device")
        argu = {}

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        argu['vip_address'] = lb.vip_address
        argu['cluster_id'] = vapv['cluster_id']
        driver = ArrayAPVAPIDriver(management_ip)
        driver.clear_cluster(argu['cluster_id'], argu['vip_address'])
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

        pool = listener.default_pool
        if pool:
            sp_type = None
            ck_name = None
            argu['pool_id'] = pool.id
            if pool.session_persistence:
                sp_type = pool.session_persistence.type
                ck_name = pool.session_persistence.cookie_name
            argu['lb_algorithm'] = pool.lb_algorithm
            argu['session_persistence_type'] = sp_type
            argu['cookie_name'] = ck_name
        else:
            argu['pool_id'] = None

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.create_listener(argu)
        driver.write_memory(argu)

    def upload_cert(self, vapv, listener, vhost_id, key, cert, domain_name):
        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.configure_ssl(vhost_id, listener.id, key, cert, domain_name)
        driver.write_memory()


    def clear_cert(self, vapv, listener, vhost_id, domain_name):
        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.clear_ssl(vhost_id, listener.id, domain_name)
        driver.write_memory()

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

        pool = listener.default_pool
        if pool:
            sp_type = None
            argu['pool_id'] = pool.id
            if pool.session_persistence:
                sp_type = pool.session_persistence.type
            argu['lb_algorithm'] = pool.lb_algorithm
            argu['session_persistence_type'] = sp_type
        else:
            argu['pool_id'] = None

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
        if listener:
            argu['listener_id'] = listener.id
        else:
            argu['listener_id'] = None
        argu['pool_id'] = pool.id
        argu['session_persistence_type'] = sp_type
        argu['cookie_name'] = ck_name
        argu['lb_algorithm'] = pool.lb_algorithm
        argu['vip_id'] = pool.root_loadbalancer.id

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

        if pool.listener:
            argu['listener_id'] = pool.listener.id
        else:
            argu['listener_id'] = None
        argu['pool_id'] = pool.id
        argu['session_persistence_type'] = sp_type
        argu['cookie_name'] = ck_name
        argu['lb_algorithm'] = pool.lb_algorithm
        argu['vip_id'] = pool.root_loadbalancer.id

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


    def create_l7_policy(self, policy, vapv, updated=False):
        argu = {}

        argu['action'] = policy.action
        argu['id'] = policy.id
        argu['listener_id'] = policy.listener_id
        argu['pool_id'] = policy.redirect_pool_id
        argu['position'] = policy.position
        argu['redirect_url'] = policy.redirect_url

        sp_type = None
        ck_name = None
        pool = policy.redirect_pool
        if pool:
            if pool.session_persistence:
                sp_type = pool.session_persistence.type
                ck_name = pool.session_persistence.cookie_name
            argu['session_persistence_type'] = sp_type
            argu['cookie_name'] = ck_name
            argu['lb_algorithm'] = pool.lb_algorithm

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.create_l7_policy(argu, updated=updated)
        if not updated:
            driver.write_memory(argu)


    def update_l7_policy(self, policy, old, vapv):
        need_recreate = False
        policy_dict = policy.to_dict()
        old_dict = old.to_dict()
        for changed in ('action', 'redirect_pool_id', 'redirect_url'):
            if policy_dict[changed] != old_dict[changed]:
                need_recreate = True

        if not need_recreate:
            LOG.debug("It doesn't need do any thing(update_l7_policy)")
            return

        argu = {}
        self.delete_l7_policy(old, vapv, updated=True)
        self.create_l7_policy(policy, vapv, updated=True)

        self.create_all_rules(policy, vapv)
        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.write_memory(argu)

    def delete_l7_policy(self, policy, vapv, updated=False):
        argu = {}
        argu['action'] = policy.action
        argu['id'] = policy.id
        argu['listener_id'] = policy.listener_id
        argu['pool_id'] = policy.redirect_pool_id

        sp_type = None
        pool = policy.redirect_pool
        if pool:
            pool = policy.redirect_pool
            if pool.session_persistence:
                sp_type = pool.session_persistence.type
            argu['session_persistence_type'] = sp_type
            argu['lb_algorithm'] = pool.lb_algorithm

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)

        LOG.debug("Delete all rules from policy in delete_l7_policy")
        self.delete_all_rules(policy, vapv)

        driver.delete_l7_policy(argu, updated=updated)
        if not updated:
            driver.write_memory(argu)


    def create_l7_rule(self, rule, vapv):
        argu = {}
        policy = rule.policy

        LOG.debug("Delete all rules from policy in create_l7_rule")
        self.delete_all_rules(policy, vapv)
        LOG.debug("Create all rules from policy in create_l7_rule")
        self.create_all_rules(policy, vapv)

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.write_memory(argu)


    def update_l7_rule(self, rule, old, vapv):
        need_recreate = False
        policy_changed = False
        rule_dict = rule.to_dict()
        old_dict = old.to_dict()
        for changed in ('type', 'compare_type', 'l7policy_id', 'key', 'value'):
            if rule_dict[changed] != old_dict[changed]:
                need_recreate = True

        if not need_recreate:
            LOG.debug("It doesn't need do any thing(update_l7_rule)")
            return

        if rule_dict['l7policy_id'] != old_dict['l7policy_id']:
            policy_changed = True

        argu = {}
        old_policy = old.policy
        policy = rule.policy
        if policy_changed:
            LOG.debug("Delete all rules from old policy in update_l7_rule")
            self.delete_all_rules(old_policy, vapv)
            LOG.debug("Delete all rules from new policy in update_l7_rule")
            self.delete_all_rules(policy, vapv)

            LOG.debug("Create all rules from old policy in update_l7_rule")
            self.create_all_rules(policy, vapv, filt=rule.id)
            LOG.debug("Create all rules from new policy in update_l7_rule")
            self.create_all_rules(policy, vapv)
        else:
            LOG.debug("Delete all rules from old policy in update_l7_rule")
            self.delete_all_rules(old_policy, vapv)
            LOG.debug("Create all rules from new policy in update_l7_rule")
            self.create_all_rules(policy, vapv)

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.write_memory(argu)

    def delete_l7_rule(self, rule, vapv):
        argu = {}
        policy = rule.policy

        LOG.debug("Delete all rules from policy in delete_l7_rule")
        self.delete_all_rules(policy, vapv)
        LOG.debug("Create all rules from policy in delete_l7_rule")
        self.create_all_rules(policy, vapv, filt=rule.id)

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)
        driver.write_memory(argu)

    def delete_all_rules(self, policy, vapv):
        argu = {}
        rules = policy.rules

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)

        for rule in rules:
            argu['rule_type'] = rule.type
            argu['rule_id'] = rule.id
            driver.delete_l7_rule(argu)

    def create_all_rules(self, policy, vapv, filt = None):
        argu = {}
        rules = policy.rules

        idx = 0
        cnt = len(rules)
        if filt:
            for rule in rules:
                if rule.id == filt:
                    break
                idx += 1
            if cnt > idx:
                del rules[idx]
                cnt -= 1

        management_ip = [vapv['pri_mgmt_address'], vapv['sec_mgmt_address'],]
        driver = ArrayAPVAPIDriver(management_ip)

        argu['vs_id'] = policy.listener_id
        if policy.redirect_pool:
            argu['group_id'] = policy.redirect_pool.id
        else:
            argu['group_id'] = policy.listener.default_pool_id

        if cnt == 0:
            LOG.debug("No any rule needs to be created.")
        elif cnt == 1:
            rule = rules[0]
            argu['rule_type'] = rule.type
            argu['compare_type'] = rule.compare_type
            argu['rule_id'] = rule.id
            argu['rule_value'] = rule.value
            argu['rule_key'] = rule.key
            driver.create_l7_rule(argu)
        elif cnt == 2 or cnt == 3:
            vlinks = get_vlinks_by_policy(policy.id)
            for rule_idx in range(cnt):
                rule = rules[rule_idx]

                argu['rule_type'] = rule.type
                argu['compare_type'] = rule.compare_type
                argu['rule_id'] = rule.id
                argu['rule_value'] = rule.value
                argu['rule_key'] = rule.key
                if rule_idx == 0:
                    argu['group_id'] = vlinks[0]
                elif rule_idx == (cnt - 1):
                    if policy.redirect_pool:
                        argu['group_id'] = policy.redirect_pool.id
                    else:
                        argu['group_id'] = policy.listener.default_pool_id
                    if cnt == 2:
                        argu['vs_id'] = vlinks[0];
                    else:
                        argu['vs_id'] = vlinks[1];
                else:
                    argu['group_id'] = vlinks[1]
                    argu['vs_id'] = vlinks[0];
                driver.create_l7_rule(argu)
        else:
            LOG.debug("It doesn't support to create more than three rule in one policy.")


