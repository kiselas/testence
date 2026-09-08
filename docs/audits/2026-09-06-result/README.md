# Аудит текущего результата Testence R1

Дата: 6 сентября 2026. Версия продукта: `0.1.0.dev0`.
Объект: рабочее дерево поверх `7be8d025f81d9116ab267c59d440e14b377cfce7`, включая незакоммиченные изменения.
Нормативная база: [R1 v1.0](../2026-09-06/release-spec.md), [уточнение v1.1](../2026-09-06-followup/release-spec.md), [T01–T29](../2026-09-06-followup/backlog.md).

## Решение

**R1 не завершён; текущий результат — инженерный pre-alpha. Решение `no-go` остаётся правильным.**

Реализован существенный объём: lifecycle/identity и reconciliation, отдельный assurance, bound verdicts, expected-state oracle, изоляция runtime, capabilities, Allure/CTRF, selective execution, CLI, quality packs и установка skills. Есть реальные локальные browser/agent/consumer receipts. Переписывание ядра для продолжения не требуется.

Однако оставшаяся работа **не ограничивается внешними подтверждениями, видео и публикацией**. В этом аудите воспроизведены запись вне project root, восстановление повреждённой policy с успешным статусом, принятие фиктивного corpus acceptance и успешный smoke для файла, который вообще не является wheel. Есть незавершённые локальные критерии demo, измерений и release validation.

Прежние формулировки «local implementation passed/complete» для T21, T23–T26 нельзя трактовать как полную приёмку этих задач. Наличие файлов и зелёные штатные тесты не проверяют часть обещанных свойств.

## Метод и ограничения

Проверены код и локальные receipts перечисленных подсистем, CI, упаковка, corpus registry, release manifest и соответствие ТЗ. Дополнительно выполнены штатные проверки и независимые отрицательные пробы. Пробы изменяли только созданные для аудита fixtures; продуктовый код, старые receipts и release decision не исправлялись.

Основные материалы: [машинные пробы](../../../outputs/audit-2026-09-06-result/probe-results.json), [rollback/manifest/provenance](../../../outputs/audit-2026-09-06-result/integrity-results.json), [smoke фиктивного wheel](../../../outputs/audit-2026-09-06-result/wrong-wheel-smoke.json). Скрипты воспроизведения сохранены рядом.

Это локальный аудит Windows, а не независимая сертификация безопасности. Hosted CI, Linux, live TestOps, внешние пилоты и полный повтор браузерного mutation corpus здесь не выполнялись. Старые результаты minimum-deps и real-agent запусков изучены как исторические receipts, не выданы за новые измерения.

## Подтверждённые находки

Приоритет P1 означает исправление до приёмки соответствующего release gate; P2 — обязательную доработку полноты R1. P0-инцидент с реальной утечкой этим аудитом не установлен.

### A01 · P1 · Инициализация и installer обходят project containment через junction

**Код:** `src/testence/agent/install.py:59,75,188`; `src/testence/application.py:32,165`.

Skills destinations проверяются через `resolve`, но `.testence/agents.json` пишется через `_state_path` без проверки containment. Scaffold также формирует пути под `.testence` без проверки конечного расположения.

**Воспроизведение:** в двух пустых проектах `.testence` сделан junction на соседний каталог. `install_skills` вернул `installed` и создал снаружи `agents.json`; `init_project` успешно создал снаружи пять scaffold-файлов, включая Python examples и manifest. Оба соседних каталога принадлежат аудиту; чужие данные не затронуты.

**Последствие:** обычная разрешённая команда изменяет файлы за пределами указанного проекта. Это не sandbox для произвольного Python, но обещанный path boundary самих команд нарушен.

**Приёмка исправления:** проверить все целевые paths и служебные state/history/temp paths до первой записи; при escape отклонить команду без частичного изменения. Добавить Windows junction и Linux symlink regression. Проверить ту же схему для quality state и doctor. T11/T18/T22, G2/G5.

### A02 · P1 · Rollback восстанавливает неподтверждённые байты как принятый digest

**Код:** `src/testence/quality.py:274–325`, особенно запись snapshot на строке 309.

Rollback проверяет текущие файлы на конфликт, но не проверяет содержимое архивного snapshot по `sha256` из archived lock до восстановления.

**Воспроизведение:** применены pack v1 и v2; в истории v1 изменён `policy.json`; rollback v1 вернул `rolled_back` и восстановил строку `CORRUPTED HISTORY BY AUDIT`. В восстановленном lock остался исходный SHA-256, не совпадающий с реальным файлом. `hash_mismatch=true` сохранён в receipt.

