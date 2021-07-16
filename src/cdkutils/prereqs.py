from typing import Any

import aws_cdk.core as cdk
import boto3
from aws_cdk.aws_sam import CfnApplication

from cdkutils.config import BaseConfig, CommonPipelineConfig


class ConfigStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, pipeline_config: BaseConfig, **kwargs: Any):
        super().__init__(scope, construct_id, **kwargs)

        pipeline_config.to_cdk(self)

        if scope.node.try_get_context("create_secrets"):
            pipeline_config.create_secrets(boto3.Session())
        elif scope.node.try_get_context("delete_secrets"):
            no_recovery = bool(scope.node.try_get_context("force_delete"))
            pipeline_config.delete_secrets(boto3.Session(), no_recovery=no_recovery)


class CleanupDeployStack(cdk.Stack):
    SAR_ACCOUNT_NUMBER = "008258580343"

    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        pipeline_config: CommonPipelineConfig,
        config_id: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.scope = scope
        cleanup_id = f"arn:aws:serverlessrepo:{self._get_region()}:{self.SAR_ACCOUNT_NUMBER}:applications/StackCleanup"
        location = CfnApplication.ApplicationLocationProperty(
            application_id=cleanup_id,
            semantic_version="1.2.0",
        )

        parameters = {
            "FunctionNamePrefix": f"cleanuplambda-{config_id}",
            "ServiceCode": pipeline_config.service.cost_code,
            "ServiceName": pipeline_config.service.name,
            "ServiceOwner": pipeline_config.service.owner,
        }

        CfnApplication(self, "CleanupLambda", location=location, parameters=parameters)

    def _get_region(self) -> Any:
        """
        Gets region from input as there is an issue with running CDK as it inserts values like ${Token[AWS.Region.13]}
        https://github.com/aws/serverless-application-model/issues/694 for more info
        :return: region from context
        """
        cleanup_region = self.scope.node.try_get_context("CleanupRegion")
        if cleanup_region is None:
            raise ValueError("the CleanupRegion must be provided, either via a parameter or CDK context variable")
        return cleanup_region
