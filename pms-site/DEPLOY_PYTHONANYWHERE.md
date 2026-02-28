# Deploy no PythonAnywhere (Flask)

## 1) Enviar o projeto

Opcao A: subir para GitHub e clonar no PythonAnywhere.

Opcao B: upload zip pelo painel Files e extrair em:

`/home/SEU_USUARIO/teste-codex/`

## 2) Criar virtualenv e instalar dependencias

No Bash Console do PythonAnywhere:

```bash
cd /home/SEU_USUARIO/teste-codex
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Criar Web App (manual config)

- Dashboard -> Web -> Add a new web app
- Escolha `Manual configuration`
- Escolha `Python 3.10`

## 4) Configurar WSGI

No arquivo WSGI (exemplo):

`/var/www/SEU_USUARIO_pythonanywhere_com_wsgi.py`

Use este conteudo:

```python
import sys

project_home = '/home/SEU_USUARIO/teste-codex/pms-site'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app import app as application
```

## 5) Configurar virtualenv no painel Web

Em "Virtualenv":

`/home/SEU_USUARIO/teste-codex/.venv`

## 6) Static files (opcional)

No painel Web, adicione:

- URL: `/static/`
- Directory: `/home/SEU_USUARIO/teste-codex/pms-site/static/`

## 7) Reload

Clique em `Reload` no painel Web.

## 8) Testar

Abra sua URL:

`https://SEU_USUARIO.pythonanywhere.com`

Se der erro, verifique:

- Error log: `Web -> Error log`
- Server log: `Web -> Server log`
