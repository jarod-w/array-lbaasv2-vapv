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

from driver_common import vAPVDeviceDriverCommon, logging_wrapper
from oslo_config import cfg
from oslo_log import log as logging
from threading import Thread
from time import sleep

LOG = logging.getLogger(__name__)


class ArrayDeviceDriverV2(vAPVDeviceDriverCommon):
    """
    Services Director Unmanaged Version
    """

    def __init__(self, plugin):
        super(ArrayDeviceDriverV2, self).__init__()
        LOG.info("\nArray vAPV LBaaS module initialized.")

    @logging_wrapper
    def create_loadbalancer(self, context, lb):
        """
        Ensures a vAPV instance is instantiated for the service.
        If the deployment model is PER_LOADBALANCER, a new vAPV instance
        will always be spawned by this call.  If the deployemnt model is
        PER_TENANT, a new instance will only be spawned if one does not
        already exist for the tenant.
        """
        self._assert_not_mgmt_network(lb.vip_subnet_id)
        deployment_model = self._get_setting(
            lb.tenant_id, "lbaas_settings", "deployment_model"
        )
        mgmt_ip = None
        vapv = None
        ports = None
        existed = True
        network_config = {}
        hostname = self._get_hostname(lb)

        LOG.debug("enter create_loadbalancer: ", deployment_model)
        if deployment_model == "PER_LOADBALANCER":
            ports = self._spawn_vapv(hostname, lb)
        elif deployment_model == "PER_SUBNET":
            # In case several loadbalancers are created in a batch, give an
            # existing instance time to come up before spawning a new one.
            count = 0
            if self.openstack_connector.subnet_in_use(lb):
                while not self.openstack_connector.vapv_exists(hostname):
                    count += 1
                    sleep(5)
                    if count > 5:
                        break;
            # No instance is coming up so spawn one.
            if not self.openstack_connector.vapv_exists(hostname):
                LOG.debug("will create vapv vm")
                existed = False
                ports = self._spawn_vapv(hostname, lb)
                sleep(5)
        elif deployment_model == "PER_TENANT":
            if not self.openstack_connector.vapv_exists(lb.tenant_id, hostname):
                ports = self._spawn_vapv(hostname, lb)
                sleep(5)
            elif not self.openstack_connector.vapv_has_subnet_port(hostname,lb):
                self._attach_subnet_port(hostname, lb)

        if ports:
            if type(hostname) is tuple:
                pass #FIXME
            else:
                mgmt_port = ports['mgmt']
                data_port = ports['data']
                if mgmt_port:
                    mgmt_ip = mgmt_port['fixed_ips'][0]['ip_address']
                network_config['pri_data_ip'] = data_port['fixed_ips'][0]['ip_address']
                network_config['pri_data_netmask'] = self.openstack_connector.get_subnet_netmask(lb.vip_subnet_id)
        else:
            mgmt_ip = self.openstack_connector.get_mgmt_ip(hostname)
            data_port = self.openstack_connector.get_server_ports(hostname)

        LOG.debug("hostname is: --%s--", hostname)
        if existed:
            self.array_amphora_db.increment_inuselb(context.session, hostname)
            vapv = self.array_amphora_db.get_vapv_by_hostname(context.session, hostname)
        else:
            vapv = self.create_vapv(context, tenant_id=lb.tenant_id,
                subnet_id=lb.vip_subnet_id,
                pri_mgmt_address=mgmt_ip,
                in_use_lb=1,
                hostname=hostname
            )
            self.array_vapv_driver.create_loadbalancer(lb, vapv, network_config)

        LOG.debug("create lb vapv: --%s--", vapv)
        description_updater_thread = DescriptionUpdater(
            self.openstack_connector, lb, hostname
        )
        description_updater_thread.start()

    @logging_wrapper
    def update_loadbalancer(self, context, lb, old):
        """
        Creates or updates a TrafficIP group for the loadbalancer VIP address.
        The VIP is added to the allowed_address_pairs of the vAPV's
        Neutron port to enable it to receive traffic to this address.
        Can also update the bandwidth allocation of the vAPV instance.
        """
        deployment_model = self._get_setting(
            lb.tenant_id, "lbaas_settings", "deployment_model"
        )
        hostname = self._get_hostname(lb)
        if deployment_model in ["PER_TENANT", "PER_SUBNET"]:
            # Update allowed_address_pairs
            if not old or lb.vip_address != old.vip_address:
                port_ids = self.openstack_connector.get_server_port_ids(
                    hostname
                )
                self.openstack_connector.add_ip_to_ports(
                    lb.vip_address, port_ids
                )
        # Update bandwidth allocation
        #if old is not None and old.bandwidth != lb.bandwidth:
        #    self._update_instance_bandwidth(hostname, lb.bandwidth)

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
        hostname = self._get_hostname(lb)
        if deployment_model in ["PER_TENANT", "PER_SUBNET"]:
            inuse = self.array_amphora_db.get_inuselb_by_hostname(context.session, hostname)
            if inuse < 2:
                LOG.debug(
                    "\ndelete_loadbalancer({}): "
                    "last loadbalancer deleted; destroying vAPV".format(lb.id)
                )
                deleted = True
                self._destroy_vapv(hostname, lb)
        elif deployment_model == "PER_LOADBALANCER":
            self._destroy_vapv(hostname, lb)

        # update the db
        if deleted:
            self.array_amphora_db.delete(context.session, hostname=hostname)
        else:
            self.array_amphora_db.decrement_inuselb(context.session, hostname)

