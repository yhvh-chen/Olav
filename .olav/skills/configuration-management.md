---
id: configuration-management
intent: config
complexity: complex
description: "Device configuration management and change execution, requires HITL approval"
examples:
  - "Modify VLAN configuration"
  - "Update BGP routing policy"
  - "Apply security policy"
enabled: true
---

# Configuration Management Skill

## Overview

Configuration management skill is used for device configuration changes and policy application.

### Use Cases

- Apply interface configuration
- Modify routing policy
- Update ACL
- Configure BGP parameters

### Execution Steps

1. ✅ Verify the reasonableness of changes
2. ⚠️ **Request manual approval** (HITL)
3. Apply configuration to device
4. Verify configuration takes effect
5. Save configuration

### Risk Level

**High - All configuration changes require manual approval**

### Related Commands

```
configure terminal
interface <name>
ip address <ip> <mask>
exit
copy running-config startup-config
```
