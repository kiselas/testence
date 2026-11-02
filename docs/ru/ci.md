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
      - name: Summarize what the run proved
        if: always()
        run: testence ci summary "runs/ci-${{ github.run_id }}" >> "$GITHUB_STEP_SUMMARY"
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
- `testence ci summary` пишет в summary джоба, что доказал прогон: обязательные claim,
  подтверждённые verified assertion, тесты без verified-доказательства, flaky-тесты и
  последним число прошедших тестов с пометкой, что это не аргумент. Команда читает только
  прогон и для читаемого прогона всегда завершается с кодом 0, поэтому результат джоба
  она не определяет.
- Для Allure TestOps передавайте результаты потоково через `--testence-allure-results`
  ([отчётность](reporting.md#загрузка-результатов-в-allure-testops)); для других систем
  экспортируйте `--to ctrf`.
- GitLab CI и другим системам нужны те же четыре команды: `pip install testence`,
  `python -m playwright install --with-deps chromium`, `testence run`, `testence export`.

## Требовать доказательство, что тесты умеют падать

`ci evaluate --quality-mode assurance` (по умолчанию) требует, чтобы каждый тест был
`verified`. Тест, ожидаемое значение которого списано с продукта, тоже `verified`.
Необязательный режим `proven` дополнительно требует для каждого обязательного claim
прогон с [негативным контролем](configuration.md#негативные-контроли), в котором тот же
тест упал на assertion этого claim ([ADR-0033](../en/adr/0033-negative-proof.md)):

```bash
testence run --project . --run-id "ci-${GITHUB_RUN_ID}"
testence run --project . --run-id "ci-${GITHUB_RUN_ID}-drop-save" --control drop-save || true
testence ci evaluate "runs/ci-${GITHUB_RUN_ID}" --run-id "ci-${GITHUB_RUN_ID}" \
  --test-exit 0 --quality-mode proven \
  --negative-run "runs/ci-${GITHUB_RUN_ID}-drop-save" -o ci-receipt.json
```

Негативный прогон должен падать, поэтому его код выхода не определяет результат джоба.
В receipt поле `quality.negative_proof` даёт по каждому claim один исход:

| исход | значение |
|---|---|
| `proven` | при активном контроле тест упал на этом claim |
| `stayed_green` | при активном контроле тест прошёл: этот дефект он не заметит |
| `wrong_reason` | тест упал, но на других claim |
| `inconclusive` | тест не запускался, повторялся или упал не на assertion |
| `stale` | тест или его план изменились между двумя прогонами |
| `no_control` | ни один переданный контроль не нацелен на этот claim |

`testence ci summary RUN_DIR --negative-run DIR` добавляет в summary джоба claim с
негативным доказательством. Чтобы публиковать сводку комментарием в pull request,
дайте джобу `pull-requests: write` и выполните
`testence ci summary RUN_DIR > summary.md && gh pr comment "$PR" --body-file summary.md --edit-last --create-if-none`.

Падения claim, на которые контроль не нацелен, перечислены в `collateral_claims`.
Каждый контроль стоит ещё одного прогона, а у части claim честного контроля нет,
поэтому `proven` — более строгий уровень для самых важных claim, а не режим по
умолчанию.
