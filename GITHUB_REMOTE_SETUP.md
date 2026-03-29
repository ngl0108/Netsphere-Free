# GitHub Remote Setup

Suggested repository:

- name: `Netsphere-Free`
- visibility: `public`

## Option 1: add remote after the GitHub repo already exists

```powershell
git remote add origin https://github.com/<your-account-or-org>/Netsphere-Free.git
git push -u origin main
```

## Option 2: create with GitHub CLI

```powershell
gh repo create Netsphere-Free --public --source=. --remote=origin --push
```
