# How to Deploy Array vAPV LBaaS Integration Solution?

Array vAPV LBaaS integration solution enables OpenStack cloud providers to provision load balance services to their tenants by collaborating Array vAPV instances with the OpenStack LBaaS framework.

This document will guide you through the deployment of the Array vAPV LBaaS integration solution.

## 1. Introduction

Array vAPV LBaaS integration solution is comprised by the following parts:

* OpenStack environment with OpenStack LBaaS v2 framework
* vAPV LBaaS driver: responsible for converting LB-related OpenStack API requests into RESTful API requests sent to vAPV instances.
* vAPV instances: will be created per demand and provide load balance services to tenants.


## 2. Deployment

The vAPV LBaaS driver supports OpenStack Kilo and later versions with the OpenStack LBaaS v2 framework. Before deployment, please ensure that the OpenStack environment including the OpenStack LBaaS v2 framework has been well prepared.

The deployment of the Array vAPV LBaaS integration solution can be divided into serveral steps:

1. Upload the vAPV image to OpenStack.
2. Create a flavor used to create vAPV instances.
3. Create a management network for vAPV instances to create.
4. Install the vAPV LBaaS driver on the OpenStack network node.
5. Generate the vAPV LBaaS configuration file.
6. Generate the Array database table in the neutron database.
7. Enable the LBaaS v2 service.
8. Create the device for the management network of vAPV instances.

### 2.1 Upload the vAPV image to OpenStack

To provision load balance services for teneants through Array vAPV instances, OpenStack admin needs to upload the vAPV image to OpenStack.

To upload the vAPV image to OpenStack, follow these steps:

1. Contact Array Networks Customer Support to obtain the vAPV image for OpenStack and save it in a directory on the OpenStack client.
2. Create the vAPV image on by executing the "**openstack image create**" command through the OpenStack command-line client. For example:

```sh
openstack image create --public --disk-format qcow2 --container-format bare --file $IMAGE_PATH vapv
```

Note:

* "$IMAGE\_PATH" should be replaced by the real directory where the vAPV image is saved.
* Currently, the virtio-type NIC does not work very well with the vAPV image. As a workaround, you can change the NIC type that the vAPV image supports to e1000 by executing the "glance image-update" command. For example:

```sh
glance image-update --property hw_vif_model=e1000 $IMAGE_UUID
```

### 2.2 Create the Flavor Used to Create vAPV Instance

In OpenStack, flavors define the compute, memory, and storage capacity of nova computing instances (such as vAPV instances). Therefore, OpenStack admin should create a flavor used to create vAPV instances in advance.

To create a flavor,  execute the "**openstack flavor create**" command through the OpenStack command-line client. For example:

```sh
openstack flavor create --vcpus 2 --ram 4096 --disk 42 xxx
```

Note: The flavor used to create vAPV instances should have at least 2 vCPUs, 4GB memory and 42GB disk.

### 2.3 Create a Management Network for vAPV Instances to Create

To allow vAPV instances to be managed, we should attach these instances to a management network. Then, the vAPV LBaaS driver can discover these vAPV instances through this management network.

To create a management network, follow these steps:

1. Create a management network using the "**neutron net-create**" command through the OpenStack command-line client. For example:

```sh
neutron net-create vapv_mgmt_net
```

2. Create a subnet for the management network using the "**neutron subnet-create**" command through the OpenStack command-line client. For example:

```sh
neutron subnet-create --name vapv_mgmt_subnet --gateway 192.168.101.1 --enable-dhcp --ip-version 4 vapv_mgmt_net 192.168.101.0/24
```

Note: When creating load balancers, customers must choose a subnet other than the management subnet of vAPV instances.

### 2.4 Install the vAPV LBaaS Driver on the OpenStack Network Node

The vAPV LBaaS driver supports two installation methods:

* Install it from a RPM package
* Install it from source codes

If the based OS is CentOS 7.x, you can install the vAPV LBaaS driver from an RPM installation package. Otherwise, you can install the driver from a source code installation package.

