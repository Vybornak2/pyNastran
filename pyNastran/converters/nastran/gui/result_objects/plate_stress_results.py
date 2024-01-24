from __future__ import annotations
from collections import defaultdict
import numpy as np
from typing import Optional, TYPE_CHECKING

from pyNastran.utils.mathematics import get_abs_max
from pyNastran.gui.gui_objects.gui_result import GuiResultCommon
from pyNastran.femutils.utils import pivot_table, abs_nan_min_max # abs_min_max
from pyNastran.bdf.utils import write_patran_syntax_dict

from .displacement_results import VectorResultsCommon
if TYPE_CHECKING:
    from pyNastran.bdf.bdf import BDF
    from pyNastran.op2.tables.oes_stressStrain.real.oes_plates import RealPlateArray

#pcomp_stress = ['o11', 'o22', 't12', 't1z', 't2z', 'oangle', 'Max Principal', 'minor', 'ovm', 'omax_shear']
#pcomp_strain = ['e11', 'e22', 'e12', 'e1z', 'e2z', 'eangle', 'Max Principal', 'minor', 'evm', 'emax_shear']
col_axis = 1

class PlateResults2(VectorResultsCommon):
    def __init__(self,
                 subcase_id: int,
                 model: BDF,
                 node_id: np.ndarray,
                 element_id: np.ndarray,
                 cases: list[RealPlateArray],
                 result: str,
                 is_fiber_distance: bool,
                 eid_to_nid_map: dict[int, list[int]],
                 #dim_max: float,
                 data_format: str='%g',
                 nlabels=None, labelsize=None, ncolors=None,
                 colormap: str='',
                 set_max_min: bool=False,
                 uname: str='CompositeResults2'):
        assert isinstance(is_fiber_distance, bool), is_fiber_distance
        GuiResultCommon.__init__(self)
        self.layer_indices = (-1, )  # All
        self.is_fiber_distance = is_fiber_distance
        i = -1
        name = None

        # slice off the methods (from the boolean) and then pull the 0th one
        self.min_max_method = self.has_derivation_transform(i, name)[1]['derivation'][0]
        self.transform = self.has_coord_transform(i, name)[1][0]
        self.nodal_combine = self.has_nodal_combine_transform(i, name)[1][0]
        #assert len(element_id) >= self.case.

        self.is_dense = False
        self.dim = cases[0].data.ndim
        for case in cases:
            assert case.data.ndim == 3, case.data.shape

        self.subcase_id = subcase_id
        self.is_stress = case.is_stress
        self.eid_to_nid_map = eid_to_nid_map
        if self.is_stress:
            self.iresult_map = {
                #0 : 'FiberCurvature',
                0 : 'FiberDistance',
                1 : 'XX Stress',
                2 : 'YY Stress',
                3 : 'XY Stress',
                4 : 'Theta',
                5 : 'MaxPrincipal Stress',
                6 : 'MinPrincipal Stress',
                7 : 'AbsPrincipal Stress',  # special
                8 : 'von Mises Stress',     # special
                9 : 'Max Shear Stress',     # special
            }
        else:
            self.iresult_map = {
                #0 : 'FiberCurvature',
                0 : 'FiberDistance',
                1 : 'XX Strain',
                2 : 'YY Strain',
                3 : 'XY Strain',
                4 : 'Theta',
                5 : 'MaxPrincipal Strain',
                6 : 'MinPrincipal Strain',
                7 : 'AbsPrincipal Strain', # special
                8 : 'von Mises Strain',    # special
                9 : 'Max Shear Strain',    # special
            }
        if self.is_fiber_distance:
            self.layer_map = {
                0: 'Both',
                1: 'Bottom',
                2: 'Top',
            }
        else:
            self.layer_map = {
                0: 'Both',  # wut?  This makes no sense...
                1: 'Mean',
                2: 'Slope',
            }
            self.iresult_map[0] = 'FiberCurvature'

        #if dim_max == 0.0:
            #dim_max = 1.0
        #self.dim_max = dim_max
        self.linked_scale_factor = False

        self.data_format = data_format

        #  global ids
        self.model = model
        self.node_id = node_id
        self.element_id = element_id

        # local case object
        self.cases = cases
        self.result = result

        self.data_type = case.data.dtype.str # '<c8', '<f4'
        self.is_real = True if self.data_type in ['<f4', '<f8'] else False
        #self.is_real = dxyz.data.dtype.name in {'float32', 'float64'}
        self.is_complex = not self.is_real

        ntimes = case.data.shape[0]
        #nscale = ntimes
        #if self.linked_scale_factor:
            #nscale = 1

        #def fscales():
            #return [None] * nscale
        def ftimes():
            return [None] * ntimes
        def fphases():
            return np.zeros(ntimes, dtype='float64')

        #self.default_scales = defaultdict(fscales)
        #self.scales = defaultdict(fscales)
        self.default_mins = defaultdict(ftimes)
        self.default_maxs = defaultdict(ftimes)
        self.mins = defaultdict(ftimes)
        self.maxs = defaultdict(ftimes)
        self.phases = defaultdict(fphases)

        self.data_formats = [self.data_format]
        self.headers = ['PlateResult2'] * ntimes

        self.nlabels = None
        self.labelsize = None
        self.ncolors = None
        self.colormap = colormap

        self.uname = uname
        self.location = 'centroid'

    def _get_default_tuple_indices(self):
        out = tuple(np.array(self._get_default_layer_indicies()) - 1)
        return out

    def _get_default_layer_indicies(self):
        default_indices = list(self.layer_map.keys())
        default_indices.remove(0)
        return default_indices

    def set_sidebar_args(self,
                         itime: str, res_name: str,
                         min_max_method: str='', # Absolute Max
                         transform: str='', # Material
                         methods_keys: Optional[list[int]]=None,
                         # unused
                         nodal_combine: str='', # Centroid
                         **kwargs) -> None:
        assert len(kwargs) == 0, kwargs
        transforms = self.has_coord_transform(itime, res_name)[1]
        min_max_methods = self.has_derivation_transform(itime, res_name)[1]['derivation']
        combine_methods = self.has_nodal_combine_transform(itime, res_name)[1]

        transform = transform if transform else transforms[0]
        min_max_method = min_max_method if min_max_method else min_max_methods[0]
        nodal_combine = nodal_combine if nodal_combine else combine_methods[0]

        assert transform in transforms, transform
        assert min_max_method in min_max_methods, min_max_method
        assert nodal_combine in combine_methods, nodal_combine

        #sidebar_kwargs = {
            #'min_max_method': min_max_method,
            #'transform': coord,
            #'nodal_combine': nodal_combine,
            #'methods_keys': keys_b,
        #}
        # if Both is selected, only use Both
        # methods = ['Both', 'Top', 'Bottom']
        default_indices = self._get_default_layer_indicies()
        if methods_keys is None or len(methods_keys) == 0:
            # default; All
            indices = default_indices
        elif 0 in methods_keys: # Both
            # include all components b/c All is selected
            indices = default_indices
        else:
            # no 0 (Both) in methods_keys
            # update the indices to correspond to the array
            #methods_keys.sort()
            indices = methods_keys
        self.layer_indices = tuple(np.array(indices, dtype='int32') - 1)
        #self.layer_indices = (1, )

        # doesn't matter cause it's already nodal
        assert min_max_method in min_max_methods, min_max_method
        assert nodal_combine in combine_methods, nodal_combine
        self.min_max_method = min_max_method
        self.nodal_combine = nodal_combine
        self.transform = transform

    def has_methods_table(self, i: int, res_name: str) -> bool:
        return True
    def has_coord_transform(self, i: int, res_name: str) -> tuple[bool, list[str]]:
        return True, ['Material']
    def has_derivation_transform(self, i: int, case_tuple: str) -> tuple[bool, list[str]]:
        """min/max/avg"""
        #(itime, iresult, header) = case_tuple
        out = {
            'tooltip': 'Method to reduce multiple layers (top/btm) into a single nodal/elemental value',
            'derivation': ['Absolute Max', 'Min', 'Max', 'Mean', 'Std. Dev.', 'Difference',
                           #'Derive/Average'
                           ],
        }
        return True, out
    def has_nodal_combine_transform(self, i: int, res_name: str) -> tuple[bool, list[str]]:
        """elemental -> nodal"""
        return True, ['Centroid'] # 'Nodal Max'
        #return True, ['Absolute Max', 'Min', 'Max']

    def get_annotation(self, itime: int, case_tuple: str) -> str:
        """
        A header is the thingy that goes in the lower left corner
        title = 'Plate Stress'
        method = 'Absolute Max'
        header = 'Static'
        nodal_combine = 'Nodal Max'
        returns 'Plate Stress Both (Absolute Max; Nodal Max, Static): sigma11'
        """
        # overwrite itime based on linked_scale factor
        (itime, iresult, header) = case_tuple
        itime, unused_case_flag = self.get_case_flag(case_tuple)

        default_indices = self._get_default_tuple_indices() # 0-based
        if self.layer_indices == default_indices:
            layer_str = 'Both'
        else:
            if self.layer_indices == (0, ):
                layer_str = self.layer_map[0]  # Bottom
            elif self.layer_indices == (1, ):
                layer_str = self.layer_map[1]  # Top
            else:
                raise RuntimeError(self.layer_indices)
            self.layer_indices

        result = get_plate_result(self.result, iresult, index=1)

        #'Compostite Plate Stress (Absolute Max; Static): sigma11'
        annotation_label = f'{self.title}; {layer_str} ({self.min_max_method}, {self.nodal_combine}, {header}): {result}'
        #return self.uname
        return annotation_label

    def get_default_min_max(self, itime: int,
                            case_tuple: str) -> tuple[float, float]:
        #(itime, iresult, unused_header) = case_tuple
        itime, case_flag = self.get_case_flag(case_tuple)
        mins = self.default_mins[case_flag]
        maxs = self.default_maxs[case_flag]
        if mins[itime] is not None and maxs[itime] is not None:
            return mins[itime], maxs[itime]

        datai = self._get_real_data(case_tuple)
        mins[itime] = np.nanmin(datai)
        maxs[itime] = np.nanmax(datai)
        return mins[itime], maxs[itime]

    def get_min_max(self, itime, case_tuple) -> tuple[float, float]:
        #(itime, iresult, header) = case_tuple
        itime, case_flag = self.get_case_flag(case_tuple)
        mins = self.mins[case_flag]
        maxs = self.maxs[case_flag]
        if mins[itime] is not None and maxs[itime] is not None:
            return mins[itime], maxs[itime]

        # save the defaults if they're not None
        mini2, maxi2 = self.get_default_min_max(itime, case_tuple)
        if mini2 is not None:
            mins[itime] = mini2
        if maxi2 is not None:
            maxs[itime] = maxi2
        return mins[itime], maxs[itime]

    def set_min_max(self, itime, case_tuple, min_value, max_value) -> tuple[float, float]:
        #(itime, iresult, header) = case_tuple
        itime, case_flag = self.get_case_flag(case_tuple)

        mins = self.mins[case_flag]
        maxs = self.maxs[case_flag]
        mins[itime] = min_value
        maxs[itime] = max_value

    def get_case_flag(self, case_tuple: tuple[int, int, str]) -> tuple[int,
                                                                       tuple[int, int, tuple, str, str]]:
        """
        itime = 0
        iresult = 0 # o11
        layer_indices = (1, 2)
        min_max_method = 'Absolute Max'
        nodal_combine = 'Centroid'
        """
        (itime, iresult, header) = case_tuple
        #if self.is_linked_scale_factor:
            #itime = 0

        return itime, (itime, iresult, self.layer_indices, self.min_max_method, self.nodal_combine)

    def get_default_legend_title(self, itime: int, case_tuple: str) -> str:
        (itime, iresult, header) = case_tuple
        #method_ = 'Composite Stress Layers:' if self.is_stress else 'Composite Strain Layers:'
        #self.layer_indices
        results = list(self.result.values())
        #method = method_ + ', '.join(str(idx) for idx in (self.layer_indices+1))
        #method = method.strip()
        #title = f'{self.title} {method}'
        title = results[iresult][0]  # sidebar label=legend
        return title
    def set_legend_title(self, itime: int, res_name: str,
                         title: str) -> None:
        self.title = title
    def get_legend_title(self, itime: int, case_tuple: str):
        """Composite Stress Layers: 1, 2, 3, 4"""
        (itime, iresult, header) = case_tuple
        #method_ = 'Composite Stress Layers:' if self.is_stress else 'Composite Strain Layers:'
        #self.layer_indices
        #self.result
        #method = method_ + ', '.join(str(idx) for idx in (self.layer_indices+1))
        #title = f'{self.title} {method}'
        result = get_plate_result(self.result, iresult, index=0)
        return result

    def _get_real_data(self, case_tuple: int) -> np.ndarray:
        (itime, iresult, header) = case_tuple

        # [itime, ielement, ilayer, iresult
        #self.centroid_eids = np.hstack(centroid_elements_list)
        #self.centroid_data = np.hstack(data_list)

        ilayer = self.layer_indices
        if self.layer_indices == (-1, ):
            self.layer_indices = (0, 1)

        #self.case.get_headers()
        #[fiber_dist, 'oxx', 'oyy', 'txy', 'angle', 'omax', 'omin', ovm]
        results = list(self.result.keys())
        neids = self.centroid_data.shape[1]

        if self.nodal_combine == 'Centroid':
            # [itime, ielement, ilayer, iresult]
            #'eabs' : ('eAbs Principal', -1),
            #'von_mises' : ('ϵ von Mises', -2),
            #'max_shear' : ('𝛾max', -3),
            if iresult == 'abs_principal': # abs max
                omax = self.centroid_data[itime, :, ilayer, 5]
                omin = self.centroid_data[itime, :, ilayer, 6]
                abs_principal = get_abs_max(omin, omax, dtype=omin.dtype)
                #'exx' : ('Strain XX', 1),
                #'eyy' : ('Strain YY', 2),
                #'exy' : ('Strain XY', 3),
                data = abs_principal
            elif iresult == 'von_mises': # von mises
                oxx = self.centroid_data[itime, :, ilayer, 1]
                oyy = self.centroid_data[itime, :, ilayer, 2]
                txy = self.centroid_data[itime, :, ilayer, 3]
                ovm = np.sqrt(oxx**2 + oyy**2 - oxx*oyy +3*(txy**2) )
                data = ovm
            elif iresult == 'max_shear':
                # not checked for strain
                omax = self.centroid_data[itime, :, ilayer, 5]
                omin = self.centroid_data[itime, :, ilayer, 6]
                max_shear = (omax - omin) / 2.
                data = max_shear
            #elif iresult < 0:
                #data = self.centroid_data[itime, :, ilayer, 0] * 0. + iresult
            else:
                data = self.centroid_data[itime, :, ilayer, iresult].copy()
        #elif self.nodal_combine == 'Nodal Max':
        #elif self.nodal_combine == 'Nodal Min':
        #elif self.nodal_combine == 'Nodal Mean':
        #elif self.nodal_combine == 'Nodal Abs Max':
        #elif self.nodal_combine == 'Nodal Std. Dev.':
        #elif self.nodal_combine == 'Nodal Difference':
        else:
            raise RuntimeError(self.nodal_combine)

        assert len(data.shape) == 2, data.shape

        # multiple plies
        # ['Absolute Max', 'Min', 'Max', 'Derive/Average']
        ## TODO: why is this shape backwards?!!!
        ## [ilayer, ielement] ???
        axis = 0
        if self.min_max_method == 'Absolute Max':
            data2 = abs_nan_min_max(data, axis=axis)
        elif self.min_max_method == 'Min':
            data2 = np.nanmin(data, axis=axis)
        elif self.min_max_method == 'Max':
            data2 = np.nanmax(data, axis=axis)
        elif self.min_max_method == 'Mean':  #   (Derive/Average)???
            data2 = np.nanmean(data, axis=axis)
        elif self.min_max_method == 'Std. Dev.':
            data2 = np.nanstd(data, axis=axis)
        elif self.min_max_method == 'Difference':
            data2 = np.nanmax(data, axis=axis) - np.nanmin(data, axis=axis)
        #elif self.min_max_method == 'Max Over Time':
            #data2 = np.nanmax(data, axis=axis) - np.nanmin(data2, axis=axis)
        #elif self.min_max_method == 'Derive/Average':
            #data2 = np.nanmax(data, axis=1)
        else:  # pragma: no cover
            raise NotImplementedError(self.min_max_method)

        # TODO: hack to try and debug things...
        assert data2.shape == (neids, )
        #data4 = eids_new.astype('float32')
        return data2

    #def _get_complex_data(self, itime: int) -> np.ndarray:
        #return self._get_real_data(itime)
        #if self.is_translation:
            #datai = self.dxyz.data[itime, :, :3]
            #assert datai.shape[1] == 3, datai.shape
        #else:
            #datai = self.dxyz.data[itime, :, 3:]
            #assert datai.shape[1] == 3, datai.shape
        #return datai

    def get_result(self, itime: int, case_tuple: str,
                   method: str='',
                   return_dense: bool=True) -> np.ndarray:
        """
        gets the 'typical' result which is a vector
         - GuiResult:           fringe; (n,)   array
         - DisplacementResults: vector; (n, 3) array

        Parameters
        ----------
        return_dense: bool
            Rreturns the data array in a way that the gui can use.
            Handles the null result case (e.g; SPC forces only
            at the SPC location).
        """
        #method = self._update_method(itime, case_tuple, method)
        assert self.is_real
        # multiple results
        # .0006 -> 0.0
        # .057 -> 0.0123
        # min
        data = self._get_real_data(case_tuple)
        #dxyz = data[itime, :, :]
        #else:
        #data = self._get_complex_data(case_tuple)
        assert len(data.shape) == 1, data.shape

        return_sparse = not return_dense
        if return_sparse or self.is_dense:
            return data

        if self.get_location(0, 0) == 'node':
            nnode = len(self.node_id)
            result_out = np.full(nnode, np.nan, dtype=data.dtype)
            result_out[self.inode] = data
        else:
            nelement = len(self.element_id)
            result_out = np.full(nelement, np.nan, dtype=data.dtype)
            result_out[self.ielement_centroid] = data
        return result_out

    def get_default_scale(self, itime: int, res_name: str) -> float:
        return None
    def get_scale(self, itime: int, res_name: str) -> float:
        return 0.0
    def set_scale(self, itime: int, res_name: str) -> None:
        return

    def get_default_phase(self, itime: int, res_name: str) -> float:
        return 0.0
    def get_phase(self, itime: int, res_name: str) -> float:
        return 0.0
    def set_phase(self, itime: int, res_name: str) -> None:
        return
    #def get_phase(self, itime: int, case_tuple: str) -> int:
        #(itime, iresult, header) = case_tuple
        #if self.is_real:
            #return 0.0
        #phases = self.phases[self.layer_indices]
        #return phases[itime]
    #def set_phase(self, itime: int, case_tuple: str, phase: float) -> None:
        #(itime, iresult, header) = case_tuple
        #if self.is_real:
            #return
        #phases = self.phases[self.layer_indices]
        #phases[itime] = phase


