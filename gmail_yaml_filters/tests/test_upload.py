# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from gmail_yaml_filters.upload import GmailFilters
from gmail_yaml_filters.upload import GmailLabels
from gmail_yaml_filters.upload import fake_label
from mock import MagicMock
import pytest


def fake_gmail_filter(name):
    return {
        'id': 'fake_gmail_filter_{}'.format(name),
        'criteria': {
            'from': '{}@example.com'.format(name),
        },
        'action': {
            'addLabelIds': ['fake_label'],
        },
    }


@pytest.fixture
def fake_gmail():
    fake_gmail = MagicMock()

    fake_gmail.fake_labels = [fake_label(x) for x in ['one', 'two', 'three']]
    fake_gmail.users().labels().list().execute.return_value = {
        'labels': fake_gmail.fake_labels,
    }

    fake_gmail.fake_filters = [fake_gmail_filter(x) for x in ['one', 'two']]
    fake_gmail.users().settings().filters().list().execute.return_value = {
        'filter': fake_gmail.fake_filters,
    }

    return fake_gmail


def test_fake_labels(fake_gmail):
    labels = GmailLabels(fake_gmail, dry_run=True)
    assert labels['one']['name'] == 'one'
    with pytest.raises(KeyError):
        labels['whatever']
    assert labels.get_or_create('whatever')['name'] == 'whatever'
    assert labels.get_or_create('🚀')['name'] == '🚀'


def test_filters(fake_gmail):
    GmailFilters(fake_gmail)


def test_filters_without_action(fake_gmail):
    # see https://github.com/mesozoic/gmail-yaml-filters/issues/5
    for fake_filter in fake_gmail.fake_filters:
        del fake_filter['action']
    GmailFilters(fake_gmail)
