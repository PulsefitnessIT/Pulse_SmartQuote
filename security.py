"""Local pilot authentication and role controls.
Not a substitute for company SSO, HTTPS and centrally managed access controls.
"""
import os, sqlite3, secrets, hashlib, hmac, datetime
from pathlib import Path
DB=Path(__file__).parent/'smartquote_local.db'
ROLES={'coordinator','manager','admin'}

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, role TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
 c.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires TEXT NOT NULL)')
 c.commit();return c

def enabled():return os.getenv('SMARTQUOTE_AUTH','on').lower() not in ('off','0','false')
def count():
 c=db();result=c.execute('SELECT count(*) FROM users').fetchone()[0];c.close();return result

def add_user(username,password,role='coordinator'):
 username=username.strip().lower()
 if not 3<=len(username)<=60 or not all(x.isalnum() or x in '._-' for x in username):raise ValueError('Username should contain 3-60 letters, digits, dots, hyphens or underscores.')
 if role not in ROLES:raise ValueError('Invalid role')
 if len(password)<12:raise ValueError('Password must contain at least 12 characters.')
 salt=secrets.token_bytes(20);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,250000)
 c=db();c.execute('INSERT INTO users VALUES (?,?,?,?,1)',(username,role,salt.hex(),digest.hex()));c.execute('DELETE FROM sessions WHERE username=?',(username,));c.commit();c.close()
 return username

def verify(username,password):
 c=db();r=c.execute('SELECT * FROM users WHERE username=? AND active=1',(str(username).strip().lower(),)).fetchone();c.close()
 if not r:return None
 attempt=hashlib.pbkdf2_hmac('sha256',str(password).encode(),bytes.fromhex(r['salt']),250000)
 return {'username':r['username'],'role':r['role']} if hmac.compare_digest(attempt.hex(),r['password_hash']) else None

def login(username,password):
 user=verify(username,password)
 if not user:return None
 token=secrets.token_urlsafe(40);tokenhash=hashlib.sha256(token.encode()).hexdigest()
 until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=10)).isoformat()
 c=db();c.execute('DELETE FROM sessions WHERE expires<?',(datetime.datetime.now(datetime.timezone.utc).isoformat(),))
 c.execute('INSERT INTO sessions VALUES (?,?,?)',(tokenhash,user['username'],until));c.commit();c.close()
 return {'token':token,'user':user,'expires':until}

def identify(token):
 if not token:return None
 c=db();row=c.execute('SELECT u.username,u.role FROM sessions s JOIN users u ON u.username=s.username WHERE s.token_hash=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),datetime.datetime.now(datetime.timezone.utc).isoformat())).fetchone();c.close()
 return dict(row) if row else None

def logout(token):
 c=db();c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),));c.commit();c.close()


def list_users():
 c=db();rows=c.execute('SELECT username,role,active FROM users ORDER BY username').fetchall();c.close()
 return [dict(x) for x in rows]

def create_user(username,password,role='coordinator'):
 name=username.strip().lower()
 c=db();exists=c.execute('SELECT 1 FROM users WHERE username=?',(name,)).fetchone();c.close()
 if exists:raise ValueError('This username already exists. Use Reset Password instead.')
 return add_user(name,password,role)

def set_user_status(username,active,acting_username):
 name=username.strip().lower()
 if name==acting_username.lower() and not active:raise ValueError('You cannot deactivate your own account.')
 c=db();item=c.execute('SELECT role FROM users WHERE username=?',(name,)).fetchone()
 if not item:c.close();raise ValueError('Account does not exist.')
 if item['role']=='admin' and not active and c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:
  c.close();raise ValueError('At least one active administrator is required.')
 c.execute('UPDATE users SET active=? WHERE username=?',(int(active),name))
 if not active:c.execute('DELETE FROM sessions WHERE username=?',(name,))
 c.commit();c.close()

def reset_password(username,password):
 name=username.strip().lower()
 if len(password)<12:raise ValueError('Password must have 12 or more characters.')
 c=db();row=c.execute('SELECT username FROM users WHERE username=?',(name,)).fetchone()
 if not row:c.close();raise ValueError('User does not exist.')
 salt=secrets.token_bytes(20);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,250000)
 c.execute('UPDATE users SET salt=?, password_hash=? WHERE username=?',(salt.hex(),digest.hex(),name))
 c.execute('DELETE FROM sessions WHERE username=?',(name,));c.commit();c.close()
