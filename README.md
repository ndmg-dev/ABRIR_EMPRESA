# Formulário de Abertura de Empresa — Mendonca Galvao

Sistema web para coleta estruturada de dados e documentos necessarios ao processo de abertura de empresa, desenvolvido para uso interno da Mendonca Galvao Contadores Associados.

---

## Visao Geral

A aplicacao apresenta um formulario em etapas (wizard) que guia o cliente pelo preenchimento das informacoes societarias, fiscais, patrimoniais e de contato. Ao final, os documentos sao enviados ao Supabase e as notificacoes de email sao disparadas automaticamente via API do Brevo.

---

## Tecnologias

| Camada        | Tecnologia                        |
| ------------- | --------------------------------- |
| Backend       | Python 3.13 + FastAPI + Uvicorn   |
| Frontend      | HTML5, CSS3, JavaScript (vanilla) |
| Banco Local   | SQLite                            |
| Armazenamento | Supabase Storage                  |
| Email         | Brevo Transactional API           |
| Deploy        | Railway                           |

---

## Estrutura do Projeto

```
.
├── app.py                  # Aplicacao principal (FastAPI)
├── Procfile                # Comando de inicializacao para Railway
├── requirements.txt        # Dependencias Python
├── .env                    # Variaveis de ambiente (nao versionado)
├── static/
│   ├── css/style.css       # Estilos da interface
│   ├── js/script.js        # Logica do wizard (navegacao, validacao, preview)
│   └── img/                # Imagens e favicon
└── templates/
    └── index.html          # Template principal do wizard
```

---

## Configuracao Local

### Pre-requisitos

- Python 3.11 ou superior
- Pip

### Instalacao

```bash
# Clonar o repositorio
git clone https://github.com/ndmg-dev/ABRIR_EMPRESA.git
cd ABRIR_EMPRESA

# Criar e ativar ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / macOS

# Instalar dependencias
pip install -r requirements.txt
```

### Variaveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variaveis:

```env
# Brevo (envio de email via API REST)
BREVO_API_KEY=sua-chave-da-api-brevo
EMAIL_FROM=remetente@dominio.com.br
EMAIL_FROM_NAME=Mendonca Galvao
EMAIL_TO=destinatario@dominio.com.br

# Supabase (armazenamento de documentos)
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
```

### Execucao

```bash
python app.py
```

A aplicacao estara disponivel em `http://localhost:8000`.

---

## Deploy (Railway)

O projeto esta configurado para deploy automatico via Railway conectado ao repositorio GitHub.

A cada `git push` na branch `main`, o Railway detecta a mudanca e realiza um novo deploy utilizando o comando definido no `Procfile`:

```
web: uvicorn app:app --host 0.0.0.0 --port $PORT
```

### Variaveis de Ambiente no Railway

Configure as mesmas variaveis do `.env` no painel do Railway em **Variables**.

### DNS (Hostgator)

Para o dominio personalizado `formulario.mendoncagalvao.com.br`, os seguintes registros DNS devem estar configurados:

| Tipo  | Nome                       | Valor                 |
| ----- | -------------------------- | --------------------- |
| CNAME | formulario                 | [gerado pelo Railway] |
| TXT   | _railway-verify.formulario | [gerado pelo Railway] |

---

## Funcionalidades

- Wizard multi-etapas com validacao por passo
- Busca de endereco por CEP via API ViaCEP
- Busca de atividade economica (CNAE) via API IBGE com cache em memoria
- Upload de documentos (identidade, comprovante de residencia, certidao de casamento)
- Armazenamento de arquivos no Supabase Storage
- Registro da submissao em banco SQLite
- Envio de email interno com dados e anexos via Brevo API
- Envio de email de confirmacao para o cliente
- Preview dos dados antes do envio final

---

## Licenca

Uso interno — Mendonca Galvao Contadores Associados. Todos os direitos reservados.
