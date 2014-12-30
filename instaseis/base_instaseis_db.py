#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Abstract base class for all Instaseis database classes.

:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de), 2014
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from future.utils import with_metaclass

from abc import ABCMeta, abstractmethod
from obspy.core import AttribDict
import warnings

from .source import Source, ForceSource, Receiver


class BaseInstaseisDB(with_metaclass(ABCMeta)):
    """
    Abstract base class for all Instaseis database classes.

    Each subclass must provide at least a ``get_seismograms()`` and a
    ``get_info()`` method. The ``get_seismograms_finite_source()`` method must
    not be implemented by all subclasses as it may not be practical for some
    of them.
    """
    @abstractmethod
    def get_seismograms(self, source, receiver, components=("Z", "N", "E"),
                        kind='displacement', remove_source_shift=True,
                        reconvolve_stf=False, return_obspy_stream=True,
                        dt=None, a_lanczos=5):
        """
        Must return either an ObsPy Stream object or a raw numpy array
        depending on the ``return_obspy_stream`` argument.
        """
        pass

    @abstractmethod
    def get_info(self):
        """
        Must return a dictionary with the following keys:

        ``"is_reciprocal"``, ``"components"``, ``"source_depth"``,
        ``"velocity_model"``, ``"attenuation"``, ``"period"``,
        ``"dump_type"``, ``"excitation_type"``, ``"dt"``,
        ``"sampling_rate"``, ``"npts"``, ``"length"``, ``"stf"``,
        ``"slip"``, ``"sliprate"``, ``"src_shift"``, ``"spatial_order"``,
        ``"min_radius"``, ``"max_radius"``, ``"planet_radius"``,
        ``"min_d"``, ``"max_d"``, ``"time_scheme"``, ``"directory"``,
        ``"filesize"``, ``"compiler"``, ``"user"``, ``"format_version"``,
        ``"axisem_version"``, ``"datetime"``
        """
        pass

    def get_seismograms_finite_source(self, sources, receiver,
                                      components=("Z", "N", "E"),
                                      kind='displacement', dt=None,
                                      a_lanczos=5, correct_mu=False,
                                      progress_callback=None):
        """
        """
        raise NotImplementedError

    def _get_seismograms_sanity_checks(self, source, receiver, kind):
        """
        Common sanity checks for the get_seismograms method. Also parses
        source and receiver objects if necessary.

        :param source: instaseis.Source or instaseis.ForceSource object
        :type source: :class:`instaseis.source.Source` or
            :class:`instaseis.source.ForceSource`
        :param receiver: instaseis.Receiver object
        :type receiver: :class:`instaseis.source.Receiver`
        :param kind: 'displacement', 'velocity' or 'acceleration'
        """
        # Attempt to parse them if the types are not correct.
        if not isinstance(source, Source) and \
                not isinstance(source, ForceSource):
            source = Source.parse(source)
        if not isinstance(receiver, Receiver):
            # This only works in the special case of one station, otherwise
            # it has to be called more then once.
            rec = Receiver.parse(receiver)
            if len(rec) != 1:
                raise ValueError("Receiver object/file contains multiple "
                                 "stations. Please parse outside the "
                                 "get_seismograms() function and call in a "
                                 "loop.")
            receiver = rec[0]

        if kind not in ['displacement', 'velocity', 'acceleration']:
            raise ValueError('unknown kind %s' % (kind,))

        if self.info.is_reciprocal:
            if receiver.depth_in_m is not None:
                warnings.warn('Receiver depth cannot be changed when reading '
                              'from reciprocal DB. Using depth from the DB.')
        else:
            if source.depth_in_m is not None:
                warnings.warn('Source depth cannot be changed when reading '
                              'from forward DB. Using depth from the DB.')

        return source, receiver

    @staticmethod
    def _get_band_code(dt):
        """
        Figure out the channel band code. Done as in SPECFEM.
        """
        sr = 1.0 / dt
        if sr <= 0.001:
            band_code = "F"
        elif sr <= 0.004:
            band_code = "C"
        elif sr <= 0.0125:
            band_code = "H"
        elif sr <= 0.1:
            band_code = "B"
        elif sr < 1:
            band_code = "M"
        else:
            band_code = "L"
        return band_code

    @property
    def info(self):
        """
        Returns the info dictionary about the class.
        """
        if not hasattr(self, "__cached_info"):
            self.__cached_info = AttribDict(self.get_info())
        return self.__cached_info

    def __str__(self):
        info = self.info

        return_str = (
            "{db} {reciprocal} Green's function Database (v{"
            "format_version}) "
            "generated with these parameters:\n"
            "\tcomponents           : {components}\n"
            "{source_depth}"
            "\tvelocity model       : {velocity_model}\n"
            "\tattenuation          : {attenuation}\n"
            "\tdominant period      : {period:.3f} s\n"
            "\tdump type            : {dump_type}\n"
            "\texcitation type      : {excitation_type}\n"
            "\ttime step            : {dt:.3f} s\n"
            "\tsampling rate        : {sampling_rate:.3f} Hz\n"
            "\tnumber of samples    : {npts}\n"
            "\tseismogram length    : {length:.1f} s\n"
            "\tsource time function : {stf}\n"
            "\tsource shift         : {src_shift:.3f} s\n"
            "\tspatial order        : {spatial_order}\n"
            "\tmin/max radius       : {min_radius:.1f} - {max_radius:.1f} km\n"
            "\tPlanet radius        : {planet_radius:.1f} km\n"
            "\tmin/max distance     : {min_d:.1f} - {max_d:.1f} deg\n"
            "\ttime stepping scheme : {time_scheme}\n"
            "\tcompiler/user        : {compiler} by {user}\n"
            "\tdirectory/url        : {directory}\n"
            "\tsize of netCDF files : {filesize}\n"
            "\tgenerated by AxiSEM version {axisem_version} at {datetime}\n"
        ).format(
            db=self.__class__.__name__,
            reciprocal="reciprocal" if info.is_reciprocal else "forward",
            components=info.components,
            source_depth=(
                "\tsource depth         : %.2f km\n" %
                info.source_depth) if info.source_depth is not None else "",
            velocity_model=info.velocity_model,
            attenuation=info.attenuation,
            period=info.period,
            dump_type=info.dump_type,
            excitation_type=info.excitation_type,
            dt=info.dt,
            sampling_rate=info.sampling_rate,
            npts=info.npts,
            length=info.length,
            stf=info.stf,
            src_shift=info.src_shift,
            spatial_order=info.spatial_order,
            min_radius=info.min_radius,
            max_radius=info.max_radius,
            planet_radius=info.planet_radius,
            min_d=info.min_d,
            max_d=info.max_d,
            time_scheme=info.time_scheme,
            directory=info.directory,
            filesize=sizeof_fmt(info.filesize),
            compiler=info.compiler,
            user=info.user,
            format_version=info.format_version,
            axisem_version=info.axisem_version,
            datetime=info.datetime
        )
        return return_str


def sizeof_fmt(num):
    """
    Handy formatting for human readable filesizes.

    From http://stackoverflow.com/a/1094933/1657047
    """
    for x in ["bytes", "KB", "MB", "GB"]:
        if num < 1024.0 and num > -1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0
    return "%3.1f %s" % (num, "TB")