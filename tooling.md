# Tooling
This repository uses a variety of different tools to reduce developer friction and ensure high quality code.
We have adopted `invoke` as a tool to provide a single entry point that can run a variety of different tasks in a
standard way.

## Tooling in use
* linting:
    * `isort` (https://pycqa.github.io/isort/)
    * `black` (https://black.readthedocs.io/en/stable/)
    * `mypy` (https://mypy.readthedocs.io/en/stable/)
    * `pylint` (https://pylint.pycqa.org/en/latest/)
    * `checkov` (https://www.checkov.io/documentation)
    * `safety` (https://pyup.io/safety/)
    * `pip-licenses` (https://github.com/raimon49/pip-licenses/blob/master/README.md)
    * SonarCloud (https://sonarcloud.io/) for collecting quality statistics
* workflow & builds:
    * GitHub Actions (https://docs.github.com/en/actions) to do as much of our builds as possible
    * pre-commit hooks (https://pre-commit.com/) to reject commits that fail the linting
    * `tox` (https://tox.readthedocs.io/en/latest/) to orchestrate `virtualenv` creation and testing
    * `pytest` (https://docs.pytest.org/en/stable/) to run unit tests
    * `coverage.py` (https://coverage.readthedocs.io/en/latest/) to generate coverage reports & enforcing minimum coverage
* packaging & publishing:
    * `setuptools` (https://setuptools.readthedocs.io/en/latest/userguide/index.html) to package python code
    * `versioneer` (https://github.com/python-versioneer/python-versioneer) for calculating version numbers based on git tags and repo state
* `invoke` (https://www.pyinvoke.org/) for running tasks

## How tooling is used in the workflow
1. Direct invocation using invoke e.g. `invoke lint` using tasks set up in [tasks.py]()
1. Pre-commit hooks, if installed, will run `invoke lint` before each commit
1. Using github actions as defined in [Coding Standards](.github/workflows/coding-standards.yml) and [Unit Tests](.github/workflows/unit-tests.yml)

When code is added that needs to have unit tests run, it should be added to the unit tests matrix in the
[unit-tests.yml workflow](.github/workflows/unit-tests.yml)

## Using Invoke
### Setup
The prerequisites for invoke need to be installed into each environment (virtual or real) that you want to run.

The prerequisites are installed by changing directory to `requirements/` and running
`pip install -r requirements-dev.txt`
(which include everything needed for development)

(which include everything needed for invoke, plus the `pre-commit` library)

### Running tasks
Tasks can be run from anywhere in the repo.
Currently all tasks work with the whole repo, and there's no way to run them against a portion of the repo.
The main command is `invoke` or its shorter alias `inv`.

Available tasks can be viewed by running `invoke --list`.
Help for a command can be viewed with `invoke [command] --help`.

Common tasks:
* Run tests: `invoke test`
* Run all linters: `invoke lint`
* Auto-format code: `invoke format`

See the [invoke documentation](https://docs.pyinvoke.org/en/0.11.0/getting_started.html) for more details on how to use invoke and run commands with arguments.

# Using pre-commit hooks
The prerequisites are installed with `pip install -r requirements-dev.txt` from the `requirements/` directory.

The pre-commit hooks are described in [.pre-commit-config.yaml]().
They need to be installed with `pre-commit install`, and that command needs to be run again after changes.

The command inspects the config, generates a hook script based on it, and installs it into the correct location within
the `.git/` folder

Once installed, the hooks will trigger the `invoke lint` command before each commit. Any failures will prevent the
commit being committed.

The checks can by bypassed by adding the `--no-verify` flag to the git command. However, this is not recommended as it's
best to avoid known-bad code getting into the repo (and it won't pass the GH Action workflows in any case).

If you wish to add more tools, see [creating new hooks](https://pre-commit.com/#intro#new-hooks) for more details on how to specify what to use and what the flags mean.

# Pushing packages to artifactory
A [push_to_artifactory.yml](.github/workflows/push_to_artifactory.yml) is provided for packaging. This will only work with a package created at the top level of the repository, and in order to use it, the changes specified at the top of the file need to be made to activate it. Once this is active, it can be used by creating a Release through the github UI, specifying a tag which will then be used as the package version. Once this has been published, the package should be available to install via artifactory using pip install.

[comment]: <> (Moved this to here for future expansion)
TODO:
* Setting up virtualenvs with tox
    * `cd` to directory with `pyproject.toml` & `tox.ini`
    * run `tox --devenv /path/to/where/you/want/your/venv`  _# TODO, maybe we should wrap this in an invoke command?_
* Configuring IntelliJ (including configuring modules for each python project)