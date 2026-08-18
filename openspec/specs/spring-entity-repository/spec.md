# Spring Entity & Repository Specification

| Field | Value |
|-------|--------|
| **Capability id** | `spring-entity-repository` |
| **Document type** | SDD data-model reference (not a request/response feature spec) |
| **Status** | As-built (haystack-side **read** copy of the Spring JPA schema) |
| **Module** | `heavy-rental-spring-rest-api` |
| **Packages** | `com.heavy_rental.rest_api.entity`, `com.heavy_rental.rest_api.repository`, `com.heavy_rental.rest_api.enums` |
| **Write source of truth** | Spring Boot repo (JPA entities + `application.properties`) — update this file in the same change set when haystack read models depend on a schema change |
| **Environment context** | [`../project-setup/spec.md`](../project-setup/spec.md) (read first) |
| **Related** | [`../domain/spec.md`](../domain/spec.md) · [`../domain-seed-data/spec.md`](../domain-seed-data/spec.md) · [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md) |
| **Related code** | 13 JPA entities, 12 Spring Data repositories, `enums.ConditionType` |
| **Legacy path** | `specification/SPEC-spring-entity-repository.md` (removed 2026-08-13) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD |

This document is the **haystack-side read reference** for the JPA data model: entities, columns, relationships, enums, and the Spring Data repositories built on top of them. It does not define REST endpoints — see §3.2. Spring-only companion SPECs named below (`SPEC-booking-delivery-return-api`, `SPEC-auth-login-logout`, `SPEC-seed-data`, `SPEC-api-index`) live in the Spring Boot repo and are **not** mirrored here.

---

## 1. Purpose

Capture the **current, as-built** persistence layer so later feature SDDs (bookings, assets, payments, AI recommendations, …) can:

1. Reuse existing entities/repositories instead of re-deriving field names and types from source.
2. Know which relationships exist, their direction, and their fetch strategy.
3. Know which repository query methods already exist vs. need to be added.
4. See known modeling quirks up front instead of rediscovering them mid-feature.

When this document and the codebase diverge, update them in the same change set.

---

## 2. Outcomes

When this spec is followed:

- New feature SDDs reference entity/repository names and fields correctly on the first pass.
- Nobody assumes a bidirectional/collection relationship (e.g. `asset.getImages()`) exists — none do; navigation from the "one" side goes through a repository `findByXId` call.
- Nobody assumes cascading deletes — none are configured; FK constraints are enforced at the database level with default (restrictive) delete behavior.

---

## 3. Scope

### 3.1 In scope

- All 13 entities under `entity/` and their column mappings.
- All 12 repositories under `repository/` and their derived query methods.
- The shared `ConditionType` enum and each entity's inline status/type enums.
- Relationship map (FK → referenced table) and schema lifecycle (`ddl-auto`).

### 3.2 Out of scope / not yet built

- **REST controllers, services, and DTOs for this data model — partially.** `User`/`UserRepository` are consumed by the auth flow (`CustomUserDetailsService`). `Payment` has a controller (`PaymentController`/`PaymentService`, merged via `HR-60`) that creates Stripe `PaymentIntent`s but does **not** use `PaymentRepository` — no `Payment` row is ever persisted by that flow; no feature spec covers it. `Booking` has a full read/update surface plus delivery/return status transitions — see [`SPEC-booking-delivery-return-api.md`](./SPEC-booking-delivery-return-api.md) for the contract, including why `DeliveryRecord`/`ReturnRecord` (§5.10/§5.11 below) are never created by that flow. The remaining entities/repositories (`AssetCategory`, `Asset`, `AssetImage`, `RentalPlan`, `RentalPlanRecord`, `AIRecommendation`, `RecommendationItem`) still compile and would create tables, but have **no controller, service, or DTO wired up** on this branch. Adding one is a new feature SDD.
- Database migrations (Flyway/Liquibase) — schema is Hibernate-generated only; see [`../project-setup/spec.md`](../project-setup/spec.md) §5.2.
- Validation annotations (Bean Validation) — none of these entities use `@NotNull`/`@Size`/etc.; the only enforced constraints are JPA `@Column(nullable=…)` / `unique=…`, which become DB-level `NOT NULL` / `UNIQUE` constraints.

---

## 4. Conventions shared across all entities

