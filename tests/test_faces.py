"""agri_sfincs.faces: the minimax spill level, its bottleneck face and path, on a small graph."""

import unittest

import numpy as np

from agri_sfincs.faces import bottleneck, path_faces, spill


class TestSpill(unittest.TestCase):
    # a chain 0 - 1 - 2 - 3 with a bypass 0 - 4 - 3; seed = cell 0
    a = np.array([0, 1, 2, 0, 4])
    b = np.array([1, 2, 3, 4, 3])
    cost = np.array([0.0, 2.0, 0.5, 1.0, 1.5])  # faces: 0-1, 1-2, 2-3, 0-4, 4-3

    def test_levels_take_the_lower_route(self):
        lvl, _ = spill(5, self.a, self.b, self.cost, np.array([0]))
        # 3 via 4 (max 1.5) beats via 1-2 (max 2.0); 2 then via 3 (max(1.5, 0.5))
        np.testing.assert_allclose(lvl, [-np.inf, 0.0, 1.5, 1.5, 1.0])

    def test_bottleneck_and_path(self):
        lvl, par = spill(5, self.a, self.b, self.cost, np.array([0]))
        self.assertEqual(path_faces(2, par, self.a, self.b), [2, 4, 3])
        self.assertEqual(bottleneck(2, par, self.a, self.b, self.cost), 4)

    def test_unreachable_stays_inf(self):
        cost = self.cost.copy()
        cost[[1, 2, 4]] = np.inf
        lvl, par = spill(5, self.a, self.b, cost, np.array([0]))
        self.assertTrue(np.isinf(lvl[2]) and lvl[2] > 0)
        self.assertEqual(path_faces(2, par, self.a, self.b), [])


if __name__ == "__main__":
    unittest.main()
