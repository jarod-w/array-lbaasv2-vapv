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
from array_neutron_lbaas.db import repository
from array_neutron_lbaas.array import device_driver
from neutron_lbaas.common.tls_utils.cert_parser import get_host_names
from openstack_connector import OpenStackInterface
from oslo_config import cfg
from oslo_log import log as logging
from traceback import format_exc
from xmlrpclib import ServerProxy

try:
    from neutron_lbaas.common.cert_manager import CERT_MANAGER_PLUGIN
except ImportError:
    from neutron_lbaas.common import cert_manager
    CERT_MANAGER_PLUGIN = cert_manager.get_backend()

LOG = logging.getLogger(__name__)


def logging_wrapper(lbaas_func):
    def log_writer(*args):
        LOG.debug(
            "\n{}({}): called".format(
                lbaas_func.__name__, getattr(args[2], "id")
        ))
        try:
            return_value = lbaas_func(*args)
            LOG.debug(
                "\n{}({}): completed!".format(
                    lbaas_func.__name__, getattr(args[2], "id")
            ))
            return return_value
        except Exception as e:
            LOG.error(
                "\nError in {}({}): {}\n\n{}".format(
                    lbaas_func.__name__,
                    getattr(args[2], "id"),
                    e,
                    format_exc()
            ))
            raise e
    return log_writer


class vAPVDeviceDriverCommon(object):
    """
    Common methods/properties
    """

    def __init__(self):
        self.openstack_connector = OpenStackInterface()
        self.certificate_manager = CERT_MANAGER_PLUGIN.CertManager
        self.array_amphora_db = repository.ArrayAmphoraRepository()
        self.array_vapv_driver = device_driver.ArrayADCDriver()
        # Get connector to tenant customizations database if enabled...
        if cfg.CONF.lbaas_settings.allow_tenant_customizations is True:
            self.customizations_db = customization_helper.\
                ArrayLbaasTenantCustomizationsDatabaseHelper(
                    cfg.CONF.lbaas_settings.tenant_customizations_db
                )
        else:
            self.customizations_db = None

#############
# LISTENERS #
#############

    def create_listener(self, context, listener):
        self.update_listener(context, listener, None)

    def update_listener(self, context, listener, old, vapv,
                        use_security_group=True, note=None):
        # Configure SSL termination...
        lb = listener.loadbalancer
        if listener.protocol == "TERMINATED_HTTPS":
            if cfg.CONF.lbaas_settings.https_offload is False:
                raise Exception("HTTPS termination has been disabled by "
                                "the administrator")
        # Modify Neutron security group to allow access to data port...
        if use_security_group:
            identifier = self.openstack_connector.get_identifier(lb)
            if not old or old.protocol_port != listener.protocol_port:
                LOG.debug("will allow port %s", str(listener.protocol_port))
                protocol = 'udp' if listener.protocol == "UDP" else 'tcp'
                self.openstack_connector.allow_port(
                    lb, listener.protocol_port, identifier,
                    protocol
                )
                if old:
                    self.openstack_connector.block_port(
                        lb, old.protocol_port, identifier,
                        protocol
                    )
        if old:
            self.array_vapv_driver.update_listener(lb, listener, old, vapv)
        else:
            self.array_vapv_driver.create_listener(lb, listener, vapv)
            if listener.protocol == "TERMINATED_HTTPS":
                self._config_ssl(vapv, listener)

    def delete_listener(self, context, listener, vapv, use_security_group=False):
        # Delete associated SSL certificates
        if listener.protocol == "TERMINATED_HTTPS":
            self._clean_up_certificates(vapv, listener)
        if use_security_group:
            # Delete security group rule for the listener port/protocol
            protocol = 'udp' if listener.protocol == "UDP" else 'tcp'
            identifier = self.openstack_connector.get_identifier(
                listener.loadbalancer
            )
            self.openstack_connector.block_port(
                listener.loadbalancer, listener.protocol_port, identifier,
                protocol
            )
        self.array_vapv_driver.delete_listener(listener, vapv)

