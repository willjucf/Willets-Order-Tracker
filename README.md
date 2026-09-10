# Willet's Order Tracker v1.5

Desktop app that scans your email for Pokemon Center, Walmart, Target and Best Buy orders and tracks status, spending, and item stick rates.

Works with standard mailboxes (Gmail, Outlook/Hotmail, iCloud, Yahoo, AOL) **and with [AYCD Inbox](https://aycd.io/inbox)** via its built-in IMAP server — so you can point the tracker at one unified inbox that spans all of your synced mail accounts.

## Requirements

- [Node.js](https://nodejs.org) 18+
- [Python](https://python.org) 3.10+

## Run in Dev Mode

```
npm install
pip install -r backend/requirements.txt
npm run dev
```

## Build the Installer

Double-click **`build.bat`** — it handles everything automatically and produces:

```
release/Willets Order Tracker Setup 1.5.0.exe
```

Or run it from the terminal:

```
build.bat
```

## What the Installer Does

The setup `.exe` is a standard Windows installer. When you run it:

1. Asks where to install (defaults to `C:\Users\YourName\AppData\Local\Programs\Willet's Order Tracker`)
2. Installs all app files — no Python or Node.js needed on the target machine
3. Creates a **Start Menu shortcut** and optionally a **Desktop shortcut**
4. Adds an entry to **Add/Remove Programs** so you can uninstall it normally

The app is fully self-contained — everything is bundled inside the installer. Users just run the setup, open Willet's Order Tracker, and go.

---

## Email Providers

Pick your provider in the sidebar's **Email Connection** panel.

### Standard mailboxes (Gmail, Outlook, iCloud, Yahoo, AOL)

Enter your email address and an **app password** (generated from your email provider's security settings — *not* your normal login password), then click **Connect**. IMAP must be enabled on the account.

### AYCD Inbox (IMAP)

AYCD Inbox can expose all of your synced mail accounts through a single, local **IMAP server**. The tracker logs into that server's **Unified Inbox** (`inbox@aycd.me`) and reads every exposed account at once — ideal for tracking orders across a large fleet of accounts.

#### Quick start — everything on one PC (the simple version)

New to this? This is the easiest setup, and it uses **zero UpLink data**. Do all of it on the computer where AYCD Inbox is installed.

1. **Open AYCD Inbox** and make sure your mail accounts are added and syncing (you can see emails on the Mail screen).
2. Go to **Settings → IMAP Server** and switch **Enable IMAP Server** on. The **Status** should change to **Running**.
3. Leave **Bind Address** on **Localhost Only** and **TLS/SSL** on **Off**. Write down the **Port** number shown (e.g. `43828`).
4. Under **Accounts**, click **Configure Accounts** and **tick every email account** that receives order confirmations. Set **Email Lookback Duration** to how far back you want to search (e.g. 60 days).
5. Set **Max Connections** to at least **16**, then click **Save**.
6. **Copy the Password** shown on that page (click it to copy).
7. Go to **Mail → Sync**, tick those same accounts to turn on **Intelligent Sync**, set **Priority** to **Coverage**, and give it a few minutes to sync.
8. **Open Willet's Order Tracker** on the same PC. In the Email Connection panel:
   - **Provider:** AYCD Inbox (IMAP)
   - **Email:** `inbox@aycd.me`
   - **Host:** `127.0.0.1`  ·  **Port:** the number from step 3
   - **Use TLS/SSL:** leave **unchecked**
   - **IMAP Server Password:** paste from step 6
9. Click **Connect**, then run a scan.

That's the whole thing. Connecting from a **different** computer instead? See *Remote (UpLink)* below — that path uses AYCD data.

#### The two ways to connect

Read the bandwidth note before choosing.

| Connection | When to use | Host / Port / TLS | UpLink data used |
|------------|-------------|-------------------|------------------|
| **Local (recommended)** | Tracker runs on the **same machine** as AYCD Inbox | `127.0.0.1` · your IMAP Server port · **TLS off** | **None** — localhost is not metered |
| **UpLink (remote)** | Tracker runs on a **different machine/network** | your `…-inbox-imap.aycd.net` host · `993` · **TLS on** | **Yes** — every scan counts on AYCD plan |

> ⚠️ **UpLink bandwidth is metered and resets monthly.** AYCD gives you a data allowance tied to your plan that refreshes on a rolling ~30-day cycle. Every scan over UpLink pulls the matched order emails through the tunnel, so remote testing eats into that allowance quickly — a few big scans can burn a noticeable chunk. **Run the tracker on the same PC as AYCD Inbox and connect over `127.0.0.1`, which is free and unmetered.** Only use UpLink when you genuinely need remote access, and turn Remote Access **off** when you're done. Also stay on the latest build.

#### Step 1 — AYCD → Settings → IMAP Server

| Setting | Set to | Notes |
|---------|--------|-------|
| **Enable IMAP Server** | **ON** — Status must read **Running** | **Stays ON** while you use the tracker. Click **Save**. |
| **Bind Address** | **Localhost Only (127.0.0.1)** | Keep this for local use. Only change if you have a specific network reason — UpLink does **not** need "All Interfaces". |
| **Port** | Your choice (e.g. `43828`) | Note it — you enter the same number in the tracker (local mode). |
| **TLS/SSL** | **Off** | This is the *local* server. It **stays off** — leave the tracker's "Use TLS/SSL" box unchecked for local connections. |
| **Password** | Copy it | Paste into the tracker's **IMAP Server Password** field. Use the redo icon to rotate if needed. |
| **Accounts (exposed)** | **Select every account that receives order emails** | Un-exposed accounts are invisible to the tracker. |
| **Email Lookback Duration** | **≥ your scan date range** (default 30 days) | Mail older than this is hidden from the tracker, so older orders won't be found. Higher values use more memory/bandwidth — set only as far back as you need. |
| **Max Connections** | **At least 16** | The tracker opens ~8 parallel fetch connections + 1. Too low a limit drops fetches. |
| **Remote Access (UpLink)** | **Off for local use** | Only turn on for remote connections — see Step 3. |
| **Unified Inbox username** | `inbox@aycd.me` | This is the username you enter in the tracker. |

#### Step 2 — AYCD → Mail → Sync

The Unified Inbox only shows mail that AYCD has synced, so keep syncing running.

| Setting | Set to | Notes |
|---------|--------|-------|
| **Intelligent Sync** | **ON** — select all order-receiving accounts | Auto-enables once accounts are selected. **Stays ON.** |
| **Intelligent Sync Priority** | **Coverage** | Order emails can arrive on any account, including quiet ones. Coverage polls every account evenly. |
| **Concurrent Sync Limit** | As high as your proxies sustain | Higher = faster refresh, more bandwidth. |
| **Sync Speed** | **Automatic** | Raise toward Maximum only if your proxies have headroom. |
| **Priority Mail Monitoring** | **Off** | Can degrade sync performance; not needed here. |
| **Sync Mail On Startup** | **Off** | Deprecated — Intelligent Sync replaces it. |

> 💡 **Running lots of accounts? Use proxies.** Proxies are set **on your AYCD accounts** (Mail → Accounts, per account — *not* in this tracker), and it's the **IMAP proxy** that paces syncing. One proxy shared across many mailboxes is the bottleneck: spread accounts across **more IMAP proxies / subnets** so AYCD syncs the whole fleet faster, and new orders reach the Unified Inbox — and your scans — sooner. Without enough proxies, a large fleet can take hours to refresh.

#### Step 3 — Remote only: AYCD → Settings → UpLink Remote

Skip this entirely if the tracker runs on the same machine as AYCD Inbox.

1. Click **Enable Remote Access for Inbox IMAP**. It fills in **Protocol / Host / Port** (typically `imaps` / `…-inbox-imap.aycd.net` / `993`).
2. In the tracker, set **Host** and **Port** to those values and **turn Use TLS/SSL ON** (because the Protocol is `imaps`). You can leave the IMAP Server bind on **Localhost Only** — UpLink tunnels it for you.
3. **Turn Remote Access OFF when you're done.** ✅ **This is the switch that saves your UpLink data** — while it's on, remote scans keep drawing from your bandwidth.

#### What stays on vs. what to turn off

- **Stays ON while using the tracker:** IMAP Server (Enabled / Running), the exposed **Accounts**, and **Intelligent Sync**. The local server's **TLS/SSL stays Off**.
- **Turn OFF after use:** **UpLink Remote Access** — the main bandwidth saver. Leave it off unless you're actively connecting from another machine.

#### What to enter in the tracker

| Field | Local | UpLink (remote) |
|-------|-------|-----------------|
| Email Provider | AYCD Inbox (IMAP) | AYCD Inbox (IMAP) |
| Email Address | `inbox@aycd.me` | `inbox@aycd.me` |
| Host | `127.0.0.1` | your `…-inbox-imap.aycd.net` host |
| Port | your IMAP Server port | `993` |
| Use TLS/SSL | ☐ off | ☑ on |
| IMAP Server Password | from the IMAP Server page | same |

Credentials are remembered **per provider**, so switching between Gmail and AYCD keeps each login separate.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| "python is not recognized" | Reinstall Python and check **"Add Python to PATH"** during install |
| Windows blocks the downloaded file | Right-click the file > Properties > check **Unblock** at the bottom > OK |
| Port 8420 already in use | Close other Willet's Order Tracker instances or run `taskkill /F /IM main.exe` |
| "running scripts is disabled on this system" | Run once in PowerShell: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| App opens but shows blank screen | Backend is still starting — wait a few seconds |
| "Cannot create symbolic link" during build | Enable Developer Mode: Settings > System > For Developers > ON |
| AYCD: "Could not reach IMAP server…" | IMAP Server isn't **Running**, or wrong host/port. Local uses `127.0.0.1` + your port; from another machine you must use UpLink (host + `993` + TLS on). |
| AYCD: "reached but rejected login" | Wrong username or password. Use `inbox@aycd.me` and the IMAP Server password (rotate/re-copy it if unsure). |
| AYCD: scan finds 0 orders | Widen the tracker's date range **and** raise AYCD's **Email Lookback Duration** to cover it; make sure the order accounts are **exposed** and have **synced**. |
| AYCD: UpLink data disappearing fast | You're scanning over UpLink. Run the tracker on the AYCD machine and connect via `127.0.0.1`, and **turn Remote Access off** when not in use. |

## Data Storage

All data stored in `%APPDATA%/WalmartOrderTracker/` (database, settings, backgrounds).
