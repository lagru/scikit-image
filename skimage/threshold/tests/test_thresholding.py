import math

import numpy as np
import pytest
from numpy.testing import (
    assert_allclose,
    assert_almost_equal,
    assert_array_equal,
    assert_equal,
)
from scipy import ndimage as ndi

from skimage import data, util
from skimage._shared._dependency_checks import has_mpl
from skimage._shared._warnings import expected_warnings
from skimage._shared.utils import _supported_float_type
from skimage.color import rgb2gray
from skimage.draw import disk
from skimage.exposure import histogram
from skimage.threshold._multiotsu import (
    _get_multiotsu_thresh_indices,
    _get_multiotsu_thresh_indices_lut,
)
from skimage.threshold._thresholding import (
    _cross_entropy,
    _mean_std,
    isodata,
    li,
    local_image,
    mean,
    minimum,
    multiotsu,
    niblack_image,
    otsu,
    sauvola_image,
    triangle,
    yen,
    try_all_threshold,
)


class TestSimpleImage:
    def setup_method(self):
        self.image = np.array(
            [
                [0, 0, 1, 3, 5],
                [0, 1, 4, 3, 4],
                [1, 2, 5, 4, 1],
                [2, 4, 5, 2, 1],
                [4, 5, 1, 0, 0],
            ],
            dtype=int,
        )

    def test_minimum(self):
        with pytest.raises(RuntimeError):
            minimum(self.image)

    @pytest.mark.skipif(not has_mpl, reason="matplotlib not installed")
    def test_try_all_threshold(self):
        fig, ax = try_all_threshold(self.image)
        all_texts = [axis.texts for axis in ax if axis.texts != []]
        text_content = [text.get_text() for x in all_texts for text in x]
        assert 'RuntimeError' in text_content

    def test_otsu(self):
        assert otsu(self.image) == 2

    def test_otsu_negative_int(self):
        image = self.image - 2
        assert otsu(image) == 0

    def test_otsu_float_image(self):
        image = np.float64(self.image)
        assert 2 <= otsu(image) < 3

    def test_li(self):
        assert 2 < li(self.image) < 3

    def test_li_negative_int(self):
        image = self.image - 2
        assert 0 < li(image) < 1

    def test_li_float_image(self):
        image = self.image.astype(float)
        assert 2 < li(image) < 3

    def test_li_constant_image(self):
        assert li(np.ones((10, 10))) == 1.0

    def test_yen(self):
        assert yen(self.image) == 2

    def test_yen_negative_int(self):
        image = self.image - 2
        assert yen(image) == 0

    def test_yen_float_image(self):
        image = np.float64(self.image)
        assert 2 <= yen(image) < 3

    def test_yen_arange(self):
        image = np.arange(256)
        assert yen(image) == 127

    def test_yen_binary(self):
        image = np.zeros([2, 256], dtype=np.uint8)
        image[0] = 255
        assert yen(image) < 1

    def test_yen_blank_zero(self):
        image = np.zeros((5, 5), dtype=np.uint8)
        assert yen(image) == 0

    def test_yen_blank_max(self):
        image = np.empty((5, 5), dtype=np.uint8)
        image.fill(255)
        assert yen(image) == 255

    def test_isodata(self):
        assert isodata(self.image) == 2
        assert isodata(self.image, return_all=True) == [2]

    def test_isodata_blank_zero(self):
        image = np.zeros((5, 5), dtype=np.uint8)
        assert isodata(image) == 0
        assert isodata(image, return_all=True) == [0]

    def test_isodata_linspace(self):
        image = np.linspace(-127, 0, 256)
        assert -63.8 < isodata(image) < -63.6
        assert_almost_equal(
            isodata(image, return_all=True), [-63.74804688, -63.25195312]
        )

    def test_isodata_16bit(self):
        np.random.seed(0)
        imfloat = np.random.rand(256, 256)
        assert 0.49 < isodata(imfloat, nbins=1024) < 0.51
        assert all(0.49 < isodata(imfloat, nbins=1024, return_all=True))

    @pytest.mark.parametrize('ndim', [2, 3])
    def test_local_image_gaussian(self, ndim):
        ref = np.array(
            [
                [False, False, False, False, True],
                [False, False, True, False, True],
                [False, False, True, True, False],
                [False, True, True, False, False],
                [True, True, False, False, False],
            ]
        )
        if ndim == 2:
            image = self.image
            block_sizes = [3, (3,) * image.ndim]
        else:
            image = np.stack((self.image,) * 5, axis=-1)
            ref = np.stack((ref,) * 5, axis=-1)
            block_sizes = [3, (3,) * image.ndim, (3,) * (image.ndim - 1) + (1,)]

        for block_size in block_sizes:
            out = local_image(image, block_size, method='gaussian', mode='reflect')
            assert_equal(ref, image > out)

        out = local_image(image, 3, method='gaussian', mode='reflect', param=1 / 3)
        assert_equal(ref, image > out)

    @pytest.mark.parametrize('ndim', [2, 3])
    def test_local_image_mean(self, ndim):
        ref = np.array(
            [
                [False, False, False, False, True],
                [False, False, True, False, True],
                [False, False, True, True, False],
                [False, True, True, False, False],
                [True, True, False, False, False],
            ]
        )
        if ndim == 2:
            image = self.image
            block_sizes = [3, (3,) * image.ndim]
        else:
            image = np.stack((self.image,) * 5, axis=-1)
            ref = np.stack((ref,) * 5, axis=-1)
            # Given the same data at each z location, the following block sizes
            # will all give an equivalent result.
            block_sizes = [3, (3,) * image.ndim, (3,) * (image.ndim - 1) + (1,)]
        for block_size in block_sizes:
            out = local_image(image, block_size, method='mean', mode='reflect')
            assert_equal(ref, image > out)

    @pytest.mark.parametrize('block_size', [(3,), (3, 3, 3)])
    def test_local_image_invalid_block_size(self, block_size):
        # len(block_size) != image.ndim
        with pytest.raises(ValueError):
            local_image(self.image, block_size, method='mean')

    @pytest.mark.parametrize('ndim', [2, 3])
    def test_local_image_median(self, ndim):
        ref = np.array(
            [
                [False, False, False, False, True],
                [False, False, True, False, False],
                [False, False, True, False, False],
                [False, False, True, True, False],
                [False, True, False, False, False],
            ]
        )
        if ndim == 2:
            image = self.image
        else:
            image = np.stack((self.image,) * 5, axis=-1)
            ref = np.stack((ref,) * 5, axis=-1)
        out = local_image(image, 3, method='median', mode='reflect')
        assert_equal(ref, image > out)

    def test_local_image_median_constant_mode(self):
        out = local_image(self.image, 3, method='median', mode='constant', cval=20)
        expected = np.array(
            [
                [20.0, 1.0, 3.0, 4.0, 20.0],
                [1.0, 1.0, 3.0, 4.0, 4.0],
                [2.0, 2.0, 4.0, 4.0, 4.0],
                [4.0, 4.0, 4.0, 1.0, 2.0],
                [20.0, 5.0, 5.0, 2.0, 20.0],
            ]
        )
        assert_equal(expected, out)

    def test_niblack_image(self):
        ref = np.array(
            [
                [False, False, False, True, True],
                [False, True, True, True, True],
                [False, True, True, True, False],
                [False, True, True, True, True],
                [True, True, False, False, False],
            ]
        )
        thres = niblack_image(self.image, window_size=3, k=0.5)
        out = self.image > thres
        assert_equal(ref, out)

    def test_sauvola_image(self):
        ref = np.array(
            [
                [False, False, False, True, True],
                [False, False, True, True, True],
                [False, False, True, True, False],
                [False, True, True, True, False],
                [True, True, False, False, False],
            ]
        )
        thres = sauvola_image(self.image, window_size=3, k=0.2, r=128)
        out = self.image > thres
        assert_equal(ref, out)

    def test_niblack_image_iterable_window_size(self):
        ref = np.array(
            [
                [False, False, False, True, True],
                [False, False, True, True, True],
                [False, True, True, True, False],
                [False, True, True, True, False],
                [True, True, False, False, False],
            ]
        )
        thres = niblack_image(self.image, window_size=[3, 5], k=0.5)
        out = self.image > thres
        assert_array_equal(ref, out)

    def test_sauvola_image_iterable_window_size(self):
        ref = np.array(
            [
                [False, False, False, True, True],
                [False, False, True, True, True],
                [False, False, True, True, False],
                [False, True, True, True, False],
                [True, True, False, False, False],
            ]
        )
        thres = sauvola_image(self.image, window_size=(3, 5), k=0.2, r=128)
        out = self.image > thres
        assert_array_equal(ref, out)


