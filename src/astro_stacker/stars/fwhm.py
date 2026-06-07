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
            p0=p0
        )

        sigma = abs(popt[3])

        return 2.355 * sigma

    except Exception:
        return None