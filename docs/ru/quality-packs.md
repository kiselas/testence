# Multi-project quality packs

Quality pack — каталог с `quality-pack.json` и перечисленными по digest файлами policy,
fixture interfaces, oracle recipes или selection rules. Примените точную revision:

```bash
testence quality apply ../team-quality-pack . --json
```

Команда проверяет каждый byte, отвергает выход path за pack и credential-like files,
записывает фиксированные name/version/digest в `testence.json` и managed files в
`.testence/quality-pack.lock.json`. Update заменяет файл только при совпадении с прошлым
pack. Human edit даёт conflict. Для намеренного local edit нужен
`.testence/quality-overrides.json` с path, reason, owner и неистёкшей датой `YYYY-MM-DD`;
такой файл сохраняется и попадает в report.

Каждая принятая revision сохраняет прошлые файлы в
`.testence/quality-pack-history/`. Восстановите точный digest:

```bash
testence quality rollback . --digest sha256:...
```

Rollback отвергает одновременно изменённый target и не удаляет history. Для сводки
reconciled runs без копирования raw evidence:

```bash
testence quality summary runs/r-catalog runs/r-billing runs/r-admin --json
```

Summary группирует по project и показывает только actionable violations, missing
execution, missing proof и integrity failures. Очередь фильтруется через `--project`,
`--owner`, `--risk`, `--case`. Requirements/manual descriptions остаются в TMS,
executable policy — в Git, execution facts — в immutable runs, diagnosis/repair — в
bound proposals.
