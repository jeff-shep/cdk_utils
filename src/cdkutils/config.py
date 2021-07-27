from abc import ABC
from typing import Any, Dict, List, Optional, Type, Union

import boto3
from aws_cdk import aws_ssm as ssm
from aws_cdk import core as cdk
from pygit2 import Repository

from cdkutils.persistent_config import PersistedAttribute, PersistedConfig
from cdkutils.errors import ConfigException


class SsmConfig:
    """Represents SSM config details"""

    def __init__(
        self,
        namespace: Optional[str] = None,
        config_id: Optional[str] = None,
        org_name: Optional[str] = None,
        cdk_scope: Optional[cdk.Construct] = None,
    ) -> None:

        if namespace is None and cdk_scope:
            namespace = cdk_scope.node.try_get_context("SsmNamespace")

        if namespace is None:  # i.e. if namespace is *still* None
            raise ValueError("a namespace must be provided, either via a parameter or CDK context variable")
        self.namespace = namespace

        if cdk_scope is not None and config_id is None:
            config_id = cdk_scope.node.try_get_context("SsmConfigId")
        self.config_id = "default" if config_id is None else config_id

        if cdk_scope is not None and org_name is None:
            org_name = cdk_scope.node.try_get_context("SsmConfigOrg")
        self.org_name = "metoffice" if org_name is None else org_name

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, SsmConfig)
            and self.config_id == other.config_id
            and self.org_name == other.org_name
            and self.namespace == other.namespace
        )

    def __repr__(self) -> str:
        return f"SsmConfig({self.namespace!r}, {self.config_id!r}, {self.org_name!r})"

    def __str__(self) -> str:
        return self.path_prefix

    @property
    def path_prefix(self) -> str:
        """Return the path prefix common to all config entries relating to this config"""
        return f"/{self.org_name}/{self.namespace}/{self.config_id}"

    def get_full_path(self, partial_path: str) -> str:
        """
        Return full SSM path for the given partial_path, which is the same as prepending the path_prefix to partial_path
        """
        return f"{self.path_prefix}/{partial_path}"


class ServiceDetails(PersistedConfig):
    """
    Details for complying with the tagging policy:
    https://metoffice.sharepoint.com/sites/CloudTeamCommsSite/SitePages/AWS-Tagging.aspx
    """

    def __init__(
        self, ssm_config: SsmConfig, name: str = "", cost_code: str = "", owner: str = "transporttribe@metoffice.gov.uk"
    ) -> None:
        super().__init__(ssm_config)
        self.name = name
        self.cost_code = cost_code
        self.owner = owner

    @classmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return super()._get_persisted_attributes() + [
            PersistedAttribute("name", "ServiceName", "service/name"),
            PersistedAttribute("cost_code", "ServiceCostCode", "service/cost_code"),
            PersistedAttribute("owner", "ServiceOwner", "service/owner"),
        ]

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        subconfigs = super()._get_subconfigs()
        subconfigs.update({})  # Add subconfigs here
        return subconfigs

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, ServiceDetails)
            and super().__eq__(other)
            and self.owner == other.owner
            and self.name == other.name
            and self.cost_code == other.cost_code
        )

    def apply_tags_to(self, scope: cdk.IConstruct) -> None:
        """Apply Tags using this instance's values"""
        tag_scope = cdk.Tags.of(scope)
        for tag_name, tag_value in [
            ("ServiceName", self.name),
            ("ServiceOwner", self.owner),
            ("ServiceCode", self.cost_code),
        ]:
            if tag_value:
                tag_scope.add(tag_name, tag_value)


