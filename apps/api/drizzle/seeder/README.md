# D1 Seeders

Apply in numeric order. Foreign keys are enforced in D1, so later seeders depend on earlier ones.

## Local

```bash
pnpm wrangler d1 execute DB --local --file=./drizzle/seeder/01_events.sql
pnpm wrangler d1 execute DB --local --file=./drizzle/seeder/02_quotas.sql
pnpm wrangler d1 execute DB --local --file=./drizzle/seeder/03_promo_codes.sql
```

Atau jalankan semua sekaligus:

```bash
./drizzle/seeder/seed-local.sh
```

## Remote

Swap `--local` for `--remote`, atau gunakan `./drizzle/seeder/seed-remote.sh`.

## Isi seed

- **01_events.sql** — 5 program Digitalisasi UMKM Nusantara (Kuliner, Kecantikan, Kesehatan, Fashion, Pendidikan).
- **02_quotas.sql** — Quota slot per event (3 slot/event, Kuliner sudah terisi 1).
- **03_promo_codes.sql** — Kode promo gratis paket Standar (`KULINER2025`, `CANTIK2025`, `SEHAT2025`, `FASHION2025`, `BELAJAR2025`).
- **04_users.sql** — Admin login: `itsanla` / `070078` (PBKDF2-SHA256).