class PlateStrainStressResults2(PlateResults2):
    def __init__(self,
                 subcase_id: int,
                 model: BDF,
                 node_id: np.ndarray,
                 element_id: np.ndarray,
                 cases: list[RealPlateArray],
                 result: str,
                 title: str,
                 is_fiber_distance: bool,
                 eid_to_nid_map: dict[int, list[int]],
                 #dim_max: float=1.0,
                 data_format: str='%g',
                 is_variable_data_format: bool=False,
                 nlabels=None, labelsize=None, ncolors=None,
                 colormap: str='',
                 set_max_min: bool=False,
                 uname: str='PlateStressStrainResults2'):
        """
        Defines a Displacement/Eigenvector result

        Parameters
        ----------
        subcase_id : int
            the flag that points to self.subcases for a message
        headers : list[str]
            the sidebar word
        titles : list[str]
            the legend title
        xyz : (nnodes, 3)
            the nominal xyz locations
        dxyz : (nnodes, 3)
            the delta xyz values
        scalars : (nnodes,n) float ndarray
            #the data to make a contour plot with
            does nothing
        scales : list[float]
            the deflection scale factors
            nominally, this starts as an empty list and is filled later
        data_formats : str
            the type of data result (e.g. '%i', '%.2f', '%.3f')
        ncolors : int; default=None
            sets the default for reverting the legend ncolors
        set_max_min : bool; default=False
            set default_mins and default_maxs

        Unused
        ------
        uname : str
            some unique name for ...
        """
        PlateResults2.__init__(
            self,
            subcase_id,
            model, node_id, element_id,
            cases,
            result,
            is_fiber_distance,
            eid_to_nid_map,
            #dim_max,
            data_format=data_format,
            nlabels=nlabels, labelsize=labelsize, ncolors=ncolors,
            colormap=colormap,
            set_max_min=set_max_min,
            uname=uname)
        self.title = title

        self.is_variable_data_format = is_variable_data_format

        #linked_scale_factor = False
        #location = 'node'

        out = setup_centroid_node_data(eid_to_nid_map, cases)
        centroid_eids, centroid_data, element_node, node_data = out
        assert centroid_data.ndim == 4, centroid_data.shape
        assert node_data.ndim == 4, node_data.shape

        self.centroid_eids = centroid_eids
        # [ntime, nelement_nnode, nlayer, nresult]
        self.centroid_data = centroid_data

        # [ntime, nelement_nnode, nlayer, nresult]
        self.element_node = element_node
        self.node_data = node_data

        common_eids = np.intersect1d(self.centroid_eids, element_id)
        if len(common_eids) == 0:
            raise IndexError('no plate elements found...')
        elif len(common_eids) != len(self.centroid_eids):
            icommon = np.searchsorted(common_eids, self.centroid_eids)
            #self.centroid_data = self.centroid_data[:, icommon, :]
            raise RuntimeError('some common elements were found...but some are missing')

        self.ielement_centroid = np.searchsorted(element_id, self.centroid_eids)

        # dense -> no missing nodes in the results set
        self.is_dense = (len(element_id) == len(self.centroid_eids))
        #self.is_dense = False

        #self.xyz = xyz
        #assert len(self.xyz.shape) == 2, self.xyz.shape
        if self.is_stress:
            self.headers = ['PlateStress2']
        else:
            self.headers = ['PlateStrain2']
        str(self)

    #-------------------------------------
    # unmodifyable getters

    def get_location(self, unused_i: int, unused_res_name: str) -> str:
        """the result type"""
        return self.location

    #-------------------------------------
    def get_methods(self, itime: int, res_name: str) -> list[str]:
        layers = list(self.layer_map.values())
        return layers

    def get_scalar(self, itime: int, res_name: str, method: str) -> np.ndarray:
        return self.get_plot_value(itime, res_name, method)

    def get_plot_value(self, itime: int, res_name: str, method: str) -> np.ndarray:
        """get_fringe_value"""
        normi = self.get_result(itime, res_name, method, return_dense=False)
        #normi = safe_norm(dxyz, axis=col_axis)
        if self.is_dense:
            return normi

        #case.data.shape = (11, 43, 6)
        #nnodes = len(self.node_id) =  48
        #nnodesi = len(self.inode) = len(self.dxyz.node_gridtype) = 43
        normi2 = np.full(len(self.element_id), np.nan, dtype=normi.dtype)
        normi2[self.ielement_centroid] = normi
        return normi2

    #def get_force_vector_result(self, itime: int, res_name: str, method: str) -> np.ndarray:
        #dxyz = self.get_result(itime, res_name, method, return_dense=True)
        #scale = 1.
        #return self.xyz, dxyz * scale

    #def get_vector_result(self, itime: int, res_name: str, method: str) -> tuple[np.ndarray, np.ndarray]:
        #dxyz = self.get_result(itime, res_name, method, return_dense=True)
        #scale = self.get_scale(itime, res_name)
        #deflected_xyz = self.xyz + scale * dxyz
        #return self.xyz, deflected_xyz

    #def get_vector_result_by_scale_phase(self, i: int, unused_name: str,
                                         #scale: float,
                                         #phase: float=0.) -> tuple[np.ndarray, np.ndarray]:
        #"""
        #Gets the real/complex deflection result

        #Parameters
        #----------
        #i : int
            #mode/time/loadstep number
        #name : str
            #unused; useful for debugging
        #scale : float
            #deflection scale factor; true scale
        #phase : float; default=0.0
            #phase angle (degrees); unused for real results

        #Returns
        #-------
        #xyz : (nnodes, 3) float ndarray
            #the nominal state
        #deflected_xyz : (nnodes, 3) float ndarray
            #the deflected state
        #"""
        #assert self.dim == 3, self.dim
        #assert len(self.xyz.shape) == 2, self.xyz.shape
        #if self.is_real:
            #deflected_xyz = self.xyz + scale * self.dxyz[i, :]
        #else:
            #assert isinstance(i, int), (i, phase)
            #assert isinstance(phase, float), (i, phase)
            #dxyz = self._get_complex_displacements_by_phase(i, phase)
            #deflected_xyz = self.xyz + scale * dxyz
        #assert len(deflected_xyz.shape) == 2, deflected_xyz.shape
        #return self.xyz, deflected_xyz

    def __repr__(self) -> str:
        """defines str(self)"""
        msg = 'CompositeStrainStressResults2\n'
        #msg += f'    titles={self.titles!r}\n'
        msg += f'    subcase_id={self.subcase_id}\n'
        msg += f'    data_type={self.data_type!r}\n'
        msg += f'    is_real={self.is_real} is_complex={self.is_complex}\n'
        msg += f'    location={self.location!r}\n'
        msg += f'    header={self.headers!r}\n'
        msg += f'    data_format={self.data_formats!r}\n'
        msg += f'    uname={self.uname!r}\n'
        return msg


