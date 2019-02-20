#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 28 09:31:16 2018

@author: straaten
"""
import os
import sys
import numpy as np
import xarray as xr
import pandas as pd
import dask.dataframe as dd
from observations import SurfaceObservations, EventClassification
#from forecasts import Forecast
from helper_functions import monthtoseasonlookup, unitconversionfactors

class ForecastToObsAlignment(object):
    """
    Idea is: you have already prepared an observation class, with a certain variable, temporal extend and space/time aggregation.
    This searches the corresponding forecasts, and possibly forces the same aggregations.
    TODO: not sure how to handle groups yet.
    """
    def __init__(self, season, cycle, observations = None):
        """
        Temporal extend can be read from the attributes of the observation class. 
        Specify the season under inspection for subsetting.
        """
        self.basedir = '/nobackup/users/straaten/match/'
        self.cycle = cycle
        self.season = season
        if observations is not None:
            self.obs = observations
            self.dates = self.obs.array.coords['time'].to_series() # Left stamped
            self.dates = self.dates[monthtoseasonlookup(self.dates.index.month) == self.season]
            # infer dominant time aggregation in days
            self.time_agg = int(self.dates.diff().dt.days.mode())
            self.maxleadtime = 46
    
    def find_forecasts(self):
        """
        Here the forecasts corresponding to the observations are determined, by testing their existence.
        Hindcasts and forecasts might be mixed. But they are in the same class.
        Leadtimes may differ.
        """
        self.forecasts = {}
        for date in self.dates.tolist():
            # Find forecast initialization times that fully contain the observation date (including its window for time aggregation)
            containstart = date + pd.Timedelta(str(self.time_agg) + 'D') - pd.Timedelta(str(self.maxleadtime) + 'D')
            containend = date
            contain = pd.date_range(start = containstart, end = containend, freq = 'D').strftime('%Y-%m-%d')
            forecasts = [Forecast(indate, prefix = 'for_', cycle = self.cycle) for indate in contain]
            hindcasts = [Forecast(indate, prefix = 'hin_', cycle = self.cycle) for indate in contain]
            # select from potential forecasts only those that exist.
            forecasts = [f for f in forecasts if os.path.isfile(f.basedir + f.processedfile)]
            hindcasts = [h for h in hindcasts if os.path.isfile(h.basedir + h.processedfile)]
            self.forecasts.update({date : forecasts + hindcasts})   
        
    def load_forecasts(self, n_members):
        """
        Gets the daily processed forecasts into memory. Delimited by the left timestamp and the aggregation time.
        This is done by using the load method of each Forecast class in the dictionary. They are stored in a list.
        """
        for date, listofforecasts in self.forecasts.items():
            
            if listofforecasts: # empty lists are skipped
                tmin = date
                tmax = date + pd.Timedelta(str(self.time_agg - 1) + 'D') # -1 because date itself also counts for one day in the aggregation.
                
                for forecast in listofforecasts:
                    forecast.load(variable = self.obs.basevar, tmin = tmin, tmax = tmax, n_members = n_members)
        
        self.n_members = n_members
     
    def force_resolution(self, time = True, space = True):
        """
        Force the observed resolution onto the Forecast arrays. Checks if the same resolution and force spatial/temporal aggregation if that is not the case.
        Makes use of the methods of each Forecast class
        """
            
        for date, listofforecasts in self.forecasts.items():
        
            for forecast in listofforecasts:
                
                if time:
                    # Check time aggregation
                    obstimemethod = getattr(self.obs, 'timemethod')
                                
                    try:
                        fortimemethod = getattr(forecast, 'timemethod')
                        if not fortimemethod == obstimemethod:
                            raise AttributeError
                        else:
                            print('Time already aligned')
                    except AttributeError:
                        print('Aligning time aggregation')
                        freq, method = obstimemethod.split('-')
                        forecast.aggregatetime(freq = freq, method = method, keep_leadtime = True)
                
                if space:
                    # Check space aggregation
                    obsspacemethod = getattr(self.obs, 'spacemethod')
                        
                    try:
                        forspacemethod = getattr(forecast, 'spacemethod')
                        if not forspacemethod == obsspacemethod:
                            raise AttributeError
                        else:
                            print('Space already aligned')
                    except AttributeError:
                        print('Aligning space aggregation')
                        step, what, method = obsspacemethod.split('-')
                        forecast.aggregatespace(step = float(step), method = method, by_degree = (what == 'degrees'))
                      
    def force_new_variable(self, array):
        """
        Call upon event classification to get the on-the-grid conversion of the base variable.
        Do this by a small initization of an object with an .array attribute.
        Then call the classification method with a similar name as the newvar and execute it to let it return the newvar array
        """
        newvariable = self.obs.newvar
        temp = SurfaceObservations(alias = newvariable, **{'array':array}) # Just a convenient class, does not neccessarily mean the array is an observed one.
        method = getattr(EventClassification(obs = temp), newvariable)
        return(method(inplace = False))
        
                
    def match_and_write(self, newvariable = False):
        """
        Neirest neighbouring to match pairs. Be careful when domain of observations is larger.
        Also converts forecast units to observed units.
        Creates the dataset and writes it to disk. Possibly empties basket and writes to disk 
        at intermediate steps if intermediate results press too much on memory.
        """
        import uuid
        from datetime import datetime
        
        aligned_basket = []
        self.outfiles = []
        
        # Make sure the first parts are recognizable as the time method and the space method. Make last part unique
        # Possibly I can also append in h5 files.
        def write_outfile(basket, newvariable = False):
            """
            Saves to a unique filename and creates a bookkeeping file (appends if it already exists)
            """
            if newvariable:
                characteristics = [self.obs.newvar, self.season, self.cycle, self.obs.timemethod, self.obs.spacemethod]
            else:
                characteristics = [self.obs.basevar, self.season, self.cycle, self.obs.timemethod, self.obs.spacemethod]
            filepath = self.basedir + '_'.join(characteristics) + '_' + uuid.uuid4().hex + '.h5'
            self.books_name = 'books_' + '_'.join(characteristics) + '.csv'
            books_path = self.basedir + self.books_name
            
            dataset = pd.concat(basket)
            dataset.to_hdf(filepath, key = 'intermediate', format = 'table')
            
            books = pd.DataFrame({'write_date':[datetime.now().strftime('%Y-%m-%d_%H:%M:%S')],
                                  'file':[filepath],
                                  'tmin':[dataset.time.min().strftime('%Y-%m-%d')],
                                  'tmax':[dataset.time.max().strftime('%Y-%m-%d')],
                                  'unit':[self.obs.array.units]})
            
            try:
                with open(books_path, 'x') as f:
                    books.to_csv(f, header=True, index = False)
            except FileExistsError:
                with open(books_path, 'a') as f:
                    books.to_csv(f, header = False, index = False)
            
            print('written out', filepath)
            self.outfiles.append(filepath)
        
        for date, listofforecasts in self.forecasts.items():
            
            if listofforecasts:
                fieldobs = self.obs.array.sel(time = date).drop('time')
                
                allleadtimes = xr.concat(objs = [f.array.swap_dims({'time':'leadtime'}) for f in listofforecasts], dim = 'leadtime') # concatenates over leadtime dimension.
                a,b = unitconversionfactors(xunit = allleadtimes.units, yunit = fieldobs.units)
                exp = allleadtimes.reindex_like(fieldobs, method='nearest') * a + b
                
                # Call force_new_variable here. Which in its turn calls the same EventClassification method that was also used on the obs.
                if newvariable:
                    binary = self.force_new_variable(exp) # the binary members are discarded at some point.
                    pi = binary.mean(dim = 'number') # only the probability of the event over the members is retained.
                    # Merging, exporting to pandas and masking by dropping on NA observations.
                    combined = xr.Dataset({'forecast':exp.drop('time'),'observation':fieldobs, 'pi':pi.drop('time')}).to_dataframe().dropna(axis = 0)
                    # Unstack creates duplicates. Two extra columns (obs and pi) need to be selected. Therefore the iloc
                    temp = combined.unstack('number').iloc[:,np.append(np.arange(0,self.n_members + 1), self.n_members * 2)]
                    temp.reset_index(inplace = True) # places latitude and all in 
                    labels = [l for l in temp.columns.labels[1]]
                    labels[-2:] = np.repeat(self.n_members, 2)
                else:
                    # Merging, exporting to pandas and masking by dropping on NA observations.
                    combined = xr.Dataset({'forecast':exp.drop('time'), 'observation':fieldobs}).to_dataframe().dropna(axis = 0)
                    # Handle the multi-index
                    # first puts number dimension into columns. observerations are duplicated so therefore selects up to n_members +1
                    temp = combined.unstack('number').iloc[:,:(self.n_members + 1)]
                    temp.reset_index(inplace = True) # places latitude and all in 
                    labels = [l for l in temp.columns.labels[1]]
                    labels[-1] = self.n_members
                
                temp.columns.set_labels(labels, level = 1, inplace = True)
                
                # Downcasting latitude and longitude
                temp[['latitude', 'longitude']] = temp[['latitude', 'longitude']].apply(pd.to_numeric, downcast = 'float')
                # Downcasting the leadtime column
                temp['leadtime'] = np.array(temp['leadtime'].values.astype('timedelta64[D]'), dtype = 'int8')
                
                # prepend with the time index.
                temp.insert(0, 'time', date)
                aligned_basket.append(temp) # temp.swaplevel(1,2, axis = 0)
                print(date, 'matched')
                
                # If aligned takes too much system memory (> 1Gb) . Write it out
                if sys.getsizeof(aligned_basket[0]) * len(aligned_basket) > 1*10**9:
                    write_outfile(aligned_basket, newvariable=newvariable)
                    aligned_basket = []
        
        # After last loop also write out 
        if aligned_basket:
            write_outfile(aligned_basket, newvariable=newvariable)
        
        
    def recollect(self, booksname = None):
        """
        Makes a dask dataframe object. The outfilenames can be collected by reading the timefiles. Or for instance by searching with a regular expression.
        """
        if hasattr(self, 'outfiles'):
            outfilenames = self.outfiles
        else:
            try:
                books = pd.read_csv(self.basedir + booksname)
                outfilenames = books['file'].values.tolist()
            except AttributeError:
                pass
            
        self.alignedobject = dd.read_hdf(outfilenames, key = 'intermediate')
        

class Comparison(object):
    """
    All based on the dataframe format. No arrays anymore. In this class the aligned object is grouped in multiple ways to fit models in a cross-validation sense. 
    To make predictions and to score, raw, post-processed and climatological forecasts
    Potentially I can set an index like time in any operation where time becomes unique to speed up lookups.
    """
    
    def __init__(self, alignedobject, climatology = None):
        """
        The aligned object has Observation | members |
        Potentially an external observed climatology array can be supplied that takes advantage of the full observed dataset. It has to have a location and dayofyear timestamp. Is it already aggregated?
        This climatology can be a quantile (used as the threshold for brier scoring) of it is a climatological probability if we have an aligned event predictor like POP.
        """
        self.frame = alignedobject
        if climatology is not None: 
            climatology.name = 'climatology'
            self.clim = climatology.to_dataframe().dropna(axis = 0, how = 'any')
            # Some formatting to make merging with the two-level aligned object easier
            self.clim.reset_index(inplace = True)
            self.clim[['latitude','longitude','climatology']] = self.clim[['latitude','longitude','climatology']].apply(pd.to_numeric, downcast = 'float')
            self.clim.columns = pd.MultiIndex.from_product([self.clim.columns, ['']])
            try:
                self.quantile = climatology.attrs['quantile']
            except KeyError:
                pass
            
            
    def fit_pp_models(self, groupers = ['leadtime','latitude','longitude'], nfolds = 1):
        """
        Computes simple predictors like. Groups the dask dataframe per location and leadtime, and then pushes these groups to an apply function. In this apply a model fitting function can be called which uses the predictor columns and the observation column, the function currently returns a Dataframe with parametric coefficients. Which are stored in-memory with the groupers as multi-index.
        """
        from sklearn.linear_model import LinearRegression
        from scipy import optimize
        
        def cv_fit(data, nfolds, fitfunc, modelcoefs = ['a0','a1']):
            """
            Acts per group (predictors should already be constructed). Calls a fitting function in a time-cross-validation fashion. Supplies data as (nfolds - 1)/nfolds for training, and writes the returned coeficients by the model to the remaining 1/nfolds part (where the prediction will be made) as a dataframe
            """
            
            nperfold = len(data) // nfolds
            foldindex = range(1,nfolds+1)
            
            # Pre-allocating a structure for the dataframe.
            coefs = pd.DataFrame(data = np.nan, index = data['time'], columns = modelcoefs)
                        
            # Need inverse of the data index to select train. For loc this can be np.setdiff1d or df.index.difference(indexyoudontwant).
            # Question is: what kind of index is present within the groups?
            # Stored by increasing time enables the cv to be done by integer location. (assuming equal group size)
            full_ind = np.arange(len(coefs))
            
            for fold in foldindex:
                if (fold == foldindex[-1]):
                    test_ind = np.arange((fold - 1)*nperfold, len(coefs))
                else:
                    test_ind = np.arange(((fold - 1)*nperfold),(fold*nperfold))

                train_ind = np.setdiff1d(full_ind, test_ind)
                
                # Calling of the fitting function on the training Should return an 1d array with the indices (same size as modelcoefs)
                fitted_coef = fitfunc(data.iloc[train_ind,:])
                
                # Write to the frame with time index. Should the fold be prepended as extra level in a multi-index?
                coefs.iloc[test_ind,:] = fitted_coef
                         
            return(coefs)
        
        def fit_ngr(train):
            """
            Uses CRPS-minimization for the fitting.
            Model is specified as N(a0 + a1 * mu_ens, exp(b0 + b1 * sig_ens)) 
            So a logarithmic transformation on sigma to keep those positive.
            Returns an array with 4 model coefs.
            """
            
            def crpscostfunc(parameters, mu_ens, std_ens, obs):
                """
                Cost function returns the mean crps (to be independent from the amount of observations) and also the analytical gradient, 
                translated from sigma and mu to the model parameters,
                for better optimization (need not be approximated)
                """
                mu = parameters[0] + parameters[1] * mu_ens
                logstd = parameters[2] + parameters[3] * std_ens
                std = np.exp(logstd)
                crps, grad = ps.crps_gaussian(obs, mu, std, grad = True) # grad is returned as np.array([dmu, dsig])
                dcrps_d0 = grad[0,:]
                dcrps_d1 = grad[0,:] * mu_ens
                dcrps_d2 = grad[1,:] * std
                dcrps_d3 = grad[1,:] * std * std_ens
                return(crps.mean(), np.array([dcrps_d0.mean(), dcrps_d1.mean(), dcrps_d2.mean(), dcrps_d3.mean()])) # obs can be vector.

            res = optimize.minimize(crpscostfunc, x0 = [0,1,0.5,0.2], jac = True,
                            args=(train['ensmean'], train['ensstd'], train['observation']), 
                            method='L-BFGS-B', bounds = [(-20,20),(0,10),(-10,10),(-10,10)])
                             
            return(res.x)

        def fit_logistic(train):
            """
            Uses L2-loss minimization to fit a logistic model
            The model is specified as ln(p/(1-p)) = a0 + a1 * raw_pop + a2 * mu_ens
            """
            clf = LogisticRegression(solver='liblinear').fit(X = pd.DataFrame({'pi':train['pi'], 'ens_mean':train['forecast'].mean(axis = 1)}), y = train['observation'])
            
            return(clf.intercept_.append(clf.coef_))
        
        def cv_fitlinear(data, nfolds):
            """
            Fits a linear model. If nfolds = 1 it uses all the data, otherwise it is split up. This cross validation is done here because addition of a column to the full ungrouped frame is too expensive, also the amount of available times can differ per leadtime and due to NA's the field size is not always equal. Therefore, the available amount is computed here.
            TODO: needs to be expanded to NGR and Logistic regression for the PoP. Plus fitting on 2/3 of the data.
            """
            
            modelcoefs = ['intercept','slope']
            nperfold = len(data) // nfolds
            foldindex = range(1,nfolds+1)
            
            # Pre-allocating a structure.
            coefs = np.full((nfolds,len(modelcoefs)), np.nan)
            
            for fold in foldindex:
                if (fold == foldindex[-1]):
                    train = data.iloc[((fold - 1)*nperfold):,:]
                else:
                    train = data.iloc[((fold - 1)*nperfold):(fold*nperfold),:]
                
                # Fitting of the linear model
                reg = LinearRegression().fit(train['ensmean'].values.reshape(-1,1), train['observation'].values.reshape(-1,1))
                coefs[fold-1,:] = [reg.intercept_[0], reg.coef_[0]]
            
            models = pd.DataFrame(data = coefs, index = pd.Index(foldindex, name = 'fold'), columns = modelcoefs)            
            
            return(models)
        
        # Computation of predictands for the linear models.
        # There are some negative precipitation values in .iloc[27:28,:]
        self.frame['ensmean'] = self.frame['forecast'].mean(axis = 1)
        self.frame['ensstd']  = self.frame['forecast'].std(axis = 1)
        
        grouped = self.frame.groupby(groupers)
        #self.fits = grouped.apply(fitngr, meta = {'intercept':'float32', 'slope':'float32'}).compute() #
        
        self.fits = grouped.apply(cv_fitlinear, meta = {'intercept':'float32', 'slope':'float32'}, **{'nfolds':nfolds}).compute()
        
        
    def make_pp_forecast(self):
        """
        Adds either forecast members or a probability distribution
        """
    

    def add_custom_groups(self):
        """
        Add groups that are for instance chosen with clustering in observations. Based on lat-lon coding.
        """
    
    def brierscore(self, groupers = ['leadtime']):
        """
        Check requirements for the forecast horizon of Buizza. Theirs is based on the crps. No turning the knob of extremity
        Asks a list of groupers, could use custom groupers. Also able to get climatological exceedence if climatology was supplied at initiazion.
        """
        # Merging with climatological file. In case of quantile scoring for the exceeding quantiles. In case of an already e.g. pop for the climatological probability.
        self.frame['doy'] = self.frame['time'].dt.dayofyear
        delayed = self.frame.merge(self.clim, on = ['doy','latitude','longitude'], how = 'left')
        
        if 'pi' in self.frame.columns: # This column comes from the match-and-write, when it is present we are dealing with an already binary observation.
            delayed['rawbrier'] = (delayed['pi'] - delayed['observation'])**2
            delayed['climbrier'] = (delayed['climatology'] - delayed['observation'])**2
        else: # In this case quantile scoring.
            # Boolean comparison cannot be made in one go. because it does not now how to compare N*members agains the climatology of N
            boolcols = list()
            for member in delayed['forecast'].columns:
                name = '_'.join(['bool',str(member)])
                delayed[name] = delayed[('forecast',member)] > delayed['climatology']
                boolcols.append(name)
            delayed['pi'] = delayed[boolcols].sum(axis = 1) / len(delayed['forecast'].columns) # or use .count(axis = 1) if members might be NA
            delayed['oi'] = delayed['observation'] > delayed['climatology']
            delayed['rawbrier'] = (delayed['pi'] - delayed['oi'])**2
            delayed['climbrier'] = ((1 - self.quantile) - delayed['oi'])**2  # Add the climatological score. use self.quantile.
        
        
        # threshold base scoring OLD
        #delayed = self.frame
        #delayed['pi'] = (delayed['forecast'] > threshold).sum(axis = 1) / len(delayed['forecast'].columns) # or use .count(axis = 1) if members might be NA
        #delayed['oi'] = delayed['observation'] > threshold  
        
        grouped = delayed.groupby(groupers)
        return(grouped.mean()[['rawbrier','climbrier']].compute())
        

ddtx = dd.read_hdf('/home/jsn295/ownCloud/Documents/tx_JJA_41r1_3D_max_1.5_degrees_max_169c5dbd7e3a4881928a9f04ca68c400.h5', key = 'intermediate')

self = Comparison(alignedobject = ddtx)
