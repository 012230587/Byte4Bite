# Byte4Bite

AI recipe assistant that turns pantry ingredients into complete, step-by-step recipes. The backend uses **semantic vector search** over a MySQL corpus (~1,500 recipes) and **Gemini** to compose one tailored dish per request.

Design inspiration: clean food-blog layouts like [RecipeTin Eats](https://www.recipetineats.com/) — warm cream palette, serif headings, and a single clear call to action.

## Features

- **Get recipe** — one button: vector retrieval → LLM composition (ingredients, method, prep time)
- **Cuisine filters** — Italian, Thai, Indian, Mexican, and 15+ styles aligned with the backend
- **Dietary filters** — vegetarian, vegan, halal, gluten-free
- **Inspired-by transparency** — shows which corpus recipes informed the composition
- **Saved recipes** — sign in and save results to your account
- **Authentication** — JWT sessions, profile preferences, protected routes
- **Semantic search** — `gemini-embedding-001` embeddings (768-d) stored in MySQL

## Project structure

```
byte4bite/
├── Backend/          FastAPI, MySQL, RAG pipeline
├── Frontend/         Next.js 15 dashboard
├── Makefile          Dev shortcuts (make up, make verify, …)
└── dev.ps1           Windows equivalent when GNU Make is unavailable
```

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 20+
- MySQL 8 (database `byte4bite`, schema in `Backend/database/schema.sql`)
- [Gemini API key](https://ai.google.dev/)

### 1. Environment

```powershell
cd byte4bite
.\dev.ps1 setup-env          # Windows
# or: make setup-env

# Edit Backend/.env — at minimum:
#   GEMINI_API_KEY=...
#   MYSQL_PASSWORD=...
#   GENERATION_MODEL=gemini-2.0-flash
#   JWT_SECRET=...            # required for production
#   CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

Apply schema and optional migration:

```powershell
# Import Backend/database/schema.sql in MySQL, then:
make migrate
```

### 2. Install dependencies

```powershell
make install
# or: .\dev.ps1 install
```

### 3. Embeddings (first run or after new CSV data)

```powershell
make backfill    # embed corpus (~1,572 recipes)
make verify      # semantic search health check (3/3 probes)
```

### 4. Run the app

```powershell
make up
# or: .\dev.ps1 up
```

- **Dashboard:** http://127.0.0.1:3000/dashboard  
- **API:** http://127.0.0.1:8000  

Stop servers: `make down` or Ctrl+C.

## Makefile targets

| Command | Description |
|---------|-------------|
| `make up` | Backend + frontend |
| `make backend` | API only (:8000) |
| `make frontend` | Next.js only (:3000) |
| `make verify` | Embedding + search probes |
| `make backfill` | Resume-safe embedding backfill |
| `make ingest` | Sync new CSV datasets |
| `make health` | MySQL ping + verify |

Install GNU Make on Windows: `winget install GnuWin32.Make`

## API overview

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/recipes/generate` | Optional | Compose one recipe; logs `user_id` when signed in |
| `GET /api/recipes` | No | Browse corpus (vector-ranked) |
| `POST /api/auth/register` | No | Create account |
| `POST /api/auth/login` | No | Issue JWT |
| `GET /api/auth/me` | Bearer | Validate session + profile summary |
| `GET/PUT /api/auth/profile` | Bearer | Read/update preferences |
| `GET/POST /api/auth/saved-recipes` | Bearer | List/save recipes |

## Authentication & caching

**Backend**

- Passwords: bcrypt. Tokens: JWT (`JWT_EXPIRE_HOURS`, default 72h).
- `GET /api/auth/me` — session validation endpoint for the frontend.
- Profile reads cached in-process for **60 seconds** (`services/profile_cache.py`); invalidated on profile update.
- CORS origins from `CORS_ORIGINS` env var; `Authorization` header allowed.

**Frontend**

- `AuthProvider` wraps the app — shared session state, Navbar updates on login/logout.
- JWT stored in `localStorage`; `authFetch` attaches `Bearer` token.
- In-memory cache (`services/cache.ts`):
  - `/api/auth/me` — 60s fresh, 120s stale-while-revalidate
  - `/api/auth/saved-recipes` — 30s fresh, 60s stale
  - Cache cleared on login, logout, profile update, and save recipe.
- Protected routes: `/profile`, `/saved` redirect to `/signin?next=...`
- Dashboard **Get recipe** works without login; profile dietary preference pre-fills filters when signed in.

## Compose fallbacks (when Gemini quota is off)

If the LLM returns 429/quota errors, recipes are still built from your corpus and technique templates (`services/method_templates.py`):

1. **corpus_adapt** — steps from the top vector match (e.g. simmer chicken in sauce)
2. **corpus_hybrid** — corpus steps + technique template padding
3. **method_template** — one of 8 methods: sauce/simmer, grill, boil/poach, stir-fry, braise/stew, roast/bake, steam, pan sauté

Method is inferred from the query (`chicken sauce` → simmer, `grilled beef` → grill, etc.).

## Tech stack

- **Frontend:** Next.js 15, React 19, Tailwind CSS 4  
- **Backend:** FastAPI, mysql-connector-python  
- **AI:** Google Gemini (`gemini-2.0-flash` generation, `gemini-embedding-001` embeddings)  
- **Search:** Cosine similarity over VARBINARY(768-d) vectors in MySQL  

## License

Academic / project use — see repository root for course context.
