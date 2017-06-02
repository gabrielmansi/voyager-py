# (C) Copyright 2016 Voyager Search
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
import uuid
from utils import status
from utils import worker_utils


status_writer = status.Writer()

def run_job(job):
    """Worker function to index each document in each table in the database."""
    job.connect_to_zmq()

    total_items = 1000
    for x in range(1, total_items):
        entry = {}
        entry['location'] = job.location_id
        entry['action'] = job.action_type

        fields = dict()
        # each item must have either an id or a path. 
        fields['id'] = uuid.uuid4().hex
        fields['title'] = 'item {0}'.format(x)
        fields['fss_foo'] = ['foo1', 'foo2']

        entry['entry'] = {
            'fields': fields
        }
        job.send_entry(entry)
        status_writer.send_percent(float(x) / total_items,
                                   '{0}: {1:.2f}%'.format("alex_worker", (x / total_items)*100),
                                   'AlexWorker')
