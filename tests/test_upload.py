# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import googleapiclient.errors
import pytest
from mock import MagicMock

from gmail_yaml_filters.ruleset import RuleSet
from gmail_yaml_filters.upload import (
    GmailFilters,
    GmailLabels,
    fake_label,
    prune_labels_not_in_ruleset,
    upload_ruleset,
)


def fake_gmail_filter(name):
    return {
        "id": "fake_gmail_filter_{}".format(name),
        "criteria": {
            "from": "{}@example.com".format(name),
        },
        "action": {
            "addLabelIds": ["fake_label"],
        },
    }


@pytest.fixture
def fake_gmail():
    fake_gmail = MagicMock()

    def fake_create_label(**kwargs):
        create = MagicMock()
        create.execute.return_value = fake_label(kwargs["body"]["name"])
        return create

    fake_gmail.fake_labels = [fake_label(x) for x in ["one", "two", "three"]]
    fake_gmail.users().labels().create = fake_create_label
    fake_gmail.users().labels().list().execute.return_value = {
        "labels": fake_gmail.fake_labels,
    }

    fake_gmail.fake_filters = [fake_gmail_filter(x) for x in ["one", "two"]]
    fake_gmail.users().settings().filters().list().execute.return_value = {
        "filter": fake_gmail.fake_filters,
    }

    return fake_gmail


def test_fake_labels(fake_gmail):
    labels = GmailLabels(fake_gmail, dry_run=True)
    assert labels["one"]["name"] == "one"
    with pytest.raises(KeyError):
        labels["whatever"]
    assert labels.get_or_create("whatever")["name"] == "whatever"
    assert labels.get_or_create("🚀")["name"] == "🚀"


def test_filters(fake_gmail):
    GmailFilters(fake_gmail)


def test_remote_filters_without_action(fake_gmail):
    # see https://github.com/mesozoic/gmail-yaml-filters/issues/5
    for fake_filter in fake_gmail.fake_filters:
        del fake_filter["action"]
    GmailFilters(fake_gmail)


def test_upload_excludes_non_publishable(fake_gmail):
    ruleset = RuleSet.from_object(
        [
            {"from": "alice", "archive": True},
            {"from": "bob"},  # test that rules with no actions are ignored
            {"archive": True},  # test that rules with no conditions are ignored
        ]
    )
    upload_ruleset(ruleset, fake_gmail)
    assert fake_gmail.users().settings().filters().create.call_count == 1
    assert fake_gmail.users().settings().filters().create.call_args_list[0][1] == {
        "userId": "me",
        "body": {
            "criteria": {"from": "alice"},
            "action": {"removeLabelIds": ["FakeLabel_INBOX"]},
        },
    }


def test_upload_forward(fake_gmail):
    ruleset = RuleSet.from_object([{"from": "alice", "forward": "bob"}])
    upload_ruleset(ruleset, fake_gmail)
    assert fake_gmail.users().settings().filters().create.call_count == 1
    assert fake_gmail.users().settings().filters().create.call_args_list[0][1] == {
        "userId": "me",
        "body": {
            "criteria": {"from": "alice"},
            "action": {"forward": "bob"},
        },
    }


def test_prune_labels_not_in_ruleset(fake_gmail):
    ruleset = RuleSet.from_object([{"from": "alice", "label": "one"}])
    prune_labels_not_in_ruleset(ruleset, fake_gmail)
    deleted_label_ids = {
        call_arg[1]["id"]
        for call_arg in fake_gmail.users().labels().delete.call_args_list
    }
    assert fake_gmail.users().labels().delete.call_count == 2
    assert deleted_label_ids == {"FakeLabel_two", "FakeLabel_three"}


def test_prune_labels_not_in_ruleset_raises_http_error(fake_gmail):
    ruleset = RuleSet.from_object([{"from": "alice", "label": "one"}])

    def raises_error(*args, **kwargs):
        raise googleapiclient.errors.HttpError(MagicMock(), b"")

    fake_gmail.users().labels().delete().execute.side_effect = raises_error

    with pytest.raises(googleapiclient.errors.HttpError):
        prune_labels_not_in_ruleset(ruleset, fake_gmail)

    assert fake_gmail.users().labels().delete().execute.call_count == 1


def test_prune_labels_not_in_ruleset_continue_on_http_error(fake_gmail):
    ruleset = RuleSet.from_object([{"from": "alice", "label": "one"}])

    def raises_error(*args, **kwargs):
        raise googleapiclient.errors.HttpError(MagicMock(), b"")

    fake_gmail.users().labels().delete().execute.side_effect = raises_error

    prune_labels_not_in_ruleset(ruleset, fake_gmail, continue_on_http_error=True)
    assert fake_gmail.users().labels().delete().execute.call_count == 2