#### 2.4.1 Install the vAPV LBaaS Driver from an RPM Package

1. Contact Array Networks Customer Support to obtain the RPM installation package of the driver and upload it to a directory of the network node.
2. Log into the network node as a root user, navigate to this directory, and execute the "rpm" command to execute the RMP package to install the driver. For example

```sh
rpm -Uvh array-lbaasv2-vapv-1.0.0-1.el7.noarch.rpm
```

#### 2.4.2 Install the vAPV LBaaS Driver from Source Codes

1. Contact Array Networks Customer Support to obtain the source code installation package of the driver and upload it to a directory of the network node.
2. Log into the network node as a root user, navigate to this directory, and run the “tar” command to decompress the package.

```sh
tar zxvf array-lbaasv2-vapv.xxxxxxxx.tar.gz
```

3. Navigate to the compressed directory and execute the "python" command to install the driver from source codes.

```sh
python setup.py install
```

### 2.5 Generate the vAPV LBaaS Configuration File

The configuration file contains all the information required for the vAPV LBaaS driver to deploy and manage vAPV instances.

To generate the vAPV LBaaS configuration file, log into the network node as a root user and execute the "**array_lbaas_config_generator**" script to generate the configuration file by answering the step-by-step questions. For example:
```sh
array_lbaas_config_generator /etc/neutron/conf.d/neutron-server/array_vapv_lbaas.conf
```

Following is an example of the step-by-step questions:

```sh
Which deployment model do you wish to use?
	1) A vAPV instance per tenant
	2) A vAPV instance per subnet
	3) A vAPV instance per load balancer object (VIP)
Please enter your choice [1-3]: 2

How should vAPV instances be deployed?
	1) As single instances
	2) As HA pairs
Please enter your choice [1-2]: 1

What MTU should be used by the vAPV instance’s network interfaces?
	1) 1500 (local/flat/VLAN)
	2) 1476 (GRE)
	3) 1450 (VXLAN)
	4) Custom
Please enter your choice [1-4]: 3

What is the Glance ID of the vAPV image to use?
Input: uuid_vapv_image

What is the Nova ID of the flavor used to create vAPV instances?
Input: xxxxxxx

Which management mode should be used?
	1) Dedicated management network
	2) Floating IP addresses
Please enter your choice [1-2]: 1

What is the license server address of vAPV instances?
Input: 2.2.2.2

What is the Neutron ID of the management subnet?
Input: xxxxx

How much bandwidth (Mbps) should each vAPV instance be allocated?
Input: 100

Whether to enable per-tenant database configuration customization?
	1) Yes
	2) No
Please enter your choice [1-2]: 2

Should HTTPS offload be supported? (Select 2 if Barbican is unavailable)?
	1) Yes
	2) No
Please enter your choice [1-2]: 2

Which TCP port does the vAPV REST API listen on?
Input (Default=9997):

What is the username of the OpenStack admin user?
Input (Default=admin):

What is the password of the OpenStack admin user?
Input (hidden):

What is the project ID of the OpenStack admin user?
Input: 2ceaec5956e548359c05ba7c17720a5d

What is the username of the OpenStack LBaaS user?
Input (Default=admin):

What is the password of the OpenStack LBaaS user?
Input (hidden):

What is the project ID of the OpenStack LBaaS user?
Input: 2ceaec5956e548359c05ba7c17720a5d

Which Keystone version should be used?
	1) v2
	2) v3
Please enter your choice [1-2]: 2
```

Note:

* For question "Which deployment model do you wish to use?", only option 2 (A vAPV instance per subnet) is supported for now.
* For question "How should vAPV instances be deployed?", only option 1 (As single instances) is supported for now.
* For question "Which management mode should be used?", only option 1 (Dedicated management network) is supported for now.
* For question "What is the license server address of vAPV instances?", this function is not implemented yet and you can fill any address for now, such as 2.2.2.2.
* For question "How much bandwidth (Mbps) should each vAPV instance be allocated?", this function is not implemented yet and you can fill any you can fill any value for now.
* For question "Whether to enable per-tenant database configuration customization?", only option 2 (No) is supported for now.

