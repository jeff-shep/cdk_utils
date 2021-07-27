"""Contains all custom exception handlers relating to the config classes"""

class ConfigException(Exception):
    pass


class AttributeNotFoundException(ConfigException):
    pass


class SecretCreationException(ConfigException):
    pass
