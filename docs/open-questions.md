# Open questions

- [x] **What is on anton's 4 TB mirror?** Nothing. It's empty, now mounted at `/raiddrive` (2026-10-18).
- [x] **Name for 172.16.50.11:** `douglas1` (decided 2026-10-18; `douglas1_gpu` removed).
- [ ] **What is `172.16.99.0/24` on douglas1** (`enp72s0f3u2u3c2`, a USB network interface)? It may be the BMC's host interface.
- [ ] **douglas1's `enp66s0f0np0` is down.** Is it meant to be cabled, for example as a faster cluster link?
- [ ] **Billing rates:** price per GPU-hour and CPU-hour, and whether memory is charged.
- [ ] **Account structure:** one Slurm account per customer? Per project within a customer?
- [ ] **User identity:** keep a managed `users.yml` (planned), or use a directory service such as FreeIPA later?
- [ ] **Exposure to the internet:** anton accepts SSH from public IPs. Check that password login is disabled for SSH and add fail2ban before customers are onboarded.
- [ ] **Remove `/etc/sudoers.d/90-papaya-temp`** from both machines when the build is done.
- [x] **GitLab:** gitlab.com, private project `nicolas478/anton-ops` (2026-10-18).
- [x] **Moved to GitHub:** private repo `nsaux1-png/anton-ops` (2026-10-19).
