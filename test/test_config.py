from typing import TYPE_CHECKING, Optional
from unittest import TestCase, mock
from unittest.mock import Mock, call

import aws_cdk.core as cdk
import boto3
from aws_cdk.aws_ssm import StringParameter
from moto import mock_secretsmanager, mock_ssm

from cdkutils.config import (
    AccountIdConfig,
    AttributeNotFoundException,
    CommonPipelineConfig,
    ConfigException,
    GitHubConfig,
    PersistedAttribute,
    PipelineConfig,
    PipIndexConfig,
    ServiceDetails,
    SsmConfig,
)

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
    mgmt_account_id: Optional[str] = None,
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

    context_vars_dict = {
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
        "MgmtAccountId": mgmt_account_id,
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
    }

    def _mock_try_get_context(key):
        return context_vars_dict.get(key)

    mock_scope = Mock()
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

    def test_str(self):
        """GIVEN a valid SsmConfig object WHEN its __str__ method is called THEN it returns its path_prefix attribute"""
        expected_namespace = "test"
        expected_path_prefix = f"/{self.DEFAULT_ORG}/{expected_namespace}/{self.DEFAULT_CONFIG_ID}"
        actual = SsmConfig(namespace=expected_namespace)

        self.assertEqual(expected_path_prefix, str(actual))


