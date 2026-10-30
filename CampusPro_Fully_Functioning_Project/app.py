import json
import os
import uuid
from functools import wraps
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import get_connection, init_db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key-before-deployment"
)

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["PROJECT_UPLOAD_FOLDER"] = os.path.join(
    app.root_path, "static", "uploads", "projects"
)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_PROJECT_IMAGES = 5
MAX_IMAGE_SIZE = 3 * 1024 * 1024

ALLOWED_DEPARTMENTS = {
    "CSE", "IT", "ECE", "EEE",
    "Mechanical", "Civil", "Other"
}

PROJECT_STATUSES = {
    "Submitted", "Under Review", "Approved", "Needs Changes"
}


def prepare_project_images(projects):
    for project in projects:
        try:
            images = json.loads(project.get("image_paths") or "[]")
            project["images"] = (
                images if isinstance(images, list)
                and all(isinstance(image, str) for image in images)
                else []
            )
        except (ValueError, TypeError):
            project["images"] = []

    return projects


def valid_project_link(link):
    if not link:
        return True

    try:
        parsed = urlparse(link)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not any(character.isspace() for character in link)
        )
    except ValueError:
        return False


def valid_image_signature(file):
    header = file.read(12)
    file.seek(0)

    return (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (
            len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        )
    )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in first.", "warning")
            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please sign in first.", "warning")
                return redirect(url_for("login"))

            if session.get("role") not in roles:
                flash(
                    "You do not have permission to access that page.",
                    "danger"
                )
                return redirect(url_for("dashboard"))

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def get_user_dashboard():
    dashboards = {
        "admin": "admin_dashboard",
        "faculty": "faculty_dashboard",
        "student": "student_dashboard"
    }

    return dashboards.get(session.get("role"), "index")


@app.context_processor
def inject_user():
    current_user = None

    if session.get("user_id"):
        current_user = {
            "name": session.get("name"),
            "role": session.get("role")
        }

    return {"current_user": current_user}


@app.errorhandler(413)
def request_too_large(_error):
    flash(
        "The total upload is too large. Keep the whole submission under 16 MB.",
        "danger"
    )

    if session.get("role") == "student":
        return redirect(url_for("project_form"))

    return redirect(url_for("index"))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        department = request.form.get("department", "").strip()

        if not all([name, email, password, confirm_password, department]):
            flash("Please complete every field.", "danger")
            return render_template("register.html")

        if len(name) > 100 or len(email) > 190:
            flash("Name or email exceeds the allowed length.", "danger")
            return render_template("register.html")

        if department not in ALLOWED_DEPARTMENTS:
            flash("Please select a valid department.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        conn = get_connection()

        if conn is None:
            flash(
                "Database connection failed. Check MySQL and your .env settings.",
                "danger"
            )
            return render_template("register.html")

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users
                        (name, email, password_hash, role, department)
                    VALUES (%s, %s, %s, 'student', %s)
                    """,
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        department
                    )
                )

            conn.commit()
            flash("Account created successfully. Please sign in.", "success")
            return redirect(url_for("login"))

        except Exception as exc:
            conn.rollback()

            if "duplicate" in str(exc).lower() or "1062" in str(exc):
                flash("That email is already registered.", "warning")
            else:
                app.logger.exception("Registration failed")
                flash(
                    "Could not create account. Check the database configuration.",
                    "danger"
                )

        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "student").strip().lower()

        if selected_role not in {"student", "faculty", "admin"}:
            flash("Please select a valid role.", "danger")
            return render_template("login.html")

        conn = get_connection()

        if conn is None:
            flash("Database connection failed. Check MySQL settings.", "danger")
            return render_template("login.html")

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM users WHERE email = %s",
                    (email,)
                )
                user = cur.fetchone()

            if (
                user
                and user.get("is_active", 1)
                and check_password_hash(user["password_hash"], password)
                and user["role"] == selected_role
            ):
                session.clear()
                session["user_id"] = user["id"]
                session["name"] = user["name"]
                session["email"] = user["email"]
                session["role"] = user["role"]
                session["department"] = user.get("department", "")

                flash("Welcome back, " + user["name"] + "!", "success")
                return redirect(url_for("dashboard"))

            flash(
                "Invalid email, password, or selected role.",
                "danger"
            )

        except Exception:
            app.logger.exception("Login failed")
            flash("Unable to sign in. Please try again.", "danger")

        finally:
            conn.close()

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for(get_user_dashboard()))


@app.route("/student/dashboard")
@login_required
@role_required("student")
def student_dashboard():
    conn = get_connection()

    if conn is None:
        flash("Database connection failed. Please try again.", "danger")
        return render_template("student_dashboard.html", projects=[])

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM projects
                WHERE owner_id = %s
                ORDER BY created_at DESC
                """,
                (session["user_id"],)
            )
            projects = prepare_project_images(cur.fetchall())

        return render_template(
            "student_dashboard.html",
            projects=projects
        )

    except Exception:
        app.logger.exception("Could not load student projects")
        flash("Could not load your projects.", "danger")
        return render_template("student_dashboard.html", projects=[])

    finally:
        conn.close()


