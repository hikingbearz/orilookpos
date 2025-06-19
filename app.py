# ==============================================================================
# FINAL - app.py dengan Fitur PPN per-Produk
# Perubahan ditandai dengan komentar '--- PERUBAHAN PPN ---'
# --- BARANG & JASA ---: Penambahan fitur untuk membedakan Barang (Goods) dan Jasa (Services)
# --- MODIFIKASI LANGKAH 4 ---: Penyesuaian logika backend sesuai instruksi
# --- PERBAIKAN KASIR ---: Memperbaiki query NULL-unsafe di halaman Kasir
# --- REFRAKTOR KASIR KE SALES ---: Mengganti role 'kasir' menjadi 'sales'
# --- STOCK OPNAME ---: Penambahan fitur untuk stock opname
# ==============================================================================

# ==============================================================================
# BAGIAN 1: IMPOR BARU DAN FUNGSI HELPER UNTUK APLIKASI DESKTOP
# ==============================================================================
import os
import sys
import threading
import socket
import webview  
import re
import shutil
import zipfile 
import pytz
# --- AKHIR PERUBAHAN ---
from babel.dates import format_datetime, format_date, format_time
import click
from flask.cli import with_appcontext

def get_data_path(subfolder=None):
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_path, 'app_data')
    if subfolder:
        path = os.path.join(data_dir, subfolder)
    else:
        path = data_dir
    os.makedirs(path, exist_ok=True)
    return path

# ==============================================================================
# BAGIAN 2: KONFIGURASI APLIKASI FLASK YANG DIMODIFIKASI
# ==============================================================================
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, 
    jsonify, send_from_directory, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required, 
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, SubmitField, SelectField as WTFormsSelectField,
    FloatField, IntegerField, TextAreaField, DateField,
    FieldList, FormField, HiddenField, SelectMultipleField,
    BooleanField,
    RadioField
)
from wtforms.validators import (
    DataRequired, Length, EqualTo, ValidationError,
    NumberRange, Optional, Email, InputRequired
)
from wtforms.widgets import TextArea, ListWidget, CheckboxInput
from functools import wraps
from datetime import datetime, date, timedelta
from sqlalchemy import or_, func as sqlfunc, cast, Date as SQLDate, exc as sqlalchemy_exc, CheckConstraint
from markupsafe import Markup, escape

MINIMUM_STOCK_THRESHOLD = 10
TARGET_TIMEZONE = pytz.timezone('Asia/Jakarta')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app = Flask(__name__)

DB_FILE_PATH = os.path.join(get_data_path(), 'pos_app.db')
UPLOAD_FOLDER_PATH = get_data_path('product_images')
BRANDING_FOLDER_PATH = get_data_path('branding')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'INI_ADALAH_KUNCI_RAHASIA_FINAL_YANG_SANGAT_AMAN_DAN_PANJANG_123'
app.config['WTF_CSRF_ENABLED'] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER_PATH
app.config['BACKUP_FOLDER'] = get_data_path('backups')
app.config['BRANDING_FOLDER'] = BRANDING_FOLDER_PATH