def get_plate_result(result: dict[str, Any],
                     iresult: Union[int, str], index: int):
    """
    values
    0=title, 'annotation'
    ('sAbs Principal', 'Abs Principal')
    """
    assert index in (0, 1), index
    #if isinstance(iresult, int):
        #assert iresult >= 0, iresult
    results = result[iresult]
    return results[index]
    #elif iresult == 'von_mises':
        #word = 'von Mises'
    #elif iresult == 'max_shear':
        #word = 'Max Shear'
    #elif iresult == 'abs_principal':
        #word = 'Abs Principal'
    #else:
        #raise RuntimeError(iresult)
    #return word


def setup_centroid_node_data(eid_to_nid_map: dict[int, list[int]],
                             cases: list[RealPlateArray]) -> tuple[np.ndarray, np.ndarray,
                                                                   np.ndarray, np.ndarray]:
    # setup the node mapping
    centroid_elements_list = []
    centroid_data_list = []

    element_node_list = []
    node_data_list = []
    nlayer = 2
    for case in cases:
        ntime, nelement_nnode_nlayer, nresult = case.data.shape
        nelement_nnode = nelement_nnode_nlayer // 2
        if case.is_bilinear():
            nnode = case.nnodes_per_element
            nelement = len(case.element_node) // (2 * nnode)

            # remvoed the centroid
            nplies = nelement * (nnode - 1) * nlayer

            element_node_4d = case.element_node.reshape(nelement, nnode, nlayer, 2)
            element_node_3d = element_node_4d[:, 1:, :, :]
            element_node = element_node_3d.reshape(nplies, 2)

            centroid_eidsi = case.element_node[0::2*nnode, 0]
            centroid_datai = case.data.copy().reshape(ntime, nelement, nnode, nlayer, nresult)
            centroid_dataii = centroid_datai[:, :, 0, :, :]
            node_dataii     = centroid_datai[:, :, 1:, :, :]

            node_data_list.append(node_dataii)
            element_node_list.append(element_node)
        else:
            # ctria3 - no nodal
            centroid_eidsi = case.element_node[::2, 0]
            centroid_datai = case.data.reshape(ntime, nelement_nnode, 1, nlayer, nresult)
            centroid_dataii = centroid_datai[:, :, 0, :, :]

            eid0 = centroid_eidsi[0]
            nid0 = eid_to_nid_map[eid0]

            ## TODO: probably wrong for fancy CQUAD8/CTRIA6
            nnodes = len(nid0)
            node_data_list.extend([centroid_dataii]*nnodes)
            element_nodei = []
            for eid in centroid_eidsi:
                nids = eid_to_nid_map[eid]
                for nid in nids:
                    # two layers per node
                    element_nodei.append((eid, nid))
                    element_nodei.append((eid, nid))
            element_node_list.append(element_nodei)
        # slice off the centroid
        centroid_elements_list.append(centroid_eidsi)
        centroid_data_list.append(centroid_dataii)
        del node_dataii, centroid_dataii, centroid_eidsi, element_nodei

    centroid_eids = np.hstack(centroid_elements_list)
    centroid_data = np.hstack(centroid_data_list)

    element_node = np.vstack(element_node_list)
    node_data = np.hstack(node_data_list)
    return centroid_eids, centroid_data, element_node, node_data