#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from __future__ import print_function

from collections import Iterable
from collections import OrderedDict
from datetime import datetime
from functools import total_ordering
from itertools import chain
from lxml import etree
import argparse
import re
import sys
import yaml

from gmail_yaml_filters.upload import get_gmail_service
from gmail_yaml_filters.upload import upload_ruleset
from gmail_yaml_filters.upload import prune_filters_not_in_ruleset
from gmail_yaml_filters.upload import prune_labels_not_in_ruleset


"""
Produces Gmail filter XML files based on a more human-readable YAML spec.
"""


# Unicode support. <http://stackoverflow.com/questions/2890146>
def construct_yaml_str(self, node):
    return self.construct_scalar(node)


yaml.Loader.add_constructor('tag:yaml.org,2002:str', construct_yaml_str)
yaml.SafeLoader.add_constructor('tag:yaml.org,2002:str', construct_yaml_str)


def quote_value_if_necessary(value):
    if ' ' in value and '"' not in value \
            and not value.startswith('-') \
            and not (
                value.startswith('(') and value.endswith(')')
            ):
        return '"{0}"'.format(value)
    return value


class InvalidIdentifier(ValueError):
    pass


class InvalidRuleType(ValueError):
    pass


class KeyMismatch(RuntimeError):
    def __init__(self, first, second):
        self.first = first
        self.second = second

    def __str__(self):
        return '{0} vs. {1}'.format(repr(self.first), repr(self.second))


@total_ordering
class _RuleConstruction(object):
    # Maps kwargs and YAML keys to Google values
    identifier_map = None
    # Maps special keys to tuples of key/value format strings
    formatter_map = {}

    def __init__(self, key, value, validate_value=True):
        key, value = self.remap_key_and_value(key, value)
        key = self.validate_key(key)
        if validate_value:
            value = self.validate_value(key, value)
        self.key = key
        self._value = value

    @property
    def value(self):
        return self._value

    @classmethod
    def remap_key_and_value(cls, key, value):
        if key in cls.formatter_map:
            original = dict(key=key, value=value)
            key_fmt, value_fmt = cls.formatter_map[key]
            key = key_fmt.format(**original)
            value = value_fmt.format(**original)

        return key, value

    @classmethod
    def validate_key(cls, key):
        try:
            return cls.identifier_map[key]
        except KeyError:
            if key in cls.identifier_map.itervalues():
                return key
            else:
                raise InvalidIdentifier(repr(key))

    @classmethod
    def validate_value(cls, key, value):
        return value

    def apply_format(self, **format_vars):
        self._value = self._value.format(**format_vars)

    def __hash__(self):
        return hash((self.key, self.value))

    def __repr__(self):
        return '{0}({1!r}, {2!r})'.format(self.__class__.__name__, self.key, self.value)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and (self.key, self.value) == (other.key, other.value)

    def __lt__(self, other):
        return isinstance(other, self.__class__) and (self.key, self.value) < (other.key, other.value)


class RuleCondition(_RuleConstruction):
    """
    Represents a condition for a Gmail filter.

    >>> cond = RuleCondition('from', 'bill@microsoft.com')
    >>> cond.key
    u'from'
    >>> cond.value
    u'bill@microsoft.com'

    We don't do anything intelligent with Gmail's search keywords
    if they're included in the condition value. For example, the
    below is equivalent to the previous example:

    >>> cond = RuleCondition('match', 'from:bill@microsoft.com')
    >>> cond.key
    u'hasTheWord'
    >>> cond.value
    u'from:bill@microsoft.com'

    We implement a 'list:' shortcut:

    >>> RuleCondition('list', 'exec.msft.com')
    RuleCondition(u'hasTheWord', u'list:(exec.msft.com)')

    ...and the ability to negate a rule:

    >>> RuleCondition('list', 'exec.msft.com', negate=True)
    RuleCondition(u'hasTheWord', u'-list:(exec.msft.com)')
    """

    identifier_map = {
        'from': 'from',
        'to': 'to',
        'subject': 'subject',
        'has': 'hasTheWord',
        'match': 'hasTheWord',
        'does_not_have': 'doesNotHaveTheWord',
        'missing': 'doesNotHaveTheWord',
        'no_match': 'doesNotHaveTheWord',
    }

    formatter_map = {
        'list': ('has', 'list:({value})'),
    }

    def __init__(self, key, value, validate_value=True, negate=False):
        super(RuleCondition, self).__init__(key, value, validate_value=validate_value)
        self.negate = negate

    def negated(self):
        return self.__class__(self.key, self.value, validate_value=False, negate=(not self.negate))

    @property
    def value(self):
        if self.negate:
            return '-{0}'.format(self._value)
        else:
            return self._value

    @classmethod
    def validate_value(cls, key, value):
        if isinstance(value, basestring):
            value = quote_value_if_necessary(value)
        return value

    @classmethod
    def joined_by(cls, joiner, key, values):
        validated = [cls.validate_value(key, value) for value in sorted(values)]
        joined = '({0})'.format(joiner.join(validated))
        return cls(key, joined, validate_value=False)

    @classmethod
    def and_(cls, key, values):
        return cls.joined_by(' AND ', key, values)

    @classmethod
    def or_(cls, key, values):
        return cls.joined_by(' OR ', key, values)


