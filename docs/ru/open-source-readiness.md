# Готовность к open source

Исходное дерево использует Apache-2.0. Текущий publication inventory классифицирует код,
схемы, документацию, сгенерированные demo fixtures, SVG-знаки и benchmark SUT как
синтетические материалы репозитория и не находит vendored стороннего датасета. Эту
классификацию должен независимо проверить rights reviewer на чистом candidate; до этого
она не разрешает публикацию и не доказывает, что `NOTICE` не нужен.
Построчная по областям запись находится в
[OSS publication inventory](../oss-publication-inventory.md).

Runtime-зависимости — Playwright и pytest с их транзитивными зависимостями. В актуальном
installed-wheel inventory зафиксированы Apache-2.0, MIT, BSD, PSF-2.0 или совместимые
составные выражения. CI создаёт SPDX 2.3 SBOM, checksums дистрибутивов, dependency
inventory и build provenance. Для финального candidate lock обязательны `pip-audit` и
review лицензий.

Локальное сканирование истории 2026-09-06 выполнено Gitleaks 8.30.1 с redaction: пять
коммитов, около 2,10 MB, утечки не обнаружены. Audit закреплённых runtime-зависимостей не
нашёл известных уязвимостей. Эти проверки покрывают известные шаблоны и базы, но не
доказывают отсутствие любой возможной утечки или уязвимости.

Публикация заблокирована до включения GitHub private vulnerability reporting,
повторного сканирования чистого финального RC commit и review всех новых материалов
maintainer-ом. См. [support policy](../../SUPPORT.md),
[security policy](../../SECURITY.md) и
[текущее release-решение](../../release/rc-manifest-v2.json). Ручной workflow
`publish.yml` принимает только существующий tag, артефакты выбранного CI run и
защищённый acceptance bundle, при котором manifest возвращает `go`. До запуска нужно
фактически настроить и проверить environment `pypi` и trusted publisher в GitHub/PyPI.
