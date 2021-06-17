import boto3
from aws_cdk import core, pipelines
from pygit2 import Repository


class PipelineConfig:
    # pylint: disable=too-many-instance-attributes:
    """To be used with the CDK to manage PipelineConfig"""

    def __init__(
        self,
        app: core.App,
        default_ssm_namespace: str,
        region: str = "eu-west-2",
    ):
        self.region = region
        self.unique_id = app.node.try_get_context("UniqueId")
        if not self.unique_id:
            raise Exception("UniqueId must be specified")
        self.ssm_namespace = app.node.try_get_context("SSMNamespace") or default_ssm_namespace
        self.pipeline_ssm_config_id = app.node.try_get_context("PipelineSSMConfigId") or "default"
        self.system_ssm_config_id = app.node.try_get_context("SystemSSMConfigId") or "default"
        self.branch_to_build = app.node.try_get_context("BranchToBuild") or Repository(".").head.shorthand
        self.deploy_to_ci = app.node.try_get_context("DeployToCi") or "Disabled"
        self.deploy_to_prod = app.node.try_get_context("DeployToProd") or "Disabled"
        self.build_lambdas = not app.node.try_get_context("Local")
        self.pipeline_ssm_path = f"/metoffice/{self.ssm_namespace}/{self.pipeline_ssm_config_id}"
        self.system_ssm_path = f"/metoffice/{self.ssm_namespace}/{self.system_ssm_config_id}"
        # everything except unique_id, which is already added
        self.pipeline_parameters = "-c " + " -c ".join(
            [
                f"BranchToBuild={self.branch_to_build}",
                f"SSMNamespace={self.ssm_namespace}",
                f"PipelineSSMConfigId={self.pipeline_ssm_config_id}",
                f"SystemSSMConfigId={self.system_ssm_config_id}",
                f"DeployToCi={self.deploy_to_ci}",
                f"DeployToProd={self.deploy_to_prod}",
            ]
        )

    def get_pipeline_ssm_path(self, path: str) -> str:
        return f"{self.pipeline_ssm_path}/{path}"

    def get_system_ssm_path(self, path: str) -> str:
        return f"{self.system_ssm_path}/{path}"

    def get_pipeline_ssm_parameter(
        self,
        path: str,
    ) -> str:
        session = boto3.Session(region_name=self.region)
        client = session.client("ssm")
        ssm_parameter: str = client.get_parameter(Name=self.get_pipeline_ssm_path(path))["Parameter"]["Value"]
        return ssm_parameter

    def get_system_ssm_parameter(
        self,
        path: str,
    ) -> str:
        session = boto3.Session(region_name=self.region)
        client = session.client("ssm")
        ssm_parameter: str = client.get_parameter(Name=self.get_system_ssm_path(path))["Parameter"]["Value"]
        return ssm_parameter

    def get_secret(self, path: str) -> str:
        session = boto3.Session(region_name=self.region)
        client = session.client("secretsmanager")
        secret_string: str = client.get_secret_value(SecretId=path)["SecretString"]
        return secret_string

    @staticmethod
    def get_artifact_for_stack_output(pipeline: pipelines.CdkPipeline, output: core.CfnOutput) -> object:
        stack_output = pipeline.stack_output(output)
        return stack_output.artifact_file.artifact
