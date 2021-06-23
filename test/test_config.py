from typing import TYPE_CHECKING, Optional, cast
from unittest import TestCase, mock
from unittest.mock import Mock, call

import aws_cdk.core as cdk
import boto3
from aws_cdk.aws_ssm import StringParameter
from moto import mock_secretsmanager, mock_ssm

from cdkutils.config import GitHubConfig, PipelineConfig, PipIndexConfig, ServiceDetails, SsmConfig

if TYPE_CHECKING:
    from mypy_boto3_secretsmanager.client import SecretsManagerClient
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object
    SecretsManagerClient = object


def get_mock_cdk_scope(
    *,
    # GitHubConfig params
    github_repo: Optional[str] = None,
    github_org: Optional[str] = None,
    github_token: Optional[str] = None,
    # ServiceDetails params
    service_name: Optional[str] = None,
    service_owner: Optional[str] = None,
    service_cost_code: Optional[str] = None,
    # SsmConfig params
    ssm_namespace: Optional[str] = None,
    ssm_config_id: Optional[str] = None,
    ssm_config_org: Optional[str] = None,
    # PipIndexConfig params
    pip_index_username: Optional[str] = None,
    pip_index_password: Optional[str] = None,
    pip_index_url: Optional[str] = None,
    # SharedPipelineConfig params
    dev_account_id: Optional[str] = None,
    ci_account_id: Optional[str] = None,
    prod_account_id: Optional[str] = None,
    sonarcloud_token: Optional[str] = None,
    # PipelineConfig params
    unique_id: Optional[str] = None,
    branch_to_build: Optional[str] = None,
    build_lambdas: Optional[bool] = None,
    deploy_to_ci: Optional[bool] = None,
    deploy_to_prod: Optional[bool] = None,
) -> Mock:
    """Helper method to construct a mock CDK construct with the correct CDK context variables"""

    mock_scope = Mock()

    def _mock_try_get_context(key):
        return {
            # GitHubConfig context vars
            "GitHubRepo": github_repo,
            "GitHubOrg": github_org,
            "GitHubToken": github_token,
            # ServiceDetails context vars
            "ServiceName": service_name,
            "ServiceOwner": service_owner,
            "ServiceCostCode": service_cost_code,
            # SsmConfig context vars
            "SsmNamespace": ssm_namespace,
            "SsmConfigId": ssm_config_id,
            "SsmConfigOrg": ssm_config_org,
            # PipIndexConfig params
            "PipIndexUsername": pip_index_username,
            "PipIndexPassword": pip_index_password,
            "PipIndexUrl": pip_index_url,
            # SharedPipelineConfig params
            "DevAccountId": dev_account_id,
            "CiAccountId": ci_account_id,
            "ProdAccountId": prod_account_id,
            "SonarCloudToken": sonarcloud_token,
            # PipelineConfig params
            "UniqueId": unique_id,
            "BranchToBuild": branch_to_build,
            "Local": "True" if not build_lambdas else None,
            "DeployToCi": "True" if deploy_to_ci else None,
            "DeployToProd": "True" if deploy_to_prod else None,
        }.get(key)

    mock_scope.node.try_get_context.side_effect = _mock_try_get_context
    return mock_scope