class RuleAction(_RuleConstruction):
    """
    >>> RuleAction('important', True)
    RuleAction(u'shouldAlwaysMarkAsImportant', u'true')
    """
    identifier_map = {
        'label': 'label',
        'important': 'shouldAlwaysMarkAsImportant',
        'mark_as_important': 'shouldAlwaysMarkAsImportant',
        'not_important': 'shouldNeverMarkAsImportant',
        'never_mark_as_important': 'shouldNeverMarkAsImportant',
        'archive': 'shouldArchive',
        'read': 'shouldMarkAsRead',
        'mark_as_read': 'shouldMarkAsRead',
        'star': 'shouldStar',
        'trash': 'shouldTrash',
        'delete': 'shouldTrash',
        'not_spam': 'shouldNeverSpam',
        # TODO: support smart labels / tabs (Personal, Social, etc.)
    }

    @classmethod
    def validate_value(cls, key, value):
        if isinstance(value, bool):
            return unicode(value).lower()
        else:
            return value


def build_compound_conditions(key, compound):
    """
    Create an "any" or "all" (or combination thereof).

    >>> build_compound_conditions('hasTheWord', 'whatever')
    [RuleCondition(u'hasTheWord', u'whatever')]

    >>> build_compound_conditions('hasTheWord', {'not': 'whatever'})
    [RuleCondition(u'hasTheWord', u'-whatever')]

    >>> build_compound_conditions('hasTheWord', {'any': ['foo', 'bar', 'baz']})
    [RuleCondition(u'hasTheWord', u'(bar OR baz OR foo)')]

    >>> build_compound_conditions('hasTheWord', {'all': ['foo', 'bar', 'baz']})
    [RuleCondition(u'hasTheWord', u'(bar AND baz AND foo)')]

    >>> build_compound_conditions('hasTheWord', {'all': ['foo', 'bar'], 'any': 'baz'})
    [RuleCondition(u'hasTheWord', u'(bar AND foo)'), RuleCondition(u'hasTheWord', u'(baz)')]

    >>> build_compound_conditions('hasTheWord', {'all': ['foo', 'bar'], 'not': {'any': ['baz', 'blitz']}})
    [RuleCondition(u'hasTheWord', u'(bar AND foo)'), RuleCondition(u'hasTheWord', u'-(baz OR blitz)')]
    """
    if isinstance(compound, basestring):
        return [RuleCondition(key, compound)]

    invalid_keys = set(compound) - set(['any', 'all', 'not'])
    if invalid_keys:
        raise KeyError(invalid_keys)

    # Listify a single string rather than turning each letter into a condition; this is a common user mistake
    # and it's better to second-guess their intent than to treat a string like a list of single-letter searches.
    conditions = []

    if 'any' in compound:
        value = [compound['any']] if isinstance(compound['any'], basestring) else compound['any']
        conditions.append(RuleCondition.or_(key, value))

    if 'all' in compound:
        value = [compound['all']] if isinstance(compound['all'], basestring) else compound['all']
        conditions.append(RuleCondition.and_(key, value))

    if 'not' in compound:
        conditions.extend(rule.negated() for rule in build_compound_conditions(key, compound['not']))

    return sorted(conditions)


