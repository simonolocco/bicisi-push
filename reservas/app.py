from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os
import uuid
import hashlib
from functools import wraps
import json
import requests
import base64
import io
import mercadopago

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Load context-dependent config
def load_config():
    config = {
        "PORT": 5001,
        "DEBUG": True,
        "PUBLIC_URL": "https://bicisi.com.ar",
        "WA_TOKEN": "",
        "WA_PHONE_ID": "",
        "WA_VERIFY_TOKEN": "javier",
        "WA_VERSION": "v19.0",
        "SECRET_KEY": "bicisi-secret-key-2024",
        "MP_ACCESS_TOKEN": "TEST-4089125859574058-021718-384a315e4f5076feb41079180109d5fd-1471579186",
        "MP_PUBLIC_KEY": "TEST-82eee22b-5985-4884-bfce-d31ac77f608a"
    }
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    if value.lower() == 'true': value = True
                    elif value.lower() == 'false': value = False
                    elif value.isdigit(): value = int(value)
                    config[key] = value
                    
    return config

CONFIG = load_config()
app.secret_key = CONFIG['SECRET_KEY']

# WhatsApp Constants from Config
WA_TOKEN = CONFIG['WA_TOKEN']
WA_PHONE_ID = CONFIG['WA_PHONE_ID']
WA_VERIFY_TOKEN = CONFIG['WA_VERIFY_TOKEN']
WA_VERSION = CONFIG['WA_VERSION']

# Initialize Mercado Pago SDK
sdk = mercadopago.SDK(CONFIG['MP_ACCESS_TOKEN'])

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'bicisi.db')

