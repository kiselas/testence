# ADR-0021: Изолированный runtime и владение ресурсами

Статус: принято. Дата: 2026-09-06.

## Контекст

Session-scoped browser context переносил cookies, storage, pages и role state между
тестами. Сохранение локально запущенного browser после failure также оставляло
принадлежащий runner процесс в CI. Worker-specific ports не дают изоляцию тестов.

## Рассмотренные варианты

1. Оставить session context и поручить каждому проекту полностью очищать его.
2. Запускать новый browser для каждого теста во всех режимах.
3. Сделать isolated режимом по умолчанию, сохранять browser только в явном warm,
   заменять его собственный context между тестами, а CDP attach считать чужим ресурсом.

## Решение

Выбран вариант 3. Stateful pytest fixtures имеют function scope. Isolated run создаёт
и закрывает собственный browser для каждого теста, включая failures. Warm authoring
сохраняет один собственный browser, но заменяет context до auth каждого теста. Attached
authoring заимствует context и не закрывает или заменяет его. Seed marker связывает
project, run, worker, case, role и attempt; cleanup адаптера — видимый lifecycle step.

## Последствия

CI платит стоимость browser startup за строгую границу по умолчанию. Команда может
измерить и явно выбрать warm без изменения proof scope. Для старых custom engines без
`reset_session` действует compatibility path с очисткой taps; для заявления warm
isolation нужна миграция. Browser manifest показывает mode и ownership.

## Tripwire

Решение пересматривается, если измерение покажет несовместимость isolated startup с
принятым CI budget. Оптимизация обязана сохранить fresh cookies/storage/auth и cleanup
принадлежащего runner процесса.
