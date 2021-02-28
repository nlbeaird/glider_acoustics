from erddapy import ERDDAP
import numpy as np
import xarray as xr

def load_glider(dataset_id ='ru32-20190102T1317-profile-sci-rt', server = "http://slocum-data.marine.rutgers.edu/erddap"):
    ''' Load glider data from erddap.
        input dataset ID and server
        Returns an xarray dataset indexed on time '''
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


def merge_glider_AZFP( gds, azfp, min_pitch = -30,
                        max_pitch = -15,
                     varz = ['potential_temperature', 'salinity',
                            'chlorophyll_a','m_pitch',
                            'm_roll', ]):

    ''' Merge glider and AZFP, interpolate glider dataset
        onto AZFP pings.
        inputs:
        gds : glider xr dataset,
        azfp: azfp xr dataset (ed.Sv_clean)
        min/max pitch: pitch range to isolate downcasts
        varz: list of glider variables to return in merged ds
        Returns merged xarray dataset'''

    # subset variables
    # also, make the lat, lon, depth into variables for interpolation:
    glider_var_subset = gds[varz].reset_coords()

    # drop repeated time values
    glider_var_subset = glider_var_subset.sel(
        time=~glider_var_subset.indexes['time'].duplicated())

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

    inds = (ds.m_pitch*180/np.pi < max_pitch) & (ds.m_pitch*180/np.pi > min_pitch)

    ds = ds.where(inds, drop=True)

    return ds