"""PT Agent — governance core for an authorized penetration-testing platform.

This package implements the *governance and safety* layer described in the
product requirements document (``docs/PT_Agent_PRD_HE.md``): scope contracts,
the blocking policy engine, egress/target enforcement, evidence redaction, the
evidence vault, findings, and report generation.

It deliberately does **not** ship active exploitation tooling. Following the
PRD architecture (section 15), test execution is isolated behind the Tool
Gateway / Runner interface; only approved, schema-bound modules may run, and
only the Egress service may emit network requests. The modules shipped here are
passive/structural reference stubs.
"""

__version__ = "0.1.0"
