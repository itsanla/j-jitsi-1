CREATE TABLE `Event` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`slug` text NOT NULL,
	`title` text NOT NULL,
	`emoji` text NOT NULL,
	`target` text NOT NULL,
	`description` text NOT NULL,
	`benefits` text NOT NULL,
	`image_url` text,
	`normal_price` integer NOT NULL,
	`event_price` integer NOT NULL,
	`is_active` integer DEFAULT 1 NOT NULL,
	`createdAt` integer DEFAULT (unixepoch()) NOT NULL,
	`updatedAt` integer DEFAULT (unixepoch()) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `Event_slug_unique` ON `Event` (`slug`);--> statement-breakpoint
CREATE TABLE `PromoCode` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`event_id` integer,
	`code` text NOT NULL,
	`description` text,
	`discount_type` text NOT NULL,
	`discount_value` integer DEFAULT 0 NOT NULL,
	`max_uses` integer,
	`current_uses` integer DEFAULT 0 NOT NULL,
	`valid_until` integer,
	`is_active` integer DEFAULT 1 NOT NULL,
	`createdAt` integer DEFAULT (unixepoch()) NOT NULL,
	`updatedAt` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`event_id`) REFERENCES `Event`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `PromoCode_code_unique` ON `PromoCode` (`code`);--> statement-breakpoint
CREATE TABLE `Quota` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`event_id` integer NOT NULL,
	`total_slots` integer DEFAULT 0 NOT NULL,
	`remaining_slots` integer DEFAULT 0 NOT NULL,
	`updatedAt` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`event_id`) REFERENCES `Event`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `Quota_event_id_unique` ON `Quota` (`event_id`);--> statement-breakpoint
CREATE TABLE `RegistrationProduct` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`registration_id` integer NOT NULL,
	`name` text NOT NULL,
	`description` text,
	`price` integer,
	`image_url` text,
	`createdAt` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`registration_id`) REFERENCES `Registration`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `Registration` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`event_id` integer NOT NULL,
	`promo_code` text,
	`initial_price` integer NOT NULL,
	`final_price` integer NOT NULL,
	`status` text DEFAULT 'pending_form' NOT NULL,
	`customer_name` text NOT NULL,
	`customer_whatsapp` text NOT NULL,
	`customer_email` text,
	`customer_city` text,
	`business_name` text,
	`business_type` text,
	`business_description` text,
	`business_address` text,
	`business_hours` text,
	`business_phone` text,
	`business_instagram` text,
	`business_facebook` text,
	`business_maps_url` text,
	`notes` text,
	`createdAt` integer DEFAULT (unixepoch()) NOT NULL,
	`updatedAt` integer DEFAULT (unixepoch()) NOT NULL,
	FOREIGN KEY (`event_id`) REFERENCES `Event`(`id`) ON UPDATE no action ON DELETE restrict
);
--> statement-breakpoint
CREATE TABLE `User` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`username` text NOT NULL,
	`password` text NOT NULL,
	`role` text DEFAULT 'admin' NOT NULL,
	`createdAt` integer DEFAULT (unixepoch()) NOT NULL,
	`updatedAt` integer DEFAULT (unixepoch()) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `User_username_unique` ON `User` (`username`);