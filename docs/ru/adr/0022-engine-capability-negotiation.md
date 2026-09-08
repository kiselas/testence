# ADR-0022: Согласование возможностей engine

Статус: принято. Дата: 2026-09-06.

## Контекст

Исходный Engine protocol смешивал platform-neutral lifecycle/evidence со всеми DOM/CDP
операциями. Fake или будущий native adapter должен был притворяться browser engine либо
падал поздно. Несколько observation helpers также молча выбирали `.first`, поэтому
неоднозначный target мог выглядеть healthy.

## Рассмотренные варианты

1. Оставить один protocol и документировать unsupported methods.
2. Определять поддержку через `hasattr` в месте вызова.
3. Опубликовать versioned capabilities и малые structural protocols, связать требования
   с PlanSpec и отвергать неподдерживаемую операцию до silent skip/green.

## Решение

Выбран вариант 3. Capability document — сортированные schema-validated данные. Plan
scenario объявляет требования, pytest проверяет их на collection. DSL применяет тот же
контракт и возвращает `UnsupportedCapability`. Playwright реализует web matrix R1;
platform-neutral fake требует только lifecycle и evidence. Locator observations strict,
а явный fast actionability записывается в evidence и снижает assurance.

## Последствия

Adapters не используют Playwright types. Старые composite engines временно работают с
предполагаемой legacy web support, но это не conformance certificate. Новая capability
требует изменения schema, implementation fixture и compatibility decision.

## Tripwire

Capability разделяется или версионируется, если два backend придают одному имени
существенно разную семантику. Нельзя расширять declaration только для обхода preflight.
