import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";
import { relations, sql } from "drizzle-orm";

export const discountTypeEnum = ["free", "percentage", "fixed"] as const;
export type DiscountType = (typeof discountTypeEnum)[number];

export const userRoleEnum = ["admin"] as const;
export type UserRole = (typeof userRoleEnum)[number];

export const registrationStatusEnum = [
  "pending_form",
  "form_completed",
  "in_progress",
  "completed",
  "cancelled",
] as const;
export type RegistrationStatus = (typeof registrationStatusEnum)[number];

export const usersTable = sqliteTable("User", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
  role: text("role").notNull().$type<UserRole>().default("admin"),
  createdAt: integer("createdAt")
    .notNull()
    .default(sql`(unixepoch())`),
  updatedAt: integer("updatedAt")
    .notNull()
    .default(sql`(unixepoch())`),
});

export const eventsTable = sqliteTable("Event", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  slug: text("slug").notNull().unique(),
  title: text("title").notNull(),
  emoji: text("emoji").notNull(),
  target: text("target").notNull(),
  description: text("description").notNull(),
  benefits: text("benefits", { mode: "json" }).$type<string[]>().notNull(),
  image_url: text("image_url"),
  normal_price: integer("normal_price").notNull(),
  event_price: integer("event_price").notNull(),
  is_active: integer("is_active").notNull().default(1),
  createdAt: integer("createdAt")
    .notNull()
    .default(sql`(unixepoch())`),
  updatedAt: integer("updatedAt")
    .notNull()
    .default(sql`(unixepoch())`),
});

export const quotasTable = sqliteTable("Quota", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  event_id: integer("event_id")
    .notNull()
    .unique()
    .references(() => eventsTable.id, { onDelete: "cascade" }),
  total_slots: integer("total_slots").notNull().default(0),
  remaining_slots: integer("remaining_slots").notNull().default(0),
  updatedAt: integer("updatedAt")
    .notNull()
    .default(sql`(unixepoch())`),
});

export const promoCodesTable = sqliteTable("PromoCode", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  event_id: integer("event_id").references(() => eventsTable.id, {
    onDelete: "cascade",
  }),
  code: text("code").notNull().unique(),
  description: text("description"),
  discount_type: text("discount_type").notNull().$type<DiscountType>(),
  discount_value: integer("discount_value").notNull().default(0),
  max_uses: integer("max_uses"),
  current_uses: integer("current_uses").notNull().default(0),
  valid_until: integer("valid_until"),
  is_active: integer("is_active").notNull().default(1),
  createdAt: integer("createdAt")
    .notNull()
    .default(sql`(unixepoch())`),
  updatedAt: integer("updatedAt")
    .notNull()
    .default(sql`(unixepoch())`),
});

export const registrationsTable = sqliteTable("Registration", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  event_id: integer("event_id")
    .notNull()
    .references(() => eventsTable.id, { onDelete: "restrict" }),
  promo_code: text("promo_code"),
  initial_price: integer("initial_price").notNull(),
  final_price: integer("final_price").notNull(),
  status: text("status")
    .notNull()
    .$type<RegistrationStatus>()
    .default("pending_form"),
  customer_name: text("customer_name").notNull(),
  customer_whatsapp: text("customer_whatsapp").notNull(),
  customer_email: text("customer_email"),
  customer_city: text("customer_city"),
  business_name: text("business_name"),
  business_type: text("business_type"),
  business_description: text("business_description"),
  business_address: text("business_address"),
  business_hours: text("business_hours"),
  business_phone: text("business_phone"),
  business_instagram: text("business_instagram"),
  business_facebook: text("business_facebook"),
  business_maps_url: text("business_maps_url"),
  notes: text("notes"),
  createdAt: integer("createdAt")
    .notNull()
    .default(sql`(unixepoch())`),
  updatedAt: integer("updatedAt")
    .notNull()
    .default(sql`(unixepoch())`),
});

export const registrationProductsTable = sqliteTable("RegistrationProduct", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  registration_id: integer("registration_id")
    .notNull()
    .references(() => registrationsTable.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  description: text("description"),
  price: integer("price"),
  image_url: text("image_url"),
  createdAt: integer("createdAt")
    .notNull()
    .default(sql`(unixepoch())`),
});

export const eventsRelations = relations(eventsTable, ({ one, many }) => ({
  quota: one(quotasTable, {
    fields: [eventsTable.id],
    references: [quotasTable.event_id],
  }),
  promoCodes: many(promoCodesTable),
  registrations: many(registrationsTable),
}));

export const quotasRelations = relations(quotasTable, ({ one }) => ({
  event: one(eventsTable, {
    fields: [quotasTable.event_id],
    references: [eventsTable.id],
  }),
}));

export const promoCodesRelations = relations(promoCodesTable, ({ one }) => ({
  event: one(eventsTable, {
    fields: [promoCodesTable.event_id],
    references: [eventsTable.id],
  }),
}));

export const registrationsRelations = relations(
  registrationsTable,
  ({ one, many }) => ({
    event: one(eventsTable, {
      fields: [registrationsTable.event_id],
      references: [eventsTable.id],
    }),
    products: many(registrationProductsTable),
  }),
);

export const registrationProductsRelations = relations(
  registrationProductsTable,
  ({ one }) => ({
    registration: one(registrationsTable, {
      fields: [registrationProductsTable.registration_id],
      references: [registrationsTable.id],
    }),
  }),
);

export type User = typeof usersTable.$inferSelect;
export type Event = typeof eventsTable.$inferSelect;
export type Quota = typeof quotasTable.$inferSelect;
export type PromoCode = typeof promoCodesTable.$inferSelect;
export type Registration = typeof registrationsTable.$inferSelect;
export type RegistrationProduct = typeof registrationProductsTable.$inferSelect;
