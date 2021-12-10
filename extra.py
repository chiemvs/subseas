import numpy as np
import xarray as xr

from pathlib import Path

from forecasts import ModelClimatology, Forecast
from observations import SurfaceObservations, Climatology, EventClassification
from comparison import ForecastToObsAlignment


if __name__ == "__main__":
    """
    Creation of matched set to ERA5 observations. First surface observation
    """
    #t2m = SurfaceObservations(basevar = 'tg', basedir = '/nobackup/users/straaten/ERA5/', name = 't2m-anom_1979-01-01_2019-12-31_1D_0.25-degrees') # Override normal E-OBS directory
    #t2m.load(tmin = '1998-06-07', tmax = '2019-10-31')
    #t2m.aggregatespace(clustername = 't2m-q095-adapted', level = 15)
    #t2m.aggregatetime(freq = '21D', method = 'mean', rolling = True)
    ##### write output. Correct the name for later matching to forecasts?
    ##### Utins match, namely K
    #t2m.newvar = 'anom' # Actually already done
    #t2m.construct_name(force = True) # Adds new tim/spacemethod
    ##print(t2m.name)
    #t2m.array = t2m.array.drop(['nclusters','dissim_threshold'], errors = 'ignore')
    ####out = xr.Dataset({'clustidfield':t2m.clusterarray.drop('nclusters', errors = 'ignore'),t2m.array.name:t2m.array})
    ####out.to_netcdf(t2m.filepath)
    #t2m.clusterarray = t2m.clusterarray.drop(['nclusters','dissim_threshold'], errors = 'ignore') # So that they are not carried into matching

    #### create a climatology
    #c = Climatology(f'{t2m.basevar}-{t2m.newvar}')
    #c.localclim(obs = t2m, daysbefore = 15, daysafter = 15, mean = False, quant = 0.9)
    #c.savelocalclim()

    #t2m = SurfaceObservations(basevar = 'tg', basedir = '/nobackup/users/straaten/ERA5/', name = 'tg-anom_1998-06-07_2019-10-31_31D-roll-mean_15-t2m-q095-adapted-mean') # Override normal E-OBS directory
    t2m = SurfaceObservations(basevar = 'tg', basedir = '/nobackup/users/straaten/ERA5/', name = 'tg-anom_1998-06-07_2019-10-31_21D-roll-mean_15-t2m-q095-adapted-mean') # Override normal E-OBS directory
    t2m.load()
    t2m.newvar = 'anom'

    ### Matching. preparation with a highresmodelclim 
    highresmodelclim = ModelClimatology(cycle='45r1', variable = t2m.basevar, **{'name':'tg_45r1_1998-06-07_2019-08-31_1D_0.38-degrees_5_5_mean'}) # Name for loading
    highresmodelclim.local_clim()
    newvarkwargs={'climatology':highresmodelclim}
    loadkwargs = {'llcrnr':(30,None),'rucrnr':(None,42)} # Limiting the domain a bit.

    #alignment = ForecastToObsAlignment(season = 'JJA', observations=t2m, cycle='45r1', n_members = 11, **{'expname':'paper3-1'}) # Season subsets the obs
    #alignment.match_and_write(newvariable = True, # Do I need loadkwargs
    #                          newvarkwargs = newvarkwargs,
    #                          loadkwargs = loadkwargs,
    #                          matchtime = True, 
    #                          matchspace= True)

    basedirkwargs = {'basedir':'/nobackup/users/straaten/EXT/'} # Needed because they need to be searching in EXT and not EXT_extra
    modelclim = ModelClimatology(cycle='45r1', variable = 'tg-anom') # Quantclimatology
    modelclim.local_clim(tmin = '1998-06-07', tmax = '2019-08-31', timemethod = t2m.timemethod, spacemethod = t2m.spacemethod, mean = False, quant = 0.9, lead_time_dep = True, daysbefore = 15, daysafter = 15, clusterarray = t2m.clusterarray, loadkwargs = loadkwargs, newvarkwargs = newvarkwargs, basedirkwargs = basedirkwargs)
    modelclim.savelocalclim()

    """
    Creation of amount of hot days predictand
    space-aggregation of surface obs.
    Daily Quantile climatology needed.
    then 'rolling temporal counting' Cannot be done with one Event_classification, because need to consider multiple days
    """
    #windowsize = 21
    #t2m = SurfaceObservations(basevar = 'tg', basedir = '/nobackup/users/straaten/ERA5/', name = 't2m-anom_1979-01-01_2019-12-31_1D_0.25-degrees') # Override normal E-OBS directory
    #t2m.load(tmin = '1998-06-07', tmax = '2019-10-31')
    #t2m.aggregatespace(clustername = 't2m-q095-adapted', level = 15)
    #t2m.array = t2m.array.drop(['nclusters','dissim_threshold'], errors = 'ignore')
    #t2m.clusterarray = t2m.clusterarray.drop(['nclusters','dissim_threshold'], errors = 'ignore')
    ###c = Climatology('t2m-anom')
    ###c.localclim(obs = t2m, daysbefore = 15, daysafter = 15, mean = False, quant = 0.75)
    ###c.clim.to_netcdf(c.filepath)
    #c = Climatology('t2m-anom', name = 't2m-anom_clim_1998-06-07_2019-10-31_1D_15-t2m-q095-adapted-mean_15_15_q0.75')
    #c.localclim()
    #
    #e = EventClassification(obs = t2m, quantclimatology = c, windowsize = windowsize)
    #e.hotdays(inplace = True)

    #t2m.construct_name(force = True) # not possible directly via save_changes because variable not in standard encoding
    #out = xr.Dataset({'clustidfield':t2m.clusterarray.drop('nclusters', errors = 'ignore'),t2m.array.name:t2m.array})
    #out.to_netcdf(t2m.filepath)

    #t2m = SurfaceObservations('tg',basedir = '/nobackup/users/straaten/ERA5/', name = 'tg-ex-q0.75-21D_1998-06-07_2019-10-31_1D_15-t2m-q095-adapted-mean')
    #t2m.load()
    #t2m.newvar = 'ex-q0.75-21D'

    """
    The procedure for forecasts can be done through the matching.
    Calling event-classification should be possible
    But needs a special model climatology for quantile thresholds (at daily time resolution, but aggregated in space)
    For that we need to make anomalies first (with highresmodelclim, highres in both space and time)
        Note: The quantile climatology is not lead-time dependent! In a way not to bad because mean model drift has been accounted for while making anomalie. Only a variability drift is not accounted for then.
    The actual forecasts will be spatially aggregated in the matching
    """

    #highresmodelclim = ModelClimatology(cycle='45r1', variable = 'tg', **{'name':f'tg_45r1_1998-06-07_2019-08-31_1D_0.38-degrees_5_5_mean'})
    #highresmodelclim.local_clim()
    #newvarkwargs = {'climatology':highresmodelclim} # For constructing the quant modelcim
    #loadkwargs = dict(llcrnr= (36,-24), rucrnr = (None,40))
    #basedirkwargs = {'basedir':'/nobackup/users/straaten/EXT/'} # Needed because they need to be searching in EXT and not EXT_extra. Actually EXT has not months like april etc.
    #clusterarray = t2m.clusterarray

    #modelclim = ModelClimatology(cycle='45r1', variable = 'tg-anom') # Quantclimatology
    #modelclim.local_clim(tmin = '1998-06-07', tmax = '2019-08-31', timemethod = '1D', spacemethod = t2m.spacemethod, mean = False, quant = 0.75, lead_time_dep = True, daysbefore = 15, daysafter = 15, clusterarray = clusterarray, loadkwargs = loadkwargs, newvarkwargs = newvarkwargs, basedirkwargs = basedirkwargs)
    #modelclim.savelocalclim()

    #modelclim = ModelClimatology(cycle='45r1', variable = 'tg-anom', name = 'tg-anom_45r1_1998-06-07_2019-08-31_1D_15-t2m-q095-adapted-mean_15_15_q0.75')
    #modelclim.local_clim()

    # Now comes the matching.
    # Make sure that the newvar is recognized, actually it is a double newvar. first anom, then hotdays
    # Also it needs to recognize that multiple days should be loaded. So over-ride the self.time_agg 

    #newvarkwargs={'climatology':highresmodelclim, 'quantclimatology':modelclim, 'windowsize':windowsize}
    #loadkwargs = {'llcrnr':(30,None),'rucrnr':(None,42)} # Limiting the domain a bit.
    #alignment = ForecastToObsAlignment(season = 'JJA', observations=t2m, cycle='45r1', n_members = 11, **{'expname':'paper3-2','time_agg':windowsize}) # Season subsets the obs
    #alignment.match_and_write(newvariable = True, 
    #                          newvarkwargs = newvarkwargs,
    #                          loadkwargs = loadkwargs,
    #                          matchtime = False, 
    #                          matchspace= True)
