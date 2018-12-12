# -*- coding: utf-8 -*-

from __future__ import unicode_literals


from gmail_yaml_filters.ruleset import RuleSet
from gmail_yaml_filters.ruleset import RuleAction
from gmail_yaml_filters.ruleset import RuleCondition


def rule(rule_obj):
    return sorted(RuleSet.from_object(rule_obj))[0]


def _flat(rule_obj):
    return rule(rule_obj).flatten()


def sample_rule(name):
    return {
        'from': '{}@msft.com'.format(name),
        'trash': True,
    }


# Test how identifier_map and formatter_map operate

def test_condition_has():
    assert _flat({'has': 'whatever'}) == {
        'hasTheWord': RuleCondition('hasTheWord', 'whatever'),
    }


def test_condition_has_special():
    assert _flat({'has': 'drive'}) == {
        'hasTheWord': RuleCondition('hasTheWord', 'has:drive'),
    }


def test_condition_has_label():
    assert _flat({'labeled': 'whatever'}) == {
        'hasTheWord': RuleCondition('hasTheWord', 'label:(whatever)'),
    }


def test_condition_does_not_have_label():
    assert _flat({'labeled': '-whatever'}) == {
        'doesNotHaveTheWord': RuleCondition('doesNotHaveTheWord', 'label:(whatever)'),
    }


def test_condition_is():
    assert _flat({'is': 'snoozed'}) == {
        'hasTheWord': RuleCondition('hasTheWord', 'is:(snoozed)'),
    }


def test_condition_is_not():
    assert _flat({'is': '-snoozed'}) == {
        'doesNotHaveTheWord': RuleCondition('doesNotHaveTheWord', 'is:(snoozed)'),
    }


def test_action_archive():
    assert _flat({'archive': True}) == {
        'shouldArchive': RuleAction('shouldArchive', 'true'),
    }


def test_action_forward():
    assert _flat({'forward': 'someone@example.com'}) == {
        'forwardTo': RuleAction('forwardTo', 'someone@example.com'),
    }


def test_publishable():
    assert not rule({'from': 'alice'}).publishable
    assert not rule({'archive': True}).publishable
    assert rule({'from': 'alice', 'archive': True}).publishable


# Test generating rulesets from complex nested objects

def test_ruleset_from_dict():
    rules = sorted(RuleSet.from_object(sample_rule('bill')))
    assert len(rules) == 1
    assert rules[0].flatten() == {
        'from': RuleCondition('from', 'bill@msft.com'),
        'shouldTrash': RuleAction('shouldTrash', 'true'),
    }


def test_ruleset_from_list():
    rules = sorted(RuleSet.from_object([sample_rule('bill'), sample_rule('steve')]))
    assert len(rules) == 2
    assert rules[0].flatten() == {
        'from': RuleCondition('from', 'bill@msft.com'),
        'shouldTrash': RuleAction('shouldTrash', 'true'),
    }
    assert rules[1].flatten() == {
        'from': RuleCondition('from', 'steve@msft.com'),
        'shouldTrash': RuleAction('shouldTrash', 'true'),
    }


def test_nested_conditions():
    ruleset = RuleSet.from_object({
        'from': 'steve@aapl.com',
        'archive': True,
        'more': {
            'subject': 'stop ignoring me',
            'archive': False,
        }
    })
    assert len(ruleset) == 2
    assert sorted(ruleset)[0].flatten() == {
        'from': RuleCondition('from', 'steve@aapl.com'),
        'subject': RuleCondition('subject', '"stop ignoring me"'),
        'shouldArchive': RuleAction('shouldArchive', 'false'),
    }
    assert sorted(ruleset)[1].flatten() == {
        'from': RuleCondition('from', 'steve@aapl.com'),
        'shouldArchive': RuleAction('shouldArchive', 'true'),
    }


def test_foreach():
    """
    Loop through each item in a list and create a rule from it.
    """
    ruleset = RuleSet.from_object({
        'for_each': ['steve', 'jony', 'tim'],
        'rule': {
            'from': '{item}@aapl.com',
            'star': True,
            'important': True,
            'more': [
                {'label': 'everyone', 'to': 'everyone@aapl.com'},
            ]
        }
    })
    assert sorted(rule.conditions for rule in ruleset) == [
        [RuleCondition(u'from', u'jony@aapl.com')],
        [RuleCondition(u'from', u'jony@aapl.com'), RuleCondition(u'to', u'everyone@aapl.com')],
        [RuleCondition(u'from', u'steve@aapl.com')],
        [RuleCondition(u'from', u'steve@aapl.com'), RuleCondition(u'to', u'everyone@aapl.com')],
        [RuleCondition(u'from', u'tim@aapl.com')],
        [RuleCondition(u'from', u'tim@aapl.com'), RuleCondition(u'to', u'everyone@aapl.com')],
    ]


def test_foreach_dict():
    """
    When the item in a for_each construct is a dict, format the rule
    using the dict's keys and values.
    """
    ruleset = RuleSet.from_object({
        'for_each': [
            {'team': 'retail', 'email': 'angela'},
            {'team': 'marketing', 'email': 'phil'},
            {'team': 'design', 'email': 'jony'},
        ],
        'rule': {
            'from': '{email}@aapl.com',
            'to': '{team}@aapl.com',
            'star': True,
        }
    })
    assert sorted(rule.conditions for rule in ruleset) == [
        [RuleCondition('from', 'angela@aapl.com'), RuleCondition('to', 'retail@aapl.com')],
        [RuleCondition('from', 'jony@aapl.com'), RuleCondition('to', 'design@aapl.com')],
        [RuleCondition('from', 'phil@aapl.com'), RuleCondition('to', 'marketing@aapl.com')],
    ]


def test_foreach_dict_within_nested_condition():
    """
    Make sure that key/value substitution works within nested conditions.
    """
    ruleset = RuleSet.from_object({
        'for_each': [
            {'team': 'retail'},
            {'team': 'marketing'},
            {'team': 'design'},
        ],
        'rule': {
            'has': {
                'any': [
                    'to:{team}@tsla.com',
                    'cc:{team}@tsla.com',
                    'bcc:{team}@tsla.com',
                ],
            },
            'star': True,
        }
    })
    assert sorted(rule.conditions for rule in ruleset) == [
        [RuleCondition(u'hasTheWord', u'(bcc:design@tsla.com OR cc:design@tsla.com OR to:design@tsla.com)')],
        [RuleCondition(u'hasTheWord', u'(bcc:marketing@tsla.com OR cc:marketing@tsla.com OR to:marketing@tsla.com)')],
        [RuleCondition(u'hasTheWord', u'(bcc:retail@tsla.com OR cc:retail@tsla.com OR to:retail@tsla.com)')],
    ]