# Operating hours
OPERATING_START = 8
OPERATING_END = 19

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Hash password with SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Initialize database with tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript('''
        -- Admin users table
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Categories table
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price_full_day INTEGER DEFAULT 0,
            price_half_day INTEGER DEFAULT 0,
            price_per_hour INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 0,
            image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Reservations table
        CREATE TABLE IF NOT EXISTS reservations (
            id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            customer_email TEXT,
            customer_dni TEXT,
            dni_photo TEXT,
            rental_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            start_hour INTEGER DEFAULT 8,
            end_hour INTEGER DEFAULT 19,
            payment_method TEXT NOT NULL,
            pickup_location TEXT DEFAULT 'sucursal',
            return_location TEXT DEFAULT 'sucursal',
            total INTEGER DEFAULT 0,
            deposit INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            overridden_by TEXT,
            overridden_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Reservation items table (many-to-many)
        CREATE TABLE IF NOT EXISTS reservation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id TEXT NOT NULL,
            category_id TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        
        -- Settings table
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    
    # Check if admin exists, if not create default
    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO admins (username, password) VALUES (?, ?)",
            ('admin', hash_password('bicisi2024'))
        )
    
    # Check if categories exist, if not create defaults
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ('cat-aluminio', 'Bicicleta Aluminio', 'Bicicleta liviana de aluminio, ideal para paseos', 15000, 10000, 3000, 10, '/static/images/bici-aluminio.jpg'),
            ('cat-acero', 'Bicicleta Acero', 'Bicicleta resistente de acero, perfecta para todo terreno', 12000, 8000, 2500, 8, '/static/images/bici-acero.jpg'),
            ('cat-sillita', 'Sillita para Niño', 'Sillita de seguridad para transportar niños', 5000, 3000, 1000, 5, '/static/images/sillita.jpg'),
            ('cat-remolque', 'Remolque', 'Remolque para llevar equipaje o niños', 8000, 5000, 2000, 3, '/static/images/remolque.jpg'),
        ]
        cursor.executemany(
            "INSERT INTO categories (id, name, description, price_full_day, price_half_day, price_per_hour, stock, image) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            default_categories
        )
    
    # Check if settings exist, if not create defaults
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        default_settings = [
            ('business_name', 'BiciSí'),
            ('address', 'Villa Carlos Paz, Córdoba'),
            ('phone', '+54 9 3541 57-5810'),
            ('delivery_fee', '10000'),
            ('bank_name', 'Banco Francés BBVA'),
            ('bank_account', '274-22784/8'),
            ('bank_cbu', '0170274540000002278483'),
            ('bank_alias', 'BICISI.26'),
            ('bank_holder', 'Lucas Brunazzi'),
        ]
        cursor.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", default_settings)
    
    conn.commit()
    conn.close()
    
    # Run migration for existing images
    try:
        migrate_images_to_db()
    except Exception as e:
        print(f"Migration error: {e}")

def migrate_images_to_db():
    """Migrate existing file-based images to base64 in the database"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Categories
    cursor.execute("SELECT id, image FROM categories WHERE image LIKE '/static/%'")
    categories = cursor.fetchall()
    
    for cat in categories:
        local_path = cat['image']
        # Convert /static/ to the actual static folder path
        rel_path = local_path.lstrip('/')
        # Use a safe join, assuming relative paths from project root or static folder
        # In this project, app.py is in /reservas/, and static is there too.
        full_path = os.path.join(os.path.dirname(__file__), rel_path)
        
        if os.path.exists(full_path):
            with open(full_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                ext = local_path.rsplit('.', 1)[-1].lower()
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                data_uri = f"data:{mime_type};base64,{encoded_string}"
                
                cursor.execute("UPDATE categories SET image = ? WHERE id = ?", (data_uri, cat['id']))
                print(f"Migrated category image: {cat['id']}")

    # 2. Reservations (DNI photos)
    cursor.execute("SELECT id, dni_photo FROM reservations WHERE dni_photo LIKE '/static/%'")
    reservations = cursor.fetchall()
    
    for res in reservations:
        local_path = res['dni_photo']
        rel_path = local_path.lstrip('/')
        full_path = os.path.join(os.path.dirname(__file__), rel_path)
        
        if os.path.exists(full_path):
            with open(full_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                ext = local_path.rsplit('.', 1)[-1].lower()
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                data_uri = f"data:{mime_type};base64,{encoded_string}"
                
                cursor.execute("UPDATE reservations SET dni_photo = ? WHERE id = ?", (data_uri, res['id']))
                print(f"Migrated reservation DNI photo: {res['id']}")
                
    conn.commit()
    conn.close()

def login_required(f):
    """Decorator for admin routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_settings():
    """Get all settings as dict with JSON fallback"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    db_settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    
    # Load defaults from JSON
    defaults = {}
    json_path = os.path.join(os.path.dirname(__file__), 'data', 'default_messages.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                defaults = json.load(f)
        except Exception as e:
            print(f"Error loading default_messages.json: {e}")
            
    # Merge: DB values override defaults (only if not empty)
    final_settings = defaults.copy()
    for k, v in db_settings.items():
        if v and v.strip():
            final_settings[k] = v
            
    return final_settings

@app.route('/api/admin/default-messages')
def get_default_messages():
    """Endpoint for admin panel to get placeholders"""
    json_path = os.path.join(os.path.dirname(__file__), 'data', 'default_messages.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except: pass
    return jsonify({})

def get_categories():
    """Get all categories as list of dicts"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return categories

# ==================== PUBLIC ROUTES ====================

@app.route('/')
def landing():
    """Landing page"""
    categories = get_categories()
    settings = get_settings()
    return render_template('landing.html', categories=categories, settings=settings)

@app.route('/reserva')
def reserva():
    """Reservation page"""
    categories = get_categories()
    settings = get_settings()
    return render_template('reserva.html', categories=categories, settings=settings)

# ==================== API ROUTES ====================

@app.route('/api/categories')
def api_get_categories():
    """Get all categories"""
    return jsonify(get_categories())

@app.route('/api/settings')
def api_get_settings():
    """Get settings"""
    return jsonify(get_settings())

@app.route('/api/available-slots', methods=['POST'])
def get_available_slots():
    """Get available time slots for a specific date"""
    data = request.json
    date_str = data.get('date')
    category_id = data.get('category_id')
    quantity = data.get('quantity', 1)
    
    if not date_str:
        return jsonify({"error": "Date required"}), 400
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return jsonify({"error": "Invalid date format"}), 400
    
    now = datetime.now()
    today = now.date()
    current_hour = now.hour
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get category stock
    cursor.execute("SELECT stock FROM categories WHERE id = ?", (category_id,))
    row = cursor.fetchone()
    max_stock = row['stock'] if row else 0
    
    # Get reservations for this date and category
    cursor.execute('''
        SELECT r.start_hour, r.end_hour, ri.quantity 
        FROM reservations r
        JOIN reservation_items ri ON r.id = ri.reservation_id
        WHERE ri.category_id = ? 
        AND r.start_date = ?
        AND r.status != 'cancelled'
        AND r.status != 'overridden'
    ''', (category_id, date_str))
    
    reserved_hours = {}
    for row in cursor.fetchall():
        for h in range(row['start_hour'], row['end_hour']):
            reserved_hours[h] = reserved_hours.get(h, 0) + row['quantity']
    
    conn.close()
    
    # Generate available slots
    slots = []
    for hour in range(OPERATING_START, OPERATING_END):
        available = True
        reason = ""
        
        # Check if hour already passed (for today) - also block 1 hour before and after for logistics
        if selected_date == today:
            if hour <= current_hour + 1:
                available = False
                reason = "Hora no disponible (logística)"
        
        # Check stock availability
        reserved_qty = reserved_hours.get(hour, 0)
        remaining = max_stock - reserved_qty
        if remaining < quantity:
            available = False
            reason = f"Stock insuficiente (disponible: {remaining})"
        
        slots.append({
            "hour": hour,
            "label": f"{hour:02d}:00",
            "available": available,
            "reason": reason,
            "remaining": max(0, remaining)
        })
    
    return jsonify({
        "date": date_str,
        "slots": slots,
        "operating_hours": {"start": OPERATING_START, "end": OPERATING_END}
    })

@app.route('/api/calculate-price', methods=['POST'])
def calculate_price():
    """Calculate reservation price"""
    data = request.json
    items = data.get('items', [])
    rental_type = data.get('rental_type')
    hours = data.get('hours', 0)
    days = data.get('days', 1)
    payment_method = data.get('payment_method', 'cash')
    
    conn = get_db()
    cursor = conn.cursor()
    settings = get_settings()
    
    total = 0
    breakdown = []
    
    for item in items:
        cursor.execute("SELECT * FROM categories WHERE id = ?", (item['category_id'],))
        category = cursor.fetchone()
        if not category:
            continue
        
        qty = item.get('quantity', 1)
        
        if rental_type == 'full_day':
            price = category['price_full_day'] * qty * days
            label = f"{category['name']} x{qty} - {days} día(s) completo(s)"
        elif rental_type == 'half_day':
            price = category['price_half_day'] * qty * days
            label = f"{category['name']} x{qty} - {days} medio día(s)"
        elif rental_type == 'hours':
            price = category['price_per_hour'] * qty * hours
            label = f"{category['name']} x{qty} - {hours} hora(s)"
        else:
            price = category['price_full_day'] * qty * days
            label = f"{category['name']} x{qty} - {days} día(s)"
        
        total += price
        breakdown.append({"label": label, "price": price})
    
    conn.close()
    
    # Add delivery fee if payment by transfer
    delivery_fee = 0
    if payment_method == 'transfer':
        delivery_fee = int(settings.get('delivery_fee', 10000))
        breakdown.append({"label": "Servicio de entrega/retiro", "price": delivery_fee})
        total += delivery_fee
    
    deposit = int(total * 0.5)
    
    return jsonify({
        "breakdown": breakdown,
        "subtotal": total - delivery_fee,
        "delivery_fee": delivery_fee,
        "total": total,
        "deposit": deposit
    })

@app.route('/api/reservations', methods=['POST'])
def create_reservation():
    """Create a new reservation"""
    data = request.json
    
    required = ['items', 'rental_type', 'start_date', 'customer_name', 'customer_phone', 'payment_method']
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo requerido: {field}"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if there's an existing cash reservation that should be overridden
    if data.get('payment_method') == 'transfer':
        cursor.execute('''
            SELECT id FROM reservations 
            WHERE payment_method = 'cash' 
            AND status = 'pending' 
            AND start_date = ?
        ''', (data.get('start_date'),))
        
        for row in cursor.fetchall():
            cursor.execute('''
                UPDATE reservations 
                SET status = 'overridden', overridden_by = ?, overridden_at = ?
                WHERE id = ?
            ''', (data.get('customer_phone'), datetime.now().isoformat(), row['id']))
    
    # Create new reservation
    reservation_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO reservations (
            id, customer_name, customer_phone, customer_email, customer_dni, dni_photo,
            rental_type, start_date, end_date, start_hour, end_hour,
            payment_method, pickup_location, return_location, total, deposit, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        reservation_id,
        data.get('customer_name'),
        data.get('customer_phone'),
        data.get('customer_email', ''),
        data.get('customer_dni', ''),
        data.get('dni_photo', ''),
        data.get('rental_type'),
        data.get('start_date'),
        data.get('end_date', data.get('start_date')),
        data.get('start_hour', OPERATING_START),
        data.get('end_hour', OPERATING_END),
        data.get('payment_method'),
        data.get('pickup_location', 'sucursal'),
        data.get('return_location', 'sucursal'),
        data.get('total', 0),
        data.get('deposit', 0),
        'confirmed' if data.get('payment_method') == 'transfer' else ('pending_payment' if data.get('payment_method') == 'mercadopago' else 'pending'),
        data.get('notes', '')
    ))
    
    # Add reservation items
    preference_items = []
    for item in data.get('items', []):
        cursor.execute('''
            INSERT INTO reservation_items (reservation_id, category_id, quantity)
            VALUES (?, ?, ?)
        ''', (reservation_id, item['category_id'], item.get('quantity', 1)))
        
        # Get category details for MP preference
        if data.get('payment_method') == 'mercadopago':
            cursor.execute("SELECT name, price_full_day, price_half_day, price_per_hour FROM categories WHERE id = ?", (item['category_id'],))
            cat = cursor.fetchone()
            if cat:
                unit_price = 0
                rental_type = data.get('rental_type')
                if rental_type == 'full_day': unit_price = cat['price_full_day']
                elif rental_type == 'half_day': unit_price = cat['price_half_day']
                elif rental_type == 'hours': 
                    hours = data.get('end_hour', OPERATING_END) - data.get('start_hour', OPERATING_START)
                    unit_price = cat['price_per_hour'] * hours
                else: unit_price = cat['price_full_day'] # Fallback
                
                # Charge only 50% (Deposit)
                deposit_price = unit_price * 0.5
                
                preference_items.append({
                    "title": f"Seña (50%) - {cat['name']}",
                    "quantity": item.get('quantity', 1),
                    "unit_price": float(deposit_price),
                    "currency_id": "ARS"
                })

    conn.commit()
    conn.close()
    
    # Create Mercado Pago Preference if applicable
    init_point = None
    if data.get('payment_method') == 'mercadopago' and preference_items:
        preference_data = {
            "items": preference_items,
            "payer": {
                "name": data.get('customer_name'),
                "email": data.get('customer_email', 'test_user@test.com'),
                "phone": {
                    "area_code": "",
                    "number": data.get('customer_phone')
                },
                "identification": {
                    "type": "DNI",
                    "number": data.get('customer_dni')
                }
            },
            "back_urls": {
                "success": f"{CONFIG['PUBLIC_URL']}/reserva?status=success&reservation_id={reservation_id}",
                "failure": f"{CONFIG['PUBLIC_URL']}/reserva?status=failure&reservation_id={reservation_id}",
                "pending": f"{CONFIG['PUBLIC_URL']}/reserva?status=pending&reservation_id={reservation_id}"
            },
            "auto_return": "approved", # Descomentar en producción (requiere HTTPS/dominio real)
            "external_reference": reservation_id,
            "statement_descriptor": "BICISI RESERVA"
        }
        
        try:
            print(f"DEBUG: Creating MP preference with data: {json.dumps(preference_data, indent=2)}")
            print(f"DEBUG: PUBLIC_URL is: {CONFIG['PUBLIC_URL']}")
            
            preference_response = sdk.preference().create(preference_data)
            preference = preference_response["response"]
            
            if "init_point" not in preference:
                raise Exception(f"MP Error: {json.dumps(preference)}")
                
            init_point = preference["init_point"]
        except Exception as e:
            print(f"Error creating MP preference: {e}")
            return jsonify({"error": f"Error creating payment preference: {str(e)}"}), 500
    
    return jsonify({
        "success": True,
        "reservation_id": reservation_id,
        "message": "Reserva creada exitosamente",
        "init_point": init_point
    })

@app.route('/api/upload-dni', methods=['POST'])
def upload_dni_photo():
    """Public endpoint to upload DNI photo and return as base64 data URI"""
    if 'image' not in request.files:
        return jsonify({"error": "No se proporcionó imagen"}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No se seleccionó archivo"}), 400
    
    # Check extension
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'webp']:
        return jsonify({"error": "Formato de imagen no válido"}), 400
    
    # Read file and convert to base64
    image_data = file.read()
    base64_encoded = base64.b64encode(image_data).decode('utf-8')
    mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    data_uri = f"data:{mime_type};base64,{base64_encoded}"
    
    return jsonify({"success": True, "url": data_uri})

# ==================== ADMIN ROUTES ====================

@app.route('/admin')
def admin():
    """Admin panel or login"""
    if session.get('admin_logged_in'):
        return render_template('admin.html')
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM admins WHERE username = ? AND password = ?",
            (username, hash_password(password))
        )
        admin = cursor.fetchone()
        conn.close()
        
        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin'))
        return render_template('admin_login.html', error="Credenciales inválidas")
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('landing'))

# ==================== ADMIN API ROUTES ====================

@app.route('/api/admin/categories', methods=['GET', 'POST'])
@login_required
def admin_categories():
    """Get or create categories"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        return jsonify(get_categories())
    
    data = request.json
    new_id = str(uuid.uuid4())
    
    cursor.execute('''
        INSERT INTO categories (id, name, description, price_full_day, price_half_day, price_per_hour, stock, image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        new_id,
        data.get('name', ''),
        data.get('description', ''),
        data.get('price_full_day', 0),
        data.get('price_half_day', 0),
        data.get('price_per_hour', 0),
        data.get('stock', 0),
        data.get('image', '/static/images/default-bike.jpg')
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "id": new_id})

