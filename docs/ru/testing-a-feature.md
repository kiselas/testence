# Тестирование UI-функции с Testence

Руководство описывает нейтральный к продукту workflow превращения утверждения о
поведении в быстрый и поддерживаемый UI-тест.

## 1. Сформулируйте утверждение

Напишите одно предложение с субъектом, действием и наблюдаемым результатом:

> Когда авторизованный пользователь отправляет валидный widget, новый widget появляется
> в коллекции, а API возвращает те же значения.

Разделяйте независимые утверждения на независимые тесты. Путь create/edit/delete полезен
как smoke flow, но плох как regression unit: поздние assertions зависят от предыдущих
действий, parallelism невозможен, а одно падение скрывает остальные.

Для каждого утверждения зафиксируйте:

| Поле | Вопрос |
|---|---|
| предусловие | какое состояние должно существовать до взаимодействия? |
| UI-адрес | какая role, label или стабильный test id определяет control? |
| oracle | какое независимое наблюдение доказывает результат? |
| мутация | создаёт или меняет тест общие данные? |
| cleanup | как созданные данные идентифицируются и удаляются? |

Зафиксируйте это в PlanSpec до открытия браузера. Файл содержит человеческий контекст и
ровно один машиночитаемый блок `testence-planspec`; минимальный рабочий пример находится
в `examples/specs/target-page.md`. Проверяйте контракт сразу:

```bash
testence plan validate specs/widgets-create.md --json
```

## 2. Исследуйте поверхность

Перед написанием селекторов проверьте routes, roles и accessible names через браузер и
accessibility tree. Предпочитайте в таком порядке:

1. role и accessible name;
2. label или placeholder;
3. стабильный настроенный test-id attribute;
4. CSS, только если приложение не даёт семантического адреса.

Не выводите контракт API из отрисованной страницы. Читайте документированный API или
публичную схему, а специфичные селекторы приложения храните в проектном `ActionMap`,
не в пакете фреймворка.

## 3. Подготовьте данные через API

Создавайте предусловия через проектный `SeedAdapter` или `ApiClient` общей сессии.
Воспроизводите предусловие через UI только тогда, когда этот UI-flow сам является
проверяемым утверждением.

Каждая созданная запись должна иметь marker запуска и worker. Безопасная fixture:

- удаляет только записи со своим marker;
- проверяет cleanup вместо подавления ошибок;
- соблюдает порядок зависимостей;
- сообщает об остатках как о сбоях test infrastructure.

На общих окружениях предпочтительны read-only тесты. Для мутаций по возможности
используйте изолированный tenant или ephemeral environment.

## 4. Управляйте намерением, а не реализацией

Тест должен быть коротким и читаемым:

```python
@pytest.mark.testence(
    plan="specs/widgets-create.md",
    claims=["widgets.create.persisted"],
)
def test_created_widget_is_visible(ex, testence_api, widget_seed):
    widget = widget_seed.valid()

    ex.goto("/widgets", intent="open the widget collection")
    ex.click(CREATE_BUTTON, intent="start creating a widget")
    ex.fill(NAME_FIELD, widget.name, intent="name the widget")
    ex.click(SAVE_BUTTON, intent="save the widget")

    ex.expect_text(ROW_NAME, widget.name, intent="show the created widget")
    actual = testence_api.get(f"/api/widgets/{widget.id}").raise_for_status().json
    ex.verify("created widget", {"name": widget.name}, {"name": actual["name"]})
```

Избегайте произвольных sleeps. Ждите значимое состояние: request, response, видимое
значение, количество строк или специфичный сигнал готовности приложения.

## 5. Докажите, что тест правильно падает

Зелёный тест ещё не доказывает полезность assertion. Перед принятием сценария:

1. запустите его на исправном target;
2. внесите или временно сымитируйте поведение, которое он должен обнаружить;
3. проверьте, что ожидаемый assertion падает по ожидаемой причине;
4. восстановите target и снова получите зелёный тест.

Marker проверяется во время pytest collection. Во время выполнения его plan и claims
попадают в каждое событие теста, failure pack и HTML report. При ожидаемом падении
заполните созданный в pack `verdict.template.json`, сохраните как `verdict.json` и
проверьте связь с планом и доказательствами:

```bash
testence verdict validate runs/<run>/<test>/pack/verdict.json \
  --plan specs/widgets-create.md --json
```

Синтетические корпусы в `corpus/` и `bench/corpus/` применяют эту дисциплину к
самому фреймворку.

## 6. Пишите узко, проверяйте широко

Во время authoring запускайте один тест с долгоживущим attached browser:

```bash
python -m testence.dev_browser --profile staging
pytest tests_e2e/test_widgets.py -k created_widget --testence-profile staging-attached
```

Перед merge несколько раз выполните полный suite на неизменном коде. Сравните:

- стабильность outcome;
- общее и пооперационное время ожидания;
- false-red controls;
- полноту evidence pack;
- успешность cleanup;
- serial и parallel результаты.

Включайте `pytest-xdist` только после появления per-worker namespaces в fixtures и
worker-specific offsets у всех machine-wide ресурсов.

## Типичные причины ошибок

- Presence assertion проходит на skeleton или placeholder rows.
- Устаревшая panel удовлетворяет общему условию «dialog открыт».
- Request успешно обработан сервером, но страница прерывает response.
- UI и API используют разные окна sort, filter или pagination.
- Нестрогое сравнение текста выбирает другой элемент или принимает временное значение.
- Повтор interaction скрывает дефект проглоченного первого клика.
- Silent locator healing перенаправляет тест на неверный control.

Testence записывает доказательства для этих случаев, но тест всё равно обязан
формулировать точное утверждение и осмысленный oracle.
