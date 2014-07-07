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
import decimal
import json
import base_job


class ComplexEncoder(json.JSONEncoder):
    """To handle decimal types for json encoding."""
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def global_job(args):
    """Create a global job object for multiprocessing."""
    global job
    job = args


def worker():
    """Worker function to index each row in each table in the database."""
    job.connect_to_zmq()
    job.connect_to_database()
    #job.db_cursor.execute("select name from sysobjects where type='U'")
    tables = []
    if not job.tables_to_keep == ['*']:
        for tk in job.tables_to_keep:
            #tcur = job.db_cursor.execute("select * from sys.objects where name like '{0}'".format(tk))
            [tables.append(t[0]) for t in job.db_cursor.execute("select * from sys.objects where name like '{0}'".format(tk)).fetchall()]
        #tables = [t[0] for t in job.db_cursor.fetchall() if t[0] in job.tables_to_keep]
    else:
        [tables.append(t[0]) for t in job.db_cursor.execute("select name from sysobjects where type='U'").fetchall()]
        #tables = [t[0] for t in job.db_cursor.fetchall()]

    for tbl in set(tables):
        geo = {}
        has_shape = False

        query = job.get_table_query(tbl)
        constraint = job.get_table_constraint(tbl)
        if query and constraint:
            expression = """{0} AND {1}""".format(query, constraint)
        else:
            if query:
                expression = query
            else:
                expression = constraint

        if not job.fields_to_keep == '*':
            columns = []
            for col in job.fields_to_keep:
                qry = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE table_name = '{0}' AND column_name LIKE '{1}'".format(tbl, col)
                [columns.append(c[0]) for c in job.execute_query(qry).fetchall()]
        else:
            columns = [c.column_name for c in job.db_cursor.columns(table=tbl).fetchall()]

        if job.fields_to_skip:
            for col in job.fields_to_skip:
                qry = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE table_name = '{0}' AND column_name LIKE '{1}'".format(tbl, col)
                [columns.remove(c[0]) for c in job.execute_query(qry).fetchall()]

        if job.field_mapping:
            mapped_cols = job.map_fields(tbl, columns)
        else:
            mapped_cols = columns
        for c in job.db_cursor.columns(table=tbl).fetchall():
            if c.type_name == 'geometry':
                has_shape = True
                srid = job.db_cursor.execute("select {0}.STSrid from {1}".format(c.column_name, tbl)).fetchone()[0]
                geo['code'] = srid
                geom_type = job.db_cursor.execute("select {0}.STGeometryType() from {1}".format(c.column_name, tbl)).fetchone()[0]
                if geom_type == 'Point':
                    is_point = True
                    columns.insert(0, "{0}.STPointN(1).STX".format(c.column_name))
                    columns.insert(0, "{0}.STPointN(1).STY".format(c.column_name))
                else:
                    is_point = False
                    columns.insert(0, "{0}.STEnvelope().STPointN((3)).STY".format(c.column_name))
                    columns.insert(0, "{0}.STEnvelope().STPointN((3)).STX".format(c.column_name))
                    columns.insert(0, "{0}.STEnvelope().STPointN((1)).STY".format(c.column_name))
                    columns.insert(0, "{0}.STEnvelope().STPointN((1)).STX".format(c.column_name))
                break

        if not expression:
            job.db_cursor.execute("select {0} from {1}".format(','.join(columns), tbl))
        else:
            job.db_cursor.execute("select {0} from {1} where {2}".format(','.join(columns), tbl, expression))
        for i, row in enumerate(job.db_cursor.fetchall()):
            entry = {}
            if has_shape:
                if is_point:
                    geo['lon'] = row[1]
                    geo['lat'] = row[0]
                    mapped_cols = dict(zip(mapped_cols, row[2:]))
                else:
                    geo['xmin'] = row[0]
                    geo['ymin'] = row[1]
                    geo['xmax'] = row[2]
                    geo['ymax'] = row[3]
                    mapped_cols  = dict(zip(mapped_cols, row[4:]))
            else:
                mapped_cols = dict(zip(mapped_cols, row))
            try:
                if job.default_mapping:
                    mapped_cols.pop('{0}Shape'.format(job.default_mapping))
                else:
                    mapped_cols.pop('SHAPE')
            except KeyError:
                    pass
            entry['id'] = '{0}_{1}_{2}'.format(job.location_id, tbl, i)
            entry['location'] = job.location_id
            entry['action'] = job.action_type
            entry['entry'] = {'geo': geo, 'fields': mapped_cols}
            job.send_entry(entry)


def assign_job(job_info):
    """Connects to ZMQ, connects to the database, and assigns the job."""
    job = base_job.Job(job_info)
    global_job(job)
    worker()

