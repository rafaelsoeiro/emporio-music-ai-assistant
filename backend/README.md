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

## Serviços de consulta

`app.services.read_queries` fornece consultas somente leitura construídas com a
API parametrizada do SQLAlchemy. Nenhuma função aceita SQL livre ou executa
`INSERT`, `UPDATE`, `DELETE` ou `COMMIT`.

- `search_available_products`: busca apenas produtos com status `active` e
  estoque maior que zero. Aceita termo literal aplicado a nome e descrição,
  `category_id` e preços mínimo/máximo. Retorna `[]` quando nada corresponde.
- `get_active_promotions`: retorna promoções ativas e calcula o preço final com
  arredondamento monetário para duas casas decimais. Retorna `[]` quando não há
  promoções ativas.
- `get_order_detail`: retorna pedido, cliente, itens, status, pagamento,
  rastreio, previsão de entrega e observações. Retorna `None` quando o
  `order_id` não existe. Como os itens não possuem preço histórico próprio, os
  campos de preço dos itens são identificados como valores atuais do catálogo;
  o total oficial continua sendo `Order.total_brl`.

Filtros de preço negativos, faixa invertida ou `category_id` não positivo geram
`ValueError`. Os resultados são dataclasses imutáveis e não expõem entidades ORM
para alteração.

## RAG das políticas da loja

A camada em `app.rag` indexa o PDF de políticas com `PyPDFLoader`, divide o texto
com `RecursiveCharacterTextSplitter`, gera vetores com OpenAI Embeddings e usa o
Qdrant em modo local persistente. Ela ainda não está conectada a endpoints nem a
um agente.

Configure o `.env`:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
QDRANT_PATH=./data/qdrant
QDRANT_COLLECTION=store_policies
RAG_PDF_PATH=./app/data/políticas_da_loja.pdf
RAG_CHUNK_SIZE=1000
RAG_CHUNK_OVERLAP=150
RAG_TOP_K=4
```

Depois, indexe o documento:

```bash
python -m app.scripts.index_policies
# ou
make index-policies
```

Também é possível indicar outro arquivo com `--pdf caminho/arquivo.pdf`. Cada
chunk recebe metadados de fonte, página (iniciando em 1), índice e hash do PDF.
Os IDs são UUIDs determinísticos: uma reexecução faz upsert dos mesmos pontos e,
somente depois, remove chunks antigos daquela fonte que não existam mais. Assim,
a indexação pode ser repetida sem duplicar vetores.

O retriever é usado diretamente pela camada de aplicação, sem expor endpoint:

```python
from app.rag.retriever import PolicyRetriever

with PolicyRetriever.from_settings() as retriever:
    chunks = retriever.retrieve("Qual é o prazo para troca?")
```

`retrieve` retorna uma lista de trechos com conteúdo, fonte, página e score. Uma
consulta sem correspondência retorna `[]`; uma pergunta vazia gera `ValueError`.
Se a coleção ainda não foi indexada, a criação configurada do retriever gera
`RAGNotIndexedError`.

Os testes de RAG usam mocks para loader, splitter, vector store e busca vetorial;
eles não enviam dados à OpenAI nem iniciam um serviço Qdrant externo.

## Agente de atendimento

O agente usa `ChatOpenAI` com tool calling explícito. O loop está implementado em
`app.agent.service`: cada chamada é validada, executada por nome e devolvida ao
modelo como `ToolMessage`. Não é usado SQL livre nem um executor automático de
agentes.

Configuração adicional:

```dotenv
OPENAI_CHAT_MODEL=gpt-4.1-mini
AGENT_MAX_TOOL_ITERATIONS=6
AGENT_HISTORY_MESSAGES=20
```

As tools registradas são somente leitura:

- busca de produtos ativos e em estoque;
- promoções ativas;
- recuperação de políticas no Qdrant;
- consulta de pedido no SQLite.

A tool de pedido exige `order_id` e `customer_email`. Sem os dois campos, ela não
é executada e o modelo recebe uma instrução para solicitar a confirmação sem
revelar se o pedido existe. Quando os dados não correspondem, a resposta da tool
também é genérica e não contém informações do pedido.

`conversation_id` é opcional. Quando enviado, mantém apenas as mensagens recentes
em memória no processo atual; esse histórico é perdido ao reiniciar a aplicação e
não substitui autenticação.

### Endpoint

O único endpoint do agente é `POST /chat` — sem prefixo `/api/v1`:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Quais guitarras estão disponíveis até R$ 2.000?",
    "conversation_id": "cliente-123"
  }'
```

Resposta:

```json
{
  "answer": "Encontrei estas opções...",
  "sources": [
    {
      "kind": "database",
      "name": "SQLite: products/categories",
      "page": null
    }
  ]
}
```

Exemplo de consulta confirmada de pedido:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Consulte o pedido 20 para cliente@exemplo.com",
    "conversation_id": "cliente-123"
  }'
```

Fontes de políticas incluem o nome do PDF e a página. Consultas que não usam
tools retornam `sources: []`. Falha temporária do modelo ou excesso de iterações
retorna HTTP 503; payload inválido retorna HTTP 422. Ainda não há front-end.

## Docker

```bash
docker build -t emporio-music-backend .
docker run --rm -p 8000:8000 --env-file .env emporio-music-backend
```

## Endpoints iniciais

- `GET /`: informações básicas da API
- `GET /api/v1/health`: verificação de saúde
- `POST /chat`: atendimento com tools somente leitura

