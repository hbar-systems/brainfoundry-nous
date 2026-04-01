# NodeOS Authority Service - Integration Guide

## Overview

NodeOS has been added as a new authority service to the hbar-brain-lyra stack. It enforces memory and loop permit authority for all agents in the system.

## What Was Added

### New Files

```
nodeos/
├── main.py                 # FastAPI application (500+ lines)
├── Dockerfile             # Container definition
├── requirements.txt       # Python dependencies
├── brain_identity.yaml    # NodeOS identity
├── README.md             # Service documentation
└── test_nodeos.sh        # Test script

ui/pages/api/nodeos/
└── [...path].js          # Next.js proxy for browser access
```

### Modified Files

- `docker-compose.yml` - Added nodeos service (internal only, no public port)
- `docker-compose.dev.yml` - Added nodeos service (port 8011 exposed for testing)
- `docker-compose.minimal.yml` - Added nodeos service (port 8001 exposed)

## Architecture Decision: Option A

**We implemented Option A**: Browser-facing `/api/nodeos/*` routes in Next.js.

### Why Option A?

1. **Existing Pattern**: The repo already uses Next.js API routes (see `ui/pages/api/bf/[...path].js`)
2. **Security**: NodeOS is internal-only on docker network
3. **Simplicity**: No need for additional Caddy proxy configuration
4. **Consistency**: Matches existing `ui/pages/api/health.js` pattern

### How It Works

```
Browser → Next.js UI (port 3010)
         ↓
         /api/nodeos/v1/loops/request
         ↓
         ui/pages/api/nodeos/[...path].js (proxy)
         ↓
         http://nodeos:8001/v1/loops/request (internal)
         ↓
         NodeOS Service
```

## Service Configuration

### Development Mode

```yaml
nodeos:
  build: ./nodeos
  ports:
    - "8011:8001"  # Exposed for direct curl testing
  environment:
    - NODEOS_HMAC_SECRET=dev-secret-change-in-production
    - NODEOS_DB_PATH=/data/nodeos.db
  volumes:
    - nodeos_dev_data:/data
  networks:
    - llm-network
```

### Production Mode

```yaml
nodeos:
  build: ./nodeos
  # No public port - internal only
  environment:
    - NODEOS_HMAC_SECRET=${NODEOS_HMAC_SECRET:-change-this-in-production}
    - NODEOS_DB_PATH=/data/nodeos.db
  volumes:
    - nodeos_data:/data
  networks:
    - llm-network
```

## Starting the Stack

### Development Mode (Recommended for Testing)

```bash
cd /home/zyro/hbar/brains/hbar-brain-lyra

# Build and start all services
docker compose -f docker-compose.dev.yml up -d

# Check service status
docker compose -f docker-compose.dev.yml ps

# View NodeOS logs
docker compose -f docker-compose.dev.yml logs -f nodeos
```

### Production Mode

```bash
cd /home/zyro/hbar/brains/hbar-brain-lyra

# Set HMAC secret (important!)
export NODEOS_HMAC_SECRET="your-secure-secret-here"

# Build and start
docker compose up -d

# Check status
docker compose ps
```

## Testing NodeOS

### Option 1: Direct Testing (Dev Mode Only)

When running in dev mode, NodeOS is exposed on port 8011:

```bash
# Test identity
curl http://localhost:8011/v1/identity

# Test health
curl http://localhost:8011/health

# Run full test suite
cd /home/zyro/hbar/brains/hbar-brain-lyra/nodeos
./test_nodeos.sh
```

### Option 2: Via Next.js Proxy (All Modes)

Access through the UI proxy (works in all modes):

```bash
# Test identity via proxy
curl http://localhost:3010/api/nodeos/v1/identity

# Request a loop permit via proxy
curl -X POST http://localhost:3010/api/nodeos/v1/loops/request \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "lyra.v1",
    "purpose": "Generate music captions",
    "max_iterations": 10,
    "duration_minutes": 30
  }'
```

### Option 3: From Browser Console

```javascript
// Request a loop permit
const response = await fetch('/api/nodeos/v1/loops/request', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    agent_id: 'lyra.v1',
    purpose: 'Generate music captions',
    max_iterations: 10,
    duration_minutes: 30
  })
});
const data = await response.json();
console.log('Permit:', data);

// View audit events
const audit = await fetch('/api/nodeos/v1/audit/events?limit=10');
const events = await audit.json();
console.log('Audit events:', events);
```

## Quick Test Commands