class SsmConfigTest(TestCase):
    DEFAULT_ORG = "metoffice"
    DEFAULT_CONFIG_ID = "default"

    def test_init_namespace_required(self):
        """
        GIVEN no parameters are passed
        WHEN a new instance is created
        THEN a ValueError is raised due to there being no namespace value
        """

        with self.assertRaises(ValueError):
            SsmConfig()

    def test_init_defaults(self):
        """
        GIVEN only a namespace is supplied WHEN a new instance is created THEN other attributes have default values
        """
        expected_namespace = "test"
        expected_path_prefix = f"/{self.DEFAULT_ORG}/{expected_namespace}/{self.DEFAULT_CONFIG_ID}"
        actual = SsmConfig(namespace=expected_namespace)

        self.assertEqual(self.DEFAULT_ORG, actual.org_name)
        self.assertEqual(expected_namespace, actual.namespace)
        self.assertEqual(self.DEFAULT_CONFIG_ID, actual.config_id)

        self.assertEqual(expected_path_prefix, actual.path_prefix)
        self.assertEqual(f"{expected_path_prefix}/foo", actual.get_full_path("foo"))

    def test_init_load_from_cdk_context(self):
        """GIVEN only cdk_scope is supplied WHEN a new instance is created THEN attributes are read from CDK context"""

        expected_namespace = "test"
        expected_org = "myorg"
        expected_config_id = "myconfig"
        expected_path_prefix = f"/{expected_org}/{expected_namespace}/{expected_config_id}"

        mock_cdk_scope = get_mock_cdk_scope(
            ssm_namespace=expected_namespace, ssm_config_id=expected_config_id, ssm_config_org=expected_org
        )
        actual = SsmConfig(cdk_scope=mock_cdk_scope)

        self.assertEqual(expected_org, actual.org_name)
        self.assertEqual(expected_namespace, actual.namespace)
        self.assertEqual(expected_config_id, actual.config_id)

        self.assertEqual(expected_path_prefix, actual.path_prefix)
        self.assertEqual(f"{expected_path_prefix}/foo", actual.get_full_path("foo"))

    def test_init_kwargs_have_precedence(self):
        """
        GIVEN keyword args are supplied AND a cdk_scope AND context params are set
        WHEN a new instance is created
        THEN CDK context is ignored and attributes are set based on kwargs
        """

        expected_namespace = "test"
        expected_org = "myorg"
        expected_config_id = "myconfig"
        expected_path_prefix = f"/{expected_org}/{expected_namespace}/{expected_config_id}"

        mock_cdk_scope = get_mock_cdk_scope(ssm_namespace="foo", ssm_config_id="baz", ssm_config_org="bar")
        actual = SsmConfig(
            namespace=expected_namespace, org_name=expected_org, config_id=expected_config_id, cdk_scope=mock_cdk_scope
        )

        self.assertEqual(expected_org, actual.org_name)
        self.assertEqual(expected_namespace, actual.namespace)
        self.assertEqual(expected_config_id, actual.config_id)

        self.assertEqual(expected_path_prefix, actual.path_prefix)
        self.assertEqual(f"{expected_path_prefix}/foo", actual.get_full_path("foo"))


