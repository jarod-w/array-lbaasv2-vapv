#!/usr/bin/env python

from setuptools import setup, find_packages
import os
import shutil
from subprocess import check_output

setup(
    name="array_neutron_lbaas",
    description="Array vADC OpenStack Neutron LBaaS Device Driver",
    long_description=open("README.md").read(),
    version="1.0.0",
    url="https://www.arraynetworks.com.cn",
    packages=find_packages(),
    scripts=[
        "scripts/array_lbaas_config_generator",
        "scripts/array_lbaas_init_db",
        "scripts/array_lbaas_init_network",
        "scripts/array_lbaas_tenant_customization"
    ],
    data_files=[
        ("/etc/neutron/conf.d/neutron-server", ["conf/array_vapv_lbaas.conf"]),
        ("/etc/dhcp/octavia/", ["conf/dhclient.conf"])
    ],
    license="Apache Software License",
    platforms=["Linux"],
    classifiers=[
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "Environment :: OpenStack",
        "License :: OSI Approved :: Apache Software License"
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7"
    ]
)
