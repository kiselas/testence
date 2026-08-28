# ADR-0015: Agent-native control plane над детерминированным runner

Статус: proposed (golden path pending, 2026-08-28)

## Контекст

Testence предназначен прежде всего для coding agents в Claude Code, Codex/ChatGPT,
OpenCode и похожих clients. Одних pytest API и failure report недостаточно для agent
product: агенту нужно знать, когда планировать, как доказать generated tests, какие
evidence проверять и когда изменение исходников требует review.

SDK одной модели в framework противоречил бы ADR-0006. Публикация каждой внутренней
функции как MCP tool связала бы public interface с implementation details. Workflow
только в prose сделал бы outcomes зависимыми от chat context и client.

## Рассмотренные варианты

1. Создать и разместить собственный Testence agent.
2. Поставлять отдельную first-class integration для каждого coding-agent client.
3. Определить один переносимый workflow через Agent Skills и repository instructions,
   поддержанный стабильными CLI contracts и необязательным тонким MCP facade.
4. Оставить Testence только runner и заставить каждого пользователя самостоятельно
   prompt своего агента.

## Решение

Выбран вариант 3.

У Testence три контура:

- agent control plane для planning, authoring, triage и maintenance proposals;
- deterministic verification plane для browser execution, API-oracles и ledger;
- trust/governance plane для schemas, provenance, redaction, permissions и review.

Agent Skills определяют workflow и порядок. Repository instructions дают небольшое
always-on правило активации. Стабильные task-oriented CLI operations выполняют работу
и возвращают structured artifacts. MCP может раскрывать те же application contracts,
но не должен стать второй реализацией. Client adapters остаются тонкими и не содержат
product logic.

Каждая фаза материализует проверяемый artifact. Принятые тесты являются обычным
детерминированным source code; routine CI не требует агента. Source repair предлагается,
проверяется и доказывается целевым перезапуском.

## Последствия

- Primary UX — запрос функции или риска агенту, а не последовательность framework
  commands, которую должен выучить человек.
- Пользователь меняет совместимый agent client без изменения тестов и run artifacts.
- CLI и artifact schemas должны стабилизироваться до публикации MCP surface.
- Agent bootstrap, PlanSpec, traceability и verdict persistence становятся требованиями
  public alpha, а не необязательной post-alpha полировкой.
- Небольшой объём client-specific installation docs всё ещё нужен.

## Tripwire

Пересмотреть portable-skill подход, если два supported clients не могут пройти одну
golden-path corpus task с одинаковыми PlanSpec, source и verdict schemas.
Client-specific capability добавляется только тогда, когда недостающее behavior нельзя
выразить через shared skill, repository instructions или typed tool contract.

Решение становится accepted, когда хотя бы один supported coding agent проходит из
чистой установки workflow: feature request → reviewed PlanSpec → live-proved
deterministic test → evidence-backed verdict.
