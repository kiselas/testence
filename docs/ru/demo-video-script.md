# Сценарий 90-секундного demo video

Запись выполняется одним непрерывным terminal session на candidate wheel с известным
digest. На экране остаются часы, а опубликованный receipt использует те же run IDs.

- **0–10 с:** показать пустую директорию и выполнить
  `testence demo run --project testence-demo --json`.
- **10–30 с:** показать healthy run: pytest exit 0, execution `passed`, assurance
  `verified` и путь локального report.
- **30–50 с:** показать intentional false-green: pytest exit 1, execution `failed`,
  assurance `violated`, claim `onboarding.defect.detected` и расхождение UI/API.
- **50–65 с:** показать negative run: тот же healthy-тест с контролем `drop-save`
  (сохранение подтверждается, но не записывается), pytest exit 1 и claim
  `onboarding.proof.recorded` со статусом `proven` в `testence inspect`. Проговорить:
  тест, который только что прошёл, умеет падать на своём claim.
- **65–80 с:** открыть автономный report и пройти claim → assertion → evidence.
- **80–90 с:** показать machine receipt, четыре run ID и точный SHA-256 wheel.

Нельзя монтировать report от другого run или показывать usernames, локальные секреты и
посторонние пути. Финальное видео остаётся внешним launch asset; один этот сценарий не
закрывает G8.
