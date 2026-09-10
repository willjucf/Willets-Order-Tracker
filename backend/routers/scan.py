"""Scan router with WebSocket progress streaming."""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from routers.email import get_email_client, get_connected_email
from services.parsers.walmart_parser import WalmartParser
from services.parsers.target_parser import TargetParser
from services.parsers.pokemon_parser import PokemonParser
from services.parsers.bestbuy_parser import BestBuyParser
from services.database.models import Order, Item, Scan, get_order_statistics
from services.database.db import clear_orders
from utils.config import EXTENDED_SEARCH_DAYS, STORE_CONFIGS

# Parser + subject hints per store
_STORE_PARSERS = {
    "Walmart": {
        "parser": WalmartParser,
        "subject_hints": [
            "Thanks for your",
            "Shipped:",
            "Arrived:",
            "Canceled:",
            "was canceled",
            "preorder is preparing",
            "double-check your address",
        ],
    },
    "Target": {
        "parser": TargetParser,
        "subject_hints": TargetParser.SUBJECT_HINTS,
    },
    "Pokemon Center": {
        "parser": PokemonParser,
        "subject_hints": PokemonParser.SUBJECT_HINTS,
    },
    "Best Buy": {
        "parser": BestBuyParser,
        "subject_hints": BestBuyParser.SUBJECT_HINTS,
    },
}

router = APIRouter(tags=["scan"])

# Track active scans
_active_scans = {}


class ScanRequest(BaseModel):
    startDate: str  # YYYY-MM-DD
    endDate: str    # YYYY-MM-DD
    store: str = "Walmart"


class ScanResponse(BaseModel):
    scanId: str


@router.post("/api/scan/start", response_model=ScanResponse)
async def start_scan(req: ScanRequest):
    """Start a new email scan."""
    client = get_email_client()
    if not client:
        raise HTTPException(status_code=400, detail="Not connected to email")

    # Reestablish the IMAP connection if it went stale since the last scan. This lets a
    # repeat scan work without a manual disconnect/reconnect and catches missed email.
    if not client.ensure_connected():
        raise HTTPException(status_code=400, detail="Email connection lost. Please reconnect.")

    store_config = STORE_CONFIGS.get(req.store)
    if not store_config or not store_config.get("enabled"):
        raise HTTPException(status_code=400, detail="Store not supported")

    scan_id = str(uuid.uuid4())
    _active_scans[scan_id] = {
        "status": "pending",
        "progress": [],
        "start_date": req.startDate,
        "end_date": req.endDate,
        "store": req.store,
        "sender_filter": store_config["sender_filter"],
    }

    # Start scan in background
    asyncio.get_event_loop().run_in_executor(
        None, _run_scan, scan_id
    )

    return ScanResponse(scanId=scan_id)


@router.websocket("/ws/scan/{scan_id}")
async def scan_websocket(websocket: WebSocket, scan_id: str):
    """WebSocket endpoint for scan progress updates."""
    await websocket.accept()

    if scan_id not in _active_scans:
        await websocket.send_json({"error": "Scan not found"})
        await websocket.close()
        return

    scan_data = _active_scans[scan_id]
    last_index = 0

    try:
        while True:
            # Send any new progress messages
            progress = scan_data["progress"]
            while last_index < len(progress):
                await websocket.send_json(progress[last_index])
                last_index += 1

            # Check if scan is complete
            if scan_data["status"] in ("complete", "error"):
                # Send remaining messages
                while last_index < len(progress):
                    await websocket.send_json(progress[last_index])
                    last_index += 1
                break

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        # Clean up after client disconnects
        if scan_id in _active_scans and _active_scans[scan_id]["status"] in ("complete", "error"):
            del _active_scans[scan_id]