@app.route("/projects/new", methods=["GET", "POST"])
@login_required
@role_required("student")
def project_form():
    if request.method == "GET":
        return render_template("project_form.html")

    title = request.form.get("title", "").strip()
    abstract = request.form.get("abstract", "").strip()
    tech_stack = request.form.get("tech_stack", "").strip()
    project_link = request.form.get("project_link", "").strip() or None

    if not title or not abstract:
        flash("Project title and abstract are required.", "danger")
        return render_template("project_form.html"), 400

    if (
        len(title) > 200
        or len(abstract) > 5000
        or len(tech_stack) > 255
    ):
        flash("One or more fields exceed the allowed length.", "danger")
        return render_template("project_form.html"), 400

    if project_link and (
        len(project_link) > 2048
        or not valid_project_link(project_link)
    ):
        flash(
            "Enter a valid project URL beginning with http:// or https://.",
            "danger"
        )
        return render_template("project_form.html"), 400

    files = [
        file for file in request.files.getlist("project_images")
        if file and file.filename
    ]

    if len(files) > MAX_PROJECT_IMAGES:
        flash("You can upload a maximum of 5 images.", "danger")
        return render_template("project_form.html"), 400

    os.makedirs(app.config["PROJECT_UPLOAD_FOLDER"], exist_ok=True)

    saved_files = []
    relative_paths = []
    conn = None

    try:
        for file in files:
            safe_name = secure_filename(file.filename)

            if (
                not safe_name
                or "." not in safe_name
                or safe_name.rsplit(".", 1)[1].lower()
                not in ALLOWED_IMAGE_EXTENSIONS
            ):
                raise ValueError(
                    "Only JPG, JPEG, PNG and WebP images are allowed."
                )

            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)

            if size == 0 or size > MAX_IMAGE_SIZE:
                raise ValueError(
                    "Each image must be larger than 0 bytes "
                    "and no bigger than 3 MB."
                )

            if not valid_image_signature(file):
                raise ValueError(
                    "An uploaded file is not a valid JPG, PNG or WebP image."
                )

            extension = safe_name.rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{extension}"
            destination = os.path.join(
                app.config["PROJECT_UPLOAD_FOLDER"],
                filename
            )

            file.save(destination)
            saved_files.append(destination)
            relative_paths.append(f"uploads/projects/{filename}")

        conn = get_connection()

        if conn is None:
            raise RuntimeError(
                "Database connection failed. Check MySQL and your .env settings."
            )

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects
                    (title, abstract, tech_stack, owner_id,
                     project_link, image_paths, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Submitted')
                """,
                (
                    title,
                    abstract,
                    tech_stack,
                    session["user_id"],
                    project_link,
                    json.dumps(relative_paths)
                )
            )

        conn.commit()
        flash("Project submitted successfully.", "success")
        return redirect(url_for("student_dashboard"))

    except ValueError as exc:
        if conn:
            conn.rollback()

        for path in saved_files:
            if os.path.exists(path):
                os.remove(path)

        flash(str(exc), "danger")
        return render_template("project_form.html"), 400

    except Exception:
        if conn:
            conn.rollback()

        for path in saved_files:
            if os.path.exists(path):
                os.remove(path)

        app.logger.exception("Project submission failed")
        flash(
            "Could not submit project. Check MySQL and the server logs.",
            "danger"
        )
        return render_template("project_form.html"), 500

    finally:
        if conn:
            conn.close()


@app.route("/faculty/dashboard")
@login_required
@role_required("faculty", "admin")
def faculty_dashboard():
    conn = get_connection()

    if conn is None:
        flash("Database connection failed.", "danger")
        return render_template("faculty_dashboard.html", projects=[])

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.*, u.name AS student_name, u.email AS student_email
                FROM projects p
                JOIN users u ON p.owner_id = u.id
                ORDER BY p.created_at DESC
                """
            )
            projects = prepare_project_images(cur.fetchall())

        return render_template(
            "faculty_dashboard.html",
            projects=projects
        )

    except Exception:
        app.logger.exception("Could not load faculty dashboard")
        flash("Could not load projects.", "danger")
        return render_template("faculty_dashboard.html", projects=[])

    finally:
        conn.close()


