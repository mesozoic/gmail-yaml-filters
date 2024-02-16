from io import StringIO

import pytest

from gmail_yaml_filters.main import load_data_from_args


@pytest.fixture
def tmpconfig(tmp_path):
    fpath = tmp_path / "tmp.yaml"
    fpath.write_text(
        """
        - has: attachment
          archive: true
        - to: alice
          label: foo
        """
    )
    return fpath


def test_delete_requires_no_file():
    assert load_data_from_args("delete", None) == []


def test_load_data_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", StringIO("foo: bar"))
    assert load_data_from_args("upload", "-") == [{"foo": "bar"}]


def test_load_data_from_filename(tmpconfig):
    assert load_data_from_args("upload", tmpconfig) == [
        {
            "has": "attachment",
            "archive": True,
        },
        {
            "to": "alice",
            "label": "foo",
        },
    ]


def test_load_data_fails_without_filename():
    with pytest.raises(ValueError):
        load_data_from_args("upload", "")
