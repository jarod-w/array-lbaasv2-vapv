#!/usr/bin/env python
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

from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

lbaas_setting_opts = [
    cfg.BoolOpt('allow_different_host_hint', default=True, help=
                'Deploy secondary instances on different compute node. '
                'DO NOT set to True if there is only one compute node '
                '(e.g. DevStack)'),
    cfg.BoolOpt('allow_tenant_customizations', default=False,
               help='Allow certain global settings to be overriden on a '
               'per-tanant basis'),
    cfg.BoolOpt('deploy_ha_pairs', default=False, help=
                'If set to True, an HA pair of vAPVs will be deployed in '
                'the PER_TENANT and PER_LOADBALANCER deployment models. '
                'If False, single vAPV insatnces are deployed'),
    cfg.StrOpt('deployment_model', help=
               'SHARED for a shared pool of vAPVs. '
               'PER_TENANT for deploying private vAPV instance per tenant. '
               'PER_LB for deploying private vAPV instance per loadbalancer.'
               'PER_SUBNET for deploying private vAPV instance per subnet.'
               ),
    cfg.StrOpt('flavor_id',
               help='ID of flavor to use for vAPV instance'),
    cfg.StrOpt('keystone_version', default="3",
               help='Version of Keystone API to use'),
    cfg.BoolOpt('https_offload', default=True,
                help='Enable HTTPS termination'),
    cfg.StrOpt('image_id',
               help='Glance ID of vAPV image file to provision'),
    cfg.StrOpt('lbaas_project_id',
               help='Keystone ID of LBaaS instance container project'),
    cfg.StrOpt('lbaas_project_password', default="password",
               help='Password for LBaaS operations'),
    cfg.StrOpt('lbaas_project_username', default="lbaas_admin",
               help='Username for LBaaS operations'),
    cfg.StrOpt('management_mode', default='FLOATING_IP',
               help='Whether to use floating IP (FLOATING_IP) or '
                      'dedicated mgmt network (MGMT_NET)'),
    cfg.StrOpt('management_network',
               help='Neutron ID of network for admin traffic'),
    cfg.StrOpt('openstack_password', default="password",
               help='Password of OpenStack admin account'),
    cfg.StrOpt('admin_project_id',
               help='Keystone ID of admin project'),
    cfg.StrOpt('openstack_username', default="admin",
               help='LBaaS instance container project'),
    cfg.StrOpt('primary_az', help='Availability Zone for primary vAPV'),
    cfg.BoolOpt('roll_back_on_error', default=True, help=
                'If True, an error during loadbalancer provisioning will '
                'result in newly-created resources being deleted so as to '
                'return the system to its previous state. Set to False if '
                'you wish to leave resources in place for troubleshooting.'),
    cfg.StrOpt('secondary_az', help='Availability Zone for secondary vAPV'),
    cfg.ListOpt('shared_subnets', help=
                'List of Neutron subnet IDs that represent the available '
                'shared subnets'),
    cfg.BoolOpt('specify_az', default=False, help=
                'If set to true, admin can specify which Availibility Zones '
                'the primary and secondary vAPVs are deployed in.'),
    cfg.StrOpt('service_endpoint_address',
               help='Service Endpoint Address of Services Director cluster'
               ),
    cfg.StrOpt('tenant_customizations_db', help=
               'Database connection string for customizations DB '
               '(<db_type>://<username>:<password>@<db_host>/<db_name>)')
]
services_director_setting_opts = [
    cfg.IntOpt('bandwidth',
               help='Bandwidth allowance for vAPV instances')
]
vapv_setting_opts = [
    cfg.IntOpt('admin_port', default=8889,
               help='Port that the vAPV admin interface listens on'),
    cfg.StrOpt('api_version', default="4.0",
               help='Version of Stingray REST API to use'),
    cfg.IntOpt('mtu', default=1450,
               help='MTU for the vAPV instance interfaces'),
    cfg.StrOpt('password', default=None,
               help='Password of vAPV admin account'),
    cfg.IntOpt('rest_port', default=9997,
               help='TCP port that the vAPV REST daemon listens on'),
    cfg.StrOpt('username', default="admin",
               help='Username for vAPV admin account')
]
cfg.CONF.register_opts(lbaas_setting_opts, "lbaas_settings")
cfg.CONF.register_opts(services_director_setting_opts,
                       "services_director_settings")
cfg.CONF.register_opts(vapv_setting_opts, "vapv_settings")


def check_required_settings(required):
    error_msg = "\n\nThe following settings were not found in the " + \
                "Array vAPV LBaaS configuration file:\n\n"
    key_missing = False
    for section, required_settings in required.iteritems():
        section_key_missing = False
        error_msg += "Missing from section [{}]:\n".format(section)
        configured_settings = [
            key for key, value in getattr(cfg.CONF, section).iteritems()
            if value is not None
        ]
        for setting, help_string in required_settings.iteritems():
            if setting not in configured_settings:
                error_msg += "{}: {}\n".format(setting, help_string)
                section_key_missing = True
                key_missing = True
        if not section_key_missing:
            error_msg += "Nothing\n"
        error_msg += "\n"
    if key_missing:
        error_msg += "Please ensure that the Array LBaaS configuration " + \
            "file is being passed to the Neutron server with the " + \
            "--config-file parameter, and that the file contains values " + \
            "for the above settings.\n"
        raise Exception(error_msg)


if cfg.CONF.lbaas_settings.deployment_model is None:
    raise Exception(
        "LBaaS: No value for deployment_model in lbaas_settings. "
        "Either the value is not in the Array LBaaS configuration file "
        "or the configuration file was not passed to the neutron server."
    )

if cfg.CONF.lbaas_settings.deployment_model != "SHARED":
    check_required_settings({
        "lbaas_settings": {
            "flavor_id":
                "Nova flavor to use for vAPV instances (name or UUID)",
            "image_id":
                "Glance UUID of the vAPV Virtual Appliance image to use",
            "management_network":
                "For MGMT_NET mode, the Neutron UUID of the management "
                "network. For FLOATING_IP mode, the Neutron UUID of the "
                "network on which to raise the floating IPs.",
            "openstack_password":
                "Password of OpenStack admin user",
        },
        "services_director_settings": {
            "bandwidth":
                "Amount of bandwidth to allocate to each vAPV instance"
        },
        "vapv_settings": {
        }
    })
    if cfg.CONF.lbaas_settings.deploy_ha_pairs is True:
        import driver_private_instances_ha as selected_driver
    else:
        import driver_private_instances as selected_driver
device_driver = selected_driver
