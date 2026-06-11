# Byte4Bite Frontend

Next.js dashboard for the Byte4Bite recipe assistant. See the [project README](../README.md) for full setup, Makefile commands, and architecture.

## Run locally

```bash
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` in `.env.local` (created automatically by `make setup-env`).

## Auth & session

- Wrapped in `AuthProvider` (`contexts/AuthContext.tsx`)
- Sign in / register at `/signin` and `/register`
- Protected: `/profile`, `/saved` (redirects with `?next=`)
- Cached API reads via `services/cache.ts` (60s profile, 30s saved list)

See [project README](../README.md#authentication--caching) for JWT, CORS, and backend endpoints.

## Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Development server (:3000) |
| `npm run build` | Production build |
| `npm run lint` | ESLint |

## Key files

- `app/dashboard/page.tsx` — main recipe flow (single **Get recipe** action)
- `components/RecipeDetail.tsx` — recipe card with ingredients and method
- `services/auth.ts` — JWT session helpers for saved recipes
