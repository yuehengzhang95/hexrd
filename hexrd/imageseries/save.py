"""Write imageseries to various formats"""
from __future__ import print_function
import abc

import numpy as np
import h5py
import yaml

def write(ims, fname, fmt, **kwargs):
    """write imageseries to file with options

    *ims* - an imageseries
    *fname* - name of file
    *fmt* - a format string
    *kwargs* - options specific to format
    """
    wcls = _Registry.getwriter(fmt)
    w = wcls(ims, fname, **kwargs)
    w.write()

# Registry

class _RegisterWriter(abc.ABCMeta):

    def __init__(cls, name, bases, attrs):
        abc.ABCMeta.__init__(cls, name, bases, attrs)
        _Registry.register(cls)

class _Registry(object):
    """Registry for imageseries writers"""
    writer_registry = dict()

    @classmethod
    def register(cls, wcls):
        """Register writer class"""
        if wcls.__name__ is not 'Writer':
            cls.writer_registry[wcls.fmt] = wcls

    @classmethod
    def getwriter(cls, name):
        """return instance associated with name"""
        return cls.writer_registry[name]
    #
    pass  # end class

class Writer(object):
    """Base class for writers"""
    __metaclass__ = _RegisterWriter
    fmt = None
    def __init__(self, ims, fname, **kwargs):
        self._ims = ims
        self._shape = ims.shape
        self._dtype = ims.dtype
        self._nframes = len(ims)
        self._meta = ims.metadata
        self._fname = fname
        self._opts = kwargs

    pass # end class

class WriteH5(Writer):
    fmt = 'hdf5'

    def __init__(self, ims, fname, **kwargs):
        """Write imageseries in HDF5 file

           Required Args:
           path - the path in HDF5 file

"""
        Writer.__init__(self, ims, fname, **kwargs)
        self._path = self._opts['path']

    #
    # ======================================== API
    #
    def write(self):
        """Write imageseries to HDF5 file"""
        f = h5py.File(self._fname, "a")
        g = f.create_group(self._path)

        s0, s1 = self._shape
        shape = (self._nframes, s0, s1)

        # for chunking...  results of experimentation
        target_chunk_size = 50000
        bytes_per_pixel = np.dtype(self._dtype).itemsize
        nbytes_per_row = s1*bytes_per_pixel
        if nbytes_per_row < target_chunk_size:
            nrows_to_read = target_chunk_size/nbytes_per_row
            chunks = (1, min(nrows_to_read, s0), s1)
        else:
            ncols_to_read = int(target_chunk_size/float(nbytes_per_row) * s0)
            chunks = (1, 1, ncols_to_read)
        
        # define dataset
        ds = g.create_dataset('images',
                              shape,
                              dtype=self._dtype,
                              chunks=chunks,
                              compression="gzip")

        # write images to data_set
        for i in range(self._nframes):
            ds[i, :, :] = self._ims[i]
           
        # add metadata
        for k, v in self._meta.items():
            g.attrs[k] = v

    pass # end class

class WriteFrameCache(Writer):
    """info from yml file"""
    fmt = 'frame-cache'
    def __init__(self, ims, fname, **kwargs):
        """write yml file with frame cache info

        kwargs has keys:

        cache_file - name of array cache file
        meta - metadata dictionary
        """
        Writer.__init__(self, ims, fname, **kwargs)
        self._thresh = self._opts['threshold']
        self._cache = kwargs['cache_file']

    def _process_meta(self):
        d = {}
        for k, v in self._meta.items():
            if isinstance(v, np.ndarray):
                d[k] = '++np.array'
                d[k + '-array'] = v.tolist()
            else:
                d[k] = v

        return d

    def _write_yml(self):
        datad = {'file': self._cache, 'dtype': str(self._ims.dtype),
                 'nframes': len(self._ims), 'shape': list(self._ims.shape)}
        info = {'data': datad, 'meta': self._process_meta()}
        with open(self._fname, "w") as f:
            yaml.dump(info, f)

    def _write_frames(self):
        """also save shape array as originally done (before yaml)"""
        arrd = dict()
        sh = None
        for i in range(self._nframes):
            frame = self._ims[i]
            mask = frame > self._thresh
            row, col = mask.nonzero()
            arrd['%d_data' % i] = frame[mask]
            arrd['%d_row' % i] = row
            arrd['%d_col' % i] = col
            if sh is None:
                arrd['shape'] = np.array(frame.shape)

        np.savez_compressed(self._cache, **arrd)

    def write(self):
        """writes frame cache for imageseries

        presumes sparse forms are small enough to contain all frames
        """
        self._write_frames()
        self._write_yml()