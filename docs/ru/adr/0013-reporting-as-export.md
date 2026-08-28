# ADR-0013: Reporting integrations как exporters поверх ledger

Статус: accepted (2026-08-27)

## Контекст

`run.jsonl` уже записывает tests, вложенные steps с intent, oracles и evidence packs.
Добавление reporter SDK в test code создало бы второй источник истины и связало runner
с каждой reporting platform.

## Решение

`run.jsonl` — единственный источник истины. Reporting systems являются
детерминированными sinks:

```text
versioned ledger -> parsed run model -> HTML / Allure / CTRF / future exporters
```

Exporter предоставляет `name` и
`export(run, out_dir) -> list[Path]`. Встроенные реализации используют только stdlib
и загружаются lazily; third-party exporters регистрируются через entry-point group
`testence.exporters`. JUnit XML остаётся ответственностью pytest.

Golden tests фиксируют output встроенных exporters на уровне bytes. Exporter, которому
нужен client SDK, должен находиться в отдельном distribution, чтобы startup и
dependencies core не менялись.

## Последствия

Тесты не содержат reporting calls. Intent strings DSL становятся step names, markers —
tags, evidence-pack files — attachments. Allure и CTRF являются compatibility surfaces,
а не внутренней data model. OpenTelemetry и service-side reporters добавляются без
изменения execution.

## Tripwire

Если exporter нужны отсутствующие данные, расширяется append-only evidence schema, а не
instrumentation тестового кода. Повторяющийся upstream format drift должен привести к
явному version pinning или deprecation.