class GitHubConfig(PersistedConfig):
    """Encapsulates GitHub related settings"""

    _SSM_BASE_PATH = "pipeline/github/"

    def __init__(self, ssm_config: SsmConfig, repo: str = "", oauth_token: str = "", org: str = "MetOffice") -> None:
        """
        :param repo: The name of the projects git repository
        :param oauth_token: The OAuth token that permits access to the projects git repository for checking out source
                            code and configuring webhooks
        :param org: The name of the organisation that owns the project repository
        """
        super().__init__(ssm_config)
        self.repo = repo
        self.oauth_token = oauth_token
        self.org = org

    def __str__(self) -> str:
        return f"https://github.com/{self.org}/{self.repo}"

    def __repr__(self) -> str:
        token_str = "****" if self.oauth_token and isinstance(self.oauth_token, str) else repr(self.oauth_token)
        return f"GitHubConfig({self.ssm!r}, {self.repo!r}, {token_str}, {self.org!r})"

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, GitHubConfig)
            and super().__eq__(other)
            and self.repo == other.repo
            and self.org == other.org
            and self.oauth_token == other.oauth_token
        )

    @classmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return super()._get_persisted_attributes() + [
            PersistedAttribute(
                "oauth_token", "GitHubToken", cls._SSM_BASE_PATH + "oauth_token", use_secrets_manager=True
            ),
            PersistedAttribute("repo", "GitHubRepo", cls._SSM_BASE_PATH + "repository"),
            PersistedAttribute("org", "GitHubOrg", cls._SSM_BASE_PATH + "organisation"),
        ]

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        return super()._get_subconfigs()


class PipIndexConfig(PersistedConfig):
    """Encapsulates the information required to setup pip to connect to a custom package index"""

    _SSM_BASE_PATH = "pipeline/python-pip/"

    def __init__(
        self,
        ssm_config: SsmConfig,
        username: str = "",
        password: str = "",
        url: str = "https://metoffice.jfrog.io/metoffice/api/pypi/pypi/simple",
    ) -> None:
        super().__init__(ssm_config)
        self.username = username
        self.password = password
        self.url = url

    def __str__(self) -> str:
        creds = self.credentials
        return creds.replace(self.password, "****") if creds and self.password else str(creds)

    def __repr__(self) -> str:
        return f"PipIndexConfig({self.ssm!r}, {self.username!r}, {self.password!r}, {self.url!r})"

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, PipIndexConfig)
            and super().__eq__(other)
            and self.username == other.username
            and self.password == other.password
            and self.url == other.url
        )

    @property
    def credentials(self) -> str:
        if self.url and self.username and self.password:
            creds = f"{self.username}:{self.password}"
            protocol, url_without_protocol = self.url.split("//")
            full_creds = f"{protocol}//{creds}@{url_without_protocol}"
        else:
            full_creds = self.url
        return full_creds

    @classmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return super()._get_persisted_attributes() + [
            PersistedAttribute("username", "PipIndexUsername", cls._SSM_BASE_PATH + "username"),
            PersistedAttribute("url", "PipIndexUrl", cls._SSM_BASE_PATH + "index-url"),
            PersistedAttribute(
                "password", "PipIndexPassword", cls._SSM_BASE_PATH + "password", use_secrets_manager=True
            ),
            PersistedAttribute("credentials", None, cls._SSM_BASE_PATH + "auth", use_secrets_manager=True),
        ]

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        return super()._get_subconfigs()


class BaseConfig(PersistedConfig, ABC):
    @classmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return super()._get_persisted_attributes() + []

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        subconfigs = super()._get_subconfigs()
        subconfigs.update(service=ServiceDetails)
        return subconfigs

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, BaseConfig) and super().__eq__(other) and self.ssm == other.ssm


class AccountIdConfig(PersistedConfig):
    def __init__(
        self,
        ssm_config: SsmConfig,
        *,
        mgmt: str,
        dev: str,
        ci: str,  # pylint:disable=invalid-name
        prod: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(ssm_config, **kwargs)
        self.mgmt = mgmt
        self.dev = dev
        # pylint moans because it's too short, but I can't think of a better one that's longer
        self.ci = ci  # pylint:disable=invalid-name
        self.prod = prod

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, AccountIdConfig)
            and super().__eq__(other)
            and self.mgmt == other.mgmt
            and self.dev == other.dev
            and self.ci == other.ci
            and self.prod == other.prod
        )

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        return super()._get_subconfigs()

    @classmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return super()._get_persisted_attributes() + [
            PersistedAttribute("mgmt", "MgmtAccountId", "pipeline/account_id/mgmt"),
            PersistedAttribute("dev", "DevAccountId", "pipeline/account_id/dev"),
            PersistedAttribute("ci", "CiAccountId", "pipeline/account_id/ci"),
            PersistedAttribute("prod", "ProdAccountId", "pipeline/account_id/prod"),
        ]


