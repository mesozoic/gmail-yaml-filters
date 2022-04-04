from gmail_yaml_filters import upload
from gmail_yaml_filters.ruleset import RuleSet


empty_ruleset = RuleSet.from_object([])
dummy_ruleset = RuleSet.from_object([
    {'from': 'anyone', 'label': 'itest-dummy-label'}
])


def test_create_labels(gmail, capsys):
    upload.upload_ruleset(dummy_ruleset, service=gmail, dry_run=True)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert 'Creating label itest-dummy-label' in captured.err
