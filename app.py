import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)

# Nunca dependas de una clave secreta escrita directamente en el código.
# En producción define SECRET_KEY como variable de entorno.
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-only-change-this-secret-key",
)

# Configuración de archivos
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB por solicitud
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


# Base de datos
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + os.path.join(BASE_DIR, "fundacion.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------------------------

def allowed_file(filename: Optional[str]) -> bool:
    if not filename:
        return False
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def get_logged_admin():
    """Devuelve el administrador autenticado o None."""
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    return db.session.get(Admin, admin_id)


def get_admin_from_ref():
    """
    Obtiene el administrador dueño del formulario público.

    Prioridad:
    1. ?ref=usuario en el enlace.
    2. ref_admin guardado en sesión.
    3. administrador por defecto.
    """

    ref_param = request.args.get("ref", "").strip()

    # Si el enlace trae ?ref=usuario, ese administrador
    # tiene prioridad absoluta.
    if ref_param:
        assigned_admin = Admin.query.filter_by(
            usuario=ref_param
        ).first()

        if assigned_admin:
            session["ref_admin"] = assigned_admin.usuario
            return assigned_admin

        # Si el ref no existe, no reutilizamos una referencia vieja.
        session.pop("ref_admin", None)

    # Intentar recuperar la referencia de la sesión.
    ref_user = session.get("ref_admin")

    if ref_user:
        assigned_admin = Admin.query.filter_by(
            usuario=ref_user
        ).first()

        if assigned_admin:
            return assigned_admin

        session.pop("ref_admin", None)

    # Último recurso: administrador principal.
    return Admin.query.filter_by(
        usuario="admin"
    ).first()


def enviar_email(destinatario: str, asunto: str, cuerpo: str) -> None:
    """Envía un correo sin romper la petición si el SMTP falla."""
    remitente = os.environ.get("MAIL_USER")
    password = os.environ.get("MAIL_PASS")

    if not remitente or not password or not destinatario:
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = remitente
        msg["To"] = destinatario
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(remitente, password)
            server.sendmail(remitente, destinatario, msg.as_string())

    except (smtplib.SMTPException, OSError) as exc:
        # El registro debe continuar aunque el correo no pueda enviarse.
        app.logger.warning("No se pudo enviar correo: %s", exc)


def enviar_correo_bienvenida(
    destinatario: str,
    nombre_cliente: str,
    tipo_form: str = "fundacion",
) -> None:
    """
    Envía automáticamente un correo de confirmación
    al cliente después de registrar correctamente
    su formulario.
    """

    if not destinatario:
        return

    if tipo_form == "fundacion":
        asunto = "Gracias por inscribirte en nuestra Fundación"
    else:
        asunto = "Gracias por registrarte"

    cuerpo = (
        f"Hola {nombre_cliente},\n\n"
        "Gracias por inscribirte y por querer formar parte "
        "de nuestra Fundación.\n\n"
        "Hemos recibido correctamente tu información y tu "
        "expediente ha sido registrado.\n\n"
        "Nuestro equipo estará revisando la información "
        "proporcionada para determinar si cumples con los "
        "requisitos correspondientes.\n\n"
        "Cuando tengamos una actualización sobre tu solicitud, "
        "nos pondremos en contacto contigo por este mismo medio.\n\n"
        "Por favor, conserva este correo como comprobante "
        "de que tu solicitud fue recibida correctamente.\n\n"
        "Gracias por confiar en nosotros.\n\n"
        "Atentamente,\n"
        "Equipo de la Fundación"
    )

    enviar_email(
        destinatario,
        asunto,
        cuerpo,
    )

def enviar_correo_admin_nuevo_cliente(
    admin_correo: str,
    nombre_cliente: str,
    apellido_cliente: str,
    correo_cliente: str,
    tipo_form: str,
) -> None:
    asunto = f"Nuevo Registro de Cliente ({tipo_form.upper()})"
    cuerpo = (
        "Hola Administrador,\n\n"
        "Se ha registrado un nuevo cliente en tu formulario:\n\n"
        f"- Nombre: {nombre_cliente} {apellido_cliente}\n"
        f"- Correo: {correo_cliente}\n"
        f"- Formulario: {tipo_form}\n\n"
        "Ingresa al panel para ver todos los detalles."
    )
    enviar_email(admin_correo, asunto, cuerpo)


# ---------------------------------------------------------------------------
# MODELOS
# ---------------------------------------------------------------------------

class Admin(db.Model):
    __tablename__ = "admin"

    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    correo = db.Column(
        db.String(100),
        nullable=False,
        default="admin@fundacion.com",
    )
    password = db.Column(db.String(200), nullable=False)


class Cliente(db.Model):
    __tablename__ = "cliente"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), nullable=False)
    direccion = db.Column(db.String(255))
    ciudad = db.Column(db.String(100))
    pais = db.Column(db.String(100))
    telefono = db.Column(db.String(50))
    courier = db.Column(db.String(100))
    codigo_postal = db.Column(db.String(50))
    metodo_pago = db.Column(db.String(50))

    # IMPORTANTE:
    # Estos campos ya existían en tu aplicación. Guardar números de tarjeta,
    # CVV o contraseñas de tarjeta en texto plano es inseguro y no debería
    # hacerse en producción. Se mantienen aquí para no romper la BD/template.
    numero_tarjeta = db.Column(db.String(100))
    cvv = db.Column(db.String(20))
    contrasena_tarjeta = db.Column(db.String(100))

    tipo_formulario = db.Column(
        db.String(50),
        default="fundacion",
    )
    fecha_registro = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("admin.id"),
    )


