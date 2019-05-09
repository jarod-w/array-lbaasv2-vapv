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

from driver_common import logging_wrapper
from driver_private_instances import ArrayDeviceDriverV2 \
    as vAPVDeviceDriverPrivateInstances
from oslo_config import cfg
from oslo_log import log as logging

import traceback

LOG = logging.getLogger(__name__)


class ArrayDeviceDriverV2(vAPVDeviceDriverPrivateInstances):
    """
    Services Director Unmanaged Version with provisioning of HA pairs.
    """

    @logging_wrapper
    def delete_loadbalancer(self, context, lb):
        """
        Deletes the listen IP from a vAPV.
        In the case of PER_LOADBALANCER deployments, this involves destroying
        the whole vAPV instance. In the case of a PER_TENANT deployment, it
        involves deleting the TrafficIP Group associated with the VIP address.
        When the last TrafficIP Group has been deleted, the instance is
        destroyed.
        """
        deployment_model = self._get_setting(
            lb.tenant_id, "lbaas_settings", "deployment_model"
        )
        deleted = False
        hostnames = self._get_hostname(lb)
        if deployment_model in ["PER_TENANT", "PER_SUBNET"]:
            inuse = self.array_amphora_db.get_inuselb_by_hostname(context.session, hostnames[0])
            if inuse < 2:
                LOG.debug(
                    "\ndelete_loadbalancer({}): "
                    "last loadbalancer deleted; destroying vAPV".format(lb.id)
                )
                deleted = True
                self._destroy_vapv(hostnames, lb)
        elif deployment_model == "PER_LOADBALANCER":
            self._destroy_vapv(hostnames, lb)

        # update the db
        if deleted:
            self.array_amphora_db.delete(context.session, hostname=hostnames[0])
        else:
            if deployment_model in ["PER_TENANT", "PER_SUBNET"]:
                for entry in hostnames:
                    port_ids = self.openstack_connector.get_server_port_ids(entry)
                    self.openstack_connector.delete_ip_from_ports(
                        lb.vip_address, port_ids
                    )
            self.array_amphora_db.decrement_inuselb(context.session, hostnames[0])
            vapv = self._get_vapv(context, hostnames[0])
            self.array_vapv_driver.delete_loadbalancer(lb, vapv)

########
# MISC #
########

    def _get_hostname(self, lb):
        identifier = self.openstack_connector.get_identifier(lb)
        return (
            "vapv-{}-pri".format(identifier), "vapv-{}-sec".format(identifier)
        )


    def _spawn_vapv(self, hostnames, lb):
        """
        Creates a vAPV HA cluster as Nova VM instances.
        The VMs are registered with Services Director to provide licensing and
        configuration proxying.
        """
        identifier = self.openstack_connector.get_identifier(lb)
        # Initialize lists of items to clean up if operation fails
        port_ids = []
        security_groups = []
        vms = []
        try:  # For rolling back objects if failure occurs...
            # Create ports...
            ports = {}
            if cfg.CONF.lbaas_settings.management_mode == "FLOATING_IP":
                # Primary data port (floating IP)
                (port, sec_grp, mgmt_ip) = self.openstack_connector.create_port(
                    lb, hostnames[0], create_floating_ip=True, cluster=True,
                    identifier=identifier
                )
                ports[hostnames[0]] = {
                    "ports": {
                        "data": port,
                        "mgmt": None
                    },
                    "mgmt_ip": mgmt_ip
                }
                port_ids.append(port['id'])
                security_groups = [sec_grp]
                # Secondary data port (floating IP)
                (port, junk, mgmt_ip) = self.openstack_connector.create_port(
                    lb, hostnames[1], security_group=sec_grp,
                    create_floating_ip=True
                )
                ports[hostnames[1]] = {
                    "ports": {
                        "data": port,
                        "mgmt": None
                    },
                    "mgmt_ip": mgmt_ip
                }
                port_ids.append(port['id'])
            elif cfg.CONF.lbaas_settings.management_mode == "MGMT_NET":
                # Primary data port (management network)
                (data_port, data_sec_grp, junk) = self.openstack_connector.create_port(
                    lb, hostnames[0], cluster=True, identifier=identifier
                )
                # Primary mgmt port (management network)
                (mgmt_port, mgmt_sec_grp, mgmt_ip) = self.openstack_connector.create_port(
                    lb, hostnames[0], mgmt_port=True, identifier=identifier
                )
                ports[hostnames[0]] = {
                    "ports": {
                        "data": data_port,
                        "mgmt": mgmt_port
                    },
                    "mgmt_ip": mgmt_ip
                }
                security_groups = [data_sec_grp, mgmt_sec_grp]
                port_ids.append(data_port['id'])
                port_ids.append(mgmt_port['id'])
                # Secondary data port (management network)
                (data_port, sec_grp, junk) = self.openstack_connector.create_port(
                    lb, hostnames[1], security_group=data_sec_grp, cluster=True
                )
                # Secondary mgmt port (management network)
                (mgmt_port, junk, mgmt_ip) = self.openstack_connector.create_port(
                    lb, hostnames[1], mgmt_port=True, security_group=mgmt_sec_grp
                )
                ports[hostnames[1]] = {
                    "ports": {
                        "data": data_port,
                        "mgmt": mgmt_port
                    },
                    "mgmt_ip": mgmt_ip
                }
                port_ids.append(data_port['id'])
                port_ids.append(mgmt_port['id'])

            # Create instances...
            try:
                bandwidth = lb.bandwidth
                if bandwidth == 0:
                    raise AttributeError()
            except AttributeError:
                bandwidth = self._get_setting(
                    lb.tenant_id, "services_director_settings", "bandwidth"
                )
            avoid = None
            for host in hostnames:
                # Launch vAPV...
                vm = self.openstack_connector.create_vapv(
                    host, lb, ports[host]['ports'], avoid
                )
                vms.append(vm['id'])
                # Set params for next iteration...
                if cfg.CONF.lbaas_settings.allow_different_host_hint is True:
                    avoid = vm['id']
            return ports
        except Exception as e:
            LOG.debug("trace is below: %s", traceback.format_exc())
            if cfg.CONF.lbaas_settings.roll_back_on_error is True:
                self.openstack_connector.clean_up(
                    instances=vms,
                    security_groups=security_groups,
                    ports=port_ids
                )
            raise e

    def _destroy_vapv(self, hostnames, lb):
        """
        Destroys the vAPV Nova VM.
        The vAPV is "deleted" in Services Director (this flags the instance
        rather than actually deleting it from the database).
        """
        for hostname in hostnames:
            try:
                self.openstack_connector.destroy_vapv(hostname, lb)
                LOG.debug("\nvAPV {} destroyed".format(hostname))
            except Exception as e:
                LOG.error(e)
