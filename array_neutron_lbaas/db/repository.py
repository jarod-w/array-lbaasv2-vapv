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

import models

class BaseRepository(object):
    model_class = None

    def create(self, session, **model_kwargs):
        """Base create method for a database entity.

        :param session: A Sql Alchemy database session.
        :param model_kwargs: Attributes of the model to insert.
        :returns: octavia.common.data_model
        """
        with session.begin(subtransactions=True):
            model = self.model_class(**model_kwargs)
            session.add(model)
        return model.to_dict()

    def delete(self, session, **filters):
        """Deletes an entity from the database.

        :param session: A Sql Alchemy database session.
        :param filters: Filters to decide which entity should be deleted.
        :returns: None
        :raises: sqlalchemy.orm.exc.NoResultFound
        """
        model = session.query(self.model_class).filter_by(**filters).one()
        with session.begin(subtransactions=True):
            session.delete(model)
            session.flush()

    def delete_batch(self, session, ids=None):
        """Batch deletes by entity ids."""
        ids = ids or []
        for id in ids:
            self.delete(session, id=id)

    def update(self, session, id, **model_kwargs):
        """Updates an entity in the database.

        :param session: A Sql Alchemy database session.
        :param model_kwargs: Entity attributes that should be updates.
        :returns: octavia.common.data_model
        """
        with session.begin(subtransactions=True):
            session.query(self.model_class).filter_by(
                id=id).update(model_kwargs)

    def get(self, session, **filters):
        """Retrieves an entity from the database.

        :param session: A Sql Alchemy database session.
        :param filters: Filters to decide which entity should be retrieved.
        :returns: octavia.common.data_model
        """
        model = session.query(self.model_class).filter_by(**filters).first()
        if not model:
            return
        return model.to_dict()

    def exists(self, session, id):
        """Determines whether an entity exists in the database by its id.

        :param session: A Sql Alchemy database session.
        :param id: id of entity to check for existence.
        :returns: octavia.common.data_model
        """
        return bool(session.query(self.model_class).filter_by(id=id).first())


class ArrayAmphoraRepository(BaseRepository):
    model_class = models.ArrayAmphora

    def get_vapv_by_hostname(self, session, hostname):
        vapv = session.query(self.model_class).filter_by(hostname=hostname).first()
        if vapv:
            return vapv.to_dict()
        return None

    def increment_inuselb(self, session, hostname):
        vapv = session.query(self.model_class).filter_by(hostname=hostname).first()
        if vapv:
            (vapv.in_use_lb) = (vapv.in_use_lb) + 1
            return vapv.in_use_lb
        return -1

    def decrement_inuselb(self, session, hostname):
        vapv = session.query(self.model_class).filter_by(hostname=hostname).first()
        if vapv:
            (vapv.in_use_lb) = (vapv.in_use_lb) - 1
            return vapv.in_use_lb
        return -1

    def get_inuselb_by_hostname(self, session, hostname):
        vapv = session.query(self.model_class).filter_by(hostname=hostname).first()
        if vapv:
            return vapv.in_use_lb
        return -1
