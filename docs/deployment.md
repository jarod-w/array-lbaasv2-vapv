# How to deploy vAPV LBaaS driver

## Prerequisites

### Install LBaaS driver

The driver should be installed in network node.

If the based OS is centos 7.x, you can install the driver RPM package using the below CLI.

```sh
rpm -Uvh array-lbaasv2-vapv-1.0.0-1.el7.noarch.rpm
```

If not, you can use source code to install the package using the below CLI:

```sh
python setup.py install
```

Note: Before install, you should firstly install the below packages:

* openstack-neutron-lbaas
* python-neutron-lbaas

### Upload the vAPV image to OpenStack

The image can be uploaded using the below CLI:

```sh
openstack image create --public --disk-format qcow2 --container-format bare --file $IMAGE_PATH vapv
```

Note: As a workaround, we should use e1000 as its NIC type. The below CLI can be used.

```sh
glance image-update --property hw_vif_model=e1000 $IMAGE_UUID
```

### Create management network

The management network and its subnet should be created using the below CLI.

```sh
neutron net-create vapv_mgmt_net
neutron subnet-create --name vapv_mgmt_subnet --gateway 192.168.101.1 --enable-dhcp --ip-version 4 vapv_mgmt_net 192.168.101.0/24
```

Note: When creating loadbalancer, the customer CANNOT choose the subnet from the network named vapv\_mgmt\_net

### Create flavor for created vAPV

The flavor should be created using the below CLI.

```sh
openstack flavor create --vcpus 2 --ram 4096 --disk 42 xxx
```

## Deployment

### Generate the configuration file

Run the below CLI to generate the configuration file.

```sh
array_lbaas_config_generator /etc/neutron/conf.d/neutron-server/array_vapv_lbaas.conf
```

Note:

* In choose "Which deployment model do you wish to use?", it should choose 2 for now(A vTM per subnet)
* In choose "How should vTMs be deployed?", it should choose 1 for now(As single instances)
* In choose "What is the Service Endpoint Address of your Services Director cluster?", you can fill any address such as 2.2.2.2 for now.
* In choose "Enable per-tenant configuration customizations database?", you can choose 2 (No) for now.
* In choose "How much bandwidth (Mbps) should each vAPV be allocated?", you can fill any value for now, still need be implemented.
* In choose "Which management mode should be used?", it should choose 1(Dedicated management network) for now.

The below shows the configuration steps:

```sh
Which deployment model do you wish to use?
	1) A vAPV per tenant
	2) A vAPV per subnet
	3) A vAPV per loadbalancer object (VIP)
Please enter your choice [1-3]: 2

How should vAPVs be deployed?
	1) As single instances
	2) As HA pairs
Please enter your choice [1-2]: 1

What MTU should be used by the vAPV network interfaces?
	1) 1500 (local/flat/VLAN)
	2) 1476 (GRE)
	3) 1450 (VXLAN)
	4) Custom
Please enter your choice [1-4]: 3

What is the Service Endpoint Address of your Services Director cluster?
Input: 2.2.2.2

What is the Glance ID of the vAPV image to use?
Input: your_uuid_vapv

What is the Nova ID of the flavor to use for vAPVs? (must be at least 2 vCPU/4GB RAM/42GB disk)
Input: xxxxxxx

Which management mode should be used?
	1) Dedicated management network
	2) Floating IP addresses
Please enter your choice [1-2]: 1

What is the Neutron ID of the management subnet?
Input: xxxxx

How much bandwidth (Mbps) should each vAPV be allocated?
Input: 100

Enable per-tenant configuration customizations database?
	1) Yes
	2) No
Please enter your choice [1-2]: 2

Should HTTPS off-load be supported? (Select 2 if Barbican is not available)?
	1) Yes
	2) No
Please enter your choice [1-2]: 2

Which TCP port does the vAPV REST API listen on?
Input (Default=9997):

What is the username for the OpenStack admin user?
Input (Default=admin):

What is the password for the OpenStack admin user?
Input (hidden):

What is the project id for admin user?
Input: 2ceaec5956e548359c05ba7c17720a5d

What is the username for the OpenStack lbaas user?
Input (Default=admin):

What is the password for the OpenStack lbaas user?
Input (hidden):

What is the project id for lbaas user?
Input: 2ceaec5956e548359c05ba7c17720a5d

Which Keystone version should be used?
	1) v2
	2) v3
Please enter your choice [1-2]: 2

```

### Generate the array DB

Run the below CLI to generate the array DB required by the driver in neutron database.

```sh
array_lbaas_init_db initialize --db=$DB_PATH
```

Note:

The DB\_PATH can be found in neutron configuration file(connection section in database). It must be in the following format:

<DB_TYPE>://<USERNAME>:<PASSWORD>@<DB_HOST>/<DB_NAME>

Eg.

mysql://root:P@ssword1@localhost/neutron

### Enable the LBaaS v2

* Navigate to neutron configuration file (such as /etc/neutron/neutron.conf), and set the “service\_plugins” section as follows:

```sh
service_plugins=router,neutron_lbaas.services.loadbalancer.plugin.LoadBalancerPluginv2
```

* Navigate to neutron LBAAS configuration file (such as /etc/neutron/neutron\_lbaas.conf) on the OpenStack controller node, and set the “service\_provider” section to enable the load balancing function:

```sh
service_provider = LOADBALANCERV2:arrayvapv:array_neutron_lbaas.driver.driver_v2.ArrayLoadBalancerDriver:default
```

### Create the device for management network

Run the below CLI to create the device for management network.

```sh
array_lbaas_init_network <mgmt_network> <mgmt_subnet> [keystonerc admin file]
```

For example:

```sh
array_lbaas_init_network vapv_mgmt_net vapv_mgmt_subnet /root/keystonerc_admin
```

Note: After rebooting the network node, the script should be run again.