def test_otsu_camera_image():
    camera = util.img_as_ubyte(data.camera())
    assert 101 < otsu(camera) < 103


def test_otsu_camera_image_histogram():
    camera = util.img_as_ubyte(data.camera())
    hist = histogram(camera.ravel(), 256, source_range='image')
    assert 101 < otsu(hist=hist) < 103


def test_otsu_camera_image_counts():
    camera = util.img_as_ubyte(data.camera())
    counts, bin_centers = histogram(camera.ravel(), 256, source_range='image')
    assert 101 < otsu(hist=counts) < 103


def test_otsu_zero_count_histogram():
    """Issue #5497.

    As the histogram returned by np.bincount starts with zero,
    it resulted in NaN-related issues.
    """
    x = np.array([1, 2])

    t1 = otsu(x)
    t2 = otsu(hist=np.bincount(x))
    assert t1 == t2


def test_otsu_coins_image():
    coins = util.img_as_ubyte(data.coins())
    assert 106 < otsu(coins) < 108


def test_otsu_coins_image_as_float():
    coins = util.img_as_float(data.coins())
    assert 0.41 < otsu(coins) < 0.42


def test_otsu_astro_image():
    img = util.img_as_ubyte(data.astronaut())
    with expected_warnings(['grayscale']):
        assert 109 < otsu(img) < 111


