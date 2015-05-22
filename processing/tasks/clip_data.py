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
import glob
import shutil
import urllib2
from tasks.utils import status
from tasks.utils import task_utils
from tasks import _


status_writer = status.Writer()
import arcpy

files_to_package = list()


def clip_layer_file(layer_file, aoi):
    """Clips each layer in the layer file to the output workspace
    and re-sources each layer and saves a copy of the layer file."""
    if arcpy.env.workspace.endswith('.gdb'):
        layer_path = os.path.join(os.path.dirname(arcpy.env.workspace), os.path.basename(layer_file))
    else:
        layer_path = os.path.join(arcpy.env.workspace, os.path.basename(layer_file))
    shutil.copyfile(layer_file, layer_path)
    layer_from_file = arcpy.mapping.Layer(layer_path)
    layers = arcpy.mapping.ListLayers(layer_from_file)
    for layer in layers:
        if layer.isFeatureLayer:
            name = task_utils.create_unique_name(layer.name, arcpy.env.workspace)
            arcpy.Clip_analysis(layer.dataSource, aoi, name)
            if arcpy.env.workspace.endswith('.gdb'):
                layer.replaceDataSource(arcpy.env.workspace,
                                        'FILEGDB_WORKSPACE',
                                        os.path.splitext(os.path.basename(name))[0],
                                        False)
            else:
                layer.replaceDataSource(arcpy.env.workspace, 'SHAPEFILE_WORKSPACE', os.path.basename(name), False)
        elif layer.isRasterLayer:
            if isinstance(aoi, arcpy.Polygon):
                extent = aoi.extent
            else:
                extent = arcpy.Describe(aoi).extent
            ext = '{0} {1} {2} {3}'.format(extent.XMin, extent.YMin, extent.XMax, extent.YMax)
            name = task_utils.create_unique_name(layer.name, arcpy.env.workspace)
            arcpy.Clip_management(layer.dataSource, ext, name)
            if arcpy.env.workspace.endswith('.gdb'):
                layer.replaceDataSource(arcpy.env.workspace,
                                        'FILEGDB_WORKSPACE',
                                        os.path.splitext(os.path.basename(name))[0],
                                        False)
            else:
                layer.replaceDataSource(arcpy.env.workspace,
                                        'RASTER_WORKSPACE',
                                        os.path.splitext(os.path.basename(name))[0],
                                        False)

        if layer.description == '':
            layer.description == layer.name
        # Catch assertion error if a group layer.
        try:
            layer.save()
        except AssertionError:
            layers[0].save()
            pass


def clip_mxd_layers(mxd_path, aoi, map_frame=None):
    """Clips each layer in the map document to output workspace
    and re-sources each layer and saves a copy of the mxd.
    """
    mxd = arcpy.mapping.MapDocument(mxd_path)
    layers = arcpy.mapping.ListLayers(mxd)
    if map_frame:
        df = arcpy.mapping.ListDataFrames(mxd, map_frame)[0]
        df_layers = arcpy.mapping.ListLayers(mxd, data_frame=df)
        [[arcpy.mapping.RemoveLayer(d, l) for l in arcpy.mapping.ListLayers(mxd)] for d in arcpy.mapping.ListDataFrames(mxd)]
        [arcpy.mapping.AddLayer(df, l) for l in df_layers]
        layers = df_layers
    for layer in layers:
        try:
            out_name = arcpy.CreateUniqueName(layer.datasetName, arcpy.env.workspace)
            if layer.isFeatureLayer:
                arcpy.Clip_analysis(layer.dataSource, aoi, out_name)
                if arcpy.env.workspace.endswith('.gdb'):
                    layer.replaceDataSource(arcpy.env.workspace, 'FILEGDB_WORKSPACE', out_name, False)
                else:
                    layer.replaceDataSource(arcpy.env.workspace, 'SHAPEFILE_WORKSPACE', out_name, False)

            elif layer.isRasterLayer:
                ext = '{0} {1} {2} {3}'.format(aoi.extent.XMin, aoi.extent.YMin, aoi.extent.XMax, aoi.extent.YMax)
                arcpy.Clip_management(layer.dataSource, ext, out_name)
                if arcpy.env.workspace.endswith('.gdb'):
                    layer.replaceDataSource(arcpy.env.workspace, 'FILEGDB_WORKSPACE', out_name, False)
                else:
                    layer.replaceDataSource(arcpy.env.workspace, 'RASTER_WORKSPACE', out_name, False)
        except arcpy.ExecuteError:
            status_writer.send_state(status.STAT_WARNING, _(arcpy.GetMessages(2)))

    # Save a new copy of the mxd with all layers clipped and re-sourced.
    if mxd.description == '':
        mxd.description = os.path.basename(mxd.filePath)
    if arcpy.env.workspace.endswith('.gdb'):
        new_mxd = os.path.join(os.path.dirname(arcpy.env.workspace), os.path.basename(mxd.filePath))
    else:
        new_mxd = os.path.join(arcpy.env.workspace, os.path.basename(mxd.filePath))
    mxd.saveACopy(new_mxd)
    del mxd


