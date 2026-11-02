# RagBytes website

Next.js front end for RagBytes. The home page (`/`) uploads a document and shows the chunks. `/docs` shows API examples. `/privacy` is the privacy page.

The API is a separate Python service. Start it from the repo root first (see the root [README](../README.md)), then start this app.

## Getting started

```bash
cd web
npm install
npm run dev
```

Open http://127.0.0.1:3000.

The UI forwards uploads to the API through `/api/chunks`. Set `RAGBYTE_API_URL` if the API is not at `http://127.0.0.1:8000`. Set `RAGBYTE_PUBLIC_API_URL` to the address the `/docs` page should show (default `http://localhost:8000`).

Other commands:

```bash
npm run lint
npm run build
npm run start
```

`npm run build` then `npm run start` serves the production build.

## Phone layout test

Playwright opens `/`, `/docs`, and `/privacy` at 360px and 390px wide. The test fails if a page is wider than the screen. It also saves a full-page screenshot of each visit.

One-time setup, from `web/`:

```bash
npm install
npx playwright install chromium
```

`npm install` adds the Playwright package. `npx playwright install chromium` downloads the browser. You only need to do that again when Playwright itself is upgraded.

Run the test:

```bash
npm run test:mobile
```

Playwright starts `npm run dev` if the site is not already running on port 3000. If you already have the dev server open, it reuses that.

Screenshots are written to `web/test-results/` (`mobile-home-360.png`, and the same pattern for docs, privacy, and 390px). That folder is gitignored. An HTML report is written to `web/playwright-report/`; open it with `npx playwright show-report`.