def test_otsu_one_color_image():
    img = np.ones((10, 10), dtype=np.uint8)
    assert otsu(img) == 1


def test_otsu_one_color_image_3d():
    img = np.ones((10, 10, 10), dtype=np.uint8)
    assert otsu(img) == 1


def test_li_camera_image():
    image = util.img_as_ubyte(data.camera())
    threshold = li(image)
    ce_actual = _cross_entropy(image, threshold)
    assert 78 < li(image) < 79
    assert ce_actual < _cross_entropy(image, threshold + 1)
    assert ce_actual < _cross_entropy(image, threshold - 1)


def test_li_coins_image():
    image = util.img_as_ubyte(data.coins())
    threshold = li(image)
    ce_actual = _cross_entropy(image, threshold)
    assert 94 < li(image) < 95
    assert ce_actual < _cross_entropy(image, threshold + 1)
    # in the case of the coins image, the minimum cross-entropy is achieved one
    # threshold below that found by the iterative method. Not sure why that is
    # but `li` does find the stationary point of the function (ie the
    # tolerance can be reduced arbitrarily but the exact same threshold is
    # found), so my guess is some kind of histogram binning effect.
    assert ce_actual < _cross_entropy(image, threshold - 2)


def test_li_coins_image_as_float():
    coins = util.img_as_float(data.coins())
    assert 94 / 255 < li(coins) < 95 / 255


def test_li_astro_image():
    image = util.img_as_ubyte(data.astronaut())
    threshold = li(image)
    ce_actual = _cross_entropy(image, threshold)
    assert 64 < threshold < 65
    assert ce_actual < _cross_entropy(image, threshold + 1)
    assert ce_actual < _cross_entropy(image, threshold - 1)


def test_li_nan_image():
    image = np.full((5, 5), np.nan)
    assert np.isnan(li(image))


def test_li_inf_image():
    image = np.array([np.inf, np.nan])
    assert li(image) == np.inf


def test_li_inf_minus_inf():
    image = np.array([np.inf, -np.inf])
    assert li(image) == 0


def test_li_constant_image_with_nan():
    image = np.array([8, 8, 8, 8, np.nan])
    assert li(image) == 8


def test_li_arbitrary_start_point():
    cell = data.cell()
    max_stationary_point = li(cell)
    low_stationary_point = li(cell, initial_guess=np.percentile(cell, 5))
    optimum = li(cell, initial_guess=np.percentile(cell, 95))
    assert 67 < max_stationary_point < 68
    assert 48 < low_stationary_point < 49
    assert 111 < optimum < 112


def test_li_negative_inital_guess():
    coins = data.coins()
    with pytest.raises(ValueError, match=".*initial guess.*must be within the range"):
        li(coins, initial_guess=-5)


