# Протокол пилота R1

Для adoption gate нужны пять новых пользователей из трёх внешних команд. Одна команда
ведёт три проекта силами одного QA, одна выполняет live selective launch в TestOps, а
минимум два человека независимо воспроизводят frozen demo. Приглашения, credentials и
внешние сообщения организует product owner вне автоматизации.

Каждый участник начинает с одного candidate wheel digest и пустой рабочей директории.
Нужно записать согласие, псевдонимы участника и команды, версии OS/Python/browser,
время начала и конца, подсказки, exit codes и run IDs. В публичном receipt нельзя
сохранять credentials, production URLs, raw screenshots или персональные данные.

Задачи сессии:

1. Установить wheel и Chromium; выполнить `testence doctor --json`.
2. Выполнить `testence demo run --project testence-demo --json` и объяснить причину
   failure второго case.
3. Установить один agent client и проверить managed skill files.
4. Добавить второй сценарий с requirement claim и независимым oracle.
5. Проверить run и объяснить один actionable result без помощи автора.
6. Для назначенных команд применить quality pack к трём репозиториям либо выполнить
   TestOps selection/upload flow.
7. Вернуться на следующей календарной неделе и повторить один полезный run.

Приёмка: 4/5 пользователей получают trustworthy proof не более чем за 15 минут,
минимум 2/3 команд самостоятельно добавляют второй сценарий, специальные командные
задачи завершены, есть два независимых воспроизведения и week return. В итог входят
setup minutes, QA review/triage minutes, accepted scenarios, gaps и overrides. Неудачная
или прерванная сессия остаётся в denominator.

Для каждого sanitized receipt используется `docs/pilot/session-template.json`. Итог
пилота указывает candidate digest и digests всех receipts; пустые или выполненные
автором шаблоны не закрывают G7.
