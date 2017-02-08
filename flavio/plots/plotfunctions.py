from collections import OrderedDict
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import flavio
from flavio.statistics.functions import delta_chi2, confidence_level
import scipy.optimize
import scipy.interpolate
import scipy.stats
from numbers import Number
from math import sqrt
import warnings

def error_budget_pie(err_dict, other_cutoff=0.03):
    """Pie chart of an observable's error budget.

    Parameters:

    - `err_dict`: Dictionary as return from `flavio.sm_error_budget`
    - `other_cutoff`: If an individual error contribution divided by the total
      error is smaller than this number, it is lumped under "other". Defaults
      to 0.03.

    Note that for uncorrelated parameters, the total uncertainty is the squared
    sum of the individual uncertainties, so the relative size of the wedges does
    not correspond to the relative contribution to the total uncertainty.

    If the uncertainties of individual parameters are correlated, the total
    uncertainty can be larger or smaller than the squared sum of the individual
    uncertainties, so the representation can be misleading.
    """
    err_tot = sum(err_dict.values())
    err_dict_sorted = OrderedDict(sorted(err_dict.items(), key=lambda t: -t[1]))
    labels = []
    fracs = []
    small_frac = 0
    for key, value in err_dict_sorted.items():
        frac = value/err_tot
        if frac > other_cutoff:
            labels.append(flavio.Parameter.get_instance(key).tex)
            fracs.append(frac)
        else:
            small_frac += frac
    if small_frac > 0:
        labels.append('other')
        fracs.append(small_frac)
    def my_autopct(pct):
        return r'{p:.1f}\%'.format(p=pct*err_tot)
    plt.axis('equal')
    return plt.pie(fracs, labels=labels, autopct=my_autopct, wedgeprops = {'linewidth':0.5}, colors=flavio.plots.colors.pastel)


def q2_plot_th_diff(obs_name, q2min, q2max, wc=None, q2steps=100, **kwargs):
    r"""Plot the central theory prediction of a $q^2$-dependent observable
    as a function of $q^2$.

    Parameters:

    - `q2min`, `q2max`: minimum and maximum $q^2$ values in GeV^2
    - `wc` (optional): `WilsonCoefficient` instance to define beyond-the-SM
      Wilson coefficients
    - `q2steps` (optional): number of $q^2$ steps. Defaults to 100. Less is
      faster but less precise.

    Additional keyword arguments are passed to the matplotlib plot function,
    e.g. 'c' for colour.
    """
    obs = flavio.classes.Observable.get_instance(obs_name)
    if obs.arguments != ['q2']:
        raise ValueError(r"Only observables that depend on $q^2$ (and nothing else) are allowed")
    q2_arr = np.arange(q2min, q2max, (q2max-q2min)/(q2steps-1))
    if wc is None:
        wc = flavio.WilsonCoefficients() # SM Wilson coefficients
        obs_arr = [flavio.sm_prediction(obs_name, q2) for q2 in q2_arr]
    else:
        obs_arr = [flavio.np_prediction(obs_name, wc, q2) for q2 in q2_arr]
    ax = plt.gca()
    if 'c' not in kwargs and 'color' not in kwargs:
        kwargs['c'] = 'k'
    ax.plot(q2_arr, obs_arr, **kwargs)

