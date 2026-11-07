"""PRD acceptance criterion 1 — an unapproved target is blocked, including via
redirect, DNS change and internal/metadata addresses."""

from __future__ import annotations

from pt_agent.scope import EgressValidator, normalize


def test_in_scope_allowed(scope):
    v = EgressValidator(scope)
    assert v.check("https://app.test.example/login").allowed


def test_out_of_scope_blocked(scope):
    v = EgressValidator(scope)
    d = v.check("https://evil.example/")
    assert not d.allowed
    assert "not in approved scope" in d.reason


def test_subdomain_not_implied(scope):
    """Subdomains are not implied — must be listed explicitly (section 9)."""
    v = EgressValidator(scope)
    assert not v.check("https://admin.app.test.example/").allowed


def test_scheme_and_port_must_match(scope):
    v = EgressValidator(scope)
    assert not v.check("http://app.test.example/").allowed          # wrong scheme
    assert not v.check("https://app.test.example:8443/").allowed     # wrong port


def test_redirect_revalidated(scope):
    v = EgressValidator(scope)
    assert not v.check_redirect(
        "https://app.test.example/", "https://evil.example/"
    ).allowed


def test_metadata_blocked(scope):
    v = EgressValidator(scope)
    assert not v.check("https://169.254.169.254/latest/meta-data/").allowed
    assert not v.check("https://metadata.google.internal/").allowed


def test_internal_ip_blocked(scope):
    v = EgressValidator(scope)
    for host in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "[::1]"):
        assert not v.check(f"https://{host}/").allowed


def test_unicode_lookalike_normalised():
    # IDNA collapses look-alike hosts so they can be compared safely.
    nt = normalize("https://xn--e1afmkfd.example/")
    assert nt.host == "xn--e1afmkfd.example"


def test_dns_rebinding_shape(scope):
    """A host that resolves to an internal literal is still compared as a host;
    an IP literal that is internal is blocked outright."""
    v = EgressValidator(scope)
    assert not v.check("https://0.0.0.0/").allowed


def test_localhost_literal_blocked(scope):
    scope.targets.append(__import__("pt_agent.models", fromlist=["TargetSpec"]).TargetSpec(scheme="http", host="localhost", ports=[8080]))
    assert not EgressValidator(scope).check("http://localhost:8080/").allowed


def test_resolved_internal_address_refused(scope):
    """Section 9: DNS must not move an approved host onto a forbidden address."""
    v = EgressValidator(scope)
    assert not v.check_resolved("app.test.example", ["10.0.0.9"]).allowed
    assert not v.check_resolved("app.test.example", ["169.254.169.254"]).allowed
    assert not v.check_resolved("app.test.example", []).allowed
    assert v.check_resolved("app.test.example", ["93.184.216.34"]).allowed
    assert EgressValidator(scope, allow_internal=True).check_resolved("x", ["127.0.0.1"]).allowed
