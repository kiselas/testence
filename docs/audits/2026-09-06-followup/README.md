# Повторный аудит R1 и следующий этап

6 сентября 2026, HEAD `7be8d025f81d9116ab267c59d440e14b377cfce7`.

- [Аудит выполнения предыдущего ТЗ](audit.md): выполненное, регрессии, блокеры, проверки и матрица R01–R24.
- [ТЗ R1 v1.1](release-spec.md): доверенный QA workflow и подготовка OSS release candidate, 8 пакетов работ и 5 milestones.
- [Backlog](backlog.md): 29 задач и 3 discovery-пункта, зависимости и приёмка.
- [Результат M0](m0-implementation.md): реализованные совместимость статусов,
  fail-closed reconciliation/evaluator и regression evidence.
- [Результат security slice M1](m1-security-implementation.md): origin-safe auth,
  scoped session cache и containment чтения artifacts.
- [Результат T06](t06-identity-schema-implementation.md): единая identity,
  версии `/2`, legacy adapters и consumer parity.
- [Результат T07–T08](t07-t08-lifecycle-integrity-implementation.md): crash/restart/retry
  reconciliation, атомарный run manifest и fail-closed recovery.
- [Результат T09](t09-assurance-implementation.md): assertion inventory, proof digests
  и независимая от execution assurance axis.
- [Результат T13](t13-expected-state-implementation.md): authoritative expected-state
  polling, request correlation, deadlines/windows и executable edge-case corpus.
- [Результат T14](t14-bound-verdict-repair-implementation.md): immutable verdict
  bindings, JSON Pointer verification и repair proposal с фактическими proof runs.
- [Результат T15](t15-allure-consumer-implementation.md): полная Allure projection
  и отчёт, открытый реальным закреплённым Allure Report consumer.
- [Результат T16 offline](t16-testplan-implementation.md): fail-closed TestOps plan
  selection; live tenant round trip остаётся внешним gate.
- [Результат T17](t17-ci-delivery-implementation.md): раздельные CI exits,
  JUnit/CTRF parity и идемпотентный delivery receipt с bounded retry.
- [Результат T18](t18-application-services-implementation.md): doctor/init/run/inspect,
  валидируемая отправка verdict и полный synthetic workflow из установленного wheel.
- [Результат T19](t19-runtime-isolation-implementation.md): context/auth/data isolation,
  явное владение browser и эквивалентный fresh/warm consumer scope.
- [Результат T20](t20-capability-actions-implementation.md): versioned capabilities,
  strict actions, fake-engine negative и реальная Chromium web matrix.
- [Результат T21](t21-quality-pack-implementation.md): versioned quality pack,
  три project namespaces, conflict/override/rollback и actionable QA summary.
- [Результат T22](t22-agent-clients-implementation.md): conflict-safe установка в
  Codex/Claude, два реальных клиента на одном pack и два валидных submit receipt.
- [Результат T23](t23-corpus-protocol.md): frozen registry на 40 cases и честно
  незакрытые OSS/reviewer acceptance gates.
- [Результат T24](t24-scale-performance.md): raw 10k/failure-storm/warm/fresh profiles
  и прошедшие resource/flake budgets.
- [Результат T25–T26](t25-t26-distribution-demo.md): RC CI, installed-wheel Chromium
  smoke и однокомандный green/failure demo; hosted/video receipts ещё требуются.
- [Результат T27](t27-pilot-readiness.md): EN/RU pilot protocol и sanitized session
  template; внешние участники и week-return ещё требуются.
- [Результат T28](t28-open-source-readiness.md): rights/dependency inventory, history
  и vulnerability scans, support/security policy с явным channel blocker.
- [Решение T29](t29-release-decision.md): versioned G1–G8 manifest и `no-go` до
  завершения внешней приёмки на одном чистом RC SHA.
- [Воспроизводимые проверки](../../../outputs/audit-2026-09-06-followup/README.md): команды, результаты, ограничения.
- [Предыдущая версия ТЗ](../2026-09-06/release-spec.md): нормативные R01–R24 сохранены, прежние документы не перезаписаны.

Итог после начала реализации: 339 тестов проходят, два link-теста пропущены этой
Windows-системой; T01–T15 и T17–T20 подтверждены локально, offline-часть T16 реализована
(для T10–T12 сохраняются внешние
security gates), но R1 ещё не принят. Следующий этап завершает independent corpus,
QA/integration и OSS gates; web
beta/mobile не добавлены в текущий scope.
