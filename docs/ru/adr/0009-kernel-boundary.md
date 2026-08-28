# ADR-0009: Граница compute kernels для будущих native/Rust backends

Статус: accepted (2026-08-25) — seam создан, native backend пока **не обоснован**

## Контекст

Python — основной язык согласно ADR-0002: экосистема подходит, а LLM agents как
first-class пользователи кодовой базы лучше всего читают и пишут его. Поэтому вопрос
«сможем ли мы позже переписать горячие места нативно?» нужно решить архитектурно сейчас,
пока это почти бесплатно, а не пытаться проводить refactor под давлением.

Сначала нужно понять, куда уходит CPU. Есть два пути:

- **Driving plane** — engine, DSL и pytest wiring — ограничен I/O. Один step выполняет
  CDP round-trip около 10 мс, из которых Python↔driver IPC занимает около 0,85 мс по E1
  и ADR-0002. Переписывание на любом языке ничего не меняет: код ждёт Chrome.
- **Analysis plane** — parsing ledger, diff snapshots, scoring candidates и token
  counting — состоит из чистых CPU-функций над простыми данными. Только здесь native
  backend может окупиться.

## Решение

Ввести `testence.kernels`: узкий версионированный ABI `KERNEL_ABI` для **чистых**
функций с нормативным pure-Python reference backend и подключаемыми альтернативами.
Полные правила описаны в [`kernels.md`](../kernels.md):

1. Через границу проходят только простые данные: bytes, str, numbers, lists и dicts.
   Это FFI contract; framework и Playwright types запрещены.
2. Функции чистые: без I/O, clocks, randomness и global state. `EvidenceWriter`
   намеренно не kernel — это fsync I/O, остающийся в Python.
3. Reference implementation определяет корректность. Native backend проходит тот же
   conformance suite без изменений в `tests/test_kernels.py`, параметризованный по
   backends.
4. Native поставляется optional wheel `testence_kernels` и выбирается через
   `TESTENCE_KERNELS=auto|reference|native`. `auto` молча откатывается;
   `native` явно падает, чтобы benchmark не приписал Python-число Rust. ABI mismatch
   отклоняется.
5. Testence полностью работает без native artifacts. Rust toolchain не требуется для
   установки, разработки или contribution.

Текущие kernels: `parse_ledger`, `estimate_tokens`, `percentiles`, `diff_aria`,
`score_candidates`. Последние два нужны эксперименту E3 для snapshot diffs и
гипотезе H6 о heal proposals из fingerprints; они являются правдоподобными native
candidates.

## Измеренная стоимость

`bench/kernels.py`, Windows 11, Python 3.12.4, reference backend:

| Kernel | Нагрузка fleet-scale | Медиана | На единицу |
|---|---|---:|---:|
| `parse_ledger` | 80 000 events / 22 MiB, около месяца CI | 413 мс | 5,2 µs/event |
| `diff_aria` | 200 diffs snapshots по 500 nodes, один suite | 303 мс | 1 517 µs/diff |
| `score_candidates` | 100 rankings × 300 candidates | 303 мс | 3 035 µs/ranking |
| `percentiles` | 80 000 samples, 2 percentiles | 2,1 мс | — |
| `estimate_tokens` | 4 MiB evidence text | 0,9 мс | — |

Честная интерпретация:

- **Сегодня ни один kernel не оправдывает Rust.** Самый дорогой, `diff_aria`, тратит
  около 0,3 с на suite — 0,1% пятиминутного бюджета.
- `parse_ledger` уже опирается на C через `json.loads`; native rewrite даст
  примерно 3–5× на 0,4 секунды, что не стоит FFI dependency.
- `percentiles` и `estimate_tokens` навсегда исключены: фактически это `sorted()`
  и `len()`. Они находятся в kernel только ради uniform ABI.
- Реальные кандидаты — pure-Python алгоритмы `diff_aria` и `score_candidates` на
  объёмах **corpus replay**. Ablation experiments E2–E4 повторяют diff всего корпуса
  тысячи раз, превращая 1,5 мс на diff в минуты.

## Последствия

- Когда Rust станет оправдан, стоимость refactor близка к нулю: реализовать ABI в
  отдельном crate, опубликовать wheel и переключить env var. Callers не меняются.
- Differential testing доступен с первого дня: один suite работает на обоих backends,
  а `metrics.json` записывает backend каждого числа.
- Небольшая постоянная цена: kernels должны оставаться чистыми, поэтому caching внутри
  kernel или чтение файла в `parse_ledger` отклоняется на review.
- Будущие kernels, изначально требующие скорости, например настоящий BPE tokenizer
  вместо byte estimate, подключаются к уже существующей seam.

## Tripwire

Kernel получает native implementation, когда выполняется хотя бы одно условие:

1. он превышает 5% wall-clock budget suite — больше 15 секунд пятиминутного run;
2. он превышает 10 секунд в обычном analysis workflow: corpus replay,
   `testence bench` aggregation или report generation.

При текущей стоимости это более 10 000 вызовов `diff_aria` за workflow: suite из
500 cases с diff каждого шага либо corpus ablation. Такого масштаба следует достичь
**до** написания Rust, но архитектуру подготовить заранее. `bench/kernels.py`
перезапускается для каждого release; первый kernel, пересёкший порог, получает отдельный
crate и сохраняется только при ускорении не менее 5× на том же benchmark.
