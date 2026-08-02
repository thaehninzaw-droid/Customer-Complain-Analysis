# Getting the team onto one shared repo

## Why this matters (read this bit even if you're impatient)

Right now, code has been moving around as zip files in chat. The
risk isn't hypothetical: two people can end up editing the same file
without knowing it, and whoever sends their zip *second* silently
erases the first person's work - nobody finds out until it's too
late to recover it. A shared Git repo (hosted on GitHub) fixes this:
everyone's changes are tracked, nothing is silently lost, and you can
always see who changed what and roll back a mistake.

This project folder is already a fully-formed Git repo, staged and
ready for its first commit - you just need to point it at a real
GitHub repository.

## One-time setup (whoever does this becomes the repo owner)

**1. Create the GitHub repo**
Go to github.com/new, name it (e.g. `loopline`), keep it **private**
if the complaint data or anything sensitive will ever live in it,
and do **not** initialize it with a README (this folder already has
one - adding another would just conflict).

**2. Set your Git identity** (skip if already done on your machine)
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

**3. Make the first commit and push**
```bash
cd loopline
git commit -m "Initial commit: Loopline backend + frontend"
git branch -M main
git remote add origin https://github.com/<your-username>/loopline.git
git push -u origin main
```
(The files are already staged from setup - if `git commit` says
there's nothing to commit, run `git add -A` first.)

**4. Add the rest of the team**
GitHub repo → Settings → Collaborators → add each teammate's GitHub
username. Everyone else then just runs:
```bash
git clone https://github.com/<your-username>/loopline.git
```

## Workflow from here on

Given the team size and the deadline, keep this simple - don't
over-engineer the process itself:

1. **Before starting any change**, make sure you have the latest
   code: `git pull`
2. **Make a branch for what you're working on:**
   ```bash
   git checkout -b add-category-dropdown-fetch
   ```
   (short, descriptive name - what it does, not who's doing it)
3. **Commit as you go**, with messages that say *what* changed:
   ```bash
   git add -A
   git commit -m "Fetch categories from /categories instead of hardcoding options"
   ```
   A good commit message is a short sentence describing the change,
   as if finishing "This commit will...". Avoid "fixed stuff" or
   "update" - future-you (and your examiner, if they ever look) won't
   know what that means.
4. **Push your branch and open a Pull Request:**
   ```bash
   git push -u origin add-category-dropdown-fetch
   ```
   Then on GitHub, click "Compare & pull request." Even a 2-minute
   glance from one teammate before merging catches real mistakes -
   worth doing even under time pressure.
5. **Merge into `main`** once it looks good, then delete the branch.

## What never gets committed

Both `.gitignore` files already exclude these, but worth knowing why:
- `.env` - real credentials (MongoDB URI, future API keys) never
  belong in the repo, even a private one. `.env.example` (which *is*
  tracked) shows what variables are needed without the actual values.
- `venv/`, `__pycache__/` - regenerated automatically, just clutter.

## If two people edit the same file (merge conflicts)

This will happen eventually - it's normal, not a sign something went
wrong. Git will mark the conflicting section in the file with
`<<<<<<<` / `=======` / `>>>>>>>` markers; open the file, decide which
version (or a combination) is correct, delete the markers, then
`git add` and commit. If it looks confusing, it's fine to ask
whoever made the other change to sort it out together rather than
guessing.
