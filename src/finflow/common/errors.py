"""Domain exceptions. Each one maps to a distinct operational response."""


class FinFlowError(Exception):
    """Base class for expected, explainable pipeline failures."""


class ConfigurationError(FinFlowError):
    """Missing or invalid configuration. Fix the environment and rerun."""


class SourceError(FinFlowError):
    """A source system could not be read after retries."""


class BronzeConflictError(FinFlowError):
    """A batch already exists in Bronze with different content.

    Raw data is write-once: we refuse to overwrite it silently.
    """


class QualityGateError(FinFlowError):
    """A critical data quality threshold was exceeded. Nothing was loaded."""


class SimulatedFailure(FinFlowError):
    """Raised on purpose (FINFLOW_FAIL_AT) to rehearse failure recovery."""
