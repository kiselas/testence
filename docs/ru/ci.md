# Testence в CI

Workflow GitHub Actions для проекта, созданного `testence init`. Он ставит Testence и
Chromium, запускает тесты без модели, экспортирует JUnit для просмотра тестов в CI и
сохраняет evidence (`runs/`) как artifact, в том числе когда тест упал. CI самого
репозитория выполняет шаги этого файла как есть на свежем проекте `testence init`.

Файл: [`docs/examples/github-actions.yml`](../examples/github-actions.yml).

```yaml
# Copy to .github/workflows/e2e.yml in your project; `testence init` writes the rest.
name: e2e

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      # Only for an app behind a login; unset secrets are empty and ignored by auth: none.
      TESTENCE_USER: ${{ secrets.TESTENCE_USER }}
      TESTENCE_PASSWORD: ${{ secrets.TESTENCE_PASSWORD }}
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - name: Install Testence and Chromium
        run: |
          python -m pip install testence
          python -m playwright install --with-deps chromium
      - name: Run the tests
        run: testence run --project . --run-id "ci-${{ github.run_id }}"
      - name: Export JUnit for the CI test view
        if: always()
        run: testence export "runs/ci-${{ github.run_id }}" --to junit -o test-results
      - name: Keep the evidence
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: testence-evidence
          path: |
            runs/
            test-results/
```

- Приложение со входом читает `TESTENCE_USER` и `TESTENCE_PASSWORD` из secrets
  репозитория; `auth: none` их не использует ([аутентификация](auth.md)).
- `testence run` роняет job, если тест упал; экспорт и artifact всё равно выполняются
  (`if: always()`), поэтому pack каждой упавшей попытки лежит в `runs/`.
- Для Allure TestOps передавайте результаты потоково через `--testence-allure-results`
  ([отчётность](reporting.md#загрузка-результатов-в-allure-testops)); для других систем
  экспортируйте `--to ctrf`.
- GitLab CI и другим системам нужны те же четыре команды: `pip install testence`,
  `python -m playwright install --with-deps chromium`, `testence run`, `testence export`.
