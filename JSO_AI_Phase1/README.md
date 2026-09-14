
# JSO AI — Phase 1 MVP

Includes:
- Landing website
- Sign up / login
- Secure password hashing
- SQLite user database
- Dashboard
- Website URL storage
- Real public-page SEO audit (title, meta description, H1, images/alt, HTTPS, keyword frequency)
- AI report layer
- Optional OpenAI server-side enhancement
- $0.99/month Starter plan UI
- Demo checkout + payment records
- Subscription status stored in the database

## Run on Windows

1. Install Python 3.11+.
2. Open Command Prompt in this folder.
3. Create environment:
   `python -m venv .venv`
4. Activate:
   `.venv\Scripts\activate`
5. Install:
   `pip install -r requirements.txt`
6. Copy `.env.example` to `.env`.
7. Start:
   `python app.py`
8. Open:
   http://127.0.0.1:5000

## Optional real AI

Put your AI provider secret in `.env` as `OPENAI_API_KEY`.
Never put the key in HTML/JavaScript.

The code uses the OpenAI Python SDK server-side when the key exists; otherwise it uses a local fallback so the MVP still runs.

## Real payment

The included checkout is intentionally DEMO only. Before charging customers, connect a real hosted checkout/payment gateway on the server, verify the provider webhook/signature, and update the subscription only after a verified payment event.

Do not collect raw card numbers in your own HTML form.

For Bangladesh, choose a payment provider that supports your business, currency, recurring/subscription rules, and merchant onboarding. Add provider secrets only to server environment variables.

## Production checklist

- HTTPS
- Strong random FLASK_SECRET_KEY
- PostgreSQL instead of SQLite for a larger production deployment
- CSRF protection
- Rate limiting
- Email verification + password reset
- Real payment provider + verified webhook
- Terms, Privacy Policy, refund/cancellation policy
- Server-side AI limits and usage tracking
- Monitoring and backups
- OAuth/API integrations for future social-platform phase
