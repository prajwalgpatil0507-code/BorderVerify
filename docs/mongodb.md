# MongoDB Reference Database — SIH SYNTHETIC DEMO DATABASE

The BorderVerity prototype now reads its **live verification reference data** from a real
local **MongoDB** server. This dataset is **synthetic** and is used to simulate the external
data sources a real border system would query (passport registry, visa registry, watchlist,
prior-traveller records). It is **NOT** a government database and is always labelled
`SIH SYNTHETIC DEMO DATABASE` / `DEMO / MOCK`.

## How the pipeline uses it

1. An officer uploads a document image (or runs a demo scenario).
2. The existing **OCR + MRZ** pipeline extracts the passenger attributes and the **document number**.
3. The verification engine calls the **provider factory** (`get_passport_provider()`, etc.).
   - If MongoDB is reachable, it uses the `Mongo*Provider` implementations.
   - Otherwise it falls back to the SQLite demo providers (no breakage).
4. The provider queries MongoDB by document number and the result **feeds the risk engine**:
   - `passport_not_found` (+40) — document number absent from the reference DB
   - `document_anomaly` (+20) — DB status is `stolen` / `suspicious` / `document_is_valid=false`
   - `expired_passport` (+30) / `expired_visa` (+30)
   - `watchlist_match` (+65) / `blacklist`
   - `duplicate_identity` (+40)
5. The final decision (VERIFIED / REVIEW REQUIRED / HIGH RISK) and the `DATABASE VERIFICATION`
   badge on the result page reflect the real database result.

## Architecture

The verification engine depends on **interfaces**, not a concrete storage backend:

```
VerificationEngine
  ├── PassportProvider  → MongoPassportProvider   (passport_records)
  ├── VisaProvider      → MongoVisaProvider       (visa_records)
  ├── WatchlistProvider → MongoWatchlistProvider  (watchlist_records)
  └── IdentityProvider  → MongoIdentityProvider   (identity_records)
```

Swapping the Mongo providers for future authorised-government providers requires **no change**
to the pipeline.

## Environment variables (`backend/.env`)

```
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=borderverify
```

## Collections

| Collection             | Purpose                                             | Index                          |
|------------------------|-----------------------------------------------------|--------------------------------|
| `passengers`           | Traveller profiles                                  | `passenger_id` (unique)        |
| `passport_records`     | Issued-passport registry                            | `passport_number` (unique)     |
| `visa_records`         | Visa registry                                       | `visa_number` (unique)         |
| `watchlist_records`    | Watchlist / blacklist                               | `passport_number`              |
| `identity_records`     | Prior-traveller records (duplicate identity check)  | `identity_reference` (unique)  |
| `verification_records` | Historical verification outcomes                    | `verification_id` (unique)     |
| `audit_logs`           | Officer audit trail                                 | `verification_id`              |
| `system_config`        | Dataset identity / transparency metadata            | `key` (unique)                 |

## Seed data

`seeds/seed_mongo_database.py` creates a coherent synthetic dataset:

- 21 passengers, 21 passports, 12 visas, 5 watchlist entries, 22 identity records,
  5 verification records, 5 audit logs, 5 system-config keys
- **Controlled demo scenarios** (each isolates a distinct risk signal):
  - valid (P12345678) — LOW / VERIFIED
  - expired passport (P7654321) — expired_passport
  - expired visa (P2345678) — expired_visa
  - watchlist (P1111222) — watchlist_match
  - OCR/MRZ mismatch (P9998887)
  - duplicate identity (P5556665)
  - document not found (any number not in the DB) — REVIEW REQUIRED (+40)

Run it (idempotent — resets the working collections):

```
py -3.10 seeds/seed_mongo_database.py
```

## Starting MongoDB locally

```
mongodb\mongod.exe --dbpath data\mongodb --port 27017
```

## Health / inspection endpoints

- `GET /api/health` — returns `mongo.available`, `mongo.database`, and transparency labels
- `GET /api/database/overview` — label, environment, counts, storage backend
- `GET /api/database/collections` — per-collection count + sample records
- `GET /api/database/lookup/{document_number}` — cross-collection lookup
- `GET /api/database/system-config` — dataset metadata
