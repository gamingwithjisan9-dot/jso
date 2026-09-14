
import os, re, sqlite3, secrets
from functools import wraps
from urllib.parse import urlparse
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")
DB_PATH = os.getenv("DATABASE_PATH", "jso_ai.db")
AI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free',
        subscription_status TEXT NOT NULL DEFAULT 'inactive',
        subscription_expires_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS websites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        title TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        website_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        report_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(website_id) REFERENCES websites(id)
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        plan TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        provider TEXT,
        provider_reference TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    conn.commit()
    conn.close()

def now():
    return datetime.now(timezone.utc).isoformat()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def valid_url(url):
    try:
        p = urlparse(url if "://" in url else "https://" + url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def normalize_url(url):
    return url if "://" in url else "https://" + url

def analyze_website(url):
    url = normalize_url(url)
    result = {
        "url": url, "title": "", "description": "", "h1": 0, "images": 0,
        "images_without_alt": 0, "links": 0, "https": url.startswith("https://"),
        "score": 0, "issues": [], "keywords": []
    }
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent":"JSO-AI-SEO-Analyzer/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        desc_tag = soup.find("meta", attrs={"name":"description"})
        desc = desc_tag.get("content", "").strip() if desc_tag else ""
        h1s = soup.find_all("h1")
        imgs = soup.find_all("img")
        links = soup.find_all("a")
        result.update({
            "title": title,
            "description": desc,
            "h1": len(h1s),
            "images": len(imgs),
            "images_without_alt": sum(1 for x in imgs if not x.get("alt", "").strip()),
            "links": len(links),
        })
        score = 100
        if not result["https"]:
            score -= 15; result["issues"].append("HTTPS is not detected.")
        if not title:
            score -= 15; result["issues"].append("Missing page title.")
        elif len(title) < 30 or len(title) > 60:
            score -= 8; result["issues"].append("Title length could be improved (target roughly 30–60 characters).")
        if not desc:
            score -= 15; result["issues"].append("Missing meta description.")
        elif len(desc) < 70 or len(desc) > 160:
            score -= 8; result["issues"].append("Meta description length could be improved.")
        if len(h1s) == 0:
            score -= 12; result["issues"].append("No H1 heading detected.")
        elif len(h1s) > 1:
            score -= 5; result["issues"].append("More than one H1 heading detected.")
        if result["images_without_alt"]:
            score -= min(10, result["images_without_alt"] * 2)
            result["issues"].append(f"{result['images_without_alt']} image(s) are missing useful alt text.")
        text = soup.get_text(" ", strip=True)
        words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text.lower())
        stop = {"the","and","for","with","this","that","from","your","you","are","was","have","has","our","www","http","https"}
        freq = {}
        for w in words:
            if w not in stop:
                freq[w] = freq.get(w, 0) + 1
        result["keywords"] = [w for w,_ in sorted(freq.items(), key=lambda x:x[1], reverse=True)[:12]]
        result["score"] = max(0, min(100, score))
    except Exception as e:
        result["issues"].append("The website could not be fetched. Check the URL and whether the site allows automated requests.")
        result["error"] = str(e)
        result["score"] = 0
    return result

def ai_enhance(report):
    # Optional OpenAI integration. The app works in demo/fallback mode without an API key.
    if not AI_API_KEY:
        return {
            "summary": f"Your current SEO score is {report['score']}/100. Fix the highest-impact technical and on-page issues first.",
            "recommendations": [
                "Improve the page title around one clear search intent.",
                "Write a useful meta description that explains the page value.",
                "Use one clear H1 and logical H2/H3 sections.",
                "Add descriptive alt text to important images.",
                "Create content around the strongest relevant keyword opportunities."
            ]
        }
    try:
        from openai import OpenAI
        client = OpenAI(api_key=AI_API_KEY)
        prompt = f"""You are an SEO analyst. Analyze this website audit and return concise JSON with keys
summary (string) and recommendations (array of 5 strings). Do not promise rankings.
Audit: {report}"""
        response = client.responses.create(model=AI_MODEL, input=prompt)
        text = response.output_text
        return {"summary": text, "recommendations": []}
    except Exception:
        return {
            "summary": f"AI enhancement was unavailable, so JSO AI returned the local audit. Score: {report['score']}/100.",
            "recommendations": report["issues"][:5] or ["Continue publishing useful, search-intent-focused content."]
        }

