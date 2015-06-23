# -*- coding: utf-8 -*-
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
import shutil
import subprocess
import urllib2
import tasks
from utils import status
from utils import task_utils


status_writer = status.Writer()


def execute(request):
    """Copies files to a target folder.
    :param request: json as a dict.
    """
    extracted = 0
    skipped = 0
    errors = 0
    parameters = request['params']

    output_type = task_utils.get_parameter_value(parameters, 'output_format', 'value')
    task_folder = os.path.join(request['folder'], 'temp')
    if not os.path.exists(task_folder):
        os.makedirs(task_folder)

    num_results, response_index = task_utils.get_result_count(parameters)
    if num_results > task_utils.CHUNK_SIZE:
        # Query the index for results in groups of 25.
        query_index = task_utils.QueryIndex(parameters[response_index])
        fl = query_index.fl
        query = '{0}{1}{2}'.format(sys.argv[2].split('=')[1], '/select?&wt=json', fl)
        fq = query_index.get_fq()
        if fq:
            groups = task_utils.grouper(range(0, num_results), task_utils.CHUNK_SIZE, '')
            query += fq
        else:
            groups = task_utils.grouper(list(parameters[response_index]['ids']), task_utils.CHUNK_SIZE, '')

        status_writer.send_percent(0.0, _('Starting to process...'), 'copy_files')
        i = 0.
        for group in groups:
            i += len(group) - group.count('')
            if fq:
                results = urllib2.urlopen(query + "&rows={0}&start={1}".format(task_utils.CHUNK_SIZE, group[0]))
            else:
                results = urllib2.urlopen(query + '{0}&ids={1}'.format(fl, ','.join(group)))

            input_items = task_utils.get_input_items(eval(results.read())['response']['docs'])
            result = extract(input_items, output_type)
            extracted += result[0]
            errors += result[1]
            skipped += result[2]
            status_writer.send_percent(i / num_results, '{0}: {1:%}'.format("Processed", i / num_results), 'locate_xt_api')
    else:
        input_items = task_utils.get_input_items(parameters[response_index]['response']['docs'])
        converted, errors, skipped = extract(input_items, output_type, task_folder, show_progress=True)

    try:
        shutil.copy2(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'supportfiles', '_thumb.png'), task_folder)
    except IOError:
        pass

    # Zip up outputs.
    zip_file = task_utils.zip_data(task_folder, 'output.zip')
    shutil.move(zip_file, os.path.join(os.path.dirname(task_folder), os.path.basename(zip_file)))

    # Update state if necessary.
    if errors > 0 or skipped > 0:
        status_writer.send_state(status.STAT_WARNING, _('{0} results could not be processed').format(skipped + errors))
    task_utils.report(os.path.join(task_folder, '_report.json'), extracted, skipped, errors)


def extract(input_items, out_type, output_dir, gaz_file='', fuzzy_level=0, attributes_file='', show_progress=False):
    """Extract geographic information from input items."""
    extracted = 0
    skipped = 0
    errors = 0
    locate_xt_exe = 'C:/Program Files (x86)/ClearTerra/License Server/LocateXT_API_CLI32.exe'

    if show_progress:
        i = 1.
        file_count = len(input_items)
        status_writer.send_percent(0.0, _('Starting to process...'), 'locate_xt')

    for src_file in input_items:
        try:
            if os.path.isfile(src_file):
                if out_type == 'CSV':
                    if gaz_file:
                        command = '{0} "{1}" -g "{2}" -e {3}'.format(locate_xt_exe, src_file, gaz_file, fuzzy_level)
                    elif gaz_file and attributes_file:
                        command = '{0} "{1}" -g "{2}" -e {3} -c "{4}"'.format(locate_xt_exe, src_file, gaz_file, fuzzy_level, attributes_file)
                    else:
                        command = '{0} "{1}"'.format(locate_xt_exe, src_file)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=134217728)
                    sout, serr = process.communicate()
                    if process.returncode == 1:
                        sys.stderr.write('FAILED. {0}'.format(serr))
                        return
                    csv_file = os.path.join(output_dir, os.path.basename(os.path.splitext(src_file)[0]) + '.csv')
                    with open(csv_file, 'wb') as fp:
                        for line in sout:
                            fp.write(line)

                elif out_type == 'KML':
                    if gaz_file:
                        command = '{0} "{1}" -g "{2}" -e {3} --kml'.format(locate_xt_exe, src_file, gaz_file, fuzzy_level)
                    elif gaz_file and attributes_file:
                        command = '{0} "{1}" -g "{2}" -e {3} -c "{4}" --kml'.format(locate_xt_exe, src_file, gaz_file, fuzzy_level, attributes_file)
                    else:
                        command = '{0} "{1}" --kml '.format(locate_xt_exe, src_file)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=134217728)
                    sout, serr = process.communicate()
                    if process.returncode == 1:
                        sys.stderr.write('FAILED. {0}'.format(serr))
                        return
                    geo_info = sout.replace("utf-16", "utf-8")
                    kml_file = os.path.join(output_dir, os.path.basename(os.path.splitext(src_file)[0]) + '.kml')
                    with open(kml_file, 'wb') as fp:
                        for line in geo_info:
                            fp.write(line)

                elif out_type == 'SHP':
                    # geo_info = manager.Scan(lxtapi.lxtInputTypeFilename, src_file, lxtapi.lxtOutputTypeKML)
                    if gaz_file:
                        command = '{0} "{1}" -g "{2}" -e {3} --kml'.format(locate_xt_exe, src_file, gaz_file, fuzzy_level)
                    elif gaz_file and attributes_file:
                        command = '{0} "{1}" -g "{2}" -e {3} -c "{4}" --kml'.format(locate_xt_exe, src_file, gaz_file, fuzzy_level, attributes_file)
                    else:
                        command = '{0} "{1}" --kml '.format(locate_xt_exe, src_file)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=134217728)
                    sout, serr = process.communicate()
                    if process.returncode == 1:
                        sys.stderr.write('FAILED. {0}'.format(serr))
                        return
                    geo_info = sout.replace("utf-16", "utf-8")
                    kml_file = os.path.join(output_dir, os.path.basename(os.path.splitext(src_file)[0]) + '.kml')
                    out_shp = os.path.join(output_dir, os.path.basename(os.path.splitext(src_file)[0]) + '.shp')
                    with open(kml_file, 'wb') as fp:
                        for line in geo_info:
                            fp.write(line)
                    ogr_exe = tasks.ogr2ogr
                    command = '{0} -f "ESRI Shapefile" "{1}" "{2}" -skipfailures'.format(ogr_exe, out_shp, kml_file)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=134217728)
                    process.wait()
                    if process.returncode == 1:
                        status_writer.send_state(status.STAT_FAILED, process.stderr.read())
                        return
                    status_writer.send_status(process.stdout.read())

                if show_progress:
                    status_writer.send_percent(i / file_count, _('Extracted: {0}').format(src_file), 'locate_xt_api')
                extracted += 1
            else:
                if show_progress:
                    status_writer.send_percent(
                        i / file_count,
                        _('{0} is not a supported file type or does no exist').format(src_file),
                        'locate_xt'
                    )
                    i += 1
                else:
                    status_writer.send_status(_('{0} is not a supported file type or does no exist').format(src_file))
                skipped += 1
        except IOError as io_err:
            if show_progress:
                status_writer.send_percent(i / file_count, _('Skipped: {0}').format(src_file), 'locate_xt_api')
                i += 1
            status_writer.send_status(_('FAIL: {0}').format(repr(io_err)))
            errors += 1
            pass
    return extracted, errors, skipped
