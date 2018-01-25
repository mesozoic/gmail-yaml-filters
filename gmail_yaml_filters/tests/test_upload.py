# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from gmail_yaml_filters.upload import GmailLabels
from gmail_yaml_filters.upload import fake_label
from mock import MagicMock
import pytest


@pytest.fixture
def fake_gmail():
    fake_gmail = MagicMock()
    fake_gmail.users().labels().list().execute.return_value = {
        'labels': [fake_label(x) for x in ['one', 'two', 'three']]
    }
    return fake_gmail


def test_fake_labels(fake_gmail):
    labels = GmailLabels(fake_gmail, dry_run=True)
    assert labels['one']['name'] == 'one'
    with pytest.raises(KeyError):
        labels['whatever']
    assert labels.get_or_create('whatever')['name'] == 'whatever'
    assert labels.get_or_create('🚀')['name'] == '🚀'