#########
# POOLS #
#########

    def create_pool(self, context, pool):
        hostname = self._get_hostname(pool.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.create_pool(pool, vapv)

    def delete_pool(self, context, pool, vapv):
        # If pool has a listener, reset vserver default pool to 'discard'
        if pool.listener is not None:
            vs = vapv.vserver.get(pool.listener.id)
            if vs.pool == pool.id:
                vs.pool = 'discard'
                vs.update()
        # Delete the pool itelf
        vapv.pool.delete(pool.id)
        # Delete any associated persistence classes
        if pool.sessionpersistence or pool.lb_algorithm == "SOURCE_IP":
            vapv.persistence_class.delete(pool.id)

###########
# MEMBERS #
###########

    @logging_wrapper
    def create_member(self, context, member):
        hostname = self._get_hostname(member.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.create_member(member, vapv)

    @logging_wrapper
    def update_member(self, context, member, old):
        hostname = self._get_hostname(member.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.update_member(member, old, vapv)

    @logging_wrapper
    def delete_member(self, context, member):
        hostname = self._get_hostname(member.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.delete_member(member, vapv)

    def get_member_health(self, context, member, vapv):
        """
        Return the health of the specified node.
        """
        return "ACTIVE"

############
# MONITORS #
############

    @logging_wrapper
    def create_healthmonitor(self, context, monitor):
        hostname = self._get_hostname(monitor.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.create_health_monitor(monitor, vapv)

    @logging_wrapper
    def update_healthmonitor(self, context, monitor, old):
        hostname = self._get_hostname(
            monitor.root_loadbalancer
        )
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.update_health_monitor(monitor, old, vapv)

    @logging_wrapper
    def delete_healthmonitor(self, context, monitor):
        hostname = self._get_hostname(monitor.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.delete_health_monitor(monitor, vapv)


###############
# L7 POLICIES #
###############

    @logging_wrapper
    def create_l7_policy(self, context, policy):
        hostname = self._get_hostname(policy.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.create_l7_policy(policy, vapv)

    @logging_wrapper
    def update_l7_policy(self, context, policy, old):
        hostname = self._get_hostname(policy.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.update_l7_policy(policy, old, vapv)

    @logging_wrapper
    def delete_l7_policy(self, context, policy):
        hostname = self._get_hostname(policy.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.delete_l7_policy(policy, vapv)

############
# L7 RULES #
############

    @logging_wrapper
    def create_l7_rule(self, context, rule):
        hostname = self._get_hostname(rule.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.create_l7_rule(rule, vapv)

    @logging_wrapper
    def update_l7_rule(self, context, rule, old):
        hostname = self._get_hostname(rule.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.update_l7_rule(rule, old, vapv)

    @logging_wrapper
    def delete_l7_rule(self, context, rule):
        hostname = self._get_hostname(rule.root_loadbalancer)
        vapv = self._get_vapv(context, hostname)
        self.array_vapv_driver.delete_l7_rule(rule, vapv)

#########
# STATS #
#########

    def stats(self, vapv, loadbalancer):
        pri_mgmt_addr = vapv['pri_mgmt_address']
        sec_mgmt_addr = vapv['sec_mgmt_address']
        pri_url = "http://" + pri_mgmt_addr + ":8889"
        sec_url = "http://" + sec_mgmt_addr + ":8889"
        listeners = loadbalancer.listeners

        stats = {}
        stats["bytes_in"] = 0
        stats["bytes_out"] = 0
        stats["active_connections"] = 0
        stats["total_connections"] = 0
        for listener in listeners:
            lis_id = listener.id
            lis_protocol = listener.protocol
            server = ServerProxy(pri_url)
            stat = server.get_string(lis_protocol, lis_id)
            if stat == "None" or stat["bytes_in"] == -1:
                server = ServerProxy(sec_url)
                stat = server.get_string(lis_protocol, lis_id)
            try:
                stats["bytes_in"] += int(stat["bytes_in"])
                stats["bytes_out"] += int(stat["bytes_out"])
                stats["active_connections"] += int(stat["active_connections"])
                stats["total_connections"] += int(stat["total_connections"])
            except:
                LOG.error("Failed to get the loadbalancer stats")
                return {
                    "bytes_in": -1,
                    "bytes_out": -1,
                    "active_connections": -1,
                    "total_connections": -1
                }
        LOG.debug("got the loadbalancer stats %s", stats)
        return {
            "bytes_in": stats["bytes_in"],
            "bytes_out": stats["bytes_out"],
            "active_connections": stats["active_connections"],
            "total_connections": stats["total_connections"]
        }

###########
# REFRESH #
###########

    @logging_wrapper
    def refresh(self, context, lb, force):
        self.update_loadbalancer(context, lb, None)
        for listener in lb.listeners:
            self.update_listener(context, listener, None)
            pools = listener.pools
            for pool in pools:
                self.update_pool(context, pool, None)
                self.update_healthmonitor(context, pool.healthmonitor, None)

########
# MISC #
########

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

    def create_vapv(self, context, **model_kwargs):
        vapv = self.array_amphora_db.create(context.session, **model_kwargs);
        return vapv

    def find_available_cluster_id(self, context, subnet_id):
        cluster_ids = self.array_amphora_db.get_clusterids_by_subnet(context.session, subnet_id)
        supported_ids = range(1, 256)
        diff_ids=list(set(supported_ids).difference(set(cluster_ids)))
        if len(diff_ids) > 1:
            return diff_ids[0]
        return 0

    def _get_container_id(self, container_ref):
        return container_ref[container_ref.rfind("/")+1:]

    def _config_ssl(self, vapv, listener):
        # Upload default certificate
        self._upload_certificate(
            vapv, listener, listener.default_tls_container_id, default=True
        )
        # Configure SNI certificates
        if listener.sni_containers:
            for sni_container in listener.sni_containers:
                # Get cert from Barbican and upload to vAPV
                self._upload_certificate(
                    vapv, listener, sni_container.tls_container_id
                )

    def _upload_certificate(self, vapv, listener, container_id, default = False):
        # Get the certificate from Barbican
        cert = self.certificate_manager.get_cert(
            container_id,
            service_name="arrayapv provider",
            check_only=True
        )
        # Check that the private key is not passphrase-protected
        if cert.get_private_key_passphrase():
            raise Exception(
                "The vAPV LBaaS provider does not support private "
                "keys with a passphrase"
            )
        # Add server certificate to any intermediates
        try:
            cert_chain = cert.get_certificate() + cert.get_intermediates()
        except TypeError:
            cert_chain = cert.get_certificate()
        domain_name = None
        if not default:
            cert_hostnames = get_host_names(cert.get_certificate())
            domain_name = cert_hostnames['cn']
        self.array_vapv_driver.upload_cert(vapv, listener, container_id,
                cert.get_private_key(), cert_chain, domain_name)

    def _clean_up_certificates(self, vapv, listener):
        # Upload default certificate
        self._no_certificate(
            vapv, listener, listener.default_tls_container_id, default=True
        )
        # Configure SNI certificates
        if listener.sni_containers:
            for sni_container in listener.sni_containers:
                # Get cert from Barbican and upload to vAPV
                self._no_certificate(
                    vapv, listener, sni_container.tls_container_id
                )

    def _no_certificate(self, vapv, listener, container_id, default=False):
        cert = self.certificate_manager.get_cert(
            container_id,
            service_name="arrayapv provider",
            check_only=True
        )
        domain_name = None
        if not default:
            cert_hostnames = get_host_names(cert.get_certificate())
            domain_name = cert_hostnames['cn']
        self.array_vapv_driver.clear_cert(vapv, listener, container_id,
                                         domain_name)