**Последствие:** случайно повреждённая или изменённая история становится активной policy, а pinned digest ошибочно обозначает её как прежнюю принятую версию. Не требуется компрометация реального проекта для воспроизведения.

**Приёмка исправления:** заранее проверить все snapshots/lock и совместимость, восстановить согласованный набор без частичных записей, проверить фактические итоговые digests. Отдельно покрыть удалённые/добавленные файлы и локальные overrides. T21, G5.

### A03 · P1 · Corpus freeze и acceptance проверяют декларации, а не замороженное доказательство качества

**Код:** `src/testence/benchmark.py:24–104`; `corpus/r1-correctness-v1.json`; CI использует `--structure-only`.

Digest вычисляется только от JSON registry, не от referenced cases, кода evaluator и fixtures. `source` обозначает файл, но не однозначный исполнимый case. Счётчик 40 проверяет уникальность ID, а не уникальность сценариев. Четыре записи в `product_defect` описывают worker crash/missing terminal/dropped oracle/wrong identity, то есть проверки runner/proof, а не двадцать дефектов приложения. Публичная метка `holdout` не доказывает независимый замороженный holdout.

**Воспроизведения:**

- После заморозки подменён содержимый source: валидатор не заметил изменения, digest остался прежним.
- Все 40 ID могут ссылаться на один файл и проходить structural validation.
- Два одинаковых объекта с `commit=not-a-commit`, `license=placeholder`, несуществующим reproduction receipt и двумя объявленными reviewers дают `accepted`, `acceptance_ready=true`.
- Windows absolute path с прямыми слешами вне corpus root тоже принят. Утверждение предыдущего receipt «Every source path is contained» не выполняется для общего валидатора.

**Последствие:** CI freeze не защищает от изменения корпуса, а full acceptance допускает успех без двух реальных targets и проверяемых результатов. Текущий настоящий registry честно остаётся `incomplete`; фиктивные данные использовались только в копии.

**Приёмка исправления:** явные selectors и expected outcomes, content digests всех inputs, независимое исполнение/оценка, корректные strata, containment после resolve, уникальные target revisions, обязательные существующие и связанные receipts. Не считать самодекларацию reviewers машинным доказательством независимости. Затем заново заморозить корпус и выполнить rates/denominators/intervals. T23, G6.

### A04 · P1 · Installed-wheel smoke может подписать успехом произвольный файл

**Код:** `scripts/installed_wheel_smoke.py:36–38,94–98`.

Скрипт проверяет импортированную установленную библиотеку, но `--distribution` только проверяется на существование и хешируется. Связь между импортами и переданным wheel не устанавливается.

**Воспроизведение:** существующий отдельный wheel environment запущен с `--distribution not-a-wheel.whl`. Файл содержит обычный текст, не ZIP/wheel. Итог: exit 0, `status=passed`, браузер/agents/demo прошли, receipt связывает успех с SHA-256 этого текста.

**Последствие:** перепутанный или устаревший artifact может получить положительное свидетельство. В текущем CI установка и smoke последовательно выбирают wheel из одного dist, что снижает вероятность ошибки; это не доказывает binding в самом переносимом receipt.

**Приёмка исправления:** smoke создаёт чистый consumer environment и устанавливает именно переданный wheel либо строго проверяет installed origin/RECORD против этого artifact; фиксирует import location/version и связанные dependency hashes. Невалидный/чужой wheel обязан отказать до успешного receipt. T25, G8.

### A05 · P1 · Release gate не проверяет структуру и доказательства manifest

**Код:** `tests/test_release_manifest.py:7–28`; `src/testence/contracts/schemas/release-manifest.schema.json`.

Тест проверяет отдельные поля и множество ID после преобразования списка в dict. Полный JSON Schema не исполняется, дубликаты стираются, `receipts` не проверяются. Дополнительно тест жёстко требует `dirty_worktree=true` и `no-go`, поэтому законный переход к clean/go ломает тест вместо проверки критериев готовности.

**Воспроизведение:** тот же неизменённый тест запущен на отдельной копии manifest с `base_sha=INVALID`, девятью gates, повторным G1, несуществующими receipts и пустыми artifacts. Тест прошёл.

**Приёмка исправления:** самостоятельный validator manifest: JSON Schema, уникальность, ссылки/digests, применимость receipt к RC/dependencies; `go` разрешён только при чистом кандидате и полной приёмке G1–G8. Добавить отрицательные fixtures и положительную clean/go fixture. Исторический no-go документ хранить отдельно от правил проверки. T29, G8.

