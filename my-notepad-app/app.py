
import os
from datetime import timedelta, datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from slugify import slugify
import secrets

# --- App Config ---
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///notepad.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Remember-me style sessions (30 days)
app.permanent_session_lifetime = timedelta(days=30)

db = SQLAlchemy(app)

# --- Models ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folder.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default="")
    is_public = db.Column(db.Boolean, default=False, index=True)
    slug = db.Column(db.String(255), unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("folder.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- Helpers ---
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)

def login_required():
    if not current_user():
        flash("Please log in to access that page.", "warning")
        return redirect(url_for("login", next=request.path))
    return None

def ensure_owner(obj_user_id):
    u = current_user()
    if not u or u.id != obj_user_id:
        abort(403)

def unique_slug(base):
    base = slugify(base)[:180] or "note"
    candidate = base
    i = 1
    while db.session.execute(db.select(Note.id).filter_by(slug=candidate)).scalar():
        i += 1
        candidate = f"{base}-{i}"
    return candidate

# --- Routes ---

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route("/")
def home():
    u = current_user()
    if u:
        # Personalized welcome
        return render_template("home.html", user=u)
    else:
        return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))
        if db.session.execute(db.select(User.id).filter_by(email=email)).scalar():
            flash("Email already registered. Try logging in.", "warning")
            return redirect(url_for("login"))
        pwd_hash = generate_password_hash(password)
        user = User(name=name, email=email, password_hash=pwd_hash)
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        flash("Welcome! Account created.", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            flash("Logged in successfully.", "success")
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        flash("Invalid credentials.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    guard = login_required()
    if guard: return guard
    u = current_user()
    # Root folders (no parent) and uncategorized notes
    folders = db.session.execute(
        db.select(Folder).filter_by(user_id=u.id, parent_id=None).order_by(Folder.created_at.desc())
    ).scalars().all()
    notes = db.session.execute(
        db.select(Note).filter_by(user_id=u.id, folder_id=None).order_by(Note.updated_at.desc())
    ).scalars().all()
    return render_template("dashboard.html", user=u, folders=folders, notes=notes)

@app.route("/profile", methods=["GET","POST"])
def profile():
    guard = login_required()
    if guard: return guard
    u = current_user()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if name:
            u.name = name
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html", user=u)

# --- Folder CRUD ---
@app.route("/folders/create", methods=["POST"])
def create_folder():
    guard = login_required()
    if guard: return guard
    u = current_user()
    name = request.form.get("name","").strip()
    parent_id = request.form.get("parent_id")
    parent = None
    if parent_id:
        parent = db.session.get(Folder, int(parent_id))
        if parent: ensure_owner(parent.user_id)
    if not name:
        flash("Folder name is required.", "danger")
        return redirect(url_for("dashboard"))
    f = Folder(name=name, user_id=u.id, parent_id=parent.id if parent else None)
    db.session.add(f)
    db.session.commit()
    flash("Folder created.", "success")
    return redirect(url_for("view_folder", folder_id=f.id) if f.id else url_for("dashboard"))

@app.route("/folders/<int:folder_id>")
def view_folder(folder_id):
    guard = login_required()
    if guard: return guard
    u = current_user()
    folder = db.session.get(Folder, folder_id)
    if not folder: abort(404)
    ensure_owner(folder.user_id)
    subfolders = db.session.execute(
        db.select(Folder).filter_by(parent_id=folder.id).order_by(Folder.created_at.desc())
    ).scalars().all()
    notes = db.session.execute(
        db.select(Note).filter_by(folder_id=folder.id).order_by(Note.updated_at.desc())
    ).scalars().all()
    return render_template("folder.html", user=u, folder=folder, subfolders=subfolders, notes=notes)

@app.route("/folders/<int:folder_id>/delete", methods=["POST"])
def delete_folder(folder_id):
    guard = login_required()
    if guard: return guard
    folder = db.session.get(Folder, folder_id)
    if not folder: abort(404)
    ensure_owner(folder.user_id)
    # Move children up (simple safe delete)
    for note in db.session.execute(db.select(Note).filter_by(folder_id=folder.id)).scalars():
        note.folder_id = None
    for sub in db.session.execute(db.select(Folder).filter_by(parent_id=folder.id)).scalars():
        sub.parent_id = None
    db.session.delete(folder)
    db.session.commit()
    flash("Folder deleted.", "info")
    return redirect(url_for("dashboard"))

# --- Note CRUD ---
@app.route("/notes/new", methods=["GET","POST"])
def new_note():
    guard = login_required()
    if guard: return guard
    u = current_user()
    if request.method == "POST":
        title = request.form.get("title","").strip() or "Untitled"
        content = request.form.get("content","")
        is_public = bool(request.form.get("is_public"))
        folder_id = request.form.get("folder_id")
        folder = db.session.get(Folder, int(folder_id)) if folder_id else None
        if folder: ensure_owner(folder.user_id)
        note = Note(
            title=title,
            content=content,
            is_public=is_public,
            slug=unique_slug(title) if is_public else None,
            user_id=u.id,
            folder_id=folder.id if folder else None
        )
        db.session.add(note)
        db.session.commit()
        flash("Note created.", "success")
        return redirect(url_for("edit_note", note_id=note.id))
    # GET
    folders = db.session.execute(db.select(Folder).filter_by(user_id=u.id).order_by(Folder.name)).scalars().all()
    return render_template("note_new.html", user=u, folders=folders)

@app.route("/notes/<int:note_id>/edit", methods=["GET","POST"])
def edit_note(note_id):
    guard = login_required()
    if guard: return guard
    u = current_user()
    note = db.session.get(Note, note_id)
    if not note: abort(404)
    ensure_owner(note.user_id)
    if request.method == "POST":
        note.title = request.form.get("title","").strip() or "Untitled"
        note.content = request.form.get("content","")
        make_public = bool(request.form.get("is_public"))
        # Toggle public/private
        if make_public and not note.is_public:
            note.is_public = True
            note.slug = unique_slug(note.title)
        elif not make_public and note.is_public:
            note.is_public = False
            note.slug = None
        folder_id = request.form.get("folder_id")
        note.folder_id = int(folder_id) if folder_id else None
        db.session.commit()
        flash("Note updated.", "success")
        return redirect(url_for("edit_note", note_id=note.id))
    folders = db.session.execute(db.select(Folder).filter_by(user_id=u.id).order_by(Folder.name)).scalars().all()
    return render_template("note_edit.html", user=u, note=note, folders=folders)

@app.route("/notes/<int:note_id>/delete", methods=["POST"])
def delete_note(note_id):
    guard = login_required()
    if guard: return guard
    note = db.session.get(Note, note_id)
    if not note: abort(404)
    ensure_owner(note.user_id)
    db.session.delete(note)
    db.session.commit()
    flash("Note deleted.", "info")
    return redirect(url_for("dashboard"))

# --- Public note view ---
@app.route("/p/<slug>")
def public_note(slug):
    note = db.session.execute(db.select(Note).filter_by(slug=slug, is_public=True)).scalar_one_or_none()
    if not note:
        abort(404)
    # Minimal public page, no auth needed
    owner = db.session.get(User, note.user_id)
    return render_template("public_note.html", note=note, owner=owner)

# --- CLI helper to init DB ---
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
