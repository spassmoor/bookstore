#!/usr/bin/env python

# -*- coding: utf-8 -*-

"""
A notebook manager that uses OpenStack Swift object storage.

Authors:

* Kyle Kelley
"""

#-----------------------------------------------------------------------------
# Copyright (C) 2013 Rackspace
#
# Distributed under the terms of the Apache 2.0 License. The full license is in
# the file LICENSE, distributed as part of this software.
#-----------------------------------------------------------------------------

import datetime

import pyrax
from pyrax.exceptions import NoSuchContainer as NoSuchContainer

from tornado import web

from IPython.html.services.notebooks.nbmanager import NotebookManager
from IPython.nbformat import current
from IPython.utils.traitlets import Unicode, Instance
from IPython.utils import tz

class OpenStackNotebookManager(NotebookManager):

    account_name = Unicode('', config=True, help='OpenStack account name.')
    account_key = Unicode('', config=True, help='OpenStack account key.')
    identity_type = Unicode('', config=True, help='OpenStack Identity type (e.g. rackspace or openstack)')
    container_name = Unicode('', config=True, help='Container name for notebooks.')

    def __init__(self, **kwargs):
        super(OpenStackNotebookManager, self).__init__(**kwargs)
        pyrax.set_setting("identity_type", self.identity_type)
        pyrax.set_credentials(username=self.account_name, api_key=self.account_key)

        # Set the region, optionally
        # pyrax.set_setting("region", region) # e.g. "LON"

        self.cf = pyrax.cloudfiles

        try:
            self.container = self.cf.get_container(self.container_name)
        except NoSuchContainer:
            self.container = self.cf.create_container(self.container_name)


    def load_notebook_names(self):
        """On startup load the notebook ids and names from OpenStack Swift.

        The object names are the notebook ids and the notebook names are stored
        as object metadata.
        """
        # Cached version of the mapping of notebook IDs to notebook names
        self.mapping = {}

        objects = self.container.get_objects()

        for obj in objects:
            nb_id = obj.name
            metadata = obj.get_metadata()

            name = metadata['x-object-meta-nbname']
            self.mapping[nb_id] = name

    def list_notebooks(self):
        """List all notebooks in the container.

        This version uses `self.mapping` as the authoritative notebook list.
        """
        data = [dict(notebook_id=nb_id,name=name) for nb_id, name in self.mapping.items()]
        data = sorted(data, key=lambda item: item['name'])
        return data

    def read_notebook_object(self, notebook_id):
        """Get the object representation of a notebook by notebook_id."""
        if not self.notebook_exists(notebook_id):
            raise web.HTTPError(404, u'Notebook does not exist: %s' % notebook_id)
        try:
            obj = self.container.get_object(notebook_id)
            s = obj.get() # Read the file into s
        except:
            raise web.HTTPError(500, u'Notebook cannot be read.')
        try:
            nb = current.reads(s, u'json')
        except:
            raise web.HTTPError(500, u'Unreadable JSON notebook.')
        # Todo: The last modified should actually be saved in the notebook document.
        # We are just using the current datetime until that is implemented.
        last_modified = tz.utcnow()
        return last_modified, nb

    def write_notebook_object(self, nb, notebook_id=None):
        """Save an existing notebook object by notebook_id."""

        try:
            new_name = nb.metadata.name
        except AttributeError:
            raise web.HTTPError(400, u'Missing notebook name')

        if notebook_id is None:
            notebook_id = self.new_notebook_id(new_name)

        if notebook_id not in self.mapping:
            raise web.HTTPError(404, u'Notebook does not exist: %s' % notebook_id)

        try:
            data = current.writes(nb, u'json')
        except Exception as e:
            raise web.HTTPError(400, u'Unexpected error while saving notebook: %s' % e)

        metadata = {'x-object-meta-nbname': new_name}
        try:
            obj = self.container.store_object(notebook_id, data)
            obj.set_metadata(metadata)
        except Exception as e:
            raise web.HTTPError(400, u'Unexpected error while saving notebook: %s' % e)

        self.mapping[notebook_id] = new_name
        return notebook_id

    def delete_notebook(self, notebook_id):
        """Delete notebook by notebook_id."""
        if not self.notebook_exists(notebook_id):
            raise web.HTTPError(404, u'Notebook does not exist: %s' % notebook_id)
        try:
            self.container.delete_object(notebook_id)
        except Exception as e:
            raise web.HTTPError(400, u'Unexpected error while deleting notebook: %s' % e)
        else:
            self.delete_notebook_id(notebook_id)


    # Checkpoint-related

    def create_checkpoint(self, notebook_id):
        """Create a checkpoint of the current state of a notebook

        Returns a checkpoint_id for the new checkpoint.
        """
        raise web.HTTPError(405, "Checkpoints not implemented")

    def list_checkpoints(self, notebook_id):
        """Return a list of checkpoints for a given notebook"""
        raise web.HTTPError(405, "Checkpoints not implemented")

    def restore_checkpoint(self, notebook_id, checkpoint_id):
        """Restore a notebook from one of its checkpoints"""
        raise web.HTTPError(405, "Checkpoints not implemented")

    def delete_checkpoint(self, notebook_id, checkpoint_id):
        """delete a checkpoint for a notebook"""
        raise web.HTTPError(405, "Checkpoints not implemented")

    def info_string(self):
        info = "Serving notebooks from OpenStack Swift storage: {},{}"
        return info.format(self.account_name, self.container_name)

