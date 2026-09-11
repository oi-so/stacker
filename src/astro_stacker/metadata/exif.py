"""EXIF encoding shared by JPEG, PNG and linear TIFF exports."""

import struct
from fractions import Fraction
from pathlib import Path

import tifffile
from PIL import Image, TiffImagePlugin


def exif_fields(metadata):
    metadata = metadata or {}
    fields = {}
    for key, tag in [("EXPTIME", 33434), ("FNUMBER", 33437)]:
        if key in metadata:
            rational = Fraction(float(metadata[key])).limit_denominator(1_000_000)
            if rational.numerator < 0 or rational.numerator > 0xFFFFFFFF:
                raise ValueError(f"{key} is outside the EXIF rational range")
            fields[tag] = TiffImagePlugin.IFDRational(rational.numerator, rational.denominator)
    if metadata.get("ISO") is not None:
        iso = int(metadata["ISO"])
        if not 0 <= iso <= 0xFFFFFFFF:
            raise ValueError("ISO is outside the EXIF range")
        fields[34855] = min(iso, 65535)
        fields[34864] = 3  # ISO speed
        fields[34867] = iso
    comment = metadata.get("COMMENT", "")
    if comment:
        fields[37510] = b"UNICODE\x00" + b"\xfe\xff" + str(comment).encode("utf-16-be")
    return fields


def image_exif(metadata):
    exif = Image.Exif()
    exif[305] = "Astro Stacker"
    exif[34665] = exif_fields(metadata)
    return exif


def append_tiff_exif(path: Path, metadata):
    """Attach an EXIF IFD without converting uint16/float32 RGB through Pillow.

    tifffile deliberately filters ExifIFD from extratags. A reserved private
    LONG tag is emitted by our writer, then changed to the standard pointer
    after appending Pillow's relocated IFD. Only our new little-endian classic
    TIFF output is handled here; source files are never patched.
    """
    exif = Image.Exif()
    exif.endian = "<"
    for tag, value in exif_fields(metadata).items():
        exif[tag] = value
    with path.open("ab") as stream:
        if stream.tell() % 2:
            stream.write(b"\x00")
        offset = stream.tell()
        if offset > 0xFFFFFFFF:
            raise ValueError("EXIF TIFF exceeds the 4 GiB classic TIFF limit; use FITS")
        stream.write(exif.tobytes(offset=offset)[14:])  # Drop EXIF prefix + TIFF header.
    with tifffile.TiffFile(path, mode="r+") as tif:
        tag = tif.pages[0].tags[65000]
        tag.overwrite(offset)
        tif.filehandle.seek(tag.offset)
        tif.filehandle.write(struct.pack("<H", 34665))