#############
# LISTENERS #
#############

    @logging_wrapper
    def update_listener(self, context, listener, old):
        hostname = self._get_hostname(listener.loadbalancer)
        vapv = self._get_vapv(context, hostname)
        LOG.debug("listener vapvs: %s", vapv)
        super(ArrayDeviceDriverV2, self).update_listener(
            context, listener, old, vapv
        )

    @logging_wrapper
    def delete_listener(self, context, listener):
        hostname = self._get_hostname(listener.loadbalancer)
        vapv = self._get_vapv(context, hostname)
        super(ArrayDeviceDriverV2, self).delete_listener(context, listener, vapv)

#########
# POOLS #
#########

    @logging_wrapper
    def update_pool(self, context, pool, old):
        deployment_model = self._get_setting(
            pool.tenant_id, "lbaas_settings", "deployment_model"
        )
        if deployment_model in ["PER_TENANT", "PER_SUBNET"]:
            hostname = self._get_hostname(pool.root_loadbalancer)
        elif deployment_model == "PER_LOADBALANCER":
            if pool.listener.loadbalancer is not None:
                hostname = self._get_hostname(pool.listener.loadbalancer)
            else:
                hostname = self._get_hostname(
                    pool.listener.loadbalancer
                )
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.update_pool(pool, old, vapv)

    @logging_wrapper
    def delete_pool(self, context, pool):
        hostname = self._get_hostname(pool.listener.loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.delete_pool(pool, vapv)

###########
# MEMBERS #
###########

    @logging_wrapper
    def get_member_health(self, context, member):
        hostname = self._get_hostname(member.pool.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        status = super(ArrayDeviceDriverV2, self).get_member_health(
            member, vapv
        )
        return status


###############
# L7 POLICIES #
###############

    @logging_wrapper
    def update_l7_policy(self, context, policy, old):
        hostname = self._get_hostname(policy.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        super(ArrayDeviceDriverV2, self).update_l7_policy(policy, old, vapv)

    @logging_wrapper
    def delete_l7_policy(self, context, policy):
        hostname = self._get_hostname(policy.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        super(ArrayDeviceDriverV2, self).delete_l7_policy(policy, vapv)

#########
# STATS #
#########

    @logging_wrapper
    def stats(self, context, loadbalancer):
        deployment_model = self._get_setting(
            loadbalancer.tenant_id, "lbaas_settings", "deployment_model"
        )
        hostname = self._get_hostname(loadbalancer)
        vapv = self._get_vapv(context, hostname)
        if deployment_model in ["PER_TENANT", "PER_SUBNET"]:
            return super(ArrayDeviceDriverV2, self).stats(
                vapv, loadbalancer.vip_address
            )
        elif self.lb_deployment_model == "PER_LOADBALANCER":
            return super(ArrayDeviceDriverV2, self).stats(vapv)

########
# MISC #
########

    def _get_hostname(self, lb):
        identifier = self.openstack_connector.get_identifier(lb)
        return "vapv-{}".format(identifier)

    def _update_instance_bandwidth(self, hostnames, bandwidth):
        pass

    def _get_vapv(self, context, hostname):
        """
        Gets available instance of Array vAPV.
        """
        if isinstance(hostname, list) or isinstance(hostname, tuple):
            for host in hostname:
                try:
                    return self._get_vapv(context, host)
                except:
                    pass
            raise Exception("Could not contact vAPV instance")
        return self.array_amphora_db.get_vapv_by_hostname(context.session, hostname)

    def _assert_not_mgmt_network(self, subnet_id):
        network_id = self.openstack_connector.get_network_for_subnet(subnet_id)
        if network_id == cfg.CONF.lbaas_settings.management_network:
            raise Exception("Specified subnet is part of management network")

    def _attach_subnet_port(self, hostname, lb):
        pass

    def _detach_subnet_port(self, hostname, lb):
        pass

    def _spawn_vapv(self, hostname, lb):
        """
        Creates a vAPV instance as a Nova VM.
        The VM is registered with Services Director to provide licensing and
        configuration proxying.
        """
        identifier = self.openstack_connector.get_identifier(lb)
        # Initialize lists for roll-back on error
        port_ids = []
        security_groups = []
        vms = []
        data_ip = None
        mgmt_ip = None
        # Create ports...
        try: # For rolling back objects if an error occurs
            if cfg.CONF.lbaas_settings.management_mode == "FLOATING_IP":
                port, sec_grp, mgmt_ip = self.openstack_connector.create_port(
                    lb, hostname, create_floating_ip=True,
                    identifier=identifier
                )
                ports = {"data": port, "mgmt": None}
                port_ids.append(port['id'])
                security_groups = [sec_grp]
            elif cfg.CONF.lbaas_settings.management_mode == "MGMT_NET":
                data_port, sec_grp, data_ip = self.openstack_connector.create_port(
                    lb, hostname, identifier=identifier
                )
                (mgmt_port, mgmt_sec_grp, mgmt_ip) = self.openstack_connector.create_port(
                    lb, hostname, mgmt_port=True, identifier=identifier
                )
                ports = {"data": data_port, "mgmt": mgmt_port}
                security_groups = [sec_grp, mgmt_sec_grp]
                port_ids.append(data_port['id'])
                port_ids.append(mgmt_port['id'])
            # Register instance record...
            try:
                bandwidth = lb.bandwidth
                if bandwidth == 0:
                    raise AttributeError()
            except AttributeError:
                bandwidth = self._get_setting(
                    lb.tenant_id, "services_director_settings", "bandwidth"
                )
            # Start instance...
            vm = self.openstack_connector.create_vapv(hostname, lb, ports)
            vms.append(vm['id'])
            LOG.info(
                "\nvAPV {} created for tenant {}".format(
                    hostname, lb.tenant_id
                )
            )
            
            return ports
        except Exception as e:
            self.openstack_connector.clean_up(
                instances=vms,
                security_groups=security_groups,
                ports=port_ids
            )
            raise e

    def _destroy_vapv(self, hostname, lb):
        """
        Destroys the vAPV Nova VM.
        The vAPV is "deleted" in Services Director (this flags the instance
        rather than actually deleting it from the database).
        """
        self.openstack_connector.destroy_vapv(hostname, lb)
        LOG.debug("\nvAPV {} destroyed".format(hostname))


class DescriptionUpdater(Thread):
    def __init__(self, os_conn, lb, hostnames):
        self.openstack_connector = os_conn
        self.lb = lb
        if isinstance(hostnames, basestring):
            self.hostnames = [hostnames]
        else:
            self.hostnames = hostnames
        super(DescriptionUpdater, self).__init__()

    def run(self):
        ip_addresses = []
        neutron = self.openstack_connector.get_neutron_client()
        while True:
            lb = neutron.show_loadbalancer(self.lb.id)
            if lb['loadbalancer']['provisioning_status'] != "PENDING_CREATE":
                break
            sleep(3)
        body = {"loadbalancer": {
            "description": "{} {}".format(
                self.lb.description,
                "(vAPVs: {}; VIP: {})".format(
                    ", ".join(ip_addresses), self.lb.vip_address
                )
            )
        }}
        neutron.update_loadbalancer(self.lb.id, body)
