# Rethread Agents

> Assistente de IA do **Rethread**, o brechó online de roupas de segunda mão: um serviço FastAPI + LangGraph em que agentes especialistas respondem dúvidas de **tamanho/caimento** e de **estilo** com base no acervo real, com revisão de qualidade antes de cada resposta.

## Recursos

- **Atendimento multiagente**: um roteador identifica as intenções da mensagem e aciona os especialistas — **Tamanho & Caimento** e **Stylist** — em sequência
- **Revisão de qualidade** (LLM-as-judge): toda resposta é conferida contra a saída das ferramentas antes de chegar ao cliente; reprovada, volta ao especialista com o motivo
- **Busca semântica (RAG)** no acervo com pgvector, só em peças ativas, com filtros de categoria, departamento e preço
- **Caimento por medidas reais**: compara peça × corpo de forma determinística, considerando a elasticidade do tecido — o LLM explica, não faz conta
- **Sessões com memória**: histórico, peça em contexto e medidas do cliente persistem por `session_id`
- **Recomendações estruturadas**: a resposta traz os `skus` das peças sugeridas, prontos para o backend montar os cards
- **Streaming (SSE)** com eventos do pipeline e a resposta final
- **Modelos por papel**: Claude, OpenAI ou Llama (Ollama), escolhidos separadamente para especialistas, triagem e revisão

## Arquitetura

O serviço é um **read model de IA** do Rethread: o backend é a fonte da verdade (produtos, usuários, dono de cada sessão) e publica as peças aqui; o agent mantém a sua cópia otimizada para IA (embeddings e medidas) e o histórico das conversas. O frontend nunca fala com o agent diretamente.

```
Frontend ──▶ Backend (NestJS) ──▶ Agent (este serviço) ──▶ Postgres + pgvector
               valida sessão         grafo LangGraph          items, size_equivalences,
               SKUs → produtos       + tools do acervo        chat_sessions, chat_messages
```

Cada mensagem passa por uma **máquina de estados** (LangGraph):

```
START → triage → dispatch ─┬─ size_fit ──────────┐
                  ▲        ├─ style_consulting ──┤
                  │        └─ (fila vazia) ─→ compose → END
                  │                              ▼
                  └── aprovado / limite ──── quality ── reprovado → mesmo especialista
```

1. **`triage`** — modelo rápido, saída estruturada: devolve **todas** as intenções da mensagem.
2. **`dispatch`** — executa os especialistas em ordem fixa (caimento antes de estilo), passando a resposta anterior adiante para o próximo complementar em vez de repetir.
3. **`size_fit` / `style_consulting`** — agentes com tool calling e saída estruturada `{message, skus}`. Os SKUs só são aceitos se vieram das ferramentas.
4. **`quality`** — o juiz aprova ou reprova com base nas evidências (sem medida, peça ou preço inventado), até `MAX_ATTEMPTS`.
5. **`compose`** — une as respostas em uma única mensagem.

| Especialista | Foco | Ferramentas |
|---|---|---|
| **Tamanho & Caimento** | medidas da peça × medidas do cliente | `get_item_spec`, `lookup_size_equivalence`, `compare_fit` |
| **Stylist** | combinações, cores, tecidos, ocasiões | `get_item_spec`, `search_catalog` |

Organização do código:

- `src/api.py` — rotas HTTP (FastAPI)
- `src/actions/` — casos de uso, independentes de transporte (chat, catálogo)
- `src/ai/` — grafo, especialistas, ferramentas, prompts e providers de modelo
- `src/catalog/` — peças, tabela de equivalência, busca vetorial e cálculo de caimento
- `src/sessions/` — sessões e histórico de conversa
- `migrations/` — schema do banco (Alembic)

## Stack

- **Python 3.13** + **FastAPI**
- **LangGraph** / LangChain (agentes, tool calling, saída estruturada)
- **PostgreSQL + pgvector** + SQLAlchemy (com migrations Alembic)
- **Anthropic**, **OpenAI** e **Ollama** como providers de modelo
- **uv**, **Docker Compose**

## Executando com Docker Compose (recomendado)

Pré-requisito (uma vez): copie o `.env.example` para `.env` e preencha a chave do provider escolhido (`OPENAI_API_KEY` e/ou `ANTHROPIC_API_KEY`):

```bash
cp .env.example .env
```

Um único comando sobe **API + PostgreSQL com pgvector**:

```bash
docker compose up -d
```

