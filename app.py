import os
import uuid
import json
import base64
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3

# Carrega .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Supabase
try:
    from supabase import create_client, Client as SupabaseClient
except ImportError:
    create_client = None
    SupabaseClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pré-carrega o CNAE do IBGE na startup para evitar lentidão na 1ª busca
    await _get_cnae_data()
    yield

app = FastAPI(lifespan=lifespan)

# Configurações
DATABASE         = "database.sqlite"
SUPABASE_BUCKET  = "documentos"

# Supabase client
_supa_url = os.getenv("SUPABASE_URL", "")
_supa_key = os.getenv("SUPABASE_SERVICE_KEY", "")
supabase: "SupabaseClient | None" = (
    create_client(_supa_url, _supa_key)
    if (create_client and _supa_url and _supa_key)
    else None
)
if supabase:
    print("[SUPABASE] Cliente inicializado com sucesso.")
else:
    print("[SUPABASE] SUPABASE_URL / SUPABASE_SERVICE_KEY não configurados — uploads desativados.")

# Brevo API (envia via HTTP em vez de SMTP)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
EMAIL_FROM    = os.getenv("EMAIL_FROM", "")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Mendonça Galvão")
EMAIL_TO      = os.getenv("EMAIL_TO", "nucleodigitalmendoncagalvao@gmail.com")
print(f"[EMAIL] FROM={EMAIL_FROM} | TO={EMAIL_TO} | BREVO_API={'SET' if BREVO_API_KEY else 'NÃO CONFIGURADO'}")

# Templates e Arquivos Estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── CNAE cache ────────────────────────────────────────────────────────────────
import unicodedata, httpx

_cnae_cache: list[dict] | None = None

async def _get_cnae_data() -> list[dict]:
    global _cnae_cache
    if _cnae_cache is not None:
        return _cnae_cache
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://servicodados.ibge.gov.br/api/v2/cnae/subclasses"
            )
        _cnae_cache = r.json()
        print(f"[CNAE] {len(_cnae_cache)} subclasses carregadas do IBGE.")
    except Exception as e:
        print(f"[CNAE] Erro ao carregar: {e}")
        _cnae_cache = []
    return _cnae_cache

