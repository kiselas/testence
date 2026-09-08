# Реестр работ до R1

Все 24 требования обязательны для заявленного R1; P0/P1 задают порядок и риск. Статус всех строк — **к реализации / приемке**, а не «сделано» по факту существования похожего модуля. Роли владельцев предстоит назначить конкретным участникам. Нормативная приемка находится в [ТЗ](release-spec.md), текущие доказательства — в [аудите](audit.md).

| ID | Приоритет | Результат | Связь с аудитом | Зависимости | Владелец | Gate |
|---|---|---|---|---|---|---|
| R01 | P0 | Все lifecycle outcomes, включая tests без ex | A01, A03 | — | Core + SDET | G1 |
| R02 | P0 | Project/case/variant/attempt identity без коллизий | A02, A10 | R01 | Core | G1, G4 |
| R03 | P0 | Manifest scope/completion и recovery partial ledger | A03, A09, A11 | R01, R02 | Core | G1 |
| R04 | P0 | Required claims доказаны конкретными assertions | A04, A05 | R02, R03 | Core + QA | G1 |
| R05 | P0 | Expected-state oracles и consistency deadlines | A13, A14 | R04, R06, R11 | SDET + Core | G1 |
| R06 | P0 | Origin-safe auth, role/session/cache isolation | A07, A12, A18 | — | Core + Security | G2 |
| R07 | P0 | Единая redaction и безопасные artifact paths | A06, A08 | R02, R06 | Security + Core | G2 |
| R08 | P0 | Bounded capture, portable packs, recovery/retention | A03, A06, A19 | R03, R07 | Core | G2 |
| R09 | P0 | Bound verdict и безопасный reviewable repair | A05, A17 | R04, R07, R08 | Core + Agent UX | G5 |
| R10 | P0 | CI isolation, data lifecycle, parallel/attached ownership | A12, A18 | R01, R02, R03, R06 | Core + SDET | G3 |
| R11 | P0 | Strict targets, rich assertions, scoped waits | A14, A15 | R04, R10 | Core + SDET | G3 |
| R12 | P1 | Frames, shadow, popup, files, dialogs, keyboard | A16 | R10, R11, R22 | Engine + SDET | G3 |
| R13 | P0 | Allure consumer compatibility со всеми outcomes | A01, A02, A10 | R01, R02, R03, R04, R08, R09 | Integrations | G4 |
| R14 | P0 | TestOps selection/mapping/live round trip | A10 | R02, R03, R13, R15 | Integrations + QA | G4 |
| R15 | P0 | CI exit integrity, JUnit/CTRF, TMS import recipes | A10, A11 | R03, R13 | Integrations + CI | G4 |
| R16 | P1 | Doctor, typed CLI, init/update, два agent clients | A20 | R03, R04, R05, R06, R07, R08, R09 | Agent UX | G5 |
| R17 | P1 | Resource/latency/flake evidence и budgets | A19, A21 | R08, R10, R11, R12, R18 | Performance + SDET | G6 |
| R18 | P0 | Independent grader, mutations и две OSS SUT | A09, A13, A21 | R01, R02, R03, R04, R05, R09, R10, R11, R12 | Benchmark + внешний reviewer | G6 |
| R19 | P1 | CI matrix, clean wheel, supply-chain checks | A21 | R07, R12, R13, R14, R15, R16, R17, R18 | Release + CI | G8 |
| R20 | P1 | Working docs, migration и единая support matrix | A11, A20, A22 | R13, R14, R15, R16, R19 | Docs + QA | G7, G8 |
| R21 | P1 | Quality pack и один QA на трёх проектах | Уточнённая цель пользователя | R02, R04, R06, R14, R15, R16 | QA platform + Integrations | G4, G7 |
| R22 | P1 | Capability contracts и отдельная граница mobile | A16 | R02, R03, R04 | Architecture + Engine | G3 |
| R23 | P1 | Три пилота, пять onboarding, внешние reproduction | Непроверенная adoption-гипотеза | R14, R15, R16, R17, R18, R19, R20, R21 | Product + QA champions | G7 |
| R24 | P1 | Готовый публичный release package и receipts | OSS readiness | R01–R23 | Maintainer + Product | G8 |

Зависимости обозначают условия полной приемки. Ранние части работ можно выполнять раньше: исправление evaluator (R18) начинается сразу; выбор пилотов и OSS-приложений (R23 discovery) начинается до готовности всей реализации. Это устраняет ожидание внешних участников в самом конце.

## Первые десять небольших задач

1. Перенести lifecycle audit reproduction в consumer integration suite и зафиксировать failing expectations (R01).
2. Зафиксировать collision/incomplete reproductions и договориться о identity/schema migration (R02/R03).
3. Исправить empty/crashed control grading с проверкой expected scope и exit (ранняя часть R18).
4. Закрыть forwarding auth на foreign origin и добавить synthetic redirect/cookie checks (R06).
5. Закрыть artifact traversal через resolved containment с symlink/junction cases (R07).
6. Ввести run manifest и reconciliation counts до расширения export (R03).
7. Ввести assertion events и fail-closed required proof без обязательного API для UI-only claim (R04).
8. Внедрить sanitizer на persist boundary; проверить канарейки по всем sinks (R07/R08).
9. Подготовить Allure/TestOps mapping fixture и testplan selection contract (R13/R14).
10. Подготовить clean CI recipe с explicit run ID и сохранением test exit (R15).

Готовность пакета определяется receipts G1–G8. Ни число закрытых issues, ни число passing unit tests не заменяют эти условия.
