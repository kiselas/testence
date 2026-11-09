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
        # Strict mode (opt-in, one more run per declared control): replace this command
        # with `testence prove --project . --run-id "ci-${{ github.run_id }}"`.
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

## GitLab CI

Те же шаги для GitLab: [`docs/examples/gitlab-ci.yml`](../examples/gitlab-ci.yml).

```yaml
# Copy to .gitlab-ci.yml in your project; `testence init` writes the rest.
# The jobs share one target, so `resource_group` keeps two pipelines from running
# against it at the same time; set TESTENCE_PROFILE per environment.

stages: [check, test]

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  PLAYWRIGHT_BROWSERS_PATH: "$CI_PROJECT_DIR/.cache/ms-playwright"
  TESTENCE_RUN_ID: "ci-$CI_PIPELINE_ID-$CI_JOB_ID"

default:
  image: python:3.12-slim
  cache:
    key: testence-deps
    paths: [.cache/pip, .cache/ms-playwright]
  before_script:
    - python -m pip install testence
    - python -m playwright install --with-deps chromium

# Tests collect: imports, fixtures, markers. No target needed.
collect:
  stage: check
  before_script:
    - python -m pip install testence
  script:
    - python -m pytest --collect-only -q
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

e2e:
  stage: test
  resource_group: target-$TESTENCE_PROFILE
  timeout: 2h
  script:
    # TESTENCE_USER / TESTENCE_PASSWORD (or your profile's variables) come from masked
    # CI/CD variables. A deadline per test keeps one hang from stopping the job.
    - testence doctor --target
    - testence run --project . --run-id "$TESTENCE_RUN_ID" -- -q -n 4 --testence-test-timeout 600 || status=$?
    - testence export "runs/$TESTENCE_RUN_ID" --to junit -o junit || true
    - testence report "runs/$TESTENCE_RUN_ID" || true
    - testence ci summary "runs/$TESTENCE_RUN_ID" > summary.md || true
    - testence timing "runs/$TESTENCE_RUN_ID" || true
    - exit ${status:-0}
  artifacts:
    when: always
    expire_in: 14 days
    paths: [runs/, junit/, summary.md]
    reports:
      junit: junit/junit.xml
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_PIPELINE_SOURCE == "schedule"
    - if: $CI_PIPELINE_SOURCE == "web"
```

- `resource_group: target-$TESTENCE_PROFILE` пускает к общей цели один конвейер за раз;
  задание, которое стало бы вторым, ждёт.
- Учётки берутся из маскированных переменных CI/CD с именами `user_var` и `password_var`
  профиля (или `TESTENCE_USER` и `TESTENCE_PASSWORD`).
- `--testence-test-timeout` роняет зависший тест и даёт заданию идти дальше; повторов
  нет. `testence timing` печатает, куда ушло время задания.
- Отчёт JUnit виден во вкладке тестов merge request; `runs/` со всеми пакетами улик и
  `report.html` остаётся артефактом.
- Для Allure TestOps добавьте `--testence-allure-results "runs/$TESTENCE_RUN_ID/allure-results"`
  и запускайте под `allurectl watch` ([отчёты](reporting.md#загрузка-результатов-в-allure-testops)).

## Требовать доказательство, что тесты умеют падать

`ci evaluate --quality-mode assurance` (по умолчанию) требует, чтобы каждый тест был
`verified`. Тест, ожидаемое значение которого списано с продукта, тоже `verified`.
Необязательный режим `proven` дополнительно требует для каждого обязательного claim
прогон с [негативным контролем](configuration.md#негативные-контроли), в котором тот же
тест упал на assertion этого claim ([ADR-0033](../en/adr/0033-negative-proof.md)):

```bash
testence prove --project . --run-id "ci-${GITHUB_RUN_ID}"
```

`testence prove` — весь строгий режим одной командой:

1. зелёный прогон, `runs/ci-<id>`; если он не зелёный, команда останавливается с его
   кодом выхода и больше ничего не запускает: тест, падающий без дефекта, ничего не
   доказывает;
2. по одному прогону на каждый объявленный контроль, `runs/ci-<id>-<контроль>`, либо
   только на названные через `--control NAME` (опцию можно повторять);
3. оценка как `ci evaluate --quality-mode proven`, где каждый прогон контроля идёт как
   `--negative-run`, и один receipt, `runs/ci-<id>.receipt.json` (`-o` меняет путь).

Код выхода тот же, что у `ci evaluate`: 0, когда у каждого обязательного claim есть
негативное доказательство, 10, когда доказательства не хватает. Тесты и опции pytest
пишутся после `--`, как у `testence run`; без них запускается onboarding-тест. Каждый
прогон контроля выполняет тот же выбор тестов, что и зелёный. Прогоны контролей не
повторяются: `TESTENCE_RERUNS` там игнорируется, а `--testence-reruns` отклоняется.
`--json` печатает один документ в stdout, а вывод pytest отправляет в stderr.

Команда — короткая запись того, что джоб может расписать и вручную, например чтобы
гонять контроли в параллельных джобах:

```bash
testence run --project . --run-id "ci-${GITHUB_RUN_ID}"
testence run --project . --run-id "ci-${GITHUB_RUN_ID}-drop-save" --control drop-save || true
testence ci evaluate "runs/ci-${GITHUB_RUN_ID}" --run-id "ci-${GITHUB_RUN_ID}" \
  --test-exit 0 --quality-mode proven \
  --negative-run "runs/ci-${GITHUB_RUN_ID}-drop-save" -o ci-receipt.json
```

Негативный прогон должен падать, поэтому его код выхода не определяет результат джоба
(`prove` это учитывает). Шаг summary в шаблоне читает по одному прогону контроля на
каждый `--negative-run`:
`testence ci summary "runs/ci-${GITHUB_RUN_ID}" --negative-run "runs/ci-${GITHUB_RUN_ID}-drop-save"`.
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
Если больше половины claim, упавших в прогоне контроля, побочные, `testence prove`,
`ci summary` и receipt (`quality.negative_proof.controls`, `blunt: true`) предупреждают, что контроль, возможно, слишком
грубый и `proven` говорит немногое ([ADR-0033](../en/adr/0033-negative-proof.md#tripwire));
код выхода предупреждение не меняет. Каждый контроль стоит ещё одного прогона, а у
части claim честного контроля нет, поэтому `proven` — более строгий уровень для самых
важных claim, а не режим по умолчанию.
