# Pitch ↔ Reality checklist

> Для каждого утверждения с `cofounders.html` (Motor Compiler v0.3) —
> сегодняшний статус и что нужно сделать чтобы оно стало measurement,
> а не bible. Документ статичный, питч не трогаем — двигаем продукт.
>
> Статусы:
> - 🟦 **Done** — claim true, есть код + тест/артефакт.
> - 🟨 **Needs glue** — claim true по сути, но не задемонстрирован end-to-end.
> - 🔴 **Bible only** — на disk нет ничего, нужна разработка.
>
> Шкала усилий: S = ≤2 ч, M = 0.5–1 день, L = >1 день.

---

## A. «Pinocchio CRBA → M(q), spectral basis {φᵢ}»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Pinocchio установлен в проде | 🟦 **Done** (2026-04-30, `pip install pin`) | — | — |
| Spectral basis считается через настоящую mass-matrix-weighted декомпозицию, не Laplacian | 🟨 | Verify `atlas.metadata['pinocchio_handle']` ≠ None после установки; перепрогнать MVP-1 → eigenvalues в новом базисе должны отличаться от kinematic fallback. Сохранить diff-картинку. | S |
| `python-fcl` установлен → self-collision check активен | 🟦 **Done** (2026-04-30) — но нужно убрать deprecation warning `hppfcl` → `coal` | Один import-fix в `atlas/self_collision.py` | S |
| Pinocchio + fcl закреплены в `requirements.txt` / Dockerfile / Railway build | 🔴 | Добавить `pin>=3.9`, `python-fcl>=0.7` в `pyproject.toml` motor_compiler service; сборка Railway должна тянуть их без сюрпризов | S |

---

## B. «Layer A — за минуты из URDF, без данных»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| URDF/MJCF parser работает для манипуляторов и легов | 🟦 9 роботов: G1, Go2, Anymal B/C, Noetix N2, Barkour, Franka, UR5e, Kinova | — | — |
| Atlas строится за минуты | 🟦 — реально <1 секунда per robot | — | — |
| **PNG визуализация мод** для cofounder-демо | 🟨 — есть stick-figure FK через urdf chain, но без mesh; для слайда лучше MeshCat | Опционально: подгрузить `package://ur_description/meshes` для трёх manipulators, сделать MeshCat headless render — одна gif анимация на робота | M |
| Embodiment classifier (manipulator/quadruped/humanoid) | 🟦 — все три manipulator'а классифицированы корректно | — | — |
| Self-collision check в атласе при build | 🟨 — FCL установлен, но `_link_dims_from_inertia` всё ещё bbox-only | Подключить mesh loader (assimp через pinocchio), параллельно с bbox; включить по env-флагу | L |

---

## C. «Layer B — 15 минут self-supervised babbling»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Calibrator runner существует | 🟦 `libs/motor_compiler/calibrator/runner.py` | — | — |
| Empowerment selector реализован | 🟦 `domain_randomization.py` | — | — |
| EDMD fit считает K, B | 🟦 `calibrator/edmd.py` | — | — |
| **15-минутный run в реальной MuJoCo на manipulator** | 🔴 — никогда не запускался | Поднять Franka MJCF в `mujoco_bridge` (env `MUJOCO_ROBOT=franka_panda`), `tools/mvp2_calibrate_franka.py` запускает 15-мин babbling через `TrustLayerBridgeAdapter`, сохраняет trajectories.h5 | M |
| **Train/test split + held-out prediction error** | 🔴 — `_validate_one_step` вызывается, но не сохраняется | В runner добавить split (last 20% held-out), считать median + p95 prediction error per horizon ∈ {1step, 0.1s, 0.3s, 0.5s, 1.0s}, сохранить `metrics.json` | S (после §C-MVP-2 поднят) |
| **`prediction_error_vs_horizon.png`** для слайда | 🔴 | Matplotlib plot из metrics.json + per-joint bar chart + Koopman spectrum + babbling state coverage (4 PNG) | S |
| **Spectral radius ρ(K) ≤ 1.05 на реальной calibration** | 🟨 проверено только на synthetic K (unit test). После MVP-2 проверить на реальном K | Уже есть assert в test, надо просто прогнать на реальной calibration | S |
| **PE rank ≥ 0.7 × control_dim** на 15 мин | 🔴 не измерено | Будет посчитано в MVP-2 | S |

---