### 2.6 Generate the Array Database Table in the Neutron Database

Array database table is a new table added to the Neutron database. It will store the information about all created vAPV instances for the vAPV LBaaS driver.

To generate the Array database table in the neutron database, log into the network node as a root user and execute the following command:

```sh
array_lbaas_init_db initialize --db=$DB_PATH
```

Note:

* The "$DB_PATH" can be found in the neutron configuration file (connection section in database). It must be in the following format: 

```sh
<DB_TYPE>://<USERNAME>:<PASSWORD>@<DB_HOST>/<DB_NAME>
```

For example:

```sh
mysql://root:P@ssword1@localhost/neutron
```

### 2.7 Enable the LBaaS v2 Service

1.  Log into the network node as a root user, open the neutron configuration file (such as /etc/neutron/neutron.conf), and set the “service\_plugins” section as follows:

```sh
service_plugins=router,neutron_lbaas.services.loadbalancer.plugin.LoadBalancerPluginv2
```

2. Open the neutron LBaaS configuration file (such as /etc/neutron/neutron\_lbaas.conf), and set the “service\_provider” section as follows to enable the load balancing function:

```sh
service_provider = LOADBALANCERV2:arrayvapv:array_neutron_lbaas.driver.driver_v2.ArrayLoadBalancerDriver:default
```

3. Execute the following command to restart the Neutron server.

```sh
systemctl restart neutron-server
```

### 2.8 Create the Device for the Management Network of vAPV Instances

To ensure that the management network is reachable to the vAPV LBaaS driver, you should create a device for the management network of vAPV instances.

To create a device for the management network of vAPV instances, log into the network node as a root user and execute the "**array_lbaas_init_network** *<mgmt_network> <mgmt_subnet> [keystonerc admin file]*"  command. For example:

```sh
array_lbaas_init_network vapv_mgmt_net vapv_mgmt_subnet /root/keystonerc_admin
```

Note: Everytime the network node is restarted, this command should be executed again.

## 3. Load Balance Service Provision for Tenants

After the vAPV LBaaS intergration has been deployed successfuly, OpenStack providers can allow their tenants to rent load balance services.

The process of provisioning load balance services to tenants is as follows:

1. Tenants connect to the OpenStack management system through dashboard or CLI.
2. Tenants create load balaners and configure the LBaaS service for their virtual application servers (listener, pool, health monitor and members).
3. The vAPV LBaaS driver converts the OpenStack API requests of tenants into RESTful API requests.
4. OpenStack automatically create vAPV instances on compute nodes and start them.
5. vAPV instances process the RESTful API requests and add the load balance configration.

Till now, the load balancers created by tenants are ready to provide load balance services.

To create a load balaner and configure the LBaaS service, tenants should follow these steps:

1. Create a load balancer by executing the "**neutron lbaas-loadbalancer-create**" command. For example:

```sh
neutron lbaas-loadbalancer-create –name lbv1 lb_subnet
```

2.	Create a listener by executing the "neutron lbaas-listener-create" command. For example:

```sh
neutron lbaas-listener-create --name lsv1 --loadbalancer lbv1 --protocol TCP --protocol-port 80
```

3.	Create a pool by executing the  "neutron lbaas-pool-create" command. For example:

```sh
neutron lbaas-pool-create --lb-algorithm ROUND_ROBIN --listener lsv1 --protocol TCP
```

4.	Add members to the poot by execurting the "neutron lbaas-member-create" command. For example:

```sh
neutron lbaas-member-create --address 192.168.11.14 --protocol-port 80 pool-1
neutron lbaas-member-create --address 192.168.11.15 --protocol-port 80 pool-1
```

5.	Add a health monitor for the pool by executing "neutron lbaas-healthmonitor-create" command. For example:

```sh
neutron lbaas-healthmonitor-create --delay 10 --timeout 5 --max-retries 3 --type PING --pool poov1
```