| Convention | Detail |
|---|---|
| Primary key | `Long id`, `@GeneratedValue(strategy = GenerationType.IDENTITY)` on every entity |
| Lombok | `@Getter @Setter @NoArgsConstructor @AllArgsConstructor` on every entity; `User` additionally has `@Builder` |
| Associations | **Unidirectional `@ManyToOne(fetch = FetchType.LAZY)` only.** No entity declares `@OneToMany`, `@OneToOne`, `@ManyToMany`, `mappedBy`, or `cascade`/`orphanRemoval`. To get "children" of a row (e.g. images of an `Asset`, items of a `Booking`), call the child repository's `findByXId(...)`, not object-graph navigation. |
| Enums | Persisted with `@Enumerated(EnumType.STRING)` — DB stores the enum name, not ordinal |
| Money fields | `BigDecimal` with `precision = 10, scale = 2` |
| Timestamps | `LocalDateTime` for instants (`createdAt`, `updatedAt`, `deliveredAt`, …), `LocalDate` for date-only fields (`startDate`, `endDate`) — none are DB-defaulted; the application must set them explicitly |
| Table naming | `@Table(name = "…")`, snake_case, matching the entity's plural/domain name |
| Schema lifecycle | `spring.jpa.hibernate.ddl-auto=update` — Hibernate creates/updates tables/constraints from these annotations at context startup and leaves them in place at shutdown. Schema persists between runs; see [`../project-setup/spec.md`](../project-setup/spec.md) §5.2 and [`SPEC-seed-data.md`](./SPEC-seed-data.md) (whose upsert-based seeding only makes sense against a persistent schema). |

---

## 5. Entity catalog

### 5.1 `User` → table `users`

Auth principal and the `customer` / `driver` side of most relationships below.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `name` | `name` | `String(100)` | `NOT NULL`, **`UNIQUE`** |
| `password` | `password` | `String` | `NOT NULL` (BCrypt hash) |
| `email` | `email` | `String(255)` | nullable (login principal — see [`SPEC-auth-login-logout.md`](./SPEC-auth-login-logout.md)) |
| `company` | `company` | `String(255)` | nullable |
| `role` | `role` | enum `UserRole` (`USER`, `ADMIN`, `DRIVER`) | `NOT NULL` |
| `enabled` | `enabled` | `boolean` | `NOT NULL`, defaults `true` via `@Builder.Default` |
| `createdAt` | `created_at` | `LocalDateTime` | nullable |

### 5.2 `AssetCategory` → table `asset_categories`

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `name` | `name` | `String(100)` | `NOT NULL`, **`UNIQUE`** |
| `description` | `description` | `String(255)` | nullable |

### 5.3 `Asset` → table `assets`

The rentable equipment item.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `name` | `name` | `String(100)` | `NOT NULL`, **`UNIQUE`** (unique across the whole fleet, not per category) |
| `serialno` | `serialno` | `String(255)` | `NOT NULL` |
| `category` | `category_id` | → `AssetCategory` | `NOT NULL`, `@ManyToOne` LAZY |
| `capacity` | `capacity` | `Integer` | nullable — `precision/scale` on `@Column` are declared but have no effect on an `Integer` column (only apply to decimal types); harmless but misleading metadata |
| `platformHeight` | `platform_height` | `BigDecimal(10,2)` | nullable |
| `description` | `description` | `String(255)` | nullable |
| `baseDailyRate` | `base_daily_rate` | `BigDecimal(10,2)` | `NOT NULL` |
| `minDailyRate` | `min_daily_rate` | `BigDecimal(10,2)` | `NOT NULL` |
| `maxDailyRate` | `max_daily_rate` | `BigDecimal(10,2)` | `NOT NULL` |
| `condition` | `condition` | enum `ConditionType` (shared, §6) | nullable |
| `lastConditionUpdatedAt` | `last_condition_updated_at` | `LocalDateTime` | nullable |
| `purchaseYear` | `purchase_year` | `Integer` | nullable |

### 5.4 `AssetImage` → table `asset_images`

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `asset` | `asset_id` | → `Asset` | `NOT NULL`, `@ManyToOne` LAZY |
| `image` | `image` (via default naming) |
| `uploadedAt` | `uploaded_at` | `LocalDateTime` | `NOT NULL` |

### 5.5 `RentalPlan` → table `rental_plan`