@total_ordering
class Rule(object):
    """
    Defines a set of conditions and a set of actions to apply to those conditions.

    >>> rule = Rule({'from': 'bill@microsoft.com', 'delete': True})
    >>> rule.conditions
    [RuleCondition(u'from', u'bill@microsoft.com')]
    >>> rule.actions
    [RuleAction(u'shouldTrash', u'true')]

    Strings with spaces in them will get quoted, but strings without spaces won't:

    >>> rule = Rule({'has': 'great discount', 'to': '-bill@microsoft.com'})
    >>> sorted(rule.flatten().items())
    ... # doctest: +NORMALIZE_WHITESPACE
    [(u'hasTheWord', RuleCondition(u'hasTheWord', u'"great discount"')),
     (u'to', RuleCondition(u'to', u'-bill@microsoft.com'))]

    You can pass in a list of values, and they'll be AND'd together:

    >>> rule = Rule({'has': ['great discount', 'cheap airfare']})
    >>> rule.flatten()
    {u'hasTheWord': RuleCondition(u'hasTheWord', u'("cheap airfare" AND "great discount")')}

    You can also use an "all" hash to achieve the same effect:

    >>> rule = Rule({'has': ['great discount', 'cheap airfare']})
    >>> rule.flatten()
    {u'hasTheWord': RuleCondition(u'hasTheWord', u'("cheap airfare" AND "great discount")')}

    ...or an "any" hash to get conditions OR'd together:

    >>> rule = Rule({'from': {'any': ['bill@msft.com', 'steve@msft.com', 'satya@msft.com']}})
    >>> rule.flatten()
    {u'from': RuleCondition(u'from', u'(bill@msft.com OR satya@msft.com OR steve@msft.com)')}

    ...or something wacky:

    >>> rule = Rule({
    ...     'to': {
    ...         'not': {'any': ['bill@msft.com', 'steve@msft.com']},
    ...         'all': ['satya@msft.com'],
    ...     }
    ... })
    >>> rule.flatten()
    {u'to': RuleCondition(u'to', u'((satya@msft.com) AND -(bill@msft.com OR steve@msft.com))')}
    """

    def __init__(self, data=None, base_rule=None):
        # Maps the canonical Google rule key (e.g. hasTheWord) to a list of values (AND'd)
        self._conditions = {}
        # Maps the canonical Google rule key (e.g. hasTheWord) to a list of values (AND'd)
        self._actions = {}
        self.base_rule = base_rule
        if data:
            self.update(data)

    def __repr__(self):
        rule_reprs = [
            '{0}={1!r}'.format(key, sorted(value) if isinstance(value, list) else value)
            for key, value in sorted(self.data.iteritems())
        ]
        return '{0}({1})'.format(self.__class__.__name__, ', '.join(sorted(rule_reprs)))

    def __eq__(self, other):
        return self.sortable_data == other.sortable_data

    def __lt__(self, other):
        return self.sortable_data < other.sortable_data

    def update(self, data):
        for key, value in dict(data).iteritems():
            self.add(key, value)

    def add(self, key, value, validate=True):
        if isinstance(value, (bool, basestring)):
            self.add_construction(key, value)
        elif isinstance(value, dict):
            self.add_compound_conditions(key, value)
        elif isinstance(value, Iterable):
            for actual_value in value:
                self.add(key, actual_value)
        else:
            raise InvalidRuleType(type(value))

    def add_construction(self, key, value):
        try:
            self.add_condition(RuleCondition(key, value))
        except InvalidIdentifier:
            self.add_action(RuleAction(key, value))

    def add_compound_conditions(self, key, compound):
        for condition in build_compound_conditions(key, compound):
            self.add_condition(condition)

    def add_condition(self, condition):
        self._conditions.setdefault(condition.key, set()).add(condition)

    def add_action(self, action):
        self._actions.setdefault(action.key, set()).add(action)

    @property
    def data(self):
        """
        Returns a single dictionary representing all of
        the rule's conditions and actions, including its base.
        """
        data = {}
        if self.base_rule:
            data.update(self.base_rule.data)
        for condition in list(chain.from_iterable(self._conditions.itervalues())):
            data.setdefault(condition.key, []).append(condition)
        for action in list(chain.from_iterable(self._actions.itervalues())):
            data[action.key] = [action]  # you can only take a given action _once_
        return data

    @property
    def sortable_data(self):
        return tuple(sorted(self.data.items()))

    @property
    def conditions(self):
        """Returns a list of this rule's conditions.
        """
        return self._separated_constructs(RuleCondition)

    @property
    def actions(self):
        """Returns a list of all this rule's conditions.
        """
        return self._separated_constructs(RuleAction)

    def _separated_constructs(self, construct_class):
        return sorted(
            data_value
            for data_key, data_values in self.data.iteritems()
            for data_value in data_values
            if isinstance(data_value, construct_class)
        )

    def flatten(self):
        """
        Combine all conditions or actions which share the same key,
        and return a single dict of constructs that can be serialized.
        """
        flattened = {}
        for key, constructs in self.data.iteritems():
            if not constructs:
                continue
            construct_class = constructs[0].__class__  # we shouldn't ever mix
            if len(constructs) == 1:
                flattened[key] = construct_class(key, constructs[0].value, validate_value=False)
            else:
                flattened[key] = construct_class.and_(key, sorted(c.value for c in constructs))
        return flattened

    def apply_format(self, **format_vars):
        """Uses the same semantics as str.format to interpolate variables into
        the values of conditions and actions.
        """
        for construction_dict in (self._actions, self._conditions):
            for construction_key, construction_objs in construction_dict.iteritems():
                for construction in construction_objs:
                    construction.apply_format(**format_vars)


