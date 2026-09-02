# Zynovix BorderVerity — SIH Prototype

AI-powered travel document verification and fraud-detection prototype (Smart India
Hackathon). It runs a full pipeline: **OCR → MRZ parsing → cross-validation → tamper →
face → expiry → reference-DB lookup → risk scoring → decision**.

## What's new: REAL MongoDB-backed verification reference data

The uploaded / demo passport is processed by the existing **OCR + MRZ** pipeline, the
extracted **document number** is used to query a **real local MongoDB** reference database,
and the database result drives the final risk decision.

- Data is **synthetic** and clearly labelled `SIH SYNTHETIC DEMO DATABASE` / `DEMO / MOCK`.
- Not connected to any real government API (`NOT CONNECTED`).
- Result page shows a **DATABASE VERIFICATION** badge when the decision came from MongoDB.

See **[docs/mongodb.md](docs/mongodb.md)** for the data model, collections, and run steps.

## Requirements

- Python **3.10** with the packages in `backend/requirements.txt` (FastAPI, SQLAlchemy,
  RapidOCR-onnxruntime, OpenCV, pymongo, …)
- **MongoDB Community** running locally

## Running

1. **Start MongoDB** (Windows, extracted binary):

   ```
   mongodb\mongod.exe --dbpath data\mongodb --port 27017
   ```

2. **Seed the synthetic database**:

   ```
   py -3.10 seeds/seed_mongo_database.py
   ```

3. **Start the API**:

   ```
   cd backend
   py -3.10 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

4. Open `http://127.0.0.1:8000/` and sign in with:
   - **Username:** `officer`
   - **Password:** `SIH@2026Demo`

## Demo scenarios (New Verification page)

| Scenario | Expected decision      |
|----------|------------------------|
| Valid Passport | VERIFIED (LOW) |
| Expired Passport | REVIEW (MEDIUM) |
| OCR/MRZ Mismatch | HIGH RISK |
| Face Mismatch | HIGH RISK |
| Tampering | HIGH RISK |
| Watchlist Hit | HIGH RISK |
| Duplicate Identity | REVIEW (MEDIUM) |
| Document Not in DB | REVIEW (MEDIUM) · +40 |

## Key routes

- `GET  /api/health` — MongoDB status + transparency labels
- `POST /api/auth/login` — form-encoded `username` / `password`
- `POST /api/upload-document`, `POST /api/verify/document` — image verification
- `POST /api/verify/demo` — scenario verification
- `GET  /api/database/*` — demo database page endpoints

## Project layout

```
backend/app/            FastAPI app (routers, services, db, config)
backend/app/db/mongo.py MongoDB connection + collections + indexes
backend/app/services/   OCR, MRZ, face, risk, providers (Mongo-backable)
seeds/seed_mongo_database.py   synthetic Mongo dataset
frontend/               SPA (index.html, js/app.js, css)
data/samples/           sample passport / face images
docs/mongodb.md         MongoDB reference-database documentation
```
