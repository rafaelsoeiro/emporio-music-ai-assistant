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
alembic upgrade head
python -m app.scripts.ingest_csv --data-dir app/data
uvicorn app.main:app --reload
```

A API ficará disponível em `http://localhost:8000`. A documentação interativa
fica em `http://localhost:8000/docs`.

## Comandos úteis

```bash
make test      # executa os testes
make lint      # valida lint e formatação
make format    # aplica correções e formatação
make migrate   # aplica as migrações pendentes
make ingest    # importa ou atualiza os dados dos CSVs
```

## Banco de dados

Por padrão, a aplicação usa SQLite em `data/app.db`. A conexão pode ser alterada
pela variável `DATABASE_URL` do arquivo `.env`.

Para criar e aplicar uma migração após adicionar ou alterar modelos SQLAlchemy:

```bash
make migration message="descricao da alteracao"
make migrate
```

Todos os modelos devem herdar de `app.db.base.Base` e ser importados pelo arquivo
`migrations/env.py` para que o Alembic consiga detectá-los.

## Ingestão dos CSVs

A carga valida cada conjunto pelo cabeçalho, independentemente do nome do arquivo.
A operação inteira é transacional e usa `UPSERT` pelas chaves primárias: executar
o comando novamente não duplica registros e atualiza linhas alteradas no CSV.

Com o ambiente virtual ativo e as migrações aplicadas:

```bash
python -m app.scripts.ingest_csv --data-dir app/data
```

A carga esperada dos arquivos atuais é de 191 linhas: 50 clientes, 9 categorias,
65 produtos, 25 promoções, 20 pedidos e 22 itens de pedido.

## Validação e testes pendentes

Neste ambiente de desenvolvimento não foi possível instalar as dependências,
porque o Python não possui `ensurepip` e a rede externa está indisponível. A
sintaxe e a consistência estática foram verificadas. Quando `python3-venv` e o
acesso ao índice de pacotes estiverem disponíveis, execute:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.ingest_csv --data-dir app/data
ruff check .
ruff format --check .
pytest
```

Os testes de ingestão cobrem a primeira carga, a reexecução idempotente, a
atualização por chave primária, campos opcionais de pedidos e a rejeição de uma
coleção incompleta.

## Docker

```bash
docker build -t emporio-music-backend .
docker run --rm -p 8000:8000 --env-file .env emporio-music-backend
```

## Endpoints iniciais

- `GET /`: informações básicas da API
- `GET /api/v1/health`: verificação de saúde

