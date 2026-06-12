from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jp100.version import current_version


class VersionTest(unittest.TestCase):
    def test_current_version_uses_sequential_format(self) -> None:
        version = current_version()
        self.assertRegex(version, r"^v[1-9][0-9]*$")


if __name__ == "__main__":
    unittest.main()
