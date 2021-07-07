from unittest import TestCase
from unittest.mock import Mock

import aws_cdk.core as cdk
from moto import mock_secretsmanager

from cdkutils.config import CommonPipelineConfig
from cdkutils.prereqs import ConfigStack


class ConfigStackTest(TestCase):
    def setUp(self) -> None:
        self.mock_config = Mock(spec=CommonPipelineConfig)

    def test_init(self):
        config_stack = ConfigStack(cdk.App(), "test", self.mock_config)

        self.mock_config.to_cdk.assert_called_once_with(config_stack)
        self.mock_config.create_secrets.assert_not_called()
        self.mock_config.delete_secrets.assert_not_called()

    @mock_secretsmanager
    def test_init_create_secrets(self):

        config_stack = ConfigStack(cdk.App(context={"create_secrets": "True"}), "test", self.mock_config)

        self.mock_config.to_cdk.assert_called_once_with(config_stack)
        self.mock_config.create_secrets.assert_called_once()
        self.mock_config.delete_secrets.assert_not_called()

    @mock_secretsmanager
    def test_init_delete_secrets(self):

        config_stack = ConfigStack(cdk.App(context={"delete_secrets": "True"}), "test", self.mock_config)

        self.mock_config.to_cdk.assert_called_once_with(config_stack)
        self.mock_config.create_secrets.assert_not_called()
        self.mock_config.delete_secrets.assert_called_once()
