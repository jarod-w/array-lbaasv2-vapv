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

        elif old and old.protocol == "TERMINATED_HTTPS":
            self._clean_up_certificates(vapv, listener.id)
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

    def delete_listener(self, context, listener, vapv, use_security_group=False):
        # Delete associated SSL certificates
        if listener.protocol == "TERMINATED_HTTPS":
            self._clean_up_certificates(vapv, listener.id)
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
        # No point creating policy until there are rules to go in it!
        pass

    def update_l7_policy(self, context, policy, old, vapv):
        if not policy.rules:
            self.delete_l7_policy(policy)
            return
        # Create the TrafficScript(tm) rule
        ts_rule_name = "l7policy-{}".format(policy.id)
        # Make sure the rules are in the correct order
        vserver = vapv.vserver.get(policy.listener_id)
        policies = vserver.request_rules
        try:
            policies.remove(ts_rule_name)
        except ValueError:
            pass
        position = policy.position
        if position is None:
            # No position specified, so just append the rule
            policies.append(ts_rule_name)
        else:
            try:
                # Ensure l7 rules remain below rate-shaping rules
                if vserver.request_rules[0].startswith("rate-"):
                    position += 1
            except IndexError:
                pass
            if position >= len(policies):
                policies.append(ts_rule_name)
            else:
                policies.insert(position, ts_rule_name)
        # Apply ordered rules to vserver
        vserver.request_rules = policies
        vserver.update()

    def delete_l7_policy(self, context, policy, vapv):
        ts_rule_name = "l7policy-{}".format(policy.id)
        vserver = vapv.vserver.get(policy.listener_id)
        try:
            vserver.request_rules.remove(ts_rule_name)
            vserver.update()
            vapv.rule.delete(ts_rule_name)
        except ValueError:
            # May have already been deleted if rules were deleted individually
            pass

############
# L7 RULES #
############

    @logging_wrapper
    def create_l7_rule(self, context, rule):
        self.update_l7_rule(rule, None)

    @logging_wrapper
    def update_l7_rule(self, context, rule, old):
        self.update_l7_policy(rule.policy, None)

    @logging_wrapper
    def delete_l7_rule(self, context, rule_to_delete):
        policy = rule_to_delete.policy
        policy.rules = [
            rule for rule in policy.rules
            if rule.id != rule_to_delete.id
        ]
        self.update_l7_policy(policy, None)

#########
# STATS #
#########

    def stats(self, context, vapv, listen_ip=None):
        pass

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

    def _get_ssl_config(self, vapv, listener):
        container_id = self._get_container_id(
            listener.default_tls_container_id
        )
        # Upload default certificate
        default_cert_name, cert = self._upload_certificate(
            vapv, listener.id, listener.default_tls_container_id
        )
        # Set default certificate
        ssl_settings = {
            "server_cert_default": default_cert_name,
            "server_cert_host_mapping": []
        }
        # Configure SNI certificates
        if listener.sni_containers:
            for sni_container in listener.sni_containers:
                container_id = self._get_container_id(
                    sni_container.tls_container_id
                 )
                # Get cert from Barbican and upload to vAPV
                cert_name, cert = self._upload_certificate(
                    vapv, listener.id, sni_container.tls_container_id
                )
                # Get CN and subjectAltNames from certificate
                cert_hostnames = get_host_names(cert.get_certificate())
                # Add the CN and the certificate to the virtual server
                # SNI certificate mapping table
                ssl_settings['server_cert_host_mapping'].append(
                    {
                        "host": cert_hostnames['cn'],
                        "certificate": cert_name
                    }
                )
                # Add subjectAltNames to the mapping table if present
                try:
                    for alt_name in cert_hostnames['dns_names']:
                        ssl_settings['server_cert_host_mapping'].append(
                            {
                                "host": alt_name,
                                "certificate": cert_name
                            }
                        )
                except TypeError:
                    pass
        return ssl_settings

    def _upload_certificate(self, vapv, listener_id, container_id):
        # Get the certificate from Barbican
        cert = self.certificate_manager.get_cert(
            container_id,
            service_name="Neutron LBaaS v2 Brocade provider",
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
        # Upload the certificate and key to the vAPV
        cert_name = "{}-{}".format(
            listener_id, self._get_container_id(container_id)
        )
        vapv.ssl_server_cert.create(
            cert_name, private=cert.get_private_key(), public=cert_chain
        )
        return cert_name, cert

    def _clean_up_certificates(self, vapv, listener_id):
        vs = vapv.vserver.get(listener_id)
        # Delete default certificate
        vapv.ssl_server_cert.delete(vs.ssl__server_cert_default)
        # Delete SNI certificates
        for sni_cert in vs.ssl__server_cert_host_mapping:
            vapv.ssl_server_cert.delete(sni_cert['certificate'])
