# RagBytes

Service that accepts uploaded files and returns text chunks.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn ragbytes.main:app --reload
```

Semantic chunking is switched off. The implementation remains, and it is not listed on the site or served at
`POST /v1/chunk/semantic`. Set `RAGBYTES_SEMANTIC_ENABLED=true` and mark the semantic tier `listed` and
`available` in `web/src/lib/tiers.ts` to publish it again. It also needs `RAGBYTES_OPENAI_API_KEY`. The key
stays on the server. `RAGBYTES_SEMANTIC_MODEL` picks the embedding model and defaults to `text-embedding-3-small`.
The request never carries a key. Passage text is sent to OpenAI and discarded with the file. Without the
key, that endpoint returns 503 and the other tiers keep working.

When semantic is published, its endpoint takes three optional form fields next to `file`:

- `style`: `precise` (chunks up to about 1,200 characters, cut readily), `balanced` (the default, up to
  about 2,000), or `broad` (up to about 3,000, cut only at clear changes of subject).
- `strict_headings`: `true` stops very short neighbouring headings from sharing a chunk.
- `max_chunk_chars`: a size cap from 500 to 8,000 characters, replacing the style's own.

The response repeats the settings used under `options`.

Each published chunking tier has its own endpoint taking a `file` upload: `POST /v1/chunk/basic` and
`POST /v1/chunk/structured`. `GET /v1/methods` lists the tiers, their endpoints and the file types,
and `GET /health` reports the running build.

Interactive docs are served at <http://localhost:8000/docs> (Swagger UI) and `/redoc`, and the
OpenAPI spec at `/openapi.json`. The public API is <https://api.ragbytes.com> (dev:
<https://api-dev.ragbytes.com>); the website's `/docs` page has examples.

## Web UI (RagBytes)

The Next.js front end lives in `web/`. Start the API above on port 8000, then:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The UI forwards uploads to the API through its own `/api/chunks`
route. Set `RAGBYTE_API_URL` if the API runs somewhere other than `http://127.0.0.1:8000`, and
`RAGBYTE_PUBLIC_API_URL` to the address the `/docs` page should show (default
`http://localhost:8000`).

The home page animates how each tier chunks the sample report, from real chunker output saved in
`web/src/lib/cv-demo.json`. After changing a chunker or the sample report, regenerate it with
`python scripts/build_cv_demo.py`; `tests/test_cv_demo.py` fails until you do.

## Deploy

See [deploy/README.md](deploy/README.md) for hosting on a DigitalOcean Droplet behind Cloudflare.