@pytest.mark.parametrize(
    "image",
    [
        # See https://github.com/scikit-image/scikit-image/issues/4140
        [0, 0, 1, 0, 0, 1, 0, 1],
        [0, 0, 0.1, 0, 0, 0.1, 0, 0.1],
        [0, 0, 0.1, 0, 0, 0.1, 0.01, 0.1],
        [0, 0, 1, 0, 0, 1, 0.5, 1],
        [1, 1],
        [1, 2],
        # See https://github.com/scikit-image/scikit-image/issues/6744
        [0, 254, 255],
        [0, 1, 255],
        [0.1, 0.8, 0.9],
    ],
)
def test_li_pathological(image):
    image = np.array(image)
    threshold = li(image)
    assert np.isfinite(threshold)


def test_yen_camera_image():
    camera = util.img_as_ubyte(data.camera())
    assert 145 < yen(camera) < 147


def test_yen_camera_image_histogram():
    camera = util.img_as_ubyte(data.camera())
    hist = histogram(camera.ravel(), 256, source_range='image')
    assert 145 < yen(hist=hist) < 147


def test_yen_camera_image_counts():
    camera = util.img_as_ubyte(data.camera())
    counts, bin_centers = histogram(camera.ravel(), 256, source_range='image')
    assert 145 < yen(hist=counts) < 147


def test_yen_coins_image():
    coins = util.img_as_ubyte(data.coins())
    assert 109 < yen(coins) < 111


def test_yen_coins_image_as_float():
    coins = util.img_as_float(data.coins())
    assert 0.43 < yen(coins) < 0.44


def test_local_even_block_size_error():
    img = data.camera()
    with pytest.raises(ValueError):
        local_image(img, block_size=4)


def test_isodata_camera_image():
    camera = util.img_as_ubyte(data.camera())

    threshold = isodata(camera)
    assert (
        np.floor(
            (camera[camera <= threshold].mean() + camera[camera > threshold].mean())
            / 2.0
        )
        == threshold
    )
    assert threshold == 102

    assert (isodata(camera, return_all=True) == [102, 103]).all()


def test_isodata_camera_image_histogram():
    camera = util.img_as_ubyte(data.camera())
    hist = histogram(camera.ravel(), 256, source_range='image')
    threshold = isodata(hist=hist)
    assert threshold == 102


def test_isodata_camera_image_counts():
    camera = util.img_as_ubyte(data.camera())
    counts, bin_centers = histogram(camera.ravel(), 256, source_range='image')
    threshold = isodata(hist=counts)
    assert threshold == 102


def test_isodata_coins_image():
    coins = util.img_as_ubyte(data.coins())

    threshold = isodata(coins)
    assert (
        np.floor(
            (coins[coins <= threshold].mean() + coins[coins > threshold].mean()) / 2.0
        )
        == threshold
    )
    assert threshold == 107

    assert isodata(coins, return_all=True) == [107]


def test_isodata_moon_image():
    moon = util.img_as_ubyte(data.moon())

    threshold = isodata(moon)
    assert (
        np.floor((moon[moon <= threshold].mean() + moon[moon > threshold].mean()) / 2.0)
        == threshold
    )
    assert threshold == 86

    thresholds = isodata(moon, return_all=True)
    for threshold in thresholds:
        assert (
            np.floor(
                (moon[moon <= threshold].mean() + moon[moon > threshold].mean()) / 2.0
            )
            == threshold
        )
    assert_equal(thresholds, [86, 87, 88, 122, 123, 124, 139, 140])


def test_isodata_moon_image_negative_int():
    moon = util.img_as_ubyte(data.moon()).astype(np.int32)
    moon -= 100

    threshold = isodata(moon)
    assert (
        np.floor((moon[moon <= threshold].mean() + moon[moon > threshold].mean()) / 2.0)
        == threshold
    )
    assert threshold == -14

    thresholds = isodata(moon, return_all=True)
    for threshold in thresholds:
        assert (
            np.floor(
                (moon[moon <= threshold].mean() + moon[moon > threshold].mean()) / 2.0
            )
            == threshold
        )
    assert_equal(thresholds, [-14, -13, -12, 22, 23, 24, 39, 40])


def test_isodata_moon_image_negative_float():
    moon = util.img_as_ubyte(data.moon()).astype(np.float64)
    moon -= 100

    assert -14 < isodata(moon) < -13

    thresholds = isodata(moon, return_all=True)
    assert_almost_equal(
        thresholds,
        [
            -13.83789062,
            -12.84179688,
            -11.84570312,
            22.02148438,
            23.01757812,
            24.01367188,
            38.95507812,
            39.95117188,
        ],
    )


