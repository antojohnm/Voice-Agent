import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "call_centre"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD")
    )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id SERIAL PRIMARY KEY,
            call_sid TEXT UNIQUE NOT NULL,
            caller_number TEXT,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            status TEXT DEFAULT 'active',
            recording_url TEXT,
            recording_sid TEXT
        )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        call_sid TEXT UNIQUE NOT NULL REFERENCES calls(call_sid),
        conversation TEXT NOT NULL,
        last_updated TIMESTAMP NOT NULL
    )
""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS call_verifications (
        call_sid TEXT PRIMARY KEY REFERENCES calls(call_sid),
        customer_id INTEGER,
        verified_at TIMESTAMP,
        voice_code TEXT
    )
""")

    conn.commit()
    cursor.close()
    conn.close()
    print("PostgreSQL database initialized")


def start_call(call_sid, caller_number):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO calls (call_sid, caller_number, started_at, status)
        VALUES (%s, %s, %s, 'active')
        ON CONFLICT (call_sid) DO NOTHING
    """, (call_sid, caller_number, datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Call started: {call_sid} from {caller_number}")


def end_call(call_sid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE calls SET ended_at = %s, status = 'ended'
        WHERE call_sid = %s
    """, (datetime.now(), call_sid))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Call ended: {call_sid}")


def save_recording(call_sid, recording_url, recording_sid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE calls SET recording_url = %s, recording_sid = %s
        WHERE call_sid = %s
    """, (recording_url, recording_sid, call_sid))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Recording saved for {call_sid}: {recording_url}")


def save_message(call_sid, role, content):
    conn = get_connection()
    cursor = conn.cursor()

    # Get existing conversation
    cursor.execute("""
        SELECT conversation FROM messages WHERE call_sid = %s
    """, (call_sid,))
    row = cursor.fetchone()

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_line = f"[{timestamp}] {role.upper()}: {content}"

    if row:
        updated = row[0] + "\n" + new_line
        cursor.execute("""
            UPDATE messages SET conversation = %s, last_updated = %s
            WHERE call_sid = %s
        """, (updated, datetime.now(), call_sid))
    else:
        cursor.execute("""
            INSERT INTO messages (call_sid, conversation, last_updated)
            VALUES (%s, %s, %s)
        """, (call_sid, new_line, datetime.now()))

    conn.commit()
    cursor.close()
    conn.close()


def get_conversation_history(call_sid):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT conversation FROM messages
        WHERE call_sid = %s
    """, (call_sid,))
    
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row or not row[0]:
        return []

    lines = row[0].split("\n")

    history = []
    for line in lines:
        try:
            # Example line:
            # [2026-05-04 10:00:00] USER: Hello
            parts = line.split("] ", 1)
            if len(parts) < 2:
                continue

            rest = parts[1]
            role_part, content = rest.split(": ", 1)

            role = role_part.lower()  # user / assistant
            history.append({"role": role, "content": content})
        except:
            continue

    return history


def get_all_calls():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.call_sid, c.caller_number, c.started_at, c.ended_at,
               c.status, c.recording_url, COUNT(m.id) as message_count
        FROM calls c
        LEFT JOIN messages m ON c.call_sid = m.call_sid
        GROUP BY c.call_sid
        ORDER BY c.started_at DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def get_call_transcript(call_sid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT conversation, last_updated FROM messages WHERE call_sid = %s
    """, (call_sid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else "No transcript available."


# ── Order lookup — called once customer provides their order ID ──

def get_order_context(order_id):
    """
    Pull everything related to an order from all business tables.
    Returns a formatted string ready to be injected into the LLM prompt.
    Returns None if order not found.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Validate order exists
    cursor.execute("""
        SELECT o.order_id, o.order_status, o.total_amount, o.created_at,
               c.name, c.phone, c.email, c.address
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.order_id = %s
    """, (order_id,))
    order_row = cursor.fetchone()

    if not order_row:
        cursor.close()
        conn.close()
        return None

    order_id_db, order_status, total_amount, created_at, \
        cust_name, cust_phone, cust_email, cust_address = order_row

    # Order items with inventory details
    cursor.execute("""
        SELECT i.item_name, oi.quantity, oi.price_at_purchase,
               i.is_available, i.quantity as stock_quantity
        FROM order_items oi
        JOIN inventory i ON oi.item_id = i.item_id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()

    # Payment details
    cursor.execute("""
        SELECT payment_method, payment_status, amount, paid_at
        FROM payments
        WHERE order_id = %s
        ORDER BY paid_at DESC
        LIMIT 1
    """, (order_id,))
    payment = cursor.fetchone()

    # Delivery details
    cursor.execute("""
        SELECT delivery_status, delivery_address, delivered_at
        FROM deliveries
        WHERE order_id = %s
        ORDER BY delivery_id DESC
        LIMIT 1
    """, (order_id,))
    delivery = cursor.fetchone()

    cursor.close()
    conn.close()

    # ── Format everything into a clean context string ──
    lines = []

    lines.append(f"CUSTOMER NAME: {cust_name}")
    lines.append(f"CUSTOMER EMAIL: {cust_email}")
    lines.append(f"CUSTOMER ADDRESS: {cust_address}")
    lines.append("")

    lines.append(f"Order Status: {order_status}")
    lines.append(f"Order Date: {created_at.strftime('%B %d, %Y') if created_at else 'N/A'}")
    lines.append(f"Total Amount: ${total_amount}")
    lines.append("")

    lines.append("ITEMS ORDERED:")
    for item in items:
        item_name, qty, price, is_available, stock = item
        availability = "In Stock" if is_available else "Out of Stock"
        lines.append(f"  - {item_name} x{qty} @ ${price} each ({availability})")
    lines.append("")

    if payment:
        pay_method, pay_status, pay_amount, paid_at = payment
        paid_str = paid_at.strftime('%B %d, %Y') if paid_at else 'Pending'
        lines.append(f"PAYMENT: {pay_method} | Status: {pay_status} | "
                     f"Amount: ${pay_amount} | Date: {paid_str}")
    else:
        lines.append("PAYMENT: No payment record found")
    lines.append("")

    if delivery:
        del_status, del_address, delivered_at = delivery
        delivered_str = delivered_at.strftime('%B %d, %Y') if delivered_at else 'Not yet delivered'
        lines.append(f"DELIVERY: Status: {del_status} | "
                     f"Address: {del_address} | Delivered: {delivered_str}")
    else:
        lines.append("DELIVERY: No delivery record found")

    return "\n".join(lines)


def save_verified_order(call_sid, voice_code):
    """Save which voice_code this call is associated with"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO call_verifications (call_sid, voice_code, verified_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (call_sid) DO UPDATE
        SET voice_code = %s, verified_at = %s
    """, (call_sid, voice_code, datetime.now(), voice_code, datetime.now()))
    conn.commit()
    cursor.close()
    conn.close()


def get_verified_order(call_sid):
    """Return the voice_code already verified for this call, or None"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT voice_code FROM call_verifications
        WHERE call_sid = %s AND verified_at IS NOT NULL
    """, (call_sid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


# Initialize database when imported
init_db()