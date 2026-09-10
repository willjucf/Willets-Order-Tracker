"""Application configuration settings."""
import os
from pathlib import Path

# Application info
APP_NAME = "Willet's Order Tracker"
APP_VERSION = "1.5.0"
APP_FULL_NAME = APP_NAME

# GitHub repo for updates
GITHUB_REPO = "willjucf/Willets-Order-Tracker"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

# Get the app data directory for storing database and settings
def get_app_data_dir() -> Path:
    """Get the application data directory (persists across sessions)."""
    app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
    app_dir = Path(app_data) / "WalmartOrderTracker"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

# Database path
DATABASE_PATH = get_app_data_dir() / "orders.db"

# Email provider settings
EMAIL_PROVIDERS = {
    "gmail": {
        "name": "Gmail",
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "enabled": True
    },
    "outlook": {
        "name": "Outlook/Hotmail",
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "enabled": True
    },
    "icloud": {
        "name": "iCloud",
        "imap_server": "imap.mail.me.com",
        "imap_port": 993,
        "enabled": True
    },
    "yahoo": {
        "name": "Yahoo",
        "imap_server": "imap.mail.yahoo.com",
        "imap_port": 993,
        "enabled": True
    },
    "aol": {
        "name": "AOL",
        "imap_server": "imap.aol.com",
        "imap_port": 993,
        "enabled": True
    },
    "aycd": {
        # AYCD Inbox's built-in IMAP server. It runs locally (Localhost bind) with
        # TLS off by default and a user-specific port, so host/port are editable in the
        # UI (custom_connection). Log in with the Unified Inbox account (inbox@aycd.me)
        # to read mail already synced across every exposed account — ideal for backfilling
        # order history. The IMAP server password (Settings > IMAP Server) is the password.
        "name": "AYCD Inbox (IMAP)",
        "imap_server": "127.0.0.1",
        "imap_port": 43828,
        "use_ssl": False,
        "custom_connection": True,
        "enabled": True
    }
}

# Extended search settings
EXTENDED_SEARCH_DAYS = 30  # Search for shipped/delivered emails up to X days after expected delivery

# Store configurations for sender filtering
STORE_CONFIGS = {
    "Walmart": {
        "sender_filter": "walmart",
        "enabled": True
    },
    "Sam's Club": {
        "sender_filter": "samsclub.com",
        "enabled": False
    },
    "Costco": {
        "sender_filter": "costco.com",
        "enabled": False
    },
    "Pokemon Center": {
        # Confirmations come from em.pokemon.com, shipping from pokemoncenter.narvar.com,
        # and iCloud rewrites both — all contain "pokemon", so filter broadly.
        "sender_filter": "pokemon",
        "enabled": True
    },
    "Amazon": {
        "sender_filter": "amazon.com",
        "enabled": False
    },
    "Target": {
        "sender_filter": "target",
        "enabled": True
    },
    "Best Buy": {
        # Direct sender is BestBuyInfo@emailinfo.bestbuy.com; iCloud "Hide My Email"
        # rewrites it to BestBuyInfo_at_emailinfo_bestbuy_com_...@icloud.com, so
        # filter on the broad "bestbuy" substring.
        "sender_filter": "bestbuy",
        "enabled": True
    }
}

# Backend server settings
BACKEND_PORT = 8420
