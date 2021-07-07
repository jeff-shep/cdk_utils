# fmt: off
# Versioneer specifically looks for this code, if it's reformatted, it'll get added again
from ._version import get_versions  # isort: skip
__version__ = get_versions()["version"]  # type: ignore
del get_versions
# fmt: on
