from agentsty_sandbox.models import SandboxPolicy


def test_sandbox_policy_defaults_are_secure() -> None:
    policy = SandboxPolicy()

    assert policy.network.default_deny is True
    assert policy.writable_workspace is False
