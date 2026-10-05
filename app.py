from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = "skill_exchange.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        bio TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS user_skills (
        user_id INTEGER NOT NULL,
        skill_id INTEGER NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('offer','learn')),
        PRIMARY KEY(user_id, skill_id, type),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        teacher_id INTEGER NOT NULL,
        skill_id INTEGER NOT NULL,
        scheduled_at TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(requester_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER UNIQUE NOT NULL,
        reviewer_id INTEGER NOT NULL,
        reviewee_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
        FOREIGN KEY(reviewer_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(reviewee_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or len(password) < 6:
            flash("Enter a name, valid email, and password of at least 6 characters.")
            return redirect(url_for("register"))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users(name,email,password) VALUES(?,?,?)",
                (name, email, generate_password_hash(password))
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("That email is already registered.")
            return redirect(url_for("register"))

        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        session["user_id"] = user["id"]
        flash("Account created. Complete your profile.")
        return redirect(url_for("profile"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

def get_user_skills(user_id, skill_type):
    conn = get_db()
    rows = conn.execute("""
        SELECT s.id, s.name
        FROM skills s
        JOIN user_skills us ON us.skill_id=s.id
        WHERE us.user_id=? AND us.type=?
        ORDER BY s.name
    """, (user_id, skill_type)).fetchall()
    conn.close()
    return rows

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = session["user_id"]

    if request.method == "POST":
        name = request.form["name"].strip()
        bio = request.form["bio"].strip()
        offered = [x.strip() for x in request.form["offered"].split(",") if x.strip()]
        wanted = [x.strip() for x in request.form["wanted"].split(",") if x.strip()]

        conn = get_db()
        conn.execute("UPDATE users SET name=?, bio=? WHERE id=?", (name, bio, uid))
        conn.execute("DELETE FROM user_skills WHERE user_id=?", (uid,))

        for skill_name in offered:
            conn.execute("INSERT OR IGNORE INTO skills(name) VALUES(?)", (skill_name,))
            sid = conn.execute("SELECT id FROM skills WHERE name=?", (skill_name,)).fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO user_skills(user_id,skill_id,type) VALUES(?,?,?)",
                (uid, sid, "offer")
            )

        for skill_name in wanted:
            conn.execute("INSERT OR IGNORE INTO skills(name) VALUES(?)", (skill_name,))
            sid = conn.execute("SELECT id FROM skills WHERE name=?", (skill_name,)).fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO user_skills(user_id,skill_id,type) VALUES(?,?,?)",
                (uid, sid, "learn")
            )

        conn.commit()
        conn.close()
        flash("Profile updated.")
        return redirect(url_for("profile"))

    user = current_user()
    offered = get_user_skills(uid, "offer")
    wanted = get_user_skills(uid, "learn")
    return render_template("profile.html", user=user, offered=offered, wanted=wanted)

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    offered = get_user_skills(uid, "offer")
    wanted = get_user_skills(uid, "learn")

    conn = get_db()
    pending = conn.execute("""
        SELECT s.*, u.name AS other_name, sk.name AS skill_name
        FROM sessions s
        JOIN users u ON u.id = CASE
            WHEN s.requester_id=? THEN s.teacher_id ELSE s.requester_id END
        JOIN skills sk ON sk.id=s.skill_id
        WHERE (s.requester_id=? OR s.teacher_id=?)
        AND s.status='pending'
        ORDER BY s.scheduled_at
        LIMIT 5
    """, (uid, uid, uid)).fetchall()
    conn.close()

    return render_template("dashboard.html", offered=offered, wanted=wanted, pending=pending)

@app.route("/matches")
@login_required
def matches():
    uid = session["user_id"]
    my_offers = {x["name"].lower() for x in get_user_skills(uid, "offer")}
    my_wants = {x["name"].lower() for x in get_user_skills(uid, "learn")}

    conn = get_db()
    users = conn.execute("SELECT id,name,email,bio FROM users WHERE id != ?", (uid,)).fetchall()

    result = []
    for u in users:
        offers = [dict(x) for x in conn.execute("""
            SELECT s.id,s.name FROM skills s
            JOIN user_skills us ON us.skill_id=s.id
            WHERE us.user_id=? AND us.type='offer'
        """, (u["id"],)).fetchall()]
        learns = [dict(x) for x in conn.execute("""
            SELECT s.id,s.name FROM skills s
            JOIN user_skills us ON us.skill_id=s.id
            WHERE us.user_id=? AND us.type='learn'
        """, (u["id"],)).fetchall()]

        their_offers = {x["name"].lower() for x in offers}
        their_wants = {x["name"].lower() for x in learns}

        # Symmetric compatibility:
        # 1 point if they can teach something I want.
        # 1 point if I can teach something they want.
        score = len(my_wants & their_offers) + len(my_offers & their_wants)

        if score > 0:
            result.append({
                "user": u,
                "offers": offers,
                "learns": learns,
                "score": score,
                "teach_me": sorted(my_wants & their_offers),
                "learn_from_me": sorted(my_offers & their_wants)
            })

    conn.close()
    result.sort(key=lambda x: x["score"], reverse=True)
    return render_template("matches.html", matches=result)

@app.route("/request/<int:teacher_id>/<int:skill_id>", methods=["GET", "POST"])
@login_required
def request_session(teacher_id, skill_id):
    uid = session["user_id"]
    if teacher_id == uid:
        flash("You cannot request a session with yourself.")
        return redirect(url_for("matches"))

    conn = get_db()
    teacher = conn.execute("SELECT * FROM users WHERE id=?", (teacher_id,)).fetchone()
    skill = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()

    valid = conn.execute("""
        SELECT 1 FROM user_skills
        WHERE user_id=? AND skill_id=? AND type='offer'
    """, (teacher_id, skill_id)).fetchone()

    if not teacher or not skill or not valid:
        conn.close()
        flash("Invalid learning request.")
        return redirect(url_for("matches"))

    if request.method == "POST":
        scheduled_at = request.form["scheduled_at"]
        notes = request.form["notes"].strip()
        try:
            datetime.fromisoformat(scheduled_at)
        except ValueError:
            conn.close()
            flash("Choose a valid date and time.")
            return redirect(request.url)

        conn.execute("""
            INSERT INTO sessions(requester_id,teacher_id,skill_id,scheduled_at,notes)
            VALUES(?,?,?,?,?)
        """, (uid, teacher_id, skill_id, scheduled_at, notes))
        conn.commit()
        conn.close()
        flash("Session request sent.")
        return redirect(url_for("requests"))

    conn.close()
    return render_template("request_session.html", teacher=teacher, skill=skill)

@app.route("/requests")
@login_required
def requests():
    uid = session["user_id"]
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*, 
               requester.name AS requester_name,
               teacher.name AS teacher_name,
               sk.name AS skill_name
        FROM sessions s
        JOIN users requester ON requester.id=s.requester_id
        JOIN users teacher ON teacher.id=s.teacher_id
        JOIN skills sk ON sk.id=s.skill_id
        WHERE s.requester_id=? OR s.teacher_id=?
        ORDER BY s.scheduled_at DESC
    """, (uid, uid)).fetchall()
    conn.close()
    return render_template("requests.html", requests=rows)

@app.route("/session/<int:session_id>/<action>", methods=["POST"])
@login_required
def session_action(session_id, action):
    uid = session["user_id"]
    conn = get_db()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()

    if not row or uid not in (row["requester_id"], row["teacher_id"]):
        conn.close()
        flash("Unauthorized.")
        return redirect(url_for("requests"))

    if action in ("accept", "reject", "complete", "cancel"):
        new_status = {
            "accept": "accepted",
            "reject": "rejected",
            "complete": "completed",
            "cancel": "cancelled"
        }[action]
        conn.execute("UPDATE sessions SET status=? WHERE id=?", (new_status, session_id))
        conn.commit()

    conn.close()
    return redirect(url_for("requests"))

@app.route("/review/<int:session_id>", methods=["GET", "POST"])
@login_required
def review(session_id):
    uid = session["user_id"]
    conn = get_db()
    row = conn.execute("""
        SELECT s.*, teacher.name AS teacher_name, requester.name AS requester_name,
               sk.name AS skill_name
        FROM sessions s
        JOIN users teacher ON teacher.id=s.teacher_id
        JOIN users requester ON requester.id=s.requester_id
        JOIN skills sk ON sk.id=s.skill_id
        WHERE s.id=? AND (s.requester_id=? OR s.teacher_id=?)
    """, (session_id, uid, uid)).fetchone()

    if not row or row["status"] != "completed":
        conn.close()
        flash("Only completed sessions can be reviewed.")
        return redirect(url_for("requests"))

    reviewee = row["teacher_id"] if uid == row["requester_id"] else row["requester_id"]

    existing = conn.execute("SELECT id FROM reviews WHERE session_id=?", (session_id,)).fetchone()

    if request.method == "POST":
        if existing:
            conn.close()
            flash("This session has already been reviewed.")
            return redirect(url_for("requests"))

        rating = int(request.form["rating"])
        comment = request.form["comment"].strip()
        conn.execute("""
            INSERT INTO reviews(session_id,reviewer_id,reviewee_id,rating,comment)
            VALUES(?,?,?,?,?)
        """, (session_id, uid, reviewee, rating, comment))
        conn.commit()
        conn.close()
        flash("Review submitted.")
        return redirect(url_for("requests"))

    conn.close()
    return render_template("review.html", session=row)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
