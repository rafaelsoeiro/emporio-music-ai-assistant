# Backend

API do Emporio Music construída com FastAPI.

## Requisitos

- Python 3.10 ou superior

## Executando localmente

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

A API ficará disponível em `http://localhost:8000`. A documentação interativa
fica em `http://localhost:8000/docs`.

## Comandos úteis

```bash
make test      # executa os testes
make lint      # valida lint e formatação
make format    # aplica correções e formatação
```

## Docker

```bash
docker build -t emporio-music-backend .
docker run --rm -p 8000:8000 --env-file .env emporio-music-backend
```

## Endpoints iniciais

- `GET /`: informações básicas da API
- `GET /api/v1/health`: verificação de saúde