class CommonPipelineConfig(BaseConfig):
    """
    Represents config that's shared between multiple pipelines. Designed for inheritance, hence the use of
    kwargs & super.
    Primarily used for creating the shared SSM & SecretManager parameters for a management account, whilst the
    PipelineConfig is used by pipeline instances as it contains pipeline specific information.
    """

    def __init__(
        self,
        ssm_config: SsmConfig,
        *,
        service: ServiceDetails,
        account_ids: AccountIdConfig,
        github: GitHubConfig,
        pip: PipIndexConfig,
        sonarcloud_token: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(ssm_config, **kwargs)
        self.service = service
        self.account_ids = account_ids
        self.github = github
        self.pip = pip
        self.sonarcloud_token = sonarcloud_token

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, CommonPipelineConfig)
            and super().__eq__(other)
            and self.account_ids == other.account_ids
            and self.service == other.service
            and self.github == other.github
            and self.pip == other.pip
            and self.sonarcloud_token == other.sonarcloud_token
        )

    @classmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return super()._get_persisted_attributes() + [
            PersistedAttribute(
                "sonarcloud_token", "SonarCloudToken", "pipeline/sonarcloud/auth", use_secrets_manager=True
            ),
        ]

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        subconfigs = super()._get_subconfigs()
        subconfigs.update(account_ids=AccountIdConfig, github=GitHubConfig, pip=PipIndexConfig, service=ServiceDetails)
        return subconfigs


class PipelineConfig(BaseConfig):
    """Config for a particular pipeline instance, which includes the common config on an attribute called common"""

    def __init__(
        self,
        ssm_config: SsmConfig,
        *,
        unique_id: str = "main",
        branch_to_build: str = "main",
        build_lambdas: bool = True,
        deploy_to_ci: bool = False,
        deploy_to_prod: bool = False,
        common: CommonPipelineConfig,
        **kwargs: Any,
    ):
        super().__init__(ssm_config, **kwargs)

        self.common = common
        self.unique_id = unique_id
        self.branch_to_build = branch_to_build if branch_to_build else Repository(".").head.shorthand
        self.deploy_to_ci = deploy_to_ci
        self.deploy_to_prod = deploy_to_prod
        self.build_lambdas = build_lambdas

        if self.unique_id == "main" and self.branch_to_build != "main":
            raise ConfigException("Pipeline with unique_id main must deploy the main branch")

    @classmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        subconfigs = super()._get_subconfigs()
        subconfigs.update(common=CommonPipelineConfig)
        return subconfigs

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, PipelineConfig)
            and super().__eq__(other)
            and self.common == other.common
            and self.unique_id == other.unique_id
            and self.branch_to_build == other.branch_to_build
            and self.deploy_to_ci == other.deploy_to_ci
            and self.deploy_to_prod == other.deploy_to_prod
            and self.build_lambdas == other.build_lambdas
        )

    @classmethod
    def load(
        cls,
        ssm_config: SsmConfig,
        boto_session: Optional[boto3.Session] = None,
        cdk_scope: Optional[cdk.Construct] = None,
    ) -> "PipelineConfig":

        if not cdk_scope:
            raise ConfigException("cdk_scope must be provided so UniqueId cdk context variables can be read")

        unique_id = cdk_scope.node.try_get_context("UniqueId")
        if not unique_id:
            raise ConfigException("UniqueId must be specified")

        kwargs = {
            "unique_id": unique_id,
            "branch_to_build": cdk_scope.node.try_get_context("BranchToBuild"),
            "deploy_to_ci": bool(cdk_scope.node.try_get_context("DeployToCi")),
            "deploy_to_prod": bool(cdk_scope.node.try_get_context("DeployToProd")),
            "build_lambdas": not cdk_scope.node.try_get_context("Local"),
        }
        kwargs.update(super()._get_init_args(ssm_config, boto_session, cdk_scope))
        # pylint is not so good at introspecting our _get_init_args dict
        return cls(ssm_config, **kwargs)  # pylint: disable=missing-kwoa

    @property
    def pipeline_parameters(self) -> str:
        return " -c ".join(
            [
                "",  # Ensures the string starts with -c
                f"UniqueId={self.unique_id}",
                f"BranchToBuild={self.branch_to_build}",
                f"SsmNamespace={self.ssm.namespace}",
                f"SsmConfigId={self.ssm.config_id}",
                f"DeployToCi={self.deploy_to_ci}",
                f"DeployToProd={self.deploy_to_prod}",
            ]
        ).strip()