## D. «Layer C — DSL → controller за секунды»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| DSL парсер (YAML → SkillSpec) | 🟦 | — | — |
| Lifted MPC | 🟦 | — | — |
| CBF QP safety filter | 🟦 (joint-limit + velocity barriers) | — | — |
| Compound skills (preconditions/postconditions) | 🟦 + regression test | — | — |
| **Compile time ≤ 30 секунд** (slide claim) | 🟨 — реально <5 сек, но не задокументировано | Зафиксировать в `metrics.json` MVP-3 | S |
| **«Один файл — три робота» на manipulator'ах** | 🔴 reach_to_point.yaml существует, но execute не запускался на Franka/UR5e/Kinova | После MVP-2 → `tools/mvp3_reach_matrix.py`: для каждого {Franka, UR5e, Kinova} × {3 target poses} компилит и исполняет `skills/reach_to_point.yaml`, считает EE error | M |
| **`mvp3_matrix.gif`** split-screen видео | 🔴 | Параллельный three-instance MuJoCo + ffmpeg склейка | M |
| Видеодемонстрации трёх MVP | 🔴 | После §B-meshcat + §C-mvp2 + §D-mvp3 — ffmpeg в три gif | S |

---

## E. «Switched Koopman K_σ для разных контактных режимов»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Класс `SwitchedKoopman` | 🟦 `compiler/switched_koopman.py` | — | — |
| Discriminator (regime classifier) | 🟦 — но heuristic | — | — |
| **Реальные K_σ из live calibration** для manipulator | 🔴 на disk нет ни одного calibration.json с per-regime K | После MVP-2 разделить trajectories на free-fly / contact regimes, fit K на каждый, сохранить в calibration | M |
| Online residual K-adapter активен по умолчанию для production skills | 🟨 — гейтится `online_adapt: true`, ни один skill не включает | Включить в `reach_to_point.yaml` + регрессия + smoke run | S |

---

## F. «Информационно-управляемое исследование (empowerment)»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Empowerment criterion в коде | 🟦 — формула $\mathcal{E}(s) = \max I(A; S')$ через mutual information estimator | — | — |
| Selector выбирает direction по PE | 🟦 — но не валидирован на manipulator | — | — |
| **Сравнение** vs random babbling: PE rank, prediction error, sample efficiency | 🔴 | После MVP-2 запустить второй babbling с `--exploration random` flag, построить два графика side-by-side | M |

---

## G. «CBF — математически доказанная безопасность»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| CBF QP solver | 🟦 OSQP backend в pipeline | — | — |
| Joint-limit barrier + adaptive margin | 🟦 + unit-тесты | — | — |
| Velocity-cap barrier | 🟦 | — | — |
| **Self-collision barrier** на mesh | 🔴 bbox-only | См. §B-self-collision | L |
| **Reachability proof** — формальная гарантия "не выйдет за safe set за горизонт T" | 🔴 | Per-tick QP — yes; reachability — нужен tool типа `dReal` / `Marabou` или ручная Lyapunov-проверка. Из-за зависимости от calibration K_σ — нетривиально. Альтернатива: переформулировать claim как "barrier-enforced controller", не "formally proven". | L |
| **Видео где CBF реально гасит unsafe команду** для слайда | 🔴 | В `tools/scenario_full_chain.py` добавить шаг: послать joint_velocity 5.0 rad/s (выше предела), показать что фактическая скорость ≤ предела + safety_event с rule_id | S |

---

## H. «80% мат ядра реализовано»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Math implemented | 🟦 ~80% true | — | — |
| **Sim validated end-to-end** | 🟨 ~30% (G1 only). После §C+D будет ~70% | См. §C, §D | M |
| **Validated with metric** (held-out PNG/JSON) | 🔴 ~5%. После §C → ~25%, после §D → ~45% | См. §C, §D | M |

Желательно в питч-странице иметь живые цифры из последних артефактов
вместо «80%» — например, табличку «10/10 примитивов compile, 5/5 E2E
шагов pass на G1, prediction error на 0.3s = X cm на Franka».

---

## I. «Layer A работает на нескольких роботах (Noetix, Barkour, Anymal)»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Noetix, Barkour, Anymal — атлас собирается | 🟦 в `docs/demos/motor_compiler/` есть pose snapshots | — | — |
| **Барьерный «работает»** = compile + smoke. **Не означает execute** | 🟨 | Рядом с pose snapshot должна быть метрика: spectral_radius, mode count, embodiment_class. Это чтобы инженер сразу видел что compile дал sensible результат, а не нули | S |

---

