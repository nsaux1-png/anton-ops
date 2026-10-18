# 2026-10-17: Head node renamed from douglas1 to anton

## Problem
The head node (192.168.5.200 / 172.16.50.1) reported its hostname as `douglas1`, but it is meant to be **anton**. The real douglas1 is the GPU machine at 172.16.50.11. Nothing on the head node mentioned "anton".

## Found
- `/etc/hostname` and `hostnamectl`: `douglas1`.
- `/etc/hosts` had `172.16.50.11 douglas1`, which was correct for the other machine.
- The 4 TB RAID1 array on the head node is labeled `douglas1:0`, so the wrong name dates from the original install.

## Done (by papaya, in an SSH terminal on the head node)
```
sudo cp /etc/hosts /etc/hosts.bak
sudo hostnamectl set-hostname anton
echo "172.16.50.1 anton" | sudo tee -a /etc/hosts
```

## Verified
- `hostname`, `/etc/hostname` and `hostnamectl` all report `anton`.
- `getent ahostsv4 anton` returns 172.16.50.1.
- IP addresses unchanged: `eno1` 192.168.5.200, `eno2` 172.16.50.1.

## Follow-ups
- `/etc/hosts` now has `172.16.50.11 douglas1_gpu` instead of `douglas1`. This edit was made before the backup was taken and isn't explained; see `open-questions.md`.
- The SSH connection list on operators' laptops should name 192.168.5.200 `anton`.

## Lesson
`sudo` doesn't work from Claude Code's `!` prefix, because there's no terminal to read the password from. Run sudo commands in a normal SSH shell.
