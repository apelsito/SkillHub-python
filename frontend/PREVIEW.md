# Landing Page Preview

## Local Preview

```bash
cd frontend
pnpm dev
```

Open `http://127.0.0.1:3000`.

## What To Check

- The landing page renders at `/`.
- Search submits to the search page.
- "Explore Skills" opens the skill catalog.
- "Publish Skill" opens the publish flow for authenticated users.
- The layout remains usable on mobile, tablet, and desktop widths.

## Notes

- Vite proxies API requests to `http://127.0.0.1:8080`.
- Keep local URLs on `127.0.0.1` on Windows to avoid IPv6 `localhost` issues.