```bash
# 1. Start the stack
cd /home/zyro/hbar/brains/hbar-brain-lyra
docker compose -f docker-compose.dev.yml up -d

# 2. Wait for services to be ready (check logs)
docker compose -f docker-compose.dev.yml logs -f nodeos
# Press Ctrl+C when you see "Application startup complete"

# 3. Test NodeOS identity
curl http://localhost:8011/v1/identity | jq

# Expected output:
# {
#   "brain_id": "system.ops.nodeos.v1",
#   "display_name": "NodeOS (authority)",
#   "lineage": "system",
#   "domain": "ops",
#   "role": "authority",
#   "model": null,
#   "tags": ["system", "ops", "authority", "memory", "loops"]
# }

# 4. Request a loop permit
curl -X POST http://localhost:8011/v1/loops/request \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "lyra.v1",
    "purpose": "Test loop",
    "max_iterations": 5
  }' | jq

# 5. View audit events
curl http://localhost:8011/v1/audit/events | jq

# 6. Run full test suite
cd nodeos
./test_nodeos.sh
```

## Verification Checklist

- [ ] NodeOS container is running: `docker compose -f docker-compose.dev.yml ps`
- [ ] Identity endpoint works: `curl http://localhost:8011/v1/identity`
- [ ] Health check passes: `curl http://localhost:8011/health`
- [ ] Can request loop permit: `curl -X POST http://localhost:8011/v1/loops/request ...`
- [ ] Can propose memory: `curl -X POST http://localhost:8011/v1/memory/propose ...`
- [ ] Audit events are logged: `curl http://localhost:8011/v1/audit/events`
- [ ] Next.js proxy works: `curl http://localhost:3010/api/nodeos/v1/identity`
- [ ] Database persists: Check `/data/nodeos.db` in container

## Database Access

```bash
# Access SQLite database
docker compose -f docker-compose.dev.yml exec nodeos sqlite3 /data/nodeos.db

# Example queries:
sqlite> .tables
sqlite> SELECT * FROM loop_permits;
sqlite> SELECT * FROM memory_proposals;
sqlite> SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT 10;
sqlite> .quit
```

## Integration with Lyra Brain

The Lyra brain (or any agent) can now:

1. **Request autonomy** before starting a loop:
   ```python
   response = requests.post('http://nodeos:8001/v1/loops/request', json={
       'agent_id': 'hbar.music.lyra.v1',
       'purpose': 'Generate 10 music captions',
       'max_iterations': 10,
       'duration_minutes': 30
   })
   permit = response.json()
   permit_token = permit['permit_token']
   ```

2. **Propose memories** instead of directly writing:
   ```python
   response = requests.post('http://nodeos:8001/v1/memory/propose', json={
       'agent_id': 'hbar.music.lyra.v1',
       'memory_type': 'preference',
       'content': 'User prefers concise captions',
       'metadata': {'confidence': 0.95}
   })
   # Status will be PENDING until NodeOS approves
   ```

3. **Revoke permits** when done:
   ```python
   requests.post('http://nodeos:8001/v1/loops/revoke', json={
       'permit_token': permit_token,
       'agent_id': 'hbar.music.lyra.v1',
       'reason': 'Task completed successfully'
   })
   ```

## Security Notes

### Phase 1 (Current)

- HMAC-signed permit tokens
- SQLite database with volume persistence
- No authentication on memory decision endpoints (admin-only in phase 2)
- Internal-only service (no direct browser access in production)

### Phase 2 (Future)

- Admin authentication for `/v1/memory/{id}/decide`
- Token encryption
- PostgreSQL migration option
- Automatic permit expiration
- Webhook notifications

## Troubleshooting

### NodeOS container won't start

```bash
# Check logs
docker compose -f docker-compose.dev.yml logs nodeos

# Rebuild
docker compose -f docker-compose.dev.yml build --no-cache nodeos
docker compose -f docker-compose.dev.yml up -d nodeos
```

### Can't access NodeOS from browser

- Check UI container has `NODEOS_INTERNAL_URL` env var
- Verify Next.js proxy file exists: `ui/pages/api/nodeos/[...path].js`
- Check UI logs: `docker compose -f docker-compose.dev.yml logs ui`

### Database errors

```bash
# Reset database (WARNING: deletes all data)
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
```

### Port conflicts

If port 8011 is in use, edit `docker-compose.dev.yml`:
```yaml
nodeos:
  ports:
    - "8012:8001"  # Use different port
```

## Next Steps

1. **Test the integration** using the commands above
2. **Integrate with Lyra** brain to use loop permits
3. **Add UI components** to display permits and memory proposals
4. **Implement Phase 2 features** (admin auth, auto-expiration, etc.)

## Files Summary

| File | Purpose | Lines |
|------|---------|-------|
| `nodeos/main.py` | FastAPI application | ~550 |
| `nodeos/Dockerfile` | Container definition | 15 |
| `nodeos/requirements.txt` | Dependencies | 5 |
| `nodeos/brain_identity.yaml` | Identity metadata | 7 |
| `nodeos/README.md` | Service documentation | ~250 |
| `nodeos/test_nodeos.sh` | Test script | ~150 |
| `ui/pages/api/nodeos/[...path].js` | Next.js proxy | 38 |
| `docker-compose.yml` | Production config | +45 |
| `docker-compose.dev.yml` | Dev config | +18 |
| `docker-compose.minimal.yml` | Minimal config | +18 |

**Total new code**: ~1,100 lines across 10 files