def create_lpk(data_location, additional_files):
    """Creates a layer package (.lpk) for all datasets in the data location."""

    # Ensure existing layer files have a description.
    lyr_files = glob.glob(os.path.join(data_location, '*.lyr'))
    for lyr in lyr_files:
        layer = arcpy.mapping.Layer(lyr)
        if layer.description == '':
            layer.description = layer.name
            layer.save()

    # Save data to layer files.
    task_utils.save_to_layer_file(data_location, False)

    # Package all layer files.
    layer_files = glob.glob(os.path.join(data_location, '*.lyr'))
    arcpy.PackageLayer_management(layer_files,
                                  os.path.join(os.path.dirname(data_location), 'output.lpk'),
                                  'PRESERVE',
                                  version='10',
                                  additional_files=additional_files)
    task_utils.make_thumbnail(layer_files[0], os.path.join(os.path.dirname(data_location), '_thumb.png'))


def create_mxd_or_mpk(data_location, additional_files=None, mpk=False):
    """Creates a map document (.mxd) or map package (.mpk) for all the clipped datasets."""
    shutil.copyfile(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'supportfiles', 'MapTemplate.mxd'),
        os.path.join(data_location, 'output.mxd')
    )
    mxd = arcpy.mapping.MapDocument(os.path.join(data_location, 'output.mxd'))
    if mxd.description == '':
        mxd.description = os.path.basename(mxd.filePath)
    df = arcpy.mapping.ListDataFrames(mxd)[0]

    types = ('*.shp', '*.gdb', '*.mxd', '*.lyr')
    all_data = []
    for files in types:
        all_data.extend(glob.glob(os.path.join(data_location, files)))
    for ds in all_data:
        if ds.endswith('.shp'):
            # Add all shapefiles to the mxd template.
            layer = arcpy.MakeFeatureLayer_management(ds, '{0}_'.format(os.path.basename(ds)[:-3]))
            arcpy.mapping.AddLayer(df, layer.getOutput(0))
        elif ds.endswith('.gdb'):
            # Add all feature classes to the mxd template.
            arcpy.env.workspace = ds
            feature_datasets = arcpy.ListDatasets('*', 'Feature')
            if feature_datasets:
                for fds in feature_datasets:
                    arcpy.env.workspace = fds
                    for fc in arcpy.ListFeatureClasses():
                        layer = arcpy.MakeFeatureLayer_management(fc, '{0}_'.format(fc))
                        arcpy.mapping.AddLayer(df, layer.getOutput(0))
                arcpy.env.workspace = ds
            for fc in arcpy.ListFeatureClasses():
                layer = arcpy.MakeFeatureLayer_management(fc, '{0}_'.format(fc))
                arcpy.mapping.AddLayer(df, layer.getOutput(0))
            for raster in arcpy.ListRasters():
                layer = arcpy.MakeRasterLayer_management(raster, '{0}_'.format(raster))
                arcpy.mapping.AddLayer(df, layer.getOutput(0))
        elif ds.endswith('.lyr'):
            # Add all layer files to the mxd template.
            arcpy.mapping.AddLayer(df, arcpy.mapping.Layer(ds))
        # elif ds.endswith('.mxd') and not ds == mxd.filePath:
        #     # Add all layers from all map documents to the map template.
        #     temp_mxd = arcpy.mapping.MapDocument(ds)
        #     layers = arcpy.mapping.ListLayers(temp_mxd)
        #     for layer in layers:
        #         arcpy.mapping.AddLayer(df, layer)
        #     del temp_mxd

    mxd.save()
    if mpk:
        # Package the map template.
        arcpy.PackageMap_management(mxd.filePath,
                                    mxd.filePath.replace('.mxd', '.mpk'),
                                    'PRESERVE',
                                    version='10',
                                    additional_files=additional_files)

    task_utils.make_thumbnail(mxd.filePath, os.path.join(os.path.dirname(data_location), '_thumb.png'))
    del mxd


