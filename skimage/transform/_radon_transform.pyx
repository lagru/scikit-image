#cython: cdivision=True
#cython: boundscheck=False
#cython: nonecheck=False
#cython: wraparound=False
import numpy as np

cimport numpy as cnp
cimport cython
from libc.math cimport cos, sin, floor, ceil, sqrt, M_PI
from .._shared.fused_numerics cimport np_floats

cnp.import_array()

cdef bilinear_ray_sum(np_floats[:, :] image, np_floats theta,
                      np_floats ray_position):
    """
    Compute the projection of an image along a ray.

    Parameters
    ----------
    image : ndarray of float, shape (M, N)
        Image to project.
    theta : float
        Angle of the projection.
    ray_position : float
        Position of the ray within the projection.

    Returns
    -------
    projected_value : float
        Ray sum along the projection.
    norm_of_weights : float
        A measure of how long the ray's path through the reconstruction circle was.
    """
    theta = theta / 180. * M_PI
    cdef np_floats radius = image.shape[0] // 2 - 1
    cdef np_floats projection_center = image.shape[0] // 2
    cdef np_floats rotation_center = image.shape[0] // 2
    # (s, t) is the (x, y) system rotated by theta
    cdef np_floats t = ray_position - projection_center
    # s0 is the half-length of the ray's path in the reconstruction circle
    cdef np_floats s0
    s0 = sqrt(radius * radius - t * t) if radius*radius >= t*t else 0.
    cdef Py_ssize_t Ns = 2 * (<Py_ssize_t>ceil(2 * s0))  # number of steps
                                                         # along the ray
    cdef np_floats ray_sum = 0.
    cdef np_floats weight_norm = 0.
    cdef np_floats ds, dx, dy, x0, y0, x, y, di, dj,
    cdef np_floats index_i, index_j, weight
    cdef Py_ssize_t k, i, j

    with nogil:
        if Ns > 0:
            # step length between samples
            ds = 2 * s0 / Ns
            dx = -ds * cos(theta)
            dy = -ds * sin(theta)
            # point of entry of the ray into the reconstruction circle
            x0 = s0 * cos(theta) - t * sin(theta)
            y0 = s0 * sin(theta) + t * cos(theta)
            for k in range(Ns + 1):
                x = x0 + k * dx
                y = y0 + k * dy
                index_i = x + rotation_center
                index_j = y + rotation_center
                i = <Py_ssize_t>floor(index_i)
                j = <Py_ssize_t>floor(index_j)
                di = index_i - floor(index_i)
                dj = index_j - floor(index_j)
                # Use linear interpolation between values
                # Where values fall outside the array, assume zero
                if i > 0 and j > 0:
                    weight = (1. - di) * (1. - dj) * ds
                    ray_sum += weight * image[i, j]
                    weight_norm += weight * weight
                if i > 0 and j < image.shape[1] - 1:
                    weight = (1. - di) * dj * ds
                    ray_sum += weight * image[i, j+1]
                    weight_norm += weight * weight
                if i < image.shape[0] - 1 and j > 0:
                    weight = di * (1 - dj) * ds
                    ray_sum += weight * image[i+1, j]
                    weight_norm += weight * weight
                if i < image.shape[0] - 1 and j < image.shape[1] - 1:
                    weight = di * dj * ds
                    ray_sum += weight * image[i+1, j+1]
                    weight_norm += weight * weight

    return ray_sum, weight_norm


