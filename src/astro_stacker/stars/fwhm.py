"""FWHM (Full Width at Half Maximum) measurement for stars."""

from scipy.optimize import curve_fit
import numpy as np



def gaussian_2d(
    xy,
    amplitude,
    x0,
    y0,
    sigma,
    offset
):
    """2D Gaussian function for fitting.
    
    Parameters are in order: amplitude, center x, center y, sigma, offset.
    """
    x, y = xy

    return (
        amplitude
        * np.exp(
            -(
                (x - x0) ** 2
                + (y - y0) ** 2
            )
            / (2 * sigma**2)
        )
        + offset
    ).ravel()



def measure_fwhm(
    image: np.ndarray,
    star,
    box_size: int = 15
) -> float | None:
    """Measure Full Width at Half Maximum for a star.
    
    Args:
        image: Image array containing the star
        star: Star object with x, y centroid
        box_size: Size of square cutout around star (default 15x15)
        
    Returns:
        FWHM in pixels, or None if measurement failed
        
    Note:
        Uses 2D Gaussian fitting on a small cutout. Returns None if
        cutout is too small or fitting fails.
    """
    if image.ndim == 3:
        image = image[..., 0]

    x = int(star.x)
    y = int(star.y)

    half = box_size // 2

    cutout = image[
        y-half:y+half+1,
        x-half:x+half+1
    ]

    if cutout.shape[0] < box_size:
        return None

    if cutout.shape[1] < box_size:
        return None
    
    yy, xx = np.indices(cutout.shape)

    p0 = (
        cutout.max(),
        half,
        half,
        2.0,
        np.median(cutout)
    )


    try:
        popt, _ = curve_fit(
            gaussian_2d,
            (xx, yy),
            cutout.ravel(),
            p0=p0,
            maxfev=100,
        )

        sigma = abs(popt[3])

        # Convert sigma to FWHM using the formula: FWHM = 2.355 * sigma
        return 2.355 * sigma

    except Exception:
        return None