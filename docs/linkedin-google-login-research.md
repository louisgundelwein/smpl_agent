# LinkedIn Google Login & Anti-Detection Research

**Date:** 2026-03-06

## Features Implemented

### Google Login Support
The LinkedIn tool now supports login via Google account in addition to direct email/password.

- **`src/marketing/linkedin.py`**: `_login_prefix()` generates Google OAuth login instructions; `build_signup_task()` supports `login_method="google"` with `google_email` / `google_password` params.
- **`src/tools/linkedin.py`**: Schema extended with `login_method`, `google_email`, `google_password` fields. `_action_create_account()` handles both flows. New `_action_login()` action for explicit login.
- **`src/config.py`** / **`src/main.py`**: Added `BROWSER_USE_API_KEY` env var support for cloud browser mode.

### browser-use 0.12 Migration
Updated from browser-use's old API to v0.12:
- `BrowserConfig` → `BrowserSession` + `BrowserProfile`
- `Browser.close()` → `BrowserSession.stop()`
- `ChatOpenAI` now imported from `browser_use` first, fallback to `langchain_openai`
- `chromium_sandbox=False` required when running as root

### Session Persistence
Browser profiles are stored in `browser_profiles/<account_name>/` for cookie/session reuse across runs. Login prefix checks if already authenticated before attempting login.

## CAPTCHA / Anti-Detection Research

### Problem
Datacenter IPs trigger reCAPTCHA on both Google and LinkedIn login pages regardless of browser stealth measures. This is IP-reputation-based, not fingerprint-based.

### Approaches Tested

| Approach | Result | Notes |
|---|---|---|
| Headless Chromium | CAPTCHA immediately | Expected |
| Xvfb + non-headless + stealth flags | CAPTCHA | Flags like `--disable-blink-features=AutomationControlled` don't help against IP checks |
| camoufox (anti-detect Firefox) | Crash | `libgtk-3.so.0` missing, then process killed (exit 144) — sandbox/env restrictions |
| patchright monkey-patch | Broken | Replacing `sys.modules["playwright"]` breaks browser-use internals |
| patchright driver swap | CDP disconnects | Copying patchright JS lib over playwright's causes WebSocket reconnect loops |
| patchright CDP URL | Untested (promising) | Launch browser via patchright, connect browser-use via `cdp_url='http://127.0.0.1:9222'` |

### Viable Solutions (Not Yet Implemented)

1. **Browser Use Cloud** (`BROWSER_USE_API_KEY`): Paid service with residential IPs + built-in CAPTCHA solver. Code already supports this via `use_cloud=True` in `_build_browser_session()`.
2. **Residential proxy / SSH tunnel**: Route traffic through a residential IP. Requires external setup.
3. **patchright + CDP**: Launch a stealth browser via patchright with `--remote-debugging-port=9222`, then connect browser-use via `cdp_url`. Most promising free approach — patches `navigator.webdriver=false` at the Node.js driver level.

### Key Takeaway
Browser fingerprinting stealth (flags, user-agent, etc.) is insufficient. The core issue is **IP reputation** — datacenter IPs are flagged by Google/LinkedIn's reCAPTCHA regardless of browser configuration. A residential IP or a cloud browser service is required for reliable automated login.
