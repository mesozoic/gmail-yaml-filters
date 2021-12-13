#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

from collections import defaultdict
from operator import itemgetter
import argparse
import os
import sys
import time

# google-api-python-client dependencies
import apiclient.discovery
import googleapiclient.errors
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
    'shouldAlwaysMarkAsImportant': ('add', ['IMPORTANT']),
    'shouldArchive': ('remove', ['INBOX']),
    'shouldMarkAsRead': ('remove', ['UNREAD']),
    'shouldNeverMarkAsImportant': ('remove', ['IMPORTANT']),
    'shouldNeverSpam': ('remove', ['SPAM']),
    'shouldStar': ('add', ['STARRED']),
    'shouldTrash': ('add', ['TRASH']),
}


def _rule_to_actions(rule):
    result = defaultdict(set)

    for action in rule.flatten().values():
        if action.key == 'label':
            result['addLabelIds'].add(action.value)
        elif action.key == 'forwardTo':
            result['forward'] = action.value
        elif action.key in ACTION_KEY_MAP:
            label_action, label_values = ACTION_KEY_MAP[action.key]
            result['{}LabelIds'.format(label_action)].update(label_values)
        else:
            # This means it's a condition, not an action.
            pass

    return result


def fake_label(name):
    return {
        "id": u'FakeLabel_{}'.format(name.replace(' ', '-')),
        "name": name,
        "messageListVisibility": 'labelHide',
        "labelListVisibility": 'hide',
        "type": 'user',
        "messagesTotal": 0,
        "messagesUnread": 0,
        "threadsTotal": 0,
        "threadsUnread": 0,
    }


class GmailLabels(object):
    """
    Wrapper around the Gmail Users.labels API that munges label names to try to make them match.

    See https://developers.google.com/gmail/api/v1/reference/users/labels
    """
    def __init__(self, gmail, dry_run=False):
        self.gmail = gmail
        self.dry_run = dry_run
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

    def __setitem__(self, name, value):
        self.labels.append(value)
        self.by_lower_name[value['name'].lower()] = value

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
            print('Creating label', name, file=sys.stderr)
            if self.dry_run:
                self[name] = fake_label(name)
                return self[name]
            request = self.gmail.users().labels().create(userId='me', body={'name': name})
            created = request.execute()
            self[name] = created
            return self[name]


def _simplify_filter(filter_dict):
    return {
        'criteria': filter_dict['criteria'],
        'action': {
            key: set(values)
            for key, values
            in filter_dict.get('action', {}).items()
        },
    }


class GmailFilters(object):
    def __init__(self, gmail):
        self.gmail = gmail
        self.reload()

    def reload(self):
        self.filters = self.gmail.users().settings().filters().list(userId='me').execute().get('filter', [])
        self.matchable_filters = [_simplify_filter(existing) for existing in self.filters]

    def __iter__(self):
        return iter(self.filters)

    def exists(self, other):
        return _simplify_filter(other) in iter(_simplify_filter(f) for f in self.filters)

    def prunable(self, filter_dicts):
        matchable = [_simplify_filter(filter_dict) for filter_dict in filter_dicts]
        return [prunable for prunable in self.filters if _simplify_filter(prunable) not in matchable]


def rule_to_resource(rule, labels):
    actions = _rule_to_actions(rule)

    for key in ('addLabelIds', 'removeLabelIds'):
        if key in actions:
            actions[key] = list(set(labels.get_or_create(label)['id'] for label in actions[key]))

    return {
        'criteria': _rule_conditions_to_dict(rule),
        'action': actions,
    }


def upload_ruleset(ruleset, service=None, dry_run=False):
    service = service or get_gmail_service()
    known_labels = GmailLabels(service, dry_run=dry_run)
    known_filters = GmailFilters(service)

    for rule in ruleset:
        if not rule.publishable:
            continue

        # See https://developers.google.com/gmail/api/v1/reference/users/settings/filters#resource
        filter_data = rule_to_resource(rule, known_labels)

        if not known_filters.exists(filter_data):
            filter_data['action'] = dict(filter_data['action'])
            filter_data['criteria'] = dict(filter_data['criteria'])
            print('Creating', filter_data['criteria'], filter_data['action'], file=sys.stderr)
            # Strip out defaultdict and set; they won't be JSON-serializable
            request = service.users().settings().filters().create(userId='me', body=filter_data)
            if not dry_run:
                request.execute()
                time.sleep(1.5)


def find_filters_not_in_ruleset(ruleset, service, dry_run):
    known_labels = GmailLabels(service, dry_run=dry_run)
    known_filters = GmailFilters(service)
    ruleset_filters = [rule_to_resource(rule, known_labels) for rule in ruleset]

    for prunable_filter in known_filters.prunable(ruleset_filters):
        yield prunable_filter


def prune_filters_not_in_ruleset(ruleset, service, dry_run=False):
    prunable_filters = find_filters_not_in_ruleset(ruleset, service, dry_run)
    for prunable_filter in prunable_filters:
        print('Deleting', prunable_filter, file=sys.stderr)
        request = service.users().settings().filters().delete(userId='me', id=prunable_filter['id'])
        if not dry_run:
            request.execute()


def prune_labels_not_in_ruleset(ruleset, service, match=None, dry_run=False,
                                continue_on_http_error=False):
    known_labels = GmailLabels(service, dry_run=dry_run)
    ruleset_filters = [rule_to_resource(rule, known_labels) for rule in ruleset]

    used_label_ids = set(
        label_id
        for filter_dict in ruleset_filters
        for label_ids in filter_dict['action'].values()
        for label_id in label_ids
    )

    unused_labels = [
        label
        for label in GmailLabels(service, dry_run=dry_run)
        if label['id'] not in used_label_ids
        and label['type'] == 'user'
        and (match is None or match(label['name']))
    ]

    for unused_label in sorted(unused_labels, key=itemgetter('name')):
        print('Deleting label', unused_label['name'], '({})'.format(unused_label['id']), file=sys.stderr)
        request = service.users().labels().delete(userId='me', id=unused_label['id'])
        if not dry_run:
            try:
                request.execute()
            except googleapiclient.errors.HttpError:
                if not continue_on_http_error:
                    raise


def get_gmail_service(credentials=None):
    if not credentials:
        credentials = get_gmail_credentials()
    http = credentials.authorize(httplib2.Http())
    return apiclient.discovery.build('gmail', 'v1', http=http)


def get_gmail_credentials(
    scopes=[
        'https://www.googleapis.com/auth/gmail.settings.basic',
        'https://www.googleapis.com/auth/gmail.labels',
    ],
    client_secret_path='client_secret.json',
    application_name='gmail_yaml_filters',
):
    credential_dir = os.path.join(os.path.expanduser('~'), '.credentials')
    credential_path = os.path.join(credential_dir, application_name + '.json')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = oauth2client.client.flow_from_clientsecrets(client_secret_path, scopes)
        flow.user_agent = application_name
        flags_parser = argparse.ArgumentParser(parents=[oauth2client.tools.argparser])
        flags=flags_parser.parse_args([])
        flags.noauth_local_webserver = True
        credentials = oauth2client.tools.run_flow(flow, store, flags)
        print('Storing credentials to', credential_path, file=sys.stderr)

    return credentials