@app.route('/api/admin/categories/<category_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_category_detail(category_id):
    """Update or delete a category"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'DELETE':
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    data = request.json
    cursor.execute('''
        UPDATE categories SET
            name = ?, description = ?, price_full_day = ?, price_half_day = ?,
            price_per_hour = ?, stock = ?, image = ?, updated_at = ?
        WHERE id = ?
    ''', (
        data.get('name'),
        data.get('description'),
        data.get('price_full_day'),
        data.get('price_half_day'),
        data.get('price_per_hour'),
        data.get('stock'),
        data.get('image'),
        datetime.now().isoformat(),
        category_id
    ))
    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/reservations')
@login_required
def admin_reservations():
    """Get all reservations"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, GROUP_CONCAT(c.name || ' x' || ri.quantity, ', ') as items_str
        FROM reservations r
        LEFT JOIN reservation_items ri ON r.id = ri.reservation_id
        LEFT JOIN categories c ON ri.category_id = c.id
        GROUP BY r.id
        ORDER BY r.created_at DESC
    ''')
    
    reservations = []
    for row in cursor.fetchall():
        res = dict(row)
        # Get items separately for detailed view
        cursor.execute('''
            SELECT ri.*, c.name as category_name
            FROM reservation_items ri
            JOIN categories c ON ri.category_id = c.id
            WHERE ri.reservation_id = ?
        ''', (res['id'],))
        res['items'] = [dict(item) for item in cursor.fetchall()]
        reservations.append(res)
    
    conn.close()
    return jsonify(reservations)

@app.route('/api/admin/reservations/<reservation_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_reservation_detail(reservation_id):
    """Update or delete a reservation"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'DELETE':
        cursor.execute("DELETE FROM reservation_items WHERE reservation_id = ?", (reservation_id,))
        cursor.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    data = request.json
    updates = []
    params = []
    
    if 'status' in data:
        updates.append("status = ?")
        params.append(data['status'])
    if 'notes' in data:
        updates.append("notes = ?")
        params.append(data['notes'])
    
    if updates:
        params.append(reservation_id)
        cursor.execute(f"UPDATE reservations SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/upload-image', methods=['POST'])
@login_required
def upload_image():
    """Upload category image and return as base64 data URI"""
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Check extension
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'webp']:
        return jsonify({"error": "Formato de imagen no válido"}), 400
    
    # Read file and convert to base64
    image_data = file.read()
    base64_encoded = base64.b64encode(image_data).decode('utf-8')
    mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    data_uri = f"data:{mime_type};base64,{base64_encoded}"
    
    return jsonify({"success": True, "url": data_uri})

@app.route('/api/admin/stats')
@login_required
def admin_stats():
    """Get dashboard statistics"""
    conn = get_db()
    cursor = conn.cursor()
    
    today = datetime.now().date().isoformat()
    
    cursor.execute("SELECT COUNT(*) as total FROM reservations")
    total = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as count FROM reservations WHERE status = 'pending'")
    pending = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM reservations WHERE status = 'confirmed'")
    confirmed = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM reservations WHERE start_date = ?", (today,))
    today_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COALESCE(SUM(total), 0) as revenue FROM reservations WHERE status = 'confirmed'")
    revenue = cursor.fetchone()['revenue']
    
    cursor.execute("SELECT COALESCE(SUM(stock), 0) as stock FROM categories")
    stock = cursor.fetchone()['stock']
    
    cursor.execute("SELECT COUNT(*) as count FROM categories")
    cat_count = cursor.fetchone()['count']
    
    conn.close()
    
    return jsonify({
        "total_reservations": total,
        "pending": pending,
        "confirmed": confirmed,
        "today": today_count,
        "total_revenue": revenue,
        "total_stock": stock,
        "categories_count": cat_count
    })

@app.route('/api/admin/settings', methods=['GET', 'POST', 'PUT'])
@login_required
def admin_settings():
    """Get or update settings"""
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        # Return ONLY what is in the database (overrides)
        # This allows the frontend to show placeholders for the rest
        cursor.execute("SELECT key, value FROM settings")
        db_settings = {row['key']: row['value'] for row in cursor.fetchall()}
        conn.close()
        return jsonify(db_settings)
    
    data = request.json
    for key, value in data.items():
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
    
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/change-password', methods=['POST'])
@login_required
def change_password():
    """Change admin password"""
    data = request.json
    new_password = data.get('new_password')
    
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE admins SET password = ? WHERE username = ?",
        (hash_password(new_password), session.get('admin_username', 'admin'))
    )
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Contraseña actualizada"})

# WhatsApp Payloads
PAYLOAD_MENU = "MENU_PRINCIPAL"
PAYLOAD_PLANES = "VER_PLANES"
PAYLOAD_RESERVAR = "COMO_RESERVAR"
PAYLOAD_UBICACION = "VER_UBICACION"
PAYLOAD_ECO = "DETALLE_ECO"
PAYLOAD_FULL = "DETALLE_FULL"
PAYLOAD_PAGO = "DATOS_PAGO"

def send_whatsapp_message(to, data):
    url = f"https://graph.facebook.com/{WA_VERSION}/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "recipient_type": "individual",
    }
    payload.update(data)
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error enviando mensaje: {e}")

def send_wa_text(to, text):
    data = {"type": "text", "text": {"body": text}}
    send_whatsapp_message(to, data)

def send_wa_buttons(to, text, buttons):
    action_buttons = []
    for btn_id, btn_title in buttons:
        action_buttons.append({
            "type": "reply",
            "reply": {"id": btn_id, "title": btn_title}
        })
    data = {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {"buttons": action_buttons}
        }
    }
    send_whatsapp_message(to, data)

def handle_wa_message(sender, message_body, message_type):
    msg_text = ""
    payload = ""
    settings = get_settings()
    
    if message_type == "text":
        msg_text = message_body["text"]["body"].lower().strip()
        print(f"📩 {sender} escribió: {msg_text}")
    elif message_type == "interactive":
        type_interactive = message_body["interactive"]["type"]
        if type_interactive == "button_reply":
            payload = message_body["interactive"]["button_reply"]["id"]
            title = message_body["interactive"]["button_reply"]["title"]
            msg_text = title
            print(f"🔘 {sender} tocó botón: {title} (ID: {payload})")

    # URL base para links
    base_url = CONFIG.get('PUBLIC_URL', 'http://localhost:5001')

    # Flujo de conversación
    if payload == PAYLOAD_MENU or any(x in msg_text for x in ["hola", "buen dia", "buenas", "inicio", "menu"]):
        welcome_text = settings.get('msg_welcome', '¡Hola! Bienvenidos a BiciSí.')
        buttons = [
            (PAYLOAD_PLANES, "Ver Planes 🚲"),
            (PAYLOAD_RESERVAR, "Cómo Reservar 📝"),
            (PAYLOAD_UBICACION, "Ubicación 📍")
        ]
        send_wa_buttons(sender, welcome_text, buttons)
        return

    if payload == PAYLOAD_PLANES or "planes" in msg_text or "precio" in msg_text:
        text = settings.get('msg_planes', 'Nuestros planes...')
        buttons = [
            (PAYLOAD_ECO, "Más sobre ECO"),
            (PAYLOAD_FULL, "Más sobre FULL"),
            (PAYLOAD_RESERVAR, "Quiero Reservar")
        ]
        send_wa_buttons(sender, text, buttons)
        return

    if payload == PAYLOAD_ECO:
        text = settings.get('msg_eco', 'Detalle ECO...')
        buttons = [(PAYLOAD_RESERVAR, "Reservar ECO"), (PAYLOAD_PLANES, "Ver otras opciones")]
        send_wa_buttons(sender, text, buttons)
        return

    if payload == PAYLOAD_FULL:
        text = settings.get('msg_full', 'Detalle FULL...')
        buttons = [(PAYLOAD_RESERVAR, "Reservar FULL"), (PAYLOAD_PLANES, "Ver otras opciones")]
        send_wa_buttons(sender, text, buttons)
        return

    if payload == PAYLOAD_RESERVAR or "reservar" in msg_text:
        link_text = settings.get('msg_reserva', 'Link de reserva: {url}/reserva').replace('{url}', base_url)
        send_wa_text(sender, link_text)
        
        menu_text = "¿Te gustaría consultar algo más?"
        buttons = [
            (PAYLOAD_PLANES, "Ver Planes 🚲"),
            (PAYLOAD_RESERVAR, "Cómo Reservar 📝"),
            (PAYLOAD_UBICACION, "Ubicación 📍")
        ]
        send_wa_buttons(sender, menu_text, buttons)
        return

    if payload == PAYLOAD_PAGO or "cbu" in msg_text or "alias" in msg_text or "pago" in msg_text:
        header = settings.get('msg_pago_header', '🏦 *Datos Bancarios para la Seña:*')
        text = (
            f"{header}\n\n"
            f"🔹 *Banco:* {settings.get('bank_name', 'Francés BBVA')}\n"
            f"🔹 *Titular:* {settings.get('bank_holder', 'Lucas Brunazzi')}\n"
            f"🔹 *Alias:* {settings.get('bank_alias', 'BICISI.26')}\n"
            f"🔹 *CBU:* {settings.get('bank_cbu', '0170274540000002278483')}\n"
            f"🔹 *Cuenta:* {settings.get('bank_account', '274-22784/8')}\n\n"
            "⚠️ *Importante:* Envía el comprobante por aquí para agendar tu bici."
        )
        send_wa_text(sender, text)
        return

    if payload == PAYLOAD_UBICACION or "donde estan" in msg_text:
        text = settings.get('msg_ubicacion', 'Nuestra ubicación...')
        buttons = [(PAYLOAD_MENU, "Volver al Menú")]
        send_wa_buttons(sender, text, buttons)
        return

    # Respuesta por defecto
    default_text = settings.get('msg_default', 'No entendí tu mensaje.')
    buttons = [(PAYLOAD_MENU, "Ir al Menú"), (PAYLOAD_RESERVAR, "Ayuda / Reservar")]
    send_wa_buttons(sender, default_text, buttons)

@app.route("/webhook", methods=["GET"])
def wa_verify():
    """WhatsApp webhook verification"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def wa_receive():
    """WhatsApp webhook receive messages"""
    data = request.get_json()

    try:
        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for msg in value["messages"]:
                            sender = msg["from"]
                            msg_type = msg["type"]
                            handle_wa_message(sender, msg, msg_type)

        return jsonify(status="ok"), 200

    except Exception as e:
        print(f"Error en webhook: {e}")
        return jsonify(status="error"), 400

# ==================== MAIN ====================

@app.route('/api/reservations/<reservation_id>/confirm_payment', methods=['POST'])
def confirm_reservation_payment(reservation_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('UPDATE reservations SET status = ? WHERE id = ?', ('confirmed', reservation_id))
        conn.commit()
        return jsonify({"success": True, "message": "Pago confirmado exitosamente"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    
    port = CONFIG.get('PORT', 5001)
    debug_mode = CONFIG.get('DEBUG', True)
    public_url = CONFIG.get('PUBLIC_URL', f"http://localhost:{port}")

    print("\n🚲 BiciSí - Sistema Unificado (PROD READY)")
    print("=" * 45)
    print(f"📍 URL Pública/IP:  {public_url}")
    print(f"🔧 Modo:           {'DEBUG / DESARROLLO' if debug_mode else 'PRODUCCIÓN (Waitress)'}")
    print(f"🔧 Puerto:         {port}")
    print("=" * 45 + "\n")

    if debug_mode:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        try:
            from waitress import serve
            print(f"🚀 Iniciando servidor Waitress en puerto {port}...")
            serve(app, host='0.0.0.0', port=port)
        except ImportError:
            print("⚠️ Waitress no está instalado. Instalando...")
            os.system("pip install waitress")
            from waitress import serve
            serve(app, host='0.0.0.0', port=port)
