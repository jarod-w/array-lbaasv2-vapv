#!/usr/bin/env python
#
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

from array_neutron_lbaas_customizations_db import helper \
     as customization_helper
import json
from neutronclient.neutron import client as neutron_client
from oslo_config import cfg
from oslo_log import log as logging
import re
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import socket
from struct import pack
from time import sleep
import hashlib
import netaddr

LOG = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class ServerNotFoundError(BaseException):
    def __init__(self, hostname=None, server_id=None):
        self.hostname = hostname
        self.server_id = server_id


class OpenStackInterface(object):
    def __init__(self):
        self.admin_password = cfg.CONF.lbaas_settings.openstack_password
        self.admin_username = cfg.CONF.lbaas_settings.openstack_username
        self.admin_project_id = cfg.CONF.lbaas_settings.admin_project_id

        self.lbaas_password = cfg.CONF.lbaas_settings.lbaas_project_password
        self.lbaas_username = cfg.CONF.lbaas_settings.lbaas_project_username
        self.lbaas_project_id = cfg.CONF.lbaas_settings.lbaas_project_id

        # Get Neutron and Nova API endpoints...
        keystone = self.get_keystone_client(lbaas_project=False)
        neutron_service = keystone.services.find(name="neutron")
        nova_service = keystone.services.find(name="nova")

        if cfg.CONF.lbaas_settings.keystone_version == "2":
            self.neutron_endpoint = keystone.endpoints.find(
                service_id=neutron_service.id
            ).adminurl
            self.nova_endpoint = keystone.endpoints.find(
                service_id=nova_service.id
            ).adminurl
        else:
            self.neutron_endpoint = keystone.endpoints.find(
                interface="admin", service_id=neutron_service.id
            ).url
            nova_endpoint = keystone.endpoints.find(
                interface="admin", service_id=nova_service.id
            ).url
            self.nova_endpoint = nova_endpoint.replace(
                "%(tenant_id)s", self.lbaas_project_id
            )

        # Get connector to tenant customizations database if enabled...
        if cfg.CONF.lbaas_settings.allow_tenant_customizations is True:
            self.customizations_db = customization_helper.\
                ArrayLbaasTenantCustomizationsDatabaseHelper(
                    cfg.CONF.lbaas_settings.tenant_customizations_db
                )
        else:
            self.customizations_db = None

    def create_vapv(self, hostname, lb, ports, avoid=None):
        """
        Creates a vAPV instance as a Nova VM.
        """
        nics = [{"port": ports['data']['id']}]
        if ports['mgmt'] is not None:
            nics.insert(0, {"port": ports['mgmt']['id']})
        instance = self.create_server(
            tenant_id=lb.tenant_id,
            hostname=hostname,
            nics=nics,
            avoid_host_of=avoid
        )
        sleep(2)
        self._await_build_complete(instance['id'])
        return instance

    def destroy_vapv(self, hostname, lb):
        port_list = []
        sec_grp_list = []
        floatingip_list = []
        server_id = self.get_server_id_from_hostname(hostname)
        neutron = self.get_neutron_client()
        # Build lists of ports, floating IPs and security groups to delete
        ports = neutron.list_ports(device_id=server_id)
        for port in ports['ports']:
            port_list.append(port['id'])
            sec_grp_list += port['security_groups']
            floatingip_list += [
                floatingip['id']
                for floatingip in neutron.list_floatingips(
                    port_id=port['id']
                )['floatingips']
            ]
        # Delete the instance
        self.delete_server(server_id)
        # Wait for instance deletion to complete (else port deletion can fail)
        for _ in xrange(0, 60):
            try:
                self.get_server(server_id)
            except ServerNotFoundError:
                break
            sleep(1)
        # Delete floating IPs
        for flip in floatingip_list:
            try:
                neutron.delete_floatingip(flip)
            except Exception as e:
                LOG.error(
                    "\nError deleting floating IP {}: {}".format(flip, e)
                )
        # Delete ports
        for port in port_list:
            try:
                neutron.delete_port(port)
            except Exception as e:
                LOG.error("\nError deleting port {}: {}".format(port, e))
        # Delete security groups
        for sec_grp in sec_grp_list:
            try:
                neutron.delete_security_group(sec_grp)
            except Exception:
                # Might legitimately fail in HA deployments
                pass

    def clean_up(self, ports=None, security_groups=None, instances=None,
                 floating_ips=None):
        if instances is not None:
            for instance in instances:
                self.delete_server(instance)
        neutron = self.get_neutron_client()
        if floating_ips is not None:
            for flip in floating_ips:
                neutron.delete_floatingip(flip)
        if ports is not None:
            for port in ports:
                neutron.delete_port(port)
        if security_groups is not None:
            for sec_grp in security_groups:
                neutron.delete_security_group(sec_grp)

    def vapv_exists(self, hostname):
        """
        Tests whether a vAPV instance with the specified hosname exists.
        """
        hostname = hostname[0] if isinstance(hostname, tuple) else hostname
        try:
            self.get_server_id_from_hostname(hostname)
            return True
        except:
            return False

    def add_ip_to_ports(self, ip, ports):
        """
        Adds IP address to the allowed_address_pairs field of ports.
        """
        neutron = self.get_neutron_client()
        # Loop through all the ports, typically one per vAPV cluster member
        for port_id in ports:
            port = neutron.show_port(port_id)['port']
            port_ips = [
                addr['ip_address'] for addr in port['allowed_address_pairs']
            ]
            # Add the IP if it isn't already in allowed_address_pairs
            if ip not in port_ips:
                port_ips.append(ip)
                allowed_pairs = []
                for addr in port_ips:
                    allowed_pairs.append({"ip_address": addr})
                neutron.update_port(
                    port_id, {"port": {"allowed_address_pairs": allowed_pairs}}
                )

    def delete_ip_from_ports(self, ip, ports):
        """
        Deletes IP address from the allowed_address_pairs field of ports.
        """
        neutron = self.get_neutron_client()
        # Loop through all the ports, typically one per vAPV cluster member
        for port_id in ports:
            port = neutron.show_port(port_id)['port']
            port_ips = [
                addr['ip_address'] for addr in port['allowed_address_pairs']
            ]
            # Delete the IP if it is in allowed_address_pairs
            if ip in port_ips:
                new_pairs = []
                for port_ip in port_ips:
                    if ip != port_ip:
                        new_pairs.append({"ip_address": port_ip})
                neutron.update_port(
                    port_id, {"port": {"allowed_address_pairs": new_pairs}}
                )

    def _await_build_complete(self, instance_id):
        """
        Waits for a Nova instance to be built.
        """
        instance = self.get_server(instance_id)
        status = instance['status']
        while status == 'BUILD':
            sleep(10)
            instance = self.get_server(instance_id)
            status = instance['status']
            if status == 'ERROR':
                self.delete_server(instance_id)
                raise Exception("VM build failed")

    def create_port(self, lb, hostname, mgmt_port=False, cluster=False,
                    create_floating_ip=False, security_group=None,
                    identifier=None):
        if identifier is None and security_group is None:
            raise Exception("Must specify either security_group or identifier")
        # Gather parameters and create the port
        neutron = self.get_neutron_client()
        if mgmt_port is False:
            subnet = neutron.show_subnet(lb.vip_subnet_id)
            network_id = subnet['subnet']['network_id']
        else:
            network_id = cfg.CONF.lbaas_settings.management_network
        port_config = {"port": {
            "admin_state_up": True,
            "network_id": network_id,
            "tenant_id": self.lbaas_project_id,
            "name": "{}-{}".format("mgmt" if mgmt_port else "data", hostname)
        }}
        if mgmt_port is False:
            port_config['port']['fixed_ips'] = [
                {'subnet_id': lb.vip_subnet_id}
            ]
        port = neutron.create_port(port_config)['port']
        # Create or assign the appropriate security group to the port
        if create_floating_ip is True:
            floatingip = self.create_floatingip(port['id'])
            mgmt_ip = floatingip['floatingip']['floating_ip_address']
            if security_group is None:
                sec_grp = self.create_lb_security_group(
                    lb.tenant_id, identifier, mgmt_port=True, cluster=cluster
                )
                security_group = sec_grp['security_group']['id']
        else:
            if security_group is None:
                if mgmt_port is False:
                    sec_grp = self.create_lb_security_group(
                        lb.tenant_id, identifier, cluster=cluster
                    )
                else:
                    sec_grp = self.create_lb_security_group(
                        lb.tenant_id, identifier, mgmt_port=True,
                        mgmt_label=True
                    )
                security_group = sec_grp['security_group']['id']
            if mgmt_port is False:
                mgmt_ip = None
            else:
                mgmt_ip = port['fixed_ips'][0]['ip_address']
        neutron.update_port(
            port['id'], {"port": {"security_groups": [security_group]}}
        )
        return(port, security_group, mgmt_ip)

    def vapv_has_subnet_port(self, hostname, lb):
        hostname = hostname[0] if isinstance(hostname, tuple) else hostname
        ports = self.get_server_ports(hostname)
        for port in ports:
            for fixed_ip in port['fixed_ips']:
                if fixed_ip['subnet_id'] == lb.vip_subnet_id:
                    return True
        return False

    def subnet_in_use(self, lb):
        neutron = self.get_neutron_client()
        loadbalancers = neutron.list_loadbalancers(
            tenant_id=lb.tenant_id,
            vip_subnet_id=lb.vip_subnet_id
        )['loadbalancers']
        if len(loadbalancers) > 1:
            return True
        return False

    def attach_port(self, hostname, lb, identifier):
        server_id = self.get_server_id_from_hostname(hostname)
        sec_grp_id = self.get_security_group_id(
            "lbaas-{}".format(identifier)
        )
        port, junk, junk = self.create_port(
            lb, hostname, security_group=sec_grp_id
        )
        self.attach_port_to_instance(server_id, port['id'])
        return port

    def detach_port(self, hostname, lb):
        neutron = self.get_neutron_client()
        server_id = self.get_server_id_from_hostname(hostname)
        ports = neutron.list_ports(device_id=server_id,)['ports']
        for port in ports:
            if port['fixed_ips'][0]['subnet_id'] == lb.vip_subnet_id:
                self.detach_port_from_instance(server_id, port['id'])
                neutron.delete_port(port['id'])
                return port['fixed_ips'][0]['ip_address']
        raise Exception(
            "No port found for subnet {} on device {}".format(
                lb.vip_subnet_id, hostname)
        )

    def get_security_group_id(self, sec_grp_name):
        neutron = self.get_neutron_client()
        sec_grps = neutron.list_security_groups(name=sec_grp_name)
        try:
            return sec_grps['security_groups'][0]['id']
        except IndexError:
            raise Exception(
                "Security group {} not found".format(sec_grp_name)
            )

    def create_lb_security_group(self, tenant_id, uuid, mgmt_port=False,
                                 mgmt_label=False, cluster=False):
        """
        Creates a security group.
        """
        neutron = self.get_neutron_client()
        sec_grp_data = {"security_group": {
            "name": "{}lbaas-{}".format("mgmt-" if mgmt_label else "", uuid),
            "tenant_id": self.lbaas_project_id
        }}
        sec_grp = neutron.create_security_group(sec_grp_data)
        # Enable ICMP access on all ports
        self.create_security_group_rule(
            sec_grp['security_group']['id'],
            protocol="icmp"
        )
        if mgmt_port:
            LOG.debug("create rule for mgmt_port(%s)", sec_grp_data['security_group']['name'])
            self.create_security_group_rule(
                sec_grp['security_group']['id'],
                port=cfg.CONF.vapv_settings.admin_port
            )
            self.create_security_group_rule(
                sec_grp['security_group']['id'],
                port=cfg.CONF.vapv_settings.rest_port,
            )
            self.create_security_group_rule(
                sec_grp['security_group']['id'],
                port=cfg.CONF.lbaas_settings.service_endpoint_port,
            )
            # SSH access
            self.create_security_group_rule(
                sec_grp['security_group']['id'],
                port=22
            )
        if cluster:
            LOG.debug("create rule for data_port(%s)", sec_grp_data['security_group']['name'])
            self.create_security_group_rule(
                sec_grp['security_group']['id'],
                protocol='112'
            )
        return sec_grp

    def create_security_group_rule(self, sec_grp_id, port=None,
                                   src_addr=None, remote_group=None,
                                   direction="ingress", protocol='tcp'):
        """
        Creates the designatted rule in a security group.
        """
        neutron = self.get_neutron_client()
        new_rule = {"security_group_rule": {
            "direction": direction,
            "ethertype": "IPv4",
            "protocol": protocol,
            "security_group_id": sec_grp_id,
            "tenant_id": self.lbaas_project_id
        }}
        if port is not None:
            if isinstance(port, tuple):
                port_min = port[0]
                port_max = port[1]
            else:
                port_min = port
                port_max = port
            new_rule['security_group_rule']['port_range_max'] = port_max
            new_rule['security_group_rule']['port_range_min'] = port_min
        if src_addr:
            new_rule['security_group_rule']['remote_ip_prefix'] = src_addr
        if remote_group:
            new_rule['security_group_rule']['remote_group_id'] = remote_group
        try:
            neutron.create_security_group_rule(new_rule)
        except Exception as e:
            if not e.message.startswith("Security group rule already exists"):
                raise

    def allow_port(self, lb, port, identifier, protocol='tcp'):
        """
        Adds access to a given port to a security group.
        """
        # Get the name of the security group for the "loadbalancer"
        sec_grp_name = "lbaas-{}".format(identifier)
        # Get the security group
        neutron = self.get_neutron_client()
        sec_grp = neutron.list_security_groups(
            name=sec_grp_name
        )['security_groups'][0]
        # Create the required rule
        self.create_security_group_rule(sec_grp['id'], port, protocol=protocol)

    def block_port(self, lb, port, identifier, protocol='tcp', force=False):
        """
        Removes access to a given port from a security group.
        """
        neutron = self.get_neutron_client()
        # Only block the port if not in use by another listener hosted on
        # the same vAPV
        if force is False:
            # Get all listeners belonging to this tenant that use this port
            listeners = neutron.list_listeners(
                tenant_id=lb.tenant_id,
                protocol_port=port
            )['listeners']
            # Create a counter of instances of port for each vAPV identifier
            identifier_port_counter = {}
            processed_lbs = []  # Only count each LB once as they don't allow
                                # duplicate ports
            for listener in listeners:
                for loadbalancer in listener['loadbalancers']:
                    if loadbalancer['id'] in processed_lbs:
                        continue
                    processed_lbs.append(loadbalancer['id'])
                    tmp_lb = neutron.show_loadbalancer(loadbalancer['id'])
                    tmp_lb_id = self.get_identifier(tmp_lb['loadbalancer'])
                    try:
                        identifier_port_counter[tmp_lb_id] += 1
                    except KeyError:
                        identifier_port_counter[tmp_lb_id] = 1
            # If there is more than one listener on this vAPV using the
            # port, exit the function without removing it from sec group
            if identifier_port_counter[identifier] > 1:
                return False
        # Get the name of the security group for the "loadbalancer"
        sec_grp_name = "lbaas-{}".format(identifier)
        # Get the security group
        sec_grp = neutron.list_security_groups(
            name=sec_grp_name
        )['security_groups'][0]
        # Iterate through all rules in the group and delete the matching one
        for rule in sec_grp['security_group_rules']:
            if rule['port_range_min'] == port \
                and rule['port_range_max'] == port \
                and rule['direction'] == "ingress" \
                and rule['protocol'] == protocol:
                neutron.delete_security_group_rule(rule['id'])
                break

    def get_identifier(self, lb):
        if isinstance(lb, dict):
            loadbalancer_id = lb['id']
            subnet_id = lb['vip_subnet_id']
            tenant_id = lb['tenant_id']
        else:
            loadbalancer_id = lb.id
            subnet_id = lb.vip_subnet_id
            tenant_id = lb.tenant_id
        deployment_model = self._get_setting(
            tenant_id, "lbaas_settings", "deployment_model"
        )
        if deployment_model == "PER_TENANT":
            return tenant_id
        elif deployment_model == "PER_LOADBALANCER":
            return loadbalancer_id
        elif deployment_model == "PER_SUBNET":
            return hashlib.sha1(
                "{}-{}".format(subnet_id, tenant_id)
            ).hexdigest()

    def create_floatingip(self, port_id):
        neutron = self.get_neutron_client()
        network = cfg.CONF.lbaas_settings.management_network
        floatingip_data = {"floatingip": {
            "floating_network_id": network,
            "port_id": port_id,
            "tenant_id": self.lbaas_project_id
        }}
        return neutron.create_floatingip(floatingip_data)

    def get_network_for_subnet(self, subnet_id):
        neutron = self.get_neutron_client()
        return neutron.show_subnet(subnet_id)['subnet']['network_id']

    def create_server(self, tenant_id, hostname, nics, avoid_host_of=None):
        """
        Creates a Nova instance of the vAPV image.
        """
        image_id = self._get_setting(tenant_id, "lbaas_settings", "image_id")
        flavor_id = self._get_setting(tenant_id, "lbaas_settings", "flavor_id")
        token = self.get_auth_token()
        headers = {
            "Content-Type": "application/json",
            "X-Auth-Token": token
        }
        body = {"server": {
            "imageRef": image_id,
            "flavorRef": flavor_id,
            "name": hostname,
            "networks": nics,
            "config_drive": True
        }}
        specify_az = self._get_setting(tenant_id,"lbaas_settings","specify_az")
        if specify_az is True:
            if hostname.endswith("-sec"):
                body['server']['availability_zone'] = \
                self._get_setting(tenant_id,"lbaas_settings","secondary_az")
            else:
                body['server']['availability_zone'] = \
                self._get_setting(tenant_id,"lbaas_settings","primary_az")
        if avoid_host_of is not None:
            body['os:scheduler_hints'] = {
                "different_host": [avoid_host_of]
            }
        try:
            LOG.debug("will create the server(%s): %s", body, self.nova_endpoint)
            response = requests.post(
                "{}/servers".format(self.nova_endpoint),
                data=json.dumps(body),
                headers=headers
            )
            if response.status_code >= 300:
                raise Exception("{}: {}".format(
                    response.status_code, response.text
                ))
            LOG.debug("response.json: --%s--", response.json())
        except Exception as e:
            LOG.error("\nError creating vAPV instance: {}".format(e))
        return response.json()['server']

    def get_server(self, server_id):
        token = self.get_auth_token()
        response = requests.get(
            "{}/servers/{}".format(self.nova_endpoint, server_id),
            headers={"X-Auth-Token": token}
        )
        if response.status_code != 200:
            raise ServerNotFoundError(server_id=server_id)
        return response.json()['server']

    def attach_port_to_instance(self, server_id, port_id):
        token = self.get_auth_token()
        response = requests.post(
            "{}/servers/{}/os-interface".format(self.nova_endpoint, server_id),
            data=json.dumps({"interfaceAttachment": { "port_id": port_id}}),
            headers={"X-Auth-Token": token, "Content-Type": "application/json"}
        )
        if response.status_code != 200:
            raise Exception(
                "Unable to attach port '{}' to instance '{}': {}".format(
                    port_id, server_id, response.text
            ))

    def detach_port_from_instance(self, server_id, port_id):
        token = self.get_auth_token()
        response = requests.delete(
            "{}/servers/{}/os-interface/{}".format(
                self.nova_endpoint, server_id, port_id
            ),
            headers={"X-Auth-Token": token}
        )
        if response.status_code != 202:
            raise Exception(
                "Unable to detach port '{}' from instance '{}': {}".format(
                    port_id, server_id, response.text
            ))

    def get_mgmt_ip(self, hostname):
        neutron = self.get_neutron_client()
        mgmt_net = neutron.show_network(
            cfg.CONF.lbaas_settings.management_network
        )['network']['name']
        server_id = self.get_server_id_from_hostname(hostname)
        server = self.get_server(server_id)
        return server['addresses'][mgmt_net][0]['addr']

    def set_server_lock(self, server_id, lock=True):
        token = self.get_auth_token()
        response = requests.post(
            "{}/servers/{}/action".format(self.nova_endpoint, server_id),
            headers={
                "X-Auth-Token": token,
                "Content-Type": "application/json"
            },
            data='{{ "{}": null }}'.format("lock" if lock else "unlock")
        )
        if response.status_code != 202:
            raise Exception("Failed to lock server {}".format(server_id))

    def get_server_ports(self, hostname):
        """
        Gets the Neutron ID of a vAPV's data port.
        """
        neutron = self.get_neutron_client()
        server_id = self.get_server_id_from_hostname(hostname)
        all_ports = neutron.list_ports(device_id=server_id)['ports']
        data_ports = [
            port for port in all_ports
            if not port['name'].startswith("mgmt")
        ]
        if data_ports:
            return data_ports
        raise Exception("No data ports found for {}".format(hostname))

    def get_server_port_ids(self, hostname):
        ports = self.get_server_ports(hostname)
        return [port['id'] for port in ports]

    def get_server_id_from_hostname(self, hostname):
        """
        Gets the Nova ID of a server from its hostname.
        """
        token = self.get_auth_token()
        response = requests.get(
            "{}/servers?name={}".format(self.nova_endpoint, hostname),
            headers={"X-Auth-Token": token}
        )
        try:
            return response.json()['servers'][0]['id']
        except Exception:
            raise ServerNotFoundError(hostname=hostname)

    def delete_server(self, server_id):
        """
        Deletes a Nova instance.
        """
        token = self.get_auth_token()
        requests.delete(
            "{}/servers/{}".format(self.nova_endpoint, server_id),
            headers={"X-Auth-Token": token}
        )

    def get_subnet_gateway(self, subnet_id):
        neutron = self.get_neutron_client()
        subnet = neutron.show_subnet(subnet_id)['subnet']
        return subnet['gateway_ip']

    def get_neutron_client(self):
        auth_token = self.get_auth_token(lbaas_project=False)
        neutron = neutron_client.Client(
            '2.0', endpoint_url=self.neutron_endpoint, token=auth_token
        )
        neutron.format = 'json'
        return neutron

    def get_keystone_client(self, lbaas_project=False):
        auth_url = re.match(
            "^(https?://[^/]+)",
            cfg.CONF.keystone_authtoken.auth_uri
        ).group(1)
        if cfg.CONF.lbaas_settings.keystone_version == "2":
            from keystoneclient.v2_0 import client as keystone_client
            auth_url = "%s/v2.0" % auth_url
        else:
            from keystoneclient.v3 import client as keystone_client
            auth_url = "%s/v3" % auth_url
        if lbaas_project is True:
            password = self.lbaas_password
            project_id = self.lbaas_project_id
            username = self.lbaas_username
        else:
            password = self.admin_password
            project_id = self.admin_project_id
            username = self.admin_username
        return keystone_client.Client(
            username=username,
            password=password,
            project_id=project_id,
            auth_url=auth_url
        )

    def get_auth_token(self, lbaas_project=True):
        keystone_client = self.get_keystone_client(lbaas_project)
        return keystone_client.auth_token

    def get_subnet_netmask(self, subnet_id):
        neutron = self.get_neutron_client()
        subnet = neutron.show_subnet(subnet_id)['subnet']
        ip_version = subnet['ip_version']
        if int(ip_version) == 6:
            return self.get_netmask_ipv6(subnet['cidr'])
        else:
            return self.get_netmask(subnet['cidr'])

    def get_netmask_ipv6(self, cidr):
        net = netaddr.IPNetwork(cidr)
        return str(net.prefixlen)

    def get_netmask(self, cidr):
        mask = int(cidr.split("/")[1])
        bits = 0xffffffff ^ (1 << 32 - mask) - 1
        return socket.inet_ntoa(pack('>I', bits))

    def _get_setting(self, tenant_id, section, param):
        setting = None
        if self.customizations_db:
            setting = self.customizations_db.get_customization(
                tenant_id, section, param
            )
        if setting is None:
            global_section = getattr(cfg.CONF, section)
            setting = getattr(global_section, param)
        return setting

