# Deployment, monitoring, and rollback

| Practice | Implementation and evidence |
| --- | --- |
| PW1 · Git | Feature branches, PRs and code review in repository history |
| PW2 · Flask | Three authenticated workspaces and a SQLite workflow |
| PW3 · Testing | Isolated SQLite tests via `make test` |
| PW4 · CI | GitHub Actions tests Python 3.9 and 3.12, lints Python, checks JavaScript, and runs a Docker smoke test |
| PW5 · Docker | Gunicorn image and Compose volume checked via `/health` |
| PW6 · CD | CI-gated publishing of `latest` and commit-SHA tags to GHCR on main |
| PW7 · Render | Docker Blueprint with automatic deployment after main branch checks |
| PW8 · Monitoring and rollback | Render logs and health checks, UptimeRobot setup, and rollback procedure below |

## Deploy

1. After merging the infrastructure, use Render **New → Blueprint** and connect this repository. Review the plan and apply the Blueprint.
2. Check that the assigned URL serves the login screen and that `/health` returns `{"status":"ok"}`. Complete a fictional handoff.
3. In GitHub Actions, open **Publish container** and verify the commit tag in GitHub Packages. Render builds the source from main for PW7.

The free Render service uses ephemeral storage. Use fictional data that can be recreated after a restart. Local Compose stores SQLite in a named volume. Hosted persistence requires a storage-backed service selected explicitly.

## Monitor and roll back

- In UptimeRobot create an HTTP(s) monitor for `https://<render-host>/health`, select your notification contact, and confirm the first successful check. In Render, **Events** shows deployments and **Logs** shows startup errors and HTTP access logs.
- To recover a failed deploy, choose the last healthy deployment in Render **Events** and use **Rollback**. Verify health, login and sample intake afterward. A code rollback does not restore the SQLite database.
- Check auto-deploy before enabling it again. Fix or revert the offending change through a PR before the next deploy.

Official references: [Render Blueprint](https://render.com/docs/blueprint-spec), [free plan limits](https://render.com/docs/free), [rollback](https://render.com/docs/rollbacks).
