# sistema-escala-midia

Sistema web em Python (Flask) para montar a **escala de comunicação** do mês: cadastro de voluntários e aptidões por área, disponibilidade (manual ou importação CSV), cultos de quinta e domingo, eventos extras, geração automática com distribuição equilibrada e exportação em **PDF**, **PNG** e **JPG**.

## Como rodar

1. Crie o ambiente virtual e instale dependências:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

2. Inicie o servidor:

```powershell
.\.venv\Scripts\python app.py
```

3. Abra no navegador: `http://127.0.0.1:5050`

Na primeira exportação em PDF, se não existir `fonts/DejaVuSans.ttf`, o sistema tenta baixar a fonte a partir do repositório do fpdf2 (requer internet). Você também pode copiar um `DejaVuSans.ttf` válido para essa pasta.

## CSV do Google Forms

Use colunas que o import reconheça, por exemplo: **nome** (ou name) e **data** (AAAA-MM-DD ou DD/MM/AAAA). Opcionalmente uma coluna de disponibilidade (sim/não). Os nomes precisam coincidir com o cadastro de voluntários.

## Dados

O SQLite fica em `escala.sqlite` na pasta do projeto (ignorado pelo Git no `.gitignore` padrão).
