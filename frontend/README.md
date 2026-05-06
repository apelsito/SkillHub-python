# SkillHub Frontend

React/Vite web client for SkillHub.

## Stack

- React 19
- Vite 6
- TypeScript
- Tailwind CSS
- TanStack Router
- TanStack Query
- i18next configured as an English-only product surface

## Local Development

Install dependencies:

```bash
pnpm install
```

Start the dev server:

```bash
pnpm dev
```

The app runs on `http://127.0.0.1:3000` and proxies API requests to `http://127.0.0.1:8080`.

## Useful Commands

```bash
pnpm test
pnpm typecheck
pnpm build
pnpm lint
```

## Runtime Configuration

Static deployments use `runtime-config.js.template` and `docker-entrypoint.d/30-runtime-config.sh` to generate runtime settings. During local development, Vite serves `public/runtime-config.js`.
