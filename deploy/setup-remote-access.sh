#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing sshd hardening config"
sudo cp /home/jbaycroft/TheBurrow/pensieve-sms/deploy/99-pensieve-hardened.conf \
        /etc/ssh/sshd_config.d/99-pensieve-hardened.conf

echo "==> Enabling sshd"
sudo systemctl enable --now sshd

echo "==> Adding SSH ingress to Cloudflare tunnel"
sudo sed -i '/^  - service: http_status:404/i\  - hostname: ssh.theburrow.house\n    service: ssh://127.0.0.1:22\n' \
    /home/jbaycroft/.cloudflared/config.yml

echo "==> Adding DNS route (idempotent)"
cloudflared tunnel route dns theburrow ssh.theburrow.house || true

echo "==> Restarting tunnel"
sudo systemctl restart pensieve-tunnel

echo "==> Installing auto-sync systemd units"
sudo cp /home/jbaycroft/TheBurrow/pensieve-sms/deploy/pensieve-sync.service \
        /etc/systemd/system/pensieve-sync.service
sudo cp /home/jbaycroft/TheBurrow/pensieve-sms/deploy/pensieve-sync.timer \
        /etc/systemd/system/pensieve-sync.timer

echo "==> Installing sudoers rule for passwordless flask restart"
sudo cp /home/jbaycroft/TheBurrow/pensieve-sms/deploy/pensieve-sudoers \
        /etc/sudoers.d/pensieve
sudo chmod 440 /etc/sudoers.d/pensieve
sudo visudo -cf /etc/sudoers.d/pensieve

echo "==> Enabling auto-sync timer"
sudo systemctl daemon-reload
sudo systemctl enable --now pensieve-sync.timer

echo ""
echo "=== Verification ==="
echo "SSH:    $(systemctl is-active sshd)"
echo "Tunnel: $(systemctl is-active pensieve-tunnel)"
echo ""
echo "Tunnel config:"
cat /home/jbaycroft/.cloudflared/config.yml
echo ""
echo "Sync timer:"
systemctl list-timers pensieve-sync.timer --no-pager
echo ""
echo "==> Done. Now:"
echo "  1. Add Cloudflare Access policy for ssh.theburrow.house"
echo "  2. Add your travel device SSH key to ~/.ssh/authorized_keys"
