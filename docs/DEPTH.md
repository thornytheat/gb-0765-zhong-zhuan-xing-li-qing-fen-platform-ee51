# 深度登记 中转行李清分台

中转主管逐牌核对航段窗口与动作末态。跨日同航班号不能替代航段实例。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 扫描原件采信 | 查看射频重报和隔离行 | `/desk/scans` `/api/stage/scans` | `app/modules/scans/service.py` | `tests/test_scans.py` |
| M2 航段候选关联 | 核对候选段和提示 | `/desk/legs` `/api/stage/legs` | `app/modules/legs/service.py` | `tests/test_legs.py` |
| M3 扫件有序回放 | 按生效时刻核对动作 | `/desk/replay` `/api/stage/replay` | `app/modules/replay/service.py` | `tests/test_replay.py` |
| M4 错载与漏扫归因 | 按牌追踪待证与错装 | `/desk/exceptions` `/api/stage/exceptions` | `app/modules/exceptions/service.py` | `tests/test_exceptions.py` |
| M5 行李去向对账 | 勾稽计划段与去向件数、报减载补装名额 | `/` `/api/stage/ledger` | `app/modules/ledger/service.py` `app/modules/ledger/slots.py` | `tests/test_ledger.py` `tests/test_slots.py` |
| M6 批次留档复跑 | 保存并复算原件 | `/desk/archive` `POST /api/archive` | `app/modules/archive/service.py` `app/modules/archive/store.py` | `tests/test_archive.py` |
| M7 联程证据签发 | 验摘要并下载联程证据 | `/desk/evidence` `/api/evidence/<run>/export` | `app/modules/evidence/bundle.py` | `tests/test_evidence.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 脏扫描首列 BOM | 扫描号丢失 | 解码时去首 BOM | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bom` |
| TRAP-04 | 脏扫描第 16 行重复表头 | 误计为扫描 | 计独立分段 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_sections` |
| TRAP-05 | E17 多余分隔列 | 宽度误收 | 原行隔离 | `app/modules/scans/csvio.py` | `tests/test_scans.py::test_bad_width` |
| TRAP-07 | E18 时间 N/A | 默认零时 | 空值隔离 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_sentinel` |
| TRAP-08 | 清单 000101 | 强转丢零 | 字符串关联 | `app/modules/legs/contracts.py` | `tests/test_legs.py::test_tag_preserved` |
| TRAP-11 | E03 特殊偏移重复 | 误认成不同事件 | UTC 后比较 | `app/modules/scans/normalize.py` | `tests/test_scans.py::test_equivalent_offset_duplicate` |
| TRAP-13 | E02 迟到撤下 | 收件顺序末态错误 | 标迟到后按生效回放 | `app/modules/replay/radio.py` | `tests/test_replay.py::test_late_offload_before_reload` |
| TRAP-14 | E12 同键相反动作 | 后写覆盖 | 全组隔离 | `app/modules/scans/service.py` | `tests/test_scans.py::test_conflicting_id` |
| TRAP-23 | E04 恰逢跨日换窗 | 同时匹配两段 | 左闭右开 | `app/modules/legs/service.py` | `tests/test_legs.py::test_boundary_handoff` |
| TRAP-31 | 待证行李已占舱，按已装数放名额超额 | 名额 = cap − 已装 | 回放末态占用对限额，待证 LOADED 计占 | `app/modules/ledger/slots.py` | `tests/test_slots.py::test_loaded_totals_would_overbook_but_slots_do_not` |
| TRAP-32 | 迟到撤下未确认就腾舱 | 见撤下扫描即减占用 | 按生效时刻回放，末态撤下才腾名额 | `app/modules/ledger/slots.py` `app/modules/replay/radio.py` | `tests/test_slots.py::test_late_offload_only_releases_after_replay_confirms` |
| TRAP-33 | 错装件误占计划段名额 | 占用记在计划航段 | 错装按实际装载航段计占 | `app/modules/ledger/slots.py` | `tests/test_slots.py::test_dirty_slots_match_replay_occupancy` |
| TRAP-34 | 补传批次重跑重复释放名额 | 重跑累加释放 | 名额为原件纯函数，归档复算幂等 | `app/modules/ledger/slots.py` `app/modules/archive/service.py` | `tests/test_slots.py::test_rerun_is_idempotent_no_double_release` |

## 对账规则

脏样例清单 12 = 3 已装 + 8 待证 + 1 明确未装，错装 2 件另列。扫描原件记录 24 = 17 采信 + 4 隔离 + 1 重报 + 1 重复表头 + 1 空行。

减载补装名额（脏样例，限额合计 9）：NX-01 占 2/2 满额（迟到撤下回放后仍以装载收尾，不腾名额）；NX-02 占 2/1 超额（含 000108 错装）；HX-41 占 0/2；HX-42 占 1/2（000104 末态撤下不占）；JL-08 占 3/2 超额（待证 000106、清单外 009999、装撤未决 000107 各 1）。合计可补 3 件、2 个航段超额。

## 已知范围

文件内容通过限长 JSON 提交。样例为机场单站观测，时间窗由机场清单提供。扫描尾播放已采信记录的收件流。