def q2_plot_th_bin(obs_name, bin_list, wc=None, divide_binwidth=False, N=50, **kwargs):
    r"""Plot the binned theory prediction with uncertainties of a
    $q^2$-dependent observable as a function of $q^2$  (in the form of coloured
    boxes).

    Parameters:

    - `bin_list`: a list of tuples containing bin boundaries
    - `wc` (optional): `WilsonCoefficient` instance to define beyond-the-SM
      Wilson coefficients
    - `divide_binwidth` (optional): this should be set to True when comparing
      integrated branching ratios from experiments with different bin widths
      or to theory predictions for a differential branching ratio. It will
      divide all values and uncertainties by the bin width (i.e. dimensionless
      integrated BRs will be converted to integrated differential BRs with
      dimensions of GeV$^{-2}$). Defaults to False.
    - `N` (optional): number of random draws to determine the uncertainty.
      Defaults to 50. Larger is slower but more precise. The relative
      error of the theory uncertainty scales as $1/\sqrt{2N}$.

    Additional keyword arguments are passed to the matplotlib add_patch function,
    e.g. 'fc' for face colour.
    """
    obs = flavio.classes.Observable.get_instance(obs_name)
    if obs.arguments != ['q2min', 'q2max']:
        raise ValueError(r"Only observables that depend on q2min and q2max (and nothing else) are allowed")
    if wc is None:
        wc = flavio.WilsonCoefficients() # SM Wilson coefficients
        obs_dict = {bin_: flavio.sm_prediction(obs_name, *bin_) for bin_ in bin_list}
        obs_err_dict = {bin_: flavio.sm_uncertainty(obs_name, *bin_, N=N) for bin_ in bin_list}
    else:
        obs_dict = {bin_:flavio.np_prediction(obs_name, wc, *bin_) for bin_ in bin_list}
        obs_err_dict = {bin_: flavio.np_uncertainty(obs_name, wc, *bin_, N=N) for bin_ in bin_list}
    ax = plt.gca()
    for _i, (bin_, central_) in enumerate(obs_dict.items()):
        q2min, q2max = bin_
        err = obs_err_dict[bin_]
        if divide_binwidth:
            err = err/(q2max-q2min)
            central = central_/(q2max-q2min)
        else:
            central = central_
        if 'fc' not in kwargs and 'facecolor' not in kwargs:
            kwargs['fc'] = flavio.plots.colors.pastel[3]
        if 'linewidth' not in kwargs and 'lw' not in kwargs:
            kwargs['lw'] = 0
        if _i > 0:
            # the label should only be set for one (i.e. the first)
            # of the boxes, otherwise it will appear multiply in the legend
            kwargs.pop('label', None)
        ax.add_patch(patches.Rectangle((q2min, central-err), q2max-q2min, 2*err,**kwargs))