def _run_scan(scan_id: str):
    """Run the email scan (runs in thread pool)."""
    scan_data = _active_scans[scan_id]
    scan_data["status"] = "running"

    store = scan_data["store"]
    store_info = _STORE_PARSERS.get(store)
    if not store_info:
        scan_data["status"] = "error"
        _emit(scan_id, "error", 0, 0, f"No parser for store: {store}")
        return

    parser = store_info["parser"]()
    subject_hints = store_info.get("subject_hints")
    client = get_email_client()
    email_cache = {}

    try:
        start = datetime.strptime(scan_data["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(scan_data["end_date"], "%Y-%m-%d").date()
        sender_filter = scan_data["sender_filter"]

        # Add one day to end date to make it inclusive
        end_inclusive = end + timedelta(days=1)

        # Clear previous results
        clear_orders()

        _emit(scan_id, "searching", 0, 0, f"Searching {store} emails...")
        emails = client.search_and_fetch(
            start, end_inclusive,
            sender_filter=sender_filter,
            subject_hints=subject_hints,
            progress_callback=lambda c, t: _emit(scan_id, "fetching", c, t, f"Downloading emails ({c}/{t})...")
        )

        # Cache emails
        for em in emails:
            email_cache[em.uid] = em

        # Parse all emails in parallel (parser has no shared mutable state)
        total_emails = len(emails)
        with ThreadPoolExecutor(max_workers=8) as executor:
            parsed_results = list(executor.map(parser.parse, emails))

        # Save to DB sequentially (SQLite writes are serialized)
        seen_order_numbers = set()
        for i, parsed in enumerate(parsed_results):
            if parsed:
                _save_parsed_order(parsed)
                seen_order_numbers.add(parsed.order_number)
            if i % 5 == 0 or i == total_emails - 1:
                _emit(scan_id, "parsing", i + 1, total_emails, f"Parsing email {i+1}/{total_emails}")

        orders_found = len(seen_order_numbers)
        _emit(scan_id, "extended", 0, 0, f"Found {orders_found} orders. Checking statuses...")

        # Phase 2: Extended search
        _extended_status_search(scan_id, client, parser, email_cache, sender_filter, subject_hints)

        # Phase 3: Reconcile statuses against recorded dates (deterministic,
        # independent of which emails this scan happened to fetch)
        _reconcile_order_statuses()

        # Save scan history
        stats = get_order_statistics()
        scan = Scan(
            email_used=get_connected_email(),
            start_date=start,
            end_date=end,
            total_orders=stats['total_orders'],
            total_confirmed=stats['confirmed'],
            total_cancelled=stats['cancelled'],
            total_shipped=stats['shipped'],
            total_delivered=stats['delivered'],
            total_spent=stats['total_spent']
        )
        scan.save()

        # Save scan items for history detail
        _save_scan_items(scan.id)

        _emit(scan_id, "complete", 1, 1, f"Scan complete! Found {orders_found} orders")
        scan_data["status"] = "complete"

    except Exception as e:
        _emit(scan_id, "error", 0, 0, f"Error: {str(e)}")
        scan_data["status"] = "error"


def _extended_status_search(scan_id, client, parser, email_cache, sender_filter, subject_hints=None):
    """Search for shipped/delivered emails for active orders."""
    active_orders = Order.get_active_orders()
    if not active_orders:
        return

    earliest_date = None
    latest_date = date.today() + timedelta(days=1)

    for order in active_orders:
        order_start = order.order_date or date.today() - timedelta(days=60)
        if earliest_date is None or order_start < earliest_date:
            earliest_date = order_start
        if order.expected_delivery_date:
            extended_end = order.expected_delivery_date + timedelta(days=EXTENDED_SEARCH_DAYS)
            if extended_end > latest_date:
                latest_date = min(extended_end, date.today() + timedelta(days=1))

    if earliest_date is None:
        return

    _emit(scan_id, "extended", 0, 0, "Searching extended date range...")

    try:
        cached_uids = set(email_cache.keys())
        all_uids = client.search_emails(earliest_date, latest_date, sender_filter=sender_filter,
                                        subject_hints=subject_hints)
        new_uids = [uid for uid in all_uids if uid not in cached_uids]

        total_new = len(new_uids)
        if total_new > 0:
            fetched = client.fetch_emails_batch(
                new_uids,
                progress_callback=lambda c, t: _emit(scan_id, "extended_fetch", c, t, f"Fetching extended {c}/{t}")
            )
            for em in fetched:
                email_cache[em.uid] = em

        order_numbers = {order.order_number: order for order in active_orders}
        cached_emails = list(email_cache.values())
        total_cached = len(cached_emails)

        # Parse extended emails in parallel
        with ThreadPoolExecutor(max_workers=8) as executor:
            ext_parsed = list(executor.map(parser.parse, cached_emails))

        for i, parsed in enumerate(ext_parsed):
            if parsed and parsed.order_number in order_numbers:
                order = order_numbers[parsed.order_number]
                if parsed.email_type == 'shipped' and not order.shipped_date:
                    order.shipped_date = parsed.shipped_date
                    # Don't downgrade an already delivered/cancelled order back to shipped
                    if order.status not in ('delivered', 'cancelled'):
                        order.status = 'shipped'
                    if parsed.expected_delivery_date:
                        order.expected_delivery_date = parsed.expected_delivery_date
                    order.save()
                elif parsed.email_type == 'delivered' and order.status != 'cancelled':
                    # Self-heal: a delivered email always wins over shipped,
                    # even if delivered_date was already recorded (repairs orders
                    # whose status got clobbered back to 'shipped' by a later
                    # shipped email during a previous scan).
                    changed = False
                    if not order.delivered_date:
                        order.delivered_date = parsed.delivered_date
                        changed = True
                    if order.status != 'delivered':
                        order.status = 'delivered'
                        changed = True
                    if changed:
                        order.save()
                elif parsed.email_type == 'cancelled' and order.status != 'cancelled':
                    order.status = 'cancelled'
                    order.save()
            if i % 5 == 0 or i == total_cached - 1:
                _emit(scan_id, "updating", i + 1, total_cached, f"Updating statuses {i+1}/{total_cached}")

    except Exception as e:
        print(f"Error in extended search: {e}")


def _reconcile_order_statuses():
    """Enforce status invariants against recorded dates.

    A previous scan could leave an order with a delivered_date but a stale
    'shipped' status (e.g. a shipped email parsed after the delivered one).
    This pass repairs such orders deterministically, without depending on the
    delivered/shipped email being re-fetched in the current scan.
    Order of precedence: cancelled > delivered > shipped > confirmed.
    """
    for order in Order.get_all():
        if order.status == 'cancelled':
            continue
        new_status = order.status
        if order.delivered_date:
            new_status = 'delivered'
        elif order.shipped_date and order.status in ('confirmed', ''):
            new_status = 'shipped'
        if new_status != order.status:
            order.status = new_status
            order.save()


def _save_parsed_order(parsed):
    """Save parsed order to database."""
    existing = Order.get_by_order_number(parsed.order_number)

    if existing:
        if parsed.email_type == 'confirmation':
            if not existing.order_date and parsed.order_date:
                existing.order_date = parsed.order_date
            if not existing.expected_delivery_date and parsed.expected_delivery_date:
                existing.expected_delivery_date = parsed.expected_delivery_date
            if parsed.total_amount and parsed.total_amount > existing.total_amount:
                existing.total_amount = parsed.total_amount
            if not existing.items and parsed.items:
                existing.items = [
                    Item(name=item.name, quantity=item.quantity, unit_price=item.unit_price,
                         item_type=item.item_type, image_url=item.image_url)
                    for item in parsed.items
                ]
        elif parsed.email_type == 'shipped':
            existing.shipped_date = parsed.shipped_date
            if existing.status in ('confirmed', ''):
                existing.status = 'shipped'
            if parsed.expected_delivery_date:
                existing.expected_delivery_date = parsed.expected_delivery_date
            if parsed.order_date and not existing.order_date:
                existing.order_date = parsed.order_date
        elif parsed.email_type == 'delivered':
            existing.delivered_date = parsed.delivered_date
            existing.status = 'delivered'
            if parsed.order_date and not existing.order_date:
                existing.order_date = parsed.order_date
            if parsed.total_amount and existing.total_amount == 0:
                existing.total_amount = parsed.total_amount
        elif parsed.email_type == 'cancelled':
            existing.status = 'cancelled'
            if parsed.total_amount and existing.total_amount == 0:
                existing.total_amount = parsed.total_amount
        existing.save()
    else:
        if parsed.email_type != 'confirmation':
            return

        order = Order(
            order_number=parsed.order_number,
            order_date=parsed.order_date,
            expected_delivery_date=parsed.expected_delivery_date,
            shipped_date=parsed.shipped_date,
            delivered_date=parsed.delivered_date,
            total_amount=parsed.total_amount,
            status='confirmed',
            items=[
                Item(name=item.name, quantity=item.quantity, unit_price=item.unit_price,
                     item_type=item.item_type, image_url=item.image_url)
                for item in parsed.items
            ] if parsed.items else []
        )
        order.save()


def _save_scan_items(scan_id: int):
    """Save item breakdown for the scan."""
    from services.database.models import get_spending_by_item_name
    from services.database.db import get_db

    items = get_spending_by_item_name()
    with get_db() as conn:
        cursor = conn.cursor()
        for item in items:
            cursor.execute("""
                INSERT INTO scan_items (scan_id, item_name, total_quantity, cancelled_quantity, total_spent, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                scan_id,
                item['name'],
                item['active_quantity'] + item['cancelled_quantity'],
                item['cancelled_quantity'],
                item['total_spent'],
                item.get('image_url', '')
            ))


def _emit(scan_id: str, phase: str, current: int, total: int, status: str):
    """Emit a progress message for a scan."""
    if scan_id in _active_scans:
        _active_scans[scan_id]["progress"].append({
            "phase": phase,
            "current": current,
            "total": total,
            "status": status,
        })
