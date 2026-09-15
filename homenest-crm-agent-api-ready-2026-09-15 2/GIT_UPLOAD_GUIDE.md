# Git upload guide

This folder is intentionally separated from the earlier HomeNest project. It contains source files, tests, the Olist demo snapshot and configuration. Generated dependencies and build output are excluded.

## Add it to the team repository

Create a feature branch in your local clone of the team repository:

```bash
git switch -c feature/crm-service-recovery-agent
```

Copy this folder into the team repository, for example under `apps/homenest-crm-agent`, then run:

```bash
git add apps/homenest-crm-agent
git commit -m "feat: add CRM service recovery agent"
git push -u origin feature/crm-service-recovery-agent
```

The module `.gitignore` explicitly keeps `README.md` and this guide because the
team repository currently ignores nested Markdown files. Before committing,
confirm that `.env.local`, `node_modules`, `.next`, `.vinext`, `dist`, `.cache`
and `.wrangler` do not appear in the change list.

After cloning, the relevant structure should be:

```text
Show-me-your-agent-Token-Tricksters/
  apps/
    homenest-crm-agent/
      app/
      components/
      data/
      lib/
      openapi/
      tests/
      package.json
```

Open a Pull Request from the feature branch into `main`.

## Publish it as a standalone repository

```bash
git init
git add .
git commit -m "Initial HomeNest CRM service recovery agent"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Do not add `.env.local` or an API key to Git.
