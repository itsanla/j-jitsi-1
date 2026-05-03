-- Seed: Event
-- 5 program Digitalisasi UMKM Nusantara

INSERT INTO `Event` (id, slug, title, emoji, target, description, benefits, image_url, normal_price, event_price, is_active) VALUES
(
  1,
  'digitalisasi-kuliner-nusantara',
  'Digitalisasi Kuliner Nusantara',
  '🍵',
  'Cafe, warung, restoran, catering',
  'Program eksklusif untuk pelaku kuliner Indonesia agar punya website profesional, muncul di Google, dan menjangkau lebih banyak pelanggan.',
  json_array(
    'Landing page profesional khusus bisnis kuliner',
    'Subdomain .jirokit.com gratis',
    'Hosting 6 bulan gratis',
    'Section menu makanan & galeri foto',
    'Tombol pesan via WhatsApp & GoFood/GrabFood',
    'SEO basic (muncul di pencarian Google)',
    'Google Analytics terpasang',
    'Desain responsif Mobile & Desktop',
    '2x revisi desain'
  ),
  '/image/event.webp',
  399000,
  299000,
  1
),
(
  2,
  'digitalisasi-kecantikan-nusantara',
  'Digitalisasi Kecantikan Nusantara',
  '💇',
  'Salon, barbershop, spa, skincare',
  'Buka cabang digital untuk bisnis kecantikan Anda. Tampilkan layanan, portofolio, dan harga di website yang elegan.',
  json_array(
    'Landing page profesional khusus bisnis kecantikan',
    'Subdomain .jirokit.com gratis',
    'Hosting 6 bulan gratis',
    'Section layanan & price list',
    'Galeri portofolio before/after',
    'Booking via WhatsApp',
    'SEO basic (muncul di pencarian Google)',
    'Google Analytics terpasang',
    'Desain responsif Mobile & Desktop',
    '2x revisi desain'
  ),
  '/image/event.webp',
  399000,
  299000,
  1
),
(
  3,
  'digitalisasi-kesehatan-nusantara',
  'Digitalisasi Kesehatan Nusantara',
  '🏥',
  'Klinik, apotek, dokter praktik',
  'Solusi digital untuk fasilitas kesehatan agar pasien lebih mudah menemukan informasi layanan, jadwal, dan kontak Anda.',
  json_array(
    'Landing page profesional khusus bisnis kesehatan',
    'Subdomain .jirokit.com gratis',
    'Hosting 6 bulan gratis',
    'Section layanan medis & jadwal praktik',
    'Form konsultasi via WhatsApp',
    'Info lokasi dengan Google Maps',
    'SEO basic (muncul di pencarian Google)',
    'Google Analytics terpasang',
    'Desain responsif Mobile & Desktop',
    '2x revisi desain'
  ),
  '/image/event.webp',
  399000,
  299000,
  1
),
(
  4,
  'digitalisasi-fashion-nusantara',
  'Digitalisasi Fashion Nusantara',
  '👗',
  'Toko baju, konveksi, thrift store',
  'Tampilkan koleksi produk fashion Anda dengan website yang stylish dan siap jualan ke seluruh Indonesia.',
  json_array(
    'Landing page profesional khusus bisnis fashion',
    'Subdomain .jirokit.com gratis',
    'Hosting 6 bulan gratis',
    'Galeri katalog produk',
    'Tombol checkout via WhatsApp',
    'Integrasi link marketplace (Tokopedia, Shopee)',
    'SEO basic (muncul di pencarian Google)',
    'Google Analytics terpasang',
    'Desain responsif Mobile & Desktop',
    '2x revisi desain'
  ),
  '/image/event.webp',
  399000,
  299000,
  1
),
(
  5,
  'digitalisasi-pendidikan-nusantara',
  'Digitalisasi Pendidikan Nusantara',
  '🏫',
  'Les privat, bimbel, kursus',
  'Bantu lembaga pendidikan Anda dipercaya dan ditemukan calon murid dengan website profesional yang informatif.',
  json_array(
    'Landing page profesional khusus bisnis pendidikan',
    'Subdomain .jirokit.com gratis',
    'Hosting 6 bulan gratis',
    'Section program & jadwal kelas',
    'Form pendaftaran via WhatsApp',
    'Testimoni murid & orang tua',
    'SEO basic (muncul di pencarian Google)',
    'Google Analytics terpasang',
    'Desain responsif Mobile & Desktop',
    '2x revisi desain'
  ),
  '/image/event.webp',
  399000,
  299000,
  1
);
