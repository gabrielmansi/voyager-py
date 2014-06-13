# (C) Copyright 2014 Voyager Search
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import sys
import json
import datetime
import copy
import pyodbc
try:
    try:
        import zmq
    except ImportError:
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'arch', 'win32_x86', 'py', 'pyzmq-14.3.0-py2.7-win32.egg')))
        import zmq
except ImportError as ie:
    sys.stdout.write(repr(ie))
    sys.exit(1)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            encoded_object = list(obj.timetuple())[0:6]
        else:
            encoded_object = json.JSONEncoder.default(self, obj)
        return encoded_object

class Job(object):
    def __init__(self, job_file):
        self.job_file = job_file
        self.job = json.load(open(job_file, 'r'))
        self.db_connection = None
        self.db_cursor = None
        self.db_query = None
        self.zmq_socket = None

    def __del__(self):
        """Close open connections, streams, etc. after all references to Job are deleted."""
        if self.zmq_socket:
            self.zmq_socket.close()
        if self.db_connection:
            self.db_connection.close()

    @property
    def fields_to_keep(self):
        """List of fields to keep (may include wild card)."""
        try:
            return self.job['location']['config']['fields']['include']
        except KeyError:
            return ['*']

    @property
    def fields_to_skip(self):
        """List of fields to skip (may include a wild card)."""
        try:
            return self.job['location']['config']['fields']['exclude']
        except KeyError:
            return None

    @property
    def field_mapping(self):
        """Field mapping as key, value pairs."""
        try:
            return self.job['location']['config']['fields']['mapping']
        except KeyError:
            return None

    @property
    def default_mapping(self):
        """Default prefix name to append to each field."""
        try:
            return self.job['location']['config']['fields']['map_default_prefix']
        except KeyError:
            return None

    @property
    def tables_to_keep(self):
        """List of tables to keep (may include wild card)."""
        try:
            return self.job['location']['config']['tables']['include']
        except KeyError:
            return ['*']

    @property
    def tables_to_skip(self):
        """List of tables to skip (may include a wild card)."""
        try:
            return self.job['location']['config']['tables']['exclude']
        except KeyError:
            return None

    @property
    def action_type(self):
        """The action type."""
        return 'ADD'

    @property
    def location_id(self):
        """The location ID"""
        return self.job['location']['id']

    @property
    def path(self):
        """Catalog path for esri data types."""
        try:
            return self.job['location']['config']['path']
        except KeyError:
            return ''

    @property
    def url(self):
        """URL for GDAL/OGR dataset."""
        try:
            return self.job['location']['config']['url']
        except KeyError:
            return ''

    @property
    def sql_driver(self):
        try:
            return self.job['location']['config']['sql']['connection']['driver']
        except KeyError:
            return None

    @property
    def sql_connection_info(self):
        """SQL connection information as key, value pairs."""
        try:
            return self.job['location']['config']['sql']
        except KeyError:
            return None

    @property
    def sql_query(self):
        """A SQL query"""
        try:
            return self.job['location']['config']['sql']['query']
        except KeyError:
            return None

    @property
    def sql_schema(self):
        """Returns the database schema."""
        return self.job['location']['config']['sql']['connection']['schema']

    def map_fields(self, table_name, field_names):
        """Returns mapped field names. Order matters."""
        mapped_field_names = copy.copy(field_names)
        default_map = self.default_mapping

        if self.field_mapping:
            for mapping in self.field_mapping:
                if mapping['table'] == '*':
                    fmap = mapping['map']
                elif mapping['table'].lower() == table_name.lower():
                    mapped_field_names = copy.copy(field_names)
                    fmap = mapping['map']
                else:
                    return mapped_field_names
                for i, field in enumerate(mapped_field_names):
                    try:
                        mapped_field_names[i] = fmap[field]
                    except KeyError:
                        if default_map:
                            mapped_field_names[i] = '{0}{1}'.format(default_map, field)
        elif self.default_mapping:
            for i, field in enumerate(mapped_field_names):
                mapped_field_names[i] = '{0}{1}'.format(default_map, field)
        else:
            return mapped_field_names

        return mapped_field_names

    def connect_to_database(self):
        """Makes an ODBC database connection."""
        drvr = self.sql_connection_info['connection']['driver']
        srvr = self.sql_connection_info['connection']['server']
        db = self.sql_connection_info['connection']['database']
        un = self.sql_connection_info['connection']['uid']
        pw = self.sql_connection_info['connection']['pwd']
        self.db_connection = pyodbc.connect("DRIVER={0};SERVER={1};DATABASE={2};UID={3};PWD={4}".format(drvr, srvr, db, un, pw))
        self.db_cursor = self.db_connection.cursor()

    def execute_query(self, query):
        """Execute the SQL query and return a new cursor object."""
        return self.db_cursor.execute(query)

    def connect_to_zmq(self):
        """Connect to zmq instance."""
        try:
            self.zmq_socket = zmq.Context.instance().socket(zmq.PUSH)
            self.zmq_socket.connect(self.job['connection']['indexer'])
        except Exception as ex:
            sys.stdout.write(repr(ex))
            sys.exit(1)

    def send_entry(self, entry):
        """Sends an entry to be indexed using pyzmq."""
        self.zmq_socket.send_json(entry, cls=DateTimeEncoder)

    def search_fields(self, dataset):
        """Returns a valid list of existing fields for the search cursor."""
        import arcpy
        fields = []
        if not self.fields_to_keep == ['*']:
            for fld in self.fields_to_keep:
                [fields.append(f.name) for f in arcpy.ListFields(dataset, fld)]
        if self.fields_to_skip:
            for fld in self.fields_to_skip:
                [fields.remove(f.name) for f in arcpy.ListFields(dataset, fld)]
            return fields
        else:
            return [f.name for f in arcpy.ListFields(dataset)]