A draft/quote grouping of assets for a customer, prior to becoming a `Booking`.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `customer` | `customer_id` | → `User` | `NOT NULL`, `@ManyToOne` LAZY |
| `startDate` | `start_date` | `LocalDate` | nullable |
| `endDate` | `end_date` | `LocalDate` | nullable |
| `totalAmount` | `total_amount` | `BigDecimal` | nullable |
| `status` | `status` | enum `PlanStatus` (`DRAFT`, `SAVED`, `QUOTEED`, `CONVERTED`) | nullable — note: `QUOTEED` is the literal enum constant as defined (likely intended "QUOTED") |
| `siteAddress` | `site_address` | `String` | nullable |
| `sitePostalCode` | `site_postal_code` | `String` | nullable |
| `siteLatitude` | `site_latitude` | `BigDecimal` | nullable |
| `siteLongitude` | `site_longitude` | `BigDecimal` | nullable |
| `createdAt` | `created_at` | `LocalDateTime` | nullable |
| `updatedAt` | `updated_at` | `LocalDateTime` | nullable |

### 5.6 `RentalPlanRecord` → table `rental_plan_records`

Line item of a `RentalPlan` (one asset within the plan).

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `rentalPlan` | `rental_plan_id` | → `RentalPlan` | `@ManyToOne` LAZY, nullable FK |
| `asset` | `asset_id` | → `Asset` | `@ManyToOne` LAZY, nullable FK |
| `dailyRate` | `daily_rate` | `BigDecimal` | nullable |
| `subtotal` | `subtotal` | `BigDecimal` | nullable |

### 5.7 `Booking` → table `bookings`

A confirmed rental (converted from a `RentalPlan`, or created directly).

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `customer` | `customer_id` | → `User` | `@ManyToOne` LAZY, nullable FK |
| `rentalPlan` | `rental_plan_id` | → `RentalPlan` | `@ManyToOne` LAZY, nullable FK |
| `startDate` | `start_date` | `LocalDate` | nullable |
| `endDate` | `end_date` | `LocalDate` | nullable |
| `status` | `status` | enum `BookingStatus` (`PENDING_DEPOSIT`, `PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`, `COMPLETED`, `CANCELLED`) | nullable |
| `totalAmount` | `total_amount` | `BigDecimal` | nullable |
| `depositAmount` | `deposit_amount` | `BigDecimal` | nullable |
| `remainingBalance` | `remaining_balance` | `BigDecimal` | nullable |
| `siteAddress` | `site_address` | `String` | nullable |
| `sitePostalCode` | *(none — `@Formula`)* | `String` | Read-only, `@Setter(AccessLevel.NONE)`; computed as `substring(site_address from length(site_address) - 5 for 6)`, not a real column |
| `siteLatitude` | `site_latitude` | `BigDecimal` | nullable |
| `siteLongitude` | `site_longitude` | `BigDecimal` | nullable |
| `deliveryNotes` | `delivery_notes` | `String(500)` | nullable |
| `createdAt` | `created_at` | `LocalDateTime` | nullable |

### 5.8 `BookingItem` → table `booking_items`

Line item of a `Booking` (one asset within the booking), with condition tracking at handover/return.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `booking` | `booking_id` | → `Booking` | `@ManyToOne` LAZY, nullable FK |
| `asset` | `asset_id` | → `Asset` | `@ManyToOne` LAZY, nullable FK |
| `dailyRate` | `daily_rate` | `BigDecimal` | nullable |
| `subtotal` | `subtotal` | `BigDecimal` | nullable |
| `startEngineHours` | `start_engine_hours` | `BigDecimal` | nullable |
| `endEngineHours` | `end_engine_hours` | `BigDecimal` | nullable |
| `initialCondition` | `initial_condition` | enum `ConditionType` (shared, §6) | nullable |
| `returnCondition` | `return_condition` | enum `ConditionType` (shared, §6) | nullable |

### 5.9 `Payment` → table `payments`

Stripe-backed payment record against a `Booking`.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `booking` | `booking_id` | → `Booking` | `@ManyToOne` LAZY, nullable FK |
| `stripePaymentIntentId` | `stripe_payment_intent_id` | `String` | nullable |
| `stripeChargeId` | `stripe_charge_id` | `String` | nullable |
| `stripeCustomerId` | `stripe_customer_id` | `String` | nullable |
| `amount` | `amount` | `BigDecimal` | nullable |
| `paymentType` | `payment_type` | enum `PaymentType` (`DEPOSIT`, `BALANCE`, `FULL_PAYMENT`) | nullable |
| `status` | `status` | enum `PaymentStatus` (`PENDING`, `SUCCESS`, `FAIL`) | nullable |
| `failureReason` | `failure_reason` | `String` | nullable |
| `paidAt` | `paid_at` | `LocalDateTime` | nullable |
| `createdAt` | `created_at` | `LocalDateTime` | nullable |

