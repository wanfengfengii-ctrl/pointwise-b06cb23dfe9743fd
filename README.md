# 板材测厚质控台

板材厂的量规员按工单登记量规、名义厚度和取样片序。班组交正式测厚单，统计员在同一目标批上比较末片模型和均值模型，次班凭签报号查核两套预测的误差和原始出处。片序由冻结清册确定，勘误后的实际采信单随冻件传递，两库可分别关闭和重开。

## 一天的工作

1. 量规员在判读库登记量规，并把历史批 H 冻结为 B、A 两片。
2. 班组提交 B 的 8 μm 和 A 的 11 μm，凭 A 的当前实收勘误为 12 μm。实收链保留两张单。
3. 班组封存 H，领取以清册原序排列、附实际采信号的实测冻件。
4. 统计员将 H 的冻件交预测库，发布末片模型 MZ 和等权均值模型 MA，参数为 12 和 10 μm。
5. 量规员登记目标批 T，统计员接收 T 的冻结清册，按 MZ、MA 的顺序发行 B、A 的预测件。
6. 判读库在预测库关闭后接纳完整预测件，保留发行件及本地实收号。
7. 班组提交 T 的 13、11 μm 并封存。复核员凭本地预测实收号及 T 的实测冻件签报。
8. B 的两项平方误差为 1、9 μm²，A 为 1、1 μm²，片级分差为 −8、0 μm²，批均差为 −4 μm²。次班重开判读库凭原报告号领取已签正文。

## 公开 Python 入口

使用 Python 3.11 标准库。`review.store.open_review(path)` 与 `prediction.receipts.open_prediction(path)` 分别返回 SQLite 连接。重复打开只补齐结构。调用方负责关闭，推荐用 `contextlib.closing`。

| 模块 | 调用及结果 |
| --- | --- |
| `batches.gauges` | `register_gauge(db, gauge_id, provenance)` 登记量规。`read_gauge(db, gauge_id)` 复领量规。 |
| `batches.register` | `register(db, batch_id, gauge_id, nominal_um, pieces)` 返回 `Roster`。清册固定批号、量规、名义厚度和有序片号。 |
| `batches.registry` | `RosterRegistry(db).save_snapshot(roster)` 将完整清册搬入预测库，保留原冻号。`read_snapshot(roster_id)` 用原冻号复领。 |
| `measurements.intake` | `submit(db, roster_id, piece_id, source, value)` 返回正式 `Receipt`，包含 `receipt_id`。同来源同参重投返回首单。 |
| `measurements.revisions` | `correct(db, receipt_id, value, source)` 返回替代实收，并通过 `previous_id` 保留前件。`MeasurementLedger.get_receipt` 可查历史单。 |
| `measurements.seal` | `seal(db, roster_id)` 齐备时发 `FrozenTruth`，`read_sealed_truth(db, truth_id)` 按号复领。 |
| `training.fit` | `train(db, truth, model_id, strategy)` 验收冻结历史件并发布 `ModelVersion`。策略为 `last_piece` 或 `mean`。`training.catalog.read_model` 和 `training.admission.read_training_truth` 分别复领模型和训练冻件。 |
| `prediction.jobs` | `forecast(db, target, first_model_id, second_model_id)` 返回 `ForecastPair`。`target` 是本库已有清册的冻号或等义快照。`prediction.receipts.read_forecast` 按发行件号复领。 |
| `review.admission` | `admit(db, package)` 返回本地预测实收号，`read_admitted_forecast(db, admission_id)` 复领本地保存的正文。 |
| `review.reports` | `report(db, admission_id, truth)` 凭本地实际实收和本地正式实测冻件签报。`read(db, report_id)` 复领父件、片级平方误差及批均差。 |

业务编号使用非空、可打印、无首尾空白的文本。片序为非空的列表或元组且片号互异。录入读值接受整数、`Fraction` 及带数字的十进制或分数字符串，例如 `0`、`12.5`、`7/9`。名义厚度为正，实测为非负。无实收的位置表示缺测。`batches.roster`、`measurements.exchange` 和 `prediction.package` 提供对应 `encode_*` / `decode_*` 函数。交换为带版本的 JSON 正文，读值统一用约分的 `n/d` 文本表示，分母为正。实测及预测入口也接受相应编码正文。等价正文允许 JSON 的空白和字段排列差异。

未知的合法格式本地查询号报 `KeyError`。非法输入、实收来源冲突、错片、坏件、清册错配、缺片封批及失效勘误报 `ValueError`。实测封件、已发布模型和发行件可重复领取。签报原子保存父件、摘要和明细，提交失败整体回滚并传播原错误，同样的父件可重试。原报告保存计算结果，另行比较或重开后仍可原样复领。

## 运行

控制台物化后运行完整回归。

```text
python3 -B check_project.py
```

`tests` 包中的完整套件也可直接运行。

```text
python3 -B -m unittest discover -s tests
```

样例来自 `examples/workday.json`，演示用独立临时库，显式运行后给出预测、签报和重开复领的结果。

```text
python3 -B -m tests.test_workday
```
