# ADR-0006: Без LLM в execution path и provider-neutral agent contracts

Статус: accepted (2026-08-25)

## Контекст

Исследованные AI test frameworks — Stagehand, Midscene, Shortest, Skyvern — помещают
модель в execution loop: тесты являются natural-language prompts, код — cache. Это
улучшает authoring UX ценой детерминизма CI, стоимости каждого запуска и vendor
coupling. Гипотеза Testence противоположна: **агенты создают и судят, машина исполняет**.

## Решение

1. Runner не делает вызовов LLM. В runtime dependencies нет model SDKs. Стоимость
   повторного suite `llm_cost_per_ci_run_usd = 0` **по конструкции**; каждый релиз
   проверяет dependency tree и отсутствие сетевых вызовов к model providers.
2. Agent-facing surfaces — **контракты, а не привязки**: evidence pack состоит из
   обычных файлов и `pack.json`; taxonomy и инструкции triage поставляются как
   `TRIAGE.md` в каждом pack; правила authoring — как docs/skills. Судьёй может быть
   любой агент, читающий файлы. Skills являются first-class integration, но не
   dependency.
3. Будущий escape hatch `ai_step()`, при котором агент один раз выполняет шаг и
   материализует результат в код по модели Stagehand cache, работает во время
   **authoring**, но никогда внутри CI execution.

## Отклонённые варианты

- LLM-in-the-loop execution по модели Shortest: около 114K tokens/test через
  интерактивные MCP против около 27K scripted по данным Currents 2026,
  недетерминированный CI и стоимость каждого запуска.
- Anthropic SDK в core: жёсткий vendor coupling противоречит OSS; integration
  принадлежит skills/docs, но не runner.

## Последствия

- CI не нужны model API keys, поэтому возможна работа в restricted environments.
- Качество verdict зависит от измеримого и улучшаемого качества evidence через
  ablations E2–E4, а не скрыто в agent loop поставщика.

## Проверка каждого релиза

- Dependency audit: отсутствие `anthropic`, `openai` и model SDKs в runtime tree.
- E6: triage contract выполняется второй, не-Claude моделью на подмножестве корпуса;
  обнаруженные разрывы закрываются контрактом, а не простой заменой модели.