### 5.10 `DeliveryRecord` → table `delivery_records`

Proof of delivery for a `Booking`, captured by a `User` with role `DRIVER`.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `booking` | `booking_id` | → `Booking` | `@ManyToOne` LAZY, nullable FK |
| `driver` | `driver_id` | → `User` | `@ManyToOne` LAZY, nullable FK |
| `deliveredAt` | `delivered_at` | `LocalDateTime` | nullable |
| `deliveryPhotos` | `delivery_photos` | `String` | nullable (URL/CSV — no `@ElementCollection`, single column) |
| `customerSignatureUrl` | `customer_signature_url` | `String` | nullable |

### 5.11 `ReturnRecord` → table `return_records`

Proof of return for a `Booking`, mirroring `DeliveryRecord`.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `booking` | `booking_id` | → `Booking` | `@ManyToOne` LAZY, nullable FK |
| `driver` | `driver_id` | → `User` | `@ManyToOne` LAZY, nullable FK |
| `returnedAt` | `returned_at` | `LocalDateTime` | nullable |
| `returnPhotos` | `return_photos` | `String` | nullable |
| `customerSignatureUrl` | `customer_signature_url` | `String` | nullable |

### 5.12 `AIRecommendation` → table `ai_recommendations`

An AI-generated asset recommendation for a `User`; supports a revision chain via a self-reference.

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `user` | `user_id` | → `User` | `@ManyToOne` LAZY, nullable FK |
| `confidenceScore` | `confidence_score` | `BigDecimal(10,2)` | nullable |
| `status` | `status` | enum `RecommendationStatus` (`GENERATED`, `ACCEPTED`, `REJECTED`, `EXPIRED`) | nullable |
| `previousRecommendation` | `previous_recommendation_id` | → `AIRecommendation` (self-referencing) | `@ManyToOne` LAZY, nullable FK |
| `rawProjectPrompt` | `raw_project_prompt` | `TEXT` | nullable |
| `documentUrl` | `document_url` | `String` | nullable |
| `aiReasoningSummary` | `ai_reasoning_summary` | `TEXT` | nullable |
| `createdAt` | `created_at` | `LocalDateTime` | `NOT NULL` |

### 5.13 `RecommendationItem` → table `recommendation_items`

Line item of an `AIRecommendation` (one suggested asset, ranked and scored).

| Field | Column | Type | Constraints |
|---|---|---|---|
| `id` | `id` | `Long` | PK, identity |
| `recommendation` | `recommendation_id` | → `AIRecommendation` | `@ManyToOne` LAZY, nullable FK |
| `asset` | `asset_id` | → `Asset` | `@ManyToOne` LAZY, nullable FK |
| `rankOrder` | `rank_order` | `Integer` | nullable |
| `matchScore` | `match_score` | `BigDecimal` | nullable |
| `mlPredictedPrice` | `ml_predicted_price` | `BigDecimal` | nullable |

---

## 6. Enums

### 6.1 Shared: `enums.ConditionType`

Used by `Asset.condition`, `BookingItem.initialCondition`, `BookingItem.returnCondition`.

`EXCELLENT`, `GOOD`, `FAIR`, `NEEDS_REPAIR`

### 6.2 Inline (nested) enums, one per owning entity

| Entity | Enum | Values |
|---|---|---|
| `User` | `UserRole` | `USER`, `ADMIN`, `DRIVER` |
| `RentalPlan` | `PlanStatus` | `DRAFT`, `SAVED`, `QUOTEED`, `CONVERTED` |
| `Booking` | `BookingStatus` | `PENDING_DEPOSIT`, `PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`, `COMPLETED`, `CANCELLED` |
| `Payment` | `PaymentType` | `DEPOSIT`, `BALANCE`, `FULL_PAYMENT` |
| `Payment` | `PaymentStatus` | `PENDING`, `SUCCESS`, `FAIL` |
| `AIRecommendation` | `RecommendationStatus` | `GENERATED`, `ACCEPTED`, `REJECTED`, `EXPIRED` |