def q2_plot_exp(obs_name, col_dict=None, divide_binwidth=False, include_measurements=None,
                include_bins=None, exclude_bins=None,
                **kwargs):
    r"""Plot all existing experimental measurements of a $q^2$-dependent
    observable as a function of $q^2$  (in the form of coloured crosses).

    Parameters:

    - `col_dict` (optional): a dictionary to assign colours to specific
      experiments, e.g. `{'BaBar': 'b', 'Belle': 'r'}`
    - `divide_binwidth` (optional): this should be set to True when comparing
      integrated branching ratios from experiments with different bin widths
      or to theory predictions for a differential branching ratio. It will
      divide all values and uncertainties by the bin width (i.e. dimensionless
      integrated BRs will be converted to integrated differential BRs with
      dimensions of GeV$^{-2}$). Defaults to False.
    - `include_measurements` (optional): a list of strings with measurement
      names (see measurements.yml) to include in the plot. By default, all
      existing measurements will be included.
    - `include_bins` (optional): a list of bins (as tuples of the bin
      boundaries) to include in the plot. By default, all measured bins
      will be included. Should not be specified simultaneously with
      `exclude_bins`.
    - `exclude_bins` (optional): a list of bins (as tuples of the bin
      boundaries) not to include in the plot. By default, all measured bins
      will be included. Should not be specified simultaneously with
      `include_bins`.

    Additional keyword arguments are passed to the matplotlib errorbar function,
    e.g. 'c' for colour.
    """
    obs = flavio.classes.Observable.get_instance(obs_name)
    if obs.arguments != ['q2min', 'q2max']:
        raise ValueError(r"Only observables that depend on q2min and q2max (and nothing else) are allowed")
    _experiment_labels = [] # list of experiments appearing in the plot legend
    for m_name, m_obj in flavio.Measurement.instances.items():
        if include_measurements is not None and m_name not in include_measurements:
            continue
        obs_name_list = m_obj.all_parameters
        obs_name_list_binned = [o for o in obs_name_list if isinstance(o, tuple) and o[0]==obs_name]
        if not obs_name_list_binned:
            continue
        central = m_obj.get_central_all()
        err = m_obj.get_1d_errors_rightleft()
        x = []
        y = []
        dx = []
        dy_lower = []
        dy_upper = []
        for _, q2min, q2max in obs_name_list_binned:
            if include_bins is not None:
                if exclude_bins is not None:
                    raise ValueError("Please only specify include_bins or exclude_bins, not both")
                elif (q2min, q2max) not in include_bins:
                    continue
            elif exclude_bins is not None:
                if (q2min, q2max) in exclude_bins:
                    continue
            c = central[(obs_name, q2min, q2max)]
            e_right, e_left = err[(obs_name, q2min, q2max)]
            if divide_binwidth:
                c = c/(q2max-q2min)
                e_left = e_left/(q2max-q2min)
                e_right = e_right/(q2max-q2min)
            ax=plt.gca()
            x.append((q2max+q2min)/2.)
            dx.append((q2max-q2min)/2)
            y.append(c)
            dy_lower.append(e_left)
            dy_upper.append(e_right)
        kwargs_m = kwargs.copy() # copy valid for this measurement only
        if x or y: # only if a data point exists
            if col_dict is not None:
                if m_obj.experiment in col_dict:
                    col = col_dict[m_obj.experiment]
                    kwargs_m['c'] = col
            if 'label' not in kwargs_m:
                if m_obj.experiment not in _experiment_labels:
                    # if there is no plot legend entry for the experiment yet,
                    # add it and add the experiment to the list keeping track
                    # of existing labels (we don't want an experiment to appear
                    # twice in the legend)
                    kwargs_m['label'] = m_obj.experiment
                    _experiment_labels.append(m_obj.experiment)
            ax.errorbar(x, y, yerr=[dy_lower, dy_upper], xerr=dx, fmt='.', **kwargs_m)


def density_contour_data(x, y, covariance_factor=None, n_bins=None, n_sigma=(1, 2)):
    r"""Generate the data for a plot with confidence contours of the density
    of points (useful for MCMC analyses).

    Parameters:

    - `x`, `y`: lists or numpy arrays with the x and y coordinates of the points
    - `covariance_factor`: optional, numerical factor to tweak the smoothness
    of the contours. If not specified, estimated using Scott's/Silverman's rule.
    The factor should be between 0 and 1; larger values means more smoothing is
    applied.
    - n_bins: number of bins in the histogram created as an intermediate step.
      this usually does not have to be changed.
    - n_sigma: integer or iterable of integers specifying the contours
      corresponding to the number of sigmas to be drawn. For instance, the
      default (1, 2) draws the contours containing approximately 68 and 95%
      of the points, respectively.
    """
    if n_bins is None:
        n_bins = min(10*int(sqrt(len(x))), 200)
    f_binned, x_edges, y_edges = np.histogram2d(x, y, normed=True, bins=n_bins)
    x_centers = (x_edges[:-1] + x_edges[1:])/2.
    y_centers = (y_edges[:-1] + y_edges[1:])/2.
    x_mean = np.mean(x_centers)
    y_mean = np.mean(y_centers)
    dataset = np.vstack([x, y])

    d = 2 # no. of dimensions

    if covariance_factor is None:
        # Scott's/Silverman's rule
        n = len(x) # no. of data points
        _covariance_factor = n**(-1/6.)
    else:
        _covariance_factor = covariance_factor

    cov = np.cov(dataset) * _covariance_factor**2
    gaussian_kernel = scipy.stats.multivariate_normal(mean=[x_mean, y_mean], cov=cov)

    x_grid, y_grid = np.meshgrid(x_centers, y_centers)
    xy_grid = np.vstack([x_grid.ravel(), y_grid.ravel()])
    f_gauss = gaussian_kernel.pdf(xy_grid.T)
    f_gauss = np.reshape(f_gauss, (len(x_centers), len(y_centers))).T

    f = scipy.signal.fftconvolve(f_binned, f_gauss, mode='same').T
    f = f/f.sum()

    def find_confidence_interval(x, pdf, confidence_level):
        return pdf[pdf > x].sum() - confidence_level
    def get_level(n):
        return scipy.optimize.brentq(find_confidence_interval, 0., 1.,
                                     args=(f.T, confidence_level(n)))
    if isinstance(n_sigma, Number):
        levels = [get_level(n_sigma)]
    else:
        levels = [get_level(m) for m in sorted(n_sigma)]

    # replace negative or zero values by a tiny number before taking the log
    f[f <= 0] = 1e-32
    # convert probability to -2*log(probability), i.e. a chi^2
    f = -2*np.log(f)
    # convert levels to chi^2 and make the mode equal chi^2=0
    levels = list(-2*np.log(levels) - np.min(f))
    f = f - np.min(f)

    return {'x': x_grid, 'y': y_grid, 'z': f, 'levels': levels}


