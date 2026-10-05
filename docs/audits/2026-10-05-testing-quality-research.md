# AUD-Q26: исследования и следующий цикл качества Testence

Дата: 2026-10-05. Предыдущий цикл: [AUD-20261001](2026-10-01-security-proof-audit.md).
Миссия — улучшать обнаружение дефектов, достоверность свидетельств и полезность
авторинга, сохраняя детерминированный replay без модели. Рыночное лидерство этим
локальным циклом не установлено.

## Исследования и применимые подходы

Источники прочитаны через первичные публикации и официальную документацию.
Выводы для Testence ниже — наши инженерные решения, а не результаты этих работ
на нашем пакете. Ни статья, ни coverage не заменяют приёмку конкретного сценария.

| Источник | Что даёт | Решение для Testence |
|---|---|---|
| [Barr et al., The Oracle Problem in Software Testing: A Survey, TSE 2015](https://discovery.ucl.ac.uk/id/eprint/1471263/) | Систематизация проблемы определения корректного результата и подходов к oracle | Проверять происхождение ответа и независимость чтения; UI-success сам по себе недостаточен |
| [Inozemtseva & Holmes, ICSE 2014](https://www.cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf) | В исследованных Java-системах связь coverage с fault detection при контроле размера набора была низкой/умеренной | Coverage использовать для поиска пробелов; цель приёмки — пойманный конкретный дефект и healthy control |
| [Petrović et al., Does mutation testing improve testing practices?, ICSE 2021](https://arxiv.org/abs/2103.07189) | Анализ промышленных мутаций и реальных исправлений поддерживает применимость mutation testing | Начать с направленных мутаций контракта: снятая provenance, потерянная запись, неправильная entity/revision; отдельно учитывать invalid и equivalent mutants |
| [Hypothesis: stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html) | Генерация последовательностей действий, передача полученных сущностей между правилами | Для небольшого lifecycle сейчас исчерпывающе перебрать короткие последовательности; для CRUD/actors позже генерировать и минимизировать контрпримеры, сохранять replay seed |
| [Playwright Route](https://playwright.dev/python/docs/api/class-route) | `fulfill`/`abort` меняют исход; `continue_` и цепочки `fallback` имеют разную семантику | Наблюдать фактическую подмену, не объявлять mock по наличию handler; сохранять signature, identity, times и fallback chains |
| [Cypress intercept](https://docs.cypress.io/api/commands/intercept) | Разделение spying/stubbing и ожидания конкретного request/response | Записывать происхождение и конкретный запрос; пассивное наблюдение не должно портить backend proof |

Не переносим результаты Java-исследования количественно на Python/browser suite.
Не называем направленные отрицательные controls универсальным mutation score.

## Реализуемый slice Q26-01–Q26-03

1. **Q26-01 / mcp.deadline.owned**: завершить прежнюю незавершённую работу по
   владению процессами. Windows job получает gated launcher до запуска проекта;
   POSIX — отдельную группу. Завершение корня, deadline и исключения освобождают
   группу. Ответ при deadline сохраняет run reference, summary, redacted tails и
   `isError=true`, не выдумывает `run.end`. Приняты только integer timeout 1..900.
   Контроль — реальные child/grandchild listeners плюс живой unrelated process.
2. **Q26-02 / native.response.provenance**: публичные native page/context routes
   наблюдаются после входа в seam. `fulfill` и `abort` отмечены; passthrough, удаление
   исходного handler, новые страницы и смена context проверены отдельно.
   Persistence oracle отвергает подменённую мутацию; fresh HTTP read независим.
   Изменение подсказки oracle учитывает, что `fetch` мог достичь сервера до `fulfill`.
3. **Q26-03 / doctor.video.dependency**: отсутствующий FFmpeg получает точную
   подсказку установки; doctor создаёт video context, только если видео включено
   в конфигурации, чтобы проверить соответствующую runtime-зависимость.

Алгоритм model control Q26-02: независимая модель `active/closed`, операции
`register`, `unroute`, `request`, `close`, длина 1..4. Полный перебор **340**
последовательностей, сравнение каждого перехода и числа событий; это bounded
exploration, не доказательство всех возможных жизненных циклов. Реальный Playwright
corpus отдельно проверяет то, что fake модель не может подтвердить.

## Следующие шаги по пакетам

| Приоритет | Пакет / работа | Измеримая приёмка |
|---|---|---|
| P1 | `oracle` / направленный fault corpus на двух независимых backend-приложениях | Healthy подтверждён; seeded lost-write, stale revision, wrong entity, wrong role, duplicate send и substituted response отвергнуты по правильной причине; ошибки harness отдельно |
| P1 | `engine` / границы provenance | HAR, service worker, внешняя подмена и перехват до native seam: документированный fail-closed/unknown контракт вместо ложного authoritative ответа; работающий fallback-chain control |
| P1 | `evidence`, `contracts`, exporters / metamorphic controls | Redaction idempotent, export не повышает assurance, обрыв ledger остаётся incomplete, перестановка независимых тестов сохраняет агрегаты; реальные неэквивалентные дефекты обнаружены |
| P1 | `api`, `oracle`, actors / модель CRUD | create→read→update→read→delete→absence с entity/actor/revision bindings; короткий контрпример и сохранённый seed; тесты не вызывают повторную мутацию для получения green |
| P2 | `agent` / польза oracle suggest | Предложение проверено на живом backend, а не только совпало со snapshot JSON; время авторинга и replay измерены отдельно |
| P2 | `runner`, support matrix / переносимость | Exact candidate на Windows/Linux/macOS, Python/dependency floors; interruption, job failure, process groups и nested browser jobs имеют отдельные receipts |

Дальнейший алгоритмический выбор: property-based генерация с shrinking для больших
пространств данных; bounded state exploration для малых lifecycle; metamorphic
relations для redaction/export; направленные mutation operators для проверки
oracle. Добавлять dependency или API только после конкретного воспроизведения,
а не ради названия метода. Основные показатели: detection по каждому классу дефекта,
false positives на healthy controls, wrong-reason failures, replayability и latency.

Направленный mutation control уже добавлен в synthetic native corpus: запись
создана реальным API заранее и соответствует expected entity/fields, затем Save
получает подменённый ответ. Свежий read успешен, но oracle обязан отвергнуть саму
мутацию как mocked. Если в synthetic test отключить только instance tracker,
оба scope (`page`/`context`) дают `DID NOT RAISE`: это обнаружение одной конкретной
мутации в двух вариантах. Switch находится в generated test, не в runtime пакета.
Browser GET был бы подменён другим body; независимый HTTP read возвращает seeded
state. Healthy и passthrough controls остаются зелёными.

## Границы текущего assurance

Обычный public `route` не равен всем способам сетевой подмены. HAR replay, service
workers, внешние proxies и handlers до seam пока не входят в наблюдение. Участок
POSIX process-group реализован, но Windows-проверка не удостоверяет Linux/macOS.
Временный stdout/stderr ограничен по памяти возвращаемых tails, но использует диск
до окончания команды. Никакой публикации, hosted matrix или независимого клиентского
испытания не заявлено. Итоговые команды и receipts — в [handoff](2026-10-05-testing-quality-handoff.md).