All persisted as `EnumType.STRING`.

---

## 7. Relationship map (foreign keys)

Every association below is a **unidirectional `@ManyToOne`** declared on the "many" side; the referenced ("one") entity has no back-reference. Read as *child table.column → parent table*.

| Child table | FK column | → Parent table |
|---|---|---|
| `assets` | `category_id` | `asset_categories` |
| `asset_images` | `asset_id` | `assets` |
| `rental_plan` | `customer_id` | `users` |
| `rental_plan_records` | `rental_plan_id` | `rental_plan` |
| `rental_plan_records` | `asset_id` | `assets` |
| `bookings` | `customer_id` | `users` |
| `bookings` | `rental_plan_id` | `rental_plan` |
| `booking_items` | `booking_id` | `bookings` |
| `booking_items` | `asset_id` | `assets` |
| `payments` | `booking_id` | `bookings` |
| `delivery_records` | `booking_id` | `bookings` |
| `delivery_records` | `driver_id` | `users` |
| `return_records` | `booking_id` | `bookings` |
| `return_records` | `driver_id` | `users` |
| `ai_recommendations` | `user_id` | `users` |
| `ai_recommendations` | `previous_recommendation_id` | `ai_recommendations` (self) |
| `recommendation_items` | `recommendation_id` | `ai_recommendations` |
| `recommendation_items` | `asset_id` | `assets` |

```text
users ──┬── rental_plan ──── rental_plan_records ──── assets ──── asset_categories
        │        │                                       │
        ├── bookings ──┬── booking_items ─────────────────┘
        │        │     ├── payments
        │        │     ├── delivery_records ── (driver) users
        │        │     └── return_records   ── (driver) users
        │        │
        └── ai_recommendations ──┬── recommendation_items ── assets
                 │(self: previous_recommendation_id)
                 └───────────────┘
```

No cascade is configured on any `@ManyToOne`. Because Hibernate generates the schema (`ddl-auto=update`) without an explicit `onDelete` rule, the database default (restrict) applies: deleting a parent row (e.g. a `Booking`) while child rows (e.g. `booking_items`, `payments`) still reference it will fail with a foreign-key violation. Children must be deleted first, or deletion logic must be added in a service layer — none exists today.

---

## 8. Repository catalog

All repositories are plain `interface X extends JpaRepository<Entity, Long>` — each gets the full `JpaRepository` surface (`save`, `saveAll`, `findById`, `findAll`, `count`, `deleteById`, `delete`, `existsById`, …) for free. Only **derived query methods added on top** are listed below.

| Repository | Entity | Custom query methods |
|---|---|---|
| `UserRepository` | `User` | `List<User> findByRole(UserRole role)` · `Optional<User> findByEmail(String email)` · `boolean existsByEmail(String email)` |
| `AssetCategoryRepository` | `AssetCategory` | `AssetCategory findByName(String name)` — ⚠️ returns the raw entity (not `Optional`); `null` if no match, unlike every other `findByX` in this codebase |
| `AssetRepository` | `Asset` | `List<Asset> findByCategoryId(Long categoryId)` · `List<Asset> findByNameContainingIgnoreCase(String name)` · `List<Asset> findByCondition(ConditionType condition)` |
| `AssetImageRepository` | `AssetImage` | `List<AssetImage> findByAssetId(Long assetId)` |
| `RentalPlanRepository` | `RentalPlan` | `List<RentalPlan> findByCustomerId(Long customerId)` · `List<RentalPlan> findByStatus(PlanStatus status)` |
| `RentalPlanRecordRepository` | `RentalPlanRecord` | `List<RentalPlanRecord> findByRentalPlanId(Long rentalPlanId)` |
| `BookingRepository` | `Booking` | `List<Booking> findByCustomerId(Long customerId)` · `List<Booking> findByStatus(BookingStatus status)` · `List<Booking> findByCustomerIdAndStatus(Long customerId, BookingStatus status)` · `List<Booking> findByStartDateAndStatusIn(LocalDate startDate, List<BookingStatus> statuses)` · `List<Booking> findByEndDateAndStatusIn(LocalDate endDate, List<BookingStatus> statuses)` — ⚠️ `findByCustomerId`/`findByCustomerIdAndStatus` exist but are unused by any controller today; see [`SPEC-booking-delivery-return-api.md`](./SPEC-booking-delivery-return-api.md) §6.1 |
| `BookingItemRepository` | `BookingItem` | `List<BookingItem> findByBookingId(Long bookingId)` · `List<BookingItem> findByAssetId(Long assetId)` |
| `PaymentRepository` | `Payment` | `List<Payment> findByBookingId(Long bookingId)` · `List<Payment> findByStatus(PaymentStatus status)` — ⚠️ unused; no feature spec covers `PaymentController` (§3.2 above) |
| `DeliveryRecordRepository` | `DeliveryRecord` | `List<DeliveryRecord> findByBookingId(Long bookingId)` · `List<DeliveryRecord> findByDriverId(Long driverId)` — ⚠️ unused; see [`SPEC-booking-delivery-return-api.md`](./SPEC-booking-delivery-return-api.md) §6.3 |
| `ReturnRecordRepository` | `ReturnRecord` | `List<ReturnRecord> findByBookingId(Long bookingId)` · `List<ReturnRecord> findByDriverId(Long driverId)` — ⚠️ unused, same reason as `DeliveryRecordRepository` |
| `AIRecommendationRepository` | `AIRecommendation` | `List<AIRecommendation> findByUserId(Long userId)` · `List<AIRecommendation> findByStatus(RecommendationStatus status)` |
| `RecommendationItemRepository` | `RecommendationItem` | `List<RecommendationItem> findByRecommendationId(Long recommendationId)` |

