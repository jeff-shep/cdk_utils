# cdk_utils
Transport tribe library for common CDK components 

## Project installation

Before installing, make sure you use pip and are connected to artifactory:
```bash
pip install virtualenv
virtualenv .env
".env/Scripts/activate"
pip config --venv set global.extra-index-url https://username:password@metoffice.jfrog.io/metoffice/api/pypi/python-local/simple
```

If you want to use cdk_utils in your project, install with the following command:
```bash
pip install cdkutils
```

# Dev environment
You can create a dev virtualenv by running `tox -e dev --devenv .venv` from the repo's root folder

# Components

## CDK constructs

This library contains a number of CDK constructs under cdkutils.constructs. These are described in the [constructs README](src/cdkutils/constructs/README.md)

## Test helpers

This library also contains some test helpers under cdkutils.test_helpers. These are described in the [test helpers README](src/cdkutils/test_helpers/README.md)

## Details

Currently, cdk_utils contains config and prereqs management.

The config handles pipeline and SSM/Secrets Manager.

Prereqs handles all pre requisite resources needed for an account and is currently the place that cloudformation pre
requisite resources are.

## Example usage from ADS

You use the following python snippet below

```python
#!/usr/bin/env python3
from aws_cdk import core as cdk
from cdkutils.config import CommonPipelineConfig, SsmConfig
from cdkutils.prereqs import ConfigStack, CleanupDeployStack

env = cdk.Environment(region="eu-west-2")

app = cdk.App()
ssm_config = SsmConfig(cdk_scope=app)
shared_config = CommonPipelineConfig.load(ssm_config, cdk_scope=app)

shared_config.service.apply_tags_to(app)
CleanupDeployStack(app, f"CleanupStack-{ssm_config.config_id}", shared_config, ssm_config.config_id, env=env)
ConfigStack(app, f"PrerequisiteConfigStack-{ssm_config.config_id}", shared_config)
app.synth()
```

Then you run the following bash command:
```bash
# deploy all stacks
cdk deploy -c create_secrets=False -c PipIndexPassword="test" -c GitHubToken="test" -c SonarCloudToken="test" -c SsmConfigId="test" --all
```

Or for specific stacks:
```bash
# in the example, we only want to deploy CleanupStack-test
cdk deploy -c create_secrets=False -c PipIndexPassword="test" -c GitHubToken="test" -c SonarCloudToken="test" -c SsmConfigId="test" CleanupStack-test
```

# Config
![](docs/cdkutils_config_class_diagram.png)

## The SsmConfig
```
>>> import cdkutils.config
ssm_config = cdkutils.config.SsmConfig("cdkutils")

>>> print(ssm_config)
/metoffice/cdkutils/default

>>> ssm_config
SsmConfig('cdkutils', 'default', 'metoffice')
```
Configures what SSM/Secret Manager root path to use, i.e. the common stem for config stored in AWS
Can be configured via CDK context variables, or parameters passed to constructor

| Attribute Name | CDK Context Variable Override |
|----------------|-------------------------------|
| `org_name`     | `SsmConfigOrg`                |
| `namespace`    | `SsmNamespace`                |
| `config_id`    | `SsmConfigId`                 |

* `org_name`
  * defaults to `"metoffice"`
  * unlikely to ever need to change it
  * distinguishes Met Office parameters & secrets from those from other sources (although this is just a convention within Transport Tribe)
* `namespace`
  * distinguishes between configs for different services and systems
  * allows flexibility for different config structures in different services & systems
* `config_id`
  * defaults to `"default"`
  * Allows multiple instances of configs to be deployed to the same namespace in parallel
  * Useful for testing without disrupting the default config that other people are relying on
  * Similar to the UniqueId we use in our infrastructure, but for configs

## How to use it: CommonPipelineConfig & PipelineConfig
**CommonPipelineConfig**
* Exists separately from PipelineConfig to allow deployment of shared config
* Account-wide config
* Contains things like account IDs, Artifactory & github credentials

**PipelineConfig**
* Main Config object for use in pipelines
* Specific to a pipeline instance
* Contains things like unique_id, branch_to_build, deploy_to_prod
* Also holds an instance of CommonPipelineConfig

## Config Loading: How does it work?
```python
def load(cls, ssm_config: SsmConfig, boto_session: Optional[boto3.Session] = None, cdk_scope: Optional[cdk.Construct] = None)
```
![](docs/cdkutils_config_load_flow.png)

Overriding config via CDK.
3 Sources, in order of precedence:
1. command line: `-c name=value` e.g. `cdk deploy -c Local=true –c SsmConfigId=test`
1. app’s cdk.json
1. ~/.cdk.json

docs: https://docs.aws.amazon.com/cdk/latest/guide/context.html

## Deploying
* `cdkutils.prereqs.ConfigStack` – boilerplate for deploying a Config, use it in an app
* Deploying secrets doesn’t use CDK, but is triggered via CDK commands using context vars, e.g.
  * `cdk synth –c create_secrets=True ...`
  * `cdk synth –c delete_secrets=True ...`

## Config API: Key Methods
Methods are defined on `cdkutils.config.PersistedConfig`:
* `load()` – creates config instances from CDK context variables, SSMs, and Secrets
* `to_cdk()` – converts the config (and any subconfigs) to the CDK equivalent for deployment. (ignores secrets so they don’t get stored in template)
* `create_secrets`/`delete_secrets` – Create & delete secrets using boto3
* `get_ssm_param_name` - Given an SSM persisted attribute, return its name
* `get_secret_name` – Given an attribute stored in Secret Manager, return its name
* `get_cdk_secret_value` – Parts of CDK require a secret value to be wrapped in a SecretValue object, this returns the requested attribute in that format
* `get_persisted_attribute` – Gets information about how a given attribute is persisted (or exception if it isn’t or doesn’t exist)

## Project specific configs/Extending configs
You'll often want to extend the `PipelineConfig` and `CommonPipelineConfig` to add project specific config items.
These are extended from the appropriate class and use the same hooks as the classes in the library.
i.e. they implement the abstract methods defined on `PersistedConfig` 

The `PersistedConfig.load` method can also be overidden to provide custom behaviour, such as is done in 
`PipelineConfig.load()`

# Cleanup Lambda Notes

To work on the cleanup lambda you can deploy the stacks as described above with a unique id specified in the SsmConfigId.