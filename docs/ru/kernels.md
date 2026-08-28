# Вычислительные ядра (нормативный документ)

Это граница, за которой native-реализация может заменить Python без изменений callers.
Решение и измеренные затраты: [ADR-0009](adr/0009-kernel-boundary.md).

## Что может быть kernel

Функция подходит только тогда, когда она **чистая** и работает с **простыми данными**:

| Требование | Причина | Контрпример |
|---|---|---|
| без I/O | FFI boundaries несовместимы с file handles; ошибка должна легко повторяться | `EvidenceWriter` с fsync остаётся в Python |
| без clocks/randomness | воспроизводимость: один ledger должен всегда агрегироваться одинаково | timestamp остаётся в writer |
| без global state | backends должны заменяться в одном процессе для differential tests | никакой memoization внутри kernel |
| простые данные на входе/выходе | только bytes, str, int, float, list, dict — дешёвые для FFI | без `Target`, Playwright objects и callbacks |
| детерминированные ошибки | `ValueError` с сообщением либо errors как данные | никаких частичных результатов |

Если кандидат не проходит любую строку, он остаётся обычным Python-кодом. Всё внутри
границы должно быть **механически** переносимо.

## Текущие kernels

| Kernel | Роль | Кандидат на native? |
|---|---|---|
| `parse_ledger(bytes) -> list[dict]` | чтение run.jsonl; горячий путь при агрегации многих запусков | слабый: `json.loads` уже написан на C |
| `estimate_tokens(str) -> int` | контроль evidence budget | нет: фактически `len()` по bytes |
| `percentiles(list, list) -> list` | агрегация метрик | нет: фактически `sorted()` |
| `diff_aria(str, str) -> dict` | diff страницы между шагами E3, «что изменилось» для triage | **да**: pure-Python `difflib`, доминирует при replay корпуса |
| `score_candidates(dict, list) -> list[float]` | ranking heal proposal H6 | **да**: pure-Python циклы similarity |

Важная семантика `diff_aria`: node, присутствующий с обеих сторон в разной позиции,
помечается как `moved`, а не как `removed` + `added`. Triage зависит от различия:
исчезнувший элемент — `real_bug`, перестановка — нет.

## Выбор backend

```bash
TESTENCE_KERNELS=auto       # default: native при наличии, иначе reference
TESTENCE_KERNELS=reference  # принудительно pure Python
TESTENCE_KERNELS=native     # принудительно native; ошибка при отсутствии или неверном ABI
```

Silent fallback в `auto` предназначен пользователям; громкая ошибка `native` —
benchmarks, чтобы «native» измерение не оказалось Python. Каждый `metrics.json` и
fingerprint `run.start` записывают активные backend name и ABI.

## Добавление native backend

1. Реализуйте ABI в crate, публикующем Python module `testence_kernels` через PyO3 и
   maturin, с attributes `name: str` и `abi: int`.
2. Добавьте его в `BACKENDS` файла `tests/test_kernels.py`. Suite параметризован по
   backends и обязан пройти **без изменений**: reference implementation нормативна,
   любое расхождение является багом native backend, а не поводом ослабить тест.
3. Докажите выигрыш на `bench/kernels.py`: не менее 5× на той же нагрузке, иначе crate
   не окупает FFI dependency и build complexity.
4. Поставляйте отдельным optional wheel, затем подключите его к зарезервированному
   extra `pip install testence[native]`. Он не должен стать hard dependency:
   установка без compiler остаётся полностью рабочей.

## Изменение контракта kernel

Изменение формы output — это изменение схемы: повысьте `KERNEL_ABI`, обновите
conformance suite и отметьте изменение в ADR-0009. Backends объявляют реализованный
ABI, mismatch отклоняется при import. Старый native wheel, молча возвращающий старую
форму, — именно тот сбой, от которого защищает правило.
