# Changelog

All notable changes to gorm-expert-skill are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.4.0] - 2026-03-15

### Changed
- SKILL.md slimmed from 805 → ~500 lines; detailed content moved to references/
- description shortened to 12 lines; removed imperative trigger language
- Section subsection numbers corrected (13.x was mislabeled as 14.x)
- Replaced 必须/强制 phrasing in references with softer 建议/应该/需

### Added
- `assets/dbcore/auto_id.go` — snowflake ID implementation for BaseModel
- `references/README.md` — indexed guide to all 15 reference documents
- `CHANGELOG.md` — this file

### Fixed
- `analyze_gorm.py` R18a/R18b labels were both named "R18"; now clearly distinguished
- `assets/dbcore/example_order_model.go` — added `//go:build ignore` and fixed import placeholder
- `references/migration.md` — added safety warnings before raw DDL CLI commands

### Security
- `SKILL.md` frontmatter now declares `compatibility` block (runtime, binaries, no_credentials, disk_access)
- Script table annotated with 🔍 read-only / 📝 write-on-explicit-flag permissions

---

## [1.3.1] - 2026-03-15

### Security (ClawHub audit fix)
- Added `compatibility` block to SKILL.md frontmatter declaring python >= 3.8, no credentials
- Annotated `disk_access.read_only` (6 scripts) vs `write_on_explicit_flag` (2 scripts)
- Added security docstrings to `bench_template.py` and `init_project.py`
- Script table now shows 🔍/📝 permission icons

---

## [1.3.0] - 2026-03-15

### Added — GORM v2 Specific Features
- `references/session.md` — Session mechanism, goroutine safety, 8 common traps
- `references/clause.md` — Clause system (FOR UPDATE / SKIP LOCKED / Upsert / RETURNING / custom)
- `references/association.md` — Association ops (Preload/Joins/Append/Replace/Select+Omit)
- `references/serializer.md` — Serializer (json/gob/unixtime) and custom data types
- `references/raw-sql.md` — First/Take/Find behavior diff table, v2 error handling

### Added — analyze_gorm.py
- R19: goroutine unsafe *gorm.DB sharing (WARN)
- R20: *gorm.DB condition accumulation without Session (INFO)
- R21: v1 gorm.IsRecordNotFoundError usage (ERROR)

### Fixed
- R19–R21 were dead code (placed after `return issues`); now correctly inside function

---

## [1.2.1] - 2026-03-15

### Added
- `assets/dbcore/example_order_model.go` — complete OrderModel demo
- `scripts/init_project.py --example` flag to generate the demo file

---

## [1.2.0] - 2026-03-15

### Added
- `scripts/init_project.py` — scaffold dbcore package into target project
- `assets/dbcore/` — base_model.go, query_builder.go, transaction.go (production-ready, bug-fixed)
- SKILL.md section 0 "Project Init"

---

## [1.1.1] - 2026-03-15

### Added
- `references/base-model-pattern.md` — BaseModel design rules and bug fixes (312 lines)

### Fixed
- `query_builder.go` InStrings/InInts args ordering bug
- `order.go` soft-delete + unique index conflict
- `base_model.go` Find→Take, ListAll soft limit, Page dedup, PageAfter cursor pagination

---

## [1.1.0] - 2026-03-15

### Added
- SKILL.md sections: Scopes/multi-tenant, Cache-Aside integration
- `scripts/scope_gen.py` — auto-generate Scope functions
- `scripts/gen_model.py --dialect pg` — PostgreSQL type support
- `scripts/pool_advisor.py` — health check code output
- `references/scopes.md`, `references/caching.md`
- analyze_gorm.py refactored to dual-loop architecture

---

## [1.0.2] - 2026-03-15

### Added
- SKILL.md sections: Sharding, Observability
- analyze_gorm.py R11–R18 rules
- `references/sharding.md`, `references/observability.md`

---

## [1.0.1] - 2026-03-15

### Fixed
- description: removed 必须触发/不得跳过 language to pass ClawHub security scan

---

## [1.0.0] - 2026-03-15

### Added
- Initial release: SKILL.md with 9 sections, 6 scripts, 6 reference docs
