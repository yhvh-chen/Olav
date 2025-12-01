/**
 * Simple i18n translations for OLAV WebGUI
 * No external dependencies, just a simple object lookup
 */

export type Language = 'en' | 'zh';

export const translations = {
  en: {
    // Chat page
    'chat.title': 'OLAV Chat',
    'chat.welcome': '👋 Hello! I am OLAV',
    'chat.welcome_subtitle': 'Enterprise Network Operations Assistant. How can I help you?',
    'chat.placeholder': 'Type your question, e.g., Check BGP status of R1',
    'chat.thinking': 'Thinking...',
    'chat.cancelled': 'Response cancelled by user',
    
    // Sidebar
    'sidebar.new_chat': 'New Chat',
    'sidebar.settings': 'Settings',
    'sidebar.sessions': 'sessions',
    'sidebar.no_sessions': 'No sessions found',
    'sidebar.start_new': 'Start a new conversation',
    'sidebar.yesterday': 'Yesterday',
    'sidebar.days_ago': 'days ago',
    'sidebar.delete_confirm': 'Delete this session?',
    'sidebar.cancel': 'Cancel',
    'sidebar.delete': 'Delete',
    
    // Settings
    'settings.title': 'Settings',
    'settings.language': 'Language / 语言',
    'settings.llm_config': 'LLM Configuration',
    'settings.llm_readonly': '(Read-only, restart server to change)',
    'settings.version': 'Version',
    'settings.environment': 'Environment',
    'settings.expert_mode': 'Expert Mode',
    'settings.agentic_rag': 'Agentic RAG',
    'settings.streaming': 'Streaming',
    'settings.workflows': 'Workflows',
    'settings.available': 'available',
    'settings.enabled': '✓ Enabled',
    'settings.disabled': '✗ Disabled',
    'settings.limits': 'Limits',
    'settings.max_query': 'Max Query Length',
    'settings.session_timeout': 'Session Timeout',
    'settings.rate_limit': 'Rate Limit',
    'settings.chars': 'chars',
    'settings.min': 'min',
    'settings.req_min': 'req/min',
    'settings.done': 'Done',
    'settings.load_failed': 'Failed to load configuration',
    
    // HITL
    'hitl.approval_required': 'Execution Plan Requires Approval',
    'hitl.target_device': 'Target Device',
    'hitl.operation': 'Operation',
    'hitl.commands': 'Commands to Execute',
    'hitl.risk_level': 'Risk Level',
    'hitl.cancel': 'Cancel',
    'hitl.approve': 'Approve & Execute',
    'hitl.approved': '✅ Operation approved, executing...',
    'hitl.rejected': '❌ Operation rejected',
    
    // Tools
    'tools.thinking_process': 'Thinking Process',
    'tools.executing': 'Executing Tool',
    'tools.execution_log': 'Execution Log',
    'tools.events': 'events',
    'tools.running': 'Running',
    'tools.hide': 'Hide',
    'tools.show': 'Show',
  },
  zh: {
    // Chat page
    'chat.title': 'OLAV 对话',
    'chat.welcome': '👋 你好！我是 OLAV',
    'chat.welcome_subtitle': '企业网络运维助手。有什么可以帮助您的？',
    'chat.placeholder': '输入您的问题，例如：查询 R1 的 BGP 状态',
    'chat.thinking': '思考中...',
    'chat.cancelled': '已取消响应',
    
    // Sidebar
    'sidebar.new_chat': '新对话',
    'sidebar.settings': '设置',
    'sidebar.sessions': '个会话',
    'sidebar.no_sessions': '暂无会话记录',
    'sidebar.start_new': '开始新对话',
    'sidebar.yesterday': '昨天',
    'sidebar.days_ago': '天前',
    'sidebar.delete_confirm': '确定删除此会话？',
    'sidebar.cancel': '取消',
    'sidebar.delete': '删除',
    
    // Settings
    'settings.title': '设置',
    'settings.language': 'Language / 语言',
    'settings.llm_config': 'LLM 配置',
    'settings.llm_readonly': '（只读，需重启服务器修改）',
    'settings.version': '版本',
    'settings.environment': '环境',
    'settings.expert_mode': '专家模式',
    'settings.agentic_rag': '智能 RAG',
    'settings.streaming': '流式输出',
    'settings.workflows': '工作流',
    'settings.available': '可用',
    'settings.enabled': '✓ 已启用',
    'settings.disabled': '✗ 已禁用',
    'settings.limits': '限制',
    'settings.max_query': '最大查询长度',
    'settings.session_timeout': '会话超时',
    'settings.rate_limit': '速率限制',
    'settings.chars': '字符',
    'settings.min': '分钟',
    'settings.req_min': '次/分钟',
    'settings.done': '完成',
    'settings.load_failed': '加载配置失败',
    
    // HITL
    'hitl.approval_required': '执行计划需要审批',
    'hitl.target_device': '目标设备',
    'hitl.operation': '操作类型',
    'hitl.commands': '待执行命令',
    'hitl.risk_level': '风险等级',
    'hitl.cancel': '取消',
    'hitl.approve': '批准并执行',
    'hitl.approved': '✅ 操作已批准，正在执行...',
    'hitl.rejected': '❌ 操作已拒绝',
    
    // Tools
    'tools.thinking_process': '思考过程',
    'tools.executing': '正在执行工具',
    'tools.execution_log': '执行日志',
    'tools.events': '个事件',
    'tools.running': '运行中',
    'tools.hide': '收起',
    'tools.show': '展开',
  },
} as const;

export type TranslationKey = keyof typeof translations.en;

export function t(key: TranslationKey, lang: Language): string {
  return translations[lang][key] || translations.en[key] || key;
}
