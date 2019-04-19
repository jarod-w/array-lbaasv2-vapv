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
import json
import requests
import time
import six

from oslo_log import log as logging
from neutron_lbaas.services.loadbalancer import constants as lb_const

from array_neutron_lbaas.array import exceptions as driver_except
from array_neutron_lbaas.array.adc_device import ADCDevice

LOG = logging.getLogger(__name__)

VAPV_TRIFFIC_INTERFACE="port2"
VAPV_REST_USERNAME="restapi"
VAPV_REST_PASSWORD="click1"


def get_vlinks_by_policy(policy_id):
    return [policy_id + "_v" + str(idx) for idx in range(1, 3)]

class ArrayAPVAPIDriver(object):
    """ The real implementation on host to push config to
        APV instance via RESTful API
    """
    def __init__(self, management_ips):
        self.base_rest_urls = ["https://" + host + ":9997/rest/apv" for host in management_ips if host is not None]

    def get_auth(self):
        return (VAPV_REST_USERNAME, VAPV_REST_PASSWORD)


    def create_loadbalancer(self, argu):
        """ create a loadbalancer """
        if not argu:
            LOG.error("In create_loadbalancer, it should not pass the None.")
            return

        # create vip
        self._create_vip(argu['vip_address'], argu['netmask'])


    def delete_loadbalancer(self, argu):
        """ Delete a loadbalancer """
        if not argu:
            LOG.error("In delete_loadbalancer, it should not pass the None.")
            return

        # delete vip
        self._delete_vip()
        self.clear_cluster(argu['cluster_id'], argu['vip_address'])

    def create_listener(self, argu):
        """ create a listener """
        if not argu:
            LOG.error("In create_listener, it should not pass the None.")
            return

        # create vs
        self._create_vs(argu['listener_id'],
                        argu['vip_address'],
                        argu['protocol'],
                        argu['protocol_port'],
                        argu['connection_limit']
                       )

        if argu['pool_id']:
            self._create_policy(argu['pool_id'],
                                argu['listener_id'],
                                argu['session_persistence_type'],
                                argu['lb_algorithm'],
                                argu['cookie_name']
                               )


    def delete_listener(self, argu):
        """ Delete VIP in lb_delete_vip """

        if not argu:
            LOG.error("In delete_listener, it should not pass the None.")
            return

        # delete vs
        self._delete_vs(argu['listener_id'], argu['protocol'])

        if argu['pool_id']:
            self._delete_policy(
                               argu['listener_id'],
                               argu['session_persistence_type'],
                               argu['lb_algorithm']
                               )


    def _create_vip(self, vip_address, netmask):
        """ create vip"""

        interface_name = VAPV_TRIFFIC_INTERFACE
        # configure vip
        LOG.debug("Configure the vip address into interface")
        cmd_apv_config_ip = ADCDevice.configure_ip(interface_name, vip_address, netmask)
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_config_ip)


    def _delete_vip(self):
        interface_name = VAPV_TRIFFIC_INTERFACE

        LOG.debug("no the vip address into interface")
        cmd_apv_no_ip = ADCDevice.no_ip(interface_name)
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_no_ip)


    def _create_vs(self,
                   listener_id,
                   vip_address,
                   protocol,
                   protocol_port,
                   connection_limit):

        cmd_apv_create_vs = ADCDevice.create_virtual_service(
                                                             listener_id,
                                                             vip_address,
                                                             protocol_port,
                                                             protocol,
                                                             connection_limit
                                                            )
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_create_vs)


    def _delete_vs(self, listener_id, protocol):
        cmd_apv_no_vs = ADCDevice.no_virtual_service(
                                                     listener_id,
                                                     protocol
                                                    )
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_no_vs)


    def _create_policy(self,
                       pool_id,
                       listener_id,
                       session_persistence_type,
                       lb_algorithm,
                       cookie_name):
        """ Create SLB policy """

        cmd_apv_create_policy = ADCDevice.create_policy(
                                                        listener_id,
                                                        pool_id,
                                                        lb_algorithm,
                                                        session_persistence_type,
                                                        cookie_name
                                                       )

        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_create_policy)


    def _delete_policy(self, listener_id, session_persistence_type, lb_algorithm):
        """ Delete SLB policy """
        cmd_apv_no_policy = ADCDevice.no_policy(
                                                listener_id,
                                                lb_algorithm,
                                                session_persistence_type
                                               )
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_no_policy)


    def create_pool(self, argu):
        """ Create SLB group in lb-pool-create"""

        if not argu:
            LOG.error("In create_pool, it should not pass the None.")
            return

        cmd_apv_create_group = ADCDevice.create_group(argu['pool_id'],
                                                      argu['lb_algorithm'],
                                                      argu['session_persistence_type']
                                                     )
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_create_group)

        # create policy
        if argu['listener_id']:
            self._create_policy(argu['pool_id'],
                                argu['listener_id'],
                                argu['session_persistence_type'],
                                argu['lb_algorithm'],
                                argu['cookie_name']
                               )


    def delete_pool(self, argu):
        """Delete SLB group in lb-pool-delete"""

        if not argu:
            LOG.error("In delete_pool, it should not pass the None.")
            return

        # delete policy
        if argu['listener_id']:
            self._delete_policy(
                               argu['listener_id'],
                               argu['session_persistence_type'],
                               argu['lb_algorithm']
                               )

        cmd_apv_no_group = ADCDevice.no_group(argu['pool_id'])
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_no_group)


    def create_member(self, argu):
        """ create a member"""

        if not argu:
            LOG.error("In create_member, it should not pass the None.")
            return

        cmd_apv_create_real_server = ADCDevice.create_real_server(
                                                       argu['member_id'],
                                                       argu['member_address'],
                                                       argu['member_port'],
                                                       argu['protocol']
                                                       )

        cmd_apv_add_rs_into_group = ADCDevice.add_rs_into_group(
                                                               argu['pool_id'],
                                                               argu['member_id'],
                                                               argu['member_weight']
                                                               )
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_create_real_server)
            self.run_cli_extend(base_rest_url, cmd_apv_add_rs_into_group)


    def delete_member(self, argu):
        """ Delete a member"""

        if not argu:
            LOG.error("In delete_member, it should not pass the None.")
            return

        cmd_apv_no_rs = ADCDevice.no_real_server(argu['protocol'], argu['member_id'])

        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_no_rs)


    def create_health_monitor(self, argu):

        if not argu:
            LOG.error("In create_health_monitor, it should not pass the None.")
            return

        cmd_apv_create_hm = ADCDevice.create_health_monitor(
                                                           argu['hm_id'],
                                                           argu['hm_type'],
                                                           argu['hm_delay'],
                                                           argu['hm_max_retries'],
                                                           argu['hm_timeout'],
                                                           argu['hm_http_method'],
                                                           argu['hm_url'],
                                                           argu['hm_expected_codes']
                                                           )

        cmd_apv_attach_hm = ADCDevice.attach_hm_to_group(argu['pool_id'], argu['hm_id'])
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_create_hm)
            self.run_cli_extend(base_rest_url, cmd_apv_attach_hm)


    def delete_health_monitor(self, argu):

        if not argu:
            LOG.error("In delete_health_monitor, it should not pass the None.")
            return

        cmd_apv_detach_hm = ADCDevice.detach_hm_to_group(argu['pool_id'], argu['hm_id'])

        cmd_apv_no_hm = ADCDevice.no_health_monitor(argu['hm_id'])
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_detach_hm)
            self.run_cli_extend(base_rest_url, cmd_apv_no_hm)


    def create_l7_policy(self, argu, updated=False):
        if not argu:
            LOG.error("In create_l7_policy, it should not pass the None.")
            return

        cmd_create_group = None
        cmd_http_load_error_page = None
        cmd_redirect_to_url = None
        if argu['pool_id']:
            self._create_policy(argu['pool_id'],
                                argu['listener_id'],
                                argu['session_persistence_type'],
                                argu['lb_algorithm'],
                                argu['cookie_name']
                               )

        if argu['action'] == lb_const.L7_POLICY_ACTION_REJECT:
            # create the group using the policy_id
            cmd_create_group = ADCDevice.create_group(
                                                      argu['id'],
                                                      lb_const.LB_METHOD_ROUND_ROBIN,
                                                      None
                                                     )
            cmd_http_load_error_page = ADCDevice.load_http_error_page()
        elif argu['action'] == lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL:
            cmd_redirect_to_url = ADCDevice.redirect_to_url(argu['listener_id'],
                                                            argu['id'],
                                                            argu['redirect_url'])

        if not updated:
            vlinks = get_vlinks_by_policy(argu['id'])
            for vlink in vlinks:
                cmd_create_vlink = ADCDevice.create_vlink(vlink)
                for base_rest_url in self.base_rest_urls:
                    self.run_cli_extend(base_rest_url, cmd_create_vlink)

        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_create_group)
            self.run_cli_extend(base_rest_url, cmd_http_load_error_page)
            self.run_cli_extend(base_rest_url, cmd_redirect_to_url)


    def delete_l7_policy(self, argu, updated=False):
        if not argu:
            LOG.error("In delete_l7_policy, it should not pass the None.")
            return

        if argu['pool_id']:
            self._delete_policy(
                               argu['listener_id'],
                               argu['session_persistence_type'],
                               argu['lb_algorithm']
                               )

        cmd_no_group = None
        cmd_no_redirect_to_url = None
        if argu['action'] == lb_const.L7_POLICY_ACTION_REJECT:
            cmd_no_group = ADCDevice.no_group(argu['id'])
        elif argu['action'] == lb_const.L7_POLICY_ACTION_REDIRECT_TO_URL:
            cmd_no_redirect_to_url = ADCDevice.no_redirect_to_url(argu["listener_id"], argu['id'])

        if not updated:
            vlinks = get_vlinks_by_policy(argu['id'])
            for vlink in vlinks:
                cmd_no_vlink = ADCDevice.no_vlink(vlink)
                for base_rest_url in self.base_rest_urls:
                    self.run_cli_extend(base_rest_url, cmd_no_vlink)

        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_no_group)
            self.run_cli_extend(base_rest_url, cmd_no_redirect_to_url)


    def create_l7_rule(self, argu):
        if not argu:
            LOG.error("In create_l7_rule, it should not pass the None.")
            return

        cmd_create_rule = ADCDevice.create_l7_rule(argu['rule_id'],
                                                   argu['vs_id'],
                                                   argu['group_id'],
                                                   argu['rule_type'],
                                                   argu['compare_type'],
                                                   argu['rule_value'],
                                                   argu['rule_key'])
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_create_rule)

    def delete_l7_rule(self, argu):
        if not argu:
            LOG.error("In delete_l7_rule, it should not pass the None.")
            return

        cmd_no_rule = ADCDevice.no_l7_rule(argu['rule_id'], argu['rule_type'])
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_no_rule)

    def configure_cluster(self, cluster_id, priority, vip_address):
        # configure a virtual interface
        cmd_config_virtual_interface = ADCDevice.cluster_config_virtual_interface(cluster_id)
        # configure virtual vip
        cmd_config_virtual_vip = ADCDevice.cluster_config_vip(cluster_id, vip_address)
        # configure virtual priority
        cmd_config_virtual_priority = ADCDevice.cluster_config_priority(cluster_id, priority)
        # enable cluster
        cmd_enable_cluster = ADCDevice.cluster_enable(cluster_id)
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_config_virtual_interface)
            self.run_cli_extend(base_rest_url, cmd_config_virtual_vip)
            self.run_cli_extend(base_rest_url, cmd_config_virtual_priority)
            self.run_cli_extend(base_rest_url, cmd_enable_cluster)


    def clear_cluster(self, cluster_id, vip_address):
        cmd_no_config_virtual_vip = ADCDevice.no_cluster_config_vip(cluster_id, vip_address)
        cmd_no_config_virtual_priority = ADCDevice.no_cluster_config_priority(cluster_id)
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_no_config_virtual_vip)
            self.run_cli_extend(base_rest_url, cmd_no_config_virtual_priority)


    def configure_ssl(self, vhost_name, vs_name, key_content, cert_content,
            domain_name):
        cmd_create_vhost = ADCDevice.create_ssl_vhost(vhost_name, vs_name)
        cmd_import_ssl_key = ADCDevice.import_ssl_key(vhost_name, key_content, domain_name)
        cmd_import_ssl_cert = ADCDevice.import_ssl_cert(vhost_name, cert_content, domain_name)
        cmd_activate_cert = ADCDevice.activate_certificate(vhost_name, domain_name)
        cmd_start_vhost = ADCDevice.start_vhost(vhost_name)
        cmd_associate_domain_to_vhost = None
        if domain_name:
            cmd_associate_domain_to_vhost = ADCDevice.associate_domain_to_vhost(vhost_name, domain_name)
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_create_vhost)
            self.run_cli_extend(base_rest_url, cmd_import_ssl_key)
            self.run_cli_extend(base_rest_url, cmd_import_ssl_cert)
            if cmd_associate_domain_to_vhost:
                self.run_cli_extend(base_rest_url, cmd_associate_domain_to_vhost)
            self.run_cli_extend(base_rest_url, cmd_activate_cert)
            self.run_cli_extend(base_rest_url, cmd_start_vhost)

    def clear_ssl(self, vhost_name, vs_name, domain_name):
        cmd_stop_vhost = ADCDevice.stop_vhost(vhost_name)
        cmd_deactivate_certificate = ADCDevice.deactivate_certificate(vhost_name, domain_name)
        if domain_name:
            cmd_disassociate_domain_to_vhost = ADCDevice.disassociate_domain_to_vhost(vhost_name)
        cmd_no_ssl_cert = ADCDevice.no_ssl_cert(vhost_name)
        cmd_no_ssl_vhost = ADCDevice.no_ssl_vhost(vhost_name, vs_name)
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_stop_vhost)
            self.run_cli_extend(base_rest_url, cmd_deactivate_certificate)
            if domain_name:
                self.run_cli_extend(base_rest_url, cmd_disassociate_domain_to_vhost)
            self.run_cli_extend(base_rest_url, cmd_no_ssl_cert)
            self.run_cli_extend(base_rest_url, cmd_no_ssl_vhost)


    def write_memory(self, argu=None):
        cmd_apv_write_memory = ADCDevice.write_memory()
        for base_rest_url in self.base_rest_urls:
            self.run_cli_extend(base_rest_url, cmd_apv_write_memory)


    def run_cli_extend(self, base_rest_url, cmd):
        if not cmd:
            return
        url = base_rest_url + '/cli_extend'
        payload = {
            "cmd": cmd
        }
        LOG.debug("Run the URL: --%s--", url)
        LOG.debug("Run the CLI: --%s--", cmd)
        conn_max_retries = 60
        conn_retry_interval = 10
        for a in six.moves.xrange(conn_max_retries):
            try:
                r = requests.post(url,
                                  json.dumps(payload),
                                  auth=self.get_auth(),
                                  timeout=(5, 5),
                                  verify=False)
                LOG.debug("status_code: %d", r.status_code)
                if r.status_code == 200:
                    return r
                else:
                    time.sleep(conn_retry_interval)
            except (requests.ConnectionError, requests.Timeout) as e:
                exception = e
                LOG.warning("Could not connect to instance. Retrying.")
                time.sleep(conn_retry_interval)

        LOG.error("Connection retries (currently set to %(max_retries)s) "
                  "exhausted.  The vapv is unavailable. Reason: "
                  "%(exception)s",
                  {'max_retries': conn_max_retries,
                   'exception': exception})

        raise driver_except.TimeOutException()

