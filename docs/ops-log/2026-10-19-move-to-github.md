# 2026-10-19: Repo moved from GitLab to GitHub; GitLab removed from anton

## Why
The user prefers GitHub, account @nsaux1-png.

## Done
By Claude Code (a session on anton as papaya). The user did the GitHub web steps.

1. Checked GitHub's SSH host key against GitHub's published fingerprint (`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`), then added it to `~/.ssh/known_hosts`.
2. Created a key only for GitHub, and added it to `~/.ssh/config`:
   ```
   ssh-keygen -q -t ed25519 -N '' -C papaya@anton-github -f ~/.ssh/id_ed25519_github
   ```
   ```
   Host github.com
       User git
       IdentityFile ~/.ssh/id_ed25519_github
       IdentitiesOnly yes
   ```
3. **User:** created the empty private repo `nsaux1-png/anton-ops` and added the public key as a deploy key with write access (repo Settings → Deploy keys).
4. Switched the remote and pushed the full history:
   ```
   git -C /home/papaya/cluster remote set-url origin git@github.com:nsaux1-png/anton-ops.git
   git -C /home/papaya/cluster push -u origin main
   ```
5. Claude Code's auto mode blocked the push. The user approved two allow rules in `~/.claude/settings.json`: `Bash(git -C /home/papaya/cluster push *)` and `Bash(git -C /home/papaya/cluster commit *)`.
6. Updated the README, plan, decision log, open questions, to-do list and the post-commit hook comment to point at GitHub.
7. Removed GitLab from anton:
   - deleted `~/.ssh/id_ed25519_gitlab` and `~/.ssh/id_ed25519_gitlab.pub`
   - removed the `Host gitlab.com` block from `~/.ssh/config`
   - deleted the `gitlab.com` lines from `~/.ssh/known_hosts` and `~/.ssh/known_hosts.old`

## Verified
- `ssh -T git@github.com` answers `Hi nsaux1-png/anton-ops!`. The deploy key works and only covers this one repo.
- After the first commit, `git ls-remote origin` showed the same `main` as local `HEAD` (`06855f6`).
- The post-commit hook printed `pushed main to origin` for every later commit.
- Nothing under `~/.ssh`, `~/.gitconfig` or `/etc` refers to GitLab any more, except `/etc/grafana/grafana.ini`. Its GitLab login section is the package default and is commented out.

## Follow-ups
- **User:** archive the GitLab project `nicolas478/anton-ops` and delete anton's old key from the GitLab account. The private half is gone, so the key can't be used.