def test_minimum():
    camera = util.img_as_ubyte(data.camera())

    threshold = minimum(camera)
    assert_equal(threshold, 85)

    astronaut = util.img_as_ubyte(data.astronaut())
    threshold = minimum(astronaut)
    assert_equal(threshold, 114)


def test_minimum_histogram():
    camera = util.img_as_ubyte(data.camera())
    hist = histogram(camera.ravel(), 256, source_range='image')
    threshold = minimum(hist=hist)
    assert_equal(threshold, 85)


def test_minimum_counts():
    camera = util.img_as_ubyte(data.camera())
    counts, bin_centers = histogram(camera.ravel(), 256, source_range='image')
    threshold = minimum(hist=counts)
    assert_equal(threshold, 85)


def test_minimum_synthetic():
    img = np.arange(25 * 25, dtype=np.uint8).reshape((25, 25))
    img[0:9, :] = 50
    img[14:25, :] = 250

    threshold = minimum(img)
    assert_equal(threshold, 95)


def test_minimum_failure():
    img = np.zeros((16 * 16), dtype=np.uint8)
    with pytest.raises(RuntimeError):
        minimum(img)


def test_mean():
    img = np.zeros((2, 6))
    img[:, 2:4] = 1
    img[:, 4:] = 2
    assert mean(img) == 1.0


@pytest.mark.parametrize("dtype", [np.uint8, np.int16, np.float16, np.float32])
def test_triangle_uniform_images(dtype):
    assert triangle(np.zeros((10, 10), dtype=dtype)) == 0
    assert triangle(np.ones((10, 10), dtype=dtype)) == 1
    assert triangle(np.full((10, 10), 2, dtype=dtype)) == 2


def test_triangle_uint_images():
    assert triangle(np.invert(data.text())) == 151
    assert triangle(data.text()) == 104
    assert triangle(data.coins()) == 80
    assert triangle(np.invert(data.coins())) == 175


def test_triangle_float_images():
    text = data.text()
    int_bins = text.max() - text.min() + 1
    # Set nbins to match the uint case and threshold as float.
    assert round(triangle(text.astype(float), nbins=int_bins)) == 104
    # Check that rescaling image to floats in unit interval is equivalent.
    assert round(triangle(text / 255.0, nbins=int_bins) * 255) == 104
    # Repeat for inverted image.
    assert round(triangle(np.invert(text).astype(float), nbins=int_bins)) == 151
    assert round(triangle(np.invert(text) / 255.0, nbins=int_bins) * 255) == 151


def test_triangle_flip():
    # Depending on the skewness, the algorithm flips the histogram.
    # We check that the flip doesn't affect too much the result.
    img = data.camera()
    inv_img = np.invert(img)
    t = triangle(inv_img)
    t_inv_img = inv_img > t
    t_inv_inv_img = np.invert(t_inv_img)

    t = triangle(img)
    t_img = img > t

    # Check that most of the pixels are identical
    # See numpy #7685 for a future np.testing API
    unequal_pos = np.where(t_img.ravel() != t_inv_inv_img.ravel())
    assert len(unequal_pos[0]) / t_img.size < 1e-2


@pytest.mark.parametrize(
    "window_size, mean_kernel",
    [
        (11, np.full((11,) * 2, 1 / 11**2)),
        ((11, 11), np.full((11, 11), 1 / 11**2)),
        ((9, 13), np.full((9, 13), 1 / math.prod((9, 13)))),
        ((13, 9), np.full((13, 9), 1 / math.prod((13, 9)))),
        ((1, 9), np.full((1, 9), 1 / math.prod((1, 9)))),
    ],
)
def test_mean_std_2d(window_size, mean_kernel):
    image = np.random.rand(256, 256)
    m, s = _mean_std(image, w=window_size)
    expected_m = ndi.convolve(image, mean_kernel, mode='mirror')
    assert_allclose(m, expected_m)
    expected_s = ndi.generic_filter(image, np.std, size=window_size, mode='mirror')
    assert_allclose(s, expected_s)


@pytest.mark.parametrize(
    "window_size, mean_kernel",
    [
        (5, np.full((5,) * 3, 1 / 5) ** 3),
        ((5, 5, 5), np.full((5, 5, 5), 1 / 5**3)),
        ((1, 5, 5), np.full((1, 5, 5), 1 / 5**2)),
        ((3, 5, 7), np.full((3, 5, 7), 1 / math.prod((3, 5, 7)))),
    ],
)
def test_mean_std_3d(window_size, mean_kernel):
    image = np.random.rand(40, 40, 40)
    m, s = _mean_std(image, w=window_size)
    expected_m = ndi.convolve(image, mean_kernel, mode='mirror')
    assert_allclose(m, expected_m)
    expected_s = ndi.generic_filter(image, np.std, size=window_size, mode='mirror')
    assert_allclose(s, expected_s)


