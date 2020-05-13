#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from __future__ import print_function

from lxml import etree
import argparse
import os
import re
import sys
import yaml

from .ruleset import RuleSet
from .ruleset import ruleset_to_etree

from .upload import get_gmail_credentials
from .upload import get_gmail_service
from .upload import upload_ruleset
from .upload import prune_filters_not_in_ruleset
from .upload import prune_labels_not_in_ruleset


"""
Produces Gmail filter XML files based on a more human-readable YAML spec.
"""


# Unicode support. <http://stackoverflow.com/questions/2890146>
def construct_yaml_str(self, node):
    return self.construct_scalar(node)


yaml.Loader.add_constructor('tag:yaml.org,2002:str', construct_yaml_str)
yaml.SafeLoader.add_constructor('tag:yaml.org,2002:str', construct_yaml_str)


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
    parser = argparse.ArgumentParser()
    parser.set_defaults(action='xml')
    parser.add_argument('filename', metavar='FILTER_FILE', default='-')
    parser.add_argument('-n', '--dry-run', action='store_true', default=False,
                        help='do not make any API calls to Gmail')
    parser.add_argument('--client-secret', metavar='CLIENT_SECRET_FILE', nargs='?',
                        help='path to client_secret.json; default is wherever the configuration file is located')
    # Actions
    parser.add_argument('--upload', dest='action', action='store_const', const='upload',
                        help='create filters and labels in Gmail')
    parser.add_argument('--prune', dest='action', action='store_const', const='prune',
                        help='delete any Gmail filters that are not defined in the configuration file')
    parser.add_argument('--sync', dest='action', action='store_const', const='upload_prune',
                        help='equivalent to --upload and --prune')
    # Options for --prune-labels
    parser.add_argument('--prune-labels', dest='action', action='store_const', const='prune_labels',
                        help='delete any Gmail labels which are not used in the configuration file')
    parser.add_argument('--only-matching', default=r'.*', metavar='REGEX',
                        help='only prune labels matching the given expression')
    parser.add_argument('--ignore-errors', action='store_true', default=False,
                        help='ignore HTTP errors when deleting labels')
    return parser


def main():
    args = create_parser().parse_args()

    if args.filename == '-':
        default_client_secret = 'client_secret.json'
        data = yaml.safe_load(sys.stdin)
    else:
        default_client_secret = os.path.join(os.path.dirname(args.filename), 'client_secret.json')
        with open(args.filename) as inputf:
            data = yaml.safe_load(inputf)

    if not isinstance(data, list):
        data = [data]

    ruleset = RuleSet.from_object(rule for rule in data if not rule.get('ignore'))

    if not args.client_secret:
        args.client_secret = default_client_secret

    credentials = get_gmail_credentials(client_secret_path=args.client_secret)

    if args.action == 'xml':
        print(ruleset_to_xml(ruleset))
    elif args.action == 'upload':
        upload_ruleset(ruleset, dry_run=args.dry_run)
    elif args.action == 'prune':
        gmail = get_gmail_service(credentials)
        prune_filters_not_in_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
    elif args.action == 'upload_prune':
        gmail = get_gmail_service(credentials)
        upload_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
        prune_filters_not_in_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
    elif args.action == 'prune_labels':
        gmail = get_gmail_service(credentials)
        match = re.compile(args.only_matching).match if args.only_matching else None
        prune_labels_not_in_ruleset(ruleset, service=gmail, match=match, dry_run=args.dry_run,
                                    continue_on_http_error=args.ignore_errors)
    else:
        raise argparse.ArgumentError('%r not recognized' % args.action)


if __name__ == '__main__':
    main()