None of these repositories currently define a `Pageable`/`Sort` variant, a `@Query`, or a projection — every method returns a full-entity `List<T>` (or `Optional<T>` / raw `T` for single lookups). None are `@Transactional` beyond Spring Data's defaults.

---

## 9. Unique constraints summary

| Table | Column | Effect |
|---|---|---|
| `users` | `name` | One row per display name; **not** the login field (login uses `email`, unconstrained — see [`SPEC-auth-login-logout.md`](./SPEC-auth-login-logout.md)) |
| `asset_categories` | `name` | One category per name |
| `assets` | `name` | One asset per name, fleet-wide (not scoped per category) |

No other table declares a unique or composite-unique constraint (e.g. nothing prevents two `BookingItem` rows for the same `booking_id` + `asset_id`, or two `Payment` rows with the same `stripe_payment_intent_id`).

---

## 10. Design notes (as-built quirks)

1. **Read-only from the "one" side.** Since no `@OneToMany` exists, code must call e.g. `bookingItemRepository.findByBookingId(id)` to get a booking's items — `booking.getItems()` does not exist and never will unless a future SDD adds it.
2. **No cascading deletes.** Deleting a `User`, `Asset`, `Booking`, etc. that still has dependent rows will hit a DB FK violation, not a JPA cascade. This must be handled explicitly once delete endpoints are built.
3. **`Asset.capacity` has dead `precision`/`scale` metadata** — it's an `Integer` field annotated as if it were a `BigDecimal`; Hibernate ignores those attributes for integer columns.
4. **`RentalPlan.PlanStatus.QUOTEED`** is the literal enum constant in code (likely meant "QUOTED"). Any future DTO/API mapping to this enum should use the value as spelled unless a dedicated change renames it.
5. **`AssetCategoryRepository.findByName` breaks the `Optional` convention** used everywhere else in this codebase (e.g. `UserRepository.findByEmail`); callers must null-check instead of using `Optional` idioms.
6. **Schema is persistent, not ephemeral.** `ddl-auto=update` means Hibernate creates missing tables/columns at startup but never drops or truncates existing ones — data survives across app/test-context restarts against the same Postgres instance (see [`../project-setup/spec.md`](../project-setup/spec.md) §5.2). This is why `SPEC-seed-data.md`'s `data.sql` needs `ON CONFLICT` upserts: it reruns against a database that already has last run's rows in it, not a fresh one.
7. **`User`, `Payment`, and `Booking` are wired to a controller today; the rest are not.** `Payment` has a live but unspecified route (`PaymentController`, merged on `develop` before this branch — §3.2 above). `Booking` has a full contract in [`SPEC-booking-delivery-return-api.md`](./SPEC-booking-delivery-return-api.md), including why it doesn't fully exercise its own data model (`DeliveryRecord`/`ReturnRecord` never created — that spec's §6.3). `AssetCategory`, `Asset`, `AssetImage`, `RentalPlan`, `RentalPlanRecord`, `AIRecommendation`, and `RecommendationItem` remain a data-model foundation for future feature SDDs, not yet a working API surface on this branch.

