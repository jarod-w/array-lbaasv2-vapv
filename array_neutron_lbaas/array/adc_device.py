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

from array_neutron_lbaas.array.adc_map import service_group_lb_method
from array_neutron_lbaas.array.adc_map import array_protocol_map

class ADCDevice(object):
    """
        This class is used to generate the command line of Array ADC
        Product by different action.
    """

    @staticmethod
    def vlan_device(interface, vlan_device_name, vlan_tag):
        cmd = "vlan %s %s %s" % (interface, vlan_device_name, vlan_tag)
        return cmd

    @staticmethod
    def no_vlan_device(vlan_device_name):
        cmd = "no vlan %s" % vlan_device_name
        return cmd

    @staticmethod
    def configure_ip(interface, ip_address, netmask):
        cmd = "ip address %s %s %s" % (interface, ip_address, netmask)
        return cmd

    @staticmethod
    def configure_route(gateway_ip):
        cmd = "ip route default %s" % (gateway_ip)
        return cmd

    @staticmethod
    def clear_route():
        cmd = "clear ip route"
        return cmd

    @staticmethod
    def no_ip(interface):
        cmd = "no ip address %s" % interface
        return cmd

    @staticmethod
    def create_virtual_service(name, vip, port, proto, conn_limit):
        protocol = array_protocol_map(proto)
        max_conn = conn_limit
        if max_conn == -1:
            max_conn = 0

        cmd = "slb virtual %s %s %s %s arp %s" % (protocol, name, vip, port,
                max_conn)
        return cmd

    @staticmethod
    def no_virtual_service(name, proto):
        protocol = array_protocol_map(proto)
        cmd = "no slb virtual %s %s" % (protocol, name)
        return cmd

    @staticmethod
    def create_ssl_vhost(vhost_name, vs_name):
        cmd = "ssl host virtual %s %s" % (vhost_name, vs_name)
        return cmd

    @staticmethod
    def no_ssl_vhost(vhost_name, vs_name):
        cmd = "no ssl host virtual %s %s" % (vhost_name, vs_name)
        return cmd

    @staticmethod
    def import_ssl_key(vhost_name, key_content, domain_name=None):
        if domain_name:
            cmd = 'ssl import key %s %s\nYES\n%s\n...\n' % (vhost_name, domain_name, key_content)
        else:
            cmd = 'ssl import key %s\nYES\n%s\n...\n' % (vhost_name, key_content)
        return cmd

    @staticmethod
    def import_ssl_cert(vhost_name, cert_content, domain_name=None):
        if domain_name:
            cmd = 'ssl import certificate %s 1 %s\nYES\n%s\n...\n' % (vhost_name, domain_name, cert_content)
        else:
            cmd = 'ssl import certificate %s\nYES\n%s\n...\n' % (vhost_name, cert_content)
        return cmd

    @staticmethod
    def no_ssl_cert(vhost_name, domain_name=None):
        if domain_name:
            cmd = "no ssl certificate %s 1 %s" % (vhost_name, domain_name)
        else:
            cmd = "no ssl certificate %s 1 ''" % (vhost_name)
        return cmd

    @staticmethod
    def activate_certificate(vhost_name, domain_name=None):
        if domain_name:
            cmd = "ssl activate certificate %s 1 %s" % (vhost_name, domain_name)
        else:
            cmd = "ssl activate certificate %s" % (vhost_name)
        return cmd

    @staticmethod
    def deactivate_certificate(vhost_name, domain_name=None):
        if domain_name:
            cmd = "ssl deactivate certificate %s %s all" % (vhost_name, domain_name)
        else:
            cmd = "ssl deactivate certificate %s '' all" % (vhost_name)
        return cmd

    @staticmethod
    def associate_domain_to_vhost(vhost_name, domain_name):
        cmd = 'ssl sni %s %s' % (vhost_name, domain_name)
        return cmd

    @staticmethod
    def disassociate_domain_to_vhost(vhost_name, domain_name):
        cmd = 'clear ssl sni %s %s' % (vhost_name, domain_name)
        return cmd

    @staticmethod
    def start_vhost(vhost_name):
        cmd = 'ssl start %s' % (vhost_name)
        return cmd

    @staticmethod
    def stop_vhost(vhost_name):
        cmd = 'ssl stop %s' % (vhost_name)
        return cmd

    @staticmethod
    def create_group(name, lb_algorithm, sp_type):
        (algorithm, first_choice_method, policy) = \
            service_group_lb_method(lb_algorithm, sp_type)
        cmd = None

        if first_choice_method:
            if algorithm == 'HC':
                cmd = "slb group method %s hc %s" % (name, first_choice_method)
            elif algorithm == 'PI':
                cmd = "slb group method %s pi 32 %s" % (name, first_choice_method)
            elif algorithm == 'IC':
                cmd = "slb group method %s ic array 0 %s" % (name, first_choice_method)
        else:
            if algorithm == 'IC':
                cmd = "slb group method %s ic array" % (name)
            else:
                cmd = "slb group method %s %s" % (name, algorithm.lower())
        return cmd

    @staticmethod
    def no_group(name):
        cmd = "no slb group method %s" % name
        return cmd

    @staticmethod
    def create_policy(vs_name,
                      group_name,
                      lb_algorithm,
                      session_persistence_type,
                      cookie_name
                      ):
        (algorithm, first_choice_method, policy) = \
            service_group_lb_method(lb_algorithm, session_persistence_type)

        cmd = None
        if policy == 'Default':
            cmd = "slb policy default %s %s" % (vs_name, group_name)
        elif policy == 'PC':
            cmd = "slb policy default %s %s; " % (vs_name, group_name)
            cmd += "slb policy persistent cookie %s %s %s %s 100" % \
                (vs_name, vs_name, group_name, cookie_name)
        elif policy == 'IC':
            cmd = "slb policy default %s %s; " % (vs_name, group_name)
            cmd += "slb policy icookie %s %s %s 100" % (vs_name, vs_name, group_name)
        return cmd

    @staticmethod
    def no_policy(vs_name, lb_algorithm, session_persistence_type):
        (_, _, policy) = service_group_lb_method(lb_algorithm, \
                session_persistence_type)
        if policy == 'Default':
            cmd = "no slb policy default %s" % vs_name
        elif policy == 'PC':
            cmd = "no slb policy persistent cookie %s" % vs_name
        elif policy == 'IC':
            cmd = "no slb policy default %s; " % vs_name
            cmd += "no slb policy icookie %s" % vs_name
        return cmd

    @staticmethod
    def create_real_server(member_name,
                           member_address,
                           member_port,
                           proto
                          ):
        protocol = array_protocol_map(proto)
        cmd = "slb real %s %s %s %s 65535 none" % (protocol, member_name,\
                member_address, member_port)
        return cmd

    @staticmethod
    def no_real_server(proto, member_name):
        protocol = array_protocol_map(proto)
        cmd = "no slb real %s %s" % (protocol, member_name)
        return cmd

    @staticmethod
    def add_rs_into_group(group_name,
                          member_name,
                          member_weight
                         ):
        cmd = "slb group member %s %s %s" % (group_name, member_name, member_weight)
        return cmd

    @staticmethod
    def delete_rs_from_group(group_name, member_name):
        cmd = "no slb group member %s %s" % (group_name, member_name)
        return cmd

    @staticmethod
    def create_health_monitor(hm_name,
                              hm_type,
                              hm_delay,
                              hm_max_retries,
                              hm_timeout,
                              hm_http_method,
                              hm_url,
                              hm_expected_codes
                             ):
        if hm_type == 'PING':
            hm_type = 'ICMP'
        cmd = None
        if hm_type == 'HTTP' or hm_type == 'HTTPS':
            cmd = "slb health %s %s %s %s 3 %s %s \"%s\" \"%s\"" % (hm_name, hm_type.lower(), \
                    str(hm_delay), str(hm_timeout), str(hm_max_retries), \
                    hm_http_method, hm_url, str(hm_expected_codes))
        else:
            cmd = "slb health %s %s %s %s 3 %s" % (hm_name, hm_type.lower(), \
                    str(hm_delay), str(hm_timeout), str(hm_max_retries))
        return cmd

    @staticmethod
    def no_health_monitor(hm_name):
        cmd = "no slb health %s" % hm_name
        return cmd

    @staticmethod
    def attach_hm_to_group(group_name, hm_name):
        cmd = "slb group health %s %s" % (group_name, hm_name)
        return cmd

    @staticmethod
    def detach_hm_to_group(group_name, hm_name):
        cmd = "no slb group health %s %s" % (group_name, hm_name)
        return cmd

    @staticmethod
    def cluster_config_virtual_interface(cluster_id):
        cmd = "cluster virtual ifname port2 %s" % cluster_id
        return cmd

    @staticmethod
    def cluster_clear_virtual_interface(cluster_id):
        cmd = "clear cluster virtual ifname port2 %d" % cluster_id
        return cmd

    @staticmethod
    def cluster_config_vip(cluster_id, vip_address):
        cmd = "cluster virtual vip port2 %d %s" % (cluster_id, vip_address)
        return cmd

    @staticmethod
    def no_cluster_config_vip(cluster_id, vip_address):
        cmd = "no cluster virtual vip port2 %d %s" % (cluster_id, vip_address)
        return cmd

    @staticmethod
    def cluster_config_priority(cluster_id, priority):
        cmd = "cluster virtual priority port2 %d %s" % (cluster_id, priority)
        return cmd

    @staticmethod
    def no_cluster_config_priority(cluster_id):
        cmd = "no cluster virtual priority port2 %d" % (cluster_id)
        return cmd

    @staticmethod
    def cluster_enable(cluster_id):
        cmd = "cluster virtual on %d port2" % (cluster_id)
        return cmd

    @staticmethod
    def cluster_disable(cluster_id):
        cmd = "cluster virtual off %d port2" % (cluster_id)
        return cmd

    @staticmethod
    def create_l7_policy(policy_id, rule_id):
        cmd = "write memory"
        return cmd


    @staticmethod
    def write_memory():
        cmd = "write memory"
        return cmd
