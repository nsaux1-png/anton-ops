# Open questions

- [x] **What is on anton's 4 TB mirror?** Nothing. It's empty, now mounted at `/raiddrive` (2026-10-18).
- [x] **Name for 172.16.50.11:** `douglas1` (decided 2026-10-18; `douglas1_gpu` removed).
- [x] **What is `172.16.99.0/24` on douglas1?** The BMC's virtual USB network link (AMI "Virtual Ethernet"), internal to the server (2026-10-19).
- [x] **douglas1's `enp66s0f0np0` is down.** It's the second 10 Gb port, simply not cabled. Both douglas1 ports are 10 Gb; anton's are 1 Gb only (2026-10-19). See D4.
- [ ] **Grafana on anton:** version 10.2.6 is installed but disabled, and wasn't installed by this project. Use it for monitoring (plan section 13), or remove it and install it properly through Ansible? Found 2026-10-19.
- [ ] **Billing rates:** price per GPU-hour and CPU-hour, and whether memory is charged.
- [ ] **Account structure:** one Slurm account per customer? Per project within a customer?
- [ ] **User identity:** keep a managed `users.yml` (planned), or use a directory service such as FreeIPA later?
- [ ] **Exposure to the internet:** anton accepts SSH from public IPs. Check that password login is disabled for SSH and add fail2ban before customers are onboarded.
- [ ] **Remove `/etc/sudoers.d/90-papaya-temp`** from both machines when the build is done.
- [x] **GitLab:** gitlab.com, private project `nicolas478/anton-ops` (2026-10-18).
- [x] **Moved to GitHub:** private repo `nsaux1-png/anton-ops` (2026-10-19).