### A06 · P2 · Локальная provenance приписывает wheel исходному HEAD, который его не содержит

**Код:** `scripts/release_artifacts.py:113–141`; прежний `release-artifacts/provenance.json`.

Receipt содержит `source.revision=7be8d02…`, но не состояние dirty/source snapshot. В inputs только `pyproject.toml`, `uv.lock`, `MANIFEST.in`, а не реализация пакета.

**Воспроизведение:** wheel с SHA-256 `c359fdaf…` совпадает с subject в provenance и содержит `testence/application.py`; `git cat-file -e 7be8d02…:src/testence/application.py` показывает, что в этом commit файла нет.

**Последствие:** указанный commit не воспроизводит проверенный artifact. Общий RC manifest честно сообщает dirty/no-go, но отдельно переданная provenance эту существенную оговорку теряет.

**Приёмка исправления:** для release build требовать clean revision; для local build явно хранить dirty и digest полного source snapshot. Связать версии, lock, build inputs, smoke и checksums с одним artifact. T25/T29, G8.

### A07 · P2 · One-command demo не выполняет обещанный путь до failure pack

**Код:** `src/testence/application.py:43–161,281–350`.

Оба generated tests сравнивают заданные в коде словари через custom oracle. Такой synthetic smoke допустим, но он не демонстрирует полный QA workflow: actual UI/state, failure pack, Allure output, bound diagnosis/proposal не создаются этой командой.

**Воспроизведение:** `run_demo` вернул `passed`, healthy — `verified`, intentional failure — `violated`; у обоих `summary.packs=[]`, файлов `pack.json` нет. HTML reports существуют.

**Последствие:** пользователь видит успешный onboarding, но не получает обещанный переносимый объект для разбора failure. Это локальная инженерная недоработка E06/U1/U4, не только отсутствие видео. Отдельные старые agent/pack fixtures не связывают этот путь end to end.

**Приёмка исправления:** одна команда из установленного wheel выдаёт детерминированный healthy/failure с pack/report/export и валидным путём к verdict; fixtures и инструкции переносимы. Наличие намеренно упавшего assert само по себе не закрывает продуктовую приёмку. T18/T26, G5/G7/G8.

### A08 · P2 · Resource/flake receipt шире, чем реально измеряемая нагрузка

**Код:** `bench/scale_profile.py:47–105`; `outputs/audit-2026-09-06-followup/warm-fresh-profile.json`.

10k tests создаются в памяти до старта `tracemalloc` и таймера; измеряется CTRF export из готового `LoadedRun`. «Failure storm» — сериализация тысячи заранее ограниченных строк, не flood capture через network/console/DOM/ledger. Cold subprocess существует, но reported elapsed не включает запуск процесса. Равенство SHA-256 сериализации не измеряет частоту flaky browser execution. В сохранённом Chromium warm/fresh JSON только агрегаты, отдельных raw iteration samples нет.

**Последствие:** эти полезные microbenchmarks подтверждают стоимость export, но не общий RSS/run/collector budget, защиту при flood и flake rate R17/T24. Предыдущий статус «local acceptance passed» шире доказательства.

**Приёмка исправления:** сохранить точные названия microbenchmarks; дополнить end-to-end flood/capture и process-tree resource measurement, сырыми итерациями, failures/timeouts и flake denominator. Проверять caps на входе, а не только размер заранее обрезанных данных. T12/T24, G3/G6.

### A09 · P2 · SPDX SBOM описывает constraints прямых зависимостей вместо состава проверенной установки

**Код:** `scripts/release_artifacts.py:71–110`; прежний `release-artifacts/sbom.json`.

SBOM содержит только Testence, Playwright и pytest. В `versionInfo` зависимостей стоят `>=1.49` и `>=8.0`; транзитивные packages отсутствуют. Отдельный installed dependency inventory из 11 packages полезен, но generator SBOM его не использует и не связывает с тем же distribution/target environment. Wheel CI устанавливает runtime graph отдельно от `uv sync --locked`.

**Последствие:** по этому SBOM нельзя определить точные проверенные dependency versions и их транзитивный состав. Это неполнота release evidence, а не утверждение о найденной уязвимой зависимости.

**Приёмка исправления:** разграничить package requirements и SBOM конкретной проверенной среды; resolved versions/relationships/target markers и hashes должны соответствовать smoke inventory. Отдельно описать browser/driver и дополнительные поставляемые assets. T25/T28, G8.