class RuleSet(object):
    """
    Contains a set of Rule instances.

    You can create these using dictionaries:

    >>> def sample_rule(name):
    ...     return {'from': '{0}@microsoft.com'.format(name), 'trash': True}
    >>> ruleset = RuleSet.from_object(sample_rule('bill'))
    >>> sorted(ruleset)
    ... # doctest: +NORMALIZE_WHITESPACE
    [Rule(from=[RuleCondition(u'from', u'bill@microsoft.com')],
          shouldTrash=[RuleAction(u'shouldTrash', u'true')])]

    Or using lists of dictionaries:

    >>> sorted(RuleSet.from_object([sample_rule('bill'), sample_rule('steve')]))
    ... # doctest: +NORMALIZE_WHITESPACE
    [Rule(from=[RuleCondition(u'from', u'bill@microsoft.com')],
          shouldTrash=[RuleAction(u'shouldTrash', u'true')]),
     Rule(from=[RuleCondition(u'from', u'steve@microsoft.com')],
          shouldTrash=[RuleAction(u'shouldTrash', u'true')])]

    Or with nested conditions:

    >>> ruleset = RuleSet.from_object({
    ...     'from': 'steve@aapl.com',
    ...     'archive': True,
    ...     'more': {
    ...         'subject': 'stop ignoring me',
    ...         'archive': False,
    ...     }
    ... })
    >>> sorted(ruleset)
    ... # doctest: +NORMALIZE_WHITESPACE
    [Rule(from=[RuleCondition(u'from', u'steve@aapl.com')],
          shouldArchive=[RuleAction(u'shouldArchive', u'false')],
          subject=[RuleCondition(u'subject', u'"stop ignoring me"')]),
     Rule(from=[RuleCondition(u'from', u'steve@aapl.com')],
          shouldArchive=[RuleAction(u'shouldArchive', u'true')])]

    Or even with loops:

    >>> ruleset = RuleSet.from_object({
    ...     'for_each': ['steve', 'jony', 'tim'],
    ...     'rule': {
    ...         'from': '{item}@aapl.com',
    ...         'star': True,
    ...         'important': True,
    ...         'more': [
    ...             {'label': 'everyone', 'to': 'everyone@aapl.com'},
    ...         ]
    ...     }
    ... })
    >>> sorted(rule.conditions for rule in ruleset)
    ... # doctest: +NORMALIZE_WHITESPACE
    [[RuleCondition(u'from', u'jony@aapl.com')],
     [RuleCondition(u'from', u'jony@aapl.com'), RuleCondition(u'to', u'everyone@aapl.com')],
     [RuleCondition(u'from', u'steve@aapl.com')],
     [RuleCondition(u'from', u'steve@aapl.com'), RuleCondition(u'to', u'everyone@aapl.com')],
     [RuleCondition(u'from', u'tim@aapl.com')],
     [RuleCondition(u'from', u'tim@aapl.com'), RuleCondition(u'to', u'everyone@aapl.com')]]
    """

    more_key = 'more'
    foreach_key = 'for_each'
    foreach_rule_key = 'rule'

    def __init__(self):
        self._rules = OrderedDict()

    def __iter__(self):
        for rule_key, rule in self._rules.iteritems():
            yield rule

    def add(self, rule):
        self._rules[hash(rule)] = rule

    def update(self, ruleset):
        for rule in ruleset.rules:
            self.add(rule)

    @property
    def rules(self):
        return self._rules.values()

    @classmethod
    def from_object(cls, obj, base_rule=None):
        """Returns a RuleSet from a dictionary or list of rules.
        """
        if isinstance(obj, dict):
            return cls.from_dict(obj, base_rule=base_rule)
        elif isinstance(obj, Iterable):
            return cls.from_iterable(obj, base_rule=base_rule)
        else:
            raise ValueError('Cannot build {0} from {1}'.format(cls, type(obj)))

    @classmethod
    def from_dict(cls, data, base_rule=None):
        if cls.foreach_key in data:
            return cls.from_foreach_dict(data, base_rule=base_rule)

        data = data.copy()

        try:
            child_rule_data = data.pop(cls.more_key)
        except KeyError:
            child_rule_data = None

        new_rule = Rule(data, base_rule=base_rule)
        ruleset = cls()
        ruleset.add(new_rule)

        if child_rule_data:
            ruleset.update(cls.from_object(child_rule_data, base_rule=new_rule))

        return ruleset

    @classmethod
    def from_iterable(cls, iterable, base_rule=None):
        ruleset = cls()
        for data in iterable:
            ruleset.update(cls.from_object(data, base_rule=base_rule))
        return ruleset

    @classmethod
    def from_foreach_dict(cls, data, base_rule=None):
        if set(data.keys()) != set([cls.foreach_key, cls.foreach_rule_key]):
            raise InvalidIdentifier(data.keys())

        ruleset = cls()
        for index, item in enumerate(data[cls.foreach_key]):
            item_ruleset = cls.from_object(data[cls.foreach_rule_key], base_rule=base_rule)
            for rule in item_ruleset:
                rule.apply_format(index=index, item=item)
            ruleset.update(item_ruleset)

        return ruleset


