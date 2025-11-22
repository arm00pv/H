import json
from .mock_provider import MockProvider
from .webdav import WebDAVProvider

class ProviderManager:
    @staticmethod
    def get_provider(provider_type: str, config_json: str):
        try:
            config = json.loads(config_json)
        except json.JSONDecodeError:
            config = {}

        if provider_type == 'mock':
            return MockProvider(config)
        elif provider_type == 'nextcloud' or provider_type == 'owncloud':
            return WebDAVProvider(config)
        # Add others here...
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
