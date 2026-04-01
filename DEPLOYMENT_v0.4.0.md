# hbar-brain v0.4.0 Deployment Guide

## Pre-Deployment: Remote Connectivity Test

Before deploying, verify that your remote server is accessible:

```bash
# Test basic health endpoint
curl -sS http://91.99.158.48:8010/health | jq .

# Test from console (should PROPOSE and STOP - no auto-confirm on remote)
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console
python console.py --remote http://91.99.158.48:8010 "status"
```

**Expected**: You should see a PROPOSED status with a confirmation token. The command should NOT auto-confirm for remote servers.

## Server Deployment

### Step 1: SSH into the remote server

```bash
ssh hbar@91.99.158.48
```

### Step 2: Navigate to the hbar-brain directory

```bash
cd /path/to/hbar-brain  # Adjust to your actual path
```

### Step 3: Backup current version (optional but recommended)

```bash
cp api/main.py api/main.py.backup.v0.3.x
```

### Step 4: Update the server code

Option A - If using git:
```bash
git pull origin main
```

Option B - Manual copy from local machine:
```bash
# On your local machine
scp /home/zyro/CascadeProjects/systems/hbar-brain-Pulled/hbar-brain/api/main.py \
    hbar@91.99.158.48:/path/to/hbar-brain/api/main.py
```

### Step 5: Verify the changes

```bash
# Check that version constant is updated
grep "HBAR_BRAIN_VERSION" api/main.py
# Should show: HBAR_BRAIN_VERSION = "0.4.0"
```

### Step 6: Restart the server

Option A - If using systemd:
```bash
sudo systemctl restart hbar-brain
sudo systemctl status hbar-brain
```

Option B - If running manually:
```bash
# Find and kill the existing process
ps aux | grep "python.*main.py"
pkill -f "python.*main.py"

# Start the new version
cd /path/to/hbar-brain
nohup python api/main.py > server.log 2>&1 &

# Or if using uvicorn
nohup uvicorn api.main:app --host 0.0.0.0 --port 8010 > server.log 2>&1 &
```

### Step 7: Verify deployment

```bash
# Test health endpoint
curl -sS http://localhost:8010/health | jq .

# Test version command (from your local machine)
# This will PROPOSE the command - you'll need to confirm it
curl -X POST http://91.99.158.48:8010/v1/brain/command \
  -H "Content-Type: application/json" \
  -d '{"command": "version", "client_id": "deployment_test"}' | jq .
```

## Console Client Deployment

### Step 1: Update console code

```bash
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console

# If using git
git pull origin main

# Verify changes
grep -A 5 "Special formatting for help command" console.py
```

### Step 2: Test locally (optional)

```bash
# Test against local test server first
python console.py --remote http://localhost:8010 "help"
```

### Step 3: Test against remote server

```bash
# Run integration tests
./test_v0.4.0_integration.sh http://91.99.158.48:8010
```

## Post-Deployment Verification

### 1. Test new commands

```bash
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console

# Test help
python console.py --remote http://91.99.158.48:8010 "help"

# Test version
python console.py --remote http://91.99.158.48:8010 "version"

# Test audit tail
python console.py --remote http://91.99.158.48:8010 "audit tail 25"
```

### 2. Verify existing commands still work

```bash
# Test health
python console.py --remote http://91.99.158.48:8010 "health"

# Test whoami
python console.py --remote http://91.99.158.48:8010 "whoami"

# Test status
python console.py --remote http://91.99.158.48:8010 "status"
```

### 3. Verify security controls

```bash
# Verify that remote commands do NOT auto-confirm
python console.py --remote http://91.99.158.48:8010 "version" | grep PROPOSED
# Should show PROPOSED status

# Verify that localhost CAN auto-confirm (if you have a local server)
python console.py --remote http://localhost:8010 "version" | grep CONFIRMED
# Should show CONFIRMED status (auto-confirmed)
```

### 4. Run smoke tests (if server is local or test environment)

```bash
cd /home/zyro/CascadeProjects/systems/hbar-brain-Pulled/hbar-brain

# Run against local test server
python test_v0.4.0_smoke.py
```

## Rollback Procedure (if needed)

If something goes wrong, you can rollback to the previous version:

### On the server:

```bash
ssh hbar@91.99.158.48
cd /path/to/hbar-brain

# Restore backup
cp api/main.py.backup.v0.3.x api/main.py

# Restart server
sudo systemctl restart hbar-brain
# OR
pkill -f "python.*main.py"
nohup python api/main.py > server.log 2>&1 &
```

### On the console:

```bash
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console

# If using git
git checkout HEAD~1 console.py
```

## Troubleshooting

### Server not responding

```bash
# Check if server is running
ssh hbar@91.99.158.48
ps aux | grep "python.*main.py"

# Check server logs
tail -f /path/to/hbar-brain/server.log

# Check port is listening
netstat -tlnp | grep 8010
```

### Commands returning errors

```bash
# Check audit log for details
ssh hbar@91.99.158.48
tail -f /path/to/hbar-brain/ops/audit/command_audit.jsonl
```

### Database health showing error

```bash
# Check DATABASE_URL environment variable
ssh hbar@91.99.158.48
echo $DATABASE_URL

# Test database connection manually
psql $DATABASE_URL -c "SELECT 1;"
```

## Success Criteria

✓ Server responds to `/health` endpoint  
✓ `version` command returns "0.4.0"  
✓ `help` command lists all available commands  
✓ `audit tail` command returns audit entries  
✓ DB health shows "healthy" or meaningful error  
✓ Remote commands do NOT auto-confirm  
✓ Existing commands (health, whoami, status) still work  
✓ PROPOSE/CONFIRM workflow still enforced  

## Support

If you encounter issues:

1. Check the audit log: `/path/to/hbar-brain/ops/audit/command_audit.jsonl`
2. Check server logs: `/path/to/hbar-brain/server.log`
3. Verify network connectivity: `curl http://91.99.158.48:8010/health`
4. Review release notes: `RELEASE_NOTES_v0.4.0.md`
