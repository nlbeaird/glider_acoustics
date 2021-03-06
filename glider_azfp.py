from erddapy import ERDDAP
import numpy as np
import xarray as xr

def load_glider(dataset_id ='ru32-20190102T1317-profile-sci-rt', server = "http://slocum-data.marine.rutgers.edu/erddap"):
    ''' Load glider data from erddap.
        input dataset ID and server
        Returns an xarray dataset indexed on time '''
    
    # should change: write to_netcdf, then check if netcdf exists
    
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
    
    # drop repeated time values
    gds = gds.sel(
        time=~gds.indexes['time'].duplicated())

    
    # get the seafloor depths too 

    e2 = ERDDAP(
    server="http://slocum-data.marine.rutgers.edu/erddap",
    protocol="tabledap",
    response="nc",
    )



    # get some of the raw data:
#     e2.dataset_id = dataset_id[:-14] + 'trajectory-raw-rt' 
    e2.dataset_id = dataset_id.replace('profile-sci', 'trajectory-raw')

    e2.variables = ['time', 'm_water_depth', 'm_pitch']

    # this connects to the data and load into an xarray dataset

    gds_raw = e2.to_xarray().drop_dims('trajectory')

    # want to have the dimention be time not obs number

    gds_raw = gds_raw.swap_dims({"obs": "time"})
    gds_raw = gds_raw.sortby("time")

    gds_raw = gds_raw.sel(
        time=~gds_raw.indexes['time'].duplicated())

    # remove bad values:
    gds_raw['m_water_depth'] = gds_raw.m_water_depth.where(gds_raw.m_water_depth > 10, drop=True)

    gds['bottom_depth'] = gds_raw.m_water_depth.interp_like(gds, method='nearest')
    
    
    
    
    return gds


def merge_glider_AZFP( gds, azfp, min_pitch = -30,
                        max_pitch = -15,
                     varz = ['potential_temperature', 'salinity',
                            'chlorophyll_a','m_pitch',
                            'm_roll', 'bottom_depth']):

    ''' Merge glider and AZFP, interpolate glider dataset
        onto AZFP pings.
        inputs:
        gds : glider xr dataset,
        azfp: azfp xr dataset (ed.Sv_clean)
        min/max pitch: pitch range to isolate downcasts
        varz: list of glider variables to return in merged ds
        Returns merged xarray dataset'''
    
    # subset the glider data to the azfp file time
    start_time = azfp.ping_time[0]
    end_time = azfp.ping_time[-1] 
    gds = gds.sel( time = slice(start_time,end_time) )
    
    
    # subset variables
    # also, make the lat, lon, depth into variables for interpolation:
    glider_var_subset = gds[varz].reset_coords()
    
        # check if bottom depth has more than 2 points:
    nbottom_obs = np.count_nonzero(~np.isnan(glider_var_subset.bottom_depth))
    
    if nbottom_obs < 1: # if no bottom data, set to dive depth max
        glider_var_subset['bottom_depth'] = glider_var_subset.depth.max()*xr.ones_like(glider_var_subset.depth)
        
    elif nbottom_obs < 3: # if some bottom data, set to mean
        glider_var_subset['bottom_depth'] = glider_var_subset.bottom_depth.mean()*xr.ones_like(glider_var_subset.depth)
        
    # fill na


    # fill na
    segment_gdsnafill = glider_var_subset.interpolate_na(dim='time',
                                                      fill_value="extrapolate")
    # interp glider onto AZFP
    glider_interp = segment_gdsnafill.interp( time = azfp.ping_time.data,
                                         kwargs={"fill_value": "extrapolate"})

    # pick one frequency
    freq = azfp.frequency.data[1]

    # get the range bins for this frequency
    ranges = azfp.range.sel(frequency = freq )

    # stack copies of the depth data so that it has
    # a shape that is rangebins x time
    RR = np.tile(ranges.T, (azfp.ping_time.shape[0] , 1 ) )

    # locate each bin in depth by adding the range of that bin
    # to the concurrent glider depth at that time
    bin_depths = RR.T+ glider_interp.depth.T.data

    # for plotting we need a stacked copy of the times with
    # the same shape as the adjusted depth-bins
    TT = np.tile(azfp.ping_time, (len(ranges), 1))

    ds = xr.merge( [azfp,
                glider_interp.rename({'time':'ping_time'}), ] )

    # add the corrected bin depths as a variable
    ds.update({'bin_depths' :
                (('ping_time','range_bin'), bin_depths.T)})

    # make bin_depths a coordinate:
    ds = ds.set_coords('bin_depths')
    
    # only keep data within a pitch range
    inds = (ds.m_pitch*180/np.pi < max_pitch) & (ds.m_pitch*180/np.pi > min_pitch)
    ds = ds.where(inds, drop=True)
    
    # get a distance coordinate
    dist = get_dist_from_point( ds.latitude, ds.longitude, 
                           ds.latitude[0], ds.longitude[0])
    ds = ds.assign_coords(distance = ('ping_time', dist))

    return ds



def get_dist_from_point( inlat, inlon, origlat, origlon):
    """ return a vector of distances from an origin """
    import geopy.distance
    out_vec = np.empty_like(inlon) 
    
    for j in range(len(inlon)):
        if np.isnan(inlon[j]):
            out_vec[j] = np.NaN
        else:
            out_vec[j] = geopy.distance.distance((inlat[j], inlon[j]), (origlat, origlon)).m
    return out_vec