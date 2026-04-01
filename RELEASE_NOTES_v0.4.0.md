# hbar-brain v0.4.0 Release Notes

## Overview

Version 0.4.0 expands the read-only command whitelist while maintaining the strict PROPOSE/CONFIRM workflow and fail-closed security model.

## New Features

### 1. New Read-Only Commands

Three new commands have been added to the read-only whitelist:

#### `help`
- **Description**: Lists all available read-only commands with descriptions
- **Usage**: `help`
- **Returns**: Structured list of commands with usage information

#### `version`
- **Description**: Display server version information
- **Usage**: `version`
- **Returns**:
  - `server_version`: Current hbar-brain version (0.4.0)
  - `canon_version`: Authority interface canon version (v1)
  - `api_title`: API title
  - `python_version`: Python runtime version

#### `audit tail N`
- **Description**: Show last N audit log entries
- **Usage**: `audit tail [N]` (default N=50, max N=1000)
- **Returns**: Reverse chronological list of audit entries
- **Validation**: N is clamped between 1 and 1000

### 2. Improved Database Health Check

The `/health` endpoint and `status` command now use a lightweight `SELECT 1` ping instead of counting documents:

- **Before**: `SELECT COUNT(*) FROM documents` (slow, could fail on missing table)
- **After**: `SELECT 1` (fast, reliable)
- **Response format**: `{"status": "healthy"|"error", "detail": "..."}`

## Files Modified

### Server (hbar-brain)

1. **`api/main.py`**
   - Added `HBAR_BRAIN_VERSION = "0.4.0"` constant (line 33)
   - Expanded read-only whitelist to include `help`, `version`, `audit tail` (line 1281)
   - Implemented `help` command handler (lines 1310-1322)
   - Implemented `version` command handler (lines 1323-1329)
   - Implemented `audit tail N` command handler with clamping (lines 1330-1352)
   - Fixed DB health check in `status` command (lines 1378-1393)
   - Fixed DB health check in `/health` endpoint (lines 317-334)

2. **`test_v0.4.0_smoke.py`** (NEW)
   - Comprehensive smoke test suite
   - Tests PROPOSE/CONFIRM roundtrip for all commands
   - Tests token mismatch rejection (403)
   - Tests invalid token rejection (403)
   - Tests audit tail N clamping

### Console (hbar.brain.console)

1. **`repos/console/console.py`**
   - Enhanced `print_formatted_response()` with special formatting for:
     - `help`: Pretty-printed command list
     - `version`: Formatted version information
     - `audit tail`: Formatted audit entries with timestamps
   - Lines 213-258: New response rendering logic

2. **`repos/console/test_v0.4.0_integration.sh`** (NEW)
   - Integration test script for remote server
   - Tests all new commands
   - Verifies auto-confirm behavior (should NOT auto-confirm for remote)

## Security Invariants (Unchanged)

- ✓ PROPOSE/CONFIRM workflow mandatory for all commands
- ✓ Fail-closed on mismatch/unknown commands
- ✓ No mutation, no "execute" for non-whitelisted commands
- ✓ Read-only whitelist only
- ✓ Token format: `CONFIRM-xxxxxxxx`
- ✓ Token TTL: 1800 seconds (30 minutes)
- ✓ Command normalization enforced
- ✓ Append-only audit logging

## Testing

### Server-Side Smoke Tests

Run the smoke test suite against a local server:

```bash
cd /home/zyro/CascadeProjects/systems/hbar-brain-Pulled/hbar-brain

# Start the test server (if not already running)
# python test_command_endpoint.py

# Run smoke tests
python test_v0.4.0_smoke.py
```

Expected output: All tests should pass with green checkmarks.

### Console Integration Tests

Test the console client against a remote server:

```bash
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console

# Test against default remote (91.99.158.48:8010)
./test_v0.4.0_integration.sh

# Or specify a custom remote
./test_v0.4.0_integration.sh http://localhost:8010
```

### Manual Testing Examples

```bash
# Test help command
python console.py --remote http://91.99.158.48:8010 "help"

# Test version command
python console.py --remote http://91.99.158.48:8010 "version"

# Test audit tail with default N
python console.py --remote http://91.99.158.48:8010 "audit tail"

# Test audit tail with custom N
python console.py --remote http://91.99.158.48:8010 "audit tail 200"

# Test that remote does NOT auto-confirm (should see PROPOSED status)
python console.py --remote http://91.99.158.48:8010 "version" | grep PROPOSED
```

## Deployment Notes

### Server Deployment

1. **Update the server code** on your remote host (91.99.158.48):
   ```bash
   ssh hbar@91.99.158.48
   cd /path/to/hbar-brain
   git pull  # or copy updated api/main.py
   ```

2. **Restart the server**:
   ```bash
   # If using systemd
   sudo systemctl restart hbar-brain
   
   # Or if running manually
   pkill -f "python.*main.py"
   python api/main.py
   ```

3. **Verify deployment**:
   ```bash
   curl -sS http://91.99.158.48:8010/health | jq .
   ```

### Console Deployment

The console client changes are backward-compatible. Simply update the code:

```bash
cd /home/zyro/CascadeProjects/systems/hbar.brain/repos/console
git pull  # or copy updated console.py
```

## Breaking Changes

**None.** This release is fully backward-compatible with v0.3.x.

## Next Steps (v0.5.0 and beyond)

Potential future enhancements:
- Additional read-only commands (e.g., `logs tail`, `metrics`)
- Enhanced audit filtering and search
- Command history and replay
- Performance metrics and monitoring

## Changelog

### Added
- `help` command to list available commands
- `version` command to display server version
- `audit tail N` command to view audit log entries
- Improved DB health check with `SELECT 1` ping
- Comprehensive smoke test suite
- Integration test script for console

### Changed
- DB health check now returns structured `{status, detail}` format
- Response rendering enhanced for new commands

### Fixed
- DB health check no longer fails on missing tables
- DB health check provides meaningful error details

## Version History

- **v0.4.0** (2026-02-17): Added help, version, audit tail commands; improved DB health check
- **v0.3.1** (2026-02-16): Enhanced client safety controls
- **v0.3.0** (2026-02-15): Added read-only command execution
- **v0.2.0** (2026-02-14): Initial PROPOSE/CONFIRM workflow
