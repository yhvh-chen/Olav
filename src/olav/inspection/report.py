"""Inspection Report Generator - Markdown reports with timestamps.

Generates human-friendly inspection reports in Markdown format:
- Summary statistics
- Device-by-device results
- Critical/warning/info categorization
- Timestamped filenames for versioning
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.settings import AgentConfig, InspectionConfig

if TYPE_CHECKING:
    from olav.inspection.runner import CheckResult


# i18n strings for reports
I18N = {
    "report_title": {
        "zh": "# 🔍 网络巡检报告",
        "en": "# 🔍 Network Inspection Report",
        "ja": "# 🔍 ネットワーク検査レポート",
    },
    "profile": {
        "zh": "**巡检配置**: {name}",
        "en": "**Profile**: {name}",
        "ja": "**プロファイル**: {name}",
    },
    "description": {
        "zh": "**描述**: {desc}",
        "en": "**Description**: {desc}",
        "ja": "**説明**: {desc}",
    },
    "run_time": {
        "zh": "**执行时间**: {start} → {end} ({duration:.1f}秒)",
        "en": "**Run Time**: {start} → {end} ({duration:.1f}s)",
        "ja": "**実行時間**: {start} → {end} ({duration:.1f}秒)",
    },
    "summary_title": {
        "zh": "## 📊 执行摘要",
        "en": "## 📊 Executive Summary",
        "ja": "## 📊 実行サマリー",
    },
    "devices": {
        "zh": "- **设备数**: {count}",
        "en": "- **Devices**: {count}",
        "ja": "- **デバイス数**: {count}",
    },
    "checks": {
        "zh": "- **检查项**: {count}",
        "en": "- **Checks**: {count}",
        "ja": "- **チェック項目**: {count}",
    },
    "total_results": {
        "zh": "- **总检查数**: {count}",
        "en": "- **Total Results**: {count}",
        "ja": "- **総結果数**: {count}",
    },
    "passed": {
        "zh": "- ✅ **通过**: {count} ({pct:.1f}%)",
        "en": "- ✅ **Passed**: {count} ({pct:.1f}%)",
        "ja": "- ✅ **成功**: {count} ({pct:.1f}%)",
    },
    "failed": {
        "zh": "- ❌ **失败**: {count} ({pct:.1f}%)",
        "en": "- ❌ **Failed**: {count} ({pct:.1f}%)",
        "ja": "- ❌ **失敗**: {count} ({pct:.1f}%)",
    },
    "status_healthy": {
        "zh": "### 🟢 整体状态: 健康",
        "en": "### 🟢 Overall Status: Healthy",
        "ja": "### 🟢 全体ステータス: 正常",
    },
    "status_warning": {
        "zh": "### 🟡 整体状态: 需要关注",
        "en": "### 🟡 Overall Status: Needs Attention",
        "ja": "### 🟡 全体ステータス: 要注意",
    },
    "status_critical": {
        "zh": "### 🔴 整体状态: 严重问题",
        "en": "### 🔴 Overall Status: Critical Issues",
        "ja": "### 🔴 全体ステータス: 重大な問題",
    },
    "critical_title": {
        "zh": "## 🚨 严重问题 ({count})",
        "en": "## 🚨 Critical Issues ({count})",
        "ja": "## 🚨 重大な問題 ({count})",
    },
    "warning_title": {
        "zh": "## ⚠️ 警告 ({count})",
        "en": "## ⚠️ Warnings ({count})",
        "ja": "## ⚠️ 警告 ({count})",
    },
    "info_title": {
        "zh": "## ℹ️ 信息 ({count})",
        "en": "## ℹ️ Information ({count})",
        "ja": "## ℹ️ 情報 ({count})",
    },
    "device_summary_title": {
        "zh": "## 📋 设备巡检结果",
        "en": "## 📋 Device Results",
        "ja": "## 📋 デバイス結果",
    },
    "table_header": {
        "zh": "| 设备 | 检查项 | 状态 | 说明 |",
        "en": "| Device | Check | Status | Message |",
        "ja": "| デバイス | チェック | ステータス | 説明 |",
    },
    "footer": {
        "zh": "---\n*报告生成时间: {time}*\n*OLAV 自动化巡检系统*",
        "en": "---\n*Report generated: {time}*\n*OLAV Automated Inspection System*",
        "ja": "---\n*レポート生成時刻: {time}*\n*OLAV 自動検査システム*",
    },
}


def tr(key: str, **kwargs: Any) -> str:
    """Get translated string."""
    lang = AgentConfig.LANGUAGE
    if key not in I18N:
        return key
    translations = I18N[key]
    text = translations.get(lang, translations.get("en", key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


class ReportGenerator:
    """Generate Markdown inspection reports."""

    def __init__(
        self,
        profile_name: str,
        description: str,
        results: list["CheckResult"],
        start_time: datetime,
        end_time: datetime,
        devices: list[str],
        checks: list[dict[str, Any]],
        language: str = "zh",
    ) -> None:
        self.profile_name = profile_name
        self.description = description
        self.results = results
        self.start_time = start_time
        self.end_time = end_time
        self.devices = devices
        self.checks = checks
        self.language = language
        AgentConfig.LANGUAGE = language  # type: ignore

    def _get_timestamp_str(self) -> str:
        """Get timestamp string for filename."""
        return self.start_time.strftime("%Y%m%d_%H%M%S")

    def _get_report_filename(self) -> str:
        """Generate report filename with timestamp."""
        ts = self._get_timestamp_str()
        return f"inspection_{self.profile_name}_{ts}.md"

    def generate(self) -> Path:
        """Generate Markdown report and save to file.

        Returns:
            Path to generated report file
        """
        content = self._build_content()

        # Save to reports directory
        reports_dir = InspectionConfig.get_reports_dir()
        filename = self._get_report_filename()
        report_path = reports_dir / filename

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)

        return report_path

    def _build_content(self) -> str:
        """Build full report content."""
        lines: list[str] = []

        # Header
        lines.append(tr("report_title"))
        lines.append("")
        lines.append(tr("profile", name=self.profile_name))
        lines.append(tr("description", desc=self.description))

        duration = (self.end_time - self.start_time).total_seconds()
        lines.append(
            tr(
                "run_time",
                start=self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end=self.end_time.strftime("%H:%M:%S"),
                duration=duration,
            )
        )
        lines.append("")

        # Summary
        lines.append(tr("summary_title"))
        lines.append("")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        critical = sum(1 for r in self.results if not r.passed and r.severity == "critical")
        warnings = sum(1 for r in self.results if not r.passed and r.severity == "warning")

        lines.append(tr("devices", count=len(self.devices)))
        lines.append(tr("checks", count=len(self.checks)))
        lines.append(tr("total_results", count=total))

        if total > 0:
            lines.append(tr("passed", count=passed, pct=100 * passed / total))
            lines.append(tr("failed", count=failed, pct=100 * failed / total))
        lines.append("")

        # Overall status
        if critical > 0:
            lines.append(tr("status_critical"))
        elif warnings > 0 or failed > 0:
            lines.append(tr("status_warning"))
        else:
            lines.append(tr("status_healthy"))
        lines.append("")

        # Critical issues
        critical_results = [r for r in self.results if not r.passed and r.severity == "critical"]
        if critical_results:
            lines.append(tr("critical_title", count=len(critical_results)))
            lines.append("")
            for r in critical_results:
                lines.append(f"- **{r.device}** / {r.check_name}: {r.message}")
            lines.append("")

        # Warnings
        warning_results = [r for r in self.results if not r.passed and r.severity == "warning"]
        if warning_results:
            lines.append(tr("warning_title", count=len(warning_results)))
            lines.append("")
            for r in warning_results:
                lines.append(f"- **{r.device}** / {r.check_name}: {r.message}")
            lines.append("")

        # Device summary table
        lines.append(tr("device_summary_title"))
        lines.append("")
        lines.append(tr("table_header"))
        lines.append("|---|---|---|---|")

        for r in self.results:
            status = "✅" if r.passed else ("🔴" if r.severity == "critical" else "⚠️")
            # Truncate long messages
            msg = r.message[:60] + "..." if len(r.message) > 60 else r.message
            lines.append(f"| {r.device} | {r.check_name} | {status} | {msg} |")

        lines.append("")

        # Footer
        lines.append(tr("footer", time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Export report data as dict (for JSON output)."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)

        return {
            "profile": self.profile_name,
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": (self.end_time - self.start_time).total_seconds(),
            "devices": self.devices,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": passed / total if total > 0 else 0,
            },
            "results": [r.to_dict() for r in self.results],
        }
