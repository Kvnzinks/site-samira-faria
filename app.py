#!/usr/bin/env python3
"""Samira Faria - agendamento. Somente biblioteca padrão Python 3.10+."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import traceback
import threading
import urllib.parse
import smtplib
import ssl
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / 'agenda.sqlite3'
STATIC = ROOT / 'static'
try:
    TZ = ZoneInfo('America/Sao_Paulo')
except ZoneInfoNotFoundError:  # Windows sem banco IANA de fusos: horário de Brasília atual.
    TZ = timezone(timedelta(hours=-3))
PORT = int(os.environ.get('PORT', '8080'))
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@samira.local').strip().lower()
COOKIE_NAME = 'samira_session'
SESSION_DAYS = 14
BOOKING_DAYS = 60
DAYS_PT = ['Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado','Domingo']


def now_local():
    return datetime.now(TZ).replace(tzinfo=None)


def db_conn():
    con = sqlite3.connect(DB_PATH, timeout=8)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.execute('PRAGMA busy_timeout = 8000')
    return con


def pass_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf8'), salt, 280_000)
    return 'pbkdf2_sha256$280000$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def pass_check(password, encoded):
    try:
        algorithm, iterations, salt64, value64 = encoded.split('$')
        if algorithm != 'pbkdf2_sha256': return False
        dig = hashlib.pbkdf2_hmac('sha256', password.encode('utf8'), base64.b64decode(salt64), int(iterations))
        return hmac.compare_digest(dig, base64.b64decode(value64))
    except Exception:
        return False


def initialize():
    with db_conn() as con:
        con.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                phone TEXT DEFAULT '', password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'client' CHECK (role IN ('admin','client')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                csrf TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                category TEXT NOT NULL, description TEXT NOT NULL,
                duration INTEGER NOT NULL, price_cents INTEGER,
                active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS weekly_hours (
                weekday INTEGER PRIMARY KEY, enabled INTEGER NOT NULL,
                open_time TEXT NOT NULL, close_time TEXT NOT NULL,
                break_start TEXT NOT NULL, break_end TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blackouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL UNIQUE, reason TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                service_id INTEGER NOT NULL REFERENCES services(id),
                start_at TEXT NOT NULL, end_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','completed','cancelled')),
                notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_appt_time ON appointments (start_at,end_at,status);
            CREATE INDEX IF NOT EXISTS idx_appt_user ON appointments (user_id);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        if not con.execute('SELECT 1 FROM services LIMIT 1').fetchone():
            con.executemany('INSERT INTO services(title,category,description,duration,price_cents,sort_order) VALUES(?,?,?,?,?,?)', [
                ('Design de sobrancelhas', 'Sobrancelhas', 'Um olhar em harmonia com a sua beleza natural.', 45, None, 1),
                ('Micropigmentação', 'Micropigmentação', 'Realce delicado, respeitando seus traços e sua expressão.', 90, None, 2),
                ('Estética facial', 'Estética facial', 'Cuidado personalizado para valorizar a sua pele.', 60, None, 3),
                ('Avaliação personalizada', 'Avaliação', 'Uma conversa especial para entender seus objetivos e indicar o cuidado ideal.', 30, None, 4),
            ])
        if not con.execute('SELECT 1 FROM weekly_hours LIMIT 1').fetchone():
            con.executemany('INSERT INTO weekly_hours(weekday,enabled,open_time,close_time,break_start,break_end) VALUES(?,?,?,?,?,?)', [
                (i,1 if i<6 else 0, '09:00','18:00' if i<5 else '13:00','12:00' if i<5 else '','13:00' if i<5 else '') for i in range(7)
            ])
        defaults = {
            'business_name':'Samira Faria',
            'tagline':'Mais que procedimentos, realçamos a sua beleza real.',
            'subtitle':'Micropigmentação · Estética facial · Sobrancelhas',
            'instagram':'sa.dbrows',
            'whatsapp':'5511949222083',
            'booking_redirect':'whatsapp',
            'location':'São Paulo · Zona Norte',
            'address':'',
            'booking_notice':'Os horários e durações cadastrados inicialmente são exemplos. A profissional confirmará as informações do atendimento.',
            'notification_email':'',
            'notify_new_booking':'1',
            'smtp_host':'',
            'smtp_port':'587',
            'smtp_security':'tls',
            'smtp_user':'',
            'smtp_password':'',
            'smtp_from':'',
            'smtp_from_name':'Samira Faria',
        }
        for k,v in defaults.items():
            con.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
        # Atualiza o WhatsApp padrão caso a versão anterior esteja sem número configurado.
        current_whatsapp = con.execute("SELECT value FROM settings WHERE key='whatsapp'").fetchone()
        if current_whatsapp and not str(current_whatsapp['value']).strip():
            con.execute("UPDATE settings SET value=? WHERE key='whatsapp'", ('5511949222083',))
        current_redirect = con.execute("SELECT value FROM settings WHERE key='booking_redirect'").fetchone()
        if current_redirect and not str(current_redirect['value']).strip():
            con.execute("UPDATE settings SET value='whatsapp' WHERE key='booking_redirect'")
        if not con.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            password = os.environ.get('ADMIN_PASSWORD', '')
            if not password:
                password = secrets.token_urlsafe(13)
                print('\n' + '='*62)
                print(' ACESSO ADMINISTRATIVO INICIAL (guarde estas informações)')
                print(' E-mail:', ADMIN_EMAIL)
                print(' Senha: ', password)
                print(' DICA: defina ADMIN_PASSWORD antes do primeiro acesso.')
                print('='*62 + '\n', flush=True)
            elif len(password) < 10:
                raise RuntimeError('ADMIN_PASSWORD deve ter pelo menos 10 caracteres.')
            con.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                        ('Samira Faria', ADMIN_EMAIL, pass_hash(password), 'admin', now_local().isoformat(timespec='seconds')))
        con.execute('DELETE FROM sessions WHERE expires_at < ?', (now_local().isoformat(),))


def clean_user(row):
    return {'id':row['id'],'name':row['name'],'email':row['email'],'phone':row['phone'],'role':row['role']} if row else None


PUBLIC_SETTING_KEYS = {
    'business_name','tagline','subtitle','instagram','whatsapp','booking_redirect','location','address','booking_notice'
}
PRIVATE_SETTING_KEYS = {
    'notification_email','notify_new_booking','smtp_host','smtp_port','smtp_security','smtp_user','smtp_password','smtp_from','smtp_from_name'
}

def settings_dict(con, public_only=True):
    data = {r['key']:r['value'] for r in con.execute('SELECT key,value FROM settings')}
    if public_only:
        return {k:v for k,v in data.items() if k in PUBLIC_SETTING_KEYS}
    return data

def notification_settings_dict(con):
    data = settings_dict(con, public_only=False)
    return {k:data.get(k,'') for k in PRIVATE_SETTING_KEYS}

def send_booking_notification(con, appointment_id):
    cfg = notification_settings_dict(con)
    if str(cfg.get('notify_new_booking','1')).strip() not in ('1','true','True','sim','yes','on'):
        return False, 'notificações desativadas'
    host = str(cfg.get('smtp_host','')).strip()
    to_email = str(cfg.get('notification_email','')).strip()
    from_email = str(cfg.get('smtp_from','')).strip() or str(cfg.get('smtp_user','')).strip()
    if not host or not to_email or not from_email:
        return False, 'configuração SMTP incompleta'
    try:
        port = int(str(cfg.get('smtp_port','587')).strip() or '587')
    except ValueError:
        return False, 'porta SMTP inválida'
    sql = (
        "SELECT a.id, a.start_at, a.notes, u.name AS client_name, u.email AS client_email, u.phone AS client_phone, "
        "s.title AS service_title, s.duration AS service_duration "
        "FROM appointments a "
        "JOIN users u ON u.id = a.user_id "
        "JOIN services s ON s.id = a.service_id "
        "WHERE a.id = ?"
    )
    row = con.execute(sql, (appointment_id,)).fetchone()
    if not row:
        return False, 'agendamento não encontrado'
    when = datetime.fromisoformat(row['start_at'])
    pretty_date = when.strftime('%d/%m/%Y')
    pretty_time = when.strftime('%H:%M')
    subject = f"Novo agendamento — {row['service_title']} · {pretty_date} às {pretty_time}"
    business = settings_dict(con).get('business_name','Samira Faria')
    text = (
        f"Olá, Samira!\n\n"
        f"Você recebeu um novo agendamento no site {business}.\n\n"
        f"Cliente: {row['client_name']}\n"
        f"E-mail: {row['client_email']}\n"
        f"Celular: {row['client_phone'] or 'não informado'}\n"
        f"Procedimento: {row['service_title']}\n"
        f"Data: {pretty_date}\n"
        f"Horário: {pretty_time}\n"
        f"Duração estimada: {row['service_duration']} min\n"
        f"Reserva: #{row['id']}\n\n"
        f"Observações da cliente:\n{row['notes'] or 'Nenhuma observação'}\n\n"
        "Acesse o painel administrativo para acompanhar os detalhes.\n"
    )
    notes_html = (row['notes'] or 'Nenhuma observação').replace('\n', '<br>')
    html = f"""<html><body style='font-family:Arial,sans-serif;color:#3b2d29'>
    <div style='max-width:620px;margin:auto;padding:24px;background:#fffaf8;border:1px solid #eaded7;border-radius:18px'>
    <h2 style='margin:0 0 16px;color:#8b5e4b'>Novo agendamento recebido ✨</h2>
    <p style='line-height:1.7'>Você recebeu um novo agendamento no site <strong>{business}</strong>.</p>
    <table style='width:100%;border-collapse:collapse;margin:18px 0'>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Cliente</strong></td><td>{row['client_name']}</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>E-mail</strong></td><td>{row['client_email']}</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Celular</strong></td><td>{row['client_phone'] or 'não informado'}</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Procedimento</strong></td><td>{row['service_title']}</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Data</strong></td><td>{pretty_date}</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Horário</strong></td><td>{pretty_time}</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Duração</strong></td><td>{row['service_duration']} min</td></tr>
      <tr><td style='padding:8px 0;color:#8b5e4b'><strong>Reserva</strong></td><td>#{row['id']}</td></tr>
    </table>
    <div style='background:#fff;border:1px solid #eaded7;border-radius:14px;padding:14px 16px'><strong>Observações da cliente</strong><br>{notes_html}</div>
    <p style='font-size:12px;color:#8a7a74;margin-top:20px'>Acompanhe e gerencie esse horário pelo painel administrativo.</p>
    </div></body></html>"""
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{cfg.get('smtp_from_name','Samira Faria')} <{from_email}>" if cfg.get('smtp_from_name') else from_email
    msg['To'] = to_email
    msg.set_content(text)
    msg.add_alternative(html, subtype='html')
    user = str(cfg.get('smtp_user','')).strip()
    password = str(cfg.get('smtp_password',''))
    security = str(cfg.get('smtp_security','tls')).strip().lower()
    if security == 'ssl':
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
            if user:
                server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if security == 'tls':
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
            if user:
                server.login(user, password)
            server.send_message(msg)
    return True, ''


def notify_booking_in_background(appointment_id):
    try:
        with db_conn() as con:
            ok, detail = send_booking_notification(con, appointment_id)
        if not ok and detail != 'configuração SMTP incompleta':
            print('Notificação e-mail não enviada:', detail, flush=True)
    except Exception as err:
        # Uma falha no provedor de e-mail jamais desfaz o agendamento.
        print('Notificação e-mail indisponível:', type(err).__name__, str(err), flush=True)


def service_dict(row):
    return {'id':row['id'],'title':row['title'],'category':row['category'], 'description':row['description'],
            'duration':row['duration'], 'price_cents':row['price_cents'], 'active':bool(row['active'])}


def valid_clock(value):
    try:
        return datetime.strptime(value,'%H:%M').strftime('%H:%M') == value
    except (TypeError, ValueError): return False


def slots_for(con, service_id, day):
    service = con.execute('SELECT * FROM services WHERE id=? AND active=1',(service_id,)).fetchone()
    if not service: return []
    try:
        requested = date.fromisoformat(day)
        if requested.isoformat() != day: return []
    except (TypeError, ValueError): return []
    today = now_local().date()
    if requested < today or requested > today + timedelta(days=BOOKING_DAYS): return []
    if con.execute('SELECT 1 FROM blackouts WHERE day=?',(day,)).fetchone(): return []
    hours = con.execute('SELECT * FROM weekly_hours WHERE weekday=?',(requested.weekday(),)).fetchone()
    if not hours or not hours['enabled']: return []
    start = datetime.fromisoformat(day+'T'+hours['open_time'])
    finish = datetime.fromisoformat(day+'T'+hours['close_time'])
    break_start = datetime.fromisoformat(day+'T'+hours['break_start']) if hours['break_start'] else None
    break_end = datetime.fromisoformat(day+'T'+hours['break_end']) if hours['break_end'] else None
    cutoff = now_local()+timedelta(hours=1)
    booked = con.execute("SELECT start_at,end_at FROM appointments WHERE status IN ('pending','confirmed','completed') AND start_at < ? AND end_at > ?",(finish.isoformat(timespec='minutes'),start.isoformat(timespec='minutes'))).fetchall()
    out=[]
    cursor=start
    delta=timedelta(minutes=service['duration'])
    while cursor+delta<=finish:
        end=cursor+delta
        overlaps_break=break_start and break_end and cursor < break_end and end > break_start
        overlaps_booking=any(cursor<datetime.fromisoformat(r['end_at']) and end>datetime.fromisoformat(r['start_at']) for r in booked)
        if cursor>=cutoff and not overlaps_break and not overlaps_booking:
            out.append(cursor.strftime('%H:%M'))
        cursor+=timedelta(minutes=30)
    return out


def appointments_query(con, clause='', params=()):
    sql='''SELECT a.*,u.name AS client_name,u.email AS client_email,u.phone AS client_phone,
                  s.title AS service_title,s.duration AS service_duration,s.price_cents AS service_price
           FROM appointments a JOIN users u ON u.id=a.user_id JOIN services s ON s.id=a.service_id '''
    return [dict(row) for row in con.execute(sql+clause, params)]


class Problem(Exception):
    def __init__(self, msg, status=400):
        self.msg,self.status=msg,status


class Handler(BaseHTTPRequestHandler):
    server_version='SamiraAgendamento/1.0'

    def log_message(self, fmt, *args):
        if not self.path.startswith('/api/slots'): super().log_message(fmt, *args)

    def respond(self, code, content, content_type='application/json; charset=utf-8', headers=None):
        data = json.dumps(content,ensure_ascii=False).encode('utf-8') if content_type.startswith('application/json') else content
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Cache-Control','no-store' if content_type.startswith('application/json') else 'public, max-age=86400')
        if headers:
            for k,v in headers.items(): self.send_header(k,v)
        self.end_headers()
        try: self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): pass

    def send_json(self, content, code=200, headers=None): self.respond(code,content,headers=headers)

    def get_session(self, con, create=False):
        try:
            cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
            raw=cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ''
        except Exception: raw=''
        row=con.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>=?',(hashlib.sha256(raw.encode()).hexdigest(),now_local().isoformat())).fetchone() if raw else None
        self.new_cookie=None
        if row or not create: return row
        raw=secrets.token_urlsafe(36)
        csrf=secrets.token_urlsafe(24)
        exp=(now_local()+timedelta(days=SESSION_DAYS)).isoformat()
        con.execute('INSERT INTO sessions(token_hash,csrf,expires_at) VALUES(?,?,?)',(hashlib.sha256(raw.encode()).hexdigest(),csrf,exp))
        self.new_cookie=f'{COOKIE_NAME}={raw}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS*86400}' + ('; Secure' if os.environ.get('COOKIE_SECURE')=='1' else '')
        return con.execute('SELECT * FROM sessions WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()

    def get_user(self, con, sess):
        return con.execute('SELECT * FROM users WHERE id=?',(sess['user_id'],)).fetchone() if sess and sess['user_id'] else None

    def require(self, user, role=None):
        if not user: raise Problem('Entre na sua conta para continuar.',401)
        if role and user['role']!=role: raise Problem('Acesso restrito à administração.',403)

    def read_json(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length>64_000: raise Problem('Dados muito grandes.',413)
            raw=self.rfile.read(length)
            data=json.loads(raw.decode('utf8')) if length else {}
            if not isinstance(data,dict): raise ValueError()
            return data
        except (ValueError, UnicodeError): raise Problem('Dados inválidos. Envie JSON válido.')

    def csrf_check(self, sess):
        if not sess or not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),sess['csrf']):
            raise Problem('Sessão expirada. Atualize a página e tente novamente.',403)
        origin=self.headers.get('Origin')
        if origin:
            host=self.headers.get('Host','')
            parsed=urllib.parse.urlparse(origin)
            if parsed.netloc!=host: raise Problem('Origem não permitida.',403)

    def do_GET(self): self.dispatch('GET')
    def do_POST(self): self.dispatch('POST')
    def do_PUT(self): self.dispatch('PUT')
    def do_DELETE(self): self.dispatch('DELETE')

    def dispatch(self, method):
        try:
            url=urllib.parse.urlsplit(self.path)
            path=url.path
            if path.startswith('/static/') and method=='GET':
                target=(ROOT/path.lstrip('/')).resolve()
                if not target.is_relative_to(STATIC.resolve()) or not target.is_file(): raise Problem('Arquivo não encontrado.',404)
                mime = ({'.webp':'image/webp','.svg':'image/svg+xml','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.png':'image/png','.webmanifest':'application/manifest+json','.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8'}.get(target.suffix,'application/octet-stream'))
                return self.respond(200,target.read_bytes(),mime)
            if not path.startswith('/api/'):
                if method!='GET': raise Problem('Rota não encontrada.',404)
                return self.respond(200,(STATIC/'index.html').read_bytes(),'text/html; charset=utf-8',headers={'Cache-Control':'no-cache'})
            with db_conn() as con:
                sess=self.get_session(con,create=path=='/api/bootstrap')
                user=self.get_user(con,sess)
                if method!='GET':self.csrf_check(sess)
                data=self.read_json() if method!='GET' else {}
                out=self.api(con,method,path,urllib.parse.parse_qs(url.query),data,user,sess)
                headers={'Set-Cookie':self.new_cookie} if self.new_cookie else None
                con.commit()  # Garantir reserva salva antes de notificações.
                if method=='POST' and path=='/api/appointments' and out.get('appointment_id'):
                    threading.Thread(target=notify_booking_in_background,args=(out['appointment_id'],),daemon=True).start()
                self.send_json(out,headers=headers)
        except Problem as ex:
            self.send_json({'error':ex.msg},ex.status)
        except sqlite3.IntegrityError:
            self.send_json({'error':'Não foi possível concluir a operação. Verifique os dados.'},409)
        except Exception:
            traceback.print_exc()
            self.send_json({'error':'Ocorreu um erro inesperado. Tente novamente.'},500)

    def api(self,con,method,path,query,data,user,sess):
        if method=='GET' and path=='/api/bootstrap':
            return {'user':clean_user(user),'csrf':sess['csrf'],'settings':settings_dict(con),'today':now_local().date().isoformat(),
                    'services':[service_dict(r) for r in con.execute('SELECT * FROM services WHERE active=1 ORDER BY sort_order,id')],
                    'booking_days':BOOKING_DAYS}
        if method=='GET' and path=='/api/slots':
            try: sid=int(query.get('service_id',[0])[0])
            except ValueError:sid=0
            day=query.get('date',[''])[0]
            return {'slots':slots_for(con,sid,day),'date':day,'service_id':sid}
        if method=='POST' and path=='/api/register':
            name=str(data.get('name','')).strip()[:90]; email=str(data.get('email','')).strip().lower()[:160]
            phone=''.join(c for c in str(data.get('phone','')) if c.isdigit() or c=='+')[:20]
            password=str(data.get('password',''))
            if len(name)<3 or '@' not in email or '.' not in email.split('@')[-1] or len(password)<8:
                raise Problem('Informe nome, e-mail válido e senha com pelo menos 8 caracteres.')
            if con.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone(): raise Problem('Este e-mail já está cadastrado.',409)
            cur=con.execute('INSERT INTO users(name,email,phone,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                            (name,email,phone,pass_hash(password),'client',now_local().isoformat()))
            con.execute('UPDATE sessions SET user_id=? WHERE token_hash=?',(cur.lastrowid,sess['token_hash']))
            return {'ok':True,'user':clean_user(con.execute('SELECT * FROM users WHERE id=?',(cur.lastrowid,)).fetchone())}
        if method=='POST' and path=='/api/login':
            email=str(data.get('email','')).strip().lower(); password=str(data.get('password',''))
            target=con.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not target or not pass_check(password,target['password_hash']): raise Problem('E-mail ou senha inválidos.',401)
            con.execute('UPDATE sessions SET user_id=? WHERE token_hash=?',(target['id'],sess['token_hash']))
            return {'ok':True,'user':clean_user(target)}
        if method=='POST' and path=='/api/logout':
            con.execute('UPDATE sessions SET user_id=NULL WHERE token_hash=?',(sess['token_hash'],))
            return {'ok':True}
        if method=='GET' and path=='/api/my-appointments':
            self.require(user)
            return {'appointments':appointments_query(con,'WHERE a.user_id=? ORDER BY a.start_at DESC',(user['id'],))}
        if method=='POST' and path=='/api/appointments':
            self.require(user)
            try: sid=int(data.get('service_id',0))
            except (ValueError,TypeError):sid=0
            day=str(data.get('date','')); time=str(data.get('time',''))
            notes=str(data.get('notes','')).strip()[:500]
            if not valid_clock(time): raise Problem('Horário inválido.')
            con.execute('BEGIN IMMEDIATE')
            if time not in slots_for(con,sid,day):raise Problem('Este horário acabou de ficar indisponível. Selecione outro.',409)
            service=con.execute('SELECT duration FROM services WHERE id=?',(sid,)).fetchone()
            start=datetime.fromisoformat(day+'T'+time)
            end=start+timedelta(minutes=service['duration'])
            cur=con.execute('INSERT INTO appointments(user_id,service_id,start_at,end_at,status,notes,created_at) VALUES(?,?,?,?,?,?,?)',
                  (user['id'],sid,start.isoformat(timespec='minutes'),end.isoformat(timespec='minutes'),'confirmed',notes,now_local().isoformat(timespec='seconds')))
            return {'ok':True,'appointment_id':cur.lastrowid}
        if method=='POST' and path.startswith('/api/my-appointments/') and path.endswith('/cancel'):
            self.require(user)
            try: aid=int(path.split('/')[3])
            except (ValueError,IndexError):raise Problem('Agendamento inválido.')
            item=con.execute('SELECT * FROM appointments WHERE id=? AND user_id=?',(aid,user['id'])).fetchone()
            if not item:raise Problem('Agendamento não encontrado.',404)
            if item['status'] not in ('confirmed','pending'):raise Problem('Este agendamento não pode ser cancelado.')
            if datetime.fromisoformat(item['start_at'])<=now_local():raise Problem('Entre em contato para cancelar um horário que já começou.')
            con.execute("UPDATE appointments SET status='cancelled' WHERE id=?",(aid,))
            return {'ok':True}
        # Admin endpoints
        if path.startswith('/api/admin/'):
            self.require(user,'admin')
            if method=='GET' and path=='/api/admin/overview':
                today=now_local().date().isoformat()
                upcoming=appointments_query(con,"WHERE a.start_at>=? AND a.status IN ('pending','confirmed') ORDER BY a.start_at ASC LIMIT 7",(today,))
                counts={'clients':con.execute("SELECT COUNT(*) FROM users WHERE role='client'").fetchone()[0],
                        'scheduled':con.execute("SELECT COUNT(*) FROM appointments WHERE status IN ('confirmed','pending') AND start_at>=?",(today,)).fetchone()[0],
                        'today':con.execute("SELECT COUNT(*) FROM appointments WHERE status IN ('confirmed','pending') AND substr(start_at,1,10)=?",(today,)).fetchone()[0],
                        'completed':con.execute("SELECT COUNT(*) FROM appointments WHERE status='completed'").fetchone()[0]}
                return {'counts':counts,'upcoming':upcoming}
            if method=='GET' and path=='/api/admin/appointments':
                status=query.get('status',['all'])[0]; day=query.get('date',[''])[0]
                where=[]; params=[]
                if status!='all':where.append('a.status=?');params.append(status)
                if day:where.append('substr(a.start_at,1,10)=?');params.append(day)
                cond=('WHERE '+' AND '.join(where)) if where else ''
                return {'appointments':appointments_query(con,cond+' ORDER BY a.start_at DESC LIMIT 400',tuple(params))}
            if method=='PUT' and path.startswith('/api/admin/appointments/'):
                try:aid=int(path.split('/')[-1])
                except ValueError:raise Problem('ID inválido.')
                status=str(data.get('status',''))
                if status not in ('confirmed','completed','cancelled','pending'):raise Problem('Situação inválida.')
                con.execute('BEGIN IMMEDIATE')
                current=con.execute('SELECT * FROM appointments WHERE id=?',(aid,)).fetchone()
                if not current:raise Problem('Agendamento não encontrado.',404)
                if status in ('confirmed','pending','completed'):
                    overlap=con.execute("SELECT 1 FROM appointments WHERE id<>? AND status IN ('confirmed','pending','completed') AND start_at<? AND end_at>? LIMIT 1",
                                        (aid,current['end_at'],current['start_at'])).fetchone()
                    if overlap:raise Problem('Não é possível reativar esta reserva: o horário já está ocupado.',409)
                con.execute('UPDATE appointments SET status=? WHERE id=?',(status,aid))
                return {'ok':True}
            if method=='GET' and path=='/api/admin/services':
                return {'services':[service_dict(r) for r in con.execute('SELECT * FROM services ORDER BY sort_order,id')]}
            if method in ('POST','PUT') and (path=='/api/admin/services' or path.startswith('/api/admin/services/')):
                title=str(data.get('title','')).strip()[:100]; category=str(data.get('category','')).strip()[:50]
                desc=str(data.get('description','')).strip()[:400]
                try:
                    duration=int(data.get('duration',0));order=int(data.get('sort_order',0))
                    price_raw=data.get('price_cents')
                    price=None if price_raw is None or price_raw=='' else int(price_raw)
                except (TypeError,ValueError):raise Problem('Duração ou preço inválido.')
                active=int(bool(data.get('active',True)))
                if not title or not category or duration<15 or duration>480 or duration%15!=0 or (price is not None and (price<0 or price>100_000_000)):
                    raise Problem('Confira os campos. Duração entre 15 e 480 minutos, em passos de 15.')
                if method=='POST':
                    con.execute('INSERT INTO services(title,category,description,duration,price_cents,active,sort_order) VALUES(?,?,?,?,?,?,?)',
                                (title,category,desc,duration,price,active,order))
                else:
                    try:sid=int(path.split('/')[-1])
                    except ValueError:raise Problem('ID inválido.')
                    if not con.execute('SELECT 1 FROM services WHERE id=?',(sid,)).fetchone():raise Problem('Serviço não encontrado.',404)
                    con.execute('UPDATE services SET title=?,category=?,description=?,duration=?,price_cents=?,active=?,sort_order=? WHERE id=?',
                                (title,category,desc,duration,price,active,order,sid))
                return {'ok':True}
            if method=='GET' and path=='/api/admin/hours':
                return {'hours':[dict(r) for r in con.execute('SELECT * FROM weekly_hours ORDER BY weekday')]}
            if method=='PUT' and path=='/api/admin/hours':
                hours=data.get('hours')
                if not isinstance(hours,list) or len(hours)!=7:raise Problem('Envie os sete dias da semana.')
                for dayrow in hours:
                    i=int(dayrow.get('weekday',-1)); enabled=int(bool(dayrow.get('enabled',False)))
                    start=str(dayrow.get('open_time',''));end=str(dayrow.get('close_time',''))
                    bstart=str(dayrow.get('break_start',''));bend=str(dayrow.get('break_end',''))
                    if i not in range(7) or not valid_clock(start) or not valid_clock(end) or start>=end or ((bstart or bend) and (not valid_clock(bstart) or not valid_clock(bend) or not(start<=bstart<bend<=end))):
                        raise Problem('Confira os horários e o intervalo de cada dia.')
                    con.execute('UPDATE weekly_hours SET enabled=?,open_time=?,close_time=?,break_start=?,break_end=? WHERE weekday=?',(enabled,start,end,bstart,bend,i))
                return {'ok':True}
            if method=='GET' and path=='/api/admin/blackouts':
                return {'blackouts':[dict(r) for r in con.execute('SELECT * FROM blackouts ORDER BY day DESC')]}
            if method=='POST' and path=='/api/admin/blackouts':
                day=str(data.get('day',''));reason=str(data.get('reason','')).strip()[:130]
                try:
                    if date.fromisoformat(day).isoformat()!=day:raise ValueError()
                except ValueError:raise Problem('Data inválida.')
                con.execute('INSERT OR REPLACE INTO blackouts(day,reason) VALUES(?,?)',(day,reason))
                return {'ok':True}
            if method=='DELETE' and path.startswith('/api/admin/blackouts/'):
                try:bid=int(path.split('/')[-1])
                except ValueError:raise Problem('ID inválido.')
                con.execute('DELETE FROM blackouts WHERE id=?',(bid,))
                return {'ok':True}
            if method=='PUT' and path=='/api/admin/settings':
                allowed=['business_name','tagline','subtitle','instagram','whatsapp','booking_redirect','location','address','booking_notice']
                for key in allowed:
                    if key in data:
                        value=str(data[key]).strip()[:400]
                        if key=='booking_redirect' and value not in ('whatsapp','client','confirmation'):
                            raise Problem('Modo de redirecionamento inválido.')
                        con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,value))
                return {'ok':True,'settings':settings_dict(con)}
            if method=='GET' and path=='/api/admin/notifications':
                return {'settings': notification_settings_dict(con)}
            if method=='PUT' and path=='/api/admin/notifications':
                allowed=['notification_email','notify_new_booking','smtp_host','smtp_port','smtp_security','smtp_user','smtp_password','smtp_from','smtp_from_name']
                for key in allowed:
                    if key in data:
                        value=str(data[key]).strip()[:500]
                        if key=='smtp_security' and value not in ('tls','ssl','none'):
                            raise Problem('Tipo de segurança SMTP inválida.')
                        if key=='smtp_port' and value and (not value.isdigit() or not 1 <= int(value) <= 65535):
                            raise Problem('Porta SMTP inválida.')
                        if key=='notify_new_booking':
                            value = '1' if str(data[key]).strip() in ('1','true','True','on','sim','yes') else '0'
                        con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,value))
                return {'ok':True,'settings':notification_settings_dict(con)}
            if method=='PUT' and path=='/api/admin/account':
                old=str(data.get('old_password',''));new=str(data.get('new_password',''))
                if not pass_check(old,user['password_hash']):raise Problem('Senha atual incorreta.')
                if len(new)<10:raise Problem('A nova senha precisa ter pelo menos 10 caracteres.')
                con.execute('UPDATE users SET password_hash=? WHERE id=?',(pass_hash(new),user['id']))
                return {'ok':True}
        raise Problem('Endpoint não encontrado.',404)


if __name__=='__main__':
    initialize()
    server=ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),PORT), Handler)
    print(f'Samira Faria — site pronto em http://127.0.0.1:{PORT}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nEncerrando...')
    finally:server.server_close()
