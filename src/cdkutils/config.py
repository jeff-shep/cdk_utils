"""Classes for persisting and accessing pipeline config"""
import contextlib
import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar, Union, final

import boto3
from aws_cdk import aws_ssm as ssm
from aws_cdk import core as cdk
from pygit2 import Repository

if TYPE_CHECKING:
    from mypy_boto3_secretsmanager.client import SecretsManagerClient
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object
    SecretsManagerClient = object


_LOGGER = logging.getLogger(__name__)


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


@dataclass
class PersistedAttribute:
    """Stores the CDK context variable and SSM parameter names linked to the attribute"""

    attribute: str
    cdk_context_param: Optional[str]
    aws_partial_path: str
    use_secrets_manager: bool = False  # If false, the attribute is stored in a SSM Parameter

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, PersistedAttribute)
            and self.attribute == other.attribute
            and self.cdk_context_param == other.cdk_context_param
            and self.aws_partial_path == other.aws_partial_path
            and self.use_secrets_manager == other.use_secrets_manager
        )


class ConfigException(Exception):
    pass


class AttributeNotFoundException(ConfigException):
    pass


T = TypeVar("T", bound="PersistedConfig")  # pylint:disable=invalid-name


class PersistedConfig(ABC):
    """
    Mixin class that provides common functionality for loading config from context variables, SSM parameters, or
    SecretsManager Secrets
    """

    @classmethod
    @abstractmethod
    def _get_persisted_attributes(cls) -> List[PersistedAttribute]:
        return []

    @classmethod
    @abstractmethod
    def _get_subconfigs(cls) -> Dict[str, Type["PersistedConfig"]]:
        return {}

    def __init__(self, ssm_config: SsmConfig, *_args: Any, **_kwargs: Any) -> None:
        self.ssm = ssm_config

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, PersistedConfig) and self.ssm == other.ssm

    @classmethod
    @final
    def _get_init_args_from_context_vars(
        cls, cdk_scope: cdk.Construct, persisted_attrs: List[PersistedAttribute]
    ) -> Dict[str, str]:
        """
        Given a CDK Construct that is within the scope of a CDK app and a list of `PersistedAttribute`s, then return any
        values for those attributes found in the CDK's context variables.
        `PersistedAttribute`s with no `cdk_context_param` value are ignored, and missing values are omitted from the
        resulting Dict
        """

        res: Dict[str, str] = {}

        for persisted_attr in persisted_attrs:
            if persisted_attr.cdk_context_param:
                val = cdk_scope.node.try_get_context(persisted_attr.cdk_context_param)
                if val:
                    res[persisted_attr.attribute] = val

        return res

    @classmethod
    @final
    def _get_init_args_from_aws(
        cls,
        ssm_config: SsmConfig,
        boto_session: boto3.Session,
        persisted_attrs: List[PersistedAttribute],
    ) -> Dict[str, str]:
        """
        Given a list of PersistedAttributes, return a dict of `PersistedAttribute.attribute` mapped to its valued.
        `PersistedAttribute.use_secrets_manager` controls whether a SSM Parameter or Secrets Manager Secret is checked.
        `ssm_config` is used to compute the full name of the SSM/Secret to lookup.
        If a SSM/Secret with that name doesn't exist, an exception will be thrown.
        `PersistedAttribute`s that don't have an `aws_partial_path` value are ignored.
        """
        # This is a local method, for local developers!
        # pylint:disable=too-many-locals
        # Suggestions welcome

        res: Dict[str, str] = {}
        ssm_client: SSMClient = boto_session.client("ssm")
        secret_mgr_client: SecretsManagerClient = boto_session.client("secretsmanager")

        for persisted_attr in persisted_attrs:
            try:
                is_attribute = not isinstance(getattr(cls, persisted_attr.attribute), property)
                # Do not read values from AWS for properties, only true attributes. Properties are methods that can be
                # accessed as if they were attributes. We use them here for values derived from other attributes, thus
                # they aren't passed into the class' __init__ method, so we skip them here.
            except AttributeError:
                # Maybe counter-intuitive, but if the class doesn't have an attribute with the desired name, that
                # implies it's an instance attribute that's declared and set by the __init__ method, and hence is not a
                # property.
                is_attribute = True

            if is_attribute and persisted_attr.aws_partial_path:
                full_path = ssm_config.get_full_path(persisted_attr.aws_partial_path)
                try:
                    if persisted_attr.use_secrets_manager:
                        val = secret_mgr_client.get_secret_value(SecretId=full_path)["SecretString"]
                    else:
                        val = ssm_client.get_parameter(Name=full_path)["Parameter"]["Value"]
                except (
                    ssm_client.exceptions.ParameterNotFound,
                    secret_mgr_client.exceptions.ResourceNotFoundException,
                ) as exc:
                    default_value = inspect.signature(cls.__init__).parameters[persisted_attr.attribute].default
                    if default_value and default_value != inspect.Parameter.empty:
                        val = default_value
                    else:
                        param_type = "Secret Manager Secret" if persisted_attr.use_secrets_manager else "SSM parameter"
                        msg = f"Unable to load {param_type} {full_path}. It does not exist"
                        _LOGGER.info(msg)
                        raise AttributeNotFoundException(msg) from exc

                res[persisted_attr.attribute] = val

        return res

    @classmethod
    @final
    def _get_init_args(
        cls,
        ssm_config: SsmConfig,
        boto_session: Optional[boto3.Session] = None,
        cdk_scope: Optional[cdk.Construct] = None,
    ) -> Dict[str, Union["PersistedConfig", str]]:
        kwargs: Dict[str, Union["PersistedConfig", str]] = {}

        persisted_attrs = cls._get_persisted_attributes()

        if cdk_scope:
            kwargs.update(cls._get_init_args_from_context_vars(cdk_scope, persisted_attrs))

        if ssm_config and boto_session:
            attrs_to_get_from_aws = [a for a in persisted_attrs if a.attribute not in kwargs]
            kwargs.update(cls._get_init_args_from_aws(ssm_config, boto_session, attrs_to_get_from_aws))

        # Deal with nested configs
        for attribute_name, subconfig_class in cls._get_subconfigs().items():
            kwargs[attribute_name] = subconfig_class.load(ssm_config, boto_session, cdk_scope)

        return kwargs

    @classmethod
    def load(
        cls: Type[T],
        ssm_config: SsmConfig,
        boto_session: Optional[boto3.Session] = None,
        cdk_scope: Optional[cdk.Construct] = None,
    ) -> T:
        kwargs = cls._get_init_args(ssm_config, boto_session, cdk_scope)
        return cls(ssm_config, **kwargs)

    @classmethod
    @final
    def get_persisted_attribute(cls, attribute_name: str) -> PersistedAttribute:
        try:
            return next(a for a in cls._get_persisted_attributes() if a.attribute == attribute_name)
        except StopIteration as exc:
            raise KeyError(f"Didn't find a persisted attribute named {attribute_name!r}") from exc

    @final
    def get_ssm_param_name(self, attribute_name: str, ssm_config_override: Optional[SsmConfig] = None) -> str:

        ssm_config = ssm_config_override if ssm_config_override else self.ssm
        param = self.get_persisted_attribute(attribute_name)
        if param.use_secrets_manager:
            raise KeyError(f"Attribute {attribute_name} is not stored in SSM")
        return ssm_config.get_full_path(param.aws_partial_path)

    @final
    def get_secret_name(self, attribute_name: str, ssm_config_override: Optional[SsmConfig] = None) -> str:

        ssm_config = ssm_config_override if ssm_config_override else self.ssm
        param = self.get_persisted_attribute(attribute_name)
        if not param.use_secrets_manager:
            raise KeyError(f"Attribute {attribute_name} is not stored in Secrets Manager")
        return ssm_config.get_full_path(param.aws_partial_path)

    @final
    def get_cdk_secret_value(self, attribute_name: str) -> cdk.SecretValue:
        persisted_attr = self.get_persisted_attribute(attribute_name)
        if persisted_attr.use_secrets_manager:
            return cdk.SecretValue(value=getattr(self, attribute_name))

        raise KeyError(f"Attribute {attribute_name} is not stored in Secrets Manager")

    def to_cdk(self, scope: cdk.Stack, ssm_config_override: Optional[SsmConfig] = None) -> None:

        ssm_config = ssm_config_override if ssm_config_override else self.ssm

        for mapping in self._get_persisted_attributes():
            if mapping.use_secrets_manager:
                _LOGGER.info(
                    f"Not creating SecretsManager Secret for {mapping.attribute} because the value would be "
                    f"stored in plaintext in the resulting template. Call create_secrets instead."
                )
            else:
                val = getattr(self, mapping.attribute)
                if not val:
                    _LOGGER.info(f"Skipping {type(self).__name__}.{mapping.attribute} because no value is set")
                    continue
                full_path = ssm_config.get_full_path(mapping.aws_partial_path)
                ssm.StringParameter(scope, f"{mapping.attribute}-ssm", parameter_name=full_path, string_value=val)

        # Deal with nested configs
        for attribute_name in self._get_subconfigs():
            getattr(self, attribute_name).to_cdk(scope, ssm_config)

    @final
    def create_secrets(self, boto_session: boto3.Session, ssm_config_override: Optional[SsmConfig] = None) -> None:

        ssm_config = ssm_config_override if ssm_config_override else self.ssm
        sm_client: SecretsManagerClient = boto_session.client("secretsmanager")

        for mapping in self._get_persisted_attributes():
            if mapping.use_secrets_manager:
                secret_string = getattr(self, mapping.attribute)
                if secret_string:
                    name = ssm_config.get_full_path(mapping.aws_partial_path)
                    sm_client.create_secret(Name=name, SecretString=secret_string)
                    _LOGGER.info(f"Created {name} in Secret Manager")

        for subconfig in self._get_subconfigs():
            getattr(self, subconfig).create_secrets(boto_session)

    @final
    def delete_secrets(
        self, boto_session: boto3.Session, ssm_config_override: Optional[SsmConfig] = None, no_recovery: bool = False
    ) -> None:

        ssm_config = ssm_config_override if ssm_config_override else self.ssm
        sm_client: SecretsManagerClient = boto_session.client("secretsmanager")

        for mapping in self._get_persisted_attributes():
            if mapping.use_secrets_manager:
                with contextlib.suppress(
                    sm_client.exceptions.ResourceNotFoundException, sm_client.exceptions.InvalidRequestException
                ):
                    sm_client.delete_secret(
                        SecretId=ssm_config.get_full_path(mapping.aws_partial_path),
                        ForceDeleteWithoutRecovery=no_recovery,
                    )

        for subconfig in self._get_subconfigs():
            getattr(self, subconfig).delete_secrets(boto_session)


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

    def apply_tags_to(self, scope: cdk.Construct) -> None:
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
                f"BranchToBuild={self.branch_to_build}",
                f"SSMNamespace={self.ssm.namespace}",
                f"PipelineSSMConfigId={self.ssm.config_id}",
                f"SystemSSMConfigId={self.ssm.config_id}",
                f"DeployToCi={self.deploy_to_ci}",
                f"DeployToProd={self.deploy_to_prod}",
            ]
        ).strip()
