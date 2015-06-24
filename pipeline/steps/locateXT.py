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
import csv
import sys
import json
import subprocess
from copy import deepcopy
from collections import defaultdict


def run(entry):
    """Extracts coordinates from the given entry and returns a new entry with coordinate information.
    :param entry: a file containing the entry information
    """
    orig_entry = json.load(open(entry, "rb"))
    new_entry = deepcopy(orig_entry)
    if 'fields' in orig_entry and 'text' in orig_entry['fields']:
        text_field = orig_entry['fields']['text']
        try:
            command = 'C:/Program Files (x86)/ClearTerra/License Server/LocateXT_API_CLI32.exe -t "{0}"'.format(''.join(text_field))
        except UnicodeEncodeError:
            command = 'C:/Program Files (x86)/ClearTerra/License Server/LocateXT_API_CLI32.exe -t "{0}"'.format(text_field.encode(orig_entry['fields']['contentEncoding']))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=134217728)
        process.wait()
        if process.returncode in (1, -1):
            command = 'C:/Program Files (x86)/ClearTerra/License Server/LocateXT_API_CLI32.exe "{0}"'.format(entry)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=134217728)
            process.wait()
            if process.returncode in (1, -1):
                sys.stderr.write('FAILED. {0}'.format(process.stderr.read()))
                return new_entry
        columns = defaultdict(list)
        reader = csv.DictReader(process.stdout.read().splitlines())
        for row in reader:
            for (k,v) in row.items():
                columns[k].append(v)
        y_coordinates = columns['Latitude (WGS-84)']
        x_coordinates = columns['Longitude (WGS-84)']
        if len(x_coordinates) > 1:
            # Make a Multipoint WKT.
            coordinates = zip(x_coordinates, y_coordinates)
            points = (' '.join(str(round(float(c), 3)) for c in pt) for pt in coordinates)
            points = ('({0})'.format(pt) for pt in points)
            wkt_multipoint = 'MULTIPOINT ({0})'.format(', '.join(points))
            geo = {}
            geo['wkt'] = wkt_multipoint
            new_entry['geo'] = geo
        else:
            # Make single point.
            wkt_point = 'POINT ({0} {1})'.format(x_coordinates[0], y_coordinates[0])
            geo = {}
            geo['wkt'] = wkt_point
            new_entry['geo'] = geo

        new_entry['fields']['fs_processed_by'] = 'LocateXT'
        sys.stdout.write(json.dumps(new_entry, ensure_ascii=True))
        sys.stdout.flush()
    else:
        sys.stderr.write("No text to process for: {0}".format(orig_entry['fields']['id']))
        sys.stderr.flush()
        return