def _normalize(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


@app.get("/api/cnae")
async def cnae_search(q: str = ""):
    q = q.strip()
    if len(q) < 2:
        return JSONResponse([])
    data = await _get_cnae_data()
    norm_q = _normalize(q)
    results = [
        {"id": item["id"], "descricao": item["descricao"]}
        for item in data
        if norm_q in _normalize(item["descricao"]) or q in item["id"]
    ][:15]
    return JSONResponse(results)

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wizard_submissions (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS submission_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id TEXT,
        file_label TEXT,
        file_path TEXT,
        FOREIGN KEY(submission_id) REFERENCES wizard_submissions(id)
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ── E-MAIL ────────────────────────────────────────────────────────────────────
FIELD_LABELS = {
    "razao_social_1":        "Razão Social — Opção 1 (Preferencial)",
    "razao_social_2":        "Razão Social — Opção 2",
    "razao_social_3":        "Razão Social — Opção 3",
    "nome_fantasia":         "Nome Fantasia",
    "cep":                   "CEP",
    "rua":                   "Rua / Logradouro",
    "numero":                "Número",
    "complemento":           "Complemento",
    "bairro":                "Bairro",
    "cidade":                "Cidade",
    "uf":                    "UF",
    "inscricao_imobiliaria": "Inscrição Imobiliária",
    "area_m2":               "Área (m²)",
    "tipo_imovel":           "Tipo de Imóvel",
    "cnae_codigo":           "CNAE — Código",
    "cnae_descricao":        "CNAE — Descrição",
    "ramo_descricao":        "Ramo de Atuação (Manual)",
    "valor_capital":         "Capital Social (R$)",
    "tipo_integralizacao":   "Tipo de Integralização",
    "data_limite":           "Data Limite para Integralização",
    "meio_integralizacao":   "Meio de Integralização",
    "email":                 "E-mail Corporativo",
    "telefone":              "Telefone / WhatsApp",
}

EMAIL_SECTIONS = [
    ("📋 Razão Social", [
        ("razao_social_1", "Opção 1 — Preferencial"),
        ("razao_social_2", "Opção 2"),
        ("razao_social_3", "Opção 3"),
        ("nome_fantasia",  "Nome Fantasia"),
    ]),
    ("📍 Endereço", [
        ("cep",     "CEP"),
        ("rua",     "Logradouro"),
        ("numero",  "Número"),
        ("complemento", "Complemento"),
        ("bairro",  "Bairro"),
        ("cidade",  "Cidade"),
        ("uf",      "UF"),
    ]),
    ("🏢 Imóvel", [
        ("inscricao_imobiliaria", "Inscrição Imobiliária"),
        ("area_m2",    "Área (m²)"),
        ("tipo_imovel", "Tipo"),
    ]),
    ("🔍 Atividade Econômica (CNAE)", [
        ("cnae_codigo",    "Código CNAE"),
        ("cnae_descricao", "Descrição"),
        ("ramo_descricao", "Ramo (manual)"),
    ]),
    ("💰 Capital Social", [
        ("valor_capital",        "Valor (R$)"),
        ("tipo_integralizacao",  "Integralização"),
        ("data_limite",          "Data Limite"),
        ("meio_integralizacao",  "Meio"),
    ]),
    ("📬 Contato", [
        ("email",    "E-mail"),
        ("telefone", "Telefone / WhatsApp"),
    ]),
]

def _section_block(title: str, rows_html: str) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0"
           style="margin-bottom:20px;border-radius:10px;overflow:hidden;
                  border:1px solid #25282f;border-left:3px solid #b9985a">
      <tr>
        <td colspan="2"
            style="padding:9px 16px;background:#1a1c21;
                   font-size:11px;font-weight:700;letter-spacing:1.2px;
                   text-transform:uppercase;color:#b9985a;
                   border-bottom:1px solid #25282f">
          {title}
        </td>
      </tr>
      {rows_html}
    </table>"""

def _row(label: str, value: str, shade: bool) -> str:
    bg = "#141619" if shade else "#111316"
    return f"""
      <tr>
        <td style="padding:9px 16px;width:190px;font-size:12px;
                   color:#8a9ab0;background:{bg};
                   border-bottom:1px solid #1e2126;
                   white-space:nowrap;vertical-align:top">{label}</td>
        <td style="padding:9px 16px;font-size:13px;
                   color:#dde1e7;background:{bg};
                   border-bottom:1px solid #1e2126">{value}</td>
      </tr>"""

def build_email_html(data: dict, file_names: list, submission_id: str) -> str:
    sections_html = ""
    for title, fields in EMAIL_SECTIONS:
        rows_html = ""
        shade = False
        for key, label in fields:
            value = data.get(key, "").strip()
            if not value:
                continue
            rows_html += _row(label, value, shade)
            shade = not shade
        if rows_html:
            sections_html += _section_block(title, rows_html)

    # Documentos
    if file_names:
        files_rows = ""
        for i, fn in enumerate(file_names):
            files_rows += _row("📎 Arquivo", fn, i % 2 == 0)
        sections_html += _section_block("📄 Documentos Anexados", files_rows)

    now    = datetime.now().strftime("%d/%m/%Y às %H:%M")
    sid    = submission_id[:8].upper()

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Nova Solicitação — Mendonça Galvão</title>
</head>
<body style="margin:0;padding:20px 0;background:#0b0d10;
             font-family:'Segoe UI',Arial,sans-serif">

  <!--  OUTER WRAPPER  -->
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="border-radius:16px;overflow:hidden;
                    border:1px solid #22252c;
                    box-shadow:0 20px 60px rgba(0,0,0,0.7)">

        <!--  HEADER  -->
        <tr>
          <td style="background:linear-gradient(150deg,#1c1f26 0%,#12141a 100%);
                     padding:36px 36px 28px;text-align:center;
                     border-bottom:2px solid #b9985a">
            <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;
                        color:#6b7888;margin-bottom:12px">Mendonça Galvão</div>
            <div style="font-size:24px;font-weight:300;color:#d4b483;letter-spacing:0.5px;
                        margin-bottom:6px">Nova Solicitação</div>
            <div style="font-size:13px;color:#8a9ab0;letter-spacing:1px">
              Abertura de Empresa
            </div>
            <div style="margin-top:20px">
              <span style="display:inline-block;background:rgba(185,152,90,0.12);
                           border:1px solid rgba(185,152,90,0.3);
                           border-radius:20px;padding:5px 16px;
                           font-family:monospace;font-size:13px;color:#c9a85c;
                           letter-spacing:1px">
                ID #{sid}
              </span>
            </div>
          </td>
        </tr>

        <!--  META BAR  -->
        <tr>
          <td style="background:#0f1115;padding:12px 36px;
                     border-bottom:1px solid #1c1f26">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:12px;color:#4a5568">
                  ⏱ Recebida em <strong style="color:#6b7888">{now}</strong>
                </td>
                <td align="right" style="font-size:12px;color:#4a5568">
                  Solicitação de abertura de empresa
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!--  BODY  -->
        <tr>
          <td style="padding:28px 36px;background:#111316">
            {sections_html}
          </td>
        </tr>

        <!--  FOOTER  -->
        <tr>
          <td style="background:#0b0d10;padding:20px 36px;
                     border-top:1px solid #1a1c21;text-align:center">
            <div style="font-size:11px;color:#2e3340;margin-bottom:4px">
              Este e-mail foi gerado automaticamente pelo sistema de abertura de empresas
            </div>
            <div style="font-size:12px;color:#3a4050">
              Mendonça Galvão Contadores Associados &nbsp;·&nbsp; Núcleo Digital
            </div>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>"""


def _brevo_send(to_email: str, subject: str, html: str,
                attachments: list | None = None):
    """Envia e-mail via Brevo API REST (sem SMTP)."""
    payload: dict = {
        "sender": {"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
    }
    if attachments:
        payload["attachment"] = [
            {"name": name, "content": base64.b64encode(content).decode()}
            for name, content in attachments
        ]
    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": BREVO_API_KEY},
        )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Brevo API {r.status_code}: {r.text}")
    return r.json()


def send_email(data: dict, file_names: list, submission_id: str,
               attachments: list | None = None):
    """Envia e-mail de solicitação para o escritório via Brevo API."""
    if not BREVO_API_KEY:
        print(f"[EMAIL] BREVO_API_KEY não configurado. Submission ID: {submission_id}")
        return
    subject = f"[Abertura de Empresa] Nova Solicitação — ID {submission_id[:8].upper()}"
    html    = build_email_html(data, file_names, submission_id)
    try:
        _brevo_send(EMAIL_TO, subject, html, attachments)
        print(f"[EMAIL] Enviado via Brevo API para {EMAIL_TO} — ID {submission_id}")
    except Exception as e:
        import traceback
        print(f"[EMAIL] ERRO ao enviar: {e}")
        traceback.print_exc()


def build_confirmation_html(data: dict, file_names: list, submission_id: str) -> str:
    """Confirmation e-mail sent to the *client* who submitted the form."""
    razao = data.get("razao_social_1") or data.get("nome_fantasia") or "sua empresa"
    sid   = submission_id[:8].upper()
    now   = datetime.now().strftime("%d/%m/%Y às %H:%M")

    # Build data summary rows (light theme)
    rows = ""
    for key, label in FIELD_LABELS.items():
        value = data.get(key, "").strip()
        if not value:
            continue
        bg = "#f9f6f1" if len(rows) % 2 == 0 else "#ffffff"
        rows += f"""
          <tr>
            <td style="padding:9px 16px;width:190px;font-size:12px;color:#7a6a50;
                       background:{bg};border-bottom:1px solid #ede8df;
                       white-space:nowrap;vertical-align:top">{label}</td>
            <td style="padding:9px 16px;font-size:13px;color:#2d2416;
                       background:{bg};border-bottom:1px solid #ede8df">{value}</td>
          </tr>"""

    files_list = "".join(
        f"<li style='margin:4px 0;color:#5a4a30'>&#128206; {fn}</li>"
        for fn in file_names
    )
    files_section = ""
    if files_list:
        files_section = f"""
        <div style="margin-top:24px;padding:16px 20px;
                    background:#fffbf4;border-radius:8px;
                    border:1px solid #e8dfc8">
          <div style="font-size:11px;font-weight:700;letter-spacing:1px;
                      text-transform:uppercase;color:#b9985a;margin-bottom:10px">
            Documentos Recebidos
          </div>
          <ul style="margin:0;padding-left:18px;font-size:13px">{files_list}</ul>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Confirmação de Solicitação — Mendonça Galvão</title>
</head>
<body style="margin:0;padding:24px 0;background:#f4f0e8;
             font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="border-radius:14px;overflow:hidden;
                    box-shadow:0 8px 32px rgba(0,0,0,0.08);
                    border:1px solid #e0d8c8">

        <!-- HEADER -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a1d22 0%,#2a2419 100%);
                     padding:36px 36px 28px;text-align:center;
                     border-bottom:3px solid #b9985a">
            <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;
                        color:#8a7a5a;margin-bottom:10px">Mendonça Galvão</div>
            <div style="font-size:22px;font-weight:300;color:#d4b483;">
              Solicitação Recebida
            </div>
            <div style="margin-top:16px">
              <span style="display:inline-block;background:rgba(185,152,90,0.15);
                           border:1px solid rgba(185,152,90,0.4);
                           border-radius:20px;padding:5px 18px;
                           font-family:monospace;font-size:12px;
                           color:#d4b483;letter-spacing:1px">
                Protocolo #{sid}
              </span>
            </div>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="padding:32px 36px;background:#ffffff">
            <p style="margin:0 0 16px;font-size:15px;color:#2d2416;line-height:1.6">
              Olá! Sua solicitação de abertura de empresa para
              <strong>{razao}</strong> foi recebida com sucesso em
              <strong>{now}</strong>.
            </p>
            <p style="margin:0 0 24px;font-size:14px;color:#5a4a30;line-height:1.6">
              A equipe do <strong>Setor Socieário</strong> da Mendonça Galvão
              Contadores Associados fará uma análise dos seus documentos e
              <strong>entrará em contato em breve</strong> para dar continuidade
              ao processo.
            </p>

            <!-- DATA TABLE -->
            <div style="font-size:11px;font-weight:700;letter-spacing:1px;
                        text-transform:uppercase;color:#b9985a;margin-bottom:10px">
              Dados Enviados
            </div>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-radius:8px;overflow:hidden;
                          border:1px solid #e0d8c8">
              {rows}
            </table>

            {files_section}

            <p style="margin:28px 0 0;font-size:12px;color:#8a7a5a;line-height:1.6">
              Se tiver dúvidas, entre em contato com nossa equipe respondendo
              este e-mail ou pelo WhatsApp.
            </p>
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#f9f6f1;padding:20px 36px;
                     border-top:1px solid #e0d8c8;text-align:center">
            <div style="font-size:12px;color:#a09070">
              Mendonça Galvão Contadores Associados
              &nbsp;&middot;&nbsp; Setor Socieário
            </div>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_confirmation_email(data: dict, file_names: list,
                            submission_id: str):
    """Envia e-mail de confirmação para o cliente via Brevo API."""
    client_email = data.get("email", "").strip()
    if not client_email:
        print("[CONFIRM] Campo 'email' não preenchido — confirmação não enviada.")
        return
    if not BREVO_API_KEY:
        return
    razao   = data.get("razao_social_1") or data.get("nome_fantasia") or "Nova Empresa"
    subject = f"Recebemos sua solicitação — {razao}"
    html    = build_confirmation_html(data, file_names, submission_id)
    try:
        _brevo_send(client_email, subject, html)
        print(f"[CONFIRM] E-mail de confirmação enviado para {client_email}")
    except Exception as e:
        import traceback
        print(f"[CONFIRM] ERRO ao enviar: {e}")
        traceback.print_exc()


# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/img/favicon.png")


@app.get("/", response_class=HTMLResponse)
async def get_wizard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/submit")
async def submit_form(request: Request, background_tasks: BackgroundTasks):
    form_data  = await request.form()
    plain_data = {
        key: form_data[key]
        for key in form_data.keys()
        if not hasattr(form_data[key], "filename")
    }

    submission_id = str(uuid.uuid4())
    conn          = get_db()
    cursor        = conn.cursor()
    file_names   = []
    attachments  = []  # list of (filename, bytes) for email

    try:
        cursor.execute(
            "INSERT INTO wizard_submissions (id, data_json) VALUES (?, ?)",
            (submission_id, json.dumps(plain_data))
        )

        for key in form_data.keys():
            field = form_data[key]
            if hasattr(field, "filename") and field.filename:
                file_bytes = await field.read()
                file_ext   = os.path.splitext(field.filename)[1].lower()
                safe_name  = f"{uuid.uuid4()}{file_ext}"
                storage_path = f"{submission_id}/{safe_name}"
                public_url   = ""

                if supabase:
                    try:
                        # Ensure bucket exists (idempotent)
                        try:
                            supabase.storage.create_bucket(
                                SUPABASE_BUCKET,
                                options={"public": True}
                            )
                        except Exception:
                            pass  # bucket already exists

                        content_type = {
                            ".pdf":  "application/pdf",
                            ".png":  "image/png",
                            ".jpg":  "image/jpeg",
                            ".jpeg": "image/jpeg",
                            ".webp": "image/webp",
                        }.get(file_ext, "application/octet-stream")

                        supabase.storage.from_(SUPABASE_BUCKET).upload(
                            path=storage_path,
                            file=file_bytes,
                            file_options={"content-type": content_type},
                        )
                        public_url = (
                            f"{_supa_url}/storage/v1/object/public/"
                            f"{SUPABASE_BUCKET}/{storage_path}"
                        )
                        print(f"[SUPABASE] Upload OK: {public_url}")
                    except Exception as sup_err:
                        print(f"[SUPABASE] Erro no upload: {sup_err}")

                cursor.execute(
                    "INSERT INTO submission_files (submission_id, file_label, file_path) VALUES (?, ?, ?)",
                    (submission_id, field.filename, public_url or storage_path)
                )
                file_names.append(field.filename)
                attachments.append((field.filename, file_bytes))

        conn.commit()

        # Envia emails em background — não bloqueia a resposta ao usuário
        background_tasks.add_task(
            send_email, plain_data, file_names, submission_id,
            attachments=attachments
        )
        background_tasks.add_task(
            send_confirmation_email, plain_data, file_names, submission_id
        )

        return JSONResponse({"status": "success", "id": submission_id})

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