def ruleset_to_etree(ruleset):
    xml = etree.Element('feed', nsmap={
        None: 'http://www.w3.org/2005/Atom',
        'apps': 'http://schemas.google.com/apps/2006',
    })
    etree.SubElement(xml, 'title').text = 'Mail Filters'
    for rule in sorted(ruleset):
        if not rule.actions:
            continue
        entry = etree.SubElement(xml, 'entry')
        etree.SubElement(entry, 'category', term='filter')
        etree.SubElement(entry, 'title').text = 'Mail Filter'
        etree.SubElement(entry, 'id').text = 'tag:mail.google.com,2008:filter:{0}'.format(abs(hash(rule)))
        etree.SubElement(entry, 'updated').text = datetime.now().replace(microsecond=0).isoformat() + 'Z'
        etree.SubElement(entry, 'content')
        for construct in rule.flatten().itervalues():
            etree.SubElement(
                entry,
                '{http://schemas.google.com/apps/2006}property',
                name=construct.key,
                value=unicode(construct.value),
            )
    return xml


def ruleset_to_xml(ruleset):
    dom = ruleset_to_etree(ruleset)
    return etree.tostring(dom, pretty_print=True, encoding='utf8').decode('utf8')


def create_parser():
    parser = argparse.ArgumentParser()
    parser.set_defaults(action='xml')
    parser.add_argument('-n', '--dry-run', action='store_true', default=False)
    parser.add_argument('filename', metavar='FILE', default='-')
    # Actions
    parser.add_argument('--prune', dest='action', action='store_const', const='prune')
    parser.add_argument('--sync', dest='action', action='store_const', const='upload_prune')
    parser.add_argument('--upload', dest='action', action='store_const', const='upload')
    parser.add_argument('--prune-labels', dest='action', action='store_const', const='prune_labels')
    # Options for --prune-labels
    parser.add_argument('--only-matching', default=r'.*', metavar='REGEX')
    parser.add_argument('--ignore-errors', action='store_true', default=False)
    return parser


def main():
    args = create_parser().parse_args()

    if args.filename == '-':
        data = yaml.safe_load(sys.stdin)
    else:
        with open(args.filename) as inputf:
            data = yaml.safe_load(inputf)

    if not isinstance(data, list):
        data = [data]

    ruleset = RuleSet.from_object(rule for rule in data if not rule.get('ignore'))

    if args.action == 'xml':
        print(ruleset_to_xml(ruleset))
    elif args.action == 'upload':
        upload_ruleset(ruleset, dry_run=args.dry_run)
    elif args.action == 'prune':
        prune_filters_not_in_ruleset(ruleset, dry_run=args.dry_run)
    elif args.action == 'upload_prune':
        gmail = get_gmail_service()
        upload_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
        prune_filters_not_in_ruleset(ruleset, service=gmail, dry_run=args.dry_run)
    elif args.action == 'prune_labels':
        gmail = get_gmail_service()
        match = re.compile(args.only_matching).match if args.only_matching else None
        prune_labels_not_in_ruleset(ruleset, service=gmail, match=match, dry_run=args.dry_run,
                                    continue_on_http_error=args.ignore_errors)
    else:
        raise argparse.ArgumentError('%r not recognized' % args.action)


if __name__ == '__main__':
    main()
