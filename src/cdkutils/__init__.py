from .cdk_utils import PipelineConfig
from ._version import get_versions # isort: skip
__version__ = get_versions()['version'] # type: ignore
del get_versions