def execute(request):
    """Clips selected search results using the clip geometry.
    :param request: json as a dict.
    """
    clipped = 0
    errors = 0
    skipped = 0
    parameters = request['params']

    # Retrieve clip geometry.
    try:
        clip_area = task_utils.get_parameter_value(parameters, 'clip_geometry', 'wkt')
        if not clip_area:
            clip_area = 'POLYGON ((-180 -90, -180 90, 180 90, 180 -90, -180 -90))'
    except KeyError:
        clip_area = 'POLYGON ((-180 -90, -180 90, 180 90, 180 -90, -180 -90))'

    # Retrieve the coordinate system code.
    out_coordinate_system = int(task_utils.get_parameter_value(parameters, 'output_projection', 'code'))

    # Retrieve the output format type.
    out_format = task_utils.get_parameter_value(parameters, 'output_format', 'value')

    # Retrieve the clip features and where statement.
    clip_feature_class = task_utils.get_parameter_value(parameters, 'clip_features', 'value')
    where_statement = task_utils.get_parameter_value(parameters, 'where_statement', 'value')

    create_mxd = task_utils.get_parameter_value(parameters, 'create_mxd', 'value')

    # Create the temporary workspace if clip_feature_class:
    out_workspace = os.path.join(request['folder'], 'temp')
    if not os.path.exists(out_workspace):
        os.makedirs(out_workspace)

    if not out_coordinate_system == 0:  # Same as Input
        out_sr = task_utils.get_spatial_reference(out_coordinate_system)
        arcpy.env.outputCoordinateSystem = out_sr

    if not clip_feature_class:
        gcs_sr = task_utils.get_spatial_reference(4326)
        gcs_clip_poly = task_utils.from_wkt(clip_area, gcs_sr)
        if not gcs_clip_poly.area > 0:
            gcs_clip_poly = task_utils.from_wkt('POLYGON ((-180 -90, -180 90, 180 90, 180 -90, -180 -90))', gcs_sr)
    else:
        gcs_sr = ""
        gcs_clip_poly = None

    status_writer.send_status(_('Setting the output workspace...'))
    if not out_format == 'SHP':
        out_workspace = arcpy.CreateFileGDB_management(out_workspace, 'output.gdb').getOutput(0)
    arcpy.env.workspace = out_workspace

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

        i = 0.
        for group in groups:
            i += len(group) - group.count('')
            if fq:
                results = urllib2.urlopen(query + "&rows={0}&start={1}".format(task_utils.CHUNK_SIZE, group[0]))
            else:
                results = urllib2.urlopen(query + '{0}&ids={1}'.format(fl, ','.join(group)))

            input_items = task_utils.get_input_items(eval(results.read())['response']['docs'])
            result = clip_data(input_items, out_workspace, out_coordinate_system,
                               clip_feature_class, where_statement, gcs_sr, gcs_clip_poly, out_format)
            clipped += result[0]
            errors += result[1]
            skipped += result[2]
            status_writer.send_percent(i / num_results, '{0}: {1:%}'.format("Processed", i / num_results), 'clip_data')
    else:
        input_items = task_utils.get_input_items(parameters[response_index]['response']['docs'])
        clipped, errors, skipped = clip_data(input_items, out_workspace, out_coordinate_system, clip_feature_class,
                                             where_statement, gcs_sr, gcs_clip_poly, out_format, True)

    if arcpy.env.workspace.endswith('.gdb'):
        out_workspace = os.path.dirname(arcpy.env.workspace)
    if clipped > 0:
        try:
            if out_format == 'MPK':
                create_mxd_or_mpk(out_workspace, files_to_package, True)
                shutil.move(os.path.join(out_workspace, 'output.mpk'),
                            os.path.join(os.path.dirname(out_workspace), 'output.mpk'))
            elif out_format == 'LPK':
                create_lpk(out_workspace, files_to_package)
            else:
                if create_mxd:
                    create_mxd_or_mpk(out_workspace)
                zip_file = task_utils.zip_data(out_workspace, 'output.zip')
                shutil.move(zip_file, os.path.join(os.path.dirname(out_workspace), os.path.basename(zip_file)))
        except arcpy.ExecuteError as ee:
            status_writer.send_state(status.STAT_FAILED, _(ee))
            sys.exit(1)
    else:
        status_writer.send_state(status.STAT_FAILED, _('No output created. Zero inputs were clipped.'))

    # Update state if necessary.
    if errors > 0 or skipped > 0:
        status_writer.send_state(status.STAT_WARNING, _('{0} results could not be processed').format(errors + skipped))
    task_utils.report(os.path.join(request['folder'], '_report.json'), clipped, skipped, errors)


