# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from gmail_yaml_filters.ruleset import RuleSet
from gmail_yaml_filters.upload import GmailFilters
from gmail_yaml_filters.upload import GmailLabels
from gmail_yaml_filters.upload import fake_label
from gmail_yaml_filters.upload import upload_ruleset
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

    def fake_create_label(**kwargs):
        create = MagicMock()
        create.execute.return_value = fake_label(kwargs['body']['name'])
        return create

    fake_gmail.fake_labels = [fake_label(x) for x in ['one', 'two', 'three']]
    fake_gmail.users().labels().create = fake_create_label
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


def test_remote_filters_without_action(fake_gmail):
    # see https://github.com/mesozoic/gmail-yaml-filters/issues/5
    for fake_filter in fake_gmail.fake_filters:
        del fake_filter['action']
    GmailFilters(fake_gmail)


def test_upload_excludes_non_publishable(fake_gmail):
    ruleset = RuleSet.from_object([
        {'from': 'alice', 'archive': True},
        {'from': 'bob'},  # test that rules with no actions are ignored
        {'archive': True},  # test that rules with no conditions are ignored
    ])
    upload_ruleset(ruleset, fake_gmail)
    assert fake_gmail.users().settings().filters().create.call_count == 1
    assert fake_gmail.users().settings().filters().create.call_args_list[0][1] == {
        'userId': 'me',
        'body': {
            'criteria': {'from': 'alice'},
            'action': {'removeLabelIds': ['FakeLabel_INBOX']},
        },
    }


def test_upload_forward(fake_gmail):
    ruleset = RuleSet.from_object([{'from': 'alice', 'forward': 'bob'}])
    upload_ruleset(ruleset, fake_gmail)
    assert fake_gmail.users().settings().filters().create.call_count == 1
    assert fake_gmail.users().settings().filters().create.call_args_list[0][1] == {
        'userId': 'me',
        'body': {
            'criteria': {'from': 'alice'},
            'action': {'forward': 'bob'},
        },
    }
