# CI template

`ci-tests.yml` runs the studio unit/integration suite on Python 3.12 without model credentials or downloaded material archives.

The initial publishing account has repository access but lacks the OAuth `workflow` scope, so the template is not installed as an active GitHub Actions workflow. To enable it later, use a GitHub login with workflow-write permission and copy this file to `.github/workflows/tests.yml`, then commit and push.
