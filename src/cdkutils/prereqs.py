from typing import Any

import aws_cdk.core as cdk
import boto3

from cdkutils.config import BaseConfig


class ConfigStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, pipeline_config: BaseConfig, **kwargs: Any):
        super().__init__(scope, construct_id, **kwargs)

        pipeline_config.to_cdk(self)

        if scope.node.try_get_context("create_secrets"):
            pipeline_config.create_secrets(boto3.Session())
        elif scope.node.try_get_context("delete_secrets"):
            no_recovery = bool(scope.node.try_get_context("force_delete"))
            pipeline_config.delete_secrets(boto3.Session(), no_recovery=no_recovery)
