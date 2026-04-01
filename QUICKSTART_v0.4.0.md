# hbar-brain v0.4.0 Quick Deployment

## Step 0: Verify Server is Running

**On the server** (ssh hbar@91.99.158.48):
```bash
# Check what's listening on port 8010
sudo ss -ltnp | grep ':8010'

# Test locally on the server
curl -sS http://127.0.0.1:8010/health
```

**From your dev machine**:
```bash
# Test remote reachability
curl -sS http://91.99.158.48:8010/health | jq .
```

If these fail, the service isn't running or isn't bound correctly. Fix that first!

## Step 1: Deploy Server Code

**On your dev machine** (already done):
```bash
cd /home/zyro/CascadeProjects/systems/hbar-brain-Pulled/hbar-brain
git status  # Verify changes to api/main.py
git add api/main.py test_v0.4.0_smoke.py RELEASE_NOTES_v0.4.0.md DEPLOYMENT_v0.4.0.md
git commit -m "v0.4.0: add help, version, audit tail commands + fix DB health"
git push
```

**On the server**:
```bash
ssh hbar@91.99.158.48
cd /path/to/hbar-brain  # wherever your repo is
git pull

# Restart (choose your method):
# If systemd:
sudo systemctl restart hbar-brain
sudo systemctl status hbar-brain --no-pager

# If docker:
docker compose up -d --build
docker compose logs -n 200 -f

# If manual:
pkill -f "python.*main.py"
nohup python api/main.py > server.log 2>&1 &
```

## Step 2: Test New Commands

**From your dev machine**:
```bash
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console

# Test version
python console.py --remote http://91.99.158.48:8010 "version"

# Test help
python console.py --remote http://91.99.158.48:8010 "help"

# Test audit tail
python console.py --remote http://91.99.158.48:8010 "audit tail 25"
```

## What Changed in v0.4.0

- ✅ Added `help`, `version`, `audit tail N` commands
- ✅ Fixed DB health check (uses `SELECT 1` now)
- ✅ All security invariants maintained
- ✅ No breaking changes

See `RELEASE_NOTES_v0.4.0.md` for full details.