def density_contour(x, y, covariance_factor=None, n_bins=None, n_sigma=(1, 2),
                    **kwargs):
    r"""A plot with confidence contours of the density of points
    (useful for MCMC analyses).

    Parameters:

    - `x`, `y`: lists or numpy arrays with the x and y coordinates of the points
    - `covariance_factor`: optional, numerical factor to tweak the smoothness
    of the contours. If not specified, estimated using Scott's/Silverman's rule.
    The factor should be between 0 and 1; larger values means more smoothing is
    applied.
    - n_bins: number of bins in the histogram created as an intermediate step.
      this usually does not have to be changed.
    - n_sigma: integer or iterable of integers specifying the contours
      corresponding to the number of sigmas to be drawn. For instance, the
      default (1, 2) draws the contours containing approximately 68 and 95%
      of the points, respectively.

    All remaining keyword arguments are passed to the `contour` function
    and allow to control the presentation of the plot (see docstring of
    `flavio.plots.plotfunctions.contour`).
    """
    data = density_contour_data(x=x, y=y, covariance_factor=covariance_factor,
                                n_bins=n_bins, n_sigma=n_sigma)
    data.update(kwargs) #  since we cannot do **data, **kwargs in Python <3.5
    return contour(**data)


def likelihood_countour_data(log_likelihood, x_min, x_max, y_min, y_max,
              n_sigma=1, steps=20):
    r"""Generate data required to plot coloured confidence contours (or bands)
    given a log likelihood function.

    Parameters:

    - `log_likelihood`: function returning the logarithm of the likelihood.
      Can e.g. be the method of the same name of a FastFit instance.
    - `x_min`, `x_max`, `y_min`, `y_max`: data boundaries
    - `n_sigma`: plot confidence level corresponding to this number of standard
      deviations. Either a number (defaults to 1) or a tuple to plot several
      contours.
    - `steps`: number of grid steps in each dimension (total computing time is
      this number squared times the computing time of one `log_likelihood` call!)
     """
    _x = np.linspace(x_min, x_max, steps)
    _y = np.linspace(y_min, y_max, steps)
    x, y = np.meshgrid(_x, _y)
    @np.vectorize
    def chi2_vect(x, y): # needed for evaluation on meshgrid
        return -2*log_likelihood([x,y])
    z = chi2_vect(x, y)
    z = z - np.min(z) # subtract the best fit point (on the grid)

    # get the correct values for 2D confidence/credibility contours for n sigma
    if isinstance(n_sigma, Number):
        levels = [delta_chi2(n_sigma, dof=2)]
    else:
        levels = [delta_chi2(n, dof=2) for n in n_sigma]
    return {'x': x, 'y': y, 'z': z, 'levels': levels}


