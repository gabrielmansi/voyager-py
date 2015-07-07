from getpass import getuser
from voyager.location.location import Location

class DataStore(Location):

  def __init__(self, name, layer, factory, params):
    Location.__init__(self, type='DATA_STORE', name=name, layer=layer, factory=factory)
    self.connection = map(lambda (k,v) : {'key':k, 'val':v}, params.items())

class PostGIS(DataStore):

  def __init__(self, db, layer, host='localhost', port=5432, user=getuser(), passwd=None, **kwargs):
    params = {
      'dbtype': 'postgis',
      'host': host,
      'port': port,
      'user': user,
      'database': db
    }
    params.update(kwargs)

    if (passwd is not None):
      params['passwd'] = passwd

    DataStore.__init__(self, db, layer, 'org.geotools.data.postgis.PostgisNGDataStoreFactory', params)