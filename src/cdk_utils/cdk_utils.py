from aws_cdk import aws_ssm, core
from pygit2 import Repository


class PipelineConfig:
    def __init__(
            self,
            app: core.App,
            default_ssm_namespace: str,
    ):
        self.unique_id = app.node.try_get_context("UniqueId")
        if not self.unique_id:
            raise Exception("UniqueId must be specified")
        self.ssm_namespace = app.node.try_get_context("SSMNamespace") or default_ssm_namespace
        self.pipeline_ssm_config_id = app.node.try_get_context("PipelineConfigId") or "default"
        self.system_ssm_config_id = app.node.try_get_context("SystemConfigId") or "default"
        self.branch_to_build = app.node.try_get_context("BranchToBuild") or Repository(".").head.shorthand
        self.pipeline_ssm_path = f"/metoffice/{self.ssm_namespace}/{self.pipeline_ssm_config_id}"
        self.system_ssm_path = f"/metoffice/{self.ssm_namespace}/{self.system_ssm_config_id}"
        # everything except unique_id, which is already added
        self.pipeline_parameters = "-c " + " -c ".join(
            [
                f"BranchToBuild={self.branch_to_build}",
                f"SSMNamespace={self.ssm_namespace}",
                f"PipelineSSMConfigId={self.pipeline_ssm_config_id}",
                f"SystemSSMConfigId={self.system_ssm_config_id}",
            ]
        )

    def get_pipeline_ssm_path(self, path: str) -> str:
        return f"{self.pipeline_ssm_path}/{path}"

    def get_system_ssm_path(self, path: str) -> str:
        return f"{self.system_ssm_path}/{path}"

    def get_pipeline_ssm_parameter(
            self,
            scope: core.Stack,
            path: str,
    ) -> str:
        return aws_ssm.StringParameter.from_string_parameter_attributes(
            scope,
            f"{self.unique_id}-{path}",
            parameter_name=self.get_pipeline_ssm_path(path),
        ).string_value

    def get_system_ssm_parameter(
            self,
            scope: core.Stack,
            path: str,
    ) -> str:
        return aws_ssm.StringParameter.from_string_parameter_attributes(
            scope,
            f"{self.unique_id}-{path}",
            parameter_name=self.get_system_ssm_path(path),
        ).string_value
