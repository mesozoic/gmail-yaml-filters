"""
Fixtures for integration tests against the live Gmail API.
"""
from pathlib import Path

import pytest

from gmail_yaml_filters.upload import get_gmail_credentials
from gmail_yaml_filters.upload import get_gmail_service


@pytest.fixture
def gmail():
    """
    Returns a Gmail service instance using integration test credentials.
    """
    here = Path(__file__).parent
    client_secret = here / 'itest_client_secret.json'
    credential_store = here / 'itest_credentials.json'

    if not client_secret.exists():
        pytest.skip(f'missing {client_secret.name}')

    credentials = get_gmail_credentials(client_secret_path=client_secret, credential_store=credential_store)
    return get_gmail_service(credentials)