cdef bilinear_ray_update(np_floats[:, :] image,
                         np_floats[:, :] image_update,
                         np_floats theta, np_floats ray_position,
                         np_floats projected_value):
    """Compute the update along a ray using bilinear interpolation.

    Parameters
    ----------
    image : ndarray of float, shape (M, N)
        Current reconstruction estimate.
    image_update : ndarray of float, shape (M, N)
        Array of same shape as ``image``. Updates will be added to this array.
    theta : float
        Angle of the projection.
    ray_position : float
        Position of the ray within the projection.
    projected_value : float
        Projected value (from the sinogram).

    Returns
    -------
    deviation : float
        Deviation before updating the image.
    """
    cdef np_floats ray_sum, weight_norm, deviation
    ray_sum, weight_norm = bilinear_ray_sum(image, theta, ray_position)
    if weight_norm > 0.:
        deviation = -(ray_sum - projected_value) / weight_norm
    else:
        deviation = 0.
    theta = theta / 180. * M_PI
    cdef np_floats radius = image.shape[0] // 2 - 1
    cdef np_floats projection_center = image.shape[0] // 2
    cdef np_floats rotation_center = image.shape[0] // 2
    # (s, t) is the (x, y) system rotated by theta
    cdef np_floats t = ray_position - projection_center
    # s0 is the half-length of the ray's path in the reconstruction circle
    cdef np_floats s0
    s0 = sqrt(radius*radius - t*t) if radius*radius >= t*t else 0.
    cdef Py_ssize_t Ns = 2 * (<Py_ssize_t>ceil(2 * s0))
    # beta for equiripple Hamming window
    cdef np_floats hamming_beta = 0.46164

    cdef np_floats ds, dx, dy, x0, y0, x, y, di, dj, index_i, index_j
    cdef np_floats hamming_window
    cdef Py_ssize_t k, i, j

    with nogil:
        if Ns > 0:
            # Step length between samples
            ds = 2 * s0 / Ns
            dx = -ds * cos(theta)
            dy = -ds * sin(theta)
            # Point of entry of the ray into the reconstruction circle
            x0 = s0 * cos(theta) - t * sin(theta)
            y0 = s0 * sin(theta) + t * cos(theta)
            for k in range(Ns + 1):
                x = x0 + k * dx
                y = y0 + k * dy
                index_i = x + rotation_center
                index_j = y + rotation_center
                i = <Py_ssize_t> floor(index_i)
                j = <Py_ssize_t> floor(index_j)
                di = index_i - floor(index_i)
                dj = index_j - floor(index_j)
                hamming_window = ((1 - hamming_beta)
                                  - hamming_beta * cos(2 * M_PI * k / (Ns - 1)))
                if i > 0 and j > 0:
                    image_update[i, j] += (deviation * (1. - di) * (1. - dj)
                                           * ds * hamming_window)
                if i > 0 and j < image.shape[1] - 1:
                    image_update[i, j+1] += (deviation * (1. - di) * dj
                                             * ds * hamming_window)
                if i < image.shape[0] - 1 and j > 0:
                    image_update[i+1, j] += (deviation * di * (1 - dj)
                                             * ds * hamming_window)
                if i < image.shape[0] - 1 and j < image.shape[1] - 1:
                    image_update[i+1, j+1] += (deviation * di * dj
                                               * ds * hamming_window)

    return deviation


@cython.boundscheck(True)
def sart_projection_update(np_floats[:, :] image not None,
                           np_floats theta,
                           np_floats[:] projection not None,
                           np_floats projection_shift=0.):
    """ Compute update to a reconstruction estimate from a single projection.

    Uses bilinear interpolation.

    Parameters
    ----------
    image : ndarray of float, shape (M, N)
        Current reconstruction estimate
    theta : float
        Angle of the projection
    projection : ndarray of float, shape (P,)
        Projected values, taken from the sinogram
    projection_shift : float
        Shift the position of the projection by this many pixels before
        using it to compute an update to the reconstruction estimate

    Returns
    -------
    image_update : ndarray of float, shape (M, N)
        Array of same shape as ``image`` containing updates that should be
        added to ``image`` to improve the reconstruction estimate
    """

    if np_floats is cnp.float32_t:
        dtype = np.float32
    else:
        dtype = np.float64

    cdef np_floats[:, ::1] image_update = np.zeros_like(
        image, dtype=dtype)
    cdef np_floats ray_position
    cdef Py_ssize_t i
    for i in range(projection.shape[0]):
        ray_position = i + projection_shift
        bilinear_ray_update[np_floats](
            image, image_update, theta, ray_position, projection[i])
    return np.asarray(image_update)