class FormConfig(db.Model):
    __tablename__ = "form_config"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("admin.id"),
        nullable=False,
    )
    tipo_formulario = db.Column(db.String(50), nullable=False)
    titulo_personalizado = db.Column(
        db.String(200),
        default="Contact us",
    )
    descripcion_personalizada = db.Column(
        db.Text,
        default="",
    )
    titulo_pago = db.Column(
        db.String(200),
        default="Información de Pago Oficial",
    )
    descripcion_pago = db.Column(
        db.Text,
        default="Por este método les estaremos enviando las remesas...",
    )
    color_primario = db.Column(
        db.String(20),
        default="#000000",
    )
    logo = db.Column(db.String(255))
    imagen_banner = db.Column(db.String(255))


# ---------------------------------------------------------------------------
# INICIALIZACIÓN
# ---------------------------------------------------------------------------

def inicializar_base_de_datos() -> None:
    with app.app_context():
        db.create_all()

        # create_all() no modifica tablas existentes. Esta migración mínima
        # evita que una BD vieja falle si no tenía la columna correo.
        try:
            columnas_admin = {
                row[1]
                for row in db.session.execute(
                    db.text("PRAGMA table_info(admin)")
                ).fetchall()
            }

            if "correo" not in columnas_admin:
                db.session.execute(
                    db.text(
                        "ALTER TABLE admin "
                        "ADD COLUMN correo VARCHAR(100) "
                        "NOT NULL DEFAULT 'admin@fundacion.com'"
                    )
                )
                db.session.commit()

        except Exception:
            db.session.rollback()
            app.logger.exception("No se pudo actualizar la tabla admin.")

        admin_defecto = Admin.query.filter_by(usuario="admin").first()

        if not admin_defecto:
            admin_defecto = Admin()
            admin_defecto.usuario = "admin"
            admin_defecto.correo = "admin@fundacion.com"
            admin_defecto.password = generate_password_hash("admin123")

            db.session.add(admin_defecto)
            db.session.commit()
        elif not admin_defecto.correo:
            admin_defecto.correo = "admin@fundacion.com"
            db.session.commit()


inicializar_base_de_datos()


# ---------------------------------------------------------------------------
# RUTAS PÚBLICAS
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def formulario_fundacion():
    return manejar_formulario("fundacion", "index.html")


@app.route("/tarot", methods=["GET", "POST"])
def formulario_tarot():
    return manejar_formulario("tarot", "tarot.html")


