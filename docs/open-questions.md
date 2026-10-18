# Open questions

- [x] **What is on anton's 4 TB mirror?** Nothing. It's empty, now mounted at `/raiddrive` (2026-10-18).
- [ ] **douglas1's entry in anton's `/etc/hosts` reads `172.16.50.11 douglas1_gpu`.** It read `douglas1` earlier on 2026-10-17. Who changed it, and which name do we want? Underscores aren't valid in hostnames, so `douglas1-gpu` is safer if a second name is wanted. Ansible will manage `/etc/hosts` from now on.
- [ ] **What is `172.16.99.0/24` on douglas1** (`enp72s0f3u2u3c2`, a USB network interface)? It may be the BMC's host interface.
- [ ] **douglas1's `enp66s0f0np0` is down.** Is it meant to be cabled, for example as a faster cluster link?
- [ ] **Billing rates:** price per GPU-hour and CPU-hour, and whether memory is charged.
- [ ] **Account structure:** one Slurm account per customer? Per project within a customer?
- [ ] **User identity:** keep a managed `users.yml` (planned), or use a directory service such as FreeIPA later?
- [ ] **Exposure to the internet:** anton accepts SSH from public IPs. Check that password login is disabled for SSH and add fail2ban before customers are onboarded.
- [ ] **Remove `/etc/sudoers.d/90-papaya-temp`** from both machines when the build is done.
- [ ] **GitLab:** gitlab.com or a self-hosted server? Which group or project?
