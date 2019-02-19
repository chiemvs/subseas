#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan 30 12:11:08 2019

@author: straaten
"""

import os
import numpy as np
import xarray as xr
import pandas as pd
import dask.dataframe as dd
from observations import SurfaceObservations, Climatology, EventClassification
#from forecasts import Forecast
from comparison import ForecastToObsAlignment, Comparison
import itertools

class Experiment(object):
    
    def __init__(self, expname, basevar, cycle, season, method = 'mean', timeaggregations = ['1D', '2D', '3D', '4D', '7D'], spaceaggregations = [0.25, 0.75, 1.5, 3], quantiles = [0.5, 0.9, 0.95]):
        """
        Setting the relevant attributes. Timeaggregations are pandas frequency strings, spaceaggregations are floats in degrees.
        """
        self.resultsdir = '/nobackup/users/straaten/results/'
        self.expname = expname
        self.basevar = basevar
        self.cycle = cycle
        self.season = season
        self.method = method
        self.timeaggregations = timeaggregations
        self.spaceaggregations = spaceaggregations
        self.quantiles = quantiles
    
    def setuplog(self):
        """
        Load an experiment log if it is present. Otherwise create one.
        """
        self.logpath = self.resultsdir + self.expname + '.h5'
        try:
            self.log = pd.read_hdf(self.logpath, key = 'exp')
        except OSError:
            self.log = pd.DataFrame(data = None, index = pd.MultiIndex.from_product([self.spaceaggregations, self.timeaggregations, self.quantiles], names = ['spaceagg','timeagg','quantile']), columns = ['climname','scores'])
            self.log = self.log.unstack(level = -1)
            self.log = self.log.assign(**{'obsname':None,'booksname':None}) # :''
    
    def savelog(self):
        """
        Saves the experiment log if it is present
        """
        if hasattr(self, 'log'):
            self.log.to_hdf(self.logpath, key = 'exp')
        else:
            print('No log to save')
    
    def iterateaggregations(self, func, column, overwrite = False, kwargs = {}):
        """
        Wrapper that calls the function with a specific spaceagg and timeagg and writes the returns of the function to the column if a name was given
        """
        for spaceagg, timeagg in itertools.product(self.spaceaggregations,self.timeaggregations):
            if self.log.loc[(spaceagg, timeagg),column].isna().any() or overwrite:
                f = getattr(self, func)
                ret = f(spaceagg, timeagg, **kwargs)
                if (ret is not None):
                    self.log.loc[(spaceagg, timeagg),column] = ret
                    self.savelog()
            else:
                print('already filled')
    
    def prepareobs(self, spaceagg, timeagg, tmin, tmax):
        """
        Writes the observations that will be matched to forecasts
        """
        obs = SurfaceObservations(self.basevar)
        obs.load(tmin = tmin, tmax = tmax, llcrnr = (25,-30), rucrnr = (75,75))
        if timeagg != '1D':
            obs.aggregatetime(freq = timeagg, method = self.method)
        if spaceagg != 0.25:
            obs.aggregatespace(step = spaceagg, method = self.method, by_degree = True)
        obs.savechanges()
        return(obs.name)
    
    def match(self, spaceagg, timeagg, obscol = 'obsname'):
        """
        Writes the intermediate files. And returns the (possibly appended) booksname
        """
        obs = SurfaceObservations(self.basevar, **{'name':self.log.loc[(spaceagg, timeagg),(obscol,'')]})
        obs.load()
        alignment = ForecastToObsAlignment(season = self.season, observations=obs, cycle=self.cycle)
        alignment.find_forecasts()
        alignment.load_forecasts(n_members = 11)
        alignment.force_resolution(time = (timeagg != '1D'), space = (spaceagg != 0.25))
        alignment.match_and_write()
        return(alignment.books_name)
    
    def makeclim(self, spaceagg, timeagg, climtmin, climtmax):
        """
        Make climatologies based on a period of 30 years, longer than the 5 years in matching. Should daysbefore/daysafter be an attribute of the class?
        """
        obs = SurfaceObservations(self.basevar)
        obs.load(tmin = climtmin, tmax = climtmax, llcrnr = (25,-30), rucrnr = (75,75))
        dailyobs = SurfaceObservations(self.basevar)
        dailyobs.load(tmin = climtmin, tmax = climtmax, llcrnr = (25,-30), rucrnr = (75,75))
        if timeagg != '1D':
            obs.aggregatetime(freq = timeagg, method = self.method)
        if spaceagg != 0.25:
            obs.aggregatespace(step = spaceagg, method = self.method, by_degree = True)
            dailyobs.aggregatespace(step = spaceagg, method = self.method, by_degree = True) # Aggregate the dailyobs for the climatology
        
        climnames = np.repeat(None,len(self.quantiles))
        for quantile in self.quantiles:
            climatology = Climatology(self.basevar)
            climatology.localclim(obs = obs, daysbefore = 5, daysafter=5, mean = False, quant = quantile, daily_obs_array = dailyobs.array)
            climatology.savelocalclim()
            climnames[self.quantiles.index(quantile)] = climatology.name
        
        return(climnames)
            
    def score(self, spaceagg, timeagg):
        """
        Read the obs and clim. make a comparison object which computes the scores in the dask dataframe. Returns a list of dataframes with raw and climatological scores. Perhaps write intermediate scores to a file? Distributed computation can take very long.
        """
        alignment = ForecastToObsAlignment(season = self.season, cycle=self.cycle)
        alignment.recollect(booksname = self.log.loc[(spaceagg, timeagg),('booksname','')])
        
        result = np.repeat(None,len(self.quantiles))
        for quantile in self.quantiles:    
            climatology = Climatology(self.basevar, **{'name':self.log.loc[(spaceagg, timeagg),('climname', quantile)]})
            climatology.localclim() # loading in this case. Creation was done in the makeclim method.
            comp = Comparison(alignedobject= alignment.alignedobject, climatology = climatology.clim)
            scores = comp.brierscore(groupers=['leadtime'])
            
            # rename the columns
            scores.columns = scores.columns.droplevel(1)
            result[self.quantiles.index(quantile)] = scores
        
        return(result)

"""
Max temperature benchmarks.
"""
## Calling of the class        
#test1 = Experiment(expname = 'test1', basevar = 'tx', cycle = '41r1', season = 'JJA', method = 'max', timeaggregations = ['1D', '2D', '3D', '4D', '7D'], spaceaggregations = [0.25, 0.75, 1.5, 3], quantiles = [0.5, 0.9, 0.95])
#test1.setuplog()
##test1.iterateaggregations(func = 'prepareobs', column = 'obsname', kwargs = {'tmin':'1996-05-30','tmax':'2006-08-31'})
##test1.iterateaggregations(func = 'match', column = 'booksname')
##test1.iterateaggregations(func = 'makeclim', column = 'climname', kwargs = {'climtmin':'1980-05-30','climtmax':'2010-08-31'})
##test1.iterateaggregations(func = 'score', column = 'scores')
#
#scoreseries = test1.log.loc[:,('scores',slice(None,None,None))].stack(level = -1)['scores']
#temp = pd.concat(scoreseries.tolist(), keys = scoreseries.index)
#temp.index.set_names(scoreseries.index.names, level = [0,1,2], inplace=True)
#skill = 1 - temp['rawbrier'] / temp['climbrier'] # Nice one to write out.
##skill.to_hdf('/nobackup/users/straaten/results/test1skill.h5', key = 'skill')
#
## Plotting
#skill.loc[(0.75,slice(None), 0.9)].unstack(level = [0,1,2]).plot()
#skill.xs(0.5, level = 'quantile', drop_level = False).unstack(level = [0,1,2]).plot()
#
## Small test as a forecast horizon
#def lastconsecutiveabovezero(series):
#    gtzero = series.gt(0)
#    if not gtzero.any():
#        leadtime = 0
#    elif gtzero.all():
#        leadtime = gtzero.index.get_level_values(level = -1)[-1]
#    else:
#        tupfirst = gtzero.idxmin()
#        locfirst = gtzero.index.get_loc(tupfirst)
#        tup = gtzero.index.get_values()[locfirst - 1]
#        leadtime = tup[-1]
#    return(leadtime)
#
#zeroskillleadtime = skill.groupby(['spaceagg', 'timeagg', 'quantile']).apply(func = lastconsecutiveabovezero)

"""
Mean temperature benchmarks. Observations split into two decades. Otherwise potential memory error in matching.
"""

# Calling of the class        
test2 = Experiment(expname = 'test2', basevar = 'tg', cycle = '41r1', season = 'DJF', method = 'mean', 
                   timeaggregations = ['1D', '2D', '3D', '4D', '5D', '6D', '7D'], spaceaggregations = [0.25, 0.75, 1.25, 2, 3], quantiles = [0.1, 0.15, 0.25, 0.33, 0.66])
test2.setuplog()
#test2.log = test2.log.assign(**{'obsname2':None}) # Extra observation column.
test2.iterateaggregations(func = 'prepareobs', column = 'obsname', kwargs = {'tmin':'1995-11-30','tmax':'2005-02-28'})
test2.iterateaggregations(func = 'prepareobs', column = 'obsname2', kwargs = {'tmin':'2005-03-01','tmax':'2015-02-28'})

#test2.iterateaggregations(func = 'match', column = 'booksname', kwargs = {'obscol':'obsname'})
#test2.iterateaggregations(func = 'match', column = 'booksname', kwargs = {'obscol':'obsname2'}, overwrite = True) # Replaces with updated books name.
#test2.iterateaggregations(func = 'makeclim', column = 'climname', kwargs = {'climtmin':'1980-05-30','climtmax':'2015-02-28'})
#test2.iterateaggregations(func = 'score', column = 'scores')

#def replace(string, first, later, number = None):
#    if not number is None:
#        return(string.replace(first, later, number))
#    else:
#        return(string.replace(first, later))

#test2.log['obsname'] = test2.log['obsname'].apply(replace, args = ('_','-'))
#test2.log['obsname'] = test2.log['obsname'].apply(replace, args = ('.','_', 4))

"""
4 years summer temperatures 1995-1998. In Forecast domain. 
match forecasts on .38 with obs on .25. Climatology of +- 5days of 30 years.
"""
#quantile = 0.9
#obs1day = SurfaceObservations('tg')
#obs1day.load(tmin = '1970-05-30', tmax = '2000-05-30', llcrnr = (25,-30), rucrnr = (75,75))
#windowed = EventClassification(obs=obs1day)
#windowed.localclim(daysbefore=5, daysafter=5, mean = False, quant=quantile)

#alignment = ForecastToObsAlignment(season = 'JJA', observations=obs1day)
# alignment.force_resolution(time = True, space = False)
#alignment.recollect(booksname='books_tg_JJA.csv')
#subset = dd.read_hdf('/nobackup/users/straaten/match/tg_JJA_badf363636004a808a701f250175131d.h5', key = 'intermediate')
#temp = xr.open_dataarray('/nobackup/users/straaten/E-OBS/climatologyQ09.nc')
#self = Comparison(alignedobject=alignment.alignedobject, climatology= temp)
#test = self.brierscore(exceedquantile=True, groupers=['leadtime', 'latitude', 'longitude'])

# self.frame.groupby(self.frame['time'].dt.dayofyear)
# subset.compute()['time'].dt.dayofyear
# self.frame['time'].dt.dayofyear
#tg_JJA_badf363636004a808a701f250175131d.h5


"""
Probability of precipitation matching.
"""
#obsrr1day = SurfaceObservations('rr')
#obsrr1day.load(tmin = '1995-01-01', tmax = '2000-12-31', llcrnr = (25,-30), rucrnr = (75,75))
#classpop1day = EventClassification(obs = obsrr1day)
#classpop1day.pop()

# Make a separate climatology
#classpop1day.localclim(daysbefore=5, daysafter = 5)
#classpop1day.clim
#classpop1day.obs.array

# Now match this to forecasts
#alignment = ForecastToObsAlignment(season = 'DJF', observations = classpop1day.obs, cycle='41r1')
#alignment.find_forecasts()
#alignment.load_forecasts(n_members=11) # With the 'rr' basevariable
#alignment.match_and_write(newvariable = True)
#alignment.recollect() # booksname = books_pop_DJF_41r1_1D_0.25_degrees.csv

# Now to scoring
#final = Comparison(alignedobject=alignment.alignedobject, climatology=classpop1day.clim) # in this case climatology is a probability
#test = final.brierscore()
