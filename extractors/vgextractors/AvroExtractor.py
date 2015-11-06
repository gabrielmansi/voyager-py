import os
import fastavro
from _vgdexfield import VgDexField


class AvroExtractor(object):

    @staticmethod
    def extractor():
        return "avro"

    def get_info(self):
        return {'name': AvroExtractor.extractor(), 'description': 'extract avro file information'}

    def extract(self, infile, job):
        minx, miny, maxx, maxy = (None, None, None, None)
        poly_wkt = None
        job.set_field(VgDexField.NAME, os.path.basename(infile))
        job.set_field(VgDexField.PATH, infile)
        with open(infile, 'rb') as avro_file:
            reader = fastavro.reader(avro_file)
            for record in reader:
                for k, v in record.iteritems():
                    if k.lower() == 'footprint_geometry':
                        poly_wkt = v
                        job.set_field(VgDexField.GEO_WKT, poly_wkt)
                        if job.get(VgDexField.GEO):
                            job.geo['wkt'] = poly_wkt
                        job.set_field(VgDexField.GEO, job.get_field(VgDexField.GEO_WKT))
                    else:
                        if k == 'MBR_EAST' and v:
                            minx = float(v)
                        elif k == 'MBR_WEST' and v:
                            maxx = float(v)
                        elif k == 'MBR_NORTH' and v:
                            maxy = float(v)
                        elif k == 'MBR_SOUTH' and v:
                            miny = float(v)
                    job.set_field("meta_{0}".format(k), v)

            if minx and not poly_wkt:
                poly_wkt = "POLYGON (({0} {1}, {0} {3}, {2} {3}, {2} {1}, {0} {1}))".format(minx, miny, maxx, maxy)
                job.set_field(VgDexField.GEO_WKT, poly_wkt)
                if job.get(VgDexField.GEO):
                    job.geo['wkt'] = poly_wkt
                job.set_field(VgDexField.GEO, job.get_field(VgDexField.GEO_WKT))