class ServiceDetailsTest(TestCase):
    def setUp(self) -> None:
        """common test setup"""
        self.test_ssm_config = SsmConfig(namespace="unittest")

    def test_init_defaults(self):
        """
        GIVEN no arguments supplied WHEN a new instance is created THEN attributes have default values
        """
        actual = ServiceDetails()

        self.assertEqual("", actual.name)
        self.assertEqual("transporttribe@metoffice.gov.uk", actual.owner)
        self.assertEqual("", actual.cost_code)

    def test_init_non_defaults(self):
        """
        GIVEN arguments are supplied WHEN a new instance is created THEN attributes have those values
        """
        expected_name = "Test Service"
        expected_owner = "Transport Tribe"
        expected_cost_code = "ABCDE"
        actual = ServiceDetails(expected_name, expected_cost_code, expected_owner)

        self.assertEqual(expected_name, actual.name)
        self.assertEqual(expected_owner, actual.owner)
        self.assertEqual(expected_cost_code, actual.cost_code)

    def test_load_uses_cdk_context(self):
        """
        GIVEN only cdk_scope is supplied WHEN load is called
        THEN a new instance is returned with values from the CDK context
        """

        expected_name = "Test Service"
        expected_owner = "Transport Tribe"
        expected_cost_code = "ABCDE"

        mock_cdk_scope = get_mock_cdk_scope(
            service_name=expected_name, service_owner=expected_owner, service_cost_code=expected_cost_code
        )
        actual = ServiceDetails.load(self.test_ssm_config, cdk_scope=mock_cdk_scope)

        self.assertEqual(expected_name, actual.name)
        self.assertEqual(expected_owner, actual.owner)
        self.assertEqual(expected_cost_code, actual.cost_code)

    @mock_ssm
    @mock_secretsmanager
    def test_load_uses_ssm(self):
        """
        GIVEN an SsmConfig and boto3.Session are supplied AND no cdk_scope is supplied
        WHEN load is called
        THEN a new instance is returned with values from AWS SSM and SecretsManager
        """
        ssm: SSMClient = boto3.client("ssm")

        expected_name = "Test Service"
        expected_name_ssm_path = self.test_ssm_config.get_full_path("service/name")
        ssm.put_parameter(Name=expected_name_ssm_path, Value=expected_name)

        expected_owner = "Transport Tribe"
        expected_owner_ssm_path = self.test_ssm_config.get_full_path("service/owner")
        ssm.put_parameter(Name=expected_owner_ssm_path, Value=expected_owner)

        expected_cost_code = "ABCDE"
        expected_cost_code_ssm_path = self.test_ssm_config.get_full_path("service/cost_code")
        ssm.put_parameter(Name=expected_cost_code_ssm_path, Value=expected_cost_code)

        actual = ServiceDetails.load(self.test_ssm_config, boto3.Session())

        self.assertEqual(expected_name, actual.name)
        self.assertEqual(expected_name_ssm_path, actual.get_ssm_param_name("name", self.test_ssm_config))

        self.assertEqual(expected_owner, actual.owner)
        self.assertEqual(expected_owner_ssm_path, actual.get_ssm_param_name("owner", self.test_ssm_config))

        self.assertEqual(expected_cost_code, actual.cost_code)
        self.assertEqual(expected_cost_code_ssm_path, actual.get_ssm_param_name("cost_code", self.test_ssm_config))

    @mock_ssm
    @mock_secretsmanager
    def test_load_context_vars_have_precedence(self):
        """
        GIVEN an SsmConfig, boto3.Session and cdk_scope are supplied
        WHEN load is called
        THEN a new instance is returned with values from cdk_scope
        AND values from SSM/Secrets Manager where cdk_scope doesn't have a context variable value
        """
        ssm: SSMClient = boto3.client("ssm")

        expected_name = "Test Service"
        expected_name_ssm_path = self.test_ssm_config.get_full_path("service/name")
        ssm.put_parameter(Name=expected_name_ssm_path, Value="something_else")

        expected_owner = "Transport Tribe"
        expected_owner_ssm_path = self.test_ssm_config.get_full_path("service/owner")
        ssm.put_parameter(Name=expected_owner_ssm_path, Value="something else")

        expected_cost_code = "ABCDE"
        expected_cost_code_ssm_path = self.test_ssm_config.get_full_path("service/cost_code")
        ssm.put_parameter(Name=expected_cost_code_ssm_path, Value=expected_cost_code)

        cdk_scope = get_mock_cdk_scope(service_name=expected_name, service_owner=expected_owner)
        actual = ServiceDetails.load(self.test_ssm_config, boto3.Session(), cdk_scope)

        self.assertEqual(expected_name, actual.name)
        self.assertEqual(expected_name_ssm_path, actual.get_ssm_param_name("name", self.test_ssm_config))

        self.assertEqual(expected_owner, actual.owner)
        self.assertEqual(expected_owner_ssm_path, actual.get_ssm_param_name("owner", self.test_ssm_config))

        self.assertEqual(expected_cost_code, actual.cost_code)
        self.assertEqual(expected_cost_code_ssm_path, actual.get_ssm_param_name("cost_code", self.test_ssm_config))

    def test_get_ssm_param_name(self):
        """GIVEN a valid attribute name WHEN get_ssm_param_name is called THEN the correct SSM path is returned"""
        expected_name_ssm_path = self.test_ssm_config.get_full_path("service/name")
        expected_owner_ssm_path = self.test_ssm_config.get_full_path("service/owner")
        expected_cost_code_ssm_path = self.test_ssm_config.get_full_path("service/cost_code")

        actual = ServiceDetails()

        self.assertEqual(expected_name_ssm_path, actual.get_ssm_param_name("name", self.test_ssm_config))
        self.assertEqual(expected_name_ssm_path, ServiceDetails.get_ssm_param_name("name", self.test_ssm_config))
        self.assertEqual(expected_owner_ssm_path, actual.get_ssm_param_name("owner", self.test_ssm_config))
        self.assertEqual(expected_owner_ssm_path, ServiceDetails.get_ssm_param_name("owner", self.test_ssm_config))
        self.assertEqual(expected_cost_code_ssm_path, actual.get_ssm_param_name("cost_code", self.test_ssm_config))
        self.assertEqual(
            expected_cost_code_ssm_path, ServiceDetails.get_ssm_param_name("cost_code", self.test_ssm_config)
        )

    def test_get_ssm_param_name_doesnt_exist(self):
        """GIVEN an invalid attribute WHEN get_ssm_param_name is called THEN a KeyError is raised"""
        with self.assertRaises(KeyError):
            ServiceDetails.get_ssm_param_name("does not exist", self.test_ssm_config)

    def test_apply_tags_to(self):
        """GIVEN a CDK construct as a scope WHEN apply_tags_to is called THEN correct tags are applied to that scope"""
        expected_name = "Test Service"
        expected_owner = "Transport Tribe"
        expected_cost_code = "ABCDE"
        cdk_scope = cdk.App()

        service_details = ServiceDetails(expected_name, expected_cost_code, expected_owner)

        with mock.patch("cdkutils.config.cdk.Tags") as mock_tags:
            service_details.apply_tags_to(cdk_scope)

        mock_tags.of.assert_any_call(cdk_scope)
        self.assertEqual(3, mock_tags.of.return_value.add.call_count)
        mock_tags.of.return_value.add.has_calls(
            [
                call("ServiceName", expected_name),
                call("ServiceOwner", expected_owner),
                call("ServiceCode", expected_cost_code),
            ]
        )

    def test_get_secret_name_not_a_secret(self):
        """
        GIVEN an attribute that exists but is not a Secret WHEN get_secret_name is called THEN a KeyError is raised
        """
        with self.assertRaises(KeyError):
            ServiceDetails.get_secret_name("name", self.test_ssm_config)

    def test_to_cdk(self):
        expected_name = "to_cdk Test"
        expected_name_ssm_path = self.test_ssm_config.get_full_path("service/name")
        expected_owner = "Transport Tribe"
        expected_owner_ssm_path = self.test_ssm_config.get_full_path("service/owner")
        expected_cost_code = "FGHI"
        expected_cost_code_ssm_path = self.test_ssm_config.get_full_path("service/cost_code")

        cdk_app = cdk.App()
        cdk_scope = cdk.Stack(cdk_app)

        service_details = ServiceDetails(expected_name, expected_cost_code, expected_owner)
        service_details.to_cdk(cdk_scope, self.test_ssm_config)

        self.assertEqual(3, len(cdk_scope.node.children))
        cfn_params = [
            cdk.Tokenization.reverse_string(p.parameter_name).first_token.target
            for p in cdk_scope.node.children
            if isinstance(p, StringParameter)
        ]
        ssms = {param.name: param.value for param in cfn_params}
        expected_ssms = {
            expected_name_ssm_path: expected_name,
            expected_owner_ssm_path: expected_owner,
            expected_cost_code_ssm_path: expected_cost_code,
        }
        self.assertEqual(expected_ssms, ssms)