class ServiceDetailsTest(TestCase):
    def setUp(self) -> None:
        """common test setup"""
        self.test_ssm_config = SsmConfig(namespace="unittest")

    def test_init_defaults(self):
        """
        GIVEN no arguments supplied WHEN a new instance is created THEN attributes have default values
        """
        actual = ServiceDetails(self.test_ssm_config)

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
        actual = ServiceDetails(self.test_ssm_config, expected_name, expected_cost_code, expected_owner)

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
        ssm: SSMClient = boto3.client("ssm", region_name="eu-west-2")

        expected_name = "Test Service"
        expected_name_ssm_path = self.test_ssm_config.get_full_path("service/name")
        ssm.put_parameter(Name=expected_name_ssm_path, Value=expected_name)

        expected_owner = "Transport Tribe"
        expected_owner_ssm_path = self.test_ssm_config.get_full_path("service/owner")
        ssm.put_parameter(Name=expected_owner_ssm_path, Value=expected_owner)

        expected_cost_code = "ABCDE"
        expected_cost_code_ssm_path = self.test_ssm_config.get_full_path("service/cost_code")
        ssm.put_parameter(Name=expected_cost_code_ssm_path, Value=expected_cost_code)

        actual = ServiceDetails.load(self.test_ssm_config, boto3.Session(region_name="eu-west-2"))

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
        ssm: SSMClient = boto3.client("ssm", region_name="eu-west-2")

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
        actual = ServiceDetails.load(self.test_ssm_config, boto3.Session(region_name="eu-west-2"), cdk_scope)

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

        actual = ServiceDetails(self.test_ssm_config)

        self.assertEqual(expected_name_ssm_path, actual.get_ssm_param_name("name", self.test_ssm_config))
        self.assertEqual(expected_owner_ssm_path, actual.get_ssm_param_name("owner", self.test_ssm_config))
        self.assertEqual(expected_cost_code_ssm_path, actual.get_ssm_param_name("cost_code", self.test_ssm_config))

    def test_get_ssm_param_name_doesnt_exist(self):
        """GIVEN an invalid attribute WHEN get_ssm_param_name is called THEN a KeyError is raised"""
        with self.assertRaises(KeyError):
            ServiceDetails(self.test_ssm_config).get_ssm_param_name("does not exist")

    def test_apply_tags_to(self):
        """GIVEN a CDK construct as a scope WHEN apply_tags_to is called THEN correct tags are applied to that scope"""
        expected_name = "Test Service"
        expected_owner = "Transport Tribe"
        expected_cost_code = "ABCDE"
        cdk_scope = cdk.App()

        service_details = ServiceDetails(self.test_ssm_config, expected_name, expected_cost_code, expected_owner)

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
            ServiceDetails(self.test_ssm_config).get_secret_name("name")

    def test_to_cdk(self):
        expected_name = "to_cdk Test"
        expected_name_ssm_path = self.test_ssm_config.get_full_path("service/name")
        expected_owner = "Transport Tribe"
        expected_owner_ssm_path = self.test_ssm_config.get_full_path("service/owner")
        expected_cost_code = "FGHI"
        expected_cost_code_ssm_path = self.test_ssm_config.get_full_path("service/cost_code")

        cdk_app = cdk.App()
        cdk_scope = cdk.Stack(cdk_app)

        service_details = ServiceDetails(self.test_ssm_config, expected_name, expected_cost_code, expected_owner)
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
        actual = GitHubConfig(self.test_ssm_config)

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
        actual = GitHubConfig(self.test_ssm_config, expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(expected_repo, actual.repo)
        self.assertEqual(expected_oauth_token, actual.oauth_token)
        self.assertEqual(expected_org, actual.org)

    def test__str__(self):
        """WHEN an instance is passed to str() THEN the expected string is generated"""
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = "ABCDE"
        gh_config = GitHubConfig(self.test_ssm_config, expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(f"https://github.com/{expected_org}/{expected_repo}", str(gh_config))

    def test__repr__(self):
        """
        WHEN an instance with an OAUTH token is passed to repr()
        THEN the expected string is generated AND the OAUTH token is obfuscated
        """
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = "ABCDE"
        gh_config = GitHubConfig(self.test_ssm_config, expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(
            f"GitHubConfig({self.test_ssm_config!r}, {expected_repo!r}, ****, {expected_org!r})", repr(gh_config)
        )

    def test__repr__token_unset(self):
        """WHEN an instance without an OAUTH token is passed to repr() THEN the expected string is generated"""
        expected_repo = "cdk_utils"
        expected_org = "MyOrg"
        expected_oauth_token = ""
        gh_config = GitHubConfig(self.test_ssm_config, expected_repo, expected_oauth_token, expected_org)

        self.assertEqual(
            f"GitHubConfig({self.test_ssm_config!r}, {expected_repo!r}, {expected_oauth_token!r}, {expected_org!r})",
            repr(gh_config),
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
        ssm: SSMClient = boto3.client("ssm", region_name="eu-west-2")
        secrets_mgr: SecretsManagerClient = boto3.client("secretsmanager", region_name="eu-west-2")

        expected_repo = "cdk_utils"
        expected_repo_ssm_path = self.test_ssm_config.get_full_path("pipeline/github/repository")
        ssm.put_parameter(Name=expected_repo_ssm_path, Value=expected_repo)

        expected_org = "MyOrg"
        expected_org_ssm_path = self.test_ssm_config.get_full_path("pipeline/github/organisation")
        ssm.put_parameter(Name=expected_org_ssm_path, Value=expected_org)

        expected_oauth_token = "1234567890"
        expected_oauth_token_ssm_path = self.test_ssm_config.get_full_path("pipeline/github/oauth_token")
        secrets_mgr.create_secret(Name=expected_oauth_token_ssm_path, SecretString=expected_oauth_token)

        actual = GitHubConfig.load(self.test_ssm_config, boto3.Session(region_name="eu-west-2"))

        self.assertEqual(expected_repo, actual.repo)
        self.assertEqual(expected_repo_ssm_path, actual.get_ssm_param_name("repo", self.test_ssm_config))

        self.assertEqual(expected_org, actual.org)
        self.assertEqual(expected_org_ssm_path, actual.get_ssm_param_name("org", self.test_ssm_config))

        self.assertEqual(expected_oauth_token, actual.oauth_token)
        self.assertEqual(expected_oauth_token_ssm_path, actual.get_secret_name("oauth_token", self.test_ssm_config))

    def test_get_ssm_param_name_doesnt_exist(self):
        """GIVEN an invalid attribute WHEN get_ssm_param_name is called THEN a KeyError is raised"""
        with self.assertRaises(KeyError):
            GitHubConfig(self.test_ssm_config).get_ssm_param_name("does not exist")

    def test_get_ssm_param_name_not_an_ssm(self):
        """
        GIVEN a valid attribute that is stored in Secrets Manager (not SSM)
        WHEN get_ssm_param_name is called
        THEN a KeyError is raised
        """
        with self.assertRaises(KeyError):
            GitHubConfig(self.test_ssm_config).get_ssm_param_name("oauth_token")

    def test_get_secret_name_not_a_secret(self):
        """
        GIVEN an attribute that exists but is not a Secret WHEN get_secret_name is called THEN a KeyError is raised
        """
        with self.assertRaises(KeyError):
            GitHubConfig(self.test_ssm_config).get_secret_name("org")


class PipIndexConfigTest(TestCase):
    def setUp(self) -> None:
        """common test setup"""
        self.test_ssm_config = SsmConfig(namespace="unittest")

    @mock_ssm
    @mock_secretsmanager
    def test_load_attribute_doesnt_exist_on_aws(self):
        """
        GIVEN that a parameter doesn't exist on AWS WHEN load is called THEN an AttributeNotFoundException is raised
        """

        with self.assertRaises(AttributeNotFoundException):
            PipIndexConfig.load(self.test_ssm_config, boto3.Session(region_name="eu-west-2"))

    def test_credentials(self):
        """
        GIVEN username, password, and url are supplied
        WHEN credentials property is accessed
        THEN correct credentials returned
        """
        test_username = "foo@metoffice.gov.uk"
        test_pass = "this_is_the_password"
        test_url = "myindex.somewhere.com/foo/bar/baz"
        expected_credentials = f"https://{test_username}:{test_pass}@{test_url}"

        pip_conf = PipIndexConfig(self.test_ssm_config, test_username, test_pass, f"https://{test_url}")

        self.assertEqual(expected_credentials, pip_conf.credentials)

    def test_credentials_default_url(self):
        """
        GIVEN username and password are supplied WHEN credentials property is accessed THEN correct credentials returned
        """
        test_username = "foo@metoffice.gov.uk"
        test_pass = "this_is_the_password"
        expected_credentials = f"https://{test_username}:{test_pass}@metoffice.jfrog.io/metoffice/api/pypi/pypi/simple"

        pip_conf = PipIndexConfig(self.test_ssm_config, test_username, test_pass)

        self.assertEqual(expected_credentials, pip_conf.credentials)

    @mock_ssm
    @mock_secretsmanager
    def test_load_with_properties(self):
        """
        GIVEN an SsmConfig and boto3.Session AND a property that is persisted
        WHEN PipIndexConfig.load is called
        THEN the expected instance is returned

        This test is particularly interested in the handling of the property, because the credentials property is
        derived from the other attributes, not loaded from AWS or CDK (although it is written to AWS)
        """
        ssm: SSMClient = boto3.client("ssm", region_name="eu-west-2")
        secret_mgr: SecretsManagerClient = boto3.client("secretsmanager", region_name="eu-west-2")

        expected_username = "foo@metoffice.gov.uk"
        ssm.put_parameter(
            Name=self.test_ssm_config.get_full_path("pipeline/python-pip/username"), Value=expected_username
        )

        expected_pass = "this_is_the_password"
        secret_mgr.create_secret(
            Name=self.test_ssm_config.get_full_path("pipeline/python-pip/password"), SecretString=expected_pass
        )

        url_part = "metoffice.jfrog.io/metoffice/api/pypi/pypi/simple"
        ssm.put_parameter(
            Name=self.test_ssm_config.get_full_path("pipeline/python-pip/index-url"),
            Value=f"https://{url_part}",
        )

        secret_mgr.create_secret(
            Name=self.test_ssm_config.get_full_path("pipeline/python-pip/auth"), SecretString="Unexpected Credentials"
        )  # This Secret should be ignored by the load method

        expected = PipIndexConfig(self.test_ssm_config, expected_username, expected_pass)
        actual = PipIndexConfig.load(self.test_ssm_config, boto3.Session(region_name="eu-west-2"))

        self.assertEqual(expected.credentials, actual.credentials)

    def test_get_persisted_attribute_with_credentials(self):
        """
        WHEN get_persisted_attribute is called with credentials
        THEN a PersistedAttribute instance for the credentials attribute is returned

        PipIndexConfig.credentials is a property with its value derived dynamically from other attributes, so the
        handling is slightly different compared to normal attributes
        """
        expected = PersistedAttribute("credentials", None, "pipeline/python-pip/auth", True)
        actual = PipIndexConfig.get_persisted_attribute("credentials")
        self.assertEqual(expected, actual)

    def test_get_cdk_secret_value(self):
        test_username = "foo@metoffice.gov.uk"
        test_pass = "this_is_the_password"
        pip_conf = PipIndexConfig(self.test_ssm_config, test_username, test_pass)
        expected_secret_value = cdk.SecretValue(value=pip_conf.credentials)

        actual = pip_conf.get_cdk_secret_value("credentials")

        self.assertEqual(expected_secret_value.plain_text, actual.plain_text)

    def test_get_cdk_secret_value_not_a_secret(self):

        with self.assertRaises(KeyError):
            PipIndexConfig(self.test_ssm_config).get_cdk_secret_value("username")

    @mock_ssm
    @mock_secretsmanager
    def test_create_secrets(self):
        test_username = "foo@metoffice.gov.uk"
        test_pass = "this_is_the_password"
        pip_conf = PipIndexConfig(self.test_ssm_config, test_username, test_pass)

        pip_conf.create_secrets(boto3.Session(region_name="eu-west-2"))

        secrets_mgr: SecretsManagerClient = boto3.client("secretsmanager", region_name="eu-west-2")
        self.assertEqual(
            pip_conf.credentials,
            secrets_mgr.get_secret_value(SecretId=pip_conf.get_secret_name("credentials"))["SecretString"],
        )
        self.assertEqual(
            pip_conf.password,
            secrets_mgr.get_secret_value(SecretId=pip_conf.get_secret_name("password"))["SecretString"],
        )
        with self.assertRaises(secrets_mgr.exceptions.ResourceNotFoundException):
            secrets_mgr.get_secret_value(SecretId=pip_conf.get_ssm_param_name("username"))
        with self.assertRaises(secrets_mgr.exceptions.ResourceNotFoundException):
            secrets_mgr.get_secret_value(SecretId=pip_conf.get_ssm_param_name("url"))

    @mock_ssm
    @mock_secretsmanager
    def test_delete_secrets(self):
        test_username = "foo@metoffice.gov.uk"
        test_pass = "this_is_the_password"
        pip_conf = PipIndexConfig(self.test_ssm_config, test_username, test_pass)

        credentials_secret_name = pip_conf.get_secret_name("credentials")
        password_secret_name = pip_conf.get_secret_name("password")

        secrets_mgr: SecretsManagerClient = boto3.client("secretsmanager", region_name="eu-west-2")
        secrets_mgr.create_secret(Name=credentials_secret_name, SecretString=pip_conf.credentials)
        secrets_mgr.create_secret(Name=password_secret_name, SecretString=pip_conf.password)

        pip_conf.delete_secrets(boto3.Session(region_name="eu-west-2"))

        # InvalidRequestException for secrets that have been marked deleted, but not yet deleted
        with self.assertRaises(secrets_mgr.exceptions.InvalidRequestException):
            secrets_mgr.get_secret_value(SecretId=credentials_secret_name)
        with self.assertRaises(secrets_mgr.exceptions.InvalidRequestException):
            secrets_mgr.get_secret_value(SecretId=password_secret_name)

        # ResourceNotFoundException for secrets that don't exist
        with self.assertRaises(secrets_mgr.exceptions.ResourceNotFoundException):
            secrets_mgr.get_secret_value(SecretId=pip_conf.get_ssm_param_name("username"))
        with self.assertRaises(secrets_mgr.exceptions.ResourceNotFoundException):
            secrets_mgr.get_secret_value(SecretId=pip_conf.get_ssm_param_name("url"))


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
        expected_service_details = ServiceDetails(self.test_ssm_config, "PipelineConfigTest", "ABCDE")
        expected_mgmt_account_id = "1357908642"
        expected_dev_account_id = "12334509876"
        expected_ci_account_id = "6789012345"
        expected_prod_account_id = "0987654321"
        expected_github_config = GitHubConfig(self.test_ssm_config, "cdk_utils", "a1b2c3d4e5f6g7h8i9j0")
        expected_pip_config = PipIndexConfig(self.test_ssm_config, "foo@metoffice.gov.uk", "password")
        expected_sonarcloud_token = "fhaoi4oyt5988439798vbr87439bvdi89gf7g67d6fd56f6g76h6"
        expected_pipeline_config = PipelineConfig(
            self.test_ssm_config,
            unique_id=expected_unique_id,
            branch_to_build=expected_branch_to_build,
            build_lambdas=expected_build_lambdas,
            deploy_to_ci=expected_deploy_to_ci,
            deploy_to_prod=expected_deploy_to_prod,
            common=CommonPipelineConfig(
                ssm_config=self.test_ssm_config,
                service=expected_service_details,
                account_ids=AccountIdConfig(
                    self.test_ssm_config,
                    mgmt=expected_mgmt_account_id,
                    dev=expected_dev_account_id,
                    ci=expected_ci_account_id,
                    prod=expected_prod_account_id,
                ),
                github=expected_github_config,
                pip=expected_pip_config,
                sonarcloud_token=expected_sonarcloud_token,
            ),
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
            mgmt_account_id=expected_mgmt_account_id,
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

        actual = PipelineConfig.load(self.test_ssm_config, boto3.Session(region_name="eu-west-2"), mock_cdk_scope)

        self.assertEqual(expected_pipeline_config, actual)
        self.assertEqual(
            f"-c UniqueId={expected_unique_id} -c BranchToBuild={expected_branch_to_build} "
            f"-c SsmNamespace={self.test_ssm_config.namespace} -c SsmConfigId={self.test_ssm_config.config_id} "
            f"-c DeployToCi={expected_deploy_to_ci} -c DeployToProd={expected_deploy_to_prod}",
            actual.pipeline_parameters,
        )

    @mock_ssm
    @mock_secretsmanager
    def test_load_no_cdk_scope(self):
        with self.assertRaises(ConfigException):
            PipelineConfig.load(self.test_ssm_config)

    @mock_ssm
    @mock_secretsmanager
    def test_load_unique_id_missing(self):
        with self.assertRaises(ConfigException):
            PipelineConfig.load(self.test_ssm_config, boto3.Session(), get_mock_cdk_scope())

    def test_init_unique_id_main_must_deploy_main(self):
        """GIVEN unique_id=="main" AND branch_to_build!="main" WHEN init called THEN an exception is raised"""

        with self.assertRaises(ConfigException):
            # noinspection PyTypeChecker
            PipelineConfig(self.test_ssm_config, unique_id="main", branch_to_build="not_main", common=None)

    def test_init_main_branch_can_be_deployed_with_any_unique_id(self):
        """GIVEN unique_id!="main" AND branch_to_build!="main" WHEN init called THEN no exception is raised"""

        # noinspection PyTypeChecker
        PipelineConfig(self.test_ssm_config, unique_id="foo", branch_to_build="main", common=None)