@pytest.mark.parametrize(
    "threshold_func",
    [local_image, niblack_image, sauvola_image],
)
@pytest.mark.parametrize("dtype", [np.uint8, np.int16, np.float16, np.float32])
def test_variable_dtypes(threshold_func, dtype):
    r = 255 * np.random.rand(32, 16)
    r = r.astype(dtype, copy=False)

    kwargs = {}
    if threshold_func is local_image:
        kwargs = dict(block_size=9)
    elif threshold_func is sauvola_image:
        kwargs = dict(r=128)

    # use double precision result as a reference
    expected = threshold_func(r.astype(float), **kwargs)

    out = threshold_func(r, **kwargs)
    assert out.dtype == _supported_float_type(dtype)
    assert_allclose(out, expected, rtol=1e-5, atol=1e-5)


def test_niblack_sauvola_pathological_image():
    # For certain values, floating point error can cause
    # E(X^2) - (E(X))^2 to be negative, and taking the square root of this
    # resulted in NaNs. Here we check that these are safely caught.
    # see https://github.com/scikit-image/scikit-image/issues/3007
    value = 0.03082192 + 2.19178082e-09
    src_img = np.full((4, 4), value).astype(np.float64)
    assert not np.any(np.isnan(niblack_image(src_img)))


def test_bimodal_multiotsu_hist():
    for name in ['camera', 'moon', 'coins', 'text', 'clock', 'page']:
        img = getattr(data, name)()
        assert otsu(img) == multiotsu(img, 2)

    for name in ['chelsea', 'coffee', 'astronaut', 'rocket']:
        img = rgb2gray(getattr(data, name)())
        assert otsu(img) == multiotsu(img, 2)


def test_check_multiotsu_results():
    image = 0.25 * np.array(
        [[0, 1, 2, 3, 4], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]]
    )

    for idx in range(3, 6):
        thr_multi = multiotsu(image, classes=idx)
        assert len(thr_multi) == idx - 1


def test_multiotsu_output():
    image = np.zeros((100, 100), dtype='int')
    coords = [(25, 25), (50, 50), (75, 75)]
    values = [64, 128, 192]
    for coor, val in zip(coords, values):
        rr, cc = disk(coor, 20)
        image[rr, cc] = val
    thresholds = [0, 64, 128]
    assert np.array_equal(thresholds, multiotsu(image, classes=4))


def test_multiotsu_astro_image():
    img = util.img_as_ubyte(data.astronaut())
    with expected_warnings(['grayscale']):
        assert_almost_equal(multiotsu(img), [58, 149])


def test_multiotsu_more_classes_then_values():
    img = np.ones((10, 10), dtype=np.uint8)
    with pytest.raises(ValueError):
        multiotsu(img, classes=2)
    img[:, 3:] = 2
    with pytest.raises(ValueError):
        multiotsu(img, classes=3)
    img[:, 6:] = 3
    with pytest.raises(ValueError):
        multiotsu(img, classes=4)


def test_multiotsu_lut():
    for classes in [2, 3, 4]:
        for name in ['camera', 'moon', 'coins', 'text', 'clock', 'page']:
            img = getattr(data, name)()
            prob, bin_centers = histogram(
                img.ravel(), nbins=256, source_range='image', normalize=True
            )
            prob = prob.astype('float32')

            result_lut = _get_multiotsu_thresh_indices_lut(prob, classes - 1)
            result = _get_multiotsu_thresh_indices(prob, classes - 1)

            assert np.array_equal(result_lut, result)


def test_multiotsu_missing_img_and_hist():
    with pytest.raises(Exception):
        multiotsu()


def test_multiotsu_hist_parameter():
    for classes in [2, 3, 4]:
        for name in ['camera', 'moon', 'coins', 'text', 'clock', 'page']:
            img = getattr(data, name)()
            sk_hist = histogram(img, nbins=256)
            #
            thresh_img = multiotsu(img, classes)
            thresh_sk_hist = multiotsu(classes=classes, hist=sk_hist)
            assert np.allclose(thresh_img, thresh_sk_hist)