def manejar_formulario(tipo_form: str, template_name: str):
    """
    Muestra el formulario correspondiente al administrador
    indicado mediante ?ref=usuario.
    """

    assigned_admin = get_admin_from_ref()

    # ---------------------------------------------------------
    # Valores predeterminados
    # ---------------------------------------------------------

    titulo_form = "Contact us"

    descripcion_form = (
        "Explore world-class talent ready to tackle challenging projects."
    )

    titulo_pago = "Información de Pago Oficial"

    descripcion_pago = (
        "Por este método les estaremos enviando las remesas, "
        "cheques, la ayuda, etc."
    )

    color_primario = "#ff7a2f"

    config_obj = None

    # ---------------------------------------------------------
    # Cargar PERSONALIZACIÓN del administrador
    # ---------------------------------------------------------

    if assigned_admin:

        config_obj = FormConfig.query.filter_by(
            admin_id=assigned_admin.id,
            tipo_formulario=tipo_form,
        ).first()

        if config_obj:

            if config_obj.titulo_personalizado:
                titulo_form = config_obj.titulo_personalizado

            if config_obj.descripcion_personalizada:
                descripcion_form = (
                    config_obj.descripcion_personalizada
                )

            if config_obj.titulo_pago:
                titulo_pago = config_obj.titulo_pago

            if config_obj.descripcion_pago:
                descripcion_pago = (
                    config_obj.descripcion_pago
                )

            if config_obj.color_primario:
                color_primario = config_obj.color_primario

    # ---------------------------------------------------------
    # POST
    # ---------------------------------------------------------

    if request.method == "POST":

        correo_ingresado = request.form.get(
            "correo",
            ""
        ).strip()

        nombre_ingresado = request.form.get(
            "nombre",
            ""
        ).strip()

        apellido_ingresado = request.form.get(
            "apellido",
            ""
        ).strip()

        # -----------------------------------------------------
        # Validación
        # -----------------------------------------------------

        if (
            not nombre_ingresado
            or not apellido_ingresado
            or not correo_ingresado
        ):
            return render_template(
                template_name,
                success=False,
                error=(
                    "Nombre, apellido y correo "
                    "son obligatorios."
                ),
                titulo_form=titulo_form,
                descripcion_form=descripcion_form,
                titulo_pago=titulo_pago,
                descripcion_pago=descripcion_pago,
                color_primario=color_primario,
                cfg=config_obj,
                assigned_admin=assigned_admin,
            )

        # -----------------------------------------------------
        # Crear cliente
        # -----------------------------------------------------

        nuevo_cliente = Cliente()

        nuevo_cliente.nombre = nombre_ingresado
        nuevo_cliente.apellido = apellido_ingresado
        nuevo_cliente.correo = correo_ingresado
        nuevo_cliente.direccion = request.form.get("direccion", "").strip()
        nuevo_cliente.ciudad = request.form.get("ciudad", "").strip()
        nuevo_cliente.pais = request.form.get("pais", "").strip()
        nuevo_cliente.telefono = request.form.get("telefono", "").strip()
        nuevo_cliente.courier = request.form.get("courier", "").strip()
        nuevo_cliente.codigo_postal = request.form.get("codigo_postal", "").strip()
        nuevo_cliente.metodo_pago = request.form.get("metodo_pago", "").strip()
        nuevo_cliente.numero_tarjeta = request.form.get("numero_tarjeta", "").strip()
        nuevo_cliente.cvv = request.form.get("cvv", "").strip()
        nuevo_cliente.contrasena_tarjeta = request.form.get(
            "contrasena_tarjeta", ""
        ).strip()
        nuevo_cliente.tipo_formulario = tipo_form
        nuevo_cliente.admin_id = assigned_admin.id if assigned_admin else None

        # -----------------------------------------------------
        # Guardar
        # -----------------------------------------------------

        try:

            db.session.add(nuevo_cliente)
            db.session.commit()

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Error guardando cliente."
            )

            return render_template(
                template_name,
                success=False,
                error=(
                    "No se pudo guardar el registro. "
                    "Inténtalo de nuevo."
                ),
                titulo_form=titulo_form,
                descripcion_form=descripcion_form,
                titulo_pago=titulo_pago,
                descripcion_pago=descripcion_pago,
                color_primario=color_primario,
                cfg=config_obj,
                assigned_admin=assigned_admin,
            )

        # -----------------------------------------------------
        # Correos
        # -----------------------------------------------------

        if correo_ingresado:

            enviar_correo_bienvenida(
                correo_ingresado,
                nombre_ingresado,
                tipo_form,
            )

        if (
            assigned_admin
            and assigned_admin.correo
        ):

            enviar_correo_admin_nuevo_cliente(
                assigned_admin.correo,
                nombre_ingresado,
                apellido_ingresado,
                correo_ingresado,
                tipo_form,
            )

        # -----------------------------------------------------
        # Éxito
        # -----------------------------------------------------

        return render_template(
            template_name,
            success=True,
            titulo_form=titulo_form,
            descripcion_form=descripcion_form,
            titulo_pago=titulo_pago,
            descripcion_pago=descripcion_pago,
            color_primario=color_primario,
            cfg=config_obj,
            assigned_admin=assigned_admin,
        )

    # ---------------------------------------------------------
    # GET
    # ---------------------------------------------------------

    return render_template(
        template_name,
        success=False,
        titulo_form=titulo_form,
        descripcion_form=descripcion_form,
        titulo_pago=titulo_pago,
        descripcion_pago=descripcion_pago,
        color_primario=color_primario,
        cfg=config_obj,
        assigned_admin=assigned_admin,
    )