@app.route("/")
def home():
    return render_template("landing.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not name or not email or len(password) < 8:
            flash("Name, valid email and a password of at least 8 characters are required.", "error")
            return render_template("signup.html")
        try:
            db().execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                (name,email,generate_password_hash(password),now())
            )
            db().commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "error")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.get("/dashboard")
@login_required
def dashboard():
    user = db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    sites = db().execute("SELECT * FROM websites WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    reports = db().execute("""
        SELECT reports.*, websites.url FROM reports
        JOIN websites ON websites.id=reports.website_id
        WHERE reports.user_id=? ORDER BY reports.id DESC LIMIT 10
    """, (user["id"],)).fetchall()
    return render_template("dashboard.html", user=user, sites=sites, reports=reports)

@app.post("/api/analyze")
@login_required
def api_analyze():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not valid_url(url):
        return jsonify({"error":"Please enter a valid website URL."}), 400
    url = normalize_url(url)
    conn = db()
    existing = conn.execute("SELECT * FROM websites WHERE user_id=? AND url=?", (session["user_id"],url)).fetchone()
    if existing:
        website_id = existing["id"]
    else:
        website_id = conn.execute(
            "INSERT INTO websites(user_id,url,created_at) VALUES(?,?,?)",
            (session["user_id"],url,now())
        ).lastrowid
        conn.commit()
    report = analyze_website(url)
    ai = ai_enhance(report)
    import json
    payload = {"audit": report, "ai": ai}
    report_id = conn.execute(
        "INSERT INTO reports(user_id,website_id,score,report_json,created_at) VALUES(?,?,?,?,?)",
        (session["user_id"],website_id,report["score"],json.dumps(payload),now())
    ).lastrowid
    conn.commit()
    return jsonify({"id":report_id, **payload})

@app.post("/api/create-checkout")
@login_required
def create_checkout():
    # Demo checkout. Replace this endpoint with a real payment provider's hosted-checkout API.
    conn = db()
    payment_id = conn.execute(
        "INSERT INTO payments(user_id,amount,currency,plan,status,provider,created_at) VALUES(?,?,?,?,?,?,?)",
        (session["user_id"],0.99,"USD","starter","demo_pending","DEMO",now())
    ).lastrowid
    conn.commit()
    return jsonify({
        "payment_id": payment_id,
        "message": "Demo checkout created. Connect a real merchant/payment provider before accepting money."
    })

@app.post("/api/demo-payment-success")
@login_required
def demo_payment_success():
    conn = db()
    conn.execute("UPDATE payments SET status='paid' WHERE id=? AND user_id=?",
                 (request.json.get("payment_id"),session["user_id"]))
    conn.execute("""
        UPDATE users SET plan='starter', subscription_status='active',
        subscription_expires_at=? WHERE id=?
    """, (datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year+1).isoformat(), session["user_id"]))
    conn.commit()
    return jsonify({"ok":True})

@app.get("/report/<int:report_id>")
@login_required
def report(report_id):
    import json
    row = db().execute("""
        SELECT reports.*, websites.url FROM reports
        JOIN websites ON websites.id=reports.website_id
        WHERE reports.id=? AND reports.user_id=?
    """, (report_id,session["user_id"])).fetchone()
    if not row:
        return "Report not found",404
    return render_template("report.html", report=row, data=json.loads(row["report_json"]))

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT","5000")), debug=True)
