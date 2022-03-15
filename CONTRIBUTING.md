# Contributing

Thanks for spending time making this code better! I really appreciate it.
Below are a few notes for how you can help me keep this project in tip top shape.

## Reporting a problem

Please [open an issue](https://github.com/mesozoic/gmail-yaml-filters/issues/new)
with a sample configuration file and steps to reproduce the problem (or, if not
possible, a terminal log of what happened when you ran the command).

## Suggesting a feature

Please [open an issue](https://github.com/mesozoic/gmail-yaml-filters/issues/new)
with the "enhancement" tag and describe what you're trying to accomplish. Sometimes
there will be other ways of getting it done that don't involve changing code and I'll
be happy to suggest them.

## Submitting a patch

Pull requests are welcome! Please keep the following guidelines in mind:

1. Fix only one issue at a time. Pull requests which attempt to fix multiple bugs
   (or which combine bug fixes and enhancements) are a lot harder to read, review,
   and reason about.

2. Include tests for any bugs or new features. Without regression tests, we have
   no way of knowing if your bug just pops back up again, or if some future change
   breaks that cool new feature you've added. While there are some doctests in
   the codebase, I will prefer adding to the `tests` submodule going forward.

3. Ensure your build passes, both locally (run `tox`) and on
   [GitHub Actions](https://github.com/mesozoic/gmail-yaml-filters/actions/workflows/tests.yml).
   Please do not ignore any failures you see from checkers or pre-commit hooks.

4. Update the CHANGELOG and README with any relevant information about what you've done.

5. Please do not submit patches which fix whitespace or other cosmetic issues unless that
   section of code is relevant to your bugfix or feature.

## Other reading

[Contributing to Open Source Projects](contribution-guide.org) is a useful collection
of best practices collected from a variety of (much larger) projects around the world.