## Что осталось за границей локальной реализации

| Gate | Оценка аудита |
|---|---|
| G1 Truth | Существенное исправленное ядро и регрессионные проверки есть; перенос статуса `passed` на будущий RC требует нового выполнения и review. Полный независимый acceptance в этом аудите не повторён. |
| G2 Safety | Не принят: A01, полная junction/symlink/retention/capture matrix и независимый review. |
| G3 Web reliability | Windows evidence есть; результаты локального pytest зависят от файлового окружения; нужен Linux RC и подтверждение resource/capture boundaries. |
| G4 Integrations | Offline и реальный Allure consumer есть; live TestOps selection/upload/history receipt отсутствует по текущему manifest. |
| G5 Agent workflow | Два real-client triage receipts полезны, но `passed` преждевременен для безопасного полного workflow: A01/A02/A07 и принятие plan/test/proposal цепочки. |
| G6 Measured quality | Не принят: A03/A08, реальные OSS targets, truth review и независимое исполнение. |
| G7 Adoption | Пилотный протокол есть; пять пользователей/три команды/week return и независимые reproduction не подтверждены. |
| G8 Distribution | Не принят: A04–A07/A09, clean RC/hosted CI, security channel, rights review, видео и release infrastructure. |

Скан пяти Git commits из T28 не покрывает текущие незакоммиченные additions. Нужны отдельный tree scan предполагаемого публичного состава и повтор history/dependency scan на RC. Наличие нового `SBOM` файла не заменяет такой scan. Этот аудит не повторял сетевой vulnerability scan и не утверждает отсутствие актуальных advisories.

В `.github/workflows` сейчас один `ci.yml`: build/attestation реализованы, protected release environment и PyPI trusted-publishing workflow ещё необходимо подготовить согласно E08. Саму публикацию выполнять только по отдельному решению владельца.

## Очередь завершения

1. **Безопасность и целостность изменений:** A01/A02; прогоны Windows junction и Linux symlink; восстановление policy только из проверенных bytes.
2. **Достоверность приёмки:** A03–A06; исполнимый frozen corpus, доказуемый wheel binding, manifest validator, clean/source-bound provenance.
3. **Завершённый пользовательский путь и измерения:** A07–A09; demo с failure pack, реальные flood/resource/flake samples, resolved SBOM.
4. **RC и внешняя приёмка:** один clean SHA, полная поддерживаемая CI matrix, scans/rights/security channel, TestOps и pilots, видео, owner go/no-go.

Это завершение существующего R1, не повод расширять объём до mobile, новых браузеров или переписывания runtime. Не нужно заново выполнять принятые части без связи с изменениями; необходимо закрыть конкретные разрывы и перепроверить затронутые gates.

## Автоматические проверки

Ruff lint: PASS. Format: PASS, 130 файлов. Mypy: PASS, 59 source files. Logs: [lint](../../../outputs/audit-2026-09-06-result/lint.log), [format](../../../outputs/audit-2026-09-06-result/format.log), [types](../../../outputs/audit-2026-09-06-result/types.log).

Первый pytest launch был невалиден как проверка продукта: аудитор указал basetemp внутри ещё не созданного parent directory, что привело к fixture setup errors. После создания parent полный прогон дал **333 passed, 6 failed, 2 skipped** за 124.12 s; failures — Windows `PermissionError` при файловых операциях. [Log](../../../outputs/audit-2026-09-06-result/pytest-rerun.log), [JUnit](../../../outputs/audit-2026-09-06-result/pytest-rerun.xml).

Повтор в исключённом из индекса корневом временном каталоге завершился: **339 passed, 2 skipped, exit 0 за 125.07 s**, Python 3.13.11. [Log](../../../outputs/audit-2026-09-06-result/pytest-final.log), [JUnit](../../../outputs/audit-2026-09-06-result/pytest-final.xml). Оба skips относятся к созданию symbolic links без необходимых Windows privileges; собственные junction-пробы аудита при этом выполнились. Причина первоначальных блокировок файлов не установлена: влияние индексатора/антивируса — гипотеза, не доказанный диагноз. Неуспешный запуск сохранён. Повтор подтверждает штатную регрессию в этом окружении, но не закрывает найденные отрицательными пробами gaps.

Независимые отрицательные пробы прошли как воспроизведения дефектов: успешные product statuses в них — предмет находок, а не evidence соответствия ТЗ.