A API fica em http://localhost:8000 e a documentação em http://localhost:8000/docs. As migrations rodam sozinhas no startup e o código é recarregado a cada alteração em `src/`.

Para popular o acervo com peças e a tabela de equivalência de exemplo:

```bash
docker compose exec -e PYTHONPATH=/app/src api uv run --no-sync python scripts/seed.py
```

Para parar:

```bash
docker compose down
```

> Use `docker compose down -v` para apagar também os dados do Postgres.

## Executando localmente (sem Docker)

```bash
uv sync
docker compose up -d postgres     # só o banco, em localhost:5434
make migrate                      # aplica as migrations
make seed                         # opcional: dados de exemplo
make api                          # http://127.0.0.1:8000
```

## Variáveis de ambiente

Copie `.env.example` para `.env`. Os modelos são definidos **por papel**:

| Papel | Variáveis | Usado em |
|---|---|---|
| large | `LLM_PROVIDER`, `MODEL` | especialistas (precisa de tool calling) |
| fast | `FAST_PROVIDER`, `MODEL_FAST` | triagem e composição |
| judge | `JUDGE_PROVIDER`, `MODEL_JUDGE` | revisão de qualidade |
| embeddings | `EMBED_PROVIDER`, `EMBED_MODEL`, `EMBED_DIMENSIONS` | busca semântica |

Providers: `anthropic` | `openai` | `ollama`. `FAST_PROVIDER` e `JUDGE_PROVIDER` vazios herdam o `LLM_PROVIDER`. A Anthropic não tem API de embeddings, então `EMBED_PROVIDER` é `openai` ou `ollama`.

> **Dimensão do vetor:** a coluna `items.embedding` é criada com `EMBED_DIMENSIONS` na migration 001 (1536 para `text-embedding-3-small`, 768 para `nomic-embed-text`). Trocar o modelo de embedding depois exige nova migration + `POST /items/reindex?only_missing=false`.

Outras: `MAX_ATTEMPTS` (tentativas por especialista), `SEARCH_TOP_K`, `CHAT_HISTORY_MESSAGES` (mensagens anteriores enviadas ao agent) e `DATABASE_URL`.

## Documentação da API

Acesse http://localhost:8000/docs após subir o servidor.

### Chat

`POST /chat/stream` (SSE) — usado pelo backend — e `POST /chat` (resposta única):

```json
{
  "session_id": "5f0c…",
  "message": "tem alguma calça para trabalho até 30 reais?",
  "item_id": "SKU-DA-PECA-EM-CONTEXTO",
  "buyer_measurements": { "waist": 72, "hip": 98 }
}
```

Todos os campos além de `message` são opcionais. Com `session_id`, o agent cria a sessão no primeiro uso e, nas seguintes, recupera histórico, peça em contexto e medidas — não é preciso reenviá-los. Quem controla e valida a sessão é o backend.

O stream emite `triage`, `specialist`, `tool`, `quality`, `status`, `token` e, por fim, `done` com a resposta completa:

```json
{ "session_id": "5f0c…", "response": "Sim! Temos a Calça Zara…", "skus": ["SKU-1"], "intents": ["style_consulting"] }
```

Rascunhos reprovados na revisão nunca são transmitidos. A mensagem cita as peças pelo nome; os SKUs vêm apenas em `skus`.

### Catálogo

| Rota | Descrição |
|---|---|
| `POST /items`, `PATCH /items/{id\|sku}` | cria/atualiza peça (gera o embedding) |
| `GET /items`, `GET /items/{id\|sku}` | lista/consulta peças |
| `POST /items/search` | busca semântica |
| `POST /items/reindex` | regera embeddings faltantes (ou todos) |
| `GET\|POST /size-equivalences` | tabela de equivalência de tamanhos |

**Medidas** (todas opcionais, em cm): circunferências (`chest`, `waist`, `hip`, `thigh`) são a **volta completa** — mediu a peça deitada, dobre o valor; lineares: `shoulder`, `sleeve`, `length`, `rise`, `inseam`, `hem`. O `stretch` do tecido (`none`/`low`/`medium`/`high`) afeta o veredito de caimento.

**Tabela de equivalência**: converte o tamanho da etiqueta em faixas de medida do **corpo** (ex.: calça 40 feminino → cintura 72–76 cm). A linha mais específica vence: marca+época > marca > época > genérica. Ela é cadastrada à parte — criar peças não a preenche.

## Migrations

```bash
make migrate                              # upgrade head
uv run python migrate.py current
uv run python migrate.py downgrade -1
```
