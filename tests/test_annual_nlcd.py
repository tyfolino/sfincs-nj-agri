import unittest

import numpy as np

from agri_sfincs import annual_nlcd


class TestDecode(unittest.TestCase):
    def test_colours_to_classes(self):
        rgb = np.array([annual_nlcd.PALETTE[82], annual_nlcd.PALETTE[11], (1, 2, 3)], "uint8").T[:, None, :]
        self.assertEqual(annual_nlcd.decode(rgb).tolist(), [[82, 11, 0]])


if __name__ == "__main__":
    unittest.main()