def clip_data(input_items, out_workspace, out_coordinate_system,
              clip_feature_class, where_statement, gcs_sr,
              gcs_clip_poly, out_format, show_progress=False):
    """Clips input results."""
    clipped = 0
    errors = 0
    skipped = 0
    fds = None

    if show_progress:
        i = 1.
        count = len(input_items)
        status_writer.send_percent(0.0, _('Starting to process...'), 'clip_data')

    for ds, out_name in input_items.iteritems():
        try:
            #TODO: Add support for WFS services -- currently a bug in _server_admin needing to be fixed.
            #TODO: Use feature set to load into and then clip it:
            #TODO:>>> server = _server_admin.Catalog("http://services.arcgis.com/Zs2aNLFN00jrS4gG/ArcGIS/rest/services")
            # Before describe, check if the path is a MXD data frame type.
            map_frame_name = task_utils.get_data_frame_name(ds)
            if map_frame_name:
                ds = ds.split('|')[0].strip()

            dsc = arcpy.Describe(ds)
            try:
                if dsc.spatialReference.name == 'Unknown':
                    status_writer.send_state(status.STAT_WARNING, _('{0} has an Unknown projection. Output may be invalid or empty.').format(dsc.name))
            except AttributeError:
                pass

            # If no output coord. system, get output spatial reference from input.
            if out_coordinate_system == 0:
                try:
                    out_sr = dsc.spatialReference
                    arcpy.env.outputCoordinateSystem = out_sr
                except AttributeError:
                    out_sr = task_utils.get_spatial_reference(4326)
                    arcpy.env.outputCoordinateSystem = out_sr
            else:
                out_sr = task_utils.get_spatial_reference(out_coordinate_system)
                arcpy.env.outputCoordinateSystem = out_sr

            # If a file, no need to project the clip area.
            if dsc.dataType not in ('File', 'TextFile'):
                if clip_feature_class:
                    arcpy.env.overwriteOutput = True
                    clip_poly = clip_feature_class
                    if where_statement:
                        clip_poly = arcpy.MakeFeatureLayer_management(clip_poly, 'clip_polygons', where_statement)
                    extent = arcpy.Describe(clip_poly).extent
                else:
                    if not out_sr.name == gcs_sr.name:
                        try:
                            geo_transformation = arcpy.ListTransformations(gcs_sr, out_sr)[0]
                            clip_poly = gcs_clip_poly.projectAs(out_sr, geo_transformation)
                        except (AttributeError, IndexError):
                            try:
                                clip_poly = gcs_clip_poly.projectAs(out_sr)
                            except AttributeError:
                                clip_poly = gcs_clip_poly
                        except ValueError:
                            clip_poly = gcs_clip_poly
                    else:
                        clip_poly = gcs_clip_poly
                    extent = clip_poly.extent
            # Feature class
            if dsc.dataType == 'FeatureClass':
                if out_name == '':
                    name = task_utils.create_unique_name(dsc.name, out_workspace)
                else:
                    name = task_utils.create_unique_name(out_name, out_workspace)
                arcpy.Clip_analysis(ds, clip_poly, name)

            # Feature dataset
            elif dsc.dataType == 'FeatureDataset':
                if not out_format == 'SHP':
                    fds_name = os.path.basename(task_utils.create_unique_name(dsc.name, out_workspace))
                    fds = arcpy.CreateFeatureDataset_management(out_workspace, fds_name)
                arcpy.env.workspace = ds
                for fc in arcpy.ListFeatureClasses():
                    try:
                        if not out_format == 'SHP':
                            arcpy.Clip_analysis(fc, clip_poly, task_utils.create_unique_name(fc, fds))
                        else:
                            arcpy.Clip_analysis(fc, clip_poly, task_utils.create_unique_name(fc, out_workspace))
                    except arcpy.ExecuteError:
                        pass
                arcpy.env.workspace = out_workspace

            # Shapefile
            elif dsc.dataType == 'ShapeFile':
                if out_name == '':
                    name = task_utils.create_unique_name(dsc.name, out_workspace)
                else:
                    name = task_utils.create_unique_name(out_name, out_workspace)
                arcpy.Clip_analysis(ds, clip_poly, name)

            # Raster dataset
            elif dsc.dataType == 'RasterDataset':
                if out_name == '':
                    name = task_utils.create_unique_name(dsc.name, out_workspace)
                else:
                    name = task_utils.create_unique_name(out_name, out_workspace)
                ext = '{0} {1} {2} {3}'.format(extent.XMin, extent.YMin, extent.XMax, extent.YMax)
                arcpy.Clip_management(ds, ext, name, in_template_dataset=clip_poly, clipping_geometry="ClippingGeometry")

            # Layer file
            elif dsc.dataType == 'Layer':
                clip_layer_file(dsc.catalogPath, clip_poly)

            # Cad drawing dataset
            elif dsc.dataType == 'CadDrawingDataset':
                arcpy.env.workspace = dsc.catalogPath
                cad_wks_name = os.path.splitext(dsc.name)[0]
                for cad_fc in arcpy.ListFeatureClasses():
                    name = task_utils.create_unique_name('{0}_{1}'.format(cad_wks_name, cad_fc), out_workspace)
                    arcpy.Clip_analysis(cad_fc, clip_poly, name)
                arcpy.env.workspace = out_workspace

            # File
            elif dsc.dataType in ('File', 'TextFile'):
                if dsc.catalogPath.endswith('.kml') or dsc.catalogPath.endswith('.kmz'):
                    name = os.path.splitext(dsc.name)[0]
                    kml_layer = arcpy.KMLToLayer_conversion(dsc.catalogPath, arcpy.env.scratchFolder, name)
                    group_layer = arcpy.mapping.Layer(os.path.join(arcpy.env.scratchFolder, '{0}.lyr'.format(name)))
                    for layer in arcpy.mapping.ListLayers(group_layer):
                        if layer.isFeatureLayer:
                            arcpy.Clip_analysis(layer,
                                                gcs_clip_poly,
                                                task_utils.create_unique_name(layer, out_workspace))
                    # Clean up temp KML results.
                    arcpy.Delete_management(os.path.join(arcpy.env.scratchFolder, '{0}.lyr'.format(name)))
                    arcpy.Delete_management(kml_layer[1])
                    del group_layer
                else:
                    if out_name == '':
                        out_name = dsc.name
                    if out_workspace.endswith('.gdb'):
                        f = arcpy.Copy_management(ds, os.path.join(os.path.dirname(out_workspace), out_name))
                    else:
                        f = arcpy.Copy_management(ds, os.path.join(out_workspace, out_name))
                    if show_progress:
                        status_writer.send_percent(i / count, _('Copied file: {0}').format(dsc.name), 'clip_data')
                        i += 1.
                    status_writer.send_state(_('Copied file: {0}').format(dsc.name))
                    clipped += 1
                    if out_format in ('LPK', 'MPK'):
                        files_to_package.append(f.getOutput(0))
                    continue

            # Map document
            elif dsc.dataType == 'MapDocument':
                clip_mxd_layers(dsc.catalogPath, clip_poly, map_frame_name)
            else:
                if show_progress:
                    status_writer.send_percent(i / count, _('Invalid input type: {0}').format(ds), 'clip_data')
                    i += 1.
                status_writer.send_state(_('Invalid input type: {0}').format(ds))
                skipped += 1
                continue

            if show_progress:
                status_writer.send_percent(i / count, _('Clipped: {0}').format(dsc.name), 'clip_data')
                i += 1.
            status_writer.send_status(_('Clipped: {0}').format(dsc.name))
            clipped += 1
        # Continue. Process as many as possible.
        except Exception as ex:
            if show_progress:
                status_writer.send_percent(i / count, _('Skipped: {0}').format(os.path.basename(ds)), 'clip_data')
            status_writer.send_status(_('FAIL: {0}').format(repr(ex)))
            i += 1.
            errors += 1
            pass
    return clipped, errors, skipped
