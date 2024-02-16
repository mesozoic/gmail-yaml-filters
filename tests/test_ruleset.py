# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import date

import pytest

from gmail_yaml_filters.ruleset import (
    InvalidIdentifier,
    InvalidRuleType,
    RuleAction,
    RuleCondition,
    RuleSet,
)


def rule(rule_obj):
    return sorted(RuleSet.from_object(rule_obj))[0]


def _flat(rule_obj):
    return rule(rule_obj).flatten()


def sample_rule(name):
    return {
        "from": "{}@msft.com".format(name),
        "trash": True,
    }


def test_empty_ruleset():
    assert _flat({}) == {}


def test_invalid_rule_type():
    with pytest.raises(InvalidRuleType):
        _flat({"has": object()})


# Test how identifier_map and formatter_map operate


@pytest.mark.parametrize(
    "input,condition,value",
    [
        ({"has": "whatever"}, "has", "whatever"),
        ({"has": "drive"}, "has", "has:drive"),
        ({"labeled": "whatever"}, "has", "label:(whatever)"),
        ({"labeled": "-whatever"}, "doesNotHave", "label:(whatever)"),
        ({"is": "snoozed"}, "has", "is:(snoozed)"),
        ({"is": "-snoozed"}, "doesNotHave", "is:(snoozed)"),
        ({"after": date(2024, 2, 15)}, "has", "after:2024-02-15"),
        ({"before": date(2024, 2, 15)}, "has", "before:2024-02-15"),
        ({"has": {"any": ["one", "two", "three"]}}, "has", "(one OR three OR two)"),
        ({"has": {"all": ["one", "two", "three"]}}, "has", "(one AND three AND two)"),
        (
            {"has": {"not": {"all": ["one", "two", "three"]}}},
            "has",
            "-(one AND three AND two)",
        ),
    ],
)
def test_flattened_condition(input, condition, value):
    condition = f"{condition}TheWord"
    assert _flat(input) == {condition: RuleCondition(condition, value)}


def test_condition_invalid_keys():
    with pytest.raises(KeyError):
        _flat({"has": {"foo": "bar"}})


@pytest.mark.parametrize(
    "input,condition,value",
    [
        ({"archive": True}, "shouldArchive", "true"),
        ({"forward": "someone@example.com"}, "forwardTo", "someone@example.com"),
    ],
)
def test_flattened_action(input, condition, value):
    assert _flat(input) == {condition: RuleAction(condition, value)}


def test_publishable():
    assert not rule({"from": "alice"}).publishable
    assert not rule({"archive": True}).publishable
    assert rule({"from": "alice", "archive": True}).publishable


# Test generating rulesets from complex nested objects


def test_ruleset_from_dict():
    rules = sorted(RuleSet.from_object(sample_rule("bill")))
    assert len(rules) == 1
    assert rules[0].flatten() == {
        "from": RuleCondition("from", "bill@msft.com"),
        "shouldTrash": RuleAction("shouldTrash", "true"),
    }


def test_ruleset_from_list():
    rules = sorted(RuleSet.from_object([sample_rule("bill"), sample_rule("steve")]))
    assert len(rules) == 2
    assert rules[0].flatten() == {
        "from": RuleCondition("from", "bill@msft.com"),
        "shouldTrash": RuleAction("shouldTrash", "true"),
    }
    assert rules[1].flatten() == {
        "from": RuleCondition("from", "steve@msft.com"),
        "shouldTrash": RuleAction("shouldTrash", "true"),
    }


def test_invalid_ruleset_object():
    with pytest.raises(ValueError):
        RuleSet.from_object(object())


def test_nested_conditions():
    ruleset = RuleSet.from_object(
        {
            "from": "steve@aapl.com",
            "archive": True,
            "more": {
                "subject": "stop ignoring me",
                "archive": False,
            },
        }
    )
    assert len(ruleset) == 2
    assert sorted(ruleset)[0].flatten() == {
        "from": RuleCondition("from", "steve@aapl.com"),
        "subject": RuleCondition("subject", '"stop ignoring me"'),
        "shouldArchive": RuleAction("shouldArchive", "false"),
    }
    assert sorted(ruleset)[1].flatten() == {
        "from": RuleCondition("from", "steve@aapl.com"),
        "shouldArchive": RuleAction("shouldArchive", "true"),
    }


def test_foreach():
    """
    Loop through each item in a list and create a rule from it.
    """
    ruleset = RuleSet.from_object(
        {
            "for_each": ["steve", "jony", "tim"],
            "rule": {
                "from": "{item}@aapl.com",
                "star": True,
                "important": True,
                "more": [
                    {"label": "everyone", "to": "everyone@aapl.com"},
                ],
            },
        }
    )
    assert sorted(rule.conditions for rule in ruleset) == [
        [RuleCondition("from", "jony@aapl.com")],
        [
            RuleCondition("from", "jony@aapl.com"),
            RuleCondition("to", "everyone@aapl.com"),
        ],
        [RuleCondition("from", "steve@aapl.com")],
        [
            RuleCondition("from", "steve@aapl.com"),
            RuleCondition("to", "everyone@aapl.com"),
        ],
        [RuleCondition("from", "tim@aapl.com")],
        [
            RuleCondition("from", "tim@aapl.com"),
            RuleCondition("to", "everyone@aapl.com"),
        ],
    ]


def test_foreach_invalid_keys():
    """
    Test that invalid keys in a foreach will throw an error.
    """
    with pytest.raises(InvalidIdentifier):
        RuleSet.from_object(
            {
                "for_each": [],
                "rule": {},
                "some_invalid_key": "",
            }
        )


def test_foreach_dict():
    """
    When the item in a for_each construct is a dict, format the rule
    using the dict's keys and values.
    """
    ruleset = RuleSet.from_object(
        {
            "for_each": [
                {"team": "retail", "email": "angela"},
                {"team": "marketing", "email": "phil"},
                {"team": "design", "email": "jony"},
            ],
            "rule": {
                "from": "{email}@aapl.com",
                "to": "{team}@aapl.com",
                "star": True,
            },
        }
    )
    assert sorted(rule.conditions for rule in ruleset) == [
        [
            RuleCondition("from", "angela@aapl.com"),
            RuleCondition("to", "retail@aapl.com"),
        ],
        [
            RuleCondition("from", "jony@aapl.com"),
            RuleCondition("to", "design@aapl.com"),
        ],
        [
            RuleCondition("from", "phil@aapl.com"),
            RuleCondition("to", "marketing@aapl.com"),
        ],
    ]


def test_foreach_dict_within_nested_condition():
    """
    Make sure that key/value substitution works within nested conditions.
    """
    ruleset = RuleSet.from_object(
        {
            "for_each": [
                {"team": "retail"},
                {"team": "marketing"},
                {"team": "design"},
            ],
            "rule": {
                "has": {
                    "any": [
                        "to:{team}@tsla.com",
                        "cc:{team}@tsla.com",
                        "bcc:{team}@tsla.com",
                    ],
                },
                "star": True,
            },
        }
    )
    assert sorted(rule.conditions for rule in ruleset) == [
        [
            RuleCondition(
                "hasTheWord",
                "(bcc:design@tsla.com OR cc:design@tsla.com OR to:design@tsla.com)",
            )
        ],
        [
            RuleCondition(
                "hasTheWord",
                "(bcc:marketing@tsla.com OR cc:marketing@tsla.com OR to:marketing@tsla.com)",
            )
        ],
        [
            RuleCondition(
                "hasTheWord",
                "(bcc:retail@tsla.com OR cc:retail@tsla.com OR to:retail@tsla.com)",
            )
        ],
    ]
