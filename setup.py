"""
This file is purely to enable development mode support (i.e. `pip install -e .`), which enables the use of
`tox --devenv` until PyPA decide how they want to standardise this pip feature
"""
import setuptools
import versioneer

setuptools.setup(version=versioneer.get_version(), cmdclass=versioneer.get_cmdclass())  # type: ignore
