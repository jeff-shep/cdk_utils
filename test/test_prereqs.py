from unittest import TestCase
from unittest.mock import Mock

import aws_cdk.core as cdk
from jsii.errors import JSIIError
from moto import mock_secretsmanager

from cdkutils.config import CommonPipelineConfig, SsmConfig
from cdkutils.prereqs import CleanupDeployStack, ConfigStack


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


class CleanupDeployStackTest(TestCase):
    def setUp(self) -> None:
        self.mock_context = {
            "SsmNamespace": "test",
            "ServiceName": "test",
            "ServiceCostCode": "TEST",
            "GitHubRepo": "test",
            "PipIndexUsername": "test",
            "MgmtAccountId": "test",
            "DevAccountId": "test",
            "CiAccountId": "test",
            "ProdAccountId": "test",
            "SonarCloudToken": "test",
            "SsmConfigId": "test",
            "GitHubToken": "test",
            "PipIndexPassword": "test",
            "create_secrets": False,
            "CleanupRegion": "eu-west-2",
        }

    def test_init(self):
        app = cdk.App(context=self.mock_context)
        ssm_config = SsmConfig(cdk_scope=app)
        shared_config = CommonPipelineConfig.load(ssm_config, cdk_scope=app)

        shared_config.service.apply_tags_to(app)
        test_stack = CleanupDeployStack(
            app, f"CleanupStack-{ssm_config.config_id}", shared_config, ssm_config.config_id
        )

        self.assertEqual("CleanupStack-test", test_stack.stack_name)
        self.assertEqual("eu-west-2", test_stack._get_region())
        self.assertEqual("hnb659fds", test_stack.default_qualifier)
        self.assertEqual("cleanuplambda-test-eu-west-1", test_stack._get_lambda_name("eu-west-1"))
        self.assertEqual(
            f"arn:aws:iam::test:role/cdk-hnb659fds-cfn-exec-role-test-eu-west-2", test_stack.cfn_execution_role
        )

    def test_no_region_error(self):
        mock_context = {k: v for k, v in self.mock_context.items() if k != "CleanupRegion"}
        app = cdk.App(context=mock_context)
        ssm_config = SsmConfig(cdk_scope=app)
        shared_config = CommonPipelineConfig.load(ssm_config, cdk_scope=app)

        shared_config.service.apply_tags_to(app)
        self.assertRaises(
            ValueError,
            CleanupDeployStack,
            app,
            f"CleanupStack-{ssm_config.config_id}",
            shared_config,
            ssm_config.config_id,
        )

        try:
            CleanupDeployStack(app, f"CleanupStack1-{ssm_config.config_id}", shared_config, ssm_config.config_id)
        except ValueError as e:
            self.assertEqual(
                "the CleanupRegion must be provided, either via a parameter or CDK context variable", str(e)
            )

    def test_no_same_name_stacks(self):
        app = cdk.App(context=self.mock_context)
        ssm_config = SsmConfig(cdk_scope=app)
        shared_config = CommonPipelineConfig.load(ssm_config, cdk_scope=app)

        shared_config.service.apply_tags_to(app)
        CleanupDeployStack(app, f"CleanupStack-{ssm_config.config_id}", shared_config, ssm_config.config_id)
        self.assertRaises(
            JSIIError,
            CleanupDeployStack,
            app,
            f"CleanupStack-{ssm_config.config_id}",
            shared_config,
            ssm_config.config_id,
        )

        try:
            CleanupDeployStack(app, f"CleanupStack-{ssm_config.config_id}", shared_config, ssm_config.config_id)
        except JSIIError as e:
            self.assertEqual("There is already a Construct with name 'CleanupStack-test' in App", str(e))
