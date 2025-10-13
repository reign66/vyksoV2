# Vykso Backend

API backend pour génération automatique de vidéos TikTok via Sora 2.

## Stack

- **FastAPI** - API REST
- **Supabase** - Database + Auth
- **Cloudflare R2** - Storage vidéos
- **Kie.ai** - Sora 2 API
- **Railway** - Hosting

## Setup Local
```bash
# Clone
git clone https://github.com/TON_USERNAME/vykso-backend.git
cd vykso-backend

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your credentials

# Run locally
uvicorn main:app --reload --port 8080
