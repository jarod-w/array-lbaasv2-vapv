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

from neutron.db import models_v2
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa

BaseTable = declarative_base()

class ArrayAmphora(BaseTable, models_v2.HasId, models_v2.HasTenant):
    """Represents an Array load balancer."""

    __tablename__ = "array_amphora"

    in_use_lb = sa.Column(sa.Integer(), nullable=False)
    subnet_id = sa.Column(sa.String(36), nullable=False)
    pri_mgmt_address = sa.Column(sa.String(64), nullable=True)
    sec_mgmt_address = sa.Column(sa.String(64), nullable=True)
    hostname = sa.Column(sa.String(64), nullable=True)

    def to_dict(self, **kwargs):
        ret = {}
        for attr in self.__dict__:
            if attr.startswith('_') or not kwargs.get(attr, True):
                continue
            if isinstance(getattr(self, attr), list):
                ret[attr] = []
                for item in self.__dict__[attr]:
                    ret[attr] = item
            elif isinstance(self.__dict__[attr], unicode):
                ret[attr.encode('utf8')] = self.__dict__[attr].encode('utf8')
            else:
                ret[attr] = self.__dict__[attr]
        return ret

    def from_dict(cls, model_dict):
        return cls(**model_dict)


