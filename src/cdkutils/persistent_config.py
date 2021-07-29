import contextlib
import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar, Union, final

import boto3
from aws_cdk import aws_ssm as ssm
from aws_cdk import core as cdk

from cdkutils.errors import AttributeNotFoundException, SecretCreationException

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
        """
        Create the secret if it doesn't exist.
        If the secret does exist, and the new value differs from the current,
        update the existing secret.
        """
        ssm_config = ssm_config_override if ssm_config_override else self.ssm
        sm_client: SecretsManagerClient = boto_session.client("secretsmanager")

        for mapping in self._get_persisted_attributes():
            if mapping.use_secrets_manager:
                secret_string = getattr(self, mapping.attribute)
                if secret_string:
                    response = None
                    name = ssm_config.get_full_path(mapping.aws_partial_path)

                    # Determine if the secret exists, if it does, return it's value
                    try:
                        response = sm_client.get_secret_value(SecretId=name)["SecretString"]

                    # Secret doesn't exist and so we create a new one
                    except sm_client.exceptions.ResourceNotFoundException:
                        sm_client.create_secret(Name=name, SecretString=secret_string)
                        _LOGGER.info(f"Created {name} in Secret Manager")

                    if response is not None:
                        # Secret exists, check if the value needs to be updated
                        if response != secret_string:
                            self.update_existing_secret(name, secret_string, sm_client)

        for subconfig in self._get_subconfigs():
            getattr(self, subconfig).create_secrets(boto_session)

    @final
    @staticmethod
    def update_existing_secret(name: str, secret_string: str, sm_client: SecretsManagerClient) -> None:

        try:
            sm_client.update_secret(SecretId=name, SecretString=secret_string)
            _LOGGER.info(f"Updated {name} in Secret Manager")

        except (
            sm_client.exceptions.InvalidRequestException,
            sm_client.exceptions.InvalidParameterException,
            sm_client.exceptions.LimitExceededException,
        ) as exc:
            msg = f"Error creating {name}: {exc}"
            _LOGGER.error(msg)
            raise SecretCreationException(msg) from exc

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
                    name = ssm_config.get_full_path(mapping.aws_partial_path)
                    sm_client.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=no_recovery)
                    _LOGGER.info(f"Deleted {name}")

        for subconfig in self._get_subconfigs():
            getattr(self, subconfig).delete_secrets(boto_session)
