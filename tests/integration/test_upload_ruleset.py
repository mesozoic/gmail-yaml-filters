from gmail_yaml_filters import upload
from gmail_yaml_filters.ruleset import RuleSet

empty_ruleset = RuleSet.from_object([])
dummy_ruleset = RuleSet.from_object([{"from": "anyone", "archive": True}])


create_tag = "Creating"
delete_tag = "Deleting"


def test_empty_ruleset(gmail, capsys):
    """
    Test that our account starts empty.
    """
    upload.upload_ruleset(empty_ruleset, service=gmail, dry_run=True)
    upload.prune_filters_not_in_ruleset(empty_ruleset, service=gmail, dry_run=True)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_upload_dry_run(gmail, capsys):
    """
    Test that the dry run parameter prevents us from creating filters.
    """
    upload.upload_ruleset(dummy_ruleset, service=gmail, dry_run=True)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count(create_tag) == 1
    assert captured.err.count(delete_tag) == 0
    test_empty_ruleset(gmail, capsys)


def test_upload_and_delete(gmail, capsys):
    """
    Test actually uploading a rule and deleting it.
    """
    upload.upload_ruleset(dummy_ruleset, service=gmail, dry_run=False)
    upload.prune_filters_not_in_ruleset(empty_ruleset, service=gmail, dry_run=False)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count(create_tag) == 1
    assert captured.err.count(delete_tag) == 1
