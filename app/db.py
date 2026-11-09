import pymysql
from app.config import settings

def get_db_connection():
    return pymysql.connect(
        host=settings.MYSQL_HOST, user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD, database=settings.MYSQL_DB,
        port=settings.MYSQL_PORT, cursorclass=pymysql.cursors.DictCursor
    )

def get_user_and_ships(phone: str):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM users WHERE whatsapp_number = %s", (phone,))
        user = cur.fetchone()
        if not user: return None, []
        cur.execute("SELECT id, CONCAT(prefix, ' ', name) as full_name FROM ships WHERE user_id = %s", (user['id'],))
        ships = cur.fetchall()
    conn.close()
    return user, ships

def match_ship(ships, ship_name_llm):
    clean_name = ship_name_llm.lower().replace("km", "").strip()
    for ship in ships:
        db_clean = ship['full_name'].lower().replace("km", "").strip()
        if db_clean == clean_name:
            return ship
    return None

def get_position(ship_id):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ship_positions WHERE ship_id = %s ORDER BY reported_at DESC LIMIT 1", (ship_id,))
        pos = cur.fetchone()
    conn.close()
    return pos

def get_sensor(ship_id):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ship_sensors WHERE ship_id = %s ORDER BY reported_at DESC LIMIT 1", (ship_id,))
        sensor = cur.fetchone()
    conn.close()
    return sensor

def save_context(user_id, ship_id, intent):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO chat_contexts (user_id, last_ship_id, pending_intent, updated_at) 
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE last_ship_id=%s, pending_intent=%s, updated_at=NOW()
        """, (user_id, ship_id, intent, ship_id, intent))
    conn.commit()
    conn.close()

def get_context(user_id):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT last_ship_id, pending_intent FROM chat_contexts 
            WHERE user_id = %s AND updated_at >= DATE_SUB(NOW(), INTERVAL 15 MINUTE)
        """, (user_id,))
        ctx = cur.fetchone()
    conn.close()
    return ctx