@app.route("/projects/<int:project_id>/status", methods=["POST"])
@login_required
@role_required("faculty", "admin")
def update_project_status(project_id):
    status = request.form.get("status", "")

    if status not in PROJECT_STATUSES:
        flash("Invalid project status.", "danger")
        return redirect(url_for("faculty_dashboard"))

    conn = get_connection()

    if conn is None:
        flash("Database connection failed.", "danger")
        return redirect(url_for("faculty_dashboard"))

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE projects SET status = %s WHERE id = %s",
                (status, project_id)
            )

            if cur.rowcount == 0:
                flash("Project not found or status unchanged.", "warning")
            else:
                flash("Project status updated.", "success")

        conn.commit()

    except Exception:
        conn.rollback()
        app.logger.exception("Project status update failed")
        flash("Could not update the project status.", "danger")

    finally:
        conn.close()

    return redirect(url_for("faculty_dashboard"))


@app.route("/admin/dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    conn = get_connection()

    users = []
    projects = []
    stats = {
        "users": 0,
        "students": 0,
        "faculty": 0,
        "projects": 0
    }

    if conn is None:
        flash("Database connection failed.", "danger")
        return render_template(
            "admin_dashboard.html",
            users=users,
            projects=projects,
            stats=stats
        )

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, department, created_at
                FROM users
                ORDER BY created_at DESC
                """
            )
            users = cur.fetchall()

            cur.execute(
                """
                SELECT p.*, u.name AS student_name, u.email AS student_email
                FROM projects p
                JOIN users u ON p.owner_id = u.id
                ORDER BY p.created_at DESC
                """
            )
            projects = prepare_project_images(cur.fetchall())

            queries = {
                "users": "SELECT COUNT(*) AS n FROM users",
                "students": "SELECT COUNT(*) AS n FROM users WHERE role='student'",
                "faculty": "SELECT COUNT(*) AS n FROM users WHERE role='faculty'",
                "projects": "SELECT COUNT(*) AS n FROM projects"
            }

            for key, query in queries.items():
                cur.execute(query)
                stats[key] = cur.fetchone()["n"]

        return render_template(
            "admin_dashboard.html",
            users=users,
            projects=projects,
            stats=stats
        )

    except Exception:
        app.logger.exception("Could not load admin dashboard")
        flash("Could not load the admin dashboard.", "danger")
        return render_template(
            "admin_dashboard.html",
            users=[],
            projects=[],
            stats=stats
        )

    finally:
        conn.close()


@app.route("/admin/faculty/create", methods=["POST"])
@login_required
@role_required("admin")
def create_faculty():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    department = request.form.get("department", "").strip()
    password = request.form.get("password", "")

    if not all([name, email, department, password]):
        flash("Complete all faculty account fields.", "danger")
        return redirect(url_for("admin_dashboard"))

    if len(name) > 100 or len(email) > 190:
        flash("Name or email exceeds the allowed length.", "danger")
        return redirect(url_for("admin_dashboard"))

    if department not in ALLOWED_DEPARTMENTS:
        flash("Please select a valid department.", "danger")
        return redirect(url_for("admin_dashboard"))

    if len(password) < 8:
        flash("Faculty password must contain at least 8 characters.", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = get_connection()

    if conn is None:
        flash("Database connection failed.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users
                    (name, email, password_hash, role, department)
                VALUES (%s, %s, %s, 'faculty', %s)
                """,
                (
                    name,
                    email,
                    generate_password_hash(password),
                    department
                )
            )

        conn.commit()
        flash("Faculty account created successfully.", "success")

    except Exception as exc:
        conn.rollback()

        if "duplicate" in str(exc).lower() or "1062" in str(exc):
            flash("That email is already registered.", "warning")
        else:
            app.logger.exception("Faculty account creation failed")
            flash("Could not create the faculty account.", "danger")

    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@role_required("admin")
def change_user_role(user_id):
    role = request.form.get("role", "")

    if role not in {"student", "faculty"} or user_id == session["user_id"]:
        flash("Invalid role change.", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = get_connection()

    if conn is None:
        flash("Database connection failed.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET role = %s
                WHERE id = %s AND role <> 'admin'
                """,
                (role, user_id)
            )

        conn.commit()
        flash("User role updated.", "success")

    except Exception:
        conn.rollback()
        app.logger.exception("User role update failed")
        flash("Could not update the user role.", "danger")

    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
