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
        for condition in rule.conditions
    }


ACTION_KEY_MAP = {
    'label': None,
    'shouldAlwaysMarkAsImportant': ('add', {'IMPORTANT'}),
    'shouldArchive': ('remove', {'INBOX'}),
    'shouldMarkAsRead': ('remove', {'UNREAD'}),
    'shouldNeverMarkAsImportant': ('remove', {'IMPORTANT'}),
    'shouldNeverSpam': ('remove', {'SPAM'}),
    'shouldStar': ('add', {'STARRED'}),
    'shouldTrash': ('add', {'TRASH'}),
}


def _rule_actions_to_dict(rule):
    result = defaultdict(set)
    for action in rule.actions:
        label_action = ACTION_KEY_MAP[action.key]
        if action.key == 'label':
            result['addLabelIds'].add(action.value)
        elif label_action:
            result['{}LabelIds'.format(label_action[0])].update(label_action[1])
        else:
            raise ValueError('Unexpected action key: {0!r}'.format(action.key))
    return result
    # strip away defaultdict and set; they won't be JSON-serializable
    return {key: list(values) for key, values in result.items()}


def rule_to_filter_resource(rule):
    """Converts a Rule instance to the Gmail v1 API Filter resource.

    See https://developers.google.com/gmail/api/v1/reference/users/settings/filters#resource
    """
    return {
        'criteria': _rule_conditions_to_dict(rule),
        'action': _rule_actions_to_dict(rule),
    }


def upload_rule(rule, service):
    rule_dict = rule_to_filter_resource(rule)
    print('Creating rule', rule_dict, file=sys.stderr)
    #service.users().settings().filters().create(userId='me', body=rule_dict)


def upload_ruleset(ruleset, service=None):
    service = service or get_gmail_service()
    for rule in ruleset:
        if not rule.actions:
            continue
        upload_rule(rule, service)


def get_gmail_service():
    credentials = get_gmail_credentials()
    http = credentials.authorize(httplib2.Http())
    service = apiclient.discovery.build('gmail', 'v1', http=http)
    return service


def get_gmail_credentials(
    scopes='https://www.googleapis.com/auth/gmail.settings.basic',
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
