# 逐片在线回测交班

值班员可以先接纳一片的正式测厚单。预测台固定该片的预测依据后，判读台即可用首收实测供数。双预测正文稍后取回，凭同一个依据签报。两台沿用 README 中的独立 SQLite 连接和冻结清册。用 `RosterRegistry.save_snapshot` 将同一清册带到预测库。线上操作按冻结清册的批号和片号定位，两库均须持有本次使用的清册。

## 训练和签报口径

每批线上训练序号从 1 起，按预测库实际接纳该批供数件的顺序连续增长。截点是建单期间同一次所见的已提交线上训练条数，0 表示空前缀。两项预测分别取该前缀末值及精确等权均值。空前缀两项都取清册名义厚度。V1 离线训练和本批线上训练各有自己的输入。相同批号、片号的重试复领同一个建单依据。建单成功时其双预测已可独立兑现，在判读库关闭、后续样本入账或预测库重开后仍可按原建单领取。依据可以固定双值，也可以固定可在预测库精确复算原双值的历史依据。

每片线上采用本地首份正式实收。已有 V1 首单即沿用该首单及其实收号，后来的勘误依原口径继续用于 V1。沿用 V1 的厚度输入格式及来源冲突规则。合法的同片同值重投即使使用另一个未占用的来源，也复领首单且不新增实收。异值重投拒办。首收与承诺可以各自先到。两者齐备即可供训练，预测正文随后接纳。训练入账与签报分别办理，签报所需的依据、双预测正文和首收一旦齐备即有资格签报。每片只产生一份正式线上签报，复领返回存值。

本站写入各自整体提交。失败传播原错误且不留下此次的部分写入，可重试。发生提交后失答时，建单、供数接纳及签报应可按同一业务键重试并领取已提交结果。调用通过两座库各自的公开入口进行，跨站仅传递返回的件。

## Python 调用

`batch_id`、`piece_id`、`source` 和各业务编号沿用 V1 的文本规则。表中的 `body` 是另一入口返回的版本化 JSON 文本，内部结构由实现确定。交换须能核对确切冻结清册、片号和同一建单绑定。预测正文须同时给出截点与双预测，供数件须同时给出原承诺的绑定与首收实测的身份及值。数值字段沿用约分后的 `n/d` 文本。有效 JSON 的空白或字段次序变化视为等价。接收端须拒绝坏件、错误种类、错配和与现有绑定冲突的正文，保持首纳。

| 模块 | 入口与结果 |
| --- | --- |
| `measurements.intake` | `submit_online(db, batch_id, piece_id, source, value)` 接纳或复领正式 `Receipt`。 |
| `prediction.jobs` | `begin_online(db, batch_id, piece_id)` 持久建单并返承诺正文 `str`。`collect_online(db, batch_id, piece_id)` 返原双预测正文 `str`。 |
| `review.admission` | `accept_online_commitment(db, batch_id, piece_id, body)` 接纳该片承诺，成功返回 `None`。`make_online_observation(db, batch_id, piece_id)` 在首收和承诺齐备时返该片供数正文 `str`，待齐返 `None`。`accept_online_prediction(db, batch_id, piece_id, body)` 核对已接纳的同片承诺并接纳双预测正文，成功返回 `None`。 |
| `training.admission` | `admit_online_observation(db, body)` 核对本库原承诺及实收归属，然后接纳供数。返回原入账序号 `int`，等价重投返回相同序号。同片换实收或同实收换归属拒办。`online_training_size(db, batch_id)` 返回已提交的该批线上训练条数 `int`。 |
| `review.reports` | `report_online(db, batch_id, piece_id)` 返回正式签报 `dict`，待齐返 `None`。`read_online_report(db, report_id)` 返回同一签报。 |

签报包含 `report_id`、`batch_id`、`roster_id`、`piece_id`、`receipt_id`、`commitment_id` 六个文本字段及 `cutoff` 整数。`first`、`second`、`actual`、`delta` 均为 `Fraction`。`delta` 为第一项平方误差减第二项平方误差，单位为 μm²。签报同时存下这些出处和结果，按号读取已签正文。非法输入、坏件、错配及冲突报 `ValueError`。直接查询时，合法格式的未知批号、片号、尚无建单的领取或未知报告号报 `KeyError`。已知片待齐属于表中的正常返回。

## 交班样例与核验

名义厚度为 11 μm，清册序为 B、A、P、Q、R。先让 A 的 8、B 的 12 按此顺序进入线上训练。A 在空前缀建单，两项均为 11。P 的 13 先实收，在前缀长度 2 时建单，丢弃已提交的建单回包。Q 的 30 先入训练。两库重开后，复领 P 的承诺，尚未领取 P 的双预测正文就可以把 P 加到训练第 4 项。随后 P 的双预测仍为 12 和 10，平方误差为 1 和 9，签报分差为 −8。R 在此时建单，取末值 13 和均值 63/4。R 实收 14 后签出分差 −33/16。

`python3 -B -m examples.online_shift` 在新增入口完成后运行上述场景，执行失败会产生非零退出码。结果包括 P 和 R 的实际签报，并核对 P 的重领。保留 `python3 -B check_project.py` 的完整原回归。交付时让 `.pointwise-runtime.json` 的 `verify` 同时核验原回归与在线交班，`demo` 展示在线签报和重开领取。清单沿用版本 1、`cli` 类型、`setup` 命令数组列表，以及各为一个命令数组的 `verify` 和 `demo`。
