from __future__ import annotations


class BenchError(Exception):
    """Root exception for all bench service errors.

    Catch BenchError to handle any bench-specific failure without catching
    bare Exception.  All subclasses carry an actionable human-readable message.
    """


class VowViolationError(BenchError):
    """A BindingVow constraint is violated.

    Raised during vow validation or when a run violates the declared contract
    (e.g. technique not declared in the vow, version mismatch, invalid space
    specification, reward range inconsistency).
    """


class ManifestError(BenchError):
    """benchanything.json is missing, malformed, or fails schema validation.

    The message identifies the file path and the specific field or structural
    problem so the environment author can fix it immediately.
    """


class EnvironmentStartupError(BenchError):
    """An environment adapter failed to start or become healthy.

    Includes the subprocess stderr tail and the health-check URL so the
    environment author can diagnose their adapter without reading logs.
    """


class StorageError(BenchError):
    """A storage backend operation failed in an unexpected way.

    Wraps low-level DB / IO errors and surfaces the backend name so operators
    know which system to inspect.
    """
