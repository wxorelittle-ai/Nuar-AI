-- ── РестоПульс · схема PostgreSQL ────────────────────────────────────
-- Хранит недельные снимки метрик конкурентов. На истории снимков строятся
-- недельные сравнения и (в перспективе) графики динамики.
--
-- Персональных данных гостей Nuar здесь НЕТ — только открытые данные о
-- заведениях-конкурентах (соответствие 152-ФЗ на Этапе 1).

CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    competitor_name TEXT        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    -- Полный снимок по всем источникам в JSON (см. CompetitorSnapshot.to_dict)
    payload         JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Быстрый доступ к «последнему снимку конкурента перед датой X»
CREATE INDEX IF NOT EXISTS idx_snapshots_name_time
    ON competitor_snapshots (competitor_name, collected_at DESC);

-- ── История отправленных дайджестов (аудит) ──────────────────────────
CREATE TABLE IF NOT EXISTS digests (
    id           BIGSERIAL PRIMARY KEY,
    week_label   TEXT        NOT NULL,
    body         TEXT        NOT NULL,   -- отрендеренный текст дайджеста
    sent_ok      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Настройки приложения (ключ-значение): AI-провайдеры, каналы соцсетей.
-- Секреты хранятся здесь, на сервере в РФ (152-ФЗ). Наружу не отдаются.
CREATE TABLE IF NOT EXISTS app_settings (
    key          TEXT        PRIMARY KEY,
    value        JSONB       NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Контент-очередь: черновики, запланированные и опубликованные посты.
CREATE TABLE IF NOT EXISTS content_posts (
    id           TEXT        PRIMARY KEY,
    data         JSONB       NOT NULL,   -- полный пост (см. Post.to_dict)
    created_at   TEXT        NOT NULL DEFAULT ''  -- ISO-строка для сортировки
);
CREATE INDEX IF NOT EXISTS idx_content_created ON content_posts (created_at DESC);

-- ── Гостевая база (VIP CRM). ПДн гостей — на сервере в РФ (152-ФЗ).
CREATE TABLE IF NOT EXISTS crm_guests (
    id           TEXT        PRIMARY KEY,
    data         JSONB       NOT NULL,   -- полный гость (см. Guest.to_dict)
    created_at   TEXT        NOT NULL DEFAULT ''
);
