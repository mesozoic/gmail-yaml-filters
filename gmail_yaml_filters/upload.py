#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

from collections import defaultdict
import argparse
import os
import sys

# google-api-python-client dependencies
import apiclient.discovery
import httplib2
import oauth2client.client
import oauth2client.file
import oauth2client.tools


"""
Pushes auto-generated mail filters to the Gmail API.
"""


CONDITION_KEY_MAP = {
    'from': 'from',
    'to': 'to',
    'subject': 'subject',
    'hasTheWord': 'query',
    'doesNotHaveTheWord': 'negatedQuery',
}


def _rule_conditions_to_dict(rule):
    return {
        CONDITION_KEY_MAP[condition.key]: condition.value
        for condition in rule.flatten().values()
        if condition.key in CONDITION_KEY_MAP
    }


ACTION_KEY_MAP = {
    'label': None,
    'shouldAlwaysMarkAsImportant': ('add', ['IMPORTANT']),
    'shouldArchive': ('remove', ['INBOX']),
    'shouldMarkAsRead': ('remove', ['UNREAD']),
    'shouldNeverMarkAsImportant': ('remove', ['IMPORTANT']),
    'shouldNeverSpam': ('remove', ['SPAM']),
    'shouldStar': ('add', ['STARRED']),
    'shouldTrash': ('add', ['TRASH']),
}


def _rule_actions_to_dict(rule):
    result = defaultdict(set)

    for action in rule.flatten().values():
        # This is how we know whether we have actions or conditions. Could be smarter.
        if action.key not in ACTION_KEY_MAP:
            continue
        if action.key == 'label':
            result['addLabelIds'].add(action.value)
        else:
            label_action, label_values = ACTION_KEY_MAP[action.key]
            result['{}LabelIds'.format(label_action)].update(label_values)

    return result


class GmailLabels(object):
    """
    Wrapper around the Gmail Users.labels API that munges label names to try to make them match.

    See https://developers.google.com/gmail/api/v1/reference/users/labels
    """
    def __init__(self, gmail):
        self.gmail = gmail
        self.reload()

    def reload(self):
        self.labels = self.gmail.users().labels().list(userId='me').execute()['labels']
        self.by_lower_name = {label['name'].lower(): label for label in self.labels}

    def __iter__(self):
        return iter(self.labels)

    def __getitem__(self, name):
        for possible_name in self._possible_names(name):
            if possible_name in self.by_lower_name:
                return self.by_lower_name[possible_name]
        raise KeyError(name)

    def _possible_names(self, name):
        name = name.lower()
        return (
            name,
            name.replace(' ', '-'),
            name.replace('-', ' '),
            name.replace('-', '/'),
        )

    def get_or_create(self, name):
        try:
            return self[name]
        except KeyError:
            print('Creating label', name.encode('utf-8'), file=sys.stderr)
            request = self.gmail.users().labels().create(userId='me', body={'name': name})
            created = request.execute()
            self.labels.append(created)
            self.by_lower_name[created['name'].lower()] = created
            return self[name]


def _simplify_filter(filter_dict):
    return {
        'criteria': filter_dict['criteria'],
        'action': {key: set(values) for key, values in filter_dict['action'].items()},
    }


class GmailFilters(object):
    def __init__(self, gmail):
        self.gmail = gmail
        self.reload()

    def reload(self):
        self.filters = self.gmail.users().settings().filters().list(userId='me').execute()['filter']
        self.matchable_filters = [
            _simplify_filter(existing_filter)
            for existing_filter
            in self.gmail.users().settings().filters().list(userId='me').execute()['filter']
        ]

    def __iter__(self):
        return iter(self.filters)

    def exists(self, other):
        return _simplify_filter(other) in iter(_simplify_filter(f) for f in self.filters)

    def prunable(self, filter_dicts):
        matchable = [_simplify_filter(filter_dict) for filter_dict in filter_dicts]
        return [prunable for prunable in self.filters if _simplify_filter(prunable) not in matchable]


def rule_to_resource(rule, labels, create_missing=False):
    return {
        'criteria': _rule_conditions_to_dict(rule),
        'action': {
            key: set(
                (labels.get_or_create(value) if create_missing else labels[value])['id']
                for value in values
            )
            for key, values
            in _rule_actions_to_dict(rule).items()
        }
    }


def upload_ruleset(ruleset, service=None):
    service = service or get_gmail_service()
    known_labels = GmailLabels(service)
    known_filters = GmailFilters(service)

    for rule in ruleset:
        if not rule.actions:
            continue

        # See https://developers.google.com/gmail/api/v1/reference/users/settings/filters#resource
        filter_data = rule_to_resource(rule, known_labels, create_missing=True)

        if not known_filters.exists(filter_data):
            print('Creating', filter_data['criteria'], filter_data['action'], file=sys.stderr)
            # Strip out defaultdict and set; they won't be JSON-serializable
            filter_data['action'] = {key: list(values) for key, values in filter_data['action'].items()}
            request = service.users().settings().filters().create(userId='me', body=filter_data)
            request.execute()


def prune_filters_not_in_ruleset(ruleset, service=None):
    service = service or get_gmail_service()
    known_labels = GmailLabels(service)
    known_filters = GmailFilters(service)
    ruleset_filters = [rule_to_resource(rule, known_labels) for rule in ruleset]

    for prunable_filter in known_filters.prunable(ruleset_filters):
        print('Deleting', prunable_filter['id'], prunable_filter['criteria'], prunable_filter['action'], file=sys.stderr)
        request = service.users().settings().filters().delete(userId='me', id=prunable_filter['id'])
        request.execute()


def get_gmail_service():
    credentials = get_gmail_credentials()
    http = credentials.authorize(httplib2.Http())
    return apiclient.discovery.build('gmail', 'v1', http=http)


def get_gmail_credentials(
    scopes=[
        'https://www.googleapis.com/auth/gmail.settings.basic',
        'https://www.googleapis.com/auth/gmail.labels',
    ],
    client_secret_file='client_secret.json',
    application_name='gmail_yaml_filters',
):
    credential_dir = os.path.join(os.path.expanduser('~'), '.credentials')
    credential_path = os.path.join(credential_dir, application_name + '.json')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = oauth2client.client.flow_from_clientsecrets(client_secret_file, scopes)
        flow.user_agent = application_name
        flags_parser = argparse.ArgumentParser(parents=[oauth2client.tools.argparser])
        credentials = oauth2client.tools.run_flow(flow, store, flags=flags_parser.parse_args([]))
        print('Storing credentials to', credential_path, file=sys.stderr)

    return credentials
