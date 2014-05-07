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
import arcpy
from voyager_tasks.utils import status
from voyager_tasks.utils import task_utils


def execute(request):
    """Package inputs to an Esri map or layer package.
    :param request: json as a dict.
    """
    status_writer = status.Writer()
    parameters = request['params']
    input_items = task_utils.get_input_items(parameters)
    out_coordinate_system = task_utils.get_parameter_value(parameters, 'output_projection', 'code')
    arcpy.env.outputCoordinateSystem = task_utils.get_spatial_reference(out_coordinate_system)
    out_format = task_utils.get_parameter_value(parameters, 'output_format', 'value')
    summary = task_utils.get_parameter_value(parameters, 'summary')
    tags = task_utils.get_parameter_value(parameters, 'tags')

    # Get the clip region as an extent object.
    try:
        clip_area_wkt = task_utils.get_parameter_value(parameters, 'processing_extent', 'wkt')
        clip_area = task_utils.get_clip_region(clip_area_wkt, out_coordinate_system)
    except KeyError:
        clip_area = None

    out_workspace = os.path.join(request['folder'], 'temp')
    if not os.path.exists(out_workspace):
        os.makedirs(out_workspace)

    errors = 0
    skipped = 0
    layers = []
    files = []
    for item in input_items:
        try:
            if item.endswith('.lyr'):
                layers.append(arcpy.mapping.Layer(item))
            else:
                dsc = arcpy.Describe(item)
                if dsc.dataType in ('FeatureClass', 'ShapeFile', 'RasterDataset'):
                    if dsc.dataType == 'RasterDataset':
                        arcpy.MakeRasterLayer_management(item, os.path.basename(item))
                    else:
                        arcpy.MakeFeatureLayer_management(item, os.path.basename(item))
                    layers.append(arcpy.mapping.Layer(os.path.basename(item)))
                elif dsc.dataType in ('CadDrawingDataset', 'FeatureDataset'):
                    arcpy.env.workspace = item
                    for fc in arcpy.ListFeatureClasses():
                        arcpy.MakeFeatureLayer_management(fc, os.path.basename(fc))
                        layers.append(arcpy.mapping.Layer(os.path.basename(fc)))
                    arcpy.env.workspace = out_workspace
                elif dsc.dataType == 'MapDocument':
                    in_mxd = arcpy.mapping.MapDocument(item)
                    mxd_layers = arcpy.mapping.ListLayers(in_mxd)
                    layers += mxd_layers
                elif item.endswith('.gdb') or item.endswith('.mdb'):
                    arcpy.env.workspace = item
                    for fc in arcpy.ListFeatureClasses():
                        arcpy.MakeFeatureLayer_management(fc, os.path.basename(fc))
                        layers.append(arcpy.mapping.Layer(os.path.basename(fc)))
                    for raster in arcpy.ListRasters():
                        arcpy.MakeRasterLayer_management(raster, os.path.basename(raster))
                        layers.append(arcpy.mapping.Layer(os.path.basename(raster)))
                    datasets = arcpy.ListDatasets('*', 'Feature')
                    for fds in datasets:
                        arcpy.env.workspace = fds
                        for fc in arcpy.ListFeatureClasses():
                            arcpy.MakeFeatureLayer_management(fc, os.path.basename(fc))
                            layers.append(arcpy.mapping.Layer(os.path.basename(fc)))
                        arcpy.env.workspace = item
                    arcpy.env.workspace = out_workspace
                elif dsc.dataType == 'File':
                    files.append(item)
                else:
                    status_writer.send_status(_('invalid_input_type').format(item))
                    skipped += 1
                    continue
        except Exception as ex:
            status_writer.send_status(_('cannot_package').format(item))
            errors += 1
            pass

    if errors == len(input_items):
        status_writer.send_state(status.STAT_FAILED, _('no_results_to_package'))
        sys.exit(1)

    try:
        if out_format == 'MPK':
            shutil.copyfile(os.path.join(os.path.dirname(__file__), 'supportfiles', 'MapTemplate.mxd'),
                            os.path.join(out_workspace, 'output.mxd'))
            mxd = arcpy.mapping.MapDocument(os.path.join(out_workspace, 'output.mxd'))
            if mxd.description == '':
                mxd.description = os.path.basename(mxd.filePath)
            df = arcpy.mapping.ListDataFrames(mxd)[0]
            for layer in layers:
                arcpy.mapping.AddLayer(df, layer)
            mxd.save()
            status_writer.send_status(_('packaging_results'))
            arcpy.PackageMap_management(mxd.filePath,
                                        os.path.join(os.path.dirname(out_workspace), 'output.mpk'),
                                        'PRESERVE',
                                        extent=clip_area,
                                        arcgisruntime='RUNTIME',
                                        version='10',
                                        additional_files=files,
                                        summary=summary,
                                        tags=tags)
        else:
            status_writer.send_status(_('packaging_results'))
            for layer in layers:
                if layer.description == '':
                    layer.description = layer.name
            arcpy.PackageLayer_management(layers,
                                          os.path.join(os.path.dirname(out_workspace), 'output.lpk'),
                                          'PRESERVE',
                                          extent=clip_area,
                                          version='10',
                                          additional_files=files,
                                          summary=summary,
                                          tags=tags)
    except (RuntimeError, ValueError, arcpy.ExecuteError) as ex:
        status_writer.send_state(status.STAT_FAILED, repr(ex))
        sys.exit(1)

    try:
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'supportfiles', '_thumb.png'), request['folder'])
    except IOError:
        pass

    # Update state if necessary.
    if errors > 0 or skipped:
        status_writer.send_state(status.STAT_WARNING, _('results_could_not_be_processed').format(errors + skipped))
    task_utils.report(os.path.join(request['folder'], '_report.json'), len(layers), skipped, errors)