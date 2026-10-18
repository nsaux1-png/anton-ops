# 2026-10-17: SSH access from anton to douglas1

## Done
- An ed25519 key without a passphrase was created on anton for papaya: `~/.ssh/id_ed25519`, comment `papaya@anton`.
- Its public key was appended to `~papaya/.ssh/authorized_keys` on douglas1 (by papaya, in a douglas1 session):
  ```
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL1u+FHTLP3iFQFMw3vgFwrriZe1lzw8fDITswtjX4SY papaya@anton" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
  ```

## Verified
`ssh -o BatchMode=yes papaya@172.16.50.11 hostname` from anton returns `douglas1`.

## Notes
- sudo on douglas1 still needs a password.
- To revoke this access, run on douglas1: `sed -i '/papaya@anton/d' ~/.ssh/authorized_keys`
- Ansible will take over node access. This key may be replaced by a dedicated automation key.
