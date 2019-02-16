# How to deploy vAPV driver

## Prerequisites

### Install LBaaS driver

The driver should be installed in network node.

If the based OS is centos 7.x, you can install the driver RPM packagesusing the below CLI.

```sh
rpm -Uvh array-lbaasv2-vapv-1.0.0-1.el7.noarch.rpm
```

If not, you can use source code to install the package using the below CLI:

```sh
python setup.py install
```

Note: Before install, you should install the below packages:

* openstack-neutron-lbaas
* python-neutron-lbaas

### Upload the vAPV image to OpenStack

The image can be uploaded using the below CLI:

```sh
openstack image create --container-format bare –disk-format qcow2 --public --file $IMAGE_PATH vapv
```

Note: As a workaround, we should use e1000 as its NIC type. The below CLI can be used.

```sh
glance image-update --property hw_vif_model=e1000 vapv
```

### Create management network

The management network and its subnet should be created using the below CLI.

```sh
neutron net-create vapv_mgmt_net
neutron subnet-create --name vapv_mgmt_subnet --gateway 192.168.101.1 --enable-dhcp --ip-version 4 vapv_mgmt_net 192.168.101.0/24
```

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

* In choose "Which deployment model do you wish to use?", it should choose 2(A vTM per subnet)
* In choose "How should vTMs be deployed?", it should choose 1(As single instances)

### Generate the array DB

Run the below CLI to generate the array DB required by the driver in neutron database.

```sh
array_lbaas_init_db initialize --db=$DB_PATH
```

Note:

The DB\_PATH can be found in /etc/neutron/neutron.conf(connection section in database)

### Enable the LBaaS v2

* Navigate to “/etc/neutron/neutron.conf” directory, and set the “service\_plugins” section as follows:

```sh
service_plugins =router,neutron_lbaas.services.loadbalancer.plugin.LoadBalancerPluginv2
```

* Navigate to “/etc/neutron/neutron\_lbaas.conf” file on the OpenStack controller node, and set the “service\_provider” section to enable the load balancing function:

```sh
service_provider = LOADBALANCERV2:arrayvapv:array_neutron_lbaas.driver.driver_v2.ArrayLoadBalancerDriver:default
```

### Create the device for management network

Run the below CLI to create the device for management network.

```sh
array_lbaas_init_network <mgmt_network> <mgmt_subnet> [keystonerc admin file]
```

Note: After rebooting the network node, the script should be run again.