def likelihood_countour(log_likelihood, x_min, x_max, y_min, y_max,
              n_sigma=1, steps=20,
              **kwargs):
    r"""Plot coloured confidence contours (or bands) given a log likelihood
    function.

    Parameters:

    - `log_likelihood`: function returning the logarithm of the likelihood.
      Can e.g. be the method of the same name of a FastFit instance.
    - `x_min`, `x_max`, `y_min`, `y_max`: data boundaries
    - `n_sigma`: plot confidence level corresponding to this number of standard
      deviations. Either a number (defaults to 1) or a tuple to plot several
      contours.
    - `steps`: number of grid steps in each dimension (total computing time is
      this number squared times the computing time of one `log_likelihood` call!)

    All remaining keyword arguments are passed to the `contour` function
    and allow to control the presentation of the plot (see docstring of
    `flavio.plots.plotfunctions.contour`).
    """
    data = likelihood_countour_data(log_likelihood=log_likelihood,
                                x_min=x_min, x_max=x_max,
                                y_min=y_min, y_max=y_max,
                                n_sigma=n_sigma, steps=steps)
    data.update(kwargs) #  since we cannot do **data, **kwargs in Python <3.5
    return contour(**data)

# alias for backward compatibility
def band_plot(log_likelihood, x_min, x_max, y_min, y_max,
              n_sigma=1, steps=20, **kwargs):
    r"""This is an alias for `likelihood_countour` which is present for
    backward compatibility."""
    warnings.warn("The `band_plot` function has been replaced "
                  "by `likelihood_contour` (or "
                  "`likelihood_countour_data` in conjunction with `contour`) "
                  "and might be removed in the future. "
                  "Please update your code.", FutureWarning)
    valid_args = likelihood_countour_data.__code__.co_varnames
    data_kwargs = {k:v for k,v in kwargs.items() if k in valid_args}
    if 'pre_calculated_z' not in kwargs:
        contour_kwargs = likelihood_countour_data(log_likelihood,
                      x_min, x_max, y_min, y_max,
                      n_sigma, steps, **data_kwargs)
    else:
        contour_kwargs = {}
        nx, ny = kwargs['pre_calculated_z'].shape
        _x = np.linspace(x_min, x_max, nx)
        _y = np.linspace(y_min, y_max, ny)
        x, y = np.meshgrid(_x, _y)
        contour_kwargs['x'] = x
        contour_kwargs['y'] = y
        contour_kwargs['z'] = kwargs['pre_calculated_z']
        if isinstance(n_sigma, Number):
            contour_kwargs['levels'] = [delta_chi2(n_sigma, dof=2)]
        else:
            contour_kwargs['levels'] = [delta_chi2(n, dof=2) for n in n_sigma]
    valid_args = contour.__code__.co_varnames
    contour_kwargs.update({k:v for k,v in kwargs.items() if k in valid_args})
    contour(**contour_kwargs)
    return contour_kwargs['x'], contour_kwargs['y'], contour_kwargs['z']


