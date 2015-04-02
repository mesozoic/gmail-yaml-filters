from __future__ import unicode_literals
from __future__ import print_function

from collections import Iterable
from datetime import datetime
from itertools import chain
from lxml import etree
import sys
import yaml


# Unicode support. <http://stackoverflow.com/questions/2890146>
def construct_yaml_str(self, node):
    return self.construct_scalar(node)

yaml.Loader.add_constructor('tag:yaml.org,2002:str', construct_yaml_str)
yaml.SafeLoader.add_constructor('tag:yaml.org,2002:str', construct_yaml_str)



class InvalidIdentifier(ValueError):
    pass


class _RuleConstruction(object):
    #. Maps kwargs and YAML keys to Google values
    identifier_map = None

    def __init__(self, key, value):
        self.key = self.validate_key(key)
        self.value = self.validate_value(value)

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
    def validate_value(cls, value):
        return value

    def __repr__(self):
        return '{0}({1!r}, {2!r})'.format(self.__class__.__name__, self.key, self.value)


class RuleCondition(_RuleConstruction):
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

    @classmethod
    def validate_value(cls, value):
        if '"' not in value:
            return '"{0}"'.format(value)
        else:
            return value


def _or(conditions):
    return ' OR '.join('({0})'.format(condition) for condition in conditions)


def _and(conditions):
    return ' AND '.join('({0})'.format(condition) for condition in conditions)


class RuleAction(_RuleConstruction):
    identifier_map = {
        'label': 'label',
        'important': 'shouldAlwaysMarkAsImportant',
        'unimportant': 'shouldNeverMarkAsImportant',
        'not_important': 'shouldNeverMarkAsImportant',
        'archive': 'shouldArchive',
        'read': 'shouldMarkAsRead',
        'star': 'shouldStar',
        'trash': 'shouldTrash',
        'delete': 'shouldTrash',
        # TODO: support smart labels / tabs (Personal, Social, etc.)
    }


class Rule(object):

    def __init__(self, data=None, base_rule=None):
        #. Maps the canonical Google rule key (e.g. hasTheWord) to a list of values (AND'd)
        self._conditions = {}
        #. Maps the canonical Google rule key (e.g. hasTheWord) to a list of values (AND'd)
        self._actions = {}
        self.base_rule = base_rule
        if data:
            self.update(data)

    def update(self, data):
        for key, value in dict(data).iteritems():
            self.add(key, value)

    def add(self, key, value):
        if isinstance(value, RuleCondition):
            if key != value.key:
                raise ValueError('Key mismatch: {0!r}, {1!r}'.format(key, value.key))
            self.add_condition(value)
        elif isinstance(value, RuleAction):
            if key != value.key:
                raise ValueError('Key mismatch: {0!r}, {1!r}'.format(key, value.key))
            self.add_action(value)
        elif isinstance(value, basestring):
            self.add_construction(key, value)
        elif isinstance(value, dict):
            self.add_compound_construction(key, value)
        elif isinstance(value, bool):
            self.add(key, str(value).lower())  # google wants 'true' or 'false'
        elif isinstance(value, Iterable):
            for actual_value in value:
                self.add(key, actual_value)
        else:
            raise ValueError('Unrecognized type for rule construction: {0}'.format(type(value)))

    def add_construction(self, key, value):
        try:
            self.add_condition(RuleCondition(key, value))
        except InvalidIdentifier:
            self.add_action(RuleAction(key, value))

    def add_compound_construction(self, key, compound):
        """
        >>> rule.add_compound_construction('hasTheWord', {'any': ['foo', 'bar', 'baz']})
        >>> rule.add_compound_construction('hasTheWord', {'all': ['foo', 'bar', 'baz']})
        """
        if 'any' in compound:
            any_conditions = _or(compound['any'])
            self.add(key, any_conditions)
        if 'all' in compound:
            self.add(key, compound['all'])

    def add_condition(self, condition):
        self._conditions.setdefault(condition.key, []).append(condition)

    def add_action(self, action):
        self._actions.setdefault(action.key, []).append(action)

    @property
    def conditions(self):
        """Returns a combined set of the base rule's conditions and this rule's conditions.
        """
        data = {}
        if self.base_rule:
            data.update(self.base_rule._conditions)
        for key, conditions in self._conditions.iteritems():
            data.setdefault(key, []).extend(conditions)
        # each value in data is a list, so we need to flatten it
        return list(chain.from_iterable(data.itervalues()))

    @property
    def actions(self):
        """Returns the set of all this rule's conditions.
        """
        # each value in self._actions is a list, so we need to flatten it
        return list(chain.from_iterable(self._actions.itervalues()))

    @property
    def data(self):
        """
        Returns a single dictionary representing all of
        the rule's conditions and actions.
        """
        data = {}
        for construct in chain(self.conditions, self.actions):
            data.setdefault(construct.key, []).append(construct)
        return data

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
                flattened[key] = construct_class(key, constructs[0].value)
            else:
                flattened[key] = construct_class(key, _and(c.value for c in constructs))
        return flattened

    def __hash__(self):
        return hash(tuple(self.data))

    def __repr__(self):
        return '{cls}({data})'.format(self.__class__.__name__, self.data)

    def to_etree(self, parent):
        entry = etree.SubElement(parent, 'entry')
        etree.SubElement(entry, 'category', term='filter')
        etree.SubElement(entry, 'title').text = 'Mail Filter'
        etree.SubElement(entry, 'id').text = 'tag:mail.google.com,2008:filter:{0}'.format(hash(self))
        etree.SubElement(entry, 'updated').text = datetime.now().replace(microsecond=0).isoformat() + 'Z'
        etree.SubElement(entry, 'content')
        for construct in self.flatten().itervalues():
            etree.SubElement(
                entry,
                '{http://schemas.google.com/apps/2006}property',
                name=construct.key,
                value=unicode(construct.value),
            )
        return entry


class RuleSet(set):
    more_key = 'more'

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
        try:
            child_rule_data = data.pop(cls.more_key)
        except KeyError:
            child_rule_data = []

        base_rule = Rule(data, base_rule=base_rule)

        ruleset = cls()
        ruleset.add(base_rule)
        ruleset.update(cls.from_object(child_rule_data, base_rule=base_rule))

        return ruleset

    @classmethod
    def from_iterable(cls, iterable, base_rule=None):
        ruleset = cls()
        for data in iterable:
            ruleset.update(cls.from_object(data, base_rule=base_rule))
        return ruleset

    def to_etree(self):
        xml = etree.Element(
            'feed',
            nsmap={
                None: 'http://www.w3.org/2005/Atom',
                'apps': 'http://schemas.google.com/apps/2006',
            },
        )
        etree.SubElement(xml, 'title').text = 'Mail Filters'
        for rule in self:
            rule.to_etree(parent=xml)
        return xml

    def __unicode__(self):
        return etree.tostring(self.to_etree(), pretty_print=True, encoding='utf-8').decode('utf-8')



if __name__ == '__main__':
    with open('levy.yaml') as inputf:
        data = yaml.safe_load(inputf.read())

    ruleset = RuleSet.from_object(data)
    print(unicode(ruleset))
