"""Configuration encryption and sensitivity detection"""

# Sensitive configuration keys that should be encrypted (keyword-based matching)
SENSITIVE_KEYS: set[str] = {
    "api_key",
    "api_token",
    "secret",
    "password",
    "private_key",
    "access_token",
    "refresh_token",
    "webhook_secret",
    "encryption_key",
}

# Config keys that contain credentials but don't match keyword patterns
SENSITIVE_CONFIG_KEY_EXACT: set[str] = {
    "browserCloudProvider",
    "browserProxy",
    "captchaSolverConfig",
}


def is_sensitive_config(key: str) -> bool:
    """
    判断配置key是否敏感

    Args:
        key: 配置key

    Returns:
        bool: True表示敏感配置，需要加密
    """
    if key in SENSITIVE_CONFIG_KEY_EXACT:
        return True
    key_lower = key.lower()
    return any(sensitive_word in key_lower for sensitive_word in SENSITIVE_KEYS)
