# 案例: test-group-health-inspection-20260108

> **创建时间**: 2026-01-09
> **自动保存**: 由 OLAV Agent 根据成功案例自动生成

## 问题描述
设备健康检查 - 全test组L1-L4巡检

## 排查过程
1. list_devices(group=test)
2. smart_query多命令批量执行
3. 分析CPU/内存/接口/OSPF
4. 生成报告

## 根因
R1连接问题; 虚拟设备命令兼容低

## 解决方案
报告生成; 建议修复R1连接

## 关键命令
- show version
- show processes cpu
- show ip interface brief
- show vlan
- show ip ospf neighbor

## 标签
#健康检查 #L1-L4 #test组 #巡检

## 相关案例
- 自动关联相似案例待实现
