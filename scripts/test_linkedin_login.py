#!/usr/bin/env python3
"""Live LinkedIn login test — run on the server where DB + browser are available.

Usage:
    # List registered accounts first:
    python scripts/test_linkedin_login.py --list

    # Test session health (is existing session still valid?):
    python scripts/test_linkedin_login.py --account <name> --check-session

    # Test automated login:
    python scripts/test_linkedin_login.py --account <name> --login

    # Test manual login (opens browser, you log in yourself):
    python scripts/test_linkedin_login.py --account <name> --manual-login

    # Test browse_feed (requires valid session):
    python scripts/test_linkedin_login.py --account <name> --browse-feed

Environment:
    Reads .env automatically. Requires DATABASE_URL to be reachable.
    Set BROWSER_STEALTH_MODE=patchright for stealth mode (recommended).
"""

import argparse
import json
import logging
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_linkedin")


def get_db():
    from src.config import Config
    from src.db import Database
    config = Config.from_env()
    return Database(config.database_url), config


def list_accounts(db):
    from src.marketing_store import MarketingStore
    store = MarketingStore(db=db)
    accounts = store.list_accounts()
    if not accounts:
        print("No accounts registered.")
        return
    print(f"\n{'Name':<25} {'Platform':<12} {'ID':<6}")
    print("-" * 45)
    for a in accounts:
        print(f"{a['name']:<25} {a['platform']:<12} {a['id']:<6}")
    print()


def build_tool(db, config):
    from src.marketing.linkedin import LinkedInAdapter
    from src.marketing.platform_knowledge import PlatformKnowledge
    from src.marketing_store import MarketingStore
    from src.tools.linkedin import LinkedInTool

    store = MarketingStore(db=db)
    knowledge = PlatformKnowledge(db=db)
    adapter = LinkedInAdapter(knowledge=knowledge)

    # Optional email store
    email_store = None
    try:
        from src.email_store import EmailStore
        email_store = EmailStore(db=db)
    except Exception:
        pass

    tool = LinkedInTool(
        store=store,
        knowledge=knowledge,
        adapter=adapter,
        openai_api_key=config.openai_api_key,
        openai_model=config.openai_model,
        openai_base_url=config.openai_base_url,
        timeout=config.linkedin_tool_timeout if hasattr(config, "linkedin_tool_timeout") else 300,
        browser_profiles_dir=getattr(config, "browser_profiles_dir", "browser_profiles"),
        email_store=email_store,
        browser_use_api_key=getattr(config, "browser_use_api_key", None),
        browser_stealth_mode=getattr(config, "browser_stealth_mode", "default"),
        browser_stealth_timezone=getattr(config, "browser_stealth_timezone", "Europe/Berlin"),
        manual_login_timeout=getattr(config, "linkedin_manual_login_timeout", 300),
    )
    return tool


def test_check_session(tool, account_name):
    print(f"\n--- Session Health Check: {account_name} ---")
    valid = tool._is_session_valid(account_name)
    print(f"Session valid: {valid}")
    return valid


def test_login(tool, account_name):
    print(f"\n--- Automated Login: {account_name} ---")
    result = tool.execute(action="login", account=account_name)
    print(f"Result: {result}")
    try:
        data = json.loads(result)
        if data.get("logged_in"):
            print("SUCCESS: Login worked!")
        elif data.get("error"):
            print(f"FAILED: {data['error']}")
        else:
            print(f"UNCLEAR: {data}")
    except json.JSONDecodeError:
        print(f"Raw result (not JSON): {result[:500]}")


def test_manual_login(tool, account_name):
    print(f"\n--- Manual Login: {account_name} ---")
    print("A browser will open. Log in manually. The script will wait.")
    result = tool.execute(action="manual_login", account=account_name)
    print(f"Result: {result}")
    try:
        data = json.loads(result)
        if data.get("logged_in"):
            print("SUCCESS: Manual login detected!")
        else:
            print(f"Result: {data}")
    except json.JSONDecodeError:
        print(f"Raw result: {result[:500]}")


def test_browse_feed(tool, account_name):
    print(f"\n--- Browse Feed: {account_name} ---")
    result = tool.execute(action="browse_feed", account=account_name, limit=3)
    print(f"Result: {result[:1000]}")
    try:
        data = json.loads(result)
        posts = data.get("posts", [])
        print(f"Got {len(posts)} posts")
        for p in posts[:3]:
            print(f"  - {p.get('author', '?')}: {p.get('content', '?')[:80]}")
    except json.JSONDecodeError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Test LinkedIn login live")
    parser.add_argument("--list", action="store_true", help="List registered accounts")
    parser.add_argument("--account", type=str, help="Account name to test")
    parser.add_argument("--check-session", action="store_true", help="Check if session is valid")
    parser.add_argument("--login", action="store_true", help="Test automated login")
    parser.add_argument("--manual-login", action="store_true", help="Test manual login")
    parser.add_argument("--browse-feed", action="store_true", help="Test feed browsing")
    args = parser.parse_args()

    if not any([args.list, args.check_session, args.login, args.manual_login, args.browse_feed]):
        parser.print_help()
        return

    db, config = get_db()

    try:
        if args.list:
            list_accounts(db)
            return

        if not args.account:
            print("ERROR: --account is required for test actions")
            return

        tool = build_tool(db, config)

        if args.check_session:
            test_check_session(tool, args.account)

        if args.login:
            test_login(tool, args.account)

        if args.manual_login:
            test_manual_login(tool, args.account)

        if args.browse_feed:
            test_browse_feed(tool, args.account)

    finally:
        db.close()


if __name__ == "__main__":
    main()
