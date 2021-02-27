from erddapy import ERDDAP

import xarray as xr

def load_glider(dataset_id ='ru32-20190102T1317-profile-sci-rt', server = "http://slocum-data.marine.rutgers.edu/erddap"):
    ''' Load glider data from erddap '''
    e = ERDDAP(
                server=server,
                protocol="tabledap",
                response="nc",
                )

    e.dataset_id = dataset_id

    gds = e.to_xarray()

    # want to have the dimention be time not obs number
    gds = gds.swap_dims({"obs": "time"})
    gds = gds.sortby("time")
    
    return gds