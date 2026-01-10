# TextFSM 自定义模板目录

此目录用于存放用户自定义的 TextFSM 模板，**优先级高于 ntc-templates**。

## 使用方法

1. 创建 `index` 文件（必须）
2. 添加 `.textfsm` 模板文件
3. OLAV 会自动使用此目录

## index 文件格式

```
Template, Hostname, Platform, Command

cisco_ios_show_custom.textfsm, .*, cisco_ios, sh[[ow]] my-custom
huawei_vrp_dis_current.textfsm, .*, huawei_vrp, dis[[play]] cu[[rrent-configuration]]
```

**字段说明：**
- `Template`: 模板文件名
- `Hostname`: 主机名匹配（正则，`.*` 表示所有）
- `Platform`: 设备平台类型（如 `cisco_ios`, `huawei_vrp`）
- `Command`: 命令匹配模式，支持 `[[]]` 缩写语法

## 模板文件示例

`cisco_ios_show_custom.textfsm`:
```
Value INTERFACE (\S+)
Value STATUS (up|down)
Value IP_ADDRESS (\d+\.\d+\.\d+\.\d+)

Start
  ^${INTERFACE}\s+${STATUS}\s+${IP_ADDRESS} -> Record
```

## 常用平台名称

| 厂商 | Platform |
|------|----------|
| Cisco IOS | `cisco_ios` |
| Cisco IOS-XE | `cisco_xe` |
| Cisco NX-OS | `cisco_nxos` |
| Huawei VRP | `huawei_vrp` |
| Arista EOS | `arista_eos` |
| Juniper Junos | `juniper_junos` |

## 参考

- [NTC Templates](https://github.com/networktocode/ntc-templates)
- [TextFSM 语法](https://github.com/google/textfsm/wiki/TextFSM)
