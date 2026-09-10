"""Best Buy email parser implementation."""
import re
from datetime import date, datetime
from typing import Optional, List
from bs4 import BeautifulSoup

from services.parsers.base_parser import BaseParser, ParsedOrder, ParsedItem
from services.email_client.base_client import RawEmail

try:
    import lxml
    HTML_PARSER = 'lxml'
except ImportError:
    HTML_PARSER = 'html.parser'


class BestBuyParser(BaseParser):
    """Parser for Best Buy order emails.

    Mail comes from ``BestBuyInfo@emailinfo.bestbuy.com`` (Salesforce Marketing Cloud).
    iCloud "Hide My Email" rewrites that to
    ``BestBuyInfo_at_emailinfo_bestbuy_com_...@icloud.com``, so both the sender filter
    and ``can_parse`` key off the broad ``bestbuy`` substring rather than a full domain.

    Sample coverage: only **pre-order confirmations** ("Thanks for your order.") have
    been captured so far — both the direct and the iCloud-forwarded variant, which are
    byte-for-byte the same template. Shipped / delivered / cancelled handling below is
    written against Best Buy's published subject lines and the shared order template,
    and is deliberately defensive (subject match first, then the in-body ``Status:``
    field) so it degrades to ``unknown`` rather than mis-classifying. Revisit
    ``SUBJECT_HINTS`` / ``detect_email_type`` once real samples of those exist.
    """

    # Subject substrings for server-side IMAP filtering. Kept broad because the
    # non-confirmation templates are unverified — a hint that never matches costs
    # nothing, a missing one silently drops the email.
    SUBJECT_HINTS = [
        "Thanks for your order",        # confirmation (verified)
        "has shipped",                  # shipped
        "is on the way",                # shipped
        "on its way",                   # shipped
        "Shipped:",                     # shipped
        "ready for pickup",             # ready for pickup (treated as shipped)
        "has been delivered",           # delivered
        "was delivered",                # delivered
        "Delivered:",                   # delivered
        "has been canceled",            # cancelled
        "has been cancelled",           # cancelled
        "we canceled",                  # cancelled
        "order cancellation",           # cancelled
        "Canceled:",                    # cancelled
        "preorder",                     # pre-order updates
    ]

    # Order number, e.g. BBY01-807250990857
    _ORDER_NUM = re.compile(r'\b(BBY\d{2}-\d{8,})\b', re.IGNORECASE)

    # Totals. Best Buy's summary reads: Subtotal / Shipping / Estimated Sales Tax / Total
    _ORDER_TOTAL = re.compile(r'Order\s+Total\s*:?\s*\$([\d,]+\.\d{2})', re.IGNORECASE)
    _TOTAL = re.compile(r'(?<!sub)\btotal\s*:?\s*\$([\d,]+\.\d{2})', re.IGNORECASE)
    _SUBTOTAL = re.compile(r'\bsubtotal\s*:?\s*\$([\d,]+\.\d{2})', re.IGNORECASE)

    # Item fields inside a product block
    _QTY = re.compile(r'Qty\s*:?\s*(\d+)', re.IGNORECASE)
    _AMOUNT = re.compile(r'\$([\d,]+\.\d{2})')

    # Product images: alt="Product Image For: <name>" on pisces.bbystatic.com
    _PRODUCT_IMG_SRC = re.compile(r'bbystatic\.com/.*?/products/', re.IGNORECASE)
    _PRODUCT_ALT = re.compile(r'^\s*Product\s+Image\s+For\s*:\s*', re.IGNORECASE)

    # Text fallback for items when no product image is present:
    # "<name> $<line total> Model #: <sku> Qty: <n>"
    _ITEM_TEXT = re.compile(
        r'(?P<name>[^$]{5,200}?)\s*'
        r'\$(?P<price>[\d,]+\.\d{2})\s*'
        r'Model\s*#\s*:?\s*(?P<sku>\S+)\s*'
        r'Qty\s*:?\s*(?P<qty>\d+)',
        re.IGNORECASE,
    )

    # Dates. "Estimated delivery: Thursday, November 19" (no year)
    _ESTIMATED_DELIVERY = re.compile(
        r'(?:Estimated\s+delivery|Arriving|Estimated\s+arrival|Expected\s+delivery)\s*:?\s*'
        r'(?:by\s+)?'
        r'(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+)?'
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)',
        re.IGNORECASE,
    )
    _DELIVERED_ON = re.compile(
        r'Delivered(?:\s+on)?\s*:?\s*'
        r'(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+)?'
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)',
        re.IGNORECASE,
    )
    _ORDER_DATE = re.compile(
        r'(?:Order\s+(?:date|placed)|Ordered\s+on)\s*:?\s*'
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})',
        re.IGNORECASE,
    )

    # In-body "Status:" field, used only when the subject is inconclusive
    _STATUS = re.compile(r'Status\s*:?\s*([A-Za-z][A-Za-z \-]{2,40})', re.IGNORECASE)

    def get_store_name(self) -> str:
        return "Best Buy"

    def can_parse(self, email: RawEmail) -> bool:
        return 'bestbuy' in email.sender.lower()

    def detect_email_type(self, subject: str, text: str = '') -> str:
        s = subject.lower()

        if 'cancel' in s:
            return 'cancelled'
        if 'delivered' in s:
            return 'delivered'
        if ('has shipped' in s or 'is on the way' in s or 'on its way' in s
                or s.startswith('shipped') or 'shipped:' in s
                or 'ready for pickup' in s):
            return 'shipped'
        if 'thanks for your order' in s or 'thank you for your order' in s:
            return 'confirmation'

        # Subject inconclusive: fall back to the order template's Status field.
        return self._status_to_type(text)

    def _status_to_type(self, text: str) -> str:
        if not text:
            return 'unknown'
        m = self._STATUS.search(text)
        if not m:
            return 'unknown'
        status = m.group(1).strip().lower()
        if 'cancel' in status:
            return 'cancelled'
        if 'delivered' in status:
            return 'delivered'
        # "Waiting to be shipped" is the confirmation state — check it before "shipped"
        if 'waiting to be shipped' in status or 'preparing' in status or 'prepping' in status:
            return 'confirmation'
        if 'shipped' in status or 'ready for pickup' in status or 'out for delivery' in status:
            return 'shipped'
        return 'unknown'

    def parse(self, email: RawEmail) -> Optional[ParsedOrder]:
        if not self.can_parse(email):
            return None

        body = email.body_html or email.body_text
        if not body:
            return None

        soup = BeautifulSoup(body, HTML_PARSER)
        text = self._normalize(soup.get_text(separator=' ', strip=True))

        email_type = self.detect_email_type(email.subject, text)
        if email_type == 'unknown':
            return None

        order_number = self._extract_order_number(text) or self._extract_order_number(email.subject)
        if not order_number:
            return None

        parsed = ParsedOrder(order_number=order_number, email_type=email_type)

        if email_type == 'confirmation':
            parsed.order_date = self._extract_order_date(text) or email.date
            parsed.expected_delivery_date = self._extract_estimated_delivery(text)
            parsed.total_amount = self._extract_total(text)
            parsed.items = self._extract_items(soup, text)
        elif email_type == 'shipped':
            parsed.shipped_date = email.date
            parsed.expected_delivery_date = self._extract_estimated_delivery(text)
            parsed.order_date = self._extract_order_date(text)
            parsed.total_amount = self._extract_total(text)
            parsed.items = self._extract_items(soup, text)
        elif email_type == 'delivered':
            parsed.delivered_date = self._extract_delivered_date(text) or email.date
            parsed.order_date = self._extract_order_date(text)
            parsed.total_amount = self._extract_total(text)
            parsed.items = self._extract_items(soup, text)
        elif email_type == 'cancelled':
            pass  # No verified cancellation sample — don't trust amounts/items yet

        return parsed

    # --- Extraction helpers ---

    def _extract_order_number(self, text: str) -> Optional[str]:
        m = self._ORDER_NUM.search(text)
        return m.group(1).upper() if m else None

    def _extract_total(self, text: str) -> float:
        m = self._ORDER_TOTAL.search(text)
        if m:
            return self._to_float(m.group(1))

        # Prefer the total inside the "Your Order Summary" block, which is where
        # Subtotal / Shipping / Estimated Sales Tax / Total live.
        summary = re.search(r'(?:Your\s+)?Order\s+Summary', text, re.IGNORECASE)
        region = text[summary.end():] if summary else text
        m = self._TOTAL.search(region)
        if m:
            return self._to_float(m.group(1))

        m = self._TOTAL.search(text)
        if m:
            return self._to_float(m.group(1))

        # Last resort: subtotal is better than nothing (misses shipping + tax)
        m = self._SUBTOTAL.search(text)
        return self._to_float(m.group(1)) if m else 0.0

    def _extract_order_date(self, text: str) -> Optional[date]:
        m = self._ORDER_DATE.search(text)
        return self._parse_date_string(m.group(1)) if m else None

    def _extract_estimated_delivery(self, text: str) -> Optional[date]:
        m = self._ESTIMATED_DELIVERY.search(text)
        return self._parse_date_string(m.group(1)) if m else None

    def _extract_delivered_date(self, text: str) -> Optional[date]:
        m = self._DELIVERED_ON.search(text)
        return self._parse_date_string(m.group(1)) if m else None

    def _extract_items(self, soup: BeautifulSoup, text: str) -> List[ParsedItem]:
        items = self._extract_items_from_images(soup)
        if not items:
            items = self._extract_items_from_text(text)
        return items

    def _extract_items_from_images(self, soup: BeautifulSoup) -> List[ParsedItem]:
        """Primary path: each purchased item has a product image whose alt text is
        "Product Image For: <name>", sitting in a block that also carries Model # / Qty.

        The Qty-proximity walk is what keeps marketing tiles ("Deal of the Day",
        "Best Buy Outlet") out of the item list — those use bbystatic images too but
        never sit near a Qty label.
        """
        items: List[ParsedItem] = []
        seen = set()

        for img in soup.find_all('img'):
            alt = (img.get('alt') or '').strip()
            if not self._PRODUCT_ALT.match(alt):
                src = img.get('src') or ''
                if not self._PRODUCT_IMG_SRC.search(src):
                    continue

            name = self._normalize(self._PRODUCT_ALT.sub('', alt)).strip()
            if len(name) < 5:
                continue

            key = name.lower()
            if key in seen:
                continue

            # Walk up to the block holding Model # / Qty / price for this item
            block_text = ''
            parent = img
            for _ in range(10):
                parent = parent.parent
                if parent is None:
                    break
                candidate = self._normalize(parent.get_text(separator=' ', strip=True))
                if 'Qty' in candidate:
                    block_text = candidate
                    break
            if not block_text:
                continue  # No Qty nearby -> marketing image, not a purchased item

            seen.add(key)

            qm = self._QTY.search(block_text)
            qty = int(qm.group(1)) if qm else 1

            # Best Buy prints the *extended* price (unit x qty) next to the item.
            pm = self._AMOUNT.search(block_text)
            line_total = self._to_float(pm.group(1)) if pm else 0.0

            items.append(ParsedItem(
                name=name[:150],
                quantity=qty,
                unit_price=self._unit_price(line_total, qty),
                item_type=self._categorize_item(name),
                image_url=self._clean_image_url(img.get('src') or ''),
            ))

            if len(items) >= 20:
                break

        return items

    def _extract_items_from_text(self, text: str) -> List[ParsedItem]:
        """Fallback for templates without product images (unverified)."""
        start = re.search(r'Product\s+Details', text, re.IGNORECASE)
        end = re.search(r'(?:Your\s+)?Order\s+Summary', text, re.IGNORECASE)
        if not start:
            return []
        region = text[start.end():end.start()] if end and end.start() > start.end() else text[start.end():]

        items: List[ParsedItem] = []
        seen = set()
        for m in self._ITEM_TEXT.finditer(region):
            name = self._clean_item_name(m.group('name'))
            if len(name) < 5:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            qty = int(m.group('qty'))
            items.append(ParsedItem(
                name=name[:150],
                quantity=qty,
                unit_price=self._unit_price(self._to_float(m.group('price')), qty),
                item_type=self._categorize_item(name),
                image_url='',
            ))
            if len(items) >= 20:
                break
        return items

    # Boilerplate that can bleed into the front of a text-extracted item name
    _NAME_NOISE = re.compile(
        r'^(?:.*?(?:Note\s*:\s*Item has been (?:pre)?ordered|Pre-ordered Item|Product Details)\s*)',
        re.IGNORECASE | re.DOTALL,
    )

    def _clean_item_name(self, name: str) -> str:
        name = self._NAME_NOISE.sub('', name)
        return self._normalize(name).strip(' -|')

    @staticmethod
    def _unit_price(line_total: float, qty: int) -> float:
        """Best Buy shows the extended price; the app stores unit price."""
        if qty > 1 and line_total:
            return round(line_total / qty, 2)
        return line_total

    @staticmethod
    def _clean_image_url(src: str) -> str:
        # Strip the ";canvasHeight=295;canvasWidth=478" scaling suffix
        return src.split(';')[0] if src else ''

    @staticmethod
    def _normalize(text: str) -> str:
        """Collapse whitespace, flatten &nbsp; (used in "Model&nbsp;#:" and
        "Estimated Sales&nbsp;Tax") so the regexes above see a plain space, and drop
        U+FFFD in case a client mis-decodes the en-dash Best Buy uses in product names.
        """
        if not text:
            return ''
        text = text.replace('\xa0', ' ')
        text = re.sub('\\s\ufffd\\s', ' - ', text)
        text = text.replace('\ufffd', '')
        return re.sub(r'\s+', ' ', text).strip()

    def _categorize_item(self, name: str) -> str:
        name_lower = name.lower()
        if 'pokemon' in name_lower or 'pokémon' in name_lower:
            if any(kw in name_lower for kw in
                   ['card', 'tcg', 'booster', 'tin', 'box', 'collection', 'bundle', 'pack']):
                return 'Pokemon TCG'
            return 'Pokemon'
        if 'trading card' in name_lower:
            return 'Trading Cards'
        if any(kw in name_lower for kw in
               ['ps5', 'playstation', 'xbox', 'nintendo', 'switch', 'controller', 'dualsense']):
            return 'Gaming'
        return 'Other'

    @staticmethod
    def _to_float(value: str) -> float:
        try:
            return float(value.replace(',', ''))
        except (ValueError, AttributeError):
            return 0.0

    def _parse_date_string(self, date_str: str) -> Optional[date]:
        if not date_str:
            return None
        date_str = self._normalize(date_str).rstrip('.').replace(',', '')

        formats = [
            "%B %d %Y",   # November 19 2026
            "%b %d %Y",   # Nov 19 2026
            "%B %d",      # November 19
            "%b %d",      # Nov 19
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
            except ValueError:
                continue
            if parsed.year == 1900:
                now = datetime.now()
                parsed = parsed.replace(year=now.year)
                if (now - parsed).days > 180:
                    parsed = parsed.replace(year=now.year + 1)
                elif (parsed - now).days > 180:
                    parsed = parsed.replace(year=now.year - 1)
            return parsed.date()
        return None