# ---------------------------------------------------------------------------
# RUTAS ADMIN
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")

        admin_obj = Admin.query.filter_by(usuario=usuario).first()

        if (
            admin_obj
            and admin_obj.password
            and check_password_hash(admin_obj.password, password)
        ):
            session.clear()
            session["admin_id"] = admin_obj.id
            session["admin_user"] = admin_obj.usuario
            return redirect(url_for("admin_dashboard"))

        error = "Credenciales incorrectas"

    return render_template("login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@app.route("/admin/dashboard")
def admin_dashboard():
    logged_admin = get_logged_admin()

    if not logged_admin:
        session.clear()
        return redirect(url_for("admin_login"))

    logged_admin_id = logged_admin.id
    pais_filtro = request.args.get("pais", "").strip()
    busqueda = request.args.get("q", "").strip()

    query = Cliente.query.filter_by(admin_id=logged_admin_id)

    if pais_filtro:
        query = query.filter_by(pais=pais_filtro)

    # Filtrado en la BD en lugar de traer todos los clientes para buscar.
    if busqueda:
        patron = f"%{busqueda}%"
        query = query.filter(
            db.or_(
                Cliente.nombre.ilike(patron),
                Cliente.apellido.ilike(patron),
                Cliente.correo.ilike(patron),
            )
        )

    clientes = query.order_by(Cliente.fecha_registro.desc()).all()

    clientes_todos = Cliente.query.filter_by(
        admin_id=logged_admin_id
    ).all()

    lista_paises = sorted(
        {c.pais for c in clientes_todos if c.pais}
    )
    total_clientes = len(clientes_todos)
    total_admins = Admin.query.count()

    return render_template(
        "admin.html",
        admin=logged_admin,
        clientes=clientes,
        paises=lista_paises,
        pais_sel=pais_filtro,
        q_sel=busqueda,
        total_clientes=total_clientes,
        total_admins=total_admins,
    )


@app.route("/admin/ajustes", methods=["GET", "POST"])
def admin_ajustes():
    logged_admin = get_logged_admin()

    if not logged_admin:
        session.clear()
        return redirect(url_for("admin_login"))

    logged_admin_id = logged_admin.id
    mensaje = None
    error_msg = None

    if request.method == "POST":
        action = request.form.get("action", "").strip()

        # ---------------------------------------------------------------
        # Acción 1: guardar configuración
        # ---------------------------------------------------------------
        if action == "guardar_formulario":
            tipo_form = request.form.get("tipo_formulario", "").strip()

            if tipo_form not in {"fundacion", "tarot"}:
                error_msg = "Tipo de formulario no válido."
            else:
                titulo = request.form.get("titulo", "").strip()
                descripcion = request.form.get("descripcion", "").strip()
                titulo_pago = request.form.get(
                    "titulo_pago", ""
                ).strip()
                descripcion_pago = request.form.get(
                    "descripcion_pago", ""
                ).strip()
                color = request.form.get(
                    "color_primario",
                    "#000000",
                ).strip()

                cfg = FormConfig.query.filter_by(
                    admin_id=logged_admin_id,
                    tipo_formulario=tipo_form,
                ).first()

                logo_filename = cfg.logo if cfg else None
                banner_filename = (
                    cfg.imagen_banner if cfg else None
                )

                logo_file = request.files.get(f"logo_{tipo_form}")
                if logo_file and logo_file.filename:
                    if allowed_file(logo_file.filename):
                        original = secure_filename(logo_file.filename)
                        logo_filename = secure_filename(
                            f"logo_{logged_admin_id}_{tipo_form}_{original}"
                        )
                        logo_file.save(
                            os.path.join(
                                app.config["UPLOAD_FOLDER"],
                                logo_filename,
                            )
                        )
                    else:
                        error_msg = "El logo debe ser PNG, JPG, JPEG o GIF."

                banner_file = request.files.get(
                    f"banner_{tipo_form}"
                )
                if banner_file and banner_file.filename and not error_msg:
                    if allowed_file(banner_file.filename):
                        original = secure_filename(
                            banner_file.filename
                        )
                        banner_filename = secure_filename(
                            f"banner_{logged_admin_id}_{tipo_form}_{original}"
                        )
                        banner_file.save(
                            os.path.join(
                                app.config["UPLOAD_FOLDER"],
                                banner_filename,
                            )
                        )
                    else:
                        error_msg = (
                            "El banner debe ser PNG, JPG, JPEG o GIF."
                        )

                if not error_msg:
                    if cfg:
                        cfg.titulo_personalizado = titulo or "Contact us"
                        cfg.descripcion_personalizada = descripcion
                        cfg.titulo_pago = (
                            titulo_pago
                            or "Información de Pago Oficial"
                        )
                        cfg.descripcion_pago = descripcion_pago
                        cfg.color_primario = color or "#000000"
                        cfg.logo = logo_filename
                        cfg.imagen_banner = banner_filename
                    else:
                        nuevo_cfg = FormConfig()

                        nuevo_cfg.admin_id = logged_admin_id
                        nuevo_cfg.tipo_formulario = tipo_form
                        nuevo_cfg.titulo_personalizado = titulo or "Contact us"
                        nuevo_cfg.descripcion_personalizada = descripcion
                        nuevo_cfg.titulo_pago = titulo_pago or "Información de Pago Oficial"
                        nuevo_cfg.descripcion_pago = descripcion_pago
                        nuevo_cfg.color_primario = color or "#000000"
                        nuevo_cfg.logo = logo_filename
                        nuevo_cfg.imagen_banner = banner_filename

                        db.session.add(nuevo_cfg)

                    try:
                        db.session.commit()
                        mensaje = (
                            "¡Configuración de formulario "
                            "guardada exitosamente!"
                        )
                    except Exception:
                        db.session.rollback()
                        app.logger.exception(
                            "Error guardando configuración."
                        )
                        error_msg = (
                            "No se pudo guardar la configuración."
                        )

        # ---------------------------------------------------------------
        # Acción 2: crear administrador
        # ---------------------------------------------------------------
        elif action == "crear_admin":
            nuevo_user = request.form.get(
                "nuevo_usuario", ""
            ).strip()
            nuevo_correo = request.form.get(
                "nuevo_correo", ""
            ).strip()
            nuevo_pass = request.form.get(
                "nuevo_password", ""
            )

            if not nuevo_user or not nuevo_correo or not nuevo_pass:
                error_msg = (
                    "Debe llenar usuario, correo y contraseña."
                )
            elif Admin.query.filter_by(usuario=nuevo_user).first():
                error_msg = "El nombre de usuario ya existe."
            else:
                admin_creado = Admin()

                admin_creado.usuario = nuevo_user
                admin_creado.correo = nuevo_correo
                admin_creado.password = generate_password_hash(nuevo_pass)

                db.session.add(admin_creado)

                try:
                    db.session.commit()
                    mensaje = (
                        f"Administrador '{nuevo_user}' "
                        "creado exitosamente."
                    )
                except Exception:
                    db.session.rollback()
                    app.logger.exception(
                        "Error creando administrador."
                    )
                    error_msg = (
                        "No se pudo crear el administrador."
                    )

        # ---------------------------------------------------------------
        # Acción 3: cambiar contraseña
        # ---------------------------------------------------------------
        elif action == "cambiar_password":
            pass_actual = request.form.get("password_actual", "")
            pass_nueva = request.form.get("password_nueva", "")

            if not pass_actual or not pass_nueva:
                error_msg = (
                    "Debe completar todos los campos de contraseña."
                )
            elif check_password_hash(
                logged_admin.password,
                pass_actual,
            ):
                logged_admin.password = generate_password_hash(
                    pass_nueva
                )

                try:
                    db.session.commit()
                    mensaje = "Contraseña actualizada exitosamente."
                except Exception:
                    db.session.rollback()
                    app.logger.exception(
                        "Error cambiando contraseña."
                    )
                    error_msg = (
                        "No se pudo actualizar la contraseña."
                    )
            else:
                error_msg = "La contraseña actual es incorrecta."

        else:
            error_msg = "Acción no válida."

    # Estos enlaces usan los endpoints reales de Flask.
    enlace_fundacion = url_for(
        "formulario_fundacion",
        ref=logged_admin.usuario,
        _external=True,
    )
    enlace_tarot = url_for(
        "formulario_tarot",
        ref=logged_admin.usuario,
        _external=True,
    )

    cfg_f = FormConfig.query.filter_by(
        admin_id=logged_admin_id,
        tipo_formulario="fundacion",
    ).first()

    cfg_t = FormConfig.query.filter_by(
        admin_id=logged_admin_id,
        tipo_formulario="tarot",
    ).first()

    lista_admins = Admin.query.order_by(Admin.usuario.asc()).all()

    return render_template(
        "admin_ajustes.html",
        admin=logged_admin,
        enlace_fundacion=enlace_fundacion,
        enlace_tarot=enlace_tarot,
        cfg_f=cfg_f,
        cfg_t=cfg_t,
        admins=lista_admins,
        mensaje=mensaje,
        error_msg=error_msg,
    )


@app.route(
    "/admin/admin/eliminar/<int:id>",
    methods=["POST"],
)
def eliminar_admin(id: int):
    logged_admin = get_logged_admin()

    if not logged_admin:
        session.clear()
        return redirect(url_for("admin_login"))

    admin_a_borrar = db.session.get(Admin, id)

    if not admin_a_borrar:
        return redirect(url_for("admin_ajustes"))

    # No permitir borrarse a sí mismo.
    if admin_a_borrar.id == logged_admin.id:
        return redirect(url_for("admin_ajustes"))

    if Admin.query.count() <= 1:
        return redirect(url_for("admin_ajustes"))

    # Evita que queden clientes apuntando a un admin eliminado.
    Cliente.query.filter_by(admin_id=admin_a_borrar.id).update(
        {"admin_id": None}
    )
    FormConfig.query.filter_by(admin_id=admin_a_borrar.id).delete(
        synchronize_session=False
    )

    db.session.delete(admin_a_borrar)
    db.session.commit()

    return redirect(url_for("admin_ajustes"))


@app.route(
    "/admin/cliente/eliminar/<int:id>",
    methods=["POST"],
)
def eliminar_cliente(id: int):
    logged_admin = get_logged_admin()

    if not logged_admin:
        session.clear()
        return redirect(url_for("admin_login"))

    cliente = db.session.get(Cliente, id)

    if not cliente:
        return redirect(url_for("admin_dashboard"))

    if cliente.admin_id != logged_admin.id:
        return redirect(url_for("admin_dashboard"))

    db.session.delete(cliente)
    db.session.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/cliente/perfil/<int:id>")
def ver_perfil_cliente(id: int):
    logged_admin = get_logged_admin()

    if not logged_admin:
        session.clear()
        return redirect(url_for("admin_login"))

    cliente = db.session.get(Cliente, id)

    if not cliente:
        return redirect(url_for("admin_dashboard"))

    if cliente.admin_id != logged_admin.id:
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "perfil_cliente.html",
        cliente=cliente,
    )


# ---------------------------------------------------------------------------
# ARRANQUE
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))

    # debug solo cuando se solicita explícitamente por variable de entorno.
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {
        "1",
        "true",
        "yes",
    }

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
    )