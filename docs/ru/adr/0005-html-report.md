# ADR-0005: Автономный single-file HTML report

Статус: accepted (2026-08-25)

## Контекст

Люди — второй first-class читатель. Тестировщик не доверяет verdict, который нельзя
проверить. Reports должны быть прозрачны и работать там, где происходят запуски:
локальная машина, browser артефактов GitLab CI, общий каталог — всё offline.

## Сравнение вариантов

| | Single-file static HTML | Served SPA | Только Allure report |
|---|---|---|---|
| Открывается из file:// и CI artifacts | да | нет, нужен process | нужен `allure serve` или TestOps |
| Zero-install для reviewer | да | нет | нет |
| Собственный drill-down verdict→evidence | да | да | нет |
| Brandable для OSS | да | да | нет |
| Стоимость реализации | низкая | высокая | отсутствует |

## Решение

Один HTML-файл рендерится из run.jsonl командой `testence report <run-dir>`: без
external assets и CDN, vanilla JS, light/dark через `prefers-color-scheme`. Это
представление того же ledger, который читает агент, но не второй источник истины.
Allure остаётся export для существующих pipelines.

Измеримые требования: работает offline; не более 5 MB для 20-case run; render не более
2 секунд; click depth от verdict до raw evidence не более 3
(`report_click_depth`).

## Последствия

- Report автоматически поставляется с каждым run; красный CI job несёт собственное
  объяснение как artifact.
- Screenshots и packs остаются соседними файлами, а не встраиваются, чтобы соблюдать
  size budget; report корректно деградирует при переносе без них.
- Hooks для theming/i18n находятся в CSS variables с первого дня.

## Tripwire

Нарушение любого требования на реальных runs — больше 5 MB, больше 2 секунд или depth
больше 3 — требует пересмотра архитектуры report через sharding/lazy assets, а не
небольшого дополнительного сжатия.