---

## 11. Verification

### 11.1 Checklist

- [ ] `./mvnw clean install` from `heavy-rental-spring-rest-api/` builds and the Hibernate DDL log (`alter table … add constraint … foreign key …`) matches §7.
- [ ] `RestApiApplicationTests` context loads (confirms all entity mappings are valid).
- [ ] Each repository resolves without a missing-method error at startup (Spring Data validates derived query methods against entity fields at context refresh).

### 11.2 Inspecting the generated schema

The schema persists across runs (`ddl-auto=update`) but is still easiest to inspect while the app or a test context is up:

```bash
cd heavy-rental-spring-rest-api
./mvnw spring-boot:run
# in another shell, with psql available on the network:
psql -h db -U postgres -d postgres -c '\dt'
psql -h db -U postgres -d postgres -c '\d bookings'
```

Or read the Hibernate DDL directly from build/test output (`spring.jpa.show-sql=true` is on by default in `application.properties`).

---

## 12. Key decisions

| Decision | Rationale |
|---|---|
| `IDENTITY` generation for all PKs | Matches PostgreSQL `SERIAL`/`BIGSERIAL`-style auto-increment; simplest cross-entity consistency |
| Unidirectional `@ManyToOne` only, no `@OneToMany` | Keeps entities simple and avoids N+1/lazy-init pitfalls from collection mappings until an actual feature needs child-collection navigation |
| `LAZY` fetch on every association | Avoids unintentionally loading full object graphs (e.g. loading a `Booking` shouldn't pull its `Customer`, `RentalPlan`) |
| `EnumType.STRING` for all enums | Human-readable DB values; safe to reorder enum constants later without corrupting stored data |
| No cascade/orphanRemoval | Deletion semantics are deliberately left to a future service-layer decision per entity, not implied by the mapping |

---

## 13. Change control

| Version | Date | Notes |
|---------|------|--------|
| 1.0.0 | 2026-08-04 | Initial as-built data-model spec: 13 entities, 12 repositories, shared `ConditionType` enum, relationship map, unique constraints, and known modeling quirks |
| 1.1.0 | 2026-08-09 | Corrected claims left stale by two changes this doc was never updated alongside: (1) `HR-77` (already on `develop`) split `Booking.BookingStatus.PENDING` into `PENDING_DEPOSIT`/`PENDING_CONFIRMED`, removed `Booking.PaidStatus`/`paidStatus` entirely, and changed `sitePostalCode` to a computed `@Formula` — §5.7/§6.2/§8 updated to match. (2) This branch (`HR-80`) wired `Booking` to `BookingController`/`DeliveryController`/`ReturnController`, and `Payment` turned out to already be wired via `PaymentController` since `HR-60` without this doc ever reflecting it — §3.2/§8/§10 updated, and gaps in both flows (no `Payment`/`DeliveryRecord`/`ReturnRecord` persistence, no customer-scoping on `BookingController`'s reads despite `BookingRepository` already having the query methods for it) called out inline. Also fixed a long-standing, unrelated error: this doc said `ddl-auto=create-drop` in four places; the project has run `ddl-auto=update` since `SPEC-seed-data.md` was written (confirmed against `application.properties`) — §4/§7/§10/§11.2 corrected. New companion index: [`SPEC-api-index.md`](./SPEC-api-index.md), which lists every route (including these) with client ownership and branch status. No entity/repository/relationship content changed beyond what's listed above — per this doc's own convention of updating alongside code changes it diverged from. |
| 1.3.0 | 2026-08-13 | Moved from `specification/SPEC-spring-entity-repository.md` into OpenSpec. Spring remains write-SoT; this file is the haystack read reference. Environment links now point at `openspec/specs/project-setup/`. |
| 1.2.0 | 2026-08-09 | Trimmed the `Booking`/`Payment` REST-layer commentary added in 1.1.0 (§3.2, §8's `BookingRepository`/`DeliveryRecordRepository`/`ReturnRecordRepository` rows, §10.7) down to short pointers now that [`SPEC-booking-delivery-return-api.md`](./SPEC-booking-delivery-return-api.md) exists as the actual contract for those routes — full behavioral detail (reproduction steps, recommended fixes) lives there now, not here. This doc's job stays data-model reference only, per its own stated scope (§ purpose: "does not define REST endpoints"). No entity/repository/relationship facts changed. |
