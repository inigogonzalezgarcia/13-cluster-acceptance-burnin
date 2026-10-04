import tempfile
import unittest
from pathlib import Path

from acceptance import criteria
from tests.helpers import ROOT


class Criteria(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text(text)
            return criteria.load(p)

    def test_repo_criteria_load(self):
        c = criteria.load(ROOT / "criteria.toml")
        self.assertEqual(c["nccl"]["node"]["min_busbw_gbps"], 450)

    def test_typos_and_missing_keys_are_errors(self):
        good = (ROOT / "criteria.toml").read_text()
        with self.assertRaisesRegex(ValueError, "unknown key burnin.max_temp"):
            self.load_text(good.replace("max_gpu_temp_c", "max_temp"))
        with self.assertRaisesRegex(ValueError, "missing inventory.gpus_per_node"):
            self.load_text(good.replace("gpus_per_node = 8\n", ""))
        with self.assertRaisesRegex(ValueError, "must be int"):
            self.load_text(good.replace("gpus_per_node = 8", "gpus_per_node = true"))
        with self.assertRaisesRegex(ValueError, r"\(0, 1\]"):
            self.load_text(good.replace("min_accepted_gpu_fraction = 0.90", "min_accepted_gpu_fraction = 1.5"))
        with self.assertRaises(ValueError):
            self.load_text("not toml [")


if __name__ == "__main__":
    unittest.main()
