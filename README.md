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

## Prereq/configuration for CDK Pipelines

TODO: put something here? Chris might be doing this?

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