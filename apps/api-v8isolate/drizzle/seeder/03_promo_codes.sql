-- Seed: PromoCode
-- Satu kode per event, tipe 'free' (unlock paket Standar gratis).
-- max_uses dibatasi sama dengan total_slots event (3).

INSERT INTO `PromoCode` (event_id, code, description, discount_type, discount_value, max_uses, current_uses, is_active) VALUES
(1, 'KULINER2025',  'Kode promo gratis paket Standar event Kuliner',    'free', 0, 3, 1, 1),
(2, 'CANTIK2025',   'Kode promo gratis paket Standar event Kecantikan', 'free', 0, 3, 0, 1),
(3, 'SEHAT2025',    'Kode promo gratis paket Standar event Kesehatan',  'free', 0, 3, 0, 1),
(4, 'FASHION2025',  'Kode promo gratis paket Standar event Fashion',    'free', 0, 3, 0, 1),
(5, 'BELAJAR2025',  'Kode promo gratis paket Standar event Pendidikan', 'free', 0, 3, 0, 1);
