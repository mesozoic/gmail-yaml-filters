#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import os
import re
import sys

import yaml
from lxml import etree

from .ruleset import RuleSet
from .ruleset import ruleset_to_etree
from .upload import get_gmail_credentials
from .upload import get_gmail_service
from .upload import prune_filters_not_in_ruleset
from .upload import prune_labels_not_in_ruleset
from .upload import upload_ruleset


"""
Produces Gmail filter XML files based on a more human-readable YAML spec.
"""


def ruleset_to_xml(ruleset, pretty_print=True, encoding='utf8'):
    dom = ruleset_to_etree(ruleset)
    chars = etree.tostring(
        dom,
        encoding=encoding,
        pretty_print=pretty_print,
        xml_declaration=True,
    )
    return chars.decode(encoding)


def create_parser():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.set_defaults(action='xml')
    parser.add_argument('filename', metavar='FILTER_FILE', nargs='?')
    parser.add_argument('-n', '--dry-run', action='store_true', default=False,
                        help='do not make any API calls to Gmail')
    parser.add_argument('--client-secret', metavar='CLIENT_SECRET_FILE', nargs='?',
                        help='path to client_secret.json; default is wherever the configuration file is located')
    parser.add_argument('--credential-store', metavar='CREDENTIAL_STORE', nargs='?',
                        help='path to persisted credentials; will be written if it does not exist',
                        default=os.path.join(os.path.expanduser('~'), '.credentials', 'gmail_yaml_filters.json'))

    # Actions
    parser.add_argument('--upload', dest='action', action='store_const', const='upload',
                        help='create filters and labels in Gmail')
    parser.add_argument('--prune', dest='action', action='store_const', const='prune',
                        help='delete any Gmail filters that are not defined in the configuration file')
    parser.add_argument('--sync', dest='action', action='store_const', const='upload_prune',
                        help='equivalent to --upload and --prune')
    parser.add_argument('--delete-all', dest='action', action='store_const', const='delete',
                        help='delete all Gmail filters')
    # Options for --prune-labels
    parser.add_argument('--prune-labels', dest='action', action='store_const', const='prune_labels',
                        help='delete any Gmail labels which are not used in the configuration file')
    parser.add_argument('--only-matching', default=r'.*', metavar='REGEX',
                        help='only prune labels matching the given expression')
    parser.add_argument('--ignore-errors', action='store_true', default=False,
                        help='ignore HTTP errors when deleting labels')
    return parser


def load_data_from_args(action, filename):
    if action == "delete":
        return []

    if filename == "-":
        data = yaml.safe_load(sys.stdin)
    elif filename:
        with open(filename) as inputf:
            data = yaml.safe_load(inputf)
    else:
        raise ValueError((action, filename))

    if not isinstance(data, list):
        data = [data]

    return data


def main():
    parser = create_parser()
    args = parser.parse_args()
    default_client_secret = 'client_secret.json'

    try:
        data = load_data_from_args(args.action, args.filename)
    except ValueError:
        parser.print_help()
        sys.exit(1)

    ruleset = RuleSet.from_object(rule for rule in data if not rule.get('ignore'))

    if not args.client_secret:
        args.client_secret = default_client_secret

    if args.action == 'xml':
        print(ruleset_to_xml(ruleset))
        return

    # every command below this point involves the Gmail API

    credentials = get_gmail_credentials(client_secret_path=args.client_secret, credential_store=args.credential_store)
    gmail = get_gmail_service(credentials)

    if args.action == 'upload':
        upload_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
    elif args.action == 'delete':
        prune_filters_not_in_ruleset(RuleSet(), service=gmail, dry_run=args.dry_run)
    elif args.action == 'prune':
        prune_filters_not_in_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
    elif args.action == 'upload_prune':
        upload_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
        prune_filters_not_in_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
    elif args.action == 'prune_labels':
        match = re.compile(args.only_matching).match if args.only_matching else None
        prune_labels_not_in_ruleset(ruleset, service=gmail, match=match, dry_run=args.dry_run,
                                    continue_on_http_error=args.ignore_errors)
    else:
        raise argparse.ArgumentError('%r not recognized' % args.action)


if __name__ == '__main__':
    main()
