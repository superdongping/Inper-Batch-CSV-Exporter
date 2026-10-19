V1.1正式发布版：以README.md为最新说明。

Inper Batch CSV Exporter V1.1
===========================

用于把 Inper fiber photometry 原始 data.db 批量整理为 CSV。
这是独立的导出工具，不依赖 Fiber Photometry Behavior Analyzer 的项目或 MATLAB。

开始使用
1. 将完整 ZIP 解压到普通工作目录。
2. 双击 Inper Batch CSV Exporter.exe（Windows 64-bit，无需安装 Python）。
   也可双击 START.bat。详细说明见 INSTRUCTION_zh-CN.txt。
3. Add batch 添加一个或多个“日期 + 实验内容/阶段”的批次目录。
4. Choose parent 选择输出父目录，并把路径末尾改成一个尚不存在的新目录名。
5. Scan 检查，确认记录与目录正确后 Export。
6. 只有 validation_summary.json 的 status 为 PASS 才表示整批完成。

主 CSV：与已核对的 Inper 样品格式一致；Time 为 410 时间，按样本序号配对。
详细 CSV：_details 内保留全部样本及独立 410/470 纳秒时间，不能删除。
默认复制 AVI 并核对 SHA256；可取消复制，仅在清单引用原视频。
不会覆盖已有输出，不写入源数据库，不生成/改写 Analyzer project.mat。

包内文件
- Inper Batch CSV Exporter.exe  Windows 图形界面
- START.bat                    启动入口
- INSTRUCTION_zh-CN.txt         完整流程、命名、格式、验收与错误处理
- AGENT_WORKFLOW.txt            下次交给助手执行时使用的 instruction
- QUICK_START_EN.txt            English quick start
- inper_exporter.py             独立核心与命令行（Python 3.10+，仅标准库）
- inper_exporter_gui.py         Tkinter GUI
- packaged_self_test.py         显式运行的纯合成诊断，不读实验数据
- tests/                        合成测试和可选旧批次对照工具
- build.ps1                     用 PyInstaller 重新打包
- VALIDATION.txt                本版验证范围和边界
- THIRD_PARTY_NOTICES.txt        打包运行时说明
- licenses/                     随包运行时许可证文本

本版支持：已验证的 Inper Camera SQLite 记录，410/470 nm、ROI-1...ROI-N。
其他波长、非 Camera 通道、不同记录结构会停止并报错，不能直接假定兼容。
本版没有用厂商 GUI 逐文件对照；基于此前本地厂商读取代码核实的解码规则，
并通过历史样品及已校验 CSV 的真实数据回归验证。

仅用于原始导出与整理：不滤波、不做基线校正、不计算 dF/F、不推断行为或组别。
源代码的公开许可证尚未由所有者指定；发布仓库为 superdongping/Inper-Batch-CSV-Exporter。
