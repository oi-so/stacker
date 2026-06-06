from astro_stacker.io.loader import load_info
from astro_stacker.io.saver import save_tiff
from pathlib import Path
from pprint import pprint

astro_img = load_info(Path("/Users/oiso/Desktop/デスクトップ - oiのMacBook Air/folders/programs/天体関連/astroStacker/test_images/DSC03444.ARW"))
pprint(astro_img.info)
astro_img.load()
save_tiff(astro_img.data, Path("/Users/oiso/Desktop/デスクトップ - oiのMacBook Air/folders/programs/天体関連/astroStacker/test_images/DSC03444.tiff"))