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

Each chunking tier has its own endpoint taking a `file` upload: `POST /v1/chunk/basic` and
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
