import netCDF4
import numpy as np
import os

import finite_elem_mapping
import mesh
import rotations
import sem_derivatives
import spectral_basis


class AxiSEMDB(object):
    def __init__(self, folder):
        self.folder = folder
        self.__files = {}
        self._meshes = {}
        self._find_and_open_files()

    def _find_and_open_files(self):
        px = os.path.join(self.folder, "PX")
        pz = os.path.join(self.folder, "PZ")
        if not os.path.exists(px) or not os.path.exists(pz):
            raise ValueError(
                "Expecting the 'PX' and 'PZ' subfolders to be present.")
        px_file = os.path.join(px, "Data", "ordered_output.nc4")
        pz_file = os.path.join(pz, "Data", "ordered_output.nc4")
        if not os.path.exists(px_file) or not os.path.exists(pz_file):
            raise ValueError("ordered_output.nc4 files must exist in the "
                             "PZ/Data and PX/Data subfolders")

        self.__files["px"] = netCDF4.Dataset(px_file, "r", format="NETCDF4")
        self.__files["pz"] = netCDF4.Dataset(pz_file, "r", format="NETCDF4")
        self._meshes["px"] = mesh.Mesh(self.__files["px"])
        self._meshes["pz"] = mesh.Mesh(self.__files["pz"])

    def __del__(self):
        for file_object in self.__files.items():
            try:
                file_object.close()
            except:
                pass

    def get_seismogram(self, source, receiver, component):
        rotmesh_s, rotmesh_phi, rotmesh_z = rotations.rotate_frame_rd(
            source.x * 1000.0, source.y * 1000.0, source.z * 1000.0,
            receiver.longitude, receiver.colatitude)

        nextpoints = self._meshes["px"].kdtree.query([rotmesh_s, rotmesh_z],
                                                     k=6)

        mesh = self.__files["px"].groups["Mesh"]
        for idx in nextpoints[1]:
            fem_mesh = mesh.variables["fem_mesh"]
            corner_point_ids = fem_mesh[idx][:4]
            eltype = mesh.variables["eltype"][idx]

            corner_points = []
            for i in corner_point_ids:
                corner_points.append((
                    mesh.variables["mesh_S"][i],
                    mesh.variables["mesh_Z"][i]
                ))
            corner_points = np.array(corner_points, dtype=np.float64)

            isin, xi, eta = finite_elem_mapping.inside_element(
                rotmesh_s, rotmesh_z, corner_points, eltype,
                tolerance=1E-3)
            if isin:
                id_elem = idx
                break
        else:
            raise ValueError("Element not found")

        # Get the ids of the GLL points.
        gll_point_ids = mesh.variables["sem_mesh"][id_elem]
        axis = bool(mesh.variables["axis"][id_elem])

        if component == "N":
            mesh = self._meshes["px"]
            if mesh.dump_type.strip() != "displ_only":
                raise NotImplementedError

            if axis:
                G = mesh.G2
                GT = mesh.G1T
                col_points_xi = mesh.glj_points
                col_points_eta = mesh.gll_points
            else:
                G = mesh.G2
                GT = mesh.G2T
                col_points_xi = mesh.gll_points
                col_points_eta = mesh.gll_points

            # Single precision in the NetCDF file but the later interpolation
            # routines require double precision. Assignment to this array will
            # force a cast.
            utemp = np.zeros((mesh.ndumps, mesh.npol + 1, mesh.npol + 1, 3),
                             dtype=np.float64, order="F")

            mesh_dict = mesh.f.groups["Snapshots"].variables

            # Load displacement from all GLL points.
            for ipol in xrange(mesh.npol + 1):
                for jpol in xrange(mesh.npol + 1):
                    start_chunk = gll_point_ids[ipol, jpol] / \
                        mesh.chunks[1] * mesh.chunks[1]
                    start_chunk = gll_point_ids[ipol, jpol]

                    for i, var in enumerate(["disp_s", "disp_p", "disp_z"]):
                        if var not in mesh_dict:
                            continue
                        # Interesting indexing once again...but consistent with
                        # the fortran output.
                        utemp[:, jpol, ipol, i] = \
                            mesh_dict[var][:, start_chunk]

            strain_fct_map = {
                "monopole": sem_derivatives.strain_monopole_td,
                "dipole": sem_derivatives.strain_dipole_td,
                "quadpole": sem_derivatives.strain_quadpole_td}

            strain = strain_fct_map[mesh.excitation_type](
                utemp, G, GT, col_points_xi, col_points_eta, mesh.npol,
                mesh.ndumps, corner_points, eltype, axis)

            final_strain = np.empty((strain.shape[0], 6))

            for i in xrange(6):
                final_strain[:, i] = spectral_basis.lagrange_interpol_2D_td(
                    col_points_xi, col_points_eta, strain[:, :, :, i], xi, eta)
            final_strain[:, 3] *= -1.0
            final_strain[:, 5] *= -1.0

            mij = rotations.rotate_symm_tensor_voigt_xyz_src_to_xyz_earth_1d(
                source.tensor_voigt, np.deg2rad(source.longitude),
                np.deg2rad(source.colatitude))
            mij = rotations.rotate_symm_tensor_voigt_xyz_earth_to_xyz_src_1d(
                mij, np.deg2rad(receiver.longitude),
                np.deg2rad(receiver.colatitude))
            mij = rotations.rotate_symm_tensor_voigt_xyz_to_src_1d(
                mij, rotmesh_phi)
            mij /= mesh.amplitude

            fac_1 = rotations.azim_factor_bw(
                rotmesh_phi, np.array([0.0, 1.0, 0.0]), 2, 1)
            fac_2 = rotations.azim_factor_bw(
                rotmesh_phi, np.array([0.0, 1.0, 0.0]), 2, 2)

            final = np.zeros(final_strain.shape[0], dtype="float64")
            final += final_strain[:, 0] * mij[0] * 1.0 * fac_1
            final += final_strain[:, 1] * mij[1] * 1.0 * fac_1
            final += final_strain[:, 2] * mij[2] * 1.0 * fac_1
            final += final_strain[:, 3] * mij[3] * 2.0 * fac_2
            final += final_strain[:, 4] * mij[4] * 2.0 * fac_1
            final += final_strain[:, 5] * mij[5] * 2.0 * fac_2
            final *= -1.0

            return final
