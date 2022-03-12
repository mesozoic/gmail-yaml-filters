# 0.9.6

* Fix #33 (implement smart labels as `categorize` action and remove documentation about CATEGORY_* labels that do not place emails into the tab categories.

# 0.9.5

* Fix #28 (pruning a filter with no actions would cause a crash)

# 0.9.4

* Fix #23 (no such file or directory `client_secret.json` when running locally)

# 0.9.3

* Added better `--help` strings and mention `client_secret.json` in README
* Moved RuleSet and related classes/functions into its own module

# 0.9.2

* Fix #7 by allowing actions with no conditions except for in nested rules

# 0.9.1

* Fix #17 (include XML declaration at top of file)

# 0.9

* Add support for a number of Gmail search operators
* Add support for `forward:` action

# 0.8.1

* Fix #5 (crash on an existing Gmail filter with no actions)

# 0.8

* Support and test Python 3.6 and Python 3.7

# 0.7.4

* Explicitly include `oauth2client` in library dependencies.
* Support `has: attachment` and `has_attachment: true` as rule conditions.

# 0.7.2

Support Unicode labels in --dry-run mode

# 0.7.1

Fix a bug where --prune or --sync would create labels even in --dry-run

# 0.7

Allow dicts in `for_each` with keys used in rule strings

# 0.6.2

Fixed #3 (crash on `--upload` when a user had no existing filters)

# 0.6.1

Fixed a bug that broke `--prune` as a standalone command.

# 0.6

* Added `--prune-labels` action to remove unused labels. This action also supports
  `--only-matching REGEX` to limit the pruning behavior and `--ignore-errors` for when
  Google's API times out or returns a 404.

# 0.5.1

* Added `--dry-run` flag for the cautious souls out there

# 0.4

* Added direct interaction with Gmail API (`--upload`, `--prune`, and `--sync`)
* Added support for Travis-CI

# 0.2

* This was the first version released to PyPI.
