from typing import Any

import aws_cdk.core as cdk
import boto3

from cdkutils.config import SharedPipelineConfig


class ConfigStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, pipeline_config: SharedPipelineConfig, **kwargs: Any):
        super().__init__(scope, construct_id, **kwargs)

        pipeline_config.to_cdk(self)

        if scope.node.try_get_context("create_secrets"):
            pipeline_config.create_secrets(boto3.Session())
        elif scope.node.try_get_context("delete_secrets"):
            pipeline_config.delete_secrets(boto3.Session())