class GitHubConfigTest(TestCase):
    def setUp(self) -> None:
        """common test setup"""
        self.test_ssm_config = SsmConfig(namespace="unittest")

    def test_init_defaults(self):
        """
        GIVEN no arguments supplied WHEN a new instance is created THEN attributes have default values
        """
        actual = GitHubConfig()

        self.assertEqual("MetOffice", actual.org)
        self.assertEqual("", actual.repo)
        self.assertEqual("", actual.oauth_token)

    def test_init_non_defaults(self):
        """
        GIVEN arguments are supplied WHEN a new instance is created THEN attributes have those values
        """
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = "ABCDE"
        actual = GitHubConfig(expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(expected_repo, actual.repo)
        self.assertEqual(expected_oauth_token, actual.oauth_token)
        self.assertEqual(expected_org, actual.org)

    def test__str__(self):
        """WHEN an instance is passed to str() THEN the expected string is generated"""
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = "ABCDE"
        gh_config = GitHubConfig(expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(f"https://github.com/{expected_org}/{expected_repo}", str(gh_config))

    def test__repr__(self):
        """
        WHEN an instance with an OAUTH token is passed to repr()
        THEN the expected string is generated AND the OAUTH token is obfuscated
        """
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = "ABCDE"
        gh_config = GitHubConfig(expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(f"GitHubConfig({expected_repo!r}, ****, {expected_org!r})", repr(gh_config))

    def test__repr__token_unset(self):
        """WHEN an instance without an OAUTH token is passed to repr() THEN the expected string is generated"""
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = ""
        gh_config = GitHubConfig(expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(
            f"GitHubConfig({expected_repo!r}, {expected_oauth_token!r}, {expected_org!r})", repr(gh_config)
        )

    def test_load_uses_cdk_context(self):
        """
        GIVEN only cdk_scope is supplied WHEN load is called
        THEN a new instance is returned with values from the CDK context
        """

        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = "1234567890"

        mock_cdk_scope = get_mock_cdk_scope(
            github_repo=expected_repo, github_org=expected_org, github_token=expected_oauth_token
        )
        actual = GitHubConfig.load(self.test_ssm_config, cdk_scope=mock_cdk_scope)

        self.assertEqual(expected_repo, actual.repo)
        self.assertEqual(expected_oauth_token, actual.oauth_token)
        self.assertEqual(expected_org, actual.org)

    @mock_ssm
    @mock_secretsmanager
    def test_load_uses_ssm(self):
        """
        GIVEN an SsmConfig and boto3.Session are supplied AND no cdk_scope is supplied
        WHEN load is called
        THEN a new instance is returned with values from AWS SSM and SecretsManager
        """
        ssm: SSMClient = boto3.client("ssm")
        secrets_mgr: SecretsManagerClient = boto3.client("secretsmanager")

        expected_repo = "cdk_utils"
        expected_repo_ssm_path = self.test_ssm_config.get_full_path("pipeline/github/repository")
        ssm.put_parameter(Name=expected_repo_ssm_path, Value=expected_repo)

        expected_org = "MyOrg"
        expected_org_ssm_path = self.test_ssm_config.get_full_path("pipeline/github/organisation")
        ssm.put_parameter(Name=expected_org_ssm_path, Value=expected_org)

        expected_oauth_token = "1234567890"
        expected_oauth_token_ssm_path = self.test_ssm_config.get_full_path("pipeline/github/oauth_token")
        secrets_mgr.create_secret(Name=expected_oauth_token_ssm_path, SecretString=expected_oauth_token)

        actual = GitHubConfig.load(self.test_ssm_config, boto3.Session())

        self.assertEqual(expected_repo, actual.repo)
        self.assertEqual(expected_repo_ssm_path, actual.get_ssm_param_name("repo", self.test_ssm_config))

        self.assertEqual(expected_org, actual.org)
        self.assertEqual(expected_org_ssm_path, actual.get_ssm_param_name("org", self.test_ssm_config))

        self.assertEqual(expected_oauth_token, actual.oauth_token)
        self.assertEqual(expected_oauth_token_ssm_path, actual.get_secret_name("oauth_token", self.test_ssm_config))

    def test_get_ssm_param_name_doesnt_exist(self):
        """GIVEN an invalid attribute WHEN get_ssm_param_name is called THEN a KeyError is raised"""
        with self.assertRaises(KeyError):
            GitHubConfig.get_ssm_param_name("does not exist", self.test_ssm_config)

    def test_get_ssm_param_name_not_an_ssm(self):
        """
        GIVEN a valid attribute that is stored in Secrets Manager (not SSM)
        WHEN get_ssm_param_name is called
        THEN a KeyError is raised
        """
        with self.assertRaises(KeyError):
            GitHubConfig.get_ssm_param_name("oauth_token", self.test_ssm_config)

    def test_get_secret_name_not_a_secret(self):
        """
        GIVEN an attribute that exists but is not a Secret WHEN get_secret_name is called THEN a KeyError is raised
        """
        with self.assertRaises(KeyError):
            GitHubConfig.get_secret_name("org", self.test_ssm_config)


class PipelineConfigTest(TestCase):
    def setUp(self) -> None:
        """common test setup"""
        self.test_ssm_config = SsmConfig(namespace="unittest")

    @mock_ssm
    @mock_secretsmanager
    def test_load(self):

        expected_unique_id = "bibbity"
        expected_branch_to_build = "ADS-386_convert_pipeline_config_to_cdk"
        expected_build_lambdas = False
        expected_deploy_to_prod = True
        expected_deploy_to_ci = True
        expected_service_details = ServiceDetails("PipelineConfigTest", "ABCDE")
        expected_dev_account_id = "12334509876"
        expected_ci_account_id = "6789012345"
        expected_prod_account_id = "0987654321"
        expected_github_config = GitHubConfig("cdk_utils", "a1b2c3d4e5f6g7h8i9j0")
        expected_pip_config = PipIndexConfig("foo@metoffice.gov.uk", "password")
        expected_sonarcloud_token = "fhaoi4oyt5988439798vbr87439bvdi89gf7g67d6fd56f6g76h6"
        expected_pipeline_config = PipelineConfig(
            self.test_ssm_config,
            unique_id=expected_unique_id,
            branch_to_build=expected_branch_to_build,
            build_lambdas=expected_build_lambdas,
            deploy_to_ci=expected_deploy_to_ci,
            deploy_to_prod=expected_deploy_to_prod,
            service=expected_service_details,
            dev_account_id=expected_dev_account_id,
            ci_account_id=expected_ci_account_id,
            prod_account_id=expected_prod_account_id,
            github=expected_github_config,
            pip=expected_pip_config,
            sonarcloud_token=expected_sonarcloud_token,
        )

        mock_cdk_scope = get_mock_cdk_scope(
            unique_id=expected_unique_id,
            branch_to_build=expected_branch_to_build,
            build_lambdas=expected_build_lambdas,
            deploy_to_ci=expected_deploy_to_ci,
            deploy_to_prod=expected_deploy_to_prod,
            service_name=expected_service_details.name,
            service_owner=expected_service_details.owner,
            service_cost_code=expected_service_details.cost_code,
            dev_account_id=expected_dev_account_id,
            ci_account_id=expected_ci_account_id,
            prod_account_id=expected_prod_account_id,
            github_org=expected_github_config.org,
            github_repo=expected_github_config.repo,
            github_token=expected_github_config.oauth_token,
            pip_index_username=expected_pip_config.username,
            pip_index_password=expected_pip_config.password,
            pip_index_url=expected_pip_config.url,
            sonarcloud_token=expected_sonarcloud_token,
        )

        actual = cast(PipelineConfig, PipelineConfig.load(self.test_ssm_config, boto3.Session(), mock_cdk_scope))

        self.assertEqual(expected_pipeline_config, actual)
