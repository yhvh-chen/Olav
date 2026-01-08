# 案例: crc-r1-interface-error

> **创建时间**: 2026-01-08
> **自动保存**: 由 OLAV Agent 根据成功案例自动生成

## 问题描述
R1 CRC错误

## 排查过程
1. 1. 添加Cisco IOS命令白名单，包括show interfaces counters errors, show interfaces, show logging
2. 2. 执行show ip interface brief检查接口状态
3. 3. 执行show interfaces counters errors识别高CRC接口
4. 4. 检查show logging相关日志
5. 5. 分析duplex/speed配置和物理连接

## 根因
物理层问题：光缆故障、SFP模块不兼容、速度/双工不匹配导致CRC错误计数持续增加。

## 解决方案
1. 检查并更换接口电缆或光模块。2. 确保两端速度/双工配置一致（推荐auto）。3. 验证光功率（show interfaces transceiver）。4. 若持续，替换接口卡。

## 关键命令
- show interfaces counters errors
- show ip interface brief
- show logging
- show interfaces
- show controllers

## 标签
#CRC #R1 #cisco_ios #物理层 #接口错误

## 相关案例
- 自动关联相似案例待实现