## J. «7 базовых примитивов и 1 compound skill на 3 роботах»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Реально 10 skills × 5+ роботов компилируются (под-claim) | 🟦 — bootstrap log это пишет | Цифра в питче занижена; после MVP-3 переписать в "10 примитивов × 8 роботов = 80 успешных компиляций" | S |
| **Execute** end-to-end проверен только на G1 (dance) | 🟨 | После §D → reach_to_point на 3 manipulator'ах добавит ещё 9 успешных execute | M |

---

## K. «Pre-trained spectral basis from URDF, no data needed»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Атлас строится без сбора данных | 🟦 — URDF-only | — | — |
| **Сравнение Atlas-only vs RL-trained baseline** на одной задаче | 🔴 — нет ablation, поэтому claim звучит unproven | Опциональный benchmark: одна reach_to_point задача, time-to-first-success: Atlas+Calibrator vs PPO baseline. Нужен SB3 + наша метрика. | L |

---

## L. «End-to-end в MuJoCo с измеренной prediction quality»

Дублирует §C — это и есть MVP-2. Эффективнее всего закрыть.

---

## M. «Live верификация на физическом роботе»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| **Любой запуск на железе** | 🔴 0 запусков | Зависит от доступа к Noetix N2 / E1 / Unitree G1 — это блокер не код. Когда есть hardware, MVP-2/3 переиспользуют тот же стек через `TrustLayerBridgeAdapter` указывающий на real bridge URL | M (после железа) |

---

## N. «Препринт arXiv + open-source Body Atlas Builder»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| `packages/partenit_body_atlas/` SDK structured | 🟦 own pyproject + Apache-2.0 | — | — |
| **PyPI publish** | 🔴 | `python -m build && twine upload`. Версионирование, namespace check (имя `partenit-body-atlas` свободен на PyPI?), README, examples notebook | M |
| **GitHub public repo** | 🔴 | Отдельный репо `GradeBuilderSL/partenit_body_atlas`, CI (GH Actions), pip-install smoke | S после PyPI |
| **arXiv preprint** | 🔴 | Не код-task. Структура: §1 problem, §2 method (Layers A/B/C), §3 results (MVP-1/2/3 после их закрытия), §4 future. ~10–15 страниц. | L |

---

## O. «Foundation models не дают формальных гарантий — мы даём CBF»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Сравнение демо: GR00T / Gemini Robotics на той же reach задаче | 🔴 | Опциональный promo benchmark; в питче можно ограничиться текстом без эксперимента | L |
| Безопасностный сравнительный прогон: один и тот же CBF input на нашем стеке vs пропущенная команда от LLM-планнера | 🔴 | Внутри `scenario_advanced.py` уже есть `velocity_clamp` — можно расширить. Но без VLA baseline это не head-to-head. | M |

---

## P. «Morphology-conditioned Koopman atlas K(m)»

| Claim | Status | What's needed | Effort |
|-------|--------|---------------|--------|
| Инфра для morph-descriptor m | 🟦 `domain_randomization.py` обрабатывает | — | — |
| **Обученная функция K(m)** — единая модель которая принимает morph-vector и выдаёт K | 🔴 | Это серьёзный ML-проект: собрать calibrations на ≥10 manipulator'ах, train hyper-network m → K, валидировать на hold-out robot. Текущий код просто хранит per-robot K, это не conditioned. | L+ |

---

## Что прямо сейчас разблокировано установкой pinocchio + fcl (2026-04-30)

- §A: **Pinocchio backend активен** (был fallback). Spectral basis теперь mass-matrix-weighted, как обещает питч.
- §B-self-collision: **FCL импортируется** — bbox-from-inertia работает с настоящим FCL backend, не silent skip.
- Тесты не сломались (11/11 motor_compiler).

Следующая логичная итерация: §C-MVP-2 (Franka MJCF в bridge + 15-мин babble + PNG метрики).

---

## Итог: сколько работы чтобы каждое утверждение стало measurement

| Bucket | Items | Total effort |
|--------|-------|--------------|
| **S** (1 day или меньше) | §A-3, §B-1, §C-3, §D-1, §E-2, §G-2, §I, §J-1 | ≈3 рабочих дня |
| **M** (несколько дней) | §B-2, §C-1, §D-3, §D-4, §E-1, §F-1, §M, §N-1, §O-1 | ≈2 рабочих недели |
| **L** (>неделя) | §B-3, §G-1, §K, §N-3, §P, §O-2 | месяц+ |

Минимальный набор чтобы 90% питча стало true: **§A + §C-MVP-2 + §D-MVP-3 + §E-online-residual + §G-CBF-video + §J-execute-matrix**. Это ≈2 рабочих недели code-time + GPU/MuJoCo wall-clock.
