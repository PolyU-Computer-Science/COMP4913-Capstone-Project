# Frontend — Human-in-the-Loop UI

React 19 + TypeScript + Vite + Tailwind CSS 4 + shadcn/ui client for the
Agentic AI Email Assistant. See the [project README](../README.md) for the
overall architecture.

## Scripts

```bash
npm install      # install dependencies
npm run dev      # dev server on http://localhost:5173 (proxies /api to :8000)
npm run lint     # oxlint
npm test         # vitest (jsdom)
npm run build    # tsc -b && vite build
```

The backend must be running (`uv run api` from the repository root) for the
UI to load data. The proxy target can be changed with `VITE_API_TARGET` in
`frontend/.env` (default `http://localhost:8000`).

## Layout

```plaintext
src/
├── App.tsx              # route registration
├── main.tsx             # React entry point
├── components/          # app shell (sidebar, header) + shared badges/fields
│   └── ui/              # shadcn/ui primitives
├── hooks/               # shared React hooks
├── lib/                 # API client (api.ts), shared types, utils
├── pages/               # dashboard, inbox, cases, case detail, mailboxes, settings
└── test/                # vitest setup + tests
```
