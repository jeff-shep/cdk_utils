import unittest
from unittest.mock import Mock, PropertyMock

import boto3
from moto import mock_secretsmanager, mock_ssm

from cdkutils.cdk_utils import PipelineConfig


class TestPipelineConfig(unittest.TestCase):
    """
    Tests for the PipelineConfig class.
    """

    def setUp(self):
        mock_app = Mock()
        mock_app.node.try_get_context.side_effect = [
            "unique-id",
            "namespace",
            "pipeline_ssm_config_id",
            "system_ssm_config_id",
            "branch_to_build",
            "DeployToCi",
            "DeployToProd",
            "Local",
        ]
        self.instance = PipelineConfig(app=mock_app, default_ssm_namespace="default")

    def test_given_a_valid_pipeline_ssm_path_when_get_pipeline_ssm_path_called_then_return_valid_ssm_path(self):
        result = self.instance.get_pipeline_ssm_path(path="valid/ssm/path")
        assert result == "/metoffice/namespace/pipeline_ssm_config_id/valid/ssm/path"

    def test_given_a_valid_system_ssm_path_when_get_system_ssm_path_is_called_then_return_valid_ssm_path(self):
        result = self.instance.get_system_ssm_path(path="valid/ssm/path")
        assert result == "/metoffice/namespace/system_ssm_config_id/valid/ssm/path"

    @mock_ssm
    def test_given_a_valid_path_when_get_pipeline_ssm_parameter_is_called_then_return_ssm_parameter(self):
        session = boto3.Session(region_name="eu-west-2")
        ssm = session.client("ssm")
        ssm.put_parameter(
            Name="/metoffice/namespace/pipeline_ssm_config_id/valid/ssm/path",
            Description="A test parameter",
            Value="value of parameter",
            Type="String",
        )
        result = self.instance.get_pipeline_ssm_parameter(path="valid/ssm/path")
        assert result == "value of parameter"

    @mock_ssm
    def test_given_a_valid_path_when_get_system_ssm_parameter_is_called_then_return_ssm_parameter(self):
        session = boto3.Session(region_name="eu-west-2")
        ssm = session.client("ssm")
        ssm.put_parameter(
            Name="/metoffice/namespace/system_ssm_config_id/valid/ssm/path",
            Description="A test parameter",
            Value="value of parameter",
            Type="String",
        )
        result = self.instance.get_system_ssm_parameter(path="valid/ssm/path")
        assert result == "value of parameter"

    @mock_secretsmanager
    def test_given_a_valid_path_when_get_secret_is_called_then_return_secret_parameter(self):
        session = boto3.Session(region_name="eu-west-2")
        secrets_manager = session.client("secretsmanager")
        secrets_manager.create_secret(Name="valid/ssm/path", SecretString="foosecret")
        result = self.instance.get_secret(path="valid/ssm/path")
        assert result == "foosecret"

    @mock_secretsmanager
    def test_given_a_valid_path_when_get_secret_is_called_then_return_secret_arn(self):
        session = boto3.Session(region_name="eu-west-2")
        secrets_manager = session.client("secretsmanager")
        response = secrets_manager.create_secret(Name="valid/ssm/path", SecretString="foosecret")
        result = self.instance.get_secret_arn(path="valid/ssm/path")
        assert result == response["ARN"]

    def test_give_a_valid_stack_output_when_get_artifact_for_stack_output_is_called_then_return_stack_output(self):
        mock_stack_output = Mock()
        cfn_output = Mock()
        mock_pipeline = Mock()
        mock_artifact_file = Mock()
        mock_artifact = Mock()

        type(mock_artifact_file).artifact = PropertyMock(return_value=mock_artifact)
        type(mock_stack_output).artifact_file = PropertyMock(return_value=mock_artifact_file)

        mock_pipeline.stack_output.return_value = mock_stack_output
        result = self.instance.get_artifact_for_stack_output(mock_pipeline, cfn_output)

        assert result == mock_artifact