csrf = CSRFProtect(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
login_manager.login_message = "Silakan login untuk mengakses halaman ini."

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==============================================================================
# BAGIAN 3: SEMUA KODE APLIKASI ANDA (MODEL, FORM, RUTE)
# ==============================================================================

@app.template_filter('nl2br')
def nl2br_filter(value):
    if value is None: return ''
    escaped_text = escape(value); result = re.sub(r'(\r\n|\r(?!\n)|\n)', '<br>\n', escaped_text)
    return Markup(result)

@app.template_filter('localtime')
def localtime_filter(utc_dt):
    if not isinstance(utc_dt, datetime): return utc_dt
    if utc_dt.tzinfo is None: utc_dt = pytz.utc.localize(utc_dt)
    local_dt = utc_dt.astimezone(TARGET_TIMEZONE)
    return format_datetime(local_dt, format='dd MMM yyyy HH:mm:ss', locale='id_ID')

@app.template_filter('localdate')
def localdate_filter(utc_dt_or_date):
    if not utc_dt_or_date: return ""
    if isinstance(utc_dt_or_date, datetime):
        if utc_dt_or_date.tzinfo is None: utc_dt_or_date = pytz.utc.localize(utc_dt_or_date)
        local_dt = utc_dt_or_date.astimezone(TARGET_TIMEZONE)
    elif isinstance(utc_dt_or_date, date): local_dt = utc_dt_or_date
    else: return utc_dt_or_date
    return format_date(local_dt, format='dd MMMM yyyy', locale='id_ID')

@app.template_filter('localtimeonly')
def localtimeonly_filter(utc_dt):
    if not isinstance(utc_dt, datetime): return utc_dt
    if utc_dt.tzinfo is None: utc_dt = pytz.utc.localize(utc_dt)
    local_dt = utc_dt.astimezone(TARGET_TIMEZONE)
    return format_time(local_dt, format='HH:mm:ss', locale='id_ID')

# --- MODELS ---
product_categories = db.Table('product_categories',
    db.Column('product_id', db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id', ondelete='CASCADE'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='sales')
    last_login = db.Column(db.DateTime, nullable=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_type = db.Column(db.String(20), nullable=False, default='goods', server_default='goods')
    product_code = db.Column(db.String(20), unique=True, nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    purchase_price = db.Column(db.Float, nullable=True)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=True) 
    image_file = db.Column(db.String(100), nullable=True, default='default_product.png')
    discount_percentage = db.Column(db.Float, nullable=True)
    discount_nominal = db.Column(db.Float, nullable=True)
    discount_start_date = db.Column(SQLDate, nullable=True)
    discount_end_date = db.Column(SQLDate, nullable=True)
    is_taxable = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    categories = db.relationship('Category', secondary=product_categories, backref=db.backref('products', lazy='dynamic'), lazy='dynamic')
    __table_args__ = (
        CheckConstraint(
            "(product_type = 'service' AND stock IS NULL) OR (product_type = 'goods' AND stock IS NOT NULL)", 
            name='ck_product_stock_based_on_type'
        ),
    )
    @property
    def current_selling_price_details(self):
        today = date.today(); original_price = self.price; effective_price = self.price
        active_discount_info = None; is_discount_active = False
        if self.discount_start_date and self.discount_end_date and self.discount_start_date <= today <= self.discount_end_date:
            is_discount_active = True
            if self.discount_percentage and self.discount_percentage > 0:
                discount_amount = (self.discount_percentage / 100) * self.price; effective_price = self.price - discount_amount
                active_discount_info = f"{self.discount_percentage:.0f}%"
            elif self.discount_nominal and self.discount_nominal > 0:
                effective_price = self.price - self.discount_nominal
                active_discount_info = f"Rp {self.discount_nominal:,.0f}".replace(",",".")
            if effective_price < 0: effective_price = 0
        return {'effective_price': effective_price, 'original_price': original_price, 'active_discount_info': active_discount_info, 'is_discount_active': is_discount_active}

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    taxable_subtotal = db.Column(db.Float, nullable=False, default=0.0)
    non_taxable_subtotal = db.Column(db.Float, nullable=False, default=0.0)
    tax_rate_at_transaction = db.Column(db.Float, nullable=False, default=0.0)
    tax_amount = db.Column(db.Float, nullable=False, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cashier = db.relationship('User', backref='transactions')
    items = db.relationship('TransactionItem', backref='transaction', lazy=True, cascade="all, delete-orphan")
    @property
    def total_subtotal(self):
        return self.taxable_subtotal + self.non_taxable_subtotal

class TransactionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_transaction = db.Column(db.Float, nullable=False)
    is_taxed_at_transaction = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    original_price_at_transaction = db.Column(db.Float, nullable=True)
    discount_applied_info = db.Column(db.String(50), nullable=True)
    purchase_price_at_transaction = db.Column(db.Float, nullable=True)
    product = db.relationship('Product', backref='transaction_items')
    @property
    def subtotal(self): return self.quantity * self.price_at_transaction

class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(50), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    stock_before = db.Column(db.Integer, nullable=False)
    stock_after = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    product = db.relationship('Product', backref=db.backref('stock_movements', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('stock_adjustments_made', lazy='dynamic'))

class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text, nullable=True)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    contact_person = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True, unique=False)
    address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), unique=True, nullable=False)
    order_date = db.Column(SQLDate, nullable=False, default=date.today)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Draft')
    total_amount = db.Column(db.Float, nullable=True, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    supplier = db.relationship('Supplier', backref=db.backref('purchase_orders', lazy='dynamic'))
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy='dynamic', cascade="all, delete-orphan")
    creator = db.relationship('User', backref='created_purchase_orders')
    def update_total_amount(self): self.total_amount = sum(item.subtotal for item in self.items.all()) if self.items else 0.0

class PurchaseOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_ordered = db.Column(db.Integer, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    quantity_received = db.Column(db.Integer, nullable=False, default=0)
    product = db.relationship('Product', backref='po_items')
    @property
    def subtotal(self): return self.quantity_ordered * self.purchase_price
    @property
    def quantity_outstanding(self): return self.quantity_ordered - self.quantity_received

# --- STOCK OPNAME: Mulai Model Baru ---
class StockOpname(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    opname_number = db.Column(db.String(50), unique=True, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='In Progress') # In Progress, Completed
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    finalized_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    creator = db.relationship('User', foreign_keys=[created_by_user_id], backref='created_opnames')
    finalizer = db.relationship('User', foreign_keys=[finalized_by_user_id], backref='finalized_opnames')
    items = db.relationship('StockOpnameItem', backref='stock_opname', lazy='dynamic', cascade="all, delete-orphan")

class StockOpnameItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_opname_id = db.Column(db.Integer, db.ForeignKey('stock_opname.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    system_stock_at_opname = db.Column(db.Integer, nullable=False)
    physical_count = db.Column(db.Integer, nullable=True) # Bisa null saat proses hitung

    product = db.relationship('Product')

    @property
    def variance(self):
        if self.physical_count is None:
            return None
        return self.physical_count - self.system_stock_at_opname
# --- STOCK OPNAME: Akhir Model Baru ---


# --- Fungsi Helper ---
def get_setting_value(key, default_value=None):
    setting = AppSetting.query.filter_by(setting_key=key).first()
    return setting.setting_value if setting else (str(default_value) if default_value is not None else None)

def get_or_create_setting(key, default_value):
    setting = AppSetting.query.filter_by(setting_key=key).first()
    if not setting: 
        setting = AppSetting(setting_key=key, setting_value=str(default_value))
        db.session.add(setting)
    return setting

def initialize_default_settings():
    with app.app_context():
        settings_to_init = {
            'store_name': 'Toko Saya POS', 
            'store_address': 'Jl. Contoh No. 123', 
            'store_phone': '081234567890', 
            'default_tax_rate': '11.0'
        }
        for key, value in settings_to_init.items(): 
            get_or_create_setting(key, value)
        db.session.commit()

def generate_po_number():
    today_str = date.today().strftime("%Y%m%d")
    last_po = PurchaseOrder.query.filter(PurchaseOrder.po_number.like(f'PO-{today_str}-%')).order_by(PurchaseOrder.id.desc()).first()
    new_suffix = 1
    if last_po:
        try: new_suffix = int(last_po.po_number.split('-')[-1]) + 1
        except: pass
    return f'PO-{today_str}-{new_suffix:04d}'

# --- STOCK OPNAME: Mulai Fungsi Helper Baru ---
def generate_opname_number():
    today_str = date.today().strftime("%Y%m%d")
    last_so = StockOpname.query.filter(StockOpname.opname_number.like(f'SO-{today_str}-%')).order_by(StockOpname.id.desc()).first()
    new_suffix = 1
    if last_so:
        try:
            new_suffix = int(last_so.opname_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            pass
    return f'SO-{today_str}-{new_suffix:04d}'
# --- STOCK OPNAME: Akhir Fungsi Helper Baru ---

def generate_product_code():
    last_product = Product.query.order_by(sqlfunc.cast(Product.product_code, db.Integer).desc()).first()
    new_number = 1
    if last_product and last_product.product_code and last_product.product_code.isdigit():
        try:
            last_number = int(last_product.product_code)
            new_number = last_number + 1
        except ValueError: pass
    new_code = f"{new_number:05d}"
    while Product.query.filter_by(product_code=new_code).first():
        new_number += 1
        new_code = f"{new_number:05d}"
    return new_code

def save_picture(form_picture):
    if not form_picture: return None
    random_hex = os.urandom(8).hex()
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext.lower()
    picture_path = os.path.join(app.config['UPLOAD_FOLDER'], picture_fn)
    form_picture.save(picture_path)
    return picture_fn

# --- FUNGSI HELPER UNTUK LAPORAN ---
def get_sales_by_date_range_data(start_date_obj, end_date_obj):
    """Mengambil data laporan penjualan berdasarkan rentang tanggal."""
    start_range_local = TARGET_TIMEZONE.localize(datetime.combine(start_date_obj, datetime.min.time()))
    end_range_local = TARGET_TIMEZONE.localize(datetime.combine(end_date_obj, datetime.max.time()))
    start_range_utc = start_range_local.astimezone(pytz.utc)
    end_range_utc = end_range_local.astimezone(pytz.utc)

    transactions_in_range = db.session.query(Transaction, User.username).join(User, Transaction.user_id == User.id).filter(Transaction.timestamp.between(start_range_utc, end_range_utc)).order_by(Transaction.timestamp.desc()).all()
    grand_total_sales = db.session.query(sqlfunc.sum(Transaction.total_amount)).filter(Transaction.timestamp.between(start_range_utc, end_range_utc)).scalar() or 0.0
    total_transactions_count = len(transactions_in_range)
    
    return {
        'start_date_formatted': format_date(start_date_obj, format='dd MMMM yyyy', locale='id_ID'),
        'end_date_formatted': format_date(end_date_obj, format='dd MMMM yyyy', locale='id_ID'),
        'transactions_with_cashier': transactions_in_range,
        'grand_total_sales': grand_total_sales,
        'total_transactions': total_transactions_count,
        'has_data': bool(transactions_in_range)
    }

def get_sales_by_product_data(start_obj, end_obj):
    """Mengambil data laporan penjualan per produk berdasarkan rentang tanggal."""
    start_range_local = TARGET_TIMEZONE.localize(datetime.combine(start_obj, datetime.min.time()))
    end_range_local = TARGET_TIMEZONE.localize(datetime.combine(end_obj, datetime.max.time()))
    start_range_utc = start_range_local.astimezone(pytz.utc)
    end_range_utc = end_range_local.astimezone(pytz.utc)

    sales_query_result = db.session.query(
        Product.name.label('product_name'),
        sqlfunc.sum(TransactionItem.quantity).label('total_quantity_sold'),
        sqlfunc.sum(TransactionItem.quantity * TransactionItem.price_at_transaction).label('total_revenue')
    ).join(TransactionItem.transaction).join(Product).filter(
        Transaction.timestamp.between(start_range_utc, end_range_utc)
    ).group_by(Product.id, Product.name).order_by(
        sqlfunc.sum(TransactionItem.quantity * TransactionItem.price_at_transaction).desc()
    ).all()
    
    products_sales = [{'product_name': r.product_name, 'total_quantity_sold': r.total_quantity_sold, 'total_revenue': r.total_revenue} for r in sales_query_result]
    
    return {
        'start_date_formatted': format_date(start_obj, format='dd MMMM yyyy', locale='id_ID'),
        'end_date_formatted': format_date(end_obj, format='dd MMMM yyyy', locale='id_ID'),
        'products_sales': products_sales,
        'has_data': bool(products_sales)
    }

# --- Login Manager & Context Processor ---
@login_manager.user_loader
def load_user(user_id): 
    return User.query.get(int(user_id))

@app.context_processor
def utility_processor():
    current_app_settings = {}
    try:
        if db.engine and db.inspect(db.engine).has_table(AppSetting.__tablename__):
             current_app_settings['store_name'] = get_setting_value('store_name', 'Toko POS')
        else: current_app_settings['store_name'] = 'Toko POS (Setup)'
    except sqlalchemy_exc.SQLAlchemyError as e:
        app.logger.warning(f"SQLAlchemyError loading app settings into context: {e}")
        current_app_settings['store_name'] = 'Toko POS (DB Error)'
    except Exception as e:
        app.logger.warning(f"General error loading app settings into context: {e}")
        current_app_settings['store_name'] = 'Toko POS (Error)'
    return dict(get_setting_value=get_setting_value, app_settings=current_app_settings)

# --- FORMS ---
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    role = WTFormsSelectField('Role', choices=[('sales', 'Sales'), ('admin', 'Admin'), ('inventory', 'Inventory'), ('manager', 'Manajer')], validators=[DataRequired()])
    submit = SubmitField('Register')
    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first(): raise ValidationError('Username sudah digunakan.')

class AdminAddUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    password = PasswordField('Password Awal', validators=[DataRequired(), Length(min=6)])
    role = WTFormsSelectField('Role', choices=[('sales', 'Sales'), ('admin', 'Admin'), ('inventory', 'Inventory'), ('manager', 'Manajer')], validators=[DataRequired()])
    submit = SubmitField('Tambah Pengguna')
    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first(): raise ValidationError('Username sudah digunakan.')

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    password = PasswordField('Password Baru (Kosongkan jika tidak diubah)', validators=[Optional(), Length(min=6)])
    role = WTFormsSelectField('Role', choices=[('sales', 'Sales'), ('admin', 'Admin'), ('inventory', 'Inventory'), ('manager', 'Manajer')], validators=[DataRequired()])
    submit = SubmitField('Simpan Perubahan')
    def __init__(self, original_username=None, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
    def validate_username(self, username):
        if username.data.lower() != self.original_username.lower():
            if User.query.filter(User.username.ilike(username.data)).first(): raise ValidationError('Username tersebut sudah digunakan. Silakan pilih yang lain.')

class ProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    password = PasswordField('Password Baru (Kosongkan jika tidak diubah)', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('Konfirmasi Password Baru', validators=[EqualTo('password', message='Password harus sama.')])
    submit = SubmitField('Simpan Perubahan Profil')
    def __init__(self, original_username=None, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
    def validate_username(self, username):
        if username.data.lower() != self.original_username.lower():
            if User.query.filter(User.username.ilike(username.data)).first(): raise ValidationError('Username tersebut sudah digunakan. Silakan pilih yang lain.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class CategoryForm(FlaskForm):
    name = StringField('Nama Kategori', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Deskripsi Kategori', validators=[Optional()])
    submit = SubmitField('Simpan Kategori')
    def __init__(self, original_category_name=None, *args, **kwargs):
        super(CategoryForm, self).__init__(*args, **kwargs)
        self.original_category_name = original_category_name
    def validate_name(self, name):
        if name.data != self.original_category_name:
            if Category.query.filter_by(name=name.data).first(): raise ValidationError('Nama kategori sudah ada. Silakan gunakan nama lain.')

class ProductForm(FlaskForm):
    product_type = RadioField('Tipe Produk', choices=[('goods', 'Barang Fisik (Punya Stok)'), ('service', 'Jasa / Layanan (Tidak Punya Stok)')], default='goods', validators=[DataRequired()])
    name = StringField('Nama Produk', validators=[DataRequired(), Length(min=3, max=120)])
    description = TextAreaField('Deskripsi', validators=[Optional()])
    purchase_price = FloatField('Harga Beli', validators=[Optional(), NumberRange(min=0)])
    price = FloatField('Harga Jual Normal (Sebelum Diskon)', validators=[DataRequired(), NumberRange(min=0)])
    is_taxable = BooleanField('Produk ini dikenakan PPN', default=True)
    stock = IntegerField('Stok Awal', validators=[Optional(), NumberRange(min=0)])
    categories = SelectMultipleField('Kategori Produk', coerce=int, widget=ListWidget(prefix_label=False), option_widget=CheckboxInput(), validators=[Optional()])
    image = FileField('Gambar Produk (Opsional)', validators=[FileAllowed(list(ALLOWED_EXTENSIONS), 'Hanya gambar!'), Optional()])
    discount_percentage = FloatField('Diskon Persentase (%)', validators=[Optional(), NumberRange(min=0, max=100)])
    discount_nominal = FloatField('Diskon Nominal (Rp)', validators=[Optional(), NumberRange(min=0)])
    discount_start_date = DateField('Tanggal Mulai Diskon', format='%Y-%m-%d', validators=[Optional()])
    discount_end_date = DateField('Tanggal Akhir Diskon', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Simpan Produk')
    def validate(self, **kwargs):
        if not super(ProductForm, self).validate(**kwargs): return False
        is_valid = True
        if self.product_type.data == 'goods':
            if self.stock.data is None: self.stock.errors.append('Stok wajib diisi untuk Barang Fisik.'); is_valid = False
            if self.purchase_price.data is None: self.purchase_price.errors.append('Harga beli wajib diisi untuk Barang Fisik.'); is_valid = False
        if self.discount_percentage.data and self.discount_nominal.data: msg = "Hanya isi diskon persentase atau nominal."; self.discount_percentage.errors.append(msg); self.discount_nominal.errors.append(msg); is_valid = False
        if (self.discount_start_date.data and not self.discount_end_date.data) or (not self.discount_start_date.data and self.discount_end_date.data):
            if not self.discount_start_date.data: self.discount_start_date.errors.append("Isi tanggal mulai jika tanggal akhir diisi.")
            if not self.discount_end_date.data: self.discount_end_date.errors.append("Isi tanggal akhir jika tanggal mulai diisi.")
            is_valid = False
        if self.discount_start_date.data and self.discount_end_date.data and self.discount_start_date.data > self.discount_end_date.data: self.discount_start_date.errors.append("Tanggal mulai tidak boleh setelah tanggal akhir."); is_valid = False
        if (self.discount_percentage.data or self.discount_nominal.data) and (not self.discount_start_date.data or not self.discount_end_date.data):
            msg = "Tanggal diskon wajib diisi jika ada nilai diskon."
            if not self.discount_start_date.data: self.discount_start_date.errors.append(msg)
            if not self.discount_end_date.data: self.discount_end_date.errors.append(msg)
            is_valid = False
        return is_valid

class StockAdjustmentForm(FlaskForm):
    product_search = StringField('Pilih Produk', validators=[DataRequired("Ketik nama atau kode produk untuk mencari.")])
    product_id = HiddenField(validators=[DataRequired(message="Anda harus memilih produk dari hasil pencarian.")])
    adjustment_type = WTFormsSelectField('Jenis Penyesuaian', choices=[('in', 'Tambah Stok'), ('out', 'Kurangi Stok')], validators=[DataRequired(message="Jenis penyesuaian harus dipilih.")])
    quantity = IntegerField('Jumlah', validators=[DataRequired(message="Jumlah tidak boleh kosong."), NumberRange(min=1, message="Jumlah harus minimal 1.")])
    notes = TextAreaField('Catatan/Alasan Penyesuaian', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Proses Penyesuaian Stok')

class SettingsForm(FlaskForm):
    store_name = StringField('Nama Toko', validators=[DataRequired(), Length(max=100)])
    store_address = TextAreaField('Alamat Toko', validators=[Optional(), Length(max=255)])
    store_phone = StringField('Telepon Toko', validators=[Optional(), Length(max=20)])
    default_tax_rate = FloatField('Tarif PPN Default (%)', default=0.0, validators=[Optional(), NumberRange(min=0, max=100, message="Tarif PPN antara 0 dan 100")])
    store_logo = FileField('Upload Logo Toko (Opsional, .png/.jpg/.gif)', validators=[FileAllowed(['png', 'jpg', 'jpeg', 'gif'], 'Hanya file gambar yang diizinkan!'), Optional()])
    login_background_image = FileField('Upload Background Halaman Login (Opsional, .jpg/.png)', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Hanya file .jpg atau .png yang diizinkan!'), Optional()])
    submit = SubmitField('Simpan Pengaturan')

class SupplierForm(FlaskForm):
    name = StringField('Nama Supplier', validators=[DataRequired(), Length(min=3, max=150)])
    contact_person = StringField('Nama Kontak Person', validators=[Optional(), Length(max=100)])
    phone = StringField('Nomor Telepon', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Email(message="Format email tidak valid."), Length(max=120)])
    address = TextAreaField('Alamat', validators=[Optional()])
    notes = TextAreaField('Catatan Tambahan', validators=[Optional()])
    submit = SubmitField('Simpan Supplier')
    def __init__(self, original_supplier_name=None, original_supplier_email=None, *args, **kwargs):
        super(SupplierForm, self).__init__(*args, **kwargs)
        self.original_supplier_name = original_supplier_name; self.original_supplier_email = original_supplier_email
    def validate_name(self, name):
        if name.data != self.original_supplier_name:
            if Supplier.query.filter_by(name=name.data).first(): raise ValidationError('Nama supplier sudah ada. Gunakan nama lain.')
    def validate_email(self, email):
        if email.data and email.data != self.original_supplier_email:
            if Supplier.query.filter_by(email=email.data).first(): raise ValidationError('Email supplier sudah digunakan.')

class PurchaseOrderItemForm(FlaskForm):
    product_id = WTFormsSelectField('Produk', coerce=int, validators=[DataRequired(message="Produk harus dipilih.")])
    quantity_ordered = IntegerField('Jumlah Dipesan', validators=[InputRequired(message="Jumlah harus diisi."), NumberRange(min=1, message="Jumlah min. 1")])
    purchase_price = FloatField('Harga Beli Satuan (Rp)', validators=[InputRequired(message="Harga beli harus diisi."), NumberRange(min=0, message="Harga beli tidak valid")])
    class Meta: csrf = False

class PurchaseOrderForm(FlaskForm):
    supplier_id = WTFormsSelectField('Supplier', coerce=int, validators=[DataRequired(message="Supplier harus dipilih.")])
    order_date = DateField('Tanggal Pesanan', format='%Y-%m-%d', default=date.today, validators=[DataRequired()])
    status = WTFormsSelectField('Status PO', choices=[('Draft', 'Draft'), ('Submitted', 'Submitted to Supplier'), ('Approved', 'Approved'), ('Partially Received', 'Diterima Sebagian'), ('Completed', 'Selesai'), ('Cancelled', 'Dibatalkan')], default='Draft', validators=[DataRequired()])
    notes = TextAreaField('Catatan Tambahan PO', validators=[Optional()])
    items = FieldList(FormField(PurchaseOrderItemForm), min_entries=1, label="Item Produk")
    submit = SubmitField('Simpan Purchase Order')

class GoodsReceiptItemForm(FlaskForm):
    product_id = HiddenField('Product ID')
    product_name = StringField('Nama Produk', render_kw={'readonly': True, 'class':'form-control-plaintext'})
    quantity_ordered = IntegerField('Dipesan', render_kw={'readonly': True, 'class':'form-control-plaintext text-center'})
    quantity_already_received = IntegerField('Sudah Diterima', render_kw={'readonly': True, 'class':'form-control-plaintext text-center'})
    quantity_outstanding = IntegerField('Sisa Belum Diterima', render_kw={'readonly': True, 'class':'form-control-plaintext text-center'})
    quantity_received_now = IntegerField('Jumlah Diterima Sekarang', default=0, validators=[InputRequired(message="Isi jumlah (0 jika tidak ada)."), NumberRange(min=0, message="Jumlah tidak boleh negatif.")])
    notes = StringField('Catatan Item', validators=[Optional(), Length(max=100)])
    class Meta: csrf = False

class GoodsReceiptForm(FlaskForm):
    po_number = StringField('Nomor Purchase Order', render_kw={'readonly': True})
    supplier_name = StringField('Nama Supplier', render_kw={'readonly': True})
    receipt_date = DateField('Tanggal Penerimaan', default=date.today, format='%Y-%m-%d', validators=[DataRequired()])
    delivery_order_ref = StringField('No. Surat Jalan Supplier', validators=[Optional(), Length(max=50)])
    notes = TextAreaField('Catatan Penerimaan Global', validators=[Optional()])
    items = FieldList(FormField(GoodsReceiptItemForm), label="Item Diterima")
    submit = SubmitField('Proses Penerimaan Barang')
    def validate_items(self, items_field):
        all_valid = True
        for item_entry in items_field.entries:
            qty_now = int(item_entry.form.quantity_received_now.data) if item_entry.form.quantity_received_now.data is not None else 0
            qty_outstanding = int(item_entry.form.quantity_outstanding.data) if item_entry.form.quantity_outstanding.data is not None else 0
            if qty_now > qty_outstanding:
                item_entry.form.quantity_received_now.errors.append(f"Diterima ({qty_now}) > Sisa ({qty_outstanding})."); all_valid = False
        return all_valid

# --- STOCK OPNAME: Mulai Form Baru ---
class StockOpnameItemForm(FlaskForm):
    item_id = HiddenField()
    product_name = StringField('Produk', render_kw={'readonly': True, 'class': 'form-control-plaintext'})
    system_stock = IntegerField('Stok Sistem', render_kw={'readonly': True, 'class': 'form-control-plaintext text-center'})
    physical_count = IntegerField('Hitungan Fisik', validators=[Optional(), NumberRange(min=0, message="Jumlah tidak boleh negatif.")], render_kw={'class': 'form-control form-control-sm text-center physical-count-input'})
    
    class Meta:
        csrf = False

class StockOpnameForm(FlaskForm):
    notes = TextAreaField('Catatan Opname', validators=[Optional()])
    items = FieldList(FormField(StockOpnameItemForm), min_entries=0)
    submit_progress = SubmitField('Simpan Progres')
    submit_finalize = SubmitField('Finalisasi & Sesuaikan Stok')
# --- STOCK OPNAME: Akhir Form Baru ---


# --- DECORATOR ---
def role_required(required_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated: return login_manager.unauthorized()
            roles_to_check = [required_roles] if isinstance(required_roles, str) else required_roles
            if not isinstance(roles_to_check, (list, tuple)):
                flash("Konfigurasi izin internal error.", "danger"); return redirect(url_for('index'))
            if current_user.role not in roles_to_check:
                flash(f"Anda tidak memiliki izin. Role yang diizinkan: {', '.join(roles_to_check)}.", "danger"); return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- ROUTES ---
@app.route('/')
@app.route('/home')
def index(): 
    return render_template('index.html', title='Home')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        new_user = User(username=form.username.data, role=form.role.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user); db.session.commit()
        flash('Akun berhasil dibuat! Silakan login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Login berhasil!', 'success')
            return redirect(request.args.get('next') or url_for('index'))
        else: flash('Login gagal. Periksa username dan password Anda.', 'danger')
    return render_template('login.html', title='LOGIN', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = current_user
    form = ProfileForm(original_username=user.username)
    if form.validate_on_submit():
        user.username = form.username.data
        if form.password.data: user.set_password(form.password.data)
        db.session.commit()
        flash('Profil Anda telah berhasil diperbarui!', 'success')
        return redirect(url_for('edit_profile'))
    elif request.method == 'GET':
        form.username.data = user.username
    return render_template('admin/edit_profile.html', title='Edit Profil Saya', form=form)

def get_local_today():
    return datetime.now(TARGET_TIMEZONE).date()

@app.route('/dashboard')
@login_required
def dashboard():
    low_stock_products = []
    total_sales_today = 0
    total_transactions_today = 0
    best_selling_products_last_30_days = []

    if current_user.role in ['admin', 'inventory', 'manager', 'sales']:
        low_stock_products = Product.query.filter(
            Product.product_type == 'goods', 
            Product.stock > 0,
            Product.stock <= MINIMUM_STOCK_THRESHOLD
        ).order_by(Product.stock.asc()).all()

    if current_user.role in ['admin', 'manager', 'sales']:
        today_local = get_local_today()
        start_of_day_local = TARGET_TIMEZONE.localize(datetime.combine(today_local, datetime.min.time()))
        end_of_day_local = TARGET_TIMEZONE.localize(datetime.combine(today_local, datetime.max.time()))
        start_of_day_utc = start_of_day_local.astimezone(pytz.utc)
        end_of_day_utc = end_of_day_local.astimezone(pytz.utc)

        total_sales_today = db.session.query(
            sqlfunc.sum(Transaction.total_amount)
        ).filter(
            Transaction.timestamp.between(start_of_day_utc, end_of_day_utc)
        ).scalar() or 0.0
        
        total_transactions_today = db.session.query(
            sqlfunc.count(Transaction.id)
        ).filter(
            Transaction.timestamp.between(start_of_day_utc, end_of_day_utc)
        ).scalar() or 0
        
        end_date_local = today_local
        start_date_local = end_date_local - timedelta(days=29)

        start_range_local = TARGET_TIMEZONE.localize(datetime.combine(start_date_local, datetime.min.time()))
        end_range_local = TARGET_TIMEZONE.localize(datetime.combine(end_date_local, datetime.max.time()))
        start_range_utc = start_range_local.astimezone(pytz.utc)
        end_range_utc = end_range_local.astimezone(pytz.utc)

        best_selling_products_last_30_days = db.session.query(
            Product.name.label('product_name'),
            Product.id.label('product_id'),
            sqlfunc.sum(TransactionItem.quantity).label('total_sold')
        ).join(
            TransactionItem, Product.id == TransactionItem.product_id
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.timestamp.between(start_range_utc, end_range_utc)
        ).group_by(
            Product.id, Product.name
        ).order_by(
            sqlfunc.sum(TransactionItem.quantity).desc()
        ).limit(5).all()
    
    return render_template('dashboard.html', 
                           title='Dashboard', 
                           low_stock_products=low_stock_products,
                           MINIMUM_STOCK_THRESHOLD=MINIMUM_STOCK_THRESHOLD,
                           total_sales_today=total_sales_today,
                           total_transactions_today=total_transactions_today,
                           best_selling_products=best_selling_products_last_30_days)

@app.route('/api/dashboard/daily_sales_chart')
@login_required
@role_required(['admin', 'manager', 'sales'])
def daily_sales_chart_data():
    labels = []; sales_values = []
    today_local = get_local_today()
    for i in range(6, -1, -1):
        target_date_local = today_local - timedelta(days=i)
        start_of_day_local = TARGET_TIMEZONE.localize(datetime.combine(target_date_local, datetime.min.time()))
        end_of_day_local = TARGET_TIMEZONE.localize(datetime.combine(target_date_local, datetime.max.time()))
        start_of_day_utc = start_of_day_local.astimezone(pytz.utc)
        end_of_day_utc = end_of_day_local.astimezone(pytz.utc)
        daily_total = db.session.query(sqlfunc.sum(Transaction.total_amount)).filter(Transaction.timestamp.between(start_of_day_utc, end_of_day_utc)).scalar() or 0.0
        labels.append(target_date_local.strftime('%a, %d %b'))
        sales_values.append(daily_total)
    chart_data = {'labels': labels, 'datasets': [{'label': 'Total Penjualan Harian (Rp)', 'data': sales_values, 'backgroundColor': 'rgba(75, 192, 192, 0.2)', 'borderColor': 'rgba(75, 192, 192, 1)', 'borderWidth': 1, 'fill': True, 'tension': 0.1}]}
    return jsonify(chart_data)

@app.route('/admin/users')
@login_required
@role_required('admin')
def manage_users():
    users = User.query.order_by(User.id).all()
    return render_template('admin/manage_users.html', title='Kelola Pengguna', users=users)

@app.route('/admin/user/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_user():
    form = AdminAddUserForm()
    if form.validate_on_submit():
        new_user = User(username=form.username.data, role=form.role.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user); db.session.commit()
        flash(f'Pengguna {form.username.data} berhasil ditambahkan.', 'success')
        return redirect(url_for('manage_users'))
    return render_template('admin/add_user_form.html', title='Tambah Pengguna Baru', form=form, legend='Tambah Pengguna Baru')

@app.route('/admin/user/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Anda tidak dapat mengedit akun Anda sendiri dari halaman ini. Gunakan halaman "Edit Profil".', 'warning')
        return redirect(url_for('manage_users'))
    form = EditUserForm(original_username=user.username)
    if form.validate_on_submit():
        user.username = form.username.data; user.role = form.role.data
        if form.password.data: user.set_password(form.password.data)
        db.session.commit()
        flash(f'Data pengguna "{user.username}" telah berhasil diperbarui!', 'success')
        return redirect(url_for('manage_users'))
    elif request.method == 'GET':
        form.username.data = user.username; form.role.data = user.role
    return render_template('admin/edit_user.html', title='Edit Pengguna', form=form, user=user)

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    if user_id == current_user.id:
        flash('Anda tidak dapat menghapus akun Anda sendiri!', 'danger'); return redirect(url_for('manage_users'))
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.transactions:
        flash(f'Pengguna "{user_to_delete.username}" tidak dapat dihapus karena memiliki riwayat transaksi.', 'danger'); return redirect(url_for('manage_users'))
    username = user_to_delete.username
    db.session.delete(user_to_delete); db.session.commit()
    flash(f'Pengguna "{username}" telah berhasil dihapus.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/admin/categories')
@login_required
@role_required(['admin', 'inventory', 'manager'])
def manage_categories():
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin/manage_categories.html', title='Kelola Kategori Produk', categories=categories)

@app.route('/admin/category/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def add_category():
    form = CategoryForm()
    if form.validate_on_submit():
        new_category = Category(name=form.name.data, description=form.description.data)
        db.session.add(new_category); db.session.commit()
        flash(f'Kategori "{new_category.name}" berhasil ditambahkan.', 'success')
        return redirect(url_for('manage_categories'))
    return render_template('admin/category_form.html', title='Tambah Kategori Baru', form=form, legend='Tambah Kategori Baru')

@app.route('/admin/category/edit/<int:category_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category, original_category_name=category.name)
    if form.validate_on_submit():
        form.populate_obj(category)
        db.session.commit()
        flash(f'Kategori "{category.name}" berhasil diperbarui.', 'success')
        return redirect(url_for('manage_categories'))
    return render_template('admin/category_form.html', title='Edit Kategori', form=form, legend=f'Edit Kategori: {category.name}')

@app.route('/admin/category/delete/<int:category_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    if category.products.first():
        flash(f'Kategori "{category.name}" tidak bisa dihapus karena masih digunakan oleh produk.', 'danger'); return redirect(url_for('manage_categories'))
    db.session.delete(category); db.session.commit()
    flash(f'Kategori "{category.name}" berhasil dihapus.', 'success')
    return redirect(url_for('manage_categories'))


@app.route('/admin/products')
@login_required
@role_required(['admin', 'inventory', 'manager', 'sales'])
def manage_products():
    page = request.args.get('page', 1, type=int); PER_PAGE = 10
    search_query = request.args.get('q', '').strip()
    category_id_str = request.args.get('category_id', '')
    query = Product.query
    if search_query:
        search_filter = or_(Product.name.ilike(f'%{search_query}%'), Product.product_code.ilike(f'%{search_query}%'))
        query = query.filter(search_filter)
    current_category_id = None
    if category_id_str.isdigit():
        current_category_id = int(category_id_str)
        query = query.filter(Product.categories.any(id=current_category_id))
    all_categories = Category.query.order_by(Category.name).all()
    products_pagination = query.order_by(Product.name).paginate(page=page, per_page=PER_PAGE, error_out=False)
    return render_template('admin/manage_products.html', title='Kelola Produk', products_pagination=products_pagination, MINIMUM_STOCK_THRESHOLD=MINIMUM_STOCK_THRESHOLD, all_categories=all_categories, search_query=search_query, current_category_id=current_category_id)

@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory'])
def add_product():
    form = ProductForm()
    form.categories.choices = [(cat.id, cat.name) for cat in Category.query.order_by(Category.name).all()]
    
    if form.validate_on_submit():
        image_filename = 'default_product.png'
        if form.image.data and allowed_file(form.image.data.filename):
            image_filename = save_picture(form.image.data)
        elif form.image.data: 
            flash('Tipe file gambar tidak diizinkan!', 'danger')
            return render_template('admin/product_form.html', title='Tambah Produk Baru', form=form, legend='Tambah Produk Baru')
        
        product_type = form.product_type.data
        new_product = Product(
            product_type=product_type,
            product_code=generate_product_code(),
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            is_taxable=form.is_taxable.data,
            image_file=image_filename,
            discount_percentage=form.discount_percentage.data,
            discount_nominal=form.discount_nominal.data,
            discount_start_date=form.discount_start_date.data,
            discount_end_date=form.discount_end_date.data,
            stock=form.stock.data if product_type == 'goods' else None,
            purchase_price=form.purchase_price.data if product_type == 'goods' else None
        )
        
        for category_id in form.categories.data:
            category = Category.query.get(category_id)
            if category: new_product.categories.append(category)
            
        db.session.add(new_product)
        db.session.flush()

        if new_product.product_type == 'goods' and new_product.stock > 0:
            db.session.add(StockMovement(
                product_id=new_product.id, 
                type='initial', 
                quantity_change=new_product.stock, 
                stock_before=0, 
                stock_after=new_product.stock, 
                notes='Stok awal produk baru', 
                user_id=current_user.id
            ))
            
        db.session.commit()
        flash('Produk baru berhasil ditambahkan!', 'success')
        return redirect(url_for('manage_products'))
        
    return render_template('admin/product_form.html', title='Tambah Produk Baru', form=form, legend='Tambah Produk Baru')

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory'])
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    original_product_type = product.product_type
    
    form = ProductForm(obj=product)
    form.stock.render_kw = {'readonly': True, 'title': 'Ubah stok melalui menu Penyesuaian Stok. Tidak berlaku untuk jasa.'}
    form.categories.choices = [(cat.id, cat.name) for cat in Category.query.order_by(Category.name).all()]
    current_image_on_load = product.image_file
    
    if request.method == 'GET':
        form.categories.data = [cat.id for cat in product.categories.all()]
        form.discount_start_date.data = product.discount_start_date
        form.discount_end_date.data = product.discount_end_date
        
    if form.validate_on_submit():
        image_filename_to_save = current_image_on_load
        if form.image.data:
            if allowed_file(form.image.data.filename):
                if current_image_on_load and current_image_on_load != 'default_product.png':
                    try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], current_image_on_load))
                    except OSError as e: app.logger.error(f"Error deleting old image {current_image_on_load}: {e}")
                image_filename_to_save = save_picture(form.image.data)
            else: flash('Tipe file gambar tidak diizinkan! Gambar tidak diubah.', 'warning')

        new_product_type = form.product_type.data

        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.is_taxable = form.is_taxable.data
        product.image_file = image_filename_to_save if image_filename_to_save else 'default_product.png'
        product.discount_percentage = form.discount_percentage.data
        product.discount_nominal = form.discount_nominal.data
        product.discount_start_date = form.discount_start_date.data
        product.discount_end_date = form.discount_end_date.data
        
        product.product_type = new_product_type

        if new_product_type == 'goods':
            if original_product_type == 'service':
                product.stock = 0
            product.purchase_price = form.purchase_price.data
        
        else:
            product.stock = None
            product.purchase_price = None

        product.categories = []
        for category_id in form.categories.data:
            category = Category.query.get(category_id)
            if category: product.categories.append(category)
        
        try:
            db.session.commit()
            flash('Produk berhasil diperbarui!', 'success')
            return redirect(url_for('manage_products'))
        except sqlalchemy_exc.IntegrityError as e:
            db.session.rollback()
            app.logger.error(f"IntegrityError during product edit for ID {product_id}: {e}")
            flash('Gagal memperbarui produk. Terjadi error integritas data. Periksa kembali input Anda.', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"General error during product edit for ID {product_id}: {e}")
            flash(f'Gagal memperbarui produk: {e}', 'danger')
        
    return render_template('admin/product_form.html', title='Edit Produk', form=form, legend=f'Edit Produk: {product.name}', current_image=current_image_on_load)


@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if TransactionItem.query.filter_by(product_id=product.id).first():
        flash(f'Produk "{product.name}" tidak dapat dihapus karena telah tercatat dalam transaksi penjualan. Pertimbangkan untuk menonaktifkan produk.', 'danger'); return redirect(url_for('manage_products'))
    stock_movements_list = product.stock_movements.all()
    allow_delete = False
    if not stock_movements_list: allow_delete = True
    elif len(stock_movements_list) == 1 and stock_movements_list[0].type == 'initial': allow_delete = True
    if not allow_delete and stock_movements_list:
        flash(f'Produk "{product.name}" tidak dapat dihapus karena memiliki riwayat stok (selain stok awal). Pertimbangkan untuk menonaktifkan produk.', 'danger'); return redirect(url_for('manage_products'))
    if allow_delete and stock_movements_list:
        for sm in stock_movements_list: db.session.delete(sm)
    product.categories = []; db.session.delete(product)
    try:
        db.session.commit()
        flash(f'Produk "{product.name}" berhasil dihapus.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menghapus produk: {str(e)}', 'danger')
        app.logger.error(f"Error deleting product {product_id}: {e}")
    return redirect(url_for('manage_products'))

@app.route('/admin/stock/adjust', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def adjust_stock():
    form = StockAdjustmentForm()
    if request.method == 'GET':
        product_id_to_select = request.args.get('product_id', type=int)
        if product_id_to_select:
            product = Product.query.get(product_id_to_select)
            if product:
                if product.product_type != 'goods':
                    flash(f"Penyesuaian stok tidak berlaku untuk produk Jasa/Layanan ('{product.name}').", "warning")
                else:
                    form.product_id.data = product.id
                    form.product_search.data = f"({product.product_code}) {product.name}"
            else: flash(f"Produk ID {product_id_to_select} tidak valid.", "warning")

    if form.validate_on_submit():
        product = Product.query.get_or_404(form.product_id.data)
        if product.product_type == 'service':
            flash(f"Tidak dapat menyesuaikan stok untuk Jasa/Layanan: '{product.name}'.", 'danger')
            return redirect(url_for('manage_products'))
        
        quantity_to_adjust = form.quantity.data; adj_type = form.adjustment_type.data; notes = form.notes.data; stock_before = product.stock
        if adj_type == 'in':
            product.stock += quantity_to_adjust; qty_change = quantity_to_adjust; log_type = 'adjustment_in'
        elif adj_type == 'out':
            if product.stock < quantity_to_adjust:
                flash(f"Stok {product.name} tidak cukup ({product.stock}) untuk dikurangi {quantity_to_adjust}.", 'danger')
                return render_template('admin/stock_adjustment_form.html', title='Penyesuaian Stok', form=form, legend='Form Penyesuaian Stok')
            product.stock -= quantity_to_adjust; qty_change = -quantity_to_adjust; log_type = 'adjustment_out'
        else:
            flash("Jenis penyesuaian tidak valid.", "danger")
            return render_template('admin/stock_adjustment_form.html', title='Penyesuaian Stok', form=form, legend='Form Penyesuaian Stok')
        db.session.add(StockMovement(product_id=product.id, type=log_type, quantity_change=qty_change, stock_before=stock_before, stock_after=product.stock, notes=notes, user_id=current_user.id))
        db.session.commit()
        flash(f"Stok produk '{product.name}' berhasil disesuaikan.", 'success')
        return redirect(url_for('manage_products'))
    return render_template('admin/stock_adjustment_form.html', title='Penyesuaian Stok', form=form, legend='Form Penyesuaian Stok')

@app.route('/admin/stock/history')
@login_required
@role_required(['admin', 'inventory', 'manager', 'sales'])
def stock_movement_history():
    page = request.args.get('page', 1, type=int); per_page = 20
    movements_pagination = StockMovement.query.join(Product, StockMovement.product_id == Product.id).outerjoin(User, StockMovement.user_id == User.id).add_columns(StockMovement.id.label('movement_id'), StockMovement.timestamp, Product.name.label('product_name'), StockMovement.type, StockMovement.quantity_change, StockMovement.stock_before, StockMovement.stock_after, User.username.label('user_username'), StockMovement.notes).order_by(StockMovement.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/stock_movement_history.html', title="Riwayat Pergerakan Stok", movements_pagination=movements_pagination)

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def application_settings():
    form = SettingsForm()
    if form.validate_on_submit():
        settings_map = {'store_name': form.store_name.data, 'store_address': form.store_address.data, 'store_phone': form.store_phone.data, 'default_tax_rate': str(form.default_tax_rate.data)}
        for key, value in settings_map.items(): get_or_create_setting(key, value).setting_value = value
        if form.store_logo.data:
            old_logo_filename = get_setting_value('store_logo')
            if old_logo_filename:
                try: os.remove(os.path.join(app.config['BRANDING_FOLDER'], old_logo_filename))
                except OSError as e: app.logger.warning(f"Gagal menghapus logo lama: {e}")
            logo_file = form.store_logo.data; logo_filename = secure_filename(logo_file.filename) 
            logo_file.save(os.path.join(app.config['BRANDING_FOLDER'], logo_filename))
            get_or_create_setting('store_logo', logo_filename).setting_value = logo_filename
        if form.login_background_image.data:
            old_bg_filename = get_setting_value('login_background_image')
            if old_bg_filename:
                try: os.remove(os.path.join(app.config['BRANDING_FOLDER'], old_bg_filename))
                except OSError as e: app.logger.warning(f"Gagal menghapus background lama: {e}")
            bg_file = form.login_background_image.data; bg_filename = "login-bg-" + secure_filename(bg_file.filename)
            bg_file.save(os.path.join(app.config['BRANDING_FOLDER'], bg_filename))
            get_or_create_setting('login_background_image', bg_filename).setting_value = bg_filename
        db.session.commit()
        flash('Pengaturan berhasil diperbarui.', 'success')
        return redirect(url_for('application_settings'))
    elif request.method == 'GET':
        form.store_name.data = get_setting_value('store_name', 'Toko Default POS')
        form.store_address.data = get_setting_value('store_address', '')
        form.store_phone.data = get_setting_value('store_phone', '')
        form.default_tax_rate.data = float(get_setting_value('default_tax_rate', '0.0'))
    current_logo = get_setting_value('store_logo')
    current_login_bg = get_setting_value('login_background_image')
    return render_template('admin/application_settings.html', title='Pengaturan Aplikasi', form=form, legend='Ubah Pengaturan Aplikasi', current_logo=current_logo, current_login_bg=current_login_bg)

@app.route('/admin/backup')
@login_required
@role_required('admin')
def manage_backups():
    backup_folder = app.config['BACKUP_FOLDER']; backups = []
    if os.path.exists(backup_folder):
        for filename in sorted(os.listdir(backup_folder), reverse=True):
            if filename.endswith('.zip'):
                file_path = os.path.join(backup_folder, filename)
                backups.append({'filename': filename, 'size': os.path.getsize(file_path), 'timestamp': os.path.getmtime(file_path)})
    return render_template('admin/backup_management.html', title="Backup & Restore", backups=backups)

@app.route('/admin/backup/create', methods=['POST'])
@login_required
@role_required('admin')
def create_backup():
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''); images_folder = app.config['UPLOAD_FOLDER']; backup_folder = app.config['BACKUP_FOLDER']
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S'); backup_filename = f"backup_{timestamp}.zip"; backup_filepath = os.path.join(backup_folder, backup_filename)
    try:
        with zipfile.ZipFile(backup_filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(db_path): zf.write(db_path, arcname='pos_app.db')
            if os.path.exists(images_folder):
                for root, _, files in os.walk(images_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_path = os.path.join('product_images', os.path.relpath(file_path, images_folder))
                        zf.write(file_path, arcname=arc_path)
        flash(f"Backup '{backup_filename}' berhasil dibuat.", "success")
    except Exception as e:
        flash(f"Gagal membuat backup: {str(e)}", "danger"); app.logger.error(f"Backup creation failed: {e}")
    return redirect(url_for('manage_backups'))

@app.route('/admin/backup/download/<filename>')
@login_required
@role_required('admin')
def download_backup(filename):
    return send_from_directory(app.config['BACKUP_FOLDER'], filename, as_attachment=True)

@app.route('/admin/backup/delete/<filename>', methods=['POST'])
@login_required
@role_required('admin')
def delete_backup(filename):
    backup_folder = app.config['BACKUP_FOLDER']; file_path = os.path.join(backup_folder, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            flash(f"File backup '{filename}' telah berhasil dihapus.", "success")
        except OSError as e:
            flash(f"Gagal menghapus file: {str(e)}", "danger"); app.logger.error(f"Error deleting backup file {filename}: {e}")
    else: flash("File backup tidak ditemukan.", "warning")
    return redirect(url_for('manage_backups'))

@app.route('/admin/backup/restore/<filename>', methods=['POST'])
@login_required
@role_required('admin')
def restore_from_backup(filename):
    backup_folder = app.config['BACKUP_FOLDER']; backup_filepath = os.path.join(backup_folder, filename)
    if not os.path.exists(backup_filepath):
        flash("File backup tidak ditemukan.", "danger"); return redirect(url_for('manage_backups'))
    try:
        with zipfile.ZipFile(backup_filepath, 'r') as zf:
            temp_extract_path = get_data_path('temp_restore')
            zf.extractall(path=temp_extract_path)
            restored_db_path = os.path.join(temp_extract_path, 'pos_app.db')
            restored_images_path = os.path.join(temp_extract_path, 'product_images')
            live_db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            live_images_path = app.config['UPLOAD_FOLDER']
            if os.path.exists(restored_db_path): shutil.copy2(restored_db_path, live_db_path)
            if os.path.exists(restored_images_path):
                if os.path.exists(live_images_path): shutil.rmtree(live_images_path)
                shutil.move(restored_images_path, live_images_path)
        shutil.rmtree(temp_extract_path)
        flash(f"Pemulihan dari '{filename}' berhasil. Silakan login kembali.", "success")
        logout_user()
        return redirect(url_for('login'))
    except Exception as e:
        flash(f"Gagal memulihkan dari backup: {str(e)}", "danger"); app.logger.error(f"Restore failed: {e}")
        return redirect(url_for('manage_backups'))

# --- RUTE LAPORAN UNTUK TAMPILAN WEB ---
@app.route('/admin/reports/sales_by_date_range', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'manager', 'sales'])
def sales_by_date_range_report():
    start_date_str = request.form.get('start_date') if request.method == 'POST' else request.args.get('start_date')
    end_date_str = request.form.get('end_date') if request.method == 'POST' else request.args.get('end_date')
    report_data = None
    if start_date_str and end_date_str:
        try:
            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date_obj > end_date_obj:
                flash("Tanggal mulai tidak boleh lebih besar dari tanggal akhir.", "warning")
            else:
                report_data = get_sales_by_date_range_data(start_date_obj, end_date_obj)
        except ValueError:
            flash("Format tanggal tidak valid. Gunakan format YYYY-MM-DD.", "danger")
            start_date_str = None
            end_date_str = None
        except Exception as e:
            flash(f"Terjadi kesalahan saat mengambil laporan: {e}", "danger")
            app.logger.error(f"DEBUG: Exception sales_by_date_range_report: {e}")

    today_local = get_local_today()
    default_start_date = start_date_str or (today_local.replace(day=1)).strftime('%Y-%m-%d')
    default_end_date = end_date_str or today_local.strftime('%Y-%m-%d')

    return render_template('admin/reports/sales_by_date_range_report.html', title='Laporan Penjualan per Rentang Tanggal', report_data=report_data, current_start_date_str=default_start_date, current_end_date_str=default_end_date)


@app.route('/admin/reports/sales_by_product', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'manager', 'sales'])
def sales_by_product_report():
    start_date_str = request.form.get('start_date', request.args.get('start_date'))
    end_date_str = request.form.get('end_date', request.args.get('end_date'))
    report_data = None
    if start_date_str and end_date_str:
        try:
            start_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_obj > end_obj:
                flash("Tanggal mulai tidak boleh lebih besar dari tanggal akhir.", "warning")
            else:
                report_data = get_sales_by_product_data(start_obj, end_obj)
        except ValueError:
            flash("Format tanggal tidak valid.", "danger")
            start_date_str=None
            end_date_str=None
        except Exception as e:
            flash(f"Error saat membuat laporan produk: {e}", "danger")
            app.logger.error(f"DEBUG sales_by_product_report: {e}")
            
    today_local = get_local_today()
    default_start_date = start_date_str or (today_local.replace(day=1)).strftime('%Y-%m-%d')
    default_end_date = end_date_str or today_local.strftime('%Y-%m-%d')

    return render_template('admin/reports/sales_by_product_report.html', title='Laporan Penjualan per Produk', report_data=report_data, current_start_date_str=default_start_date, current_end_date_str=default_end_date)


@app.route('/admin/suppliers')
@login_required
@role_required(['admin', 'inventory', 'manager'])
def manage_suppliers():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template('admin/manage_suppliers.html', title='Kelola Supplier', suppliers=suppliers)

@app.route('/admin/supplier/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def add_supplier():
    form = SupplierForm()
    if form.validate_on_submit():
        new_supplier = Supplier(name=form.name.data, contact_person=form.contact_person.data, phone=form.phone.data, email=form.email.data, address=form.address.data, notes=form.notes.data)
        db.session.add(new_supplier); db.session.commit()
        flash('Supplier baru berhasil ditambahkan!', 'success')
        return redirect(url_for('manage_suppliers'))
    return render_template('admin/supplier_form.html', title='Tambah Supplier Baru', form=form, legend='Tambah Supplier Baru')

@app.route('/admin/supplier/edit/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def edit_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    form = SupplierForm(obj=supplier, original_supplier_name=supplier.name, original_supplier_email=supplier.email)
    if form.validate_on_submit():
        form.populate_obj(supplier); db.session.commit()
        flash('Data supplier berhasil diperbarui!', 'success')
        return redirect(url_for('manage_suppliers'))
    return render_template('admin/supplier_form.html', title='Edit Supplier', form=form, legend=f'Edit Supplier: {supplier.name}')

@app.route('/admin/supplier/delete/<int:supplier_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if supplier.purchase_orders.first():
        flash(f'Supplier "{supplier.name}" tidak dapat dihapus karena memiliki Purchase Order terkait.', 'danger'); return redirect(url_for('manage_suppliers'))
    db.session.delete(supplier); db.session.commit()
    flash('Supplier berhasil dihapus!', 'success')
    return redirect(url_for('manage_suppliers'))

@app.route('/admin/purchase_orders')
@login_required
@role_required(['admin', 'inventory', 'manager'])
def manage_purchase_orders():
    page = request.args.get('page', 1, type=int); per_page = 10
    purchase_orders_pagination = PurchaseOrder.query.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/manage_purchase_orders.html', title='Kelola Purchase Order', purchase_orders_pagination=purchase_orders_pagination)

@app.route('/admin/purchase_order/add', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def add_purchase_order():
    form = PurchaseOrderForm()
    form.supplier_id.choices = [(s.id, s.name) for s in Supplier.query.order_by(Supplier.name).all()]
    all_products_choices = [(p.id, f"{p.name} (Stok: {p.stock})") for p in Product.query.filter_by(product_type='goods').order_by(Product.name).all()]
    for item_form_field in form.items: item_form_field.form.product_id.choices = all_products_choices
    if request.method == 'GET' and not form.items.entries:
        form.items.append_entry(); form.items[-1].form.product_id.choices = all_products_choices
    if form.validate_on_submit():
        po_number = generate_po_number()
        new_po = PurchaseOrder(po_number=po_number, order_date=form.order_date.data, supplier_id=form.supplier_id.data, status=form.status.data, notes=form.notes.data, created_by_user_id=current_user.id)
        current_total_amount = 0; has_valid_item = False
        for item_form_data in form.items.data:
            if item_form_data.get('product_id') and item_form_data.get('quantity_ordered') and item_form_data.get('purchase_price') is not None:
                if int(item_form_data['quantity_ordered']) > 0 and float(item_form_data['purchase_price']) >= 0:
                    po_item = PurchaseOrderItem(purchase_order=new_po, product_id=item_form_data['product_id'], quantity_ordered=item_form_data['quantity_ordered'], purchase_price=item_form_data['purchase_price'])
                    db.session.add(po_item); current_total_amount += po_item.subtotal; has_valid_item = True
        if not has_valid_item:
            flash("Purchase Order harus memiliki minimal satu item produk yang valid.", "warning")
            form.supplier_id.choices = [(s.id, s.name) for s in Supplier.query.order_by(Supplier.name).all()]
            for item_form_field in form.items: item_form_field.form.product_id.choices = all_products_choices
            return render_template('admin/purchase_order_form.html', title='Buat PO Baru', form=form, legend='Buat PO Baru', product_choices_json=jsonify(all_products_choices).json)
        new_po.total_amount = current_total_amount
        db.session.add(new_po); db.session.commit()
        flash(f'Purchase Order {po_number} berhasil dibuat!', 'success')
        return redirect(url_for('manage_purchase_orders'))
    return render_template('admin/purchase_order_form.html', title='Buat PO Baru', form=form, legend='Buat PO Baru', product_choices_json=jsonify(all_products_choices).json)

@app.route('/admin/purchase_order/view/<int:po_id>')
@login_required
@role_required(['admin', 'inventory', 'manager'])
def view_purchase_order(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    return render_template('admin/view_purchase_order.html', title=f'Detail PO: {po.po_number}', po=po)

@app.route('/admin/purchase_order/update_status/<int:po_id>/<new_status>', methods=['POST'])
@login_required
@role_required(['admin', 'manager'])
def update_po_status(po_id, new_status):
    po = PurchaseOrder.query.get_or_404(po_id)
    allowed_transitions = {'Draft': ['Approved', 'Submitted', 'Cancelled'], 'Submitted': ['Approved', 'Rejected', 'Cancelled'], 'Approved': ['Partially Received', 'Completed', 'Cancelled'], 'Partially Received': ['Completed', 'Cancelled']}
    current_status = po.status
    if new_status in allowed_transitions.get(current_status, []):
        po.status = new_status
        if new_status == 'Approved': flash(f"PO {po.po_number} telah disetujui dan siap untuk proses penerimaan barang.", "info")
        else: flash(f"Status PO {po.po_number} berhasil diubah menjadi '{new_status}'.", "success")
        db.session.commit()
    else: flash(f"Perubahan status dari '{current_status}' ke '{new_status}' tidak diizinkan.", "warning")
    return redirect(url_for('view_purchase_order', po_id=po.id))

@app.route('/admin/purchase_order/receive/<int:po_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def receive_purchase_order(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    if po.status in ['Draft', 'Cancelled', 'Completed', 'Rejected']:
        flash(f"PO {po.po_number} dengan status '{po.status}' tidak dapat diproses penerimaannya.", "warning"); return redirect(url_for('manage_purchase_orders'))
    form = GoodsReceiptForm(po_number=po.po_number, supplier_name=po.supplier.name if po.supplier else 'N/A')
    if request.method == 'GET':
        form.items.entries = []
        for item_po in po.items.filter(PurchaseOrderItem.quantity_ordered > PurchaseOrderItem.quantity_received).all():
            form.items.append_entry({'product_id': item_po.product_id, 'product_name': item_po.product.name if item_po.product else 'N/A', 'quantity_ordered': item_po.quantity_ordered, 'quantity_already_received': item_po.quantity_received, 'quantity_outstanding': item_po.quantity_outstanding, 'quantity_received_now': 0})
    if form.validate_on_submit():
        if not form.validate_items(form.items): pass
        else:
            items_processed_count = 0
            try:
                with db.session.begin_nested():
                    for received_item_data in form.items.data:
                        po_item_original = PurchaseOrderItem.query.filter_by(purchase_order_id=po.id, product_id=received_item_data['product_id']).first()
                        if not po_item_original: flash(f"Item produk asli dengan ID {received_item_data['product_id']} tidak ditemukan.", "danger"); continue
                        qty_received_now = int(received_item_data['quantity_received_now'])
                        if qty_received_now > 0:
                            if qty_received_now > po_item_original.quantity_outstanding: raise ValueError(f"Error pada item {po_item_original.product.name}: Jumlah diterima > Jumlah sisa.")
                            product_to_update = Product.query.get(po_item_original.product_id)
                            if not product_to_update: raise ValueError(f"Produk dengan ID {po_item_original.product_id} tidak ditemukan.")
                            stock_before = product_to_update.stock
                            product_to_update.stock += qty_received_now; po_item_original.quantity_received += qty_received_now
                            db.session.add(StockMovement(product_id=product_to_update.id, type='purchase_receipt', quantity_change=qty_received_now, stock_before=stock_before, stock_after=product_to_update.stock, notes=f"Penerimaan PO: {po.po_number}. No. SJ: {form.delivery_order_ref.data or '-'}. Catatan item: {received_item_data.get('notes','')}", user_id=current_user.id))
                            items_processed_count += 1
                    all_items_completed = all(item.quantity_outstanding == 0 for item in po.items)
                    if all_items_completed: po.status = 'Completed'
                    elif any(item.quantity_received > 0 for item in po.items): po.status = 'Partially Received'
                db.session.commit()
                if items_processed_count > 0: flash(f"Barang untuk PO {po.po_number} berhasil diterima.", "success")
                else: flash(f"Tidak ada barang yang diterima untuk PO {po.po_number}.", "info")
                return redirect(url_for('view_purchase_order', po_id=po.id))
            except Exception as e:
                db.session.rollback()
                flash(f"Terjadi error saat proses penerimaan barang: {str(e)}", "danger")
                app.logger.error(f"Error receiving PO {po.id}: {e}")
    return render_template('admin/receive_purchase_order.html', title=f'Terima Barang PO: {po.po_number}', form=form, po=po, legend=f'Form Penerimaan Barang PO: {po.po_number}')

# --- STOCK OPNAME: Mulai Rute Baru ---
@app.route('/admin/stock_opname')
@login_required
@role_required(['admin', 'inventory', 'manager'])
def manage_stock_opnames():
    page = request.args.get('page', 1, type=int)
    opnames = StockOpname.query.order_by(StockOpname.start_date.desc()).paginate(page=page, per_page=15, error_out=False)
    return render_template('admin/opname/manage_stock_opnames.html', title="Manajemen Stock Opname", opnames_pagination=opnames)

@app.route('/admin/stock_opname/start', methods=['POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def start_stock_opname():
    # Cek apakah ada opname yang masih 'In Progress'
    if StockOpname.query.filter_by(status='In Progress').first():
        flash("Tidak bisa memulai opname baru. Selesaikan dulu sesi opname yang sedang berjalan.", "warning")
        return redirect(url_for('manage_stock_opnames'))

    new_opname = StockOpname(
        opname_number=generate_opname_number(),
        created_by_user_id=current_user.id
    )
    db.session.add(new_opname)
    
    # Ambil semua produk fisik (goods) dan buat item opname-nya
    products_to_count = Product.query.filter_by(product_type='goods').all()
    if not products_to_count:
        flash("Tidak ada produk fisik (barang) untuk dihitung.", "warning")
        return redirect(url_for('manage_stock_opnames'))

    for product in products_to_count:
        item = StockOpnameItem(
            stock_opname=new_opname,
            product_id=product.id,
            system_stock_at_opname=product.stock if product.stock is not None else 0
        )
        db.session.add(item)
    
    db.session.commit()
    flash(f"Sesi Stock Opname {new_opname.opname_number} berhasil dimulai.", "success")
    return redirect(url_for('conduct_stock_opname', opname_id=new_opname.id))

@app.route('/admin/stock_opname/conduct/<int:opname_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'inventory', 'manager'])
def conduct_stock_opname(opname_id):
    opname = StockOpname.query.get_or_404(opname_id)
    if opname.status == 'Completed':
        flash("Sesi opname ini sudah selesai dan tidak bisa diubah lagi.", "info")
        return redirect(url_for('manage_stock_opnames'))

    form = StockOpnameForm(obj=opname)
    
    if request.method == 'POST':
        form.populate_obj(opname)
        
        # Simpan progres hitungan
        for item_form in form.items:
            item_db = StockOpnameItem.query.get(item_form.item_id.data)
            if item_db:
                item_db.physical_count = item_form.physical_count.data
        
        db.session.commit()

        # Jika tombol Finalisasi yang ditekan
        if form.submit_finalize.data:
            # Validasi semua item sudah dihitung
            all_counted = all(item.physical_count is not None for item in opname.items)
            if not all_counted:
                flash("Finalisasi gagal. Pastikan semua produk sudah dihitung (isi dengan angka, minimal 0).", "danger")
                return redirect(url_for('conduct_stock_opname', opname_id=opname.id))
            
            try:
                with db.session.begin_nested():
                    for item in opname.items:
                        if item.variance != 0:
                            product = Product.query.get(item.product_id)
                            stock_before = product.stock
                            product.stock = item.physical_count
                            
                            movement = StockMovement(
                                product_id=product.id,
                                type='opname_adjustment',
                                quantity_change=item.variance,
                                stock_before=stock_before,
                                stock_after=product.stock,
                                notes=f"Penyesuaian dari Stock Opname: {opname.opname_number}",
                                user_id=current_user.id
                            )
                            db.session.add(movement)
                    
                    opname.status = 'Completed'
                    opname.end_date = datetime.utcnow()
                    opname.finalized_by_user_id = current_user.id
                db.session.commit()
                flash(f"Stock Opname {opname.opname_number} berhasil difinalisasi dan stok telah disesuaikan.", "success")
                return redirect(url_for('manage_stock_opnames'))
            except Exception as e:
                db.session.rollback()
                flash(f"Terjadi error saat finalisasi: {str(e)}", "danger")

        else: # Jika hanya Simpan Progres
            flash("Progres hitungan berhasil disimpan.", "success")

        return redirect(url_for('conduct_stock_opname', opname_id=opname.id))

    # --- Bagian GET ---
    # Isi form dengan data dari database
    form.items.entries = [] # Kosongkan dulu
    for item in opname.items.join(Product).order_by(Product.name).all():
        item_form_data = {
            'item_id': item.id,
            'product_name': f"({item.product.product_code}) {item.product.name}",
            'system_stock': item.system_stock_at_opname,
            'physical_count': item.physical_count
        }
        form.items.append_entry(data=item_form_data)
        
    return render_template('admin/opname/conduct_stock_opname.html', title=f"Lakukan Opname: {opname.opname_number}", form=form, opname=opname)
# --- STOCK OPNAME: Akhir Rute Baru ---


# --- POS (POINT OF SALE) ROUTES ---
def get_cart(): 
    session.setdefault('cart', {})
    return session['cart']

def calculate_cart_details(cart):
    taxable_subtotal = 0.0
    non_taxable_subtotal = 0.0
    tax_rate_str = get_setting_value('default_tax_rate', '0.0')
    try: 
        tax_percent = float(tax_rate_str)
    except (ValueError, TypeError): 
        tax_percent = 0.0
        app.logger.warning(f"Invalid tax rate setting: '{tax_rate_str}', using 0.0.")
    tax_decimal = tax_percent / 100.0

    if cart:
        product_ids = [int(pid) for pid in cart.keys()]
        products_in_cart = Product.query.filter(Product.id.in_(product_ids)).all()
        product_map = {str(p.id): p for p in products_in_cart}

        for pid_str, item_data in cart.items():
            product = product_map.get(pid_str)
            item_subtotal = item_data['price'] * item_data['quantity']
            
            if product and product.is_taxable:
                taxable_subtotal += item_subtotal
            else:
                non_taxable_subtotal += item_subtotal
    
    tax_amount = taxable_subtotal * tax_decimal
    grand_total = taxable_subtotal + non_taxable_subtotal + tax_amount
    
    return {
        'taxable_subtotal': taxable_subtotal,
        'non_taxable_subtotal': non_taxable_subtotal,
        'total_subtotal': taxable_subtotal + non_taxable_subtotal,
        'tax_rate_percentage': tax_percent,
        'tax_rate_decimal': tax_decimal,
        'tax_amount': tax_amount,
        'grand_total': grand_total
    }

@app.route('/pos')
@login_required
@role_required(['sales', 'admin', 'manager'])
def pos_interface():
    summary_products = Product.query.filter(
        or_(
            (Product.product_type == 'goods') & (Product.stock > 0),
            (Product.product_type == 'service')
        )
    ).order_by(Product.id.desc()).limit(5).all()
    
    cart_details = calculate_cart_details(get_cart())
    return render_template('pos/pos_interface.html', title='Kasir', summary_products=summary_products, cart=get_cart(), cart_details=cart_details, search_query=request.args.get('search', ''), MINIMUM_STOCK_THRESHOLD=MINIMUM_STOCK_THRESHOLD)

@app.route('/api/search_products')
@login_required
@role_required(['sales', 'admin', 'manager'])
def api_search_products():
    q = request.args.get('q', '').strip()
    products_json = []
    if q and len(q) >= 1:
        search_filter = or_(Product.name.ilike(f'%{q}%'), Product.product_code.ilike(f'%{q}%'))
        
        sellable_filter = or_(
            (Product.product_type == 'goods') & (Product.stock > 0),
            (Product.product_type == 'service')
        )
        found = Product.query.filter(search_filter, sellable_filter).order_by(Product.name).limit(10).all()
        
        for p in found:
            price_details = p.current_selling_price_details
            products_json.append({
                'id': p.id, 
                'name': f"({p.product_code or 'JASA'}) {p.name}", 
                'price': price_details['effective_price'], 
                'original_price': price_details['original_price'], 
                'discount_info': price_details['active_discount_info'], 
                'stock': p.stock if p.product_type == 'goods' else 'N/A'
            })
    return jsonify(products_json)

@app.route('/pos/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
@role_required(['sales', 'admin', 'manager'])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    cart = get_cart()
    item_id_str = str(product_id)
    price_details = product.current_selling_price_details
    price_to_use = price_details['effective_price']
    
    if product.product_type == 'goods':
        if product.stock <= 0:
            flash(f"Stok produk {product.name} habis!", 'warning')
            return redirect(url_for('pos_interface'))
            
        current_qty = cart.get(str(product_id), {}).get('quantity', 0)
        if current_qty + 1 > product.stock:
            flash(f"Kuantitas produk {product.name} akan melebihi stok.", 'warning')
            return redirect(url_for('pos_interface'))
        
    if item_id_str in cart:
        if cart[item_id_str]['price'] != price_to_use:
            cart[item_id_str]['price'] = price_to_use
            cart[item_id_str]['original_price'] = price_details['original_price']
            cart[item_id_str]['discount_info'] = price_details['active_discount_info']
            flash(f"Harga produk {product.name} di keranjang telah diperbarui.", "info")
        cart[item_id_str]['quantity'] += 1
    else:
        cart[item_id_str] = {'name': product.name, 'price': price_to_use, 'quantity': 1, 'original_price': price_details['original_price'], 'discount_info': price_details['active_discount_info']}
    session['cart'] = cart
    return redirect(url_for('pos_interface'))

@app.route('/pos/update_cart/<int:product_id>', methods=['POST'])
@login_required
@role_required(['sales', 'admin', 'manager'])
def update_cart(product_id):
    product = Product.query.get_or_404(product_id)
    cart = get_cart(); item_id_str = str(product_id)
    try: new_quantity = int(request.form.get('quantity', 0))
    except ValueError: 
        flash("Kuantitas yang dimasukkan tidak valid.", "danger"); return redirect(url_for('pos_interface'))
    if item_id_str in cart:
        if new_quantity > 0:
            if product.product_type == 'goods':
                if new_quantity <= product.stock:
                    cart[item_id_str]['quantity'] = new_quantity
                else: 
                    cart[item_id_str]['quantity'] = product.stock
                    flash(f"Kuantitas produk {product.name} disesuaikan dengan stok maksimum ({product.stock}).", 'warning')
            else:
                cart[item_id_str]['quantity'] = new_quantity
        else: 
            del cart[item_id_str]
        session['cart'] = cart
    return redirect(url_for('pos_interface'))

@app.route('/pos/remove_from_cart/<int:product_id>', methods=['POST'])
@login_required
@role_required(['sales', 'admin', 'manager'])
def remove_from_cart(product_id):
    cart = get_cart(); item_id_str = str(product_id)
    if item_id_str in cart: 
        del cart[item_id_str]
        session['cart'] = cart
    return redirect(url_for('pos_interface'))

@app.route('/pos/clear_cart', methods=['POST'])
@login_required
@role_required(['sales', 'admin', 'manager'])
def clear_cart(): 
    session.pop('cart', None)
    flash("Keranjang belanja telah dikosongkan.", "info")
    return redirect(url_for('pos_interface'))

@app.route('/pos/checkout', methods=['POST'])
@login_required
@role_required(['sales', 'admin', 'manager'])
def checkout():
    cart = get_cart()
    if not cart: 
        flash("Keranjang belanja kosong. Tidak ada transaksi yang diproses.", "warning")
        return redirect(url_for('pos_interface'))
        
    cart_details = calculate_cart_details(cart)
    
    try:
        with db.session.begin_nested():
            new_transaction = Transaction(
                taxable_subtotal=cart_details['taxable_subtotal'],
                non_taxable_subtotal=cart_details['non_taxable_subtotal'],
                tax_rate_at_transaction=cart_details['tax_rate_decimal'], 
                tax_amount=cart_details['tax_amount'], 
                total_amount=cart_details['grand_total'], 
                user_id=current_user.id
            )
            db.session.add(new_transaction)
            db.session.flush()

            product_map = {p.id: p for p in Product.query.filter(Product.id.in_([int(pid) for pid in cart.keys()])).with_for_update().all()}
            
            for pid_str, item_data_in_cart in cart.items():
                pid = int(pid_str)
                product = product_map.get(pid)
                if not product: raise Exception(f"Produk dengan ID {pid} tidak ditemukan saat checkout.")
                
                if product.product_type == 'goods' and product.stock < item_data_in_cart['quantity']:
                    raise Exception(f"Stok produk {product.name} tidak mencukupi.")
                
                db.session.add(TransactionItem(
                    transaction=new_transaction, product_id=pid, quantity=item_data_in_cart['quantity'], 
                    price_at_transaction=item_data_in_cart['price'], 
                    is_taxed_at_transaction=product.is_taxable,
                    original_price_at_transaction=item_data_in_cart.get('original_price', item_data_in_cart['price']), 
                    discount_applied_info=item_data_in_cart.get('discount_info'), 
                    purchase_price_at_transaction=product.purchase_price
                ))
                
                if product.product_type == 'goods':
                    stock_before = product.stock
                    product.stock -= item_data_in_cart['quantity']
                    db.session.add(StockMovement(
                        product_id=pid, type='sale', quantity_change=-item_data_in_cart['quantity'], 
                        stock_before=stock_before, stock_after=product.stock, 
                        notes=f'Transaksi POS ID: {new_transaction.id}', user_id=current_user.id
                    ))
        
        db.session.commit()
        session.pop('cart', None)
        transaction_id_for_receipt = new_transaction.id
        flash(f"Transaksi berhasil diproses! Total: Rp {cart_details['grand_total']:,.0f}".replace(",", "."), "success")
        return redirect(url_for('view_receipt', transaction_id=transaction_id_for_receipt))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Gagal checkout: {str(e)}", "danger")
    return redirect(url_for('pos_interface'))


@app.route('/pos/receipt/<int:transaction_id>')
@login_required
@role_required(['sales', 'admin', 'manager'])
def view_receipt(transaction_id):
    transaction_query_result = db.session.query(Transaction, User.username.label('cashier_username')).join(User, Transaction.user_id == User.id).filter(Transaction.id == transaction_id).first_or_404()
    trans_obj, cashier_name = transaction_query_result[0], transaction_query_result[1]
    store_name = get_setting_value('store_name', 'Toko Anda')
    store_address = get_setting_value('store_address', 'Alamat Toko Anda')
    store_phone = get_setting_value('store_phone', 'Telepon Toko Anda')
    return render_template('pos/receipt.html', title=f'Struk Transaksi {trans_obj.id}', transaction=trans_obj, cashier_name=cashier_name, store_name=store_name, store_address=store_address, store_phone=store_phone)

# --- RUTE TAMBAHAN UNTUK MELAYANI FILE UPLOAD ---
@app.route('/user_uploads/<path:filename>')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/branding_assets/<path:filename>')
def serve_branding_file(filename):
    return send_from_directory(app.config['BRANDING_FOLDER'], filename)

# --- PERUBAHAN DARI 'KASIR' KE 'SALES' (Langkah 4) ---: Perintah CLI baru untuk update data di DB
@app.cli.command("update-role-name")
@click.option('--old-name', default='kasir', help="Nama role lama yang akan diganti.")
@click.option('--new-name', default='sales', help="Nama role baru.")
@with_appcontext
def update_role_name(old_name, new_name):
    """Mengganti nama role untuk semua pengguna di database."""
    users_to_update = User.query.filter_by(role=old_name).all()
    
    if not users_to_update:
        print(f"Tidak ada pengguna ditemukan dengan role '{old_name}'. Tidak ada yang diubah.")
        return

    count = 0
    for user in users_to_update:
        user.role = new_name
        count += 1
    
    db.session.commit()
    print(f"Sukses! {count} pengguna telah diperbarui dari role '{old_name}' ke '{new_name}'.")

# ==============================================================================
# BAGIAN 4: BLOK EKSEKUSI UNTUK WEB HOSTING
# ==============================================================================
if __name__ == '__main__':
    # Blok ini digunakan untuk pengembangan lokal.
    # Di server hosting seperti Render, mereka akan menggunakan Gunicorn untuk menjalankan app.
    with app.app_context():
        db.create_all()
        print("-> Database tables initialized/checked.")
        initialize_default_settings()
        print("-> Default application settings initialized/checked.")
    
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
