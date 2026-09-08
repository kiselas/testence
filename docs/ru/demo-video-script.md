# Сценарий 90-секундного demo video

Запись выполняется одним непрерывным terminal session на candidate wheel с известным
digest. На экране остаются часы, а опубликованный receipt использует те же run IDs.

- **0–10 с:** показать пустую директорию и выполнить
  `testence demo run --project testence-demo --json`.
- **10–35 с:** показать healthy run: pytest exit 0, execution `passed`, assurance
  `verified` и путь локального report.
- **35–60 с:** показать intentional false-green: pytest exit 1, execution `failed`,
  assurance `violated`, claim `onboarding.defect.detected` и расхождение UI/API.
- **60–78 с:** открыть автономный report и пройти claim → assertion → evidence.
- **78–90 с:** показать machine receipt, оба run ID и точный SHA-256 wheel.

Нельзя монтировать report от другого run или показывать usernames, локальные секреты и
посторонние пути. Финальное видео остаётся внешним launch asset; один этот сценарий не
закрывает G8.