def contour(x, y, z, levels,
              interpolation_factor=1,
              interpolation_order=2,
              col=0, label=None,
              filled=True,
              contour_args={}, contourf_args={}):
    r"""Plot coloured confidence contours (or bands) given numerical input
    arrays.

    Parameters:

    - `x`, `y`: 2D arrays containg x and y values as returned by numpy.meshgrid
    - `z` value of the function to plot. 2D array in the same shape as `x` and
      `y`. The lowest value of the function should be 0 (i.e. the best fit
      point).
    - levels: list of function values where to draw the contours. They should
      be positive and in ascending order.
    - `interpolation factor` (optional): in between the points on the grid,
      the functioncan be interpolated to get smoother contours.
      This parameter sets the number of subdivisions (default: 1, i.e. no
      interpolation). It should be larger than 1.
    - `col` (optional): number between 0 and 9 to choose the color of the plot
      from a predefined palette
    - `label` (optional): label that will be added to a legend created with
       maplotlib.pyplot.legend()
    - `filled` (optional): if False, contours will be drawn without shading
    - `contour_args`: dictionary of additional options that will be passed
       to matplotlib.pyplot.contour() (that draws the contour lines)
    - `contourf_args`: dictionary of additional options that will be passed
       to matplotlib.pyplot.contourf() (that paints the contour filling).
       Ignored if `filled` is false.
    """
    if interpolation_factor > 1:
        x = scipy.ndimage.zoom(x, zoom=interpolation_factor, order=1)
        y = scipy.ndimage.zoom(y, zoom=interpolation_factor, order=1)
        z = scipy.ndimage.zoom(z, zoom=interpolation_factor, order=interpolation_order)
    if not isinstance(col, int):
        _col = 0
    else:
        _col = col
    _contour_args = {}
    _contourf_args = {}
    _contour_args['colors'] = [flavio.plots.colors.set1[_col]]
    _contour_args['linewidths'] = 0.6
    N = len(levels)
    _contourf_args['colors'] = [flavio.plots.colors.pastel[_col] # RGB
                                       + (max(1-n/N, 0),) # alpha, decreasing for contours
                                       for n in range(N)]
    _contour_args['linestyles'] = 'solid'
    _contour_args.update(contour_args)
    _contourf_args.update(contourf_args)
    # for the filling, need to add zero contour
    levelsf = [np.min(z)] + levels
    ax = plt.gca()
    if filled:
        ax.contourf(x, y, z, levels=levelsf, **_contourf_args)
    CS = ax.contour(x, y, z, levels=levels, **_contour_args)
    if label is not None:
        CS.collections[0].set_label(label)


def flavio_branding(x=0.8, y=0.94, version=True):
    """Displays a little box containing 'flavio'"""
    props = dict(facecolor='white', alpha=0.4, lw=0)
    ax = plt.gca()
    text = r'\textsf{\textbf{flavio}}'
    if version:
        text += r'\textsf{\scriptsize{ v' + flavio.__version__ + '}}'
    ax.text(x, y, text, transform=ax.transAxes, fontsize=12, verticalalignment='top', bbox=props, alpha=0.4)

def flavio_box(x_min, x_max, y_min, y_max):
    ax = plt.gca()
    ax.add_patch(patches.Rectangle((x_min, y_min), x_max-x_min, y_max-y_min, facecolor='#ffffff', edgecolor='#666666', alpha=0.5, ls=':', lw=0.7))

def smooth_histogram(data, bandwidth=None, col=None, label=None, plotargs={}, fillargs={}):
    """A smooth histogram based on a Gaussian kernel density estimate.

    Parameters:

    - `data`: input array
    - `bandwidth`: (optional) smoothing bandwidth for the Gaussian kernel
    - `col`: (optional) integer to select one of the colours from the default
      palette
    - `plotargs`: keyword arguments passed to the `plot` function
    - `fillargs`: keyword arguments passed to the `fill_between` function
    """
    kde = flavio.statistics.probability.GaussianKDE(data, bandwidth=bandwidth)
    x = kde.x
    y = kde.y_norm
    ax = plt.gca()
    _plotargs = {}
    _fillargs = {}
    # default values
    _plotargs['linewidth'] = 0.6
    if label is not None:
        _plotargs['label'] = label
    if col is None:
        _plotargs['color'] = flavio.plots.colors.set1[0]
        _fillargs['facecolor'] = flavio.plots.colors.pastel[0]
    else:
        _plotargs['color'] = flavio.plots.colors.set1[col]
        _fillargs['facecolor'] = flavio.plots.colors.pastel[col]
    _fillargs.update(fillargs)
    _plotargs.update(plotargs)
    ax.plot(x, y, **_plotargs)
    ax.fill_between(x, 0, y, **_fillargs